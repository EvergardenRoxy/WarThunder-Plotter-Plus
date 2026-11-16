from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3

from wt_plotter.config import DB_SETTINGS


UNTRANSLATED_DISCONNECT = "NET_PLAYER_DISCONNECT_FROM_GAME"


class _Connection(sqlite3.Connection):
    enum_ids: dict[tuple[str, str], int]


@dataclass
class Match:
    id: int
    started_at: str
    ended_at: str | None
    map_hash: str | None
    air_map_hash: str | None
    initial_capture_count: int | None
    initial_capture_x: float | None
    initial_capture_y: float | None
    nuke_detected: int
    air_transform_a: float | None
    air_transform_b: float | None
    air_transform_c: float | None
    air_transform_d: float | None


@dataclass
class TickRecord:
    timestamp: float
    army_type: str
    vehicle_type: str
    is_player_air: int
    is_player_air_view: int


@dataclass
class EventRecord:
    timestamp: float
    game_id: int
    msg: str
    raw: str


@dataclass
class PositionRecord:
    x: float
    y: float
    color: str
    obj_type: str
    icon: str
    is_poi: int
    x_ground: float | None = None
    y_ground: float | None = None


def connect(db_path: Path) -> _Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, factory=_Connection)
    conn.row_factory = sqlite3.Row
    conn.enum_ids = {}
    # 空库先设置回收模式，再启用 WAL。
    conn.execute(f"PRAGMA auto_vacuum = {DB_SETTINGS.pragmas['auto_vacuum']}")
    for key, value in DB_SETTINGS.pragmas.items():
        if key != "auto_vacuum":
            conn.execute(f"PRAGMA {key} = {value}")
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    """创建数据库表。"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            map_hash TEXT,
            air_map_hash TEXT,
            initial_capture_count INTEGER,
            initial_capture_x REAL,
            initial_capture_y REAL,
            nuke_detected INTEGER NOT NULL DEFAULT 0,
            air_transform_a REAL,
            air_transform_b REAL,
            air_transform_c REAL,
            air_transform_d REAL
        );

        CREATE TABLE IF NOT EXISTS enum_colors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            value TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS enum_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            value TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS enum_icons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            value TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS enum_army_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            value TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS enum_vehicle_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            value TEXT NOT NULL UNIQUE
        );
\x20\x20\x20\x20\x20\x20\x20\x20
        CREATE TABLE IF NOT EXISTS ticks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            timestamp_ms INTEGER NOT NULL,
            army_type_id INTEGER NOT NULL,
            vehicle_type_id INTEGER NOT NULL,
            is_player_air INTEGER NOT NULL DEFAULT 0,
            is_player_air_view INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (match_id) REFERENCES matches(id),
            FOREIGN KEY (army_type_id) REFERENCES enum_army_types(id),
            FOREIGN KEY (vehicle_type_id) REFERENCES enum_vehicle_types(id)
        );

        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            tick_id INTEGER NOT NULL,
            x REAL NOT NULL,
            y REAL NOT NULL,
            color_id INTEGER NOT NULL,
            type_id INTEGER NOT NULL,
            icon_id INTEGER NOT NULL,
            is_poi INTEGER NOT NULL DEFAULT 0,
            x_ground REAL,
            y_ground REAL,
            FOREIGN KEY (match_id) REFERENCES matches(id),
            FOREIGN KEY (tick_id) REFERENCES ticks(id),
            FOREIGN KEY (color_id) REFERENCES enum_colors(id),
            FOREIGN KEY (type_id) REFERENCES enum_types(id),
            FOREIGN KEY (icon_id) REFERENCES enum_icons(id)
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            timestamp_ms INTEGER NOT NULL,
            game_id INTEGER NOT NULL,
            msg TEXT NOT NULL,
            raw TEXT NOT NULL,
            FOREIGN KEY (match_id) REFERENCES matches(id)
        );

        CREATE INDEX IF NOT EXISTS idx_events_match_ts ON events(match_id, timestamp_ms);
        CREATE INDEX IF NOT EXISTS idx_positions_match ON positions(match_id);
        CREATE INDEX IF NOT EXISTS idx_positions_tick ON positions(tick_id);
        CREATE INDEX IF NOT EXISTS idx_ticks_match_ts ON ticks(match_id, timestamp_ms);
    """)
    conn.commit()


def start_match(conn: sqlite3.Connection, map_hash: str) -> int:
    with conn:
        cursor = conn.execute(
            "INSERT INTO matches (started_at, map_hash) VALUES (?, ?)",
            (datetime.now().isoformat(), map_hash),
        )
    return cursor.lastrowid


