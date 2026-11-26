"""录像轨迹的公共部分：轨迹点、按命切分和重采样（飞机和地面单位共用）。"""

from __future__ import annotations

from dataclasses import dataclass
import math


# 判断采样是否连续时允许的额外位移（米）。
CONTINUITY_MARGIN = 50.0

Point = tuple[float, float, float, float]  # (t, x, 高度, z)


@dataclass(frozen=True)
class UnitTrack:
    eid: int
    points: list[Point]
    air: bool


def split_lives(samples: list[Point], deaths: list[float], max_speed: float, max_gap: float) -> list[list[Point]]:
    """按击毁时刻切成多命。击毁后的采样若与上一个采样间隔不超过 max_gap，且离击毁位置不超过 max_speed
    能走的距离，就是残骸，丢掉；离开残骸范围或断档后才算下一命开始。"""
    lives: list[list[Point]] = [[]]
    death_index, wreck, prev, anchor = 0, False, None, None
    for point in samples:
        while death_index < len(deaths) and point[0] > deaths[death_index]:
            lives.append([])
            death_index += 1
            wreck, anchor = prev is not None, prev
        if wreck:
            reach = max_speed * (point[0] - anchor[0]) + CONTINUITY_MARGIN
            wreck = point[0] - prev[0] <= max_gap and math.dist(point[1:], anchor[1:]) <= reach
        prev = point
        if not wreck:
            lives[-1].append(point)
    return [life for life in lives if life]


def resample(points: list[Point], step: float, max_gap: float) -> list[Point]:
    """在 step 的整数倍时刻线性插值；相邻采样间隔超过 max_gap 的空档不插。"""
    result = []
    for (t0, *p0), (t1, *p1) in zip(points, points[1:]):
        if t1 - t0 > max_gap:
            continue
        time = math.ceil(t0 / step) * step
        while time < t1:
            k = (time - t0) / (t1 - t0)
            result.append((round(time, 3), *(a + (b - a) * k for a, b in zip(p0, p1))))
            time += step
    return result
