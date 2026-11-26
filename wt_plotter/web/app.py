from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
import re
from threading import Thread

from flask import Flask, g, jsonify, render_template, request, send_from_directory

from wt_plotter.capture.capturer import Capturer
from wt_plotter.config import APP_SETTINGS, CAPTURE_DEFAULTS, CAPTURE_FILTERS, PATHS
from wt_plotter.i18n import LANGUAGES, get_language, language_names, load_catalog, set_language, translate
from wt_plotter.maps.lookup import image_key, is_ground_battle, is_naval_battle, level_map_id, lookup_map
from wt_plotter.maps.table import BattleType, UNKNOWN_MAP
from wt_plotter.replay import download, importer
from wt_plotter.storage import db


BATTLE_ICONS = {
    "air": "✈️",
    "ground": "🚜",
    "naval": "⛵",
    "air_in_ground": "🚜 ✈️",
    "air_in_naval": "⛵ ✈️",
    "unknown": "",
}

HISTORY_MODES = {
    BattleType.GROUND.value: (BattleType.GROUND.value, BattleType.AIR_IN_GROUND.value),
    BattleType.AIR.value: (BattleType.AIR.value,),
    BattleType.NAVAL.value: (BattleType.NAVAL.value, BattleType.AIR_IN_NAVAL.value),
}

PLAYER_LEFT = re.compile(r"\s*(?:已\u200b?掉\u200b?线[。.]?|td! kd\?NET_PLAYER_DISCONNECT_FROM_GAME)\s*$")


