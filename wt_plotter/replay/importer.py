"""把录像写入数据库：关联已有比赛，写入玩家战绩、击杀、聊天，以及飞机或地面单位的轨迹。"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta
import json
import logging
import math
from pathlib import Path
import sqlite3
import struct

import zstandard

from wt_plotter.config import REPLAY_SETTINGS
from wt_plotter.i18n import translate
from wt_plotter.maps.lookup import hash_for_map_id, image_key, is_ground_battle, level_map_id
from wt_plotter.replay import aircraft, blk, ground, messages, positions, tracks, wrpl
from wt_plotter.storage import db


logger = logging.getLogger(__name__)

SERVER_PART = "0000.wrpl"
# 完整解析的版本，解析逻辑有变化时加一；打开比赛时会重新解析版本更旧的录像。只做了轻量导入的记为 0。
PARSER_VERSION = 5
SUMMARY_VERSION = 0
# 结果块里空位的 player 块（没有名字、队伍 0）用这个 userId。
EMPTY_SLOT_USER_ID = "-1"
# 队伍 1、2 互为对方。
OTHER_TEAM = {1: 2, 2: 1}
# AI 单位号按队伍成段分配，相邻号相差不超过这么多算同一段；两队的段之间相差不超过 AI_PAIR_GAP。
AI_UID_GAP = 2
AI_PAIR_GAP = 4


def _countries(results: blk.Block) -> dict[str, str]:
    """客户端录像的结果块带 uiScriptsData，可取国家。"""
    infos = [child for key, child in results.blocks if key == "uiScriptsData"]
    if not infos:
        return {}
    return {str(info.get("id")): info.get("country") for _, info in infos[0].block("playersInfo").blocks}


def _lineups(results: blk.Block) -> dict[str, list[str]]:
    """服务器结果块的 matchingInfo 带部分玩家的出战载具。"""
    lineups = {}
    for key, info in results.block("matchingInfo").blocks:
        crafts = [child for name, child in info.blocks if name == "crafts_info"]
        if crafts:
            lineups[key] = [craft.get("name") for _, craft in crafts[0].blocks]
    return lineups


def _players(results: blk.Block, used: dict[str, list[str]]) -> list[db.ReplayPlayer]:
    countries = _countries(results)
    lineups = _lineups(results)
    players = []
    for player in results.all("player"):
        user_id = player.get("userId")
        if user_id == EMPTY_SLOT_USER_ID:
            continue
        vehicles = list(dict.fromkeys(used.get(user_id, []) + lineups.get(user_id, [])))
        players.append(db.ReplayPlayer(
            user_id=user_id, name=player.get("name"), clan_tag=player.get("clanTag"),
            team=player.get("team"), squad_id=player.get("squadId"), country=countries.get(user_id),
            vehicles=",".join(vehicles),
            kills=player.get("kills"), ground_kills=player.get("groundKills"),
            naval_kills=player.get("navalKills"), ai_kills=player.get("aiKills"),
            ai_ground_kills=player.get("aiGroundKills"), ai_naval_kills=player.get("aiNavalKills"),
            team_kills=player.get("teamKills"), assists=player.get("assists"), deaths=player.get("deaths"),
            capture_zone=player.get("captureZone"), damage_zone=player.get("damageZone"),
            score=player.get("score"),
        ))
    return players


class _Roster:
    """单位（某时刻的单位号）-> 玩家（结果块里的 player 块）以及相对录像者的关系。"""

    def __init__(self, battle: messages.Battle, results: blk.Block, author_user_id: str | None):
        self.battle = battle
        self.results = results
        self.players = {player.get("userId"): player for player in results.all("player")}
        self.me = self.players.get(author_user_id) if author_user_id else None

    def player(self, eid: int, time: float) -> blk.Block | None:
        unit = self.battle.unit(eid, time)
        user_id = None if unit is None else self.battle.slots.get(unit.slot)
        return None if user_id is None else self.players.get(str(user_id))

    def name(self, eid: int, time: float) -> str | None:
        player = self.player(eid, time)
        return None if player is None else player.get("name")

    def _unowned_teams(self, eids: set[int]) -> dict[int, int]:
        """不属于玩家的单位（AI）的队伍：被玩家击毁的算击杀者的对方；单位号相邻的一段 AI 同属一队，
        按整段的多数定。AI 按队伍成对分段（队伍 1 一段、紧接着队伍 2 一段），没有证据的段取紧邻段的对方。"""
        votes: dict[int, Counter] = defaultdict(Counter)
        for kill in self.battle.kills:
            killer = None if kill.killer_eid is None else self.player(kill.killer_eid, kill.time)
            if killer is not None and kill.victim_eid in eids:
                votes[kill.victim_eid][OTHER_TEAM[killer.get("team")]] += 1
        runs: list[list[int]] = []
        for eid in sorted(eids):
            if runs and eid - runs[-1][-1] <= AI_UID_GAP:
                runs[-1].append(eid)
            else:
                runs.append([eid])
        run_teams = []
        for run in runs:
            total = sum((votes[uid] for uid in run), Counter())
            run_teams.append(total.most_common(1)[0][0] if total else None)
        evidence = list(run_teams)
        for i, run in enumerate(runs):
            if evidence[i] is not None:
                continue
            neighbours = [j for j in (i - 1, i + 1) if 0 <= j < len(runs) and evidence[j] is not None
                          and min(abs(runs[j][0] - run[-1]), abs(run[0] - runs[j][-1])) <= AI_PAIR_GAP]
            if neighbours:
                run_teams[i] = OTHER_TEAM[evidence[neighbours[0]]]
        return {uid: team for run, team in zip(runs, run_teams) if team is not None for uid in run}

    def relations(self, unit_tracks: list[tracks.UnitTrack]) -> list[str]:
        """与 unit_tracks 一一对应。"""
        my_team = self.me.get("team") if self.me else 1
        owners = [self.player(track.eid, track.points[0][0]) for track in unit_tracks]
        teams = [None if player is None else player.get("team") for player in owners]
        # 成段分队只在飞机上成立；陆战里无主的地面单位多是玩家复活后的载具，号段两队混杂。
        ai_teams = self._unowned_teams({t.eid for t, player in zip(unit_tracks, owners) if player is None and t.air})
        teams = [ai_teams.get(t.eid) if team is None and t.air else team for t, team in zip(unit_tracks, teams)]
        # 仍不知道队伍的，按起点归到最近的已知队伍。
        starts = [track.points[0][1::2] for track in unit_tracks]
        known = [(start, team) for start, team in zip(starts, teams) if team is not None]
        relations = []
        for player, team, start in zip(owners, teams, starts):
            if team is None and known:
                team = min(known, key=lambda item: math.dist(item[0], start))[1]
            if self.me is not None and player is self.me:
                relations.append("player")
            elif (self.me is not None and player is not None and not self.me.get("autoSquad")
                  and player.get("squadId") == self.me.get("squadId")):
                relations.append("squad")
            else:
                relations.append("ally" if team in (my_team, None) else "enemy")
        return relations

    def labels(self, unit_tracks: list[tracks.UnitTrack]) -> list[tuple[str | None, str | None]]:
        """与 unit_tracks 一一对应的 (玩家名, 载具)。载具取这一命出手时报出的；没出过手但这名玩家
        整场只知道一种载具（出过手的加上结果块的出战载具）时用它。AI 两项都是 None。"""
        used = self.battle.vehicles()
        lineups = _lineups(self.results)
        labels = []
        for track in unit_tracks:
            unit = self.battle.unit(track.eid, track.points[0][0])
            user_id = None if unit is None else self.battle.slots.get(unit.slot)
            player = None if user_id is None else self.players.get(str(user_id))
            if player is None:
                labels.append((None, None))
                continue
            known = set(used.get(unit.slot, [])) | set(lineups.get(str(user_id), []))
            vehicle = unit.vehicle or (known.pop() if len(known) == 1 else None)
            labels.append((player.get("name"), vehicle))
        return labels

    def vehicle(self) -> str:
        """录像者最后用过的载具（出过手才知道）。"""
        if self.me is None:
            return ""
        slots = [slot for slot, user_id in self.battle.slots.items() if str(user_id) == self.me.get("userId")]
        used = self.battle.vehicles().get(slots[0], []) if slots else []
        return used[-1] if used else ""


def _kill_events(kills: list[db.ReplayKill], lang: str) -> list[db.EventRecord]:
    """把录像击杀写成战斗播报，供查看器的播报列表和时间轴使用。"""
    events = []
    for index, kill in enumerate(kills):
        if kill.killer is None:
            victim = kill.victim or translate(lang, "replay.unknown_victim")
            msg = translate(lang, "replay.event_crash", victim=victim)
        elif kill.victim is None:
            msg = translate(lang, "replay.event_kill_unknown", killer=kill.killer, killer_vehicle=kill.killer_vehicle)
        else:
            msg = translate(lang, "replay.event_kill", killer=kill.killer, killer_vehicle=kill.killer_vehicle,
                            victim=kill.victim, victim_vehicle=kill.victim_vehicle or "?")
        events.append(db.EventRecord(kill.timestamp, index, msg, json.dumps(asdict(kill), ensure_ascii=False)))
    return events


def _write_tracks(
    conn: sqlite3.Connection, match_id: int, unit_tracks: list[tracks.UnitTrack], roster: _Roster,
    kills: list[db.ReplayKill], level_hash: str | None, is_ground: bool, lang: str,
) -> None:
    match = db.get_match(conn, match_id)
    map_hash = match.map_hash or level_hash
    bounds = db.get_map_bounds(conn, image_key(map_hash)) if map_hash else None
    ticks = positions.build_ticks(
        unit_tracks, roster.relations(unit_tracks), roster.labels(unit_tracks), roster.vehicle(),
        bounds or positions.extent_bounds(unit_tracks), is_ground,
    )
    events = _kill_events(kills, lang)
    # 没有地图范围就没法把轨迹画到底图上，宁可不显示底图；采集过这张图后重新导入会补上。
    db.set_map_hash(conn, match_id, map_hash if bounds else "")
    db.clear_match_data(conn, match_id)
    for tick, records in ticks:
        db.add_tick(conn, match_id, tick, records)
    db.add_events(conn, match_id, events)


def _ground_battle_tracks(packets: list, battle: messages.Battle) -> list[tracks.UnitTrack]:
    """陆战：地面单位和飞机。地面单位各自的采样时刻不同，全部重采样到统一的帧上才能一帧画出所有单位。"""
    step, gap = REPLAY_SETTINGS.ground_frame_interval, REPLAY_SETTINGS.ground_max_gap
    units = ground.read_tracks(packets, battle) + aircraft.read_tracks(packets, battle)
    resampled = [tracks.UnitTrack(t.eid, tracks.resample(t.points, step, gap), t.air) for t in units]
    return [track for track in resampled if track.points]


def _link_match(conn: sqlite3.Connection, header: wrpl.Header, duration: float) -> tuple[int, str | None]:
    """找到录像所属的比赛（同场次、或开始时间相近的 8111 记录），没有就新建；返回比赛 ID 和关卡对应的地图哈希。"""
    started = datetime.fromtimestamp(header.start_time)
    ended_at = (started + timedelta(seconds=duration)).isoformat()
    match_id = db.find_replay_match(conn, header.session_hex) or db.find_match_near(
        conn, started.isoformat(), REPLAY_SETTINGS.match_start_tolerance, header.session_hex
    )
    map_id = level_map_id(header.level, header.battle_class)
    level_hash = map_id and hash_for_map_id(map_id)
    if match_id is None:
        match_id = db.create_finished_match(conn, started.isoformat(), ended_at, level_hash)
    db.extend_match_end(conn, match_id, ended_at)
    return match_id, level_hash


def _record(
    header: wrpl.Header, results: blk.Block, duration: float, author_user_id: str | None,
    wrote_tracks: bool, source: str, parser_version: int,
) -> db.ReplayRecord:
    return db.ReplayRecord(
        session_id=header.session_hex, is_server=int(header.is_server), level=header.level,
        mission=header.mission_name, battle_class=header.battle_class,
        started_at=datetime.fromtimestamp(header.start_time).isoformat(),
        duration=duration, status=results.get("status", None),
        author=results.get("author", None), author_user_id=author_user_id,
        wrote_tracks=int(wrote_tracks), source=source, parser_version=parser_version,
    )


def _author(conn: sqlite3.Connection, header: wrpl.Header, results: blk.Block) -> str | None:
    """服务器录像的结果块没有录像者，沿用同场本地录像记下的。"""
    return results.get("authorUserId", None) or db.find_session_author(conn, header.session_hex)


def import_summary(conn: sqlite3.Connection, header: wrpl.Header, results: blk.Block | None, source: str) -> int:
    """轻量导入：只用文件头和结果块，写入比赛、录像信息和玩家战绩；击杀、聊天和轨迹等打开比赛时再解析。"""
    if results is None:
        raise ValueError(f"replay {header.session_hex} has no results block")
    duration = results.get("timePlayed")
    # 先算完再写库，算到一半出错不会留下空比赛。
    record = _record(header, results, duration, _author(conn, header, results), False, source, SUMMARY_VERSION)
    players = _players(results, {})
    match_id, _ = _link_match(conn, header, duration)
    db.save_replay(conn, match_id, record, players, [], [])
    logger.info("Imported replay summary %s into match %s", header.session_hex, match_id)
    return match_id


def import_replay(conn: sqlite3.Connection, replay: wrpl.Replay, source: str, lang: str) -> int:
    """完整导入一份录像，返回关联的比赛 ID。没有 8111 记录的比赛还会写入录像还原的轨迹和播报。"""
    header = replay.header
    if replay.results is None:
        raise ValueError(f"replay {header.session_hex} has no results block")
    packets = list(replay.packets())
    battle = messages.read_battle(packets)
    duration = replay.results.get("timePlayed")
    author_user_id = _author(conn, header, replay.results)
    roster = _Roster(battle, replay.results, author_user_id)
    is_ground = is_ground_battle(header.battle_class)
    unit_tracks = _ground_battle_tracks(packets, battle) if is_ground else aircraft.read_tracks(packets, battle)

    # 先算完再写库，算到一半出错不会留下空比赛或半套数据。
    used = {str(battle.slots[slot]): vehicles for slot, vehicles in battle.vehicles().items() if slot in battle.slots}
    players = _players(replay.results, used)
    chat = [
        db.ReplayChat(line.time, line.sender, line.text)
        for line in (wrpl.parse_chat(p) for p in packets if p.kind == wrpl.PACKET_CHAT)
    ]

    kills = []
    for kill in battle.kills:
        victim = battle.unit(kill.victim_eid, kill.time)
        kills.append(db.ReplayKill(
            timestamp=kill.time,
            killer=None if kill.killer_eid is None else roster.name(kill.killer_eid, kill.time),
            killer_vehicle=kill.killer_vehicle,
            victim=roster.name(kill.victim_eid, kill.time),
            victim_vehicle=(victim and victim.vehicle) or None,
        ))

    match_id, level_hash = _link_match(conn, header, duration)
    # 已有 8111 轨迹的比赛不动；录像写的轨迹，服务器录像可以替换本地录像的。
    writer = db.tracks_writer(conn, match_id)
    write = bool(unit_tracks) and (
        db.count_positions(conn, match_id) == 0 if writer is None else int(header.is_server) >= writer
    )
    if write:
        _write_tracks(conn, match_id, unit_tracks, roster, kills, level_hash, is_ground, lang)

    record = _record(header, replay.results, duration, author_user_id, write, source, PARSER_VERSION)
    db.save_replay(conn, match_id, record, players, kills, chat)
    logger.info("Imported replay %s into match %s", header.session_hex, match_id)
    return match_id


def load_path(path: Path) -> wrpl.Replay:
    """文件读作客户端录像；含 0000.wrpl 的目录读作服务器分段录像。"""
    if path.is_dir():
        return wrpl.load_parts(sorted(path.glob("*.wrpl")))
    return wrpl.load(path)


def replay_sources(paths: list[Path]) -> list[Path]:
    """展开命令行参数：服务器分段目录保持整体，其它目录取其中的录像文件。"""
    sources = []
    for path in paths:
        if path.is_dir() and not (path / SERVER_PART).exists():
            sources.extend(sorted(path.glob("*.wrpl")))
        else:
            sources.append(path)
    return sources


def read_header(path: Path) -> wrpl.Header:
    """只读文件头；服务器分段目录读第 0 段。"""
    return wrpl.read_header(path / SERVER_PART if path.is_dir() else path)


def _files(source: Path) -> list[Path]:
    """录像来源对应的文件：服务器分段目录取全部分段。"""
    return sorted(source.glob("*.wrpl")) if source.is_dir() else [source]


# 录像文件读不到、不完整（正在写入）或格式认不出时抛出的异常。
REPLAY_ERRORS = (OSError, ValueError, struct.error, zstandard.ZstdError)
# 手动导入的客户端录像存放的子目录（服务器录像和下载的一样按场次建目录）。
LOCAL_UPLOAD_DIR = "local"


def store_uploads(files: list[tuple[str, bytes]], target_dir: Path) -> tuple[list[Path], list[str]]:
    """把手动选择的录像存进数据目录（打开比赛时还要读原文件），返回录像来源和逐个文件的失败原因。
    服务器分段按场次放进同一目录，客户端录像按场次命名。"""
    sources, errors = set(), []
    for name, data in files:
        try:
            header = wrpl.parse_header(data[:wrpl.SETTINGS_OFFSET])
        except REPLAY_ERRORS as error:
            errors.append(f"{name}: {error!r}")
            continue
        if header.is_server:
            path = target_dir / header.session_hex / f"{header.part_number:04d}.wrpl"
            sources.add(path.parent)
        else:
            path = target_dir / LOCAL_UPLOAD_DIR / f"{header.session_hex}.wrpl"
            sources.add(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return sorted(sources), errors


def import_new(conn: sqlite3.Connection, paths: list[Path]) -> tuple[list[int], list[str]]:
    """轻量导入尚未导入过的录像，返回比赛 ID 和逐个文件的失败原因。"""
    match_ids, errors = [], []
    for source in replay_sources(paths):
        # 游戏可能正在写入最新的录像，单个文件失败不影响其它文件。
        try:
            header = read_header(source)
            if db.replay_parser_version(conn, header.session_hex, header.is_server) is not None:
                continue
            match_ids.append(import_summary(conn, *wrpl.read_summary(_files(source)), str(source)))
        except REPLAY_ERRORS as error:
            logger.warning("Failed to import %s: %r", source, error)
            errors.append(f"{source.name}: {error!r}")
    return match_ids, errors


def ensure_parsed(conn: sqlite3.Connection, match_id: int, lang: str) -> None:
    """完整解析这场比赛里还没解析、或用旧版本解析的录像（打开比赛时调用）。"""
    for source in db.replays_to_parse(conn, match_id, PARSER_VERSION):
        # 录像文件可能已被删除或损坏：保留轻量导入的信息并记下原因（战报里显示），比赛照常打开。
        try:
            import_replay(conn, load_path(Path(source)), source, lang)
        except REPLAY_ERRORS as error:
            logger.warning("Failed to parse %s: %r", source, error)
            db.mark_replay_failed(conn, source, PARSER_VERSION, repr(error))
