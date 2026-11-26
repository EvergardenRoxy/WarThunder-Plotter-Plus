import pytest

from builders import build_blk, build_wrpl, chat_body, packet, player_block
from wt_plotter.replay import blk, wrpl


RESULTS = ([("timePlayed", 12.5), ("author", "me")], [player_block(7, "Alice", 1, kills=2)])


def test_blk_parses_params_and_nested_blocks():
    data = build_blk(([("a", 3), ("b", "text"), ("c", True), ("d", 1.5)], [
        ("child", ([("x", -1)], [("leaf", ([("y", "z")], []))])),
        ("child", ([("x", 2)], [])),
    ]))
    root = blk.parse(data)
    assert [root.get(key) for key in "abcd"] == [3, "text", True, 1.5]
    first, second = root.all("child")
    assert first.get("x") == -1 and first.block("leaf").get("y") == "z"
    assert second.get("x") == 2
    with pytest.raises(KeyError):
        root.get("missing")
    assert root.get("missing", None) is None


def test_blk_rejects_other_formats():
    with pytest.raises(ValueError):
        blk.parse(b"\x03")


def test_load_reads_header_results_and_chat(tmp_path):
    path = tmp_path / "r.wrpl"
    path.write_bytes(build_wrpl([
        packet(256_000, 1, b"\x00"),
        packet(512_000, wrpl.PACKET_CHAT, chat_body("Alice", "hi")),
    ], RESULTS, session=0xABC))
    replay = wrpl.load(path)
    assert replay.header.session_hex == "0000000000000abc"
    assert replay.header.level == "levels/avg_normandy.bin"
    assert replay.header.battle_class == "air_ground_Dom"
    assert replay.results.all("player")[0].get("name") == "Alice"
    assert [(p.time, p.kind) for p in replay.packets()] == [(1.0, 1), (2.0, wrpl.PACKET_CHAT)]
    assert wrpl.parse_chat(list(replay.packets())[1]) == wrpl.ChatMessage(2.0, "Alice", "hi", 0)


def test_load_rejects_non_replays(tmp_path):
    path = tmp_path / "x.wrpl"
    path.write_bytes(b"\x00" * 2000)
    with pytest.raises(ValueError):
        wrpl.load(path)


@pytest.mark.parametrize("size", [5, 100, 70_000, 3_000_000])
def test_size_prefix_forms(size):
    if size < 0x40:
        prefix = bytes([0x80 | size])
    elif size < 0x4000:
        prefix = (0x4000 | size).to_bytes(2, "big")
    elif size < 0x200000:
        prefix = (0x200000 | size).to_bytes(3, "big")
    else:
        prefix = (0x10000000 | size).to_bytes(4, "big")
    payload = b"\x02" + b"\x00" * 4 + b"\x01" * (size - 5)
    assert [len(p.body) for p in wrpl.iter_packets(prefix + payload)] == [size - 5]


def test_flagged_packet_reuses_previous_timestamp():
    stream = packet(256_000, 2, b"a") + bytes([0x82, 0x14, 0x62])
    assert [(p.time, p.kind, p.body) for p in wrpl.iter_packets(stream)] == [(1.0, 2, b"a"), (1.0, 4, b"b")]


def test_load_parts_skips_snapshots_and_takes_last_results(tmp_path):
    files = []
    for part, ticks, results in [(0, 1, None), (1, 2, None), (2, 3, None), (3, 4, RESULTS)]:
        path = tmp_path / f"{part:04d}.wrpl"
        path.write_bytes(build_wrpl([packet(ticks * 256_000, 1, b"")], results, part=part, server=True,
                                    settings=part == 0))
        files.append(path)
    replay = wrpl.load_parts(list(reversed(files)))
    assert replay.header.is_server
    assert [p.time for p in replay.packets()] == [1.0, 2.0, 4.0]
    assert replay.results.get("timePlayed") == 12.5


def test_load_parts_requires_one_session(tmp_path):
    for part, session in [(0, 1), (1, 2)]:
        (tmp_path / f"{part:04d}.wrpl").write_bytes(build_wrpl([], None, part=part, session=session))
    with pytest.raises(ValueError):
        wrpl.load_parts(sorted(tmp_path.glob("*.wrpl")))
