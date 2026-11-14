from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from sqlite3 import Connection

from wt_plotter.capture.air_transform import fit_air_transform, to_ground
from wt_plotter.config import CAPTURE_DEFAULTS, CAPTURE_FILTERS, CAPTURE_SETTINGS
from wt_plotter.maps.dhash import compute_dhash
from wt_plotter.maps.lookup import lookup_map
from wt_plotter.maps.table import BattleType, MapInfo, UNKNOWN_MAP
from wt_plotter.storage import db


@dataclass
class _MatchState:
    match_id: int | None = None
    started_at: float = 0.0
    map_hash: str = ""
    map_info: MapInfo = UNKNOWN_MAP
    air_map_hash: str = ""
    invalid_since: float | None = None
    nuke_detected: bool = False
    poi_captured: bool = False
    initial_capture_set: bool = False
    capture_signature: tuple[tuple[float, float], ...] | None = None
    previous_objects: list[dict] = field(default_factory=list)
    previous_air_view: bool = False
    transform: tuple[float, float, float, float] | None = None


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
            image = self.fetch_map_image()
            map_hash = compute_dhash(image) if image is not None else ""
            self._start_match(now, image, map_hash, lookup_map(map_hash))
        self._state.invalid_since = None
        if objects:
            self._capture_positions(now, indicators or {}, objects)

    def end_match(self) -> None:
        if self.match_id is not None:
            db.end_match(self.conn, self.match_id)
            self._state = _MatchState()

    def _start_match(self, now: float, image: bytes | None, map_hash: str, map_info: MapInfo) -> None:
        if image is not None:
            self._save_map_image(image, map_hash, map_info)
        self._state = _MatchState(db.start_match(self.conn, map_hash), now, map_hash, map_info)

    def _handle_invalid_match(self, now: float) -> None:
        state = self._state
        image = self.fetch_map_image()
        if image is not None:
            map_hash = compute_dhash(image)
            current = lookup_map(map_hash)
            if current.map_id == "no_map":
                self.end_match()
                return
            if map_hash != state.map_hash:
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
                self._start_match(now, image, map_hash, current)
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
        if is_air:
            self._maybe_capture_air_map()

        low, high = CAPTURE_SETTINGS.valid_coord_min, CAPTURE_SETTINGS.valid_coord_max
        valid_objects = [
            obj for obj in objects if low < obj.get("x", -1) < high and low < obj.get("y", -1) < high
        ]
        capture_zones = [
            (obj["x"], obj["y"]) for obj in valid_objects if obj.get("type") == CAPTURE_FILTERS.capture_zone_type
        ]
        precision = CAPTURE_SETTINGS.signature_rounding
        signature = tuple(sorted((round(x, precision), round(y, precision)) for x, y in capture_zones))
        poi_changed = state.capture_signature is not None and signature != state.capture_signature
        state.capture_signature = signature
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
        air_view = is_air or poi_changed or air_defence_seen
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
        if any(position.is_poi for position in positions):
            state.poi_captured = True

    def _build_positions(self, objects: list[dict], air_view: bool) -> list[db.PositionRecord]:
        state = self._state
        positions = []
        for obj in objects:
            obj_type = obj.get("type", "unknown")
            is_poi = obj_type in CAPTURE_FILTERS.poi_types
            if is_poi and obj_type != CAPTURE_FILTERS.capture_zone_type and state.poi_captured:
                continue
            x, y = obj["x"], obj["y"]
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
        if image is None:
            return
        map_hash = compute_dhash(image)
        if map_hash == state.map_hash:
            return
        self._save_map_image(image, map_hash, lookup_map(map_hash))
        db.set_air_map(self.conn, state.match_id, map_hash)
        state.air_map_hash = map_hash

    def _save_map_image(self, image: bytes, map_hash: str, map_info: MapInfo) -> None:
        key = map_hash if map_info.map_id in ("unknown", "no_map") else map_info.map_id
        self.maps_dir.mkdir(parents=True, exist_ok=True)
        path = self.maps_dir / f"{key}.png"
        if not path.exists():
            path.write_bytes(image)
