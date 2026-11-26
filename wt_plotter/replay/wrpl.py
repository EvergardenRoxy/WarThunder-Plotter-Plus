"""战争雷霆 .wrpl 录像解析：文件头、设置块、结果块和数据包流。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Iterator

import zstandard

from wt_plotter.replay import blk


MAGIC = b"\xe5\xac\x00\x10"
SETTINGS_OFFSET = 1234
# 包时间戳是毫秒 × 256（最后一个包的时间等于结果块的 timePlayed）。
TICKS_PER_SECOND = 256_000
SERVER_MARK = 0x5A

PACKET_CHAT = 3
PACKET_MPI = 4


@dataclass(frozen=True)
class Header:
    level: str
    mission_name: str
    results_offset: int
    session_id: int
    part_number: int
    is_server: bool
    settings_size: int
    start_time: int
    battle_class: str

    @property
    def session_hex(self) -> str:
        return f"{self.session_id:016x}"


@dataclass(frozen=True)
class Packet:
    time: float
    kind: int
    body: bytes


@dataclass(frozen=True)
class ChatMessage:
    time: float
    sender: str
    text: str
    channel: int


def _text(data: bytes, offset: int, size: int) -> str:
    return data[offset:offset + size].split(b"\0", 1)[0].decode("utf-8", "replace")


def decompress(data: bytes) -> bytes:
    """解压 zstd 帧（帧头不带原始长度，不能用 ZstdDecompressor.decompress）。"""
    return zstandard.ZstdDecompressor().decompressobj().decompress(data)


def parse_header(data: bytes) -> Header:
    if data[:4] != MAGIC:
        raise ValueError("not a wrpl file")
    return Header(
        level=_text(data, 8, 128),
        mission_name=_text(data, 396, 128),
        results_offset=struct.unpack_from("<I", data, 684)[0],
        session_id=struct.unpack_from("<Q", data, 732)[0],
        part_number=data[740],
        is_server=data[742] == SERVER_MARK,
        settings_size=struct.unpack_from("<H", data, 748)[0],
        start_time=struct.unpack_from("<I", data, 908)[0],
        battle_class=_text(data, 968, 128),
    )


@dataclass
class Replay:
    """一份录像（服务器录像为合并后的全部分段）。"""

    header: Header
    results: blk.Block | None
    stream: bytes

    def packets(self) -> Iterator[Packet]:
        return iter_packets(self.stream)


def _split(data: bytes) -> tuple[Header, blk.Block | None, bytes]:
    header = parse_header(data)
    # 包流在设置块（服务器录像只有第 0 段有）之后、结果块之前。
    stream_start = SETTINGS_OFFSET + header.settings_size
    stream_end = header.results_offset or len(data)
    results = blk.parse(data[header.results_offset:]) if header.results_offset else None
    return header, results, decompress(data[stream_start:stream_end])


def read_header(path: Path) -> Header:
    with path.open("rb") as file:
        return parse_header(file.read(SETTINGS_OFFSET))


def _read_results(path: Path, header: Header) -> blk.Block:
    with path.open("rb") as file:
        file.seek(header.results_offset)
        return blk.parse(file.read())


def read_summary(paths: list[Path]) -> tuple[Header, blk.Block | None]:
    """只读文件头和结果块，不解压包流。服务器分段：头取第 0 段，结果取最后一个带结果块的分段。"""
    parts = sorted(((read_header(path), path) for path in paths), key=lambda part: part[0].part_number)
    results = next((_read_results(path, header) for header, path in reversed(parts) if header.results_offset), None)
    return parts[0][0], results


def load(path: Path) -> Replay:
    """读取单个客户端录像或单个服务器分段。"""
    return Replay(*_split(path.read_bytes()))


def load_parts(paths: list[Path]) -> Replay:
    """合并服务器录像：第 0 段和奇数段是连续数据，偶数段是供跳转的快照，跳过。

    头取第 0 段，结果取最后一个带结果块的分段。
    """
    parts = sorted((_split(path.read_bytes()) for path in paths), key=lambda part: part[0].part_number)
    parts = [part for part in parts if part[0].part_number == 0 or part[0].part_number % 2]
    if len({part[0].session_id for part in parts}) != 1:
        raise ValueError("replay parts belong to different sessions")
    if parts[0][0].part_number != 0:
        raise ValueError("replay part 0 is missing")
    results = next((part[1] for part in reversed(parts) if part[1] is not None), None)
    return Replay(parts[0][0], results, b"".join(part[2] for part in parts))


def _read_size(data: bytes, pos: int) -> tuple[int, int]:
    """包长度前缀：高位标记字节数。"""
    first = data[pos]
    if first & 0x80:
        if first & 0x40:
            raise ValueError(f"bad packet size prefix at {pos}")
        return first & 0x7F, pos + 1
    if first & 0x40:
        return int.from_bytes(data[pos:pos + 2], "big") ^ 0x4000, pos + 2
    if first & 0x20:
        return int.from_bytes(data[pos:pos + 3], "big") ^ 0x200000, pos + 3
    if first & 0x10:
        return int.from_bytes(data[pos:pos + 4], "big") ^ 0x10000000, pos + 4
    return struct.unpack_from("<I", data, pos + 1)[0], pos + 5


def iter_packets(stream: bytes) -> Iterator[Packet]:
    """逐个解出数据包；类型带 0x10 标记时沿用上一个时间戳。"""
    pos = 0
    ticks = 0
    while pos < len(stream):
        size, pos = _read_size(stream, pos)
        payload = stream[pos:pos + size]
        pos += size
        if not payload:
            continue
        kind = payload[0]
        if kind & 0x10:
            kind ^= 0x10
            body = payload[1:]
        else:
            ticks = struct.unpack_from("<I", payload, 1)[0]
            body = payload[5:]
        yield Packet(ticks / TICKS_PER_SECOND, kind, body)


def parse_chat(packet: Packet) -> ChatMessage:
    body = packet.body
    sender_end = 2 + body[1]
    text_end = sender_end + 1 + body[sender_end]
    return ChatMessage(
        time=packet.time,
        sender=body[2:sender_end].decode("utf-8", "replace"),
        text=body[sender_end + 1:text_end].decode("utf-8", "replace"),
        channel=body[text_end],
    )
