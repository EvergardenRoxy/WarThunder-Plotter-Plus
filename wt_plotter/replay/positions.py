"""把录像轨迹换成查看器使用的 tick 与位置记录（坐标、颜色、图标沿用 8111 的约定）。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from wt_plotter.replay.tracks import UnitTrack
from wt_plotter.storage import db


# 8111 地图对象的颜色与图标。
COLORS = {"player": "#faC81E", "squad": "#67D756", "ally": "#174DFF", "enemy": "#fa0C00"}
PLAYER_ICON = "Player"
AIRCRAFT_ICON = "Fighter"
AIRCRAFT_TYPE = "aircraft"
AIR_ARMY = "air"
# 录像里不知道地面载具和舰船的类别，统一画成中坦、通用舰船图标。
GROUND_ICON = "MediumTank"
SHIP_ICON = "Ship"
GROUND_TYPE = "ground_model"
GROUND_ARMY = "tank"
# 不知道地图范围时，按轨迹外接正方形再留出这一比例的边。
EXTENT_MARGIN = 0.05
# 自动范围至少这么大（米），轨迹只有一个点时也能画。
EXTENT_MIN_SIZE = 1000.0

Bounds = tuple[float, float, float, float]  # (min_x, min_z, max_x, max_z)


def projector(bounds: Bounds) -> Callable[[float, float], tuple[float, float]]:
    """世界坐标 (x, z) -> 地图归一化坐标：x 向右、z 向上（地图 y 向下）。"""
    min_x, min_z, max_x, max_z = bounds
    return lambda x, z: ((x - min_x) / (max_x - min_x), (max_z - z) / (max_z - min_z))


def extent_bounds(tracks: list[UnitTrack]) -> Bounds:
    """包住全部轨迹的正方形范围。"""
    xs = [p[1] for track in tracks for p in track.points]
    zs = [p[3] for track in tracks for p in track.points]
    size = max(max(xs) - min(xs), max(zs) - min(zs), EXTENT_MIN_SIZE) * (1 + 2 * EXTENT_MARGIN)
    cx, cz = (max(xs) + min(xs)) / 2, (max(zs) + min(zs)) / 2
    return (cx - size / 2, cz - size / 2, cx + size / 2, cz + size / 2)


def build_ticks(
    tracks: list[UnitTrack], relations: list[str], labels: list[tuple[str | None, str | None]],
    author_vehicle: str, bounds: Bounds, surface_icon: str | None,
) -> list[tuple[db.TickRecord, list[db.PositionRecord]]]:
    """按帧时间分组；relations、labels 与 tracks 一一对应：相对录像者的关系（player/squad/ally/enemy）
    和 (玩家名, 载具)。
    surface_icon 是陆战/海战里地面单位的图标（帧的兵种和 8111 一样记为坦克），空战为 None。"""
    project = projector(bounds)
    ground = surface_icon is not None
    army = GROUND_ARMY if ground else AIR_ARMY
    frames: dict[float, list[db.PositionRecord]] = defaultdict(list)
    for track, relation, (name, vehicle) in zip(tracks, relations, labels):
        obj_type, icon = (AIRCRAFT_TYPE, AIRCRAFT_ICON) if track.air else (GROUND_TYPE, surface_icon)
        unit_icon = PLAYER_ICON if relation == "player" else icon
        for time, x, _, z in track.points:
            u, v = project(x, z)
            frames[time].append(db.PositionRecord(
                u, v, COLORS[relation], obj_type, unit_icon, 0, unit_name=name, unit_vehicle=vehicle,
            ))
    return [
        (db.TickRecord(time, army, author_vehicle, int(not ground), 0), positions)
        for time, positions in sorted(frames.items())
    ]
