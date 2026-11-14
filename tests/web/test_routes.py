from contextlib import closing
from threading import Event

import pytest

from wt_plotter.config import PATHS
from wt_plotter.i18n import set_language, translate
from wt_plotter.maps.table import MAPS, BattleType
from wt_plotter.storage import db
from wt_plotter.web.app import create_app


MAP_ID = "avg_normandy_tankmap"
MAP_HASH = next(key for key, info in MAPS.items() if info.map_id == MAP_ID and info.battle_type is BattleType.GROUND)


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