def end_match(conn: sqlite3.Connection, match_id: int) -> None:
    with conn:
        conn.execute(
            "UPDATE matches SET ended_at = ? WHERE id = ?",
            (datetime.now().isoformat(), match_id),
        )


def set_air_map(conn: sqlite3.Connection, match_id: int, air_map_hash: str) -> None:
    with conn:
        conn.execute("UPDATE matches SET air_map_hash = ? WHERE id = ?", (air_map_hash, match_id))


def set_nuke(conn: sqlite3.Connection, match_id: int) -> None:
    with conn:
        conn.execute("UPDATE matches SET nuke_detected = 1 WHERE id = ?", (match_id,))


def set_initial_capture(conn: sqlite3.Connection, match_id: int, count: int, x: float, y: float) -> None:
    precision = DB_SETTINGS.capture_precision
    with conn:
        conn.execute(
            "UPDATE matches SET initial_capture_count = ?, initial_capture_x = ?, initial_capture_y = ? WHERE id = ?",
            (count, round(x, precision), round(y, precision), match_id),
        )


def set_air_transform(
    conn: sqlite3.Connection, match_id: int, transform: tuple[float, float, float, float]
) -> None:
    with conn:
        conn.execute(
            """
            UPDATE matches
            SET air_transform_a = ?, air_transform_b = ?, air_transform_c = ?, air_transform_d = ?
            WHERE id = ?
            """,
            (*transform, match_id),
        )


def _enum_id(
    conn: _Connection, pending: dict[tuple[str, str], int], table: str, value: str
) -> int:
    key = (table, value)
    if key in conn.enum_ids:
        return conn.enum_ids[key]
    if key not in pending:
        conn.execute(f"INSERT OR IGNORE INTO {table} (value) VALUES (?)", (value,))
        pending[key] = conn.execute(f"SELECT id FROM {table} WHERE value = ?", (value,)).fetchone()["id"]
    return pending[key]


def _quantize(value: float | None) -> float | None:
    return None if value is None else round(value, DB_SETTINGS.position_precision)


