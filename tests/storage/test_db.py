from contextlib import closing
from datetime import datetime
from pathlib import Path
import shutil

import pytest

from wt_plotter.storage import db


UPSTREAM_DB = Path(__file__).resolve().parents[2] / "reference" / "upstream" / "data" / "matches.db"
TICK = db.TickRecord(1.5, "tank", "tank_test", 0, 0)
POSITION = db.PositionRecord(0.1234567, 0.6, "#FA0C00", "ground_model", "Tank", 0)


@pytest.fixture
def conn(tmp_path):
    with closing(db.connect(tmp_path / "m.db")) as connection:
        yield connection


def test_schema_matches_upstream(conn):
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    assert {row["name"] for row in tables} - {"sqlite_sequence"} == {
        "matches", "ticks", "positions", "enum_colors", "enum_types",
        "enum_icons", "enum_army_types", "enum_vehicle_types",
    }
    columns = conn.execute("PRAGMA table_info(matches)").fetchall()
    assert [row["name"] for row in columns] == [
        "id", "started_at", "ended_at", "map_hash", "air_map_hash",
        "initial_capture_count", "initial_capture_x", "initial_capture_y", "nuke_detected",
        "air_transform_a", "air_transform_b", "air_transform_c", "air_transform_d",
    ]


def test_match_lifecycle(conn):
    match_id = db.start_match(conn, "hash")
    assert db.get_active_match(conn).id == match_id
    db.end_match(conn, match_id)
    assert db.get_active_match(conn) is None
    assert db.get_match(conn, match_id).ended_at


def test_add_tick_and_bundle(conn):
    match_id = db.start_match(conn, "hash")
    mapped = db.PositionRecord(0.2, 0.3, "#174DFF", "ground_model", "Tank", 0, 0.4, 0.5)
    db.add_tick(conn, match_id, TICK, [POSITION, mapped])
    bundle = db.get_positions_bundle(conn, match_id, 0)
    assert bundle["ticks"][0]["timestamp"] == 1500
    assert len(bundle["positions"]) == 2
    assert set(bundle["positions"][0]) == {
        "id", "tick_id", "x", "y", "color", "type", "icon", "is_poi", "x_ground", "y_ground",
    }
    assert bundle["positions"][1]["x_ground"] == 0.4
    assert db.get_latest_tick(conn, match_id) == db.TickRecord(1500, "tank", "tank_test", 0, 0)


def test_quantize(conn):
    match_id = db.start_match(conn, "hash")
    db.add_tick(conn, match_id, TICK, [POSITION])
    assert db.get_positions_bundle(conn, match_id, 0)["positions"][0]["x"] == 0.12346


def test_since_filter(conn):
    match_id = db.start_match(conn, "hash")
    for timestamp in (1.0, 2.0):
        db.add_tick(conn, match_id, db.TickRecord(timestamp, "tank", "", 0, 0), [POSITION])
    bundle = db.get_positions_bundle(conn, match_id, 1500)
    assert [tick["timestamp"] for tick in bundle["ticks"]] == [2000]
    assert len(bundle["positions"]) == 1
    assert bundle["positions"][0]["tick_id"] == bundle["ticks"][0]["id"]


def test_delete(conn):
    match_id = db.start_match(conn, "hash")
    db.add_tick(conn, match_id, TICK, [POSITION])
    db.end_match(conn, match_id)
    db.delete_match(conn, match_id)
    assert db.get_match(conn, match_id) is None
    assert db.count_positions(conn, match_id) == 0


def test_delete_reclaims_pages(conn):
    match_id = db.start_match(conn, "hash")
    for index in range(200):
        db.add_tick(conn, match_id, db.TickRecord(index, "tank", "", 0, 0), [POSITION] * 50)
    db.end_match(conn, match_id)
    pages = conn.execute("PRAGMA page_count").fetchone()[0]
    db.delete_match(conn, match_id)
    assert conn.execute("PRAGMA freelist_count").fetchone()[0] == 0
    assert conn.execute("PRAGMA page_count").fetchone()[0] < pages


def test_close_orphaned(conn):
    db.start_match(conn, "first")
    second = db.start_match(conn, "second")
    assert db.close_orphaned_matches(conn) == 2
    assert db.get_active_match(conn) is None
    # 结束时间与开始时间同为本地时间。
    match = db.get_match(conn, second)
    assert datetime.fromisoformat(match.ended_at) >= datetime.fromisoformat(match.started_at)


def test_two_connections(tmp_path):
    path = tmp_path / "m.db"
    with closing(db.connect(path)) as first, closing(db.connect(path)) as second:
        match_id = db.start_match(first, "hash")
        db.add_tick(first, match_id, TICK, [POSITION])
        assert db.get_active_match(second).id == match_id
        assert db.count_positions(second, match_id) == 1


@pytest.mark.skipif(not UPSTREAM_DB.is_file(), reason="Upstream match database is absent")
def test_reads_upstream_db(tmp_path):
    path = tmp_path / "m.db"
    shutil.copyfile(UPSTREAM_DB, path)
    with closing(db.connect(path)) as conn:
        assert isinstance(db.get_all_matches(conn), list)
