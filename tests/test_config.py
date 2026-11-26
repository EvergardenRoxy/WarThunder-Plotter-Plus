import wt_plotter
from wt_plotter.config import (
    BASE_DIR,
    CAPTURE_ENDPOINTS,
    CAPTURE_SETTINGS,
    DB_SETTINGS,
    HASH_SETTINGS,
    PATHS,
    TRANSFORM_SETTINGS,
)


def test_version():
    assert wt_plotter.__version__ == "0.5.1"


def test_paths_under_data():
    assert PATHS.db_path == BASE_DIR / "data" / "matches.db"
    assert PATHS.maps_dir == BASE_DIR / "data" / "maps"


def test_upstream_values():
    assert CAPTURE_SETTINGS.poll_interval == 0.2
    assert CAPTURE_SETTINGS.match_end_grace_period == 20.0
    assert HASH_SETTINGS.tolerance == 42
    assert TRANSFORM_SETTINGS.min_points == 3
    assert TRANSFORM_SETTINGS.scale_max == 0.5
    assert TRANSFORM_SETTINGS.error_max == 0.01
    assert DB_SETTINGS.position_precision == 5
    assert CAPTURE_ENDPOINTS.base_url == "http://127.0.0.1:8111"
