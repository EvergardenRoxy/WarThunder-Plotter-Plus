from dataclasses import replace
import json

from wt_plotter.maps import lookup
from wt_plotter.maps.table import MAPS, UNKNOWN_MAP


def test_exact():
    key = next(iter(MAPS))
    assert lookup.lookup_map(key) is MAPS[key]


def test_fuzzy_within_tolerance():
    key = next(iter(MAPS))
    near_key = key[:-1] + f"{int(key[-1], 16) ^ 1:x}"
    assert lookup.lookup_map(near_key) is MAPS[key]


def test_unknown_logs_missing(monkeypatch, tmp_path):
    log_path = tmp_path / "missing.log"
    monkeypatch.setattr(lookup, "PATHS", replace(lookup.PATHS, missing_hash_log=log_path))
    unknown_hash = "f" * len(next(iter(MAPS)))

    assert lookup.lookup_map(unknown_hash) is UNKNOWN_MAP
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    original = json.loads(lines[0])
    assert original["hash"] == unknown_hash
    assert original.keys() >= {"best_distance", "closest_hash", "closest_map_id"}


def test_empty_hash():
    assert lookup.lookup_map("") is UNKNOWN_MAP


def test_hamming():
    assert lookup.hamming_distance("f0", "0f") == 8
