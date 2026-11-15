from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from threading import Thread

from flask import Flask, g, jsonify, render_template, request, send_from_directory

from wt_plotter.capture.capturer import Capturer
from wt_plotter.config import APP_SETTINGS, CAPTURE_DEFAULTS
from wt_plotter.i18n import LANGUAGES, get_language, language_names, load_catalog, set_language, translate
from wt_plotter.maps.lookup import lookup_map
from wt_plotter.storage import db


BATTLE_ICONS = {
    "air": "✈️",
    "ground": "🚜",
    "naval": "⛵",
    "air_in_ground": "🚜 ✈️",
    "air_in_naval": "⛵ ✈️",
    "unknown": "",
}


def create_app(db_path: Path, maps_dir: Path, settings_path: Path, capturer: Capturer | None) -> Flask:
    app = Flask(__name__)
    maps_dir = maps_dir.resolve()

    def connection():
        if "db" not in g:
            g.db = db.connect(db_path)
        return g.db

    @app.teardown_appcontext
    def close_db(error):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    @app.before_request
    def read_language():
        g.lang = get_language(settings_path)

    def t(key, **params):
        return translate(g.lang, key, **params)

    @app.context_processor
    def language_context():
        return {"lang": g.lang, "catalog": load_catalog(g.lang), "languages": language_names(), "t": t, "icons": BATTLE_ICONS}

    @app.template_filter("dt")
    def format_datetime(value):
        return datetime.fromisoformat(value).strftime(APP_SETTINGS.datetime_format)

    def map_metadata(dhash):
        info = lookup_map(dhash or "")
        return {"map_id": info.map_id, "battle_type": info.battle_type.value, "map_name": t(f"map.{info.map_id}")}

    def match_summary(match):
        return {
            "id": match.id, "started_at": match.started_at, "ended_at": match.ended_at,
            "nuke_detected": match.nuke_detected, "initial_capture_count": match.initial_capture_count,
            "initial_capture_x": match.initial_capture_x, "initial_capture_y": match.initial_capture_y,
            **map_metadata(match.map_hash),
        }

    def match_page_data(match):
        payload = match_summary(match)
        payload["air_map"] = map_metadata(match.air_map_hash) if match.air_map_hash else None
        return payload

    def default_map(match):
        # 有空战图且第一次出击是飞机时默认显示空战图。
        if not match.air_map_hash:
            return "ground"
        army = db.first_sortie_army(connection(), match.id, CAPTURE_DEFAULTS.placeholder_vehicles)
        return "air" if army == CAPTURE_DEFAULTS.air_army_type else "ground"

    def render_match(match, is_live):
        return render_template(
            "match.html", match=match_page_data(match), is_live=is_live, default_map=default_map(match),
        )

    @app.get("/")
    def index():
        conn = connection()
        matches = []
        for match in db.get_all_matches(conn):
            start = datetime.fromisoformat(match.started_at)
            end = datetime.fromisoformat(match.ended_at) if match.ended_at else datetime.now()
            matches.append({
                **match_page_data(match),
                "duration_seconds": max(0, int((end - start).total_seconds())),
                "position_count": db.count_positions(conn, match.id),
            })
        return render_template("index.html", matches=matches)

    @app.get("/match/<int:match_id>")
    def match_view(match_id):
        match = db.get_match(connection(), match_id)
        if match is None:
            return t("match.not_found"), 404
        return render_match(match, match.ended_at is None)

    @app.get("/live")
    def live_view():
        match = db.get_active_match(connection())
        if match is None:
            return render_template("waiting.html")
        return render_match(match, True)

    @app.get("/api/matches")
    def api_matches():
        conn = connection()
        return jsonify([
            {**match_summary(match), "position_count": db.count_positions(conn, match.id)}
            for match in db.get_all_matches(conn)
        ])

    @app.get("/api/match/<int:match_id>")
    def api_match(match_id):
        match = db.get_match(connection(), match_id)
        if match is None:
            return jsonify(error="match_not_found"), 404
        payload = asdict(match)
        del payload["air_map_hash"]
        return jsonify(payload | map_metadata(match.map_hash))

    @app.delete("/api/match/<int:match_id>")
    def api_delete_match(match_id):
        conn = connection()
        match = db.get_match(conn, match_id)
        if match is None:
            return jsonify(error="match_not_found"), 404
        if match.ended_at is None:
            return jsonify(error="cannot_delete_active"), 400
        db.delete_match(conn, match_id)
        return jsonify(success=True)

    @app.get("/api/match/<int:match_id>/positions")
    def api_positions(match_id):
        raw = request.args.get("since", "0")
        try:
            since = int(float(raw) * 1000) if "." in raw else int(raw)
        except (ValueError, OverflowError):
            since = 0
        return jsonify(db.get_positions_bundle(connection(), match_id, since))

    @app.get("/api/match/<int:match_id>/events")
    def api_events(match_id):
        since = request.args.get("since", 0, type=int)
        return jsonify(db.get_events(connection(), match_id, since))

    @app.get("/api/match/<int:match_id>/map.png")
    def api_map_image(match_id):
        match = db.get_match(connection(), match_id)
        if match is None:
            return "", 404
        map_hash = match.air_map_hash if request.args.get("kind") == "air" else match.map_hash
        if not map_hash:
            return "", 404
        map_id = lookup_map(map_hash).map_id
        key = map_hash if map_id in ("unknown", "no_map") else map_id
        return send_from_directory(maps_dir, f"{key}.png", mimetype="image/png")

    @app.get("/api/active")
    def api_active():
        active = db.get_active_match(connection())
        if active is None:
            return jsonify(None)
        return jsonify(id=active.id, started_at=active.started_at, **map_metadata(active.map_hash))

    @app.get("/api/status")
    def api_status():
        conn = connection()
        active = db.get_active_match(conn)
        # 有本地采集器就读它；没有（serve 模式）就读当前比赛的最新 tick。
        army = capturer.army_type if capturer else None
        vehicle = capturer.vehicle_type if capturer else None
        if active and (not army or not vehicle):
            tick = db.get_latest_tick(conn, active.id)
            if tick:
                army = army or tick.army_type
                vehicle = vehicle or tick.vehicle_type
        return jsonify(
            capturing=capturer.is_running if capturer else False,
            active_match_id=active.id if active else None,
            army_type=army or CAPTURE_DEFAULTS.army_type,
            vehicle_type=vehicle or CAPTURE_DEFAULTS.vehicle_type,
        )

    @app.post("/api/language")
    def api_language():
        data = request.get_json(silent=True)
        language = data.get("language") if isinstance(data, dict) else None
        if language not in LANGUAGES:
            return jsonify(error="unknown_language"), 400
        set_language(settings_path, language)
        return "", 204

    @app.post("/shutdown")
    def shutdown():
        Thread(target=app.config["SHUTDOWN"], name="WT Plotter Shutdown").start()
        return jsonify(success=True)

    return app
