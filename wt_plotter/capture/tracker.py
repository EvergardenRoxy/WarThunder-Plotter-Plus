from collections.abc import Callable
from dataclasses import dataclass, field
import json
from pathlib import Path
from sqlite3 import Connection

from wt_plotter.capture.air_transform import fit_air_transform, to_ground
from wt_plotter.config import CAPTURE_DEFAULTS, CAPTURE_FILTERS, CAPTURE_SETTINGS
from wt_plotter.maps.dhash import compute_dhash, is_map_loaded
from wt_plotter.maps.lookup import image_key, lookup_map
from wt_plotter.maps.table import BattleType, MapInfo, UNKNOWN_MAP
from wt_plotter.storage import db


@dataclass
class _MatchState:
    match_id: int | None = None
    started_at: float = 0.0
    map_hash: str = ""
    map_info: MapInfo = UNKNOWN_MAP
    map_retry_at: float | None = None
    air_map_hash: str = ""
    invalid_since: float | None = None
    nuke_detected: bool = False
    saved_pois: set[tuple[str, float, float]] = field(default_factory=set)
    initial_capture_set: bool = False
    base_capture_signature: frozenset[tuple[float, float]] = frozenset()
    previous_objects: list[dict] = field(default_factory=list)
    previous_air_view: bool = False
    transform: tuple[float, float, float, float] | None = None
    damage_cursor: int = 0
    damage_primed: bool = False
    bounded_maps: set[str] = field(default_factory=set)


