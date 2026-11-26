from datetime import datetime, timezone
from functools import cache
import json
import logging
from pathlib import Path
from string import hexdigits

from wt_plotter.config import HASH_SETTINGS, PATHS
from wt_plotter.maps.table import MAPS, UNKNOWN_MAP, MapInfo


logger = logging.getLogger(__name__)


def hamming_distance(a: str, b: str) -> int:
    length = max(len(a), len(b))
    return sum(
        (int(left, 16) ^ int(right, 16)).bit_count() if left in hexdigits and right in hexdigits else 4
        for left, right in zip(a.ljust(length, "0"), b.ljust(length, "0"))
    )


def _append_missing_hash(dhash: str, best_distance: int, closest_hash: str, closest_map_id: str) -> None:
    log_path = PATHS.missing_hash_log
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "time": datetime.now(timezone.utc).isoformat(),
        "hash": dhash,
        "length": len(dhash),
        "best_distance": best_distance,
        "closest_hash": closest_hash,
        "closest_map_id": closest_map_id,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


@cache
def lookup_map(dhash: str) -> MapInfo:
    if not dhash:
        return UNKNOWN_MAP
    if dhash in MAPS:
        logger.debug("Exact hash match: %s", dhash)
        return MAPS[dhash]

    distance, closest_hash = min(
        ((hamming_distance(dhash, known_hash), known_hash) for known_hash in MAPS),
        key=lambda candidate: candidate[0],
    )
    closest = MAPS[closest_hash]
    if distance <= HASH_SETTINGS.tolerance:
        logger.info("Fuzzy hash match: %s (distance: %s)", closest.map_id, distance)
        return closest

    logger.warning("No hash match found for: %s (%s chars)", dhash, len(dhash))
    _append_missing_hash(dhash, distance, closest_hash, closest.map_id)
    return UNKNOWN_MAP


def hash_for_map_id(map_id: str) -> str | None:
    """按地图 ID 反查内置哈希；没有截图哈希的录像比赛靠它显示地图。"""
    return next((dhash for dhash, info in MAPS.items() if info.map_id == map_id), None)


def image_key(map_hash: str) -> str:
    """地图图片与地图范围的存储键：已知地图用 ID，未知地图用哈希。"""
    map_id = lookup_map(map_hash).map_id
    return map_hash if map_id in ("unknown", "no_map") else map_id


def is_ground_battle(battle_class: str) -> bool:
    """录像的战斗类别：陆战是 air_ground_*，其余按空战处理。"""
    return battle_class.startswith("air_ground")


def is_naval_battle(battle_class: str) -> bool:
    """录像的战斗类别：海战是 air_naval_*。"""
    return battle_class.startswith("air_naval")


def level_map_id(level: str, battle_class: str) -> str | None:
    """关卡文件对应的地图 ID：陆战、海战用 8111 显示的 tankmap，空战用空战地图。"""
    name = Path(level).stem
    known = {info.map_id for info in MAPS.values()}
    surface = is_ground_battle(battle_class) or is_naval_battle(battle_class)
    tankmap = [f"{name}_tankmap"] if surface else []
    candidates = tankmap + [f"{name}_map", name]
    return next((map_id for map_id in candidates if map_id in known), None)
