from contextlib import closing
import io
from threading import Event

import pytest

from wt_plotter.config import PATHS
from wt_plotter.i18n import set_language, translate
from wt_plotter.maps.table import MAPS, BattleType
from wt_plotter.storage import db
from wt_plotter.web.app import create_app


MAP_ID = "avg_normandy_tankmap"
MAP_HASH = next(key for key, info in MAPS.items() if info.map_id == MAP_ID and info.battle_type is BattleType.GROUND)
AIR_MAP_ID = "avg_egypt_sinai_map"
AIR_MAP_HASH = next(key for key, info in MAPS.items() if info.map_id == AIR_MAP_ID)


@pytest.fixture
def app(tmp_path):
    settings = tmp_path / "settings.json"
    set_language(settings, "en")
    return create_app(tmp_path / "matches.db", tmp_path / "maps", settings, None)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def conn(tmp_path):
    with closing(db.connect(tmp_path / "matches.db")) as connection:
        yield connection


@pytest.fixture
def match_id(conn):
    return db.start_match(conn, MAP_HASH)


def test_index_empty(client):
    assert client.get("/").status_code == 200


def test_index_groups_and_filters_by_local_start_date(client, conn):
    dates = ("2026-11-17T23:55:00", "2026-11-18T00:05:00", "2026-11-18T15:00:00")
    older, first, latest = [db.start_match(conn, MAP_HASH) for _ in dates]
    with conn:
        conn.executemany(
            "UPDATE matches SET started_at = ? WHERE id = ?", zip(dates, (older, first, latest))
        )

    overview = client.get("/").text
    assert overview.index('datetime="2026-11-18"') < overview.index('datetime="2026-11-17"')
    numbers = [f'<span class="match-number">#{match_id}</span>' for match_id in (latest, first, older)]
    assert [overview.index(number) for number in numbers] == sorted(overview.index(number) for number in numbers)

    filtered = client.get("/", query_string={"date": "2026-11-18"}).text
    assert 'name="date" value="2026-11-18"' in filtered
    assert numbers[0] in filtered and numbers[1] in filtered and numbers[2] not in filtered
    empty = client.get("/", query_string={"date": "2026-11-16"}).text
    assert translate("en", "index.no_matches_on_date") in empty


def test_api_matches(client, match_id):
    match, = client.get("/api/matches").json
    assert match["id"] == match_id
    assert match["map_id"] == MAP_ID
    assert match["battle_type"] == "ground"
    assert match["map_name"] == translate("en", f"map.{MAP_ID}")


def test_map_name_follows_language(client, match_id, monkeypatch):
    from wt_plotter.i18n import load_catalog

    monkeypatch.setitem(load_catalog("zh"), f"map.{MAP_ID}", "诺曼底")
    assert client.post("/api/language", json={"language": "zh"}).status_code == 204
    assert client.get("/api/matches").json[0]["map_name"] == translate("zh", f"map.{MAP_ID}")
    assert client.post("/api/language", json={"language": "en"}).status_code == 204
    assert client.get("/api/matches").json[0]["map_name"] == translate("en", f"map.{MAP_ID}")


def test_language_unknown(client):
    response = client.post("/api/language", json={"language": "fr"})
    assert response.status_code == 400
    assert response.json == {"error": "unknown_language"}


def test_match_not_found(client):
    response = client.get("/api/match/999")
    assert response.status_code == 404
    assert response.json == {"error": "match_not_found"}
    assert client.get("/match/999").status_code == 404


def test_delete_active_rejected(client, match_id):
    response = client.delete(f"/api/match/{match_id}")
    assert response.status_code == 400
    assert response.json == {"error": "cannot_delete_active"}


def test_delete_ended(client, conn, match_id):
    db.end_match(conn, match_id)
    assert client.delete(f"/api/match/{match_id}").status_code == 200
    assert client.get(f"/api/match/{match_id}").status_code == 404


def test_positions_since(client, conn, match_id):
    position = db.PositionRecord(0.5, 0.5, "#fa0c00", "ground_model", "Tank", 0)
    for timestamp in (1.0, 1.5):
        db.add_tick(conn, match_id, db.TickRecord(timestamp, "tank", "", 0, 0), [position])
    url = f"/api/match/{match_id}/positions"
    seconds = client.get(url, query_string={"since": "1.5"})
    milliseconds = client.get(url, query_string={"since": 1500})
    assert seconds.status_code == milliseconds.status_code == 200
    assert seconds.json == milliseconds.json
    assert [tick["timestamp"] for tick in seconds.json["ticks"]] == [1500]


