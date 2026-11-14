from dataclasses import replace
from io import BytesIO
import json
from unittest.mock import Mock

from PIL import Image
import pytest

from wt_plotter.capture import tracker
from wt_plotter.maps import lookup
from wt_plotter.maps.dhash import compute_dhash
from wt_plotter.maps.table import MAPS, UNKNOWN_MAP
from wt_plotter.storage import db


GROUND = "avg_normandy_tankmap"
AIR = "air_normandy_map"


@pytest.fixture
def setup(conn, tmp_path):
    fetch = Mock(return_value=None)
    maps_dir = tmp_path / "maps"
    return tracker.MatchTracker(conn, fetch, maps_dir), fetch, maps_dir


def test_no_match_when_invalid(setup, conn):
    match, fetch, _ = setup
    match.tick(0, False, None, None)
    assert match.match_id is None
    assert db.get_active_match(conn) is None
    fetch.assert_not_called()


def test_start_creates_match_and_saves_map(setup, conn, map_png, obj):
    match, fetch, maps_dir = setup
    fetch.return_value = map_png(GROUND)
    match.tick(0, True, None, [obj(0.5, 0.5)])
    stored = db.get_active_match(conn)
    assert stored.id == match.match_id
    assert lookup.lookup_map(stored.map_hash).map_id == GROUND
    assert (maps_dir / f"{GROUND}.png").read_bytes() == fetch.return_value
    assert db.count_positions(conn, stored.id) == 1


def test_start_without_image(setup, conn):
    match, _, _ = setup
    match.tick(0, True, None, None)
    assert db.get_active_match(conn).map_hash == ""


def test_invalid_coords_dropped(setup, conn, obj):
    match, _, _ = setup
    invalid = [obj(x, 0.5) for x in (0, 1, -1)] + [obj(0.5, y) for y in (0, 1, -1)]
    match.tick(0, True, None, [*invalid, obj(0.5, 0.5)])
    assert db.count_positions(conn, match.match_id) == 1


def test_timestamp_relative(setup, conn, obj):
    match, _, _ = setup
    objects = [obj(0.5, 0.5)]
    match.tick(100, True, None, objects)
    match.tick(100.4, True, None, objects)
    assert db.get_latest_tick(conn, match.match_id).timestamp == 400


def test_indicator_parsing(setup, obj):
    match, _, _ = setup
    match.tick(0, True, {"army": "tank", "type": "tankModels/fr_leclerc_s1"}, [obj(0.5, 0.5)])
    assert match.army_type == "tank"
    assert match.vehicle_type == "fr_leclerc_s1"


def test_respawn_poi_once(setup, conn, obj):
    match, _, _ = setup
    objects = [obj(0.5, 0.5, type="respawn_base_tank"), obj(0.2, 0.4, type="capture_zone")]
    match.tick(0, True, None, objects)
    match.tick(1, True, None, objects)
    bundle = db.get_positions_bundle(conn, match.match_id, 0)
    ticks = {tick["id"]: tick["timestamp"] for tick in bundle["ticks"]}
    assert [(p["type"], ticks[p["tick_id"]]) for p in bundle["positions"]] == [
        ("respawn_base_tank", 0), ("capture_zone", 0), ("capture_zone", 1000),
    ]


def test_initial_capture(setup, conn, obj):
    match, _, _ = setup
    match.tick(0, True, None, [obj(0.2, 0.4, "capture_zone"), obj(0.6, 0.8, "capture_zone")])
    match.tick(1, True, None, [obj(0.3, 0.5, "capture_zone")])
    stored = db.get_active_match(conn)
    assert stored.initial_capture_count == 2
    assert (stored.initial_capture_x, stored.initial_capture_y) == pytest.approx((0.4, 0.6))


def test_grace_period(setup, map_png):
    match, fetch, _ = setup
    fetch.return_value = map_png(GROUND)
    match.tick(0, True, None, None)
    match.tick(2, False, None, None)
    match.tick(21.9, False, None, None)
    assert match.match_id is not None
    match.tick(22, False, None, None)
    assert match.match_id is None


