"""构造最小 wrpl 录像的测试工具（真实录像含其他玩家信息，不入库）。"""

import struct

import zstandard


def uleb(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def build_blk(root):
    """root 为 (参数列表, 子块列表)；参数是 (名, 值)，子块是 (名, 同样结构)。值支持 str/int/bool/float。"""
    names, blocks, params, data = [], [], [], bytearray()

    def name_id(name):
        if name not in names:
            names.append(name)
        return names.index(name)

    def add(name, node):
        # 块号与参数同时登记，参数顺序因此与块号顺序一致。
        for key, value in node[0]:
            if isinstance(value, bool):
                params.append((name_id(key), 9, int(value)))
            elif isinstance(value, int):
                params.append((name_id(key), 2, value & 0xFFFFFFFF))
            elif isinstance(value, float):
                params.append((name_id(key), 3, struct.unpack("<I", struct.pack("<f", value))[0]))
            else:
                params.append((name_id(key), 1, len(data)))
                data.extend(value.encode() + b"\0")
        blocks.append([0 if name is None else name_id(name) + 1, len(node[0]), 0, 0])
        return len(blocks) - 1

    def expand(index, node):
        # 同一块的子块编号必须连续，所以先登记整层再递归。
        child_ids = [add(child_name, child) for child_name, child in node[1]]
        if child_ids:
            blocks[index][2:] = [len(child_ids), child_ids[0]]
        for child_id, (_, child) in zip(child_ids, node[1]):
            expand(child_id, child)

    expand(add(None, root), root)
    name_bytes = b"".join(name.encode() + b"\0" for name in names)
    out = bytearray([1]) + uleb(len(names)) + uleb(len(name_bytes)) + name_bytes
    out += uleb(len(blocks)) + uleb(len(params)) + uleb(len(data)) + data
    for key, kind, raw in params:
        out += struct.pack("<II", key | kind << 24, raw)
    for block_name, count, children, first in blocks:
        out += uleb(block_name) + uleb(count) + uleb(children)
        if children:
            out += uleb(first)
    return bytes(out)


def packet(ticks, kind, body):
    """带时间戳的数据包，长度前缀用 2 字节形式。"""
    payload = bytes([kind]) + struct.pack("<I", ticks) + body
    return (0x4000 | len(payload)).to_bytes(2, "big") + payload


def chat_body(sender, text, channel=0):
    sender, text = sender.encode(), text.encode()
    return b"\x00" + bytes([len(sender)]) + sender + bytes([len(text)]) + text + bytes([channel, 0])


class BitWriter:
    """高位在前的位写入，对应 wt_plotter.replay.bits.BitReader。"""

    def __init__(self):
        self.bits = ""

    def put(self, value, n):
        if n:
            self.bits += f"{value:0{n}b}"
        return self

    def put_bytes(self, data):
        return self.put(int.from_bytes(data, "big"), len(data) * 8) if data else self

    def put_le(self, value, n):
        """每 8 位一段、段内高位在前，低位段先写。"""
        while n > 0:
            k = min(8, n)
            self.put(value & ((1 << k) - 1), k)
            value >>= 8
            n -= k
        return self

    def align(self):
        self.bits += "0" * (-len(self.bits) % 8)
        return self

    def data(self):
        self.align()
        return int(self.bits, 2).to_bytes(len(self.bits) // 8, "big") if self.bits else b""


SIZE_HEADERS = {1: 1, 8: 2, 16: 3, 32: 4, 64: 5, 96: 6, 128: 7}


def field_body(signature, fields):
    """按字段序列化的消息：signature 为 5 字节签名，fields 为 {字段号: 字节串}。"""
    mask = sum(1 << number for number in fields)
    data = b"".join(fields[number] for number in sorted(fields))
    sizes = BitWriter()
    for number in sorted(fields):
        bits = len(fields[number]) * 8
        if bits in SIZE_HEADERS:
            sizes.put(SIZE_HEADERS[bits], 3)
        else:
            sizes.put(0, 3).put_bytes(uleb(bits))
    head = uleb(mask)
    return signature + struct.pack("<H", 2 + len(head) + len(data)) + head + data + sizes.data()


def text(value):
    raw = value.encode()
    return bytes([len(raw)]) + raw


def kill_body(slot, vehicle, victim_eid, killer_eid):
    """击杀：1 击杀者槽位、2 载具、3 受害者单位、4 击杀者单位；单位号高位带标志位 0x800。"""
    return field_body(b"\x00\x02\x58\x58\xf0", {
        1: struct.pack("<I", slot), 2: text(vehicle),
        3: struct.pack("<H", victim_eid | 0x800), 4: struct.pack("<H", killer_eid | 0x800), 10: text(""),
    })


def hit_body(target_eid, slot, vehicle, attacker_eid):
    """重伤：1 目标单位、2 攻击者槽位、3 攻击者载具、4 攻击者单位。"""
    return field_body(b"\x00\x02\x58\x57\xf1", {
        1: struct.pack("<H", target_eid), 2: struct.pack("<I", slot), 3: text(vehicle),
        4: struct.pack("<H", attacker_eid), 5: b"\x00",
    })


def ground_state(x, y, z):
    """地面单位状态体：记录头、有位置、无方向（跳过 3 个 u16）、完整坐标 3 个 float32。"""
    return BitWriter().put(0, 8).put(1, 1).put(0, 48).put(0, 1).put(1, 1).put_bytes(struct.pack("<3f", x, y, z)).data()


def ground_sync_body(units, number, *, full=True, distance=0):
    """地面同步消息：units 为 {单位号: 状态体或 RLE 增量}，number 为本次包序号。"""
    lower, upper = min(units), max(units) + 1
    inner = BitWriter().put_bytes(struct.pack("<HHIH", lower, upper, 0, 0))
    for uid in range(lower, upper):
        if uid not in units:
            inner.put(0, 1)
            continue
        inner.put(1, 1).put(0, 1).put(0, 1).put(0, 2).put(0, 1).put(0, 1).put(0, 8)
        inner.put(1, 1).put(int(full), 1).put_le(distance, 5).put_le(number, 13)
        inner.put_bytes(uleb(len(units[uid]))).align().put_bytes(units[uid])
        inner.put(0, 3).align()
    data = inner.data()
    return b"\x00\x02\x58\x73\xf0" + uleb(len(data) * 8) + data


def player_record(slot, user_id, name):
    return bytes([slot]) + b"\x70\xe9\x01\x30\x60" + struct.pack("<I", user_id) + b"\x00" * 4 + name.encode() + b"\x00" * 8


def player_block(user_id, name, team, kills=0, score=0):
    return ("player", ([
        ("name", name), ("clanTag", ""), ("kills", kills), ("groundKills", 0), ("navalKills", 0),
        ("teamKills", 0), ("aiKills", 0), ("aiGroundKills", 0), ("aiNavalKills", 0), ("assists", 0),
        ("deaths", 0), ("captureZone", 0), ("damageZone", 0), ("score", score),
        ("userId", str(user_id)), ("squadId", 1), ("autoSquad", True), ("team", team),
    ], []))


def build_wrpl(packets, results, *, session=0x72C4, start_time=1_795_534_032, part=0, server=False,
               level="levels/avg_normandy.bin", battle_class="air_ground_Dom", settings=True):
    """拼出一个录像文件：文件头、设置块、zstd 包流、结果块。"""
    settings_blk = build_blk(([("level", level), ("timeLimit", 25)], [])) if settings else b""
    stream = zstandard.ZstdCompressor().compress(b"".join(packets))
    header = bytearray(1234)
    header[0:4] = b"\xe5\xac\x00\x10"
    struct.pack_into("<I", header, 4, 101421)
    header[8:8 + len(level)] = level.encode()
    mission = b"normandy_Dom"
    header[396:396 + len(mission)] = mission
    struct.pack_into("<Q", header, 732, session)
    header[740] = part
    header[742] = 0x5A if server else 0
    struct.pack_into("<H", header, 748, len(settings_blk))
    struct.pack_into("<I", header, 908, start_time)
    header[968:968 + len(battle_class)] = battle_class.encode()
    body = bytes(header) + settings_blk + stream
    if results is not None:
        struct.pack_into("<I", header, 684, len(body))
        body = bytes(header) + settings_blk + stream + build_blk(results)
    return body


def aircraft_state_body(entries):
    """类型 2 包体：首字节后是条目列表。entries 为 [(单位号, 位置或 None)]，None 表示只有单位号；
    单位号比上一条大 1 时省略不写。"""
    out = BitWriter().put(0, 8)
    previous = None
    for uid, position in entries:
        if previous is not None and uid == previous + 1:
            out.put(0, 1)
        else:
            out.put(1, 1).put_bytes(uleb(uid))
        previous = uid
        if position is None:
            out.put(1, 1)
            continue
        out.put(0, 1).put(0, 2).put(0, 1).put(0, 32).put(0, 1).put(0, 1).put_bytes(uleb(0))
        out.put_bytes(struct.pack("<3f", *position)).put(0, 64).align()
        out.put(0, 56).put(0, 8).put(0, 8).put(0, 8).put(0, 4).put(0, 1).put(0, 1)
    out.put(1, 1).put_bytes(uleb(0x7FF))
    return out.data()
