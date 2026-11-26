import pytest

from builders import ground_state, ground_sync_body

from wt_plotter.replay import ground, messages, wrpl


# 4 个 0xFF：8 组 "3 号码、参数 3"，每组 10 个 0，共 80 个 2 位值 = 20 字节 0。
ZERO_DELTA = b"\xff\xff\xff\xff" + bytes([ground.RLE_TWO])


def sync_packet(time, units, number, **kwargs):
    return wrpl.Packet(time, wrpl.PACKET_MPI, ground_sync_body(units, number, **kwargs))


def test_rle_decode_codes():
    # 低半字节：码 2 输出 1；高半字节：码 0 输出 3 个 0。值从低位装起。
    assert ground.rle_decode(bytes([0b0000_0110, ground.RLE_TWO]), 8) == bytes([0b01])
    assert ground.rle_decode(ZERO_DELTA, 64) == bytes(20)
    assert ground.rle_decode(ZERO_DELTA, 3) == bytes(3)
    with pytest.raises(ValueError):
        ground.rle_decode(b"\x00\x01", 8)


def test_xor_patch_keeps_longer_tail():
    assert ground.xor_patch(b"\x0f\xaa", b"\xff") == b"\xf0\xaa"
    assert ground.xor_patch(b"\x0f", b"\xff\x01") == b"\xf0\x01"


def test_full_and_delta_states_give_positions():
    state = ground_state(100.0, 12.5, -50.0)
    assert len(state) == 20
    packets = [
        sync_packet(1.0, {7: state, 9: ground_state(5.0, 0.0, 5.0)}, 3),
        sync_packet(2.0, {7: ZERO_DELTA}, 4, full=False, distance=1),
        # 基线（包序号 0）不在历史里：跳过这次采样，不中断解析。
        sync_packet(3.0, {7: ZERO_DELTA}, 5, full=False, distance=5),
    ]
    samples = ground.read_samples(packets)
    assert samples[7] == [(1.0, 100.0, 12.5, -50.0), (2.0, 100.0, 12.5, -50.0)]
    assert samples[9] == [(1.0, 5.0, 0.0, 5.0)]


def test_read_tracks_one_track_per_life():
    # 第 2 秒被击毁，残骸停在原地，第 4 秒复活在别处。
    places = {1: 0.0, 2: 100.0, 3: 100.0, 4: 900.0, 5: 1000.0}
    packets = [sync_packet(float(t), {7: ground_state(x, 0.0, 0.0)}, t) for t, x in places.items()]
    battle = messages.Battle({}, {}, [messages.Kill(2.0, None, "", None, 7)])
    result = ground.read_tracks(packets, battle)
    assert [(track.eid, [p[0] for p in track.points], track.air) for track in result] == [
        (7, [1.0, 2.0], False), (7, [4.0, 5.0], False),
    ]


def test_read_tracks_drops_unowned_static_units():
    # 9 号整场不动、没有归属，是静态物体；7 号同样不动但出过手，是玩家。
    packets = [sync_packet(float(t), {7: ground_state(0.0, 0.0, 0.0), 9: ground_state(500.0, 0.0, 0.0)}, t)
               for t in (1, 2, 3)]
    battle = messages.Battle({0: 1}, {7: [messages.Sighting(1.0, 0, "us_m4a1")]}, [])
    assert [track.eid for track in ground.read_tracks(packets, battle)] == [7]