def test_grace_resets_on_valid(setup, map_png):
    match, fetch, _ = setup
    fetch.return_value = map_png(GROUND)
    for now, valid in ((0, True), (1, False), (11, True), (12, False), (27, False)):
        match.tick(now, valid, None, None)
    assert match.match_id is not None


def test_no_map_ends_immediately(setup, map_png, monkeypatch):
    match, fetch, _ = setup
    fetch.return_value = map_png(GROUND)
    match.tick(0, True, None, None)
    no_map = next(info for info in MAPS.values() if info.map_id == "no_map")
    monkeypatch.setattr(tracker, "lookup_map", lambda _: no_map)
    match.tick(1, False, None, None)
    assert match.match_id is None


def test_nuke_switch_keeps_match(setup, conn, map_png):
    match, fetch, _ = setup
    fetch.return_value = map_png(GROUND)
    match.tick(0, True, None, None)
    match_id = match.match_id
    fetch.return_value = map_png(AIR)
    match.tick(1, False, None, None)
    assert match.match_id == match_id
    assert db.get_match(conn, match_id).nuke_detected == 1
    assert len(db.get_all_matches(conn)) == 1


def test_map_change_starts_new_match(setup, conn, map_png):
    match, fetch, _ = setup
    fetch.return_value = map_png(GROUND)
    match.tick(0, True, None, None)
    old_id = match.match_id
    fetch.return_value = map_png("avg_japan_tankmap")
    match.tick(1, False, None, None)
    assert db.get_match(conn, old_id).ended_at
    assert db.get_active_match(conn).id == match.match_id != old_id
    assert len(db.get_all_matches(conn)) == 2


def test_air_view_transform_applied(setup, conn, obj):
    match, _, _ = setup
    ground = [(0.2, 0.2), (0.4, 0.3), (0.6, 0.7), (0.8, 0.5)]
    match.tick(0, True, {"army": "tank"}, [obj(x, y) for x, y in ground])
    match.tick(1, True, {"army": "air"}, [obj(0.25 * x + 0.1, 0.25 * y + 0.2) for x, y in ground])
    stored = db.get_active_match(conn)
    assert (stored.air_transform_a, stored.air_transform_b, stored.air_transform_c, stored.air_transform_d) == (
        pytest.approx((0.25, 0.1, 0.25, 0.2))
    )
    bundle = db.get_positions_bundle(conn, stored.id, 1000)
    assert bundle["ticks"][0]["is_player_air_view"] == 1
    for position, expected in zip(bundle["positions"], ground, strict=True):
        assert (position["x_ground"], position["y_ground"]) == pytest.approx(expected)


def test_air_map_captured(setup, conn, map_png, obj):
    match, fetch, maps_dir = setup
    fetch.return_value = map_png(GROUND)
    objects = [obj(0.5, 0.5)]
    match.tick(0, True, {"army": "tank"}, objects)
    fetch.return_value = map_png(AIR)
    match.tick(1, True, {"army": "air"}, objects)
    assert db.get_active_match(conn).air_map_hash == compute_dhash(fetch.return_value)
    assert (maps_dir / f"{AIR}.png").exists()
    match.tick(2, True, {"army": "air"}, objects)
    assert fetch.call_count == 2


def test_end_match_idempotent(setup):
    match, _, _ = setup
    match.end_match()
    assert match.match_id is None


def test_unknown_hash_logged(setup, conn, tmp_path, monkeypatch):
    match, fetch, _ = setup
    log = tmp_path / "missing.log"
    monkeypatch.setattr(lookup, "PATHS", replace(lookup.PATHS, missing_hash_log=log))
    with BytesIO() as image_bytes:
        image = Image.new("L", (16, 15))
        image.putdata(list(range(15, -1, -1)) * 15)
        image.save(image_bytes, "PNG")
        fetch.return_value = image_bytes.getvalue()
    match.tick(0, True, None, None)
    dhash = db.get_active_match(conn).map_hash
    assert lookup.lookup_map(dhash) is UNKNOWN_MAP
    assert [json.loads(line)["hash"] for line in log.read_text(encoding="utf-8").splitlines()] == [dhash]