def add_tick(conn: _Connection, match_id: int, tick: TickRecord, positions: list[PositionRecord]) -> None:
    if not positions:
        return

    pending: dict[tuple[str, str], int] = {}
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO ticks (match_id, timestamp_ms, army_type_id, vehicle_type_id, is_player_air, is_player_air_view)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                round(tick.timestamp * 1000),
                _enum_id(conn, pending, "enum_army_types", tick.army_type),
                _enum_id(conn, pending, "enum_vehicle_types", tick.vehicle_type),
                tick.is_player_air,
                tick.is_player_air_view,
            ),
        )
        conn.executemany(
            """
            INSERT INTO positions (match_id, tick_id, x, y, color_id, type_id, icon_id, is_poi, x_ground, y_ground)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    match_id,
                    cursor.lastrowid,
                    _quantize(position.x),
                    _quantize(position.y),
                    _enum_id(conn, pending, "enum_colors", position.color),
                    _enum_id(conn, pending, "enum_types", position.obj_type),
                    _enum_id(conn, pending, "enum_icons", position.icon),
                    position.is_poi,
                    _quantize(position.x_ground),
                    _quantize(position.y_ground),
                )
                for position in positions
            ),
        )
    conn.enum_ids.update(pending)


def add_events(conn: sqlite3.Connection, match_id: int, events: list[EventRecord]) -> None:
    with conn:
        conn.executemany(
            "INSERT INTO events (match_id, timestamp_ms, game_id, msg, raw) VALUES (?, ?, ?, ?, ?)",
            ((match_id, round(e.timestamp * 1000), e.game_id, e.msg, e.raw) for e in events),
        )


def get_events(conn: sqlite3.Connection, match_id: int, since_ms: int) -> list[dict]:
    # 掉线时游戏会多发一条没翻译的原始行（"<昵称>td! kd?NET_PLAYER_DISCONNECT_FROM_GAME"），不返回。
    rows = conn.execute(
        "SELECT timestamp_ms, msg FROM events WHERE match_id = ? AND timestamp_ms >= ? AND msg NOT LIKE ? "
        "ORDER BY timestamp_ms, id",
        (match_id, since_ms, f"%{UNTRANSLATED_DISCONNECT}"),
    )
    return [{"timestamp": row["timestamp_ms"], "msg": row["msg"]} for row in rows]


def get_active_match(conn: sqlite3.Connection) -> Match | None:
    row = conn.execute("SELECT * FROM matches WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
    return Match(**dict(row)) if row is not None else None


def get_match(conn: sqlite3.Connection, match_id: int) -> Match | None:
    row = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    return Match(**dict(row)) if row is not None else None


def get_all_matches(conn: sqlite3.Connection) -> list[Match]:
    rows = conn.execute("SELECT * FROM matches ORDER BY started_at DESC")
    return [Match(**dict(row)) for row in rows]


def get_positions_bundle(conn: sqlite3.Connection, match_id: int, since_ms: int) -> dict:
    rows = conn.execute(
        """
        SELECT
            p.id, p.tick_id, p.x, p.y, c.value AS color, t.value AS type, i.value AS icon,
            p.is_poi, p.x_ground, p.y_ground,
            tk.timestamp_ms AS timestamp, at.value AS army_type, vt.value AS vehicle_type,
            tk.is_player_air, tk.is_player_air_view
        FROM positions p
        JOIN ticks tk ON tk.id = p.tick_id
        LEFT JOIN enum_colors c ON c.id = p.color_id
        LEFT JOIN enum_types t ON t.id = p.type_id
        LEFT JOIN enum_icons i ON i.id = p.icon_id
        LEFT JOIN enum_army_types at ON at.id = tk.army_type_id
        LEFT JOIN enum_vehicle_types vt ON vt.id = tk.vehicle_type_id
        WHERE p.match_id = ? AND tk.timestamp_ms >= ?
        ORDER BY tk.timestamp_ms, p.id
        """,
        (match_id, since_ms),
    )
    position_fields = ("id", "tick_id", "x", "y", "color", "type", "icon", "is_poi", "x_ground", "y_ground")
    tick_fields = ("timestamp", "army_type", "vehicle_type", "is_player_air", "is_player_air_view")
    positions = []
    ticks = {}
    for row in rows:
        tick_id = row["tick_id"]
        if tick_id not in ticks:
            ticks[tick_id] = {"id": tick_id, **{field: row[field] for field in tick_fields}}
        positions.append({field: row[field] for field in position_fields})
    return {"positions": positions, "ticks": list(ticks.values())}


def first_sortie_army(conn: sqlite3.Connection, match_id: int, placeholders: tuple[str, ...]) -> str | None:
    """返回本场第一次出击（跳过占位载具）的兵种。"""
    marks = ", ".join("?" * len(placeholders))
    row = conn.execute(
        f"""
        SELECT at.value AS army_type
        FROM ticks tk
        JOIN enum_army_types at ON at.id = tk.army_type_id
        JOIN enum_vehicle_types vt ON vt.id = tk.vehicle_type_id
        WHERE tk.match_id = ? AND vt.value NOT IN ({marks})
        ORDER BY tk.timestamp_ms, tk.id
        LIMIT 1
        """,
        (match_id, *placeholders),
    ).fetchone()
    return row["army_type"] if row is not None else None


def count_positions(conn: sqlite3.Connection, match_id: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM positions WHERE match_id = ?", (match_id,)).fetchone()[0]


def get_latest_tick(conn: sqlite3.Connection, match_id: int) -> TickRecord | None:
    row = conn.execute(
        """
        SELECT tk.timestamp_ms AS timestamp, at.value AS army_type, vt.value AS vehicle_type,
               tk.is_player_air, tk.is_player_air_view
        FROM ticks tk
        LEFT JOIN enum_army_types at ON at.id = tk.army_type_id
        LEFT JOIN enum_vehicle_types vt ON vt.id = tk.vehicle_type_id
        WHERE tk.match_id = ?
        ORDER BY tk.timestamp_ms DESC, tk.id DESC
        LIMIT 1
        """,
        (match_id,),
    ).fetchone()
    return TickRecord(**dict(row)) if row is not None else None


def delete_match(conn: sqlite3.Connection, match_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM events WHERE match_id = ?", (match_id,))
        conn.execute("DELETE FROM positions WHERE match_id = ?", (match_id,))
        conn.execute("DELETE FROM ticks WHERE match_id = ?", (match_id,))
        conn.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    # execute 只走一步，回收不完整；executescript 会执行到结束。
    conn.executescript("PRAGMA incremental_vacuum;")


def close_orphaned_matches(conn: sqlite3.Connection) -> int:
    with conn:
        # 与 started_at 一样用本地时间。
        cursor = conn.execute(
            "UPDATE matches SET ended_at = ? WHERE ended_at IS NULL", (datetime.now().isoformat(),)
        )
    return cursor.rowcount
