from contextlib import closing

import pytest
import zstandard

from builders import (
    aircraft_state_body, build_wrpl, ground_state, ground_sync_body, hit_body, kill_body, packet, player_block,
    player_record,
)
from wt_plotter.maps.lookup import hash_for_map_id, lookup_map
from wt_plotter.replay import importer, messages, tracks, wrpl
from wt_plotter.storage import db


LEVEL = "levels/air_israel.bin"
MPI = wrpl.PACKET_MPI


def results(author="101"):
    """服务器录像的结果块没有 authorUserId，传 None 模拟。"""
    params = [("timePlayed", 10.0)] + ([("authorUserId", author)] if author else [])
    return (params, [
        ("matchingInfo", ([], [])),
        player_block(101, "Alice", 1),
        player_block(202, "Bob", 2),
    ])


def air_packets(frames=12, extra_ticks=0):
    """Alice(槽位 0, eid 200) 与 Bob(槽位 1, eid 201) 各飞一段；Bob 在第 2.5 秒被 Alice 击落。"""
    roster = zstandard.ZstdCompressor().compress(player_record(0, 101, "Alice") + player_record(1, 202, "Bob"))
    out = [packet(1, MPI, b"\x00\x02\x58\x2d\xf0\x01" + roster)]
    for i in range(frames):
        a = (1000.0 + 20 * i, 500.0, 1000.0)
        b = (5000.0 - 20 * i, 600.0, -3000.0)
        out.append(packet(int((1 + i * 0.25) * wrpl.TICKS_PER_SECOND) + extra_ticks, 2, aircraft_state_body([(200, a), (201, b)])))
    out.append(packet(int(2.5 * wrpl.TICKS_PER_SECOND), MPI, kill_body(0, "yak-3", victim_eid=201, killer_eid=200)))
    return out


@pytest.fixture
def conn(tmp_path):
    with closing(db.connect(tmp_path / "m.db")) as connection:
        yield connection


def load(tmp_path, name, **kwargs):
    path = tmp_path / name
    author = kwargs.pop("author", "101")
    path.write_bytes(build_wrpl(air_packets(), results(author), level=LEVEL, battle_class="base_dom", **kwargs))
    return wrpl.load(path)


def styles(conn, match_id):
    return conn.execute(
        """SELECT i.value AS icon, c.value AS color, COUNT(*) AS n FROM positions p
           JOIN enum_icons i ON i.id = p.icon_id JOIN enum_colors c ON c.id = p.color_id
           WHERE p.match_id = ? GROUP BY 1, 2 ORDER BY 1""", (match_id,)).fetchall()


def test_air_replay_writes_tracks_and_kill_feed(conn, tmp_path):
    match_id = importer.import_replay(conn, load(tmp_path, "a.wrpl"), "a", "en")
    assert not db.get_match(conn, match_id).map_hash
    assert [tuple(row) for row in styles(conn, match_id)] == [("Fighter", "#fa0C00", 7), ("Player", "#faC81E", 12)]
    events = db.get_events(conn, match_id, 0)
    assert events == [{"timestamp": 2500, "msg": "Alice (yak-3) destroyed Bob (?)"}]
    tick = db.get_latest_tick(conn, match_id)
    assert (tick.army_type, tick.vehicle_type) == ("air", "yak-3")


def test_known_bounds_keep_map_and_project(conn, tmp_path):
    db.save_map_bounds(conn, "air_israel_map", (0.0, 0.0, 10000.0, 10000.0))
    match_id = importer.import_replay(conn, load(tmp_path, "a.wrpl"), "a", "en")
    assert lookup_map(db.get_match(conn, match_id).map_hash).map_id == "air_israel_map"
    first = db.get_positions_bundle(conn, match_id, 0)["positions"][0]
    assert (first["x"], first["y"]) == (0.1, 0.9)


def test_reimport_restores_map_once_bounds_are_known(conn, tmp_path):
    match_id = importer.import_replay(conn, load(tmp_path, "a.wrpl"), "a", "en")
    db.save_map_bounds(conn, "air_israel_map", (0.0, 0.0, 10000.0, 10000.0))
    assert importer.import_replay(conn, load(tmp_path, "a.wrpl"), "a", "en") == match_id
    assert lookup_map(db.get_match(conn, match_id).map_hash).map_id == "air_israel_map"


def test_captured_tracks_are_kept(conn, tmp_path):
    from datetime import datetime
    started = datetime.fromtimestamp(1_795_534_032).isoformat()
    match_id = db.create_finished_match(conn, started, started, hash_for_map_id("air_israel_map"))
    db.add_tick(conn, match_id, db.TickRecord(1.0, "air", "x", 1, 0),
                [db.PositionRecord(0.5, 0.5, "#faC81E", "aircraft", "Player", 0)])
    assert importer.import_replay(conn, load(tmp_path, "a.wrpl"), "a", "en") == match_id
    assert db.count_positions(conn, match_id) == 1
    assert conn.execute("SELECT wrote_tracks FROM replays").fetchone()[0] == 0


