from collections import defaultdict
from statistics import mean

from wt_plotter.config import CAPTURE_FILTERS, TRANSFORM_SETTINGS


def _group_by_icon(objects: list[dict]) -> dict[str, list[dict]]:
    groups = defaultdict(list)
    for obj in objects:
        if (
            str(obj.get("icon", "")).lower() not in CAPTURE_FILTERS.excluded_icons
            and str(obj.get("type", "")).lower() not in CAPTURE_FILTERS.excluded_types
        ):
            groups[obj.get("icon", "unknown")].append(obj)
    return groups


def _fit_axis(ground: list[float], air: list[float]) -> tuple[float, float] | None:
    ground_mean = mean(ground)
    air_mean = mean(air)
    offsets = [value - ground_mean for value in ground]
    variance = sum(offset ** 2 for offset in offsets)
    if variance == 0:
        return None
    scale = sum(offset * (value - air_mean) for offset, value in zip(offsets, air)) / variance
    if not 0 < scale <= TRANSFORM_SETTINGS.scale_max:
        return None
    shift = air_mean - scale * ground_mean
    error = mean(abs(scale * x + shift - y) for x, y in zip(ground, air))
    return (scale, shift) if error <= TRANSFORM_SETTINGS.error_max else None


def fit_air_transform(prev_objects: list[dict], curr_objects: list[dict]) -> tuple[float, float, float, float] | None:
    previous = _group_by_icon(prev_objects)
    current = _group_by_icon(curr_objects)
    pairs = [(left, right) for icon, group in previous.items() for left, right in zip(group, current.get(icon, ()))]
    if len(pairs) < TRANSFORM_SETTINGS.min_points:
        return None
    x_fit = _fit_axis([left.get("x", 0) for left, _ in pairs], [right.get("x", 0) for _, right in pairs])
    y_fit = _fit_axis([left.get("y", 0) for left, _ in pairs], [right.get("y", 0) for _, right in pairs])
    return (*x_fit, *y_fit) if x_fit is not None and y_fit is not None else None


def to_ground(x: float, y: float, transform: tuple[float, float, float, float]) -> tuple[float, float]:
    a, b, c, d = transform
    return (x - b) / a, (y - d) / c
