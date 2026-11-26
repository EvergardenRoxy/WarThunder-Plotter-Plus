"""MPI 消息解码：玩家槽位表、击杀和重伤。字段布局见 docs/zh/replay.md。"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import bisect
import re
import struct
from typing import Iterable

from wt_plotter.replay.bits import BitReader, read_fields
from wt_plotter.replay.wrpl import PACKET_MPI, Packet, decompress


KILL = b"\x00\x02\x58\x58"
HIT = b"\x00\x02\x58\x57"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
NO_PLAYER = 0xFFFFFFFF
# 单位号取低 11 位，全 1 表示无。
UID_MASK = 0x7FF
# 玩家记录：槽位、0x70、2 字节、0x30 0x60、userId、4 个 0、名字。
_PLAYER_RECORD = re.compile(rb"(.)\x70..\x30\x60(....)\x00{4}([^\x00]{1,64})\x00", re.S)


@dataclass(frozen=True)
class Kill:
    time: float
    killer_slot: int | None
    killer_vehicle: str
    killer_eid: int | None
    victim_eid: int


def _bodies(packets: Iterable[Packet]) -> Iterable[tuple[Packet, bytes]]:
    """MPI 消息体；内嵌的 zstd 块解压后一并返回。"""
    for packet in packets:
        if packet.kind != PACKET_MPI:
            continue
        yield packet, packet.body
        start = packet.body.find(ZSTD_MAGIC, 0, 16)
        if start >= 0:
            yield packet, decompress(packet.body[start:])


def player_slots(packets: Iterable[Packet]) -> dict[int, int]:
    """槽位号 -> userId。"""
    slots = {}
    for _, body in _bodies(packets):
        for match in _PLAYER_RECORD.finditer(body):
            slots[match.group(1)[0]] = struct.unpack("<I", match.group(2))[0]
    return slots


def _fields(body: bytes) -> dict[int, BitReader]:
    """消息体：4 字节签名（含消息 id）后是按字段序列化的数据。"""
    return read_fields(body[5:])


def _uid(field: BitReader) -> int | None:
    uid = field.u16() & UID_MASK
    return None if uid == UID_MASK else uid


def _parse_kill(packet: Packet) -> Kill:
    """字段：1 击杀者槽位、2 击杀者载具、3 受害者单位、4 击杀者单位。"""
    fields = _fields(packet.body)
    slot = fields[1].u32()
    victim = fields[3].u16() & UID_MASK
    if slot == NO_PLAYER:
        # 无击杀者（坠毁等）：只有受害者。
        return Kill(packet.time, None, "", None, victim)
    return Kill(packet.time, slot, fields[2].string(), _uid(fields[4]), victim)


def _parse_hit(body: bytes) -> tuple[int, int, str]:
    """重伤消息字段：1 目标单位、2 攻击者槽位、3 攻击者载具、4 攻击者单位；返回攻击者的三项。"""
    fields = _fields(body)
    return _uid(fields[4]), fields[2].u32(), fields[3].string()


@dataclass(frozen=True)
class Sighting:
    """某单位出手（击杀或重伤别人）时报出的槽位和载具。"""

    time: float
    slot: int
    vehicle: str


@dataclass
class Battle:
    """从数据包里还原的玩家槽位、单位归属和击杀。

    单位号会复用：载具被击毁后，同一个号可能分给别的玩家的下一辆载具。所以按受害时刻把每个单位号
    分成若干"命"，归属只在同一命内推断。
    """

    slots: dict[int, int]
    sightings: dict[int, list[Sighting]]
    kills: list[Kill]

    def __post_init__(self):
        self.deaths: dict[int, list[float]] = defaultdict(list)
        for kill in self.kills:
            self.deaths[kill.victim_eid].append(kill.time)
        # 每名玩家的第一辆载具：单位号 = 槽位 + 固定偏移。
        offsets = Counter(
            eid - seen.slot for eid, seen_list in self.sightings.items()
            for seen in seen_list if self.life(eid, seen.time) == 0
        )
        self.first_offset = offsets.most_common(1)[0][0] if offsets else None

    def life(self, eid: int, time: float) -> int:
        """此刻之前该单位号已被击毁几次。"""
        return bisect.bisect_left(self.deaths.get(eid, []), time)

    def unit(self, eid: int, time: float) -> Sighting | None:
        """此刻占用该单位号的玩家（载具可能未知，记为空串）。"""
        life = self.life(eid, time)
        for seen in self.sightings.get(eid, []):
            if self.life(eid, seen.time) == life:
                return seen
        slot = None if self.first_offset is None else eid - self.first_offset
        if life == 0 and slot in self.slots:
            return Sighting(time, slot, "")
        return None

    def vehicles(self) -> dict[int, list[str]]:
        """槽位 -> 出过手的载具，按时间顺序。"""
        used: dict[int, list[str]] = defaultdict(list)
        for seen in sorted((s for seen_list in self.sightings.values() for s in seen_list), key=lambda s: s.time):
            if seen.vehicle not in used[seen.slot]:
                used[seen.slot].append(seen.vehicle)
        return used


def read_battle(packets: list[Packet]) -> Battle:
    kills = [_parse_kill(p) for p in packets if p.kind == PACKET_MPI and p.body.startswith(KILL)]
    sightings: dict[int, list[Sighting]] = defaultdict(list)
    for packet in packets:
        if packet.kind == PACKET_MPI and packet.body.startswith(HIT):
            eid, slot, vehicle = _parse_hit(packet.body)
            if eid is not None and slot != NO_PLAYER:
                sightings[eid].append(Sighting(packet.time, slot, vehicle))
    for kill in kills:
        if kill.killer_slot is not None and kill.killer_eid is not None:
            sightings[kill.killer_eid].append(Sighting(kill.time, kill.killer_slot, kill.killer_vehicle))
    for seen_list in sightings.values():
        seen_list.sort(key=lambda s: s.time)
    return Battle(player_slots(packets), dict(sightings), kills)
