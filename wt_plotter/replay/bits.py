"""录像消息的位流读取：高位在前的位读取器和 Dagor 网络层的按字段序列化（IdFieldSerializer32）。

格式参考 WTACRP（MIT）对 wrpl-acmi 解析器的整理：https://github.com/ShioUmiusi/WTACRP
"""

from __future__ import annotations

import struct


class BitReader:
    """字节内高位在前；多字节整数按小端。"""

    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def bits(self, n: int) -> int:
        end = self.pos + n
        if end > len(self.data) * 8:
            raise IndexError(f"bit read past end: {end} > {len(self.data) * 8}")
        first, last = self.pos >> 3, (end + 7) >> 3
        chunk = int.from_bytes(self.data[first:last], "big")
        self.pos = end
        return (chunk >> (last * 8 - end)) & ((1 << n) - 1)

    def skip(self, n: int) -> None:
        self.pos += n

    def align(self) -> None:
        self.pos = (self.pos + 7) & ~7

    def take(self, n: int) -> bytes:
        if self.pos & 7:
            return self.bits(n * 8).to_bytes(n, "big")
        start = self.pos >> 3
        if start + n > len(self.data):
            raise IndexError(f"byte read past end: {start + n} > {len(self.data)}")
        self.pos += n * 8
        return self.data[start:start + n]

    def u16(self) -> int:
        return int.from_bytes(self.take(2), "little")

    def u32(self) -> int:
        return int.from_bytes(self.take(4), "little")

    def f32(self) -> float:
        return struct.unpack("<f", self.take(4))[0]

    def uleb(self) -> int:
        """ReadCompressed：LEB128。"""
        value = shift = 0
        while True:
            byte = self.bits(8)
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                return value

    def bits_le(self, n: int) -> int:
        """每 8 位一段、段内高位在前，各段按小端拼起来。"""
        value = shift = 0
        while n > 0:
            k = min(8, n)
            value |= self.bits(k) << shift
            shift += 8
            n -= k
        return value

    def string(self) -> str:
        """1 字节长度 + UTF-8。"""
        return self.take(self.bits(8)).decode("utf-8", "replace")


# 尺寸表的 3 位头 -> 字段位数；0 表示后面跟 LEB128 位数。
_SIZE_BITS = {1: 1, 2: 8, 3: 16, 4: 32, 5: 64, 6: 96, 7: 128}


def read_fields(data: bytes) -> dict[int, BitReader]:
    """按字段序列化：u16 尺寸表字节偏移、LEB128 字段位掩码、各字段数据、尺寸表。

    返回 字段号 -> 定位到该字段起点的读取器。
    """
    reader = BitReader(data)
    table = reader.u16()
    mask = reader.uleb()
    start = reader.pos
    numbers = [i for i in range(mask.bit_length()) if mask >> i & 1]
    sizes = BitReader(data, table * 8)
    fields = {}
    for number in numbers:
        header = sizes.bits(3)
        fields[number] = BitReader(data, start)
        start += _SIZE_BITS[header] if header else sizes.uleb()
    return fields
