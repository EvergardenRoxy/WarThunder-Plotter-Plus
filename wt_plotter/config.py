"""应用配置与默认值。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Mapping, Tuple

def _resolve_base_dir() -> Path:
    """定位运行数据目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _resolve_base_dir()
DATA_DIR = BASE_DIR / "data"


@dataclass(frozen=True)
class PathSettings:
    """应用文件路径。"""

    data_dir: Path = DATA_DIR
    maps_dir: Path = DATA_DIR / "maps"
    db_path: Path = DATA_DIR / "matches.db"
    missing_hash_log: Path = DATA_DIR / "missing_map_hashes.log"
    settings_path: Path = DATA_DIR / "settings.json"
    log_path: Path = DATA_DIR / "wt_plotter.log"


@dataclass(frozen=True)
class AppSettings:
    """网页服务默认值。"""

    host: str = "127.0.0.1"
    port: int = 5000
    datetime_format: str = "%Y-%m-%d %H:%M:%S"
    open_browser_on_start: bool = True


@dataclass(frozen=True)
class CaptureEndpoints:
    """游戏遥测接口。"""

    base_url: str = "http://127.0.0.1:8111"
    map_obj_path: str = "map_obj.json"
    map_img_path: str = "map.img"
    map_info_path: str = "map_info.json"
    indicators_path: str = "indicators"

    @property
    def map_obj_url(self) -> str:
        return f"{self.base_url}/{self.map_obj_path}"

    @property
    def map_img_url(self) -> str:
        return f"{self.base_url}/{self.map_img_path}"

    @property
    def map_info_url(self) -> str:
        return f"{self.base_url}/{self.map_info_path}"

    @property
    def indicators_url(self) -> str:
        return f"{self.base_url}/{self.indicators_path}"


@dataclass(frozen=True)
class CaptureDefaults:
    """采集默认值。"""

    army_type: str = "tank"
    vehicle_type: str = ""
    air_army_type: str = "air"


@dataclass(frozen=True)
class CaptureFilters:
    """地图对象过滤规则。"""

    air_defence_icons: Tuple[str, ...] = ("airdefence", "air_defence")
    excluded_icons: Tuple[str, ...] = ("player", "airdefence", "air_defence")
    excluded_types: Tuple[str, ...] = (
        "aircraft",
        "airfield",
        "respawn_base_fighter",
    )
    capture_zone_type: str = "capture_zone"
    poi_types: Tuple[str, ...] = (
        "capture_zone",
        "respawn_base_tank",
        "respawn_base_fighter",
        "airfield",
    )


@dataclass(frozen=True)
class CaptureSettings:
    """采集间隔与阈值。"""

    poll_interval: float = 0.2
    match_end_grace_period: float = 20.0
    signature_rounding: int = 4
    valid_coord_min: float = 0.0
    valid_coord_max: float = 1.0


@dataclass(frozen=True)
class CaptureTimeouts:
    """网络请求与线程等待超时。"""

    session: float = 2.0
    map_info: float = 2.0
    map_image: float = 3.0
    current_map_image: float = 1.0
    async_map_info: float = 1.0
    async_indicators: float = 1.0
    async_map_obj: float = 1.0
    thread_join: float = 3.0


@dataclass(frozen=True)
class TransformSettings:
    """空中坐标拟合阈值。"""

    min_points: int = 3
    scale_max: float = 0.5
    error_max: float = 0.01


@dataclass(frozen=True)
class HashSettings:
    """地图哈希查找设置。"""

    tolerance: int = 42


@dataclass(frozen=True)
class DbSettings:
    """数据库设置与精度。"""

    pragmas: Mapping[str, str] = field(
        default_factory=lambda: {
            "foreign_keys": "ON",
            "journal_mode": "WAL",
            "synchronous": "NORMAL",
            "temp_store": "MEMORY",
            "auto_vacuum": "INCREMENTAL",
            "busy_timeout": "5000",
        }
    )
    position_precision: int = 5
    capture_precision: int = 6


PATHS = PathSettings()
APP_SETTINGS = AppSettings()
CAPTURE_ENDPOINTS = CaptureEndpoints()
CAPTURE_DEFAULTS = CaptureDefaults()
CAPTURE_FILTERS = CaptureFilters()
CAPTURE_SETTINGS = CaptureSettings()
CAPTURE_TIMEOUTS = CaptureTimeouts()
TRANSFORM_SETTINGS = TransformSettings()
HASH_SETTINGS = HashSettings()
DB_SETTINGS = DbSettings()
