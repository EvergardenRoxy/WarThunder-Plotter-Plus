"""Dagor 二进制 BLK（FAT 格式，首字节 0x01）解码。"""

from __future__ import annotations

from dataclasses import dataclass, field
import struct


FAT = 0x01
_MISSING = object()


@dataclass
class Block:
    """BLK 块：参数和子块都按出现顺序保存，名字可以重复。"""

    params: list[tuple[str, object]] = field(default_factory=list)
    blocks: list[tuple[str, "Block"]] = field(default_factory=list)

    def get(self, name: str, default=_MISSING):
        """取第一个同名参数；没有时返回 default，没给 default 就报 KeyError。"""
        for key, value in self.params:
            if key == name:
                return value
        if default is _MISSING:
            raise KeyError(name)
        return default

    def block(self, name: str) -> "Block":
        for key, child in self.blocks:
            if key == name:
                return child
        raise KeyError(name)

    def all(self, name: str) -> list["Block"]:
        return [child for key, child in self.blocks if key == name]


def _uleb(data: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return value, pos


def _cstr(data: bytes, pos: int) -> str:
    return data[pos:data.index(b"\0", pos)].decode("utf-8", "replace")


# 类型号 -> (struct 格式, 是否存放在参数数据区)
_TYPES = {
    3: ("<f", False), 4: ("<2f", True), 5: ("<3f", True), 6: ("<4f", True),
    7: ("<2i", True), 8: ("<3i", True), 10: ("<4B", False), 11: ("<12f", True), 12: ("<q", True),
}


def parse(data: bytes) -> Block:
    """解析 FAT BLK，返回根块。"""
    if data[0] != FAT:
        raise ValueError(f"unsupported BLK type 0x{data[0]:02x}")
    pos = 1
    name_count, pos = _uleb(data, pos)
    names_size, pos = _uleb(data, pos)
    names = data[pos:pos + names_size].split(b"\0")[:name_count]
    names = [name.decode("utf-8", "replace") for name in names]
    pos += names_size

    block_count, pos = _uleb(data, pos)
    param_count, pos = _uleb(data, pos)
    data_size, pos = _uleb(data, pos)
    param_data = data[pos:pos + data_size]
    pos += data_size

    params = []
    for _ in range(param_count):
        head, raw = struct.unpack_from("<II", data, pos)
        pos += 8
        params.append((names[head & 0xFFFFFF], _param_value(head >> 24, raw, names, param_data)))

    blocks = [Block() for _ in range(block_count)]
    block_names = []
    next_param = 0
    for block in blocks:
        name_id, pos = _uleb(data, pos)
        own_params, pos = _uleb(data, pos)
        child_count, pos = _uleb(data, pos)
        first_child = 0
        if child_count:
            first_child, pos = _uleb(data, pos)
        block_names.append(names[name_id - 1] if name_id else "")
        block.params = params[next_param:next_param + own_params]
        next_param += own_params
        block._children = range(first_child, first_child + child_count)
    for block in blocks:
        block.blocks = [(block_names[i], blocks[i]) for i in block._children]
        del block._children
    return blocks[0]


def _param_value(kind: int, raw: int, names: list[str], param_data: bytes):
    if kind == 1:
        # 最高位表示字符串在名字表里，否则是数据区偏移。
        return names[raw & 0x7FFFFFFF] if raw & 0x80000000 else _cstr(param_data, raw)
    if kind == 2:
        return struct.unpack("<i", struct.pack("<I", raw))[0]
    if kind == 9:
        return bool(raw)
    fmt, indirect = _TYPES[kind]
    source = param_data[raw:] if indirect else struct.pack("<I", raw)
    values = struct.unpack_from(fmt, source)
    return values[0] if len(values) == 1 else values
