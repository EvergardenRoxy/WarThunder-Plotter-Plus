from dataclasses import replace
from io import BytesIO

from PIL import Image
import pytest

from wt_plotter.config import PATHS
from wt_plotter.maps import lookup
from wt_plotter.maps.dhash import compute_dhash, is_map_loaded
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


@pytest.mark.parametrize("path", MAP_IMAGES, ids=lambda path: path.stem)
def test_bundled_maps_are_loaded(path):
    assert is_map_loaded(path.read_bytes())


def test_blank_top_is_not_loaded():
    with Image.open(MAP_IMAGES[0]) as image:
        image = image.convert("RGB")
    image.paste((0, 0, 0), (0, 0, image.width, image.height // 3))
    buffer = BytesIO()
    image.save(buffer, "PNG")
    assert not is_map_loaded(buffer.getvalue())