def test_map_png(client, match_id, tmp_path):
    url = f"/api/match/{match_id}/map.png"
    assert client.get(url).status_code == 404
    path = tmp_path / "maps" / f"{MAP_ID}.png"
    path.parent.mkdir()
    path.write_bytes((PATHS.maps_dir / path.name).read_bytes())
    response = client.get(url)
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.data == path.read_bytes()


def test_live_waiting(client):
    response = client.get("/live")
    assert response.status_code == 200
    assert translate("en", "waiting.title") in response.text


def test_status_without_capturer(client):
    status = client.get("/api/status").json
    assert status["capturing"] is False
    assert status.keys() >= {"army_type", "vehicle_type", "active_match_id"}


def test_shutdown_calls_hook(app, client):
    hook = Event()
    app.config["SHUTDOWN"] = hook.set
    response = client.post("/shutdown")
    assert response.status_code == 200
    assert response.json == {"success": True}
    assert hook.wait(1)


def test_status_without_capturer_reads_latest_tick(client, conn, match_id):
    db.add_tick(
        conn, match_id, db.TickRecord(1.0, "air", "test_plane", 1, 1),
        [db.PositionRecord(0.3, 0.4, "#fff", "aircraft", "Player", 0)],
    )
    status = client.get("/api/status").json
    assert (status["army_type"], status["vehicle_type"]) == ("air", "test_plane")


def _copy_map(tmp_path, map_id):
    path = tmp_path / "maps" / f"{map_id}.png"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes((PATHS.maps_dir / path.name).read_bytes())
    return path


def test_map_png_air_kind(client, conn, match_id, tmp_path):
    url = f"/api/match/{match_id}/map.png"
    _copy_map(tmp_path, MAP_ID)
    assert client.get(url, query_string={"kind": "air"}).status_code == 404
    db.set_air_map(conn, match_id, AIR_MAP_HASH)
    path = _copy_map(tmp_path, AIR_MAP_ID)
    response = client.get(url, query_string={"kind": "air"})
    assert response.status_code == 200
    assert response.data == path.read_bytes()


def _sortie(conn, match_id, army, vehicle):
    position = db.PositionRecord(0.5, 0.5, "#fa0c00", "ground_model", "Tank", 0)
    db.add_tick(conn, match_id, db.TickRecord(0.0, "air", "dummy_plane", 1, 0), [position])
    db.add_tick(conn, match_id, db.TickRecord(1.0, army, vehicle, int(army == "air"), int(army == "air")), [position])


@pytest.mark.parametrize("army, vehicle, expected", [("air", "f-4s", "air"), ("tank", "germ_hummel", "ground")])
def test_default_map_follows_first_sortie(client, conn, match_id, army, vehicle, expected):
    _sortie(conn, match_id, army, vehicle)
    for path in (f"/match/{match_id}", "/live"):
        assert 'data-default-map="ground"' in client.get(path).text
    metadata = client.get(f"/api/match/{match_id}").json
    assert metadata["air_map"] is None
    assert metadata["default_map"] == "ground"
    db.set_air_map(conn, match_id, AIR_MAP_HASH)
    for path in (f"/match/{match_id}", "/live"):
        text = client.get(path).text
        assert f'data-default-map="{expected}"' in text
        assert 'data-has-air-map="true"' in text
    metadata = client.get(f"/api/match/{match_id}").json
    assert metadata["air_map"]["map_id"] == AIR_MAP_ID
    assert metadata["default_map"] == expected


def test_events_since(client, conn, match_id):
    db.add_events(conn, match_id, [db.EventRecord(1.0, 1, "first", "{}"), db.EventRecord(3.0, 2, "second", "{}")])
    response = client.get(f"/api/match/{match_id}/events", query_string={"since": 2000})
    assert response.status_code == 200
    assert response.json == [{"timestamp": 3000, "msg": "second"}]


@pytest.mark.parametrize("lang, message", [("zh", "Pilot 已离开战局"), ("en", "Pilot left the match")])
def test_events_localize_departures_in_old_recordings(client, conn, match_id, lang, message):
    raw = "Pilottd! kd?NET_PLAYER_DISCONNECT_FROM_GAME"
    db.add_events(conn, match_id, [
        db.EventRecord(1.0, 1, "Pilot已掉线。", "{}"),
        db.EventRecord(1.0, 2, raw, "{}"),
        db.EventRecord(1.0, 3, "Other message", "{}"),
        db.EventRecord(2.0, 4, raw, "{}"),
    ])
    client.post("/api/language", json={"language": lang})
    assert client.get(f"/api/match/{match_id}/events").json == [
        {"timestamp": 1000, "msg": message},
        {"timestamp": 1000, "msg": "Other message"},
        {"timestamp": 2000, "msg": message},
    ]