class MatchTracker:
    def __init__(self, conn: Connection, fetch_map_image: Callable[[], bytes | None], maps_dir: Path):
        self.conn = conn
        self.fetch_map_image = fetch_map_image
        self.maps_dir = maps_dir
        self._state = _MatchState()
        self.army_type = CAPTURE_DEFAULTS.army_type
        self.vehicle_type = CAPTURE_DEFAULTS.vehicle_type

    @property
    def match_id(self) -> int | None:
        return self._state.match_id

    def tick(self, now: float, map_valid: bool, indicators: dict | None, objects: list[dict] | None) -> None:
        if not map_valid:
            if self.match_id is not None:
                self._handle_invalid_match(now)
            return

        if self.match_id is None:
            self._start_match(now, self.fetch_map_image())
        elif self._state.map_retry_at is not None and now >= self._state.map_retry_at:
            self._retry_map_image(now)
        self._state.invalid_since = None
        if objects:
            self._capture_positions(now, indicators or {}, objects)

    @property
    def damage_cursor(self) -> int:
        return self._state.damage_cursor

    def record_damage(self, now: float, entries: list[dict]) -> None:
        """保存播报；每场第一批只推进游标，跳过上一场残留的消息。"""
        state = self._state
        if state.match_id is None:
            return
        if entries:
            state.damage_cursor = max(entry["id"] for entry in entries)
        if not state.damage_primed:
            state.damage_primed = True
            return
        db.add_events(self.conn, state.match_id, [
            db.EventRecord(now - state.started_at, entry["id"], entry["msg"], json.dumps(entry, ensure_ascii=False))
            for entry in entries
        ])
        if not state.nuke_detected and any(_is_nuke_message(entry["msg"]) for entry in entries):
            db.set_nuke(self.conn, state.match_id)
            state.nuke_detected = True

    def record_map_bounds(self, map_info: dict) -> None:
        """记下当前显示地图的世界坐标范围，供录像轨迹换算到地图上。"""
        state = self._state
        air = state.previous_air_view and state.air_map_hash
        map_hash = state.air_map_hash if air else state.map_hash
        if state.match_id is None or not map_hash or map_hash in state.bounded_maps:
            return
        (min_x, min_z), (max_x, max_z) = map_info["map_min"], map_info["map_max"]
        db.save_map_bounds(self.conn, image_key(map_hash), (min_x, min_z, max_x, max_z))
        state.bounded_maps.add(map_hash)

    def end_match(self) -> None:
        if self.match_id is not None:
            db.end_match(self.conn, self.match_id)
            self._state = _MatchState()

    def _start_match(self, now: float, image: bytes | None) -> None:
        loaded = image is not None and is_map_loaded(image)
        map_hash = compute_dhash(image) if loaded else ""
        map_info = lookup_map(map_hash)
        if loaded:
            self._save_map_image(image, map_hash)
        self._state = _MatchState(
            db.start_match(self.conn, map_hash), now, map_hash, map_info,
            map_retry_at=None if loaded else now + CAPTURE_SETTINGS.map_retry_interval,
        )

    def _retry_map_image(self, now: float) -> None:
        state = self._state
        image = self.fetch_map_image()
        if image is None or not is_map_loaded(image):
            state.map_retry_at = now + CAPTURE_SETTINGS.map_retry_interval
            return
        state.map_hash = compute_dhash(image)
        state.map_info = lookup_map(state.map_hash)
        state.map_retry_at = None
        self._save_map_image(image, state.map_hash)
        db.set_map_hash(self.conn, state.match_id, state.map_hash)

    def _handle_invalid_match(self, now: float) -> None:
        state = self._state
        image = self.fetch_map_image()
        if image is not None:
            map_hash = compute_dhash(image)
            current = lookup_map(map_hash)
            if current.map_id == "no_map":
                self.end_match()
                return
            if state.map_hash and map_hash != state.map_hash and is_map_loaded(image):
                if (
                    state.map_info.battle_type in (BattleType.GROUND, BattleType.NAVAL)
                    and current.battle_type == BattleType.AIR
                    and state.map_info.location
                    and state.map_info.location == current.location
                ):
                    if not state.nuke_detected:
                        db.set_nuke(self.conn, state.match_id)
                        state.nuke_detected = True
                    state.invalid_since = None
                    return
                self.end_match()
                self._start_match(now, image)
                return

        if state.invalid_since is None:
            state.invalid_since = now
        elif now - state.invalid_since >= CAPTURE_SETTINGS.match_end_grace_period:
            self.end_match()

    def _capture_positions(self, now: float, indicators: dict, objects: list[dict]) -> None:
        state = self._state
        army = indicators.get("army")
        vehicle = indicators.get("type", "").split("/", 1)[-1]
        if army:
            self.army_type = army
        if vehicle:
            self.vehicle_type = vehicle
        is_air = army == CAPTURE_DEFAULTS.air_army_type

        low, high = CAPTURE_SETTINGS.valid_coord_min, CAPTURE_SETTINGS.valid_coord_max
        valid_objects = [
            obj for obj in objects if low < obj.get("x", -1) < high and low < obj.get("y", -1) < high
        ]
        capture_zones = [
            (obj["x"], obj["y"]) for obj in valid_objects if obj.get("type") == CAPTURE_FILTERS.capture_zone_type
        ]
        if capture_zones and not state.initial_capture_set:
            count = len(capture_zones)
            db.set_initial_capture(
                self.conn, state.match_id, count,
                sum(x for x, _ in capture_zones) / count,
                sum(y for _, y in capture_zones) / count,
            )
            state.initial_capture_set = True

        air_defence_seen = any(
            isinstance(icon := obj.get("icon"), str) and icon.lower() in CAPTURE_FILTERS.air_defence_icons
            for obj in valid_objects
        )
        if capture_zones:
            precision = CAPTURE_SETTINGS.signature_rounding
            signature = frozenset((round(x, precision), round(y, precision)) for x, y in capture_zones)
            # 基准占领点集合代表主图（陆/海）坐标；分批到达或暂时缺失时仍属主图。
            base = state.base_capture_signature
            if not base or signature <= base or base <= signature:
                state.base_capture_signature = base | signature
                air_view = False
            else:
                air_view = True
        elif not state.base_capture_signature and air_defence_seen:
            # 无占领点的纯空战图上，防空炮表明处于空中视角。
            air_view = True
        else:
            air_view = state.previous_air_view
        if is_air or air_view:
            self._maybe_capture_air_map()
        if air_view and not state.previous_air_view and state.transform is None and state.previous_objects:
            state.transform = fit_air_transform(state.previous_objects, objects)
            if state.transform is not None:
                db.set_air_transform(self.conn, state.match_id, state.transform)
        state.previous_objects = valid_objects
        state.previous_air_view = air_view

        positions = self._build_positions(valid_objects, air_view)
        tick = db.TickRecord(
            now - state.started_at, army or CAPTURE_DEFAULTS.army_type,
            vehicle or CAPTURE_DEFAULTS.vehicle_type, int(is_air), int(air_view),
        )
        db.add_tick(self.conn, state.match_id, tick, positions)

    def _build_positions(self, objects: list[dict], air_view: bool) -> list[db.PositionRecord]:
        state = self._state
        precision = CAPTURE_SETTINGS.signature_rounding
        positions = []
        for obj in objects:
            obj_type = obj.get("type", "unknown")
            is_poi = CAPTURE_FILTERS.is_poi(obj_type)
            x, y = obj["x"], obj["y"]
            # 出生点、机场等静态标记每个位置只存一次。
            if is_poi and obj_type != CAPTURE_FILTERS.capture_zone_type:
                key = (obj_type, round(x, precision), round(y, precision))
                if key in state.saved_pois:
                    continue
                state.saved_pois.add(key)
            x_ground, y_ground = to_ground(x, y, state.transform) if air_view and state.transform else (None, None)
            positions.append(db.PositionRecord(
                x, y, obj.get("color", "#FFFFFF"), obj_type, obj.get("icon", "unknown"), int(is_poi),
                x_ground, y_ground,
            ))
        return positions

    def _maybe_capture_air_map(self) -> None:
        state = self._state
        if state.air_map_hash or state.map_info.battle_type == BattleType.AIR:
            return
        image = self.fetch_map_image()
        if image is None or not is_map_loaded(image):
            return
        map_hash = compute_dhash(image)
        if map_hash == state.map_hash:
            return
        self._save_map_image(image, map_hash)
        db.set_air_map(self.conn, state.match_id, map_hash)
        state.air_map_hash = map_hash

    def _save_map_image(self, image: bytes, map_hash: str) -> None:
        self.maps_dir.mkdir(parents=True, exist_ok=True)
        path = self.maps_dir / f"{image_key(map_hash)}.png"
        if not path.exists():
            path.write_bytes(image)


def _is_nuke_message(msg: str) -> bool:
    """判断战报是否包含核武器相关消息（兼容游戏插入的零宽空格）。"""
    clean = msg.replace("\u200b", "").casefold()
    return "☢" in clean or "核武器" in clean or "nuclear" in clean
