"""从类型 2（FlightModel）数据包还原飞机轨迹。

类型 2 包体跳过首字节后是按位写入（高位在前）的条目列表：每条带单位号（或沿用上一条加 1）、
位置（3 个 float32）和姿态、发动机、传感器等可变长子表；单位号 0x7FF 表示列表结束。
格式参考 WTACRP（MIT）对 wrpl-acmi 解析器的整理：https://github.com/ShioUmiusi/WTACRP
"""

from __future__ import annotations

from collections import defaultdict

from wt_plotter.replay.bits import BitReader
from wt_plotter.replay.messages import UID_MASK, Battle
from wt_plotter.replay.tracks import Point, UnitTrack, split_lives
from wt_plotter.replay.wrpl import Packet


AIRCRAFT_STATE = 2
# 飞机速度上限（米/秒）；击毁后连续坠落的残骸不算新的一命，断档这么久以上才算复活。
AIRCRAFT_MAX_SPEED = 400.0
AIRCRAFT_RESPAWN_GAP = 3.0


def _zigzag(reader: BitReader) -> int:
    value = reader.uleb() & 0xFFFFFFFF
    return (value >> 1) ^ -(value & 1)


def _skip_engines(reader: BitReader) -> None:
    for _ in range(reader.bits(8)):
        has_extra = reader.bits(1)
        reader.skip(8)
        if has_extra:
            reader.skip(16)
        if reader.bits(1):
            reader.skip(8)
        reader.skip(16)


def _skip_sensor(reader: BitReader) -> None:
    first = reader.bits(1)
    kind = reader.bits(8) >> 4
    if kind == 1:
        if not reader.bits(1):
            return
        flags = reader.u16()
        reader.skip(32 + 48)
        if flags >= 0x8000:
            reader.skip(8)
        if reader.bits(1):
            reader.skip(8)
    elif kind == 2:
        if not first:
            return
        reader.skip(1 + 16 + 96 + 96 + 32)
    elif kind == 3:
        raise ValueError("unknown aircraft sensor type 3")
    elif kind == 4:
        if reader.bits(1):
            reader.skip(96)
    if reader.bits(1):
        reader.skip(reader.bits(6) * 32 + 6)


def _skip_target(reader: BitReader) -> None:
    reader.skip(16)
    if reader.bits(1):
        reader.skip(96)
    reader.skip(96 + 48 if reader.bits(1) else 96 + 96)
    reader.skip(32 + 2)
    if reader.bits(1):
        reader.skip(8)
    reader.skip(1)
    has_byte = reader.bits(1)
    reader.skip(1)
    if has_byte:
        reader.skip(8)
    if reader.bits(1):
        reader.skip(32)


def aircraft_entries(body: bytes) -> list[tuple[int, tuple[float, float, float]]]:
    """一个类型 2 包里各条目的 (单位号, (x, 高度, z))。"""
    reader = BitReader(body, 8)
    uid, entries = 0, []
    while True:
        uid = reader.uleb() & UID_MASK if reader.bits(1) else uid + 1
        if uid == UID_MASK:
            return entries
        if reader.bits(1):  # 本条只有单位号
            continue
        if reader.bits(1) & reader.bits(1):
            continue
        reader.skip(1 + 32 + 1)
        if reader.bits(1):
            reader.skip(3)
            reader.skip(reader.bits(4))
        for _ in range(_zigzag(reader)):
            _zigzag(reader)
            for _ in range(max(0, _zigzag(reader))):
                _zigzag(reader)
        position = (reader.f32(), reader.f32(), reader.f32())
        reader.skip(32 + 32)  # 紧凑欧拉角、未知
        reader.align()
        reader.skip(7 * 8)
        _skip_engines(reader)
        sensors = reader.bits(8)
        for _ in range(sensors):
            _skip_sensor(reader)
        if sensors:
            reader.skip(8)
        countermeasures = reader.bits(8)
        reader.skip(countermeasures * 16)
        if countermeasures:
            reader.skip(8)
        for _ in range(reader.bits(4)):
            _skip_target(reader)
        if reader.bits(1):
            reader.skip(32)
        if reader.bits(1):
            reader.skip(reader.u32())
        entries.append((uid, position))


def read_tracks(packets: list[Packet], battle: Battle) -> list[UnitTrack]:
    """每架飞机（单位号）每一命一条轨迹。"""
    samples: dict[int, list[Point]] = defaultdict(list)
    for packet in packets:
        if packet.kind == AIRCRAFT_STATE:
            for uid, position in aircraft_entries(packet.body):
                samples[uid].append((packet.time, *position))
    result = []
    for uid, points in sorted(samples.items()):
        lives = split_lives(points, battle.deaths.get(uid, []), AIRCRAFT_MAX_SPEED, AIRCRAFT_RESPAWN_GAP)
        result.extend(UnitTrack(uid, life, True) for life in lives)
    return result