@pytest.mark.parametrize("army, vehicle, mode", [("air", "f-4s", "air"), ("tank", "germ_hummel", "ground")])
def test_mode_follows_first_sortie(client, conn, match_id, army, vehicle, mode):
    # 混合地图上第一次出击就是飞机的比赛是空战，列表按空战显示。
    _sortie(conn, match_id, army, vehicle)
    db.set_air_map(conn, match_id, AIR_MAP_HASH)
    [summary] = client.get("/api/matches").json
    assert summary["mode"] == mode
    label = translate("en", f"battle_type.{mode}")
    assert f'<span class="match-kind">{label}</span>' in client.get("/").text
    assert f'id="match-mode-title">{label}</span>' in client.get(f"/match/{match_id}").text


def test_history_filters_combine_map_name_date_and_effective_battle_type(client, conn):
    ground = db.start_match(conn, MAP_HASH)
    air = db.start_match(conn, MAP_HASH)
    older_air = db.start_match(conn, MAP_HASH)
    for match_id, army, vehicle in ((ground, "tank", "germ_hummel"), (air, "air", "f-4s"), (older_air, "air", "f-4s")):
        _sortie(conn, match_id, army, vehicle)
        db.set_air_map(conn, match_id, AIR_MAP_HASH)
    with conn:
        conn.executemany("UPDATE matches SET started_at = ? WHERE id = ?", [
            ("2026-11-18T10:00:00", ground),
            ("2026-11-18T10:15:00", air),
            ("2026-11-17T10:00:00", older_air),
        ])
    response = client.get("/", query_string={"date": "2026-11-18", "map": "  NoRmAnDy  ", "mode": "air"})
    assert response.status_code == 200
    assert f'<span class="match-number">#{air}</span>' in response.text
    assert f'<span class="match-number">#{ground}</span>' not in response.text
    assert f'<span class="match-number">#{older_air}</span>' not in response.text
    assert 'value="air" selected' in response.text
    assert '<time datetime="2026-11-18T10:15:00"' in response.text
    empty = client.get("/", query_string={"mode": "naval", "map": "Normandy"})
    assert translate("en", "index.no_filtered_matches") in empty.text


def test_shared_timeline_and_friendly_death_toggle_in_live_and_replay(client, conn, match_id):
    control = 'id="show-all-friendly-deaths"'
    live = client.get("/live").text
    db.end_match(conn, match_id)
    replay = client.get(f"/match/{match_id}").text
    for text in (live, replay):
        assert control in text
        assert 'id="timeline-slider"' in text
        assert 'id="follow-feed"' in text
        assert 'id="own-vehicle-name"' in text
        assert text.index('class="display-panel"') < text.index('class="feed-panel"')
        assert translate("en", "viewer.crew_knocked_out") in text
    assert 'id="timeline-live"' in live
    assert 'id="timeline-live"' not in replay


def test_mode_without_air_map_is_map_type(client, conn, match_id):
    _sortie(conn, match_id, "air", "f-4s")
    assert client.get("/api/matches").json[0]["mode"] == "ground"


def test_index_renders_map_thumbnail_vehicle_chips_and_nuke_badge(client, conn, match_id):
    ally = db.PositionRecord(0.4, 0.4, "#174DFF", "ground_model", "MediumTank", 0)
    player = db.PositionRecord(0.5, 0.5, "#faC81E", "ground_model", "Player", 0)
    db.add_tick(conn, match_id, db.TickRecord(0.0, "air", "dummy_plane", 1, 0), [player])
    db.add_tick(conn, match_id, db.TickRecord(0.5, "tank", "germ_panzerjager_tiger", 0, 0), [ally])
    db.add_tick(conn, match_id, db.TickRecord(1.0, "tank", "tankModels/ussr_t_80u", 0, 0), [player])
    db.add_tick(conn, match_id, db.TickRecord(5.0, "air", "ka_50", 1, 1), [player])
    db.add_events(conn, match_id, [db.EventRecord(8.0, 1, "Pilot 投\u200b放\u200b了\u200b核\u200b武\u200b器！", "{}")])
    html = client.get("/").text
    assert f'/api/match/{match_id}/map.png' in html
    assert '<span class="vehicle-chip">ussr t 80u</span>' in html
    assert '<span class="vehicle-chip">ka 50</span>' in html
    assert "germ panzerjager tiger" not in html
    assert "dummy plane" not in html
    assert '<span class="badge nuke">' in html
    assert translate("en", "index.col_start") in html
    assert translate("en", "index.col_duration") in html
    match_html = client.get(f"/match/{match_id}").text
    assert 'id="nuke-badge" class="badge nuke">' in match_html
    assert 'id="map-kind" role="group"' in match_html
    assert 'id="map-kind" role="group" aria-label="Base map" hidden' not in match_html


