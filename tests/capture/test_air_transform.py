import pytest

from wt_plotter.capture.air_transform import fit_air_transform, to_ground


POINTS = [(0.2, 0.2), (0.4, 0.3), (0.6, 0.7), (0.8, 0.5)]
TRANSFORM = (0.25, 0.1, 0.25, 0.2)


@pytest.fixture
def pair(obj):
    def make(points=POINTS, scale=0.25):
        return (
            [obj(x, y) for x, y in points],
            [obj(scale * x + 0.1, scale * y + 0.2) for x, y in points],
        )

    return make


def test_recovers_known_transform(pair):
    assert fit_air_transform(*pair()) == pytest.approx(TRANSFORM, abs=1e-9, rel=0)


def test_to_ground_inverts():
    assert to_ground(0.25 * 0.4 + 0.1, 0.25 * 0.3 + 0.2, TRANSFORM) == pytest.approx((0.4, 0.3))


def test_too_few_points(pair):
    assert fit_air_transform(*pair(POINTS[:2])) is None


def test_scale_too_large(pair):
    assert fit_air_transform(*pair(scale=0.6)) is None


def test_error_too_high(pair):
    ground, air = pair()
    for i, point in enumerate(air):
        point["x"] += 0.05 if i % 2 else -0.05
    assert fit_air_transform(ground, air) is None


def test_zero_variance(pair):
    assert fit_air_transform(*pair([(0.5, y) for _, y in POINTS])) is None


def test_excluded_objects_ignored(pair, obj):
    ground, air = pair()
    ground.extend([obj(0.9, 0.7, icon="Player"), obj(0.7, 0.3, type="aircraft")])
    air.extend([obj(0.7, 0.2, icon="Player"), obj(0.9, 0.1, type="aircraft")])
    assert fit_air_transform(ground, air) == pytest.approx(TRANSFORM, abs=1e-9, rel=0)
