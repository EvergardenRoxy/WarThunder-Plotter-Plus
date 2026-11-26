from contextlib import closing
from datetime import datetime

import pytest
import zstandard

from builders import build_wrpl, chat_body, hit_body, kill_body, packet, player_block, player_record
from wt_plotter.maps.lookup import hash_for_map_id, level_map_id, lookup_map
from wt_plotter.replay import importer, messages, wrpl
from wt_plotter.storage import db


START = 1_795_534_032
PLAYERS = ([("timePlayed", 30.0)], [
    ("matchingInfo", ([], [("202", ([], [("crafts_info", ([], [("array0", ([("name", "la-7"), ("rank", 4)], []))]))]))])),
    player_block(101, "Alice", 1, kills=1, score=500),
    player_block(202, "Bob", 2, score=100),
])
MPI = wrpl.PACKET_MPI


def battle_packets():
    roster = zstandard.ZstdCompressor().compress(player_record(0, 101, "Alice") + player_record(1, 202, "Bob"))
    return [
        packet(256_000, MPI, b"\x00\x02\x58\x2d\xf0\x01" + roster),
        packet(2_560_000, MPI, hit_body(target_eid=60, slot=1, vehicle="yak-3", attacker_eid=61)),
        packet(5_120_000, MPI, kill_body(slot=0, vehicle="bf-109f-4", victim_eid=61, killer_eid=50)),
        packet(6_400_000, wrpl.PACKET_CHAT, chat_body("Bob", "gg")),
        packet(7_680_000, MPI, kill_body(slot=0xFFFFFFFF, vehicle="", victim_eid=99, killer_eid=0)),
    ]


@pytest.fixture
def conn(tmp_path):
    with closing(db.connect(tmp_path / "m.db")) as connection:
        yield connection


def write(tmp_path, name, **kwargs):
    path = tmp_path / name
    path.write_bytes(build_wrpl(battle_packets(), PLAYERS, start_time=START, **kwargs))
    return path


def test_read_battle_maps_slots_units_and_kills(tmp_path):
    replay = wrpl.load(write(tmp_path, "a.wrpl"))
    battle = messages.read_battle(list(replay.packets()))
    assert battle.slots == {0: 101, 1: 202}
    assert battle.sightings == {
        61: [messages.Sighting(10.0, 1, "yak-3")], 50: [messages.Sighting(20.0, 0, "bf-109f-4")],
    }
    assert battle.kills == [
        messages.Kill(20.0, 0, "bf-109f-4", 50, 61),
        messages.Kill(30.0, None, "", None, 99),
    ]


def test_import_creates_match_with_level_map(conn, tmp_path):
    match_id = importer.import_replay(conn, wrpl.load(write(tmp_path, "a.wrpl")), "a.wrpl", "en")
    match = db.get_match(conn, match_id)
    assert match.started_at == datetime.fromtimestamp(START).isoformat()
    assert lookup_map(match.map_hash).map_id == "avg_normandy_tankmap"
    report = db.get_replay_report(conn, match_id)
    assert report["replay"]["session_id"] == "00000000000072c4"
    assert [(p["name"], p["vehicles"], p["kills"]) for p in report["players"]] == [
        ("Alice", "bf-109f-4", 1), ("Bob", "yak-3,la-7", 0),
    ]
    assert [(k["timestamp_ms"], k["killer"], k["victim"], k["victim_vehicle"]) for k in report["kills"]] == [
        (20000, "Alice", "Bob", "yak-3"), (30000, None, None, None),
    ]
    assert [(c["sender"], c["text"]) for c in report["chat"]] == [("Bob", "gg")]


def test_import_links_to_captured_match_and_server_replay_extends_it(conn, tmp_path):
    started = datetime.fromtimestamp(START + 10).isoformat()
    captured = db.create_finished_match(conn, started, datetime.fromtimestamp(START + 20).isoformat(), "hash")
    assert importer.import_replay(conn, wrpl.load(write(tmp_path, "a.wrpl")), "a", "en") == captured

    server_dir = tmp_path / "server"
    server_dir.mkdir()
    write(server_dir, "0000.wrpl", server=True)
    assert importer.import_replay(conn, importer.load_path(server_dir), "s", "en") == captured
    assert db.get_match(conn, captured).ended_at == datetime.fromtimestamp(START + 30).isoformat()
    assert db.get_replay_report(conn, captured)["replay"]["is_server"] == 1


def test_reimport_replaces_rows(conn, tmp_path):
    path = write(tmp_path, "a.wrpl")
    first = importer.import_replay(conn, wrpl.load(path), "a", "en")
    assert importer.import_replay(conn, wrpl.load(path), "a", "en") == first
    assert conn.execute("SELECT COUNT(*) FROM replay_players").fetchone()[0] == 2


def test_match_of_other_session_is_not_reused(conn, tmp_path):
    first = importer.import_replay(conn, wrpl.load(write(tmp_path, "a.wrpl")), "a", "en")
    second = importer.import_replay(conn, wrpl.load(write(tmp_path, "b.wrpl", session=0x99)), "b", "en")
    assert first != second


def test_delete_match_removes_replay(conn, tmp_path):
    match_id = importer.import_replay(conn, wrpl.load(write(tmp_path, "a.wrpl")), "a", "en")
    db.delete_match(conn, match_id)
    assert db.get_replay_report(conn, match_id) is None
    assert conn.execute("SELECT COUNT(*) FROM replay_kills").fetchone()[0] == 0


