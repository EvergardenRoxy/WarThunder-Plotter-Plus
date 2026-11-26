"""从录像还原地面单位轨迹：MPI 地面同步消息（客户端 0xF073、服务器 0xF074）。

每条消息给一段单位号范围内各单位的状态体；状态体要么是完整的，要么是相对历史某次的增量
（2 位 RLE 压缩后与基线逐字节异或）。位置在状态体里，可能是 3 个 float32，也可能是量化的两个 u32。
格式参考 WTACRP（MIT）对 wrpl-acmi 解析器的整理：https://github.com/ShioUmiusi/WTACRP
"""

from __future__ import annotations

from collections import defaultdict
import math

from wt_plotter.replay.bits import BitReader
from wt_plotter.replay.messages import Battle
from wt_plotter.replay.tracks import Point, UnitTrack, split_lives
from wt_plotter.replay.wrpl import PACKET_MPI, Packet


GROUND_SYNC = (b"\x00\x02\x58\x73\xf0", b"\x00\x02\x58\x74\xf0")
# 增量基线的历史槽数；槽内记录的包序号取低 13 位。
HISTORY = 32
PACKET_NO_MASK = 0x1FFF
# 量化坐标的范围（米）与高度步长。
QUANT_RANGE = 36000.0
QUANT_ALT_STEP = 0.007629402
QUANT_ALT_BASE = -100.0
# RLE 末字节：最后一个字节里有 1 组还是 2 组码。
RLE_ONE, RLE_TWO = 111, 222
# 位置字段最晚在状态体第 114 字节内结束；异或增量逐字节进行，所以每个状态只需保留这段前缀。
STATE_PREFIX = 128
# 被击毁后的残骸停在原地继续同步：按速度 0 判断连续，离开残骸位置才算新的一命。
WRECK_SPEED = 0.0
# 没有归属、整命都在这个范围（米）内不动的单位是地图上的静态物体，不画。
STATIC_RANGE = 30.0


