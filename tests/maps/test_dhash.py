from dataclasses import replace

import pytest

from wt_plotter.config import PATHS
from wt_plotter.maps import lookup
from wt_plotter.maps.dhash import compute_dhash
from wt_plotter.maps.table import MAPS


# 上游也无法识别这张图，见 PROGRESS.md。
UPSTREAM_UNRESOLVED = {"air_falklands_map.png"}
MAP_IMAGES = sorted(PATHS.maps_dir.glob("*.png"))


@pytest.mark.parametrize(
    "path", [path for path in MAP_IMAGES if path.name not in UPSTREAM_UNRESOLVED], ids=lambda path: path.stem
)
def test_bundled_maps_resolve(path, monkeypatch, tmp_path):
    monkeypatch.setattr(
        lookup, "PATHS", replace(lookup.PATHS, missing_hash_log=tmp_path / "missing.log")
    )
    assert lookup.lookup_map(compute_dhash(path.read_bytes())).map_id == path.stem


def test_length():
    assert len(compute_dhash(MAP_IMAGES[0].read_bytes())) == len(next(iter(MAPS)))