def test_match_page_includes_enhanced_viewer_controls(client, match_id):
    html = client.get(f"/match/{match_id}").text
    for marker in (
        'id="toggle-sidebar"',
        'id="follow-player"',
        'id="map-dim"',
        'id="speed-select"',
        'id="sortie-list"',
        'id="nuke-badge"',
        'data-feed-filter="kill"',
        'data-feed-filter="award"',
        'data-feed-filter="no_leave"',
    ):
        assert marker in html, marker


def test_unknown_map_with_naval_spawns_infers_naval_mode(client, conn):
    naval_id = db.start_match(conn, "1e989f059d086e49d8c69ce76486491c93ae372766ce01d027b48e1e8")
    db.add_tick(
        conn, naval_id, db.TickRecord(1.0, "tank", "", 0, 0),
        [
            db.PositionRecord(0.4, 0.3, "#174DFF", "respawn_base_destroyer", "respawn_base_destroyer", 1),
            db.PositionRecord(0.5, 0.4, "#174DFF", "ground_model", "LightCruiser", 0),
        ],
    )
    summary = client.get(f"/api/match/{naval_id}").json
    assert summary["battle_type"] == "naval"
    assert summary["mode"] == "naval"
    filtered = client.get("/", query_string={"mode": "naval"}).text
    assert f'<span class="match-number">#{naval_id}</span>' in filtered
    match_html = client.get(f"/match/{naval_id}").text
    assert 'data-battle-type="naval"' in match_html
    assert translate("en", "unit.LightCruiser") in match_html


def _save_replay(conn, match_id):
    record = db.ReplayRecord("00000000000072c4", 1, "levels/avg_normandy.bin", "normandy_Dom",
                             "air_ground_Dom", "2026-11-25T00:00:00", 61.5, None, None, None, 0, "test", 2)
    player = db.ReplayPlayer("101", "Alice", "=TAG=", 1, 1, None, "bf-109f-4,la-7",
                             2, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 900)
    kill = db.ReplayKill(65.0, "Alice", "bf-109f-4", None, None)
    chat = db.ReplayChat(5.0, "Alice", "<color=#fff>hi</color>")
    db.save_replay(conn, match_id, record, [player], [kill], [chat])


def test_replay_report_api_and_dialog(client, conn, match_id):
    assert client.get(f"/api/match/{match_id}/replay").status_code == 404
    db.end_match(conn, match_id)
    _save_replay(conn, match_id)

    report = client.get(f"/api/match/{match_id}/replay").get_json()
    assert report["players"][0]["name"] == "Alice"
    assert report["kills"][0]["timestamp_ms"] == 65000

    html = client.get(f"/match/{match_id}").get_data(as_text=True)
    assert 'id="open-report"' in html and 'id="replay-report"' in html
    assert ">la-7<" in html and "1:05" in html
    assert ">hi<" not in html and "hi</li>" in html
    assert translate("en", "replay.badge") in client.get("/").get_data(as_text=True)


def test_scoreboard_fragment_for_history_dropdown(client, conn, match_id):
    assert client.get(f"/match/{match_id}/scoreboard").status_code == 404
    db.end_match(conn, match_id)
    _save_replay(conn, match_id)
    html = client.get(f"/match/{match_id}/scoreboard").get_data(as_text=True)
    assert "Alice" in html and ">900<" in html and "normandy_Dom" in html
    index = client.get("/").get_data(as_text=True)
    assert f'aria-controls="scoreboard-{match_id}"' in index
    assert f'data-url="/match/{match_id}/scoreboard"' in index


def test_match_page_without_replay_has_no_report(client, match_id):
    html = client.get(f"/match/{match_id}").get_data(as_text=True)
    assert 'id="open-report"' not in html