def test_server_replay_replaces_local_tracks_but_not_reverse(conn, tmp_path):
    local = importer.import_replay(conn, load(tmp_path, "a.wrpl"), "a", "en")
    folder = tmp_path / "server"
    folder.mkdir()
    (folder / "0000.wrpl").write_bytes(
        build_wrpl(air_packets(extra_ticks=1), results(author=None), level=LEVEL, battle_class="base_dom", server=True))
    assert importer.import_replay(conn, importer.load_path(folder), "s", "en") == local
    # 服务器录像没有录像者，沿用本地录像记下的 Alice。
    assert ("Player", "#faC81E") in [(r["icon"], r["color"]) for r in styles(conn, local)]
    assert db.tracks_writer(conn, local) == 1
    server_count = db.count_positions(conn, local)
    importer.import_replay(conn, load(tmp_path, "a.wrpl"), "a", "en")
    assert db.count_positions(conn, local) == server_count
    assert db.tracks_writer(conn, local) == 1


def ground_packets():
    """陆战：Alice(槽位 0, 单位 40) 与 Bob(槽位 1, 单位 41)；Alice 命中过 Bob，Bob 从没出手。"""
    roster = zstandard.ZstdCompressor().compress(player_record(0, 101, "Alice") + player_record(1, 202, "Bob"))
    out = [packet(1, MPI, b"\x00\x02\x58\x2d\xf0\x01" + roster)]
    for t in range(1, 6):
        units = {40: ground_state(100.0 + t, 10.0, 100.0), 41: ground_state(1900.0 - t, 10.0, 1900.0)}
        out.append(packet(int((t + 0.3) * wrpl.TICKS_PER_SECOND), MPI, ground_sync_body(units, t)))
    out.append(packet(2 * wrpl.TICKS_PER_SECOND, MPI, hit_body(target_eid=41, slot=0, vehicle="us_m4a1", attacker_eid=40)))
    return out


def test_ground_battle_writes_tank_tracks(conn, tmp_path):
    path = tmp_path / "g.wrpl"
    path.write_bytes(build_wrpl(ground_packets(), results(), battle_class="air_ground_Dom"))
    match_id = importer.import_replay(conn, wrpl.load(path), "g", "en")
    # 采样在 x.3 秒，重采样到整秒 2、3、4、5。
    assert [tuple(row) for row in styles(conn, match_id)] == [("MediumTank", "#fa0C00", 4), ("Player", "#faC81E", 4)]
    vehicles = conn.execute("SELECT DISTINCT v.value FROM ticks t JOIN enum_vehicle_types v ON v.id = t.vehicle_type_id "
                            "WHERE t.match_id = ?", (match_id,)).fetchall()
    assert [row[0] for row in vehicles] == ["us_m4a1"]


def test_unit_infers_first_vehicle_offset():
    seen = messages.Sighting
    battle = messages.Battle({0: 1, 1: 2, 2: 3}, {200: [seen(5.0, 0, "a")], 202: [seen(6.0, 2, "c")]}, [])
    assert battle.unit(201, 1.0) == seen(1.0, 1, "")
    assert battle.unit(250, 1.0) is None


def test_unit_is_scoped_to_one_life():
    """单位号 200 先归 Alice（槽位 0），被击毁后复用给 Bob（槽位 1）。"""
    seen = messages.Sighting
    kill = messages.Kill(10.0, 1, "b", 300, 200)
    battle = messages.Battle({0: 1, 1: 2}, {200: [seen(5.0, 0, "a"), seen(15.0, 1, "b")], 300: [seen(10.0, 1, "b")]}, [kill])
    assert battle.unit(200, 10.0).slot == 0
    assert battle.unit(200, 12.0).slot == 1
    assert battle.vehicles() == {0: ["a"], 1: ["b"]}


def test_ai_team_follows_kills_across_uid_run(tmp_path):
    """单位 500、501 是一段 AI：501 被 Alice（队伍 1）击落，整段都算队伍 2；600 段无证据，按起点归到 Bob 一队。"""
    seen = messages.Sighting
    battle = messages.Battle({0: 101, 1: 202}, {200: [seen(1.0, 0, "yak-3")], 201: [seen(1.0, 1, "la-7")]},
                             [messages.Kill(5.0, 0, "yak-3", 200, 501)])
    roster = importer._Roster(battle, load(tmp_path, "a.wrpl").results, "101")

    def track(eid, x):
        return tracks.UnitTrack(eid, [(1.0, x, 0.0, 0.0)], True)

    units = [track(200, 0.0), track(201, 1000.0), track(500, 0.0), track(501, 0.0), track(600, 990.0)]
    assert roster.relations(units) == ["player", "enemy", "enemy", "enemy", "enemy"]


def test_air_tracks_carry_player_name_and_vehicle(conn, tmp_path):
    """Alice 击落过 Bob，载具已知；Bob 没出过手，靠首辆载具的单位号偏移认出名字，载具未知。"""
    match_id = importer.import_replay(conn, load(tmp_path, "a.wrpl"), "a", "en")
    positions = db.get_positions_bundle(conn, match_id, 0)["positions"]
    assert {(p["unit_name"], p["unit_vehicle"]) for p in positions} == {("Alice", "yak-3"), ("Bob", None)}
