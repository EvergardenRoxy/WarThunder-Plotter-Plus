from contextlib import closing

import pytest

from wt_plotter.config import PATHS
from wt_plotter.storage.db import connect


@pytest.fixture
def conn(tmp_path):
    with closing(connect(tmp_path / "matches.db")) as connection:
        yield connection


@pytest.fixture
def map_png():
    def read(map_id):
        return (PATHS.maps_dir / f"{map_id}.png").read_bytes()

    return read


@pytest.fixture
def obj():
    def create(x, y, type="ground_model", icon="Tank", color="#fa0C00"):
        return {"x": x, "y": y, "type": type, "icon": icon, "color": color}

    return create