def test_match_page_parses_replays_on_open(client, match_id, monkeypatch):
    from wt_plotter.web import app as app_module

    calls = []
    monkeypatch.setattr(app_module.importer, "ensure_parsed", lambda conn, mid, lang: calls.append((mid, lang)))
    assert client.get(f"/match/{match_id}").status_code == 200
    assert calls == [(match_id, "en")]


def test_import_replays_endpoint(client, tmp_path, monkeypatch):
    from wt_plotter.web import app as app_module

    assert client.post("/api/replays/import", json={"path": str(tmp_path / "missing")}).status_code == 400
    monkeypatch.setattr(app_module.importer, "import_new", lambda conn, paths: ([1, 2], ["x.wrpl: boom"]))
    response = client.post("/api/replays/import", json={"path": str(tmp_path)})
    assert response.get_json() == {"imported": 2, "errors": ["x.wrpl: boom"]}


def test_import_replays_endpoint_accepts_a_file(client, tmp_path, monkeypatch):
    from wt_plotter.web import app as app_module

    replay = tmp_path / "a.wrpl"
    replay.write_bytes(b"")
    calls = []
    monkeypatch.setattr(app_module.importer, "import_new", lambda conn, paths: calls.append(paths) or ([], []))
    client.post("/api/replays/import", json={"path": str(replay)})
    assert calls == [[replay]]


def test_upload_replays_endpoint(client, conn, match_id, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from wt_plotter.web import app as app_module

    stored = []

    def store(files, target):
        stored.extend(files)
        return sources, store_errors
    monkeypatch.setattr(app_module.importer, "store_uploads", store)
    monkeypatch.setattr(app_module.importer, "import_new", lambda conn, paths: ([1], []))

    # 多份录像：返回导入数量和失败原因。
    sources, store_errors = [tmp_path / "a", tmp_path / "b"], ["c.wrpl: bad"]
    data = {"files": [(io.BytesIO(b"one"), "a.wrpl"), (io.BytesIO(b"two"), "b.wrpl")]}
    response = client.post("/api/replays/upload", data=data, content_type="multipart/form-data")
    assert response.get_json() == {"imported": 1, "errors": ["c.wrpl: bad"]}
    assert stored == [("a.wrpl", b"one"), ("b.wrpl", b"two")]

    # 只选了一份：直接给出它所在的比赛，便于跳转。
    db.end_match(conn, match_id)
    _save_replay(conn, match_id)
    sources, store_errors = [tmp_path / "a"], []
    monkeypatch.setattr(app_module.importer, "read_header", lambda path: SimpleNamespace(session_hex="00000000000072c4"))
    data = {"files": [(io.BytesIO(b"one"), "a.wrpl")]}
    response = client.post("/api/replays/upload", data=data, content_type="multipart/form-data")
    assert response.get_json() == {"match_id": match_id}


def test_download_replay_endpoint(client, tmp_path, monkeypatch):
    from wt_plotter.web import app as app_module

    assert client.post("/api/replays/download", json={"session": "??"}).status_code == 400

    def missing(session, target):
        raise FileNotFoundError(session)

    monkeypatch.setattr(app_module.download, "download_server_replay", missing)
    assert client.post("/api/replays/download", json={"session": "72c412c1002817ae"}).status_code == 404

    monkeypatch.setattr(app_module.download, "download_server_replay", lambda session, target: tmp_path / session)
    monkeypatch.setattr(app_module.importer, "load_path", lambda path: path)
    monkeypatch.setattr(app_module.importer, "import_replay", lambda conn, replay, source, lang: 9)
    assert client.post("/api/replays/download", json={"session": "72c412c1002817ae"}).get_json() == {"match_id": 9}


def test_report_handles_known_victim_without_vehicle(client, conn, match_id):
    db.end_match(conn, match_id)
    _save_replay(conn, match_id)
    replay_id = conn.execute("SELECT id FROM replays").fetchone()["id"]
    with conn:
        conn.execute("UPDATE replay_kills SET victim = 'Bob', victim_vehicle = NULL WHERE replay_id = ?", (replay_id,))
    assert client.get(f"/match/{match_id}").status_code == 200


def test_replay_match_without_map_uses_level(client, conn):
    match_id = db.create_finished_match(conn, "2026-11-25T00:00:00", "2026-11-25T00:10:00", None)
    _save_replay(conn, match_id)
    data = client.get(f"/api/match/{match_id}").get_json()
    assert data["map_id"] == "avg_normandy_tankmap"
    assert data["map_name"] == translate("en", "map.avg_normandy_tankmap")
    assert data["battle_type"] == "ground"
