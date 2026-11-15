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
    db.set_air_map(conn, match_id, AIR_MAP_HASH)
    for path in (f"/match/{match_id}", "/live"):
        text = client.get(path).text
        assert f'data-default-map="{expected}"' in text
        assert 'data-has-air-map="true"' in text