def format_vehicle_name(raw: str) -> str:
    """将原始载具标识转为展示名。"""
    return raw.rsplit("/", 1)[-1].replace("_", " ")


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

    def is_air_battle(match):
        # 混合地图开局时 8111 先给地面图；有空战图且第一次出击是飞机，就是空战。
        if not match.air_map_hash:
            return False
        army = db.first_sortie_army(connection(), match.id, CAPTURE_DEFAULTS.placeholder_vehicles)
        return army == CAPTURE_DEFAULTS.air_army_type

    def match_summary(match, nuke_ids=None, replay_levels=None, naval_ids=None):
        info = map_metadata(match.map_hash)
        if naval_ids is None:
            naval_ids = db.get_naval_spawn_match_ids(connection(), CAPTURE_FILTERS.naval_spawn_types)
        if info["battle_type"] == BattleType.UNKNOWN.value and match.id in naval_ids:
            info["battle_type"] = BattleType.NAVAL.value
        levels = db.get_replay_levels(connection()) if replay_levels is None else replay_levels
        if match.id in levels:
            # 没有截图哈希的录像比赛，用录像记录的关卡补上地图名和战斗类型。
            level, battle_class = levels[match.id]
            map_id = level_map_id(level, battle_class)
            if info["map_id"] == UNKNOWN_MAP.map_id and map_id:
                info.update(map_id=map_id, map_name=t(f"map.{map_id}"))
            if info["battle_type"] == BattleType.UNKNOWN.value:
                if is_ground_battle(battle_class):
                    info["battle_type"] = BattleType.GROUND.value
                elif is_naval_battle(battle_class):
                    info["battle_type"] = BattleType.NAVAL.value
                else:
                    info["battle_type"] = BattleType.AIR.value
        nuke = bool(match.nuke_detected) or (
            match.id in nuke_ids if nuke_ids is not None else db.has_nuke_event(connection(), match.id)
        )
        return {
            "id": match.id, "started_at": match.started_at, "ended_at": match.ended_at,
            "nuke_detected": int(nuke), "initial_capture_count": match.initial_capture_count,
            "initial_capture_x": match.initial_capture_x, "initial_capture_y": match.initial_capture_y,
            **info,
            "mode": BattleType.AIR.value if is_air_battle(match) else info["battle_type"],
        }

    def map_label(info, mode):
        return f"{BATTLE_ICONS[mode]} {info['map_name']}".strip()

    def match_page_data(match, nuke_ids=None, replay_levels=None, naval_ids=None):
        payload = match_summary(match, nuke_ids, replay_levels, naval_ids)
        air_map = map_metadata(match.air_map_hash) if match.air_map_hash else None
        has_air_view = bool(air_map) or db.has_air_view(connection(), match.id)
        return {
            **payload,
            "air_map": air_map,
            "has_air_view": has_air_view,
            "replay_tracks": db.tracks_writer(connection(), match.id) is not None,
            "default_map": "air" if air_map and payload["mode"] == BattleType.AIR.value else "ground",
            "mode_label": t(f"battle_type.{payload['mode']}"),
            "map_title": map_label(payload, payload["mode"]),
            "map_label": t("match.map", name=map_label(payload, payload["battle_type"])),
            "air_map_label": t("match.air_map", name=map_label(air_map, air_map["battle_type"])) if air_map else "",
        }

    @app.template_filter("vehicle")
    def vehicle_filter(raw):
        return format_vehicle_name(raw)

    @app.template_filter("clock")
    def clock_filter(ms):
        seconds = ms // 1000
        return f"{seconds // 60}:{seconds % 60:02d}"

    def render_match(match, is_live):
        return render_template(
            "match.html", match=match_page_data(match), is_live=is_live,
            placeholder_vehicles=CAPTURE_DEFAULTS.placeholder_vehicles,
            report=db.get_replay_report(connection(), match.id),
        )

    @app.get("/")
    def index():
        conn = connection()
        selected_date = request.args.get("date", type=date.fromisoformat)
        map_query = request.args.get("map", "").strip()
        map_search = map_query.casefold()
        selected_mode = request.args.get("mode", "")
        allowed_modes = HISTORY_MODES.get(selected_mode, ())
        vehicles_by_match = db.get_match_vehicles(conn, CAPTURE_DEFAULTS.placeholder_vehicles)
        replay_levels = db.get_replay_levels(conn)
        nuke_ids = db.get_nuke_event_match_ids(conn)
        naval_ids = db.get_naval_spawn_match_ids(conn, CAPTURE_FILTERS.naval_spawn_types)
        position_counts = db.get_position_counts(conn)
        matches_by_date = {}
        for match in db.get_all_matches(conn):
            start = datetime.fromisoformat(match.started_at)
            day = start.date()
            if selected_date and day != selected_date:
                continue

            info = match_page_data(match, nuke_ids, replay_levels, naval_ids)
            if allowed_modes and info["mode"] not in allowed_modes:
                continue
            if map_search:
                names = [info["map_name"]]
                if info["air_map"]:
                    names.append(info["air_map"]["map_name"])
                if not any(map_search in name.casefold() for name in names):
                    continue

            end = datetime.fromisoformat(match.ended_at) if match.ended_at else datetime.now()
            map_hash = match.air_map_hash if info["default_map"] == "air" else match.map_hash
            matches_by_date.setdefault(day, []).append({
                **info,
                "start_time": start.strftime("%H:%M"),
                "duration_seconds": max(0, int((end - start).total_seconds())),
                "position_count": position_counts.get(match.id, 0),
                "vehicles": [format_vehicle_name(v) for v in vehicles_by_match.get(match.id, ())],
                "has_map_image": bool(map_hash),
                "has_replay": match.id in replay_levels,
            })
        return render_template(
            "index.html", matches_by_date=matches_by_date, selected_date=selected_date,
            map_query=map_query, selected_mode=selected_mode if allowed_modes else "",
            modes={mode: t(f"battle_type.{mode}") for mode in HISTORY_MODES},
            match_count=sum(map(len, matches_by_date.values())),
        )

    @app.get("/match/<int:match_id>")
    def match_view(match_id):
        match = db.get_match(connection(), match_id)
        if match is None:
            return t("match.not_found"), 404
        # 文件夹导入只读了录像摘要，第一次打开时完整解析（击杀、聊天、轨迹）。
        importer.ensure_parsed(connection(), match_id, g.lang)
        return render_match(db.get_match(connection(), match_id), match.ended_at is None)

    @app.get("/match/<int:match_id>/scoreboard")
    def match_scoreboard(match_id):
        """历史战局下拉栏里的录像战绩；只读已导入的摘要，不触发完整解析。"""
        report = db.get_replay_report(connection(), match_id)
        if report is None:
            return "", 404
        return render_template("_scoreboard.html", report=report)

    @app.get("/live")
    def live_view():
        match = db.get_active_match(connection())
        if match is None:
            return render_template("waiting.html")
        return render_match(match, True)

    @app.get("/api/matches")
    def api_matches():
        conn = connection()
        nuke_ids = db.get_nuke_event_match_ids(conn)
        naval_ids = db.get_naval_spawn_match_ids(conn, CAPTURE_FILTERS.naval_spawn_types)
        position_counts = db.get_position_counts(conn)
        return jsonify([
            {**match_summary(match, nuke_ids, naval_ids=naval_ids), "position_count": position_counts.get(match.id, 0)}
            for match in db.get_all_matches(conn)
        ])

    @app.get("/api/match/<int:match_id>")
    def api_match(match_id):
        match = db.get_match(connection(), match_id)
        if match is None:
            return jsonify(error="match_not_found"), 404
        payload = asdict(match)
        del payload["air_map_hash"]
        return jsonify(payload | match_page_data(match))

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
        events = []
        departures = set()
        for event in db.get_events(connection(), match_id, since):
            suffix = PLAYER_LEFT.search(event["msg"])
            if suffix:
                player = event["msg"][:suffix.start()]
                # 游戏可能在同一批次同时发送本地化消息和原始消息。
                key = (event["timestamp"], player)
                if key in departures:
                    continue
                departures.add(key)
                event["msg"] = t("viewer.player_left", player=player)
            events.append(event)
        return jsonify(events)

    @app.get("/api/match/<int:match_id>/replay")
    def api_replay(match_id):
        report = db.get_replay_report(connection(), match_id)
        if report is None:
            return jsonify(error="replay_not_found"), 404
        return jsonify(report)

    @app.post("/api/replays/import")
    def api_import_replays():
        # 可以是录像文件夹，也可以是单个录像文件或服务器录像的分段目录。
        path = Path(request.get_json()["path"])
        if not path.exists():
            return jsonify(error="replay_folder_not_found"), 400
        match_ids, errors = importer.import_new(connection(), [path])
        return jsonify(imported=len(match_ids), errors=errors)

    @app.post("/api/replays/upload")
    def api_upload_replays():
        """手动选择的录像（不在游戏录像目录里的）：先存进数据目录，再按文件夹导入的方式导入。"""
        files = [(file.filename, file.read()) for file in request.files.getlist("files")]
        sources, errors = importer.store_uploads(files, PATHS.replays_dir)
        match_ids, import_errors = importer.import_new(connection(), sources)
        errors += import_errors
        # 只选了一份录像就直接打开它（之前导入过的也一样）。
        if len(sources) == 1 and not errors:
            return jsonify(match_id=db.find_replay_match(connection(), importer.read_header(sources[0]).session_hex))
        return jsonify(imported=len(match_ids), errors=errors)

    @app.post("/api/replays/download")
    def api_download_replay():
        try:
            session = download.parse_session(request.get_json()["session"])
        except ValueError:
            return jsonify(error="bad_session"), 400
        try:
            folder = download.download_server_replay(session, PATHS.replays_dir)
        except FileNotFoundError:
            return jsonify(error="server_replay_not_found"), 404
        match_id = importer.import_replay(connection(), importer.load_path(folder), str(folder), g.lang)
        return jsonify(match_id=match_id)

    @app.get("/api/match/<int:match_id>/map.png")
    def api_map_image(match_id):
        match = db.get_match(connection(), match_id)
        if match is None:
            return "", 404
        map_hash = match.air_map_hash if request.args.get("kind") == "air" else match.map_hash
        if not map_hash:
            return "", 404
        return send_from_directory(maps_dir, f"{image_key(map_hash)}.png", mimetype="image/png")

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
