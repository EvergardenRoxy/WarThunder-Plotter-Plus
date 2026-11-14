from datetime import datetime, timezone
from functools import cache
import json
import logging
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