def test_level_map_id():
    assert level_map_id("levels/avg_normandy.bin", "air_ground_Dom") == "avg_normandy_tankmap"
    assert level_map_id("levels/avg_egypt_sinai.bin", "base_dom") == "avg_egypt_sinai_map"
    assert level_map_id("levels/air_israel.bin", "base_dom") == "air_israel_map"
    assert level_map_id("levels/nowhere.bin", "base_dom") is None
    assert hash_for_map_id("nowhere") is None


def test_replay_sources_expands_folders(tmp_path):
    (tmp_path / "local").mkdir()
    for name in ("b.wrpl", "a.wrpl"):
        (tmp_path / "local" / name).write_bytes(b"")
    (tmp_path / "server").mkdir()
    (tmp_path / "server" / "0000.wrpl").write_bytes(b"")
    sources = importer.replay_sources([tmp_path / "local", tmp_path / "server"])
    assert sources == [tmp_path / "local" / "a.wrpl", tmp_path / "local" / "b.wrpl", tmp_path / "server"]


def kill_count(conn):
    return conn.execute("SELECT COUNT(*) FROM replay_kills").fetchone()[0]


def test_import_new_reads_only_summary_and_skips_known(conn, tmp_path):
    folder = tmp_path / "Replays"
    folder.mkdir()
    write(folder, "a.wrpl")
    broken = build_wrpl(battle_packets(), PLAYERS, start_time=START, session=0x55)
    (folder / "b.wrpl").write_bytes(broken[:-40])
    [match_id], errors = importer.import_new(conn, [folder])
    assert len(errors) == 1 and errors[0].startswith("b.wrpl")
    # 结果块的 timePlayed 给出结束时间；玩家战绩来自结果块，击杀和聊天要等完整解析。
    assert db.get_match(conn, match_id).ended_at == datetime.fromtimestamp(START + 30).isoformat()
    report = db.get_replay_report(conn, match_id)
    assert [p["name"] for p in report["players"]] == ["Alice", "Bob"]
    assert kill_count(conn) == 0
    assert conn.execute("SELECT parser_version FROM replays").fetchone()[0] == importer.SUMMARY_VERSION
    assert importer.import_new(conn, [folder]) == ([], [errors[0]])


def test_ensure_parsed_runs_full_parse_once(conn, tmp_path):
    folder = tmp_path / "Replays"
    folder.mkdir()
    write(folder, "a.wrpl")
    [match_id], _ = importer.import_new(conn, [folder])
    importer.ensure_parsed(conn, match_id, "en")
    assert kill_count(conn) == 2
    assert conn.execute("SELECT parser_version FROM replays").fetchone()[0] == importer.PARSER_VERSION
    assert db.replays_to_parse(conn, match_id, importer.PARSER_VERSION) == []
    # 解析逻辑升级后，旧版本解析的录像在下次打开时重新解析。
    conn.execute("UPDATE replays SET parser_version = 1")
    assert db.replays_to_parse(conn, match_id, importer.PARSER_VERSION) == [str(folder / "a.wrpl")]


def test_ensure_parsed_keeps_summary_when_file_is_gone(conn, tmp_path):
    folder = tmp_path / "Replays"
    folder.mkdir()
    write(folder, "a.wrpl")
    [match_id], _ = importer.import_new(conn, [folder])
    (folder / "a.wrpl").unlink()
    importer.ensure_parsed(conn, match_id, "en")
    assert kill_count(conn) == 0
    report = db.get_replay_report(conn, match_id)
    assert report["players"]
    # 失败原因记下来在战报里显示，同一解析版本不再重试。
    assert [error["source"] for error in report["errors"]] == [str(folder / "a.wrpl")]
    assert db.replays_to_parse(conn, match_id, importer.PARSER_VERSION) == []


def test_import_new_skips_unreadable_files(conn, tmp_path):
    folder = tmp_path / "Replays"
    folder.mkdir()
    (folder / "0_empty.wrpl").write_bytes(b"")
    write(folder, "a.wrpl")
    match_ids, errors = importer.import_new(conn, [folder])
    assert len(match_ids) == 1
    assert len(errors) == 1 and errors[0].startswith("0_empty.wrpl")


def test_failed_summary_leaves_no_match(conn, tmp_path, monkeypatch):
    def broken(results, used):
        raise ValueError("bad player block")
    monkeypatch.setattr(importer, "_players", broken)
    write(tmp_path, "a.wrpl")
    _, errors = importer.import_new(conn, [tmp_path])
    assert errors and db.get_all_matches(conn) == []


def test_connect_adds_columns_missing_from_old_tables(tmp_path):
    path = tmp_path / "old.db"
    with closing(db.connect(path)) as connection:
        connection.executescript("""
            ALTER TABLE replays DROP COLUMN parser_version;
            ALTER TABLE replays DROP COLUMN parse_error;
            ALTER TABLE positions DROP COLUMN unit_name_id;
            ALTER TABLE positions DROP COLUMN unit_vehicle_id;
        """)
    with closing(db.connect(path)) as connection:
        replays = {row["name"] for row in connection.execute("PRAGMA table_info(replays)")}
        positions = {row["name"] for row in connection.execute("PRAGMA table_info(positions)")}
    assert {"parser_version", "parse_error"} <= replays
    assert {"unit_name_id", "unit_vehicle_id"} <= positions