def rle_decode(src: bytes, limit: int) -> bytes:
    """Dagor 2 位 RLE：每 4 位一组（码 + 参数），展开成 2 位值序列，低位在前装回字节；只解出前 limit 字节。"""
    marker = src[-1]
    if marker not in (RLE_ONE, RLE_TWO):
        raise ValueError(f"bad RLE marker {marker}")
    # 结果按小端整数累加，pos 是已输出的位数；0 段只移动 pos。
    acc = pos = 0
    code = repeat_of = -1
    last = len(src) - 2
    for index, byte in enumerate(src[:-1]):
        if pos >= limit * 8:
            break
        for half in range(1 if index == last and marker == RLE_ONE else 2):
            a, b = (byte >> (half * 4)) & 3, (byte >> (half * 4 + 2)) & 3
            if code != 4:
                code = a
            if code == 0:  # b+3 个 0
                pos += (b + 3) * 2
            elif code == 3:  # b+7 个 0
                pos += (b + 7) * 2
            elif code == 1:  # 本组输出 b，下一组整组作为 2 个值
                code, repeat_of = 4, b
                acc |= b << pos
                pos += 2
            elif code == 2:  # 输出 b
                acc |= b << pos
                pos += 2
            else:  # 上一组 code=1 的续组
                code = -1
                if repeat_of == 0 and a == 0 and b == 0:
                    pos += 39 * 2
                else:
                    acc |= (a | b << 2) << pos
                    pos += 4
    size = min((pos + 7) // 8, limit)
    return (acc & ((1 << size * 8) - 1)).to_bytes(size, "little")


def xor_patch(base: bytes, delta: bytes) -> bytes:
    """逐字节异或；长出的部分取较长的一方。"""
    common = min(len(base), len(delta))
    head = (int.from_bytes(base[:common], "little") ^ int.from_bytes(delta[:common], "little")).to_bytes(common, "little")
    return head + (delta[common:] if len(delta) > len(base) else base[common:])


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def vehicle_position(state: bytes, has_direction: bool) -> tuple[float, float, float] | None:
    """状态体里的世界坐标 (x, 高度, z)；没有位置时返回 None。"""
    reader = BitReader(state)
    reader.skip(8)
    if not reader.bits(1):
        return None
    if has_direction:
        reader.skip(4 * 32)
        if reader.bits(1):
            reader.skip(21 * 32)
    else:
        reader.skip(3 * 16)
    reader.skip(1)
    if reader.bits(1):
        return reader.f32(), reader.f32(), reader.f32()
    a, b = reader.u32(), reader.u32()
    x = _clamp((a >> 10) / 2 ** 21 - 1) * QUANT_RANGE
    y = (((a & 0x3FF) << 10) | (b >> 22)) * QUANT_ALT_STEP + QUANT_ALT_BASE
    z = _clamp((b & 0x3FFFFF) / 2 ** 21 - 1) * QUANT_RANGE
    return x, y, z


class GroundSync:
    """逐条喂入地面同步消息，按单位号累积位置采样。"""

    def __init__(self):
        self.history: dict[int, dict[int, tuple[int, bytes]]] = defaultdict(dict)
        self.samples: dict[int, list[Point]] = defaultdict(list)

    def _state(self, uid: int, full: bool, distance: int, number: int, packed: bytes) -> bytes | None:
        """还原状态体；增量的基线不在历史里时（服务器录像跳过了偶数分段）返回 None。"""
        slots = self.history[uid]
        if full:
            state = packed[:STATE_PREFIX]
        else:
            base_no = number - distance
            tag, base = slots.get(base_no % HISTORY, (None, b""))
            if tag != base_no & PACKET_NO_MASK:
                return None
            state = xor_patch(base, rle_decode(packed, STATE_PREFIX))
        slots[number % HISTORY] = (number & PACKET_NO_MASK, state)
        return state

    def feed(self, time: float, body: bytes) -> None:
        outer = BitReader(body, len(GROUND_SYNC[0]) * 8)
        size = outer.uleb()
        outer.align()
        reader = BitReader(outer.take((size + 7) // 8))
        lower, upper = reader.u16(), reader.u16()
        reader.skip(32 + 16)  # 同步时刻、可靠性序号
        for uid in range(lower, upper):
            if not reader.bits(1):
                continue
            reader.skip(1)
            if reader.bits(1):
                reader.skip(4)
            if reader.bits(1) & reader.bits(1):
                continue
            reader.skip(1)
            has_direction = bool(reader.bits(1))
            turrets = reader.bits(8)
            if not reader.bits(1):
                raise ValueError("uncompressed ground state")
            full = bool(reader.bits(1))
            distance, number = reader.bits_le(5), reader.bits_le(13)
            packed_size = reader.uleb()
            reader.align()
            state = self._state(uid, full, distance, number, reader.take(packed_size))
            position = None if state is None else vehicle_position(state, has_direction)
            if position is not None:
                self.samples[uid].append((time, *position))
            # 其后的可选段：方向、炮塔、传感器。
            if reader.bits(1):
                reader.skip(4 * 32)
            if reader.bits(1):
                for _ in range(turrets):
                    if reader.bits(1):
                        reader.skip(8 + 64)
                        reader.skip(reader.bits(8) * 16)
            if reader.bits(1) and reader.bits(1):
                reader.skip(reader.u32())
            reader.align()


def read_samples(packets: list[Packet]) -> dict[int, list[Point]]:
    """单位号 -> 按时间排列的 (t, x, 高度, z)。"""
    sync = GroundSync()
    for packet in packets:
        if packet.kind == PACKET_MPI and packet.body.startswith(GROUND_SYNC):
            sync.feed(packet.time, packet.body)
    return dict(sync.samples)


def _static(life: list[Point]) -> bool:
    start = life[0]
    return all(math.dist((p[1], p[3]), (start[1], start[3])) < STATIC_RANGE for p in life)


def read_tracks(packets: list[Packet], battle: Battle) -> list[UnitTrack]:
    """每个单位号每一命一条轨迹（去掉无主的静态物体）。"""
    result = []
    for uid, samples in sorted(read_samples(packets).items()):
        lives = split_lives(samples, battle.deaths.get(uid, []), WRECK_SPEED, math.inf)
        result.extend(
            UnitTrack(uid, life, False) for life in lives
            if battle.unit(uid, life[0][0]) is not None or not _static(life)
        )
    return result
