from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import sqlite3

from wt_plotter.config import DB_SETTINGS


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
class ReplayRecord:
    session_id: str
    is_server: int
    level: str
    mission: str
    battle_class: str
    started_at: str
    duration: float
    status: str | None
    author: str | None
    author_user_id: str | None
    wrote_tracks: int
    source: str
    parser_version: int
    # 完整解析失败的原因（解析成功或只做了轻量导入时为 None）。
    parse_error: str | None = None


@dataclass
class ReplayPlayer:
    user_id: str
    name: str
    clan_tag: str
    team: int
    squad_id: int
    country: str | None
    vehicles: str
    kills: int
    ground_kills: int
    naval_kills: int
    ai_kills: int
    ai_ground_kills: int
    ai_naval_kills: int
    team_kills: int
    assists: int
    deaths: int
    capture_zone: int
    damage_zone: int
    score: int


@dataclass
class ReplayKill:
    timestamp: float
    killer: str | None
    killer_vehicle: str
    victim: str | None
    victim_vehicle: str | None


@dataclass
class ReplayChat:
    timestamp: float
    sender: str
    text: str


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
    # 录像还原的单位：玩家名与载具（AI 或不知道时为 None）。
    unit_name: str | None = None
    unit_vehicle: str | None = None


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

        CREATE TABLE IF NOT EXISTS enum_unit_names (
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
            unit_name_id INTEGER,
            unit_vehicle_id INTEGER,
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

        CREATE TABLE IF NOT EXISTS map_bounds (
            map_key TEXT PRIMARY KEY,
            min_x REAL NOT NULL,
            min_z REAL NOT NULL,
            max_x REAL NOT NULL,
            max_z REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS replays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            is_server INTEGER NOT NULL,
            level TEXT NOT NULL,
            mission TEXT NOT NULL,
            battle_class TEXT NOT NULL,
            started_at TEXT NOT NULL,
            duration REAL NOT NULL,
            status TEXT,
            author TEXT,
            author_user_id TEXT,
            wrote_tracks INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL,
            parser_version INTEGER NOT NULL DEFAULT 0,
            parse_error TEXT,
            UNIQUE (session_id, is_server),
            FOREIGN KEY (match_id) REFERENCES matches(id)
        );

        CREATE TABLE IF NOT EXISTS replay_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            replay_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            clan_tag TEXT NOT NULL,
            team INTEGER NOT NULL,
            squad_id INTEGER NOT NULL,
            country TEXT,
            vehicles TEXT NOT NULL,
            kills INTEGER NOT NULL,
            ground_kills INTEGER NOT NULL,
            naval_kills INTEGER NOT NULL,
            ai_kills INTEGER NOT NULL,
            ai_ground_kills INTEGER NOT NULL,
            ai_naval_kills INTEGER NOT NULL,
            team_kills INTEGER NOT NULL,
            assists INTEGER NOT NULL,
            deaths INTEGER NOT NULL,
            capture_zone INTEGER NOT NULL,
            damage_zone INTEGER NOT NULL,
            score INTEGER NOT NULL,
            FOREIGN KEY (replay_id) REFERENCES replays(id)
        );

        CREATE TABLE IF NOT EXISTS replay_kills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            replay_id INTEGER NOT NULL,
            timestamp_ms INTEGER NOT NULL,
            killer TEXT,
            killer_vehicle TEXT NOT NULL,
            victim TEXT,
            victim_vehicle TEXT,
            FOREIGN KEY (replay_id) REFERENCES replays(id)
        );

        CREATE TABLE IF NOT EXISTS replay_chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            replay_id INTEGER NOT NULL,
            timestamp_ms INTEGER NOT NULL,
            sender TEXT NOT NULL,
            text TEXT NOT NULL,
            FOREIGN KEY (replay_id) REFERENCES replays(id)
        );

        CREATE INDEX IF NOT EXISTS idx_events_match_ts ON events(match_id, timestamp_ms);
        CREATE INDEX IF NOT EXISTS idx_replays_match ON replays(match_id);
        CREATE INDEX IF NOT EXISTS idx_positions_match ON positions(match_id);
        -- 首页按 tick 查自机图标、按类型查海战出生点；(tick_id, icon_id) 取代早期只有 tick_id 的索引。
        DROP INDEX IF EXISTS idx_positions_tick;
        CREATE INDEX IF NOT EXISTS idx_positions_tick_icon ON positions(tick_id, icon_id);
        CREATE INDEX IF NOT EXISTS idx_positions_type ON positions(type_id);
        CREATE INDEX IF NOT EXISTS idx_ticks_match_ts ON ticks(match_id, timestamp_ms);
    """)
    # 早期建的表缺少后加的列。
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(replays)")}
    if "parser_version" not in columns:
        conn.execute("ALTER TABLE replays ADD COLUMN parser_version INTEGER NOT NULL DEFAULT 0")
    if "parse_error" not in columns:
        conn.execute("ALTER TABLE replays ADD COLUMN parse_error TEXT")
    # 早期导入把结果块里的空位也存成了玩家。
    conn.execute("DELETE FROM replay_players WHERE user_id = '-1'")
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(positions)")}
    if "unit_name_id" not in columns:
        conn.execute("ALTER TABLE positions ADD COLUMN unit_name_id INTEGER")
        conn.execute("ALTER TABLE positions ADD COLUMN unit_vehicle_id INTEGER")
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


def set_map_hash(conn: sqlite3.Connection, match_id: int, map_hash: str) -> None:
    with conn:
        conn.execute("UPDATE matches SET map_hash = ? WHERE id = ?", (map_hash, match_id))


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
            INSERT INTO positions (
                match_id, tick_id, x, y, color_id, type_id, icon_id, is_poi, x_ground, y_ground,
                unit_name_id, unit_vehicle_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    None if position.unit_name is None else _enum_id(conn, pending, "enum_unit_names", position.unit_name),
                    None if position.unit_vehicle is None
                    else _enum_id(conn, pending, "enum_vehicle_types", position.unit_vehicle),
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
    rows = conn.execute(
        "SELECT timestamp_ms, msg FROM events WHERE match_id = ? AND timestamp_ms >= ? ORDER BY timestamp_ms, id",
        (match_id, since_ms),
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


POSITION_FIELDS = (
    "tick_id", "x", "y", "color", "type", "icon", "is_poi", "x_ground", "y_ground", "unit_name", "unit_vehicle",
)
_TICK_FIELDS = ("id", "timestamp", "army_type", "vehicle_type", "is_player_air", "is_player_air_view")


def get_positions_bundle(conn: sqlite3.Connection, match_id: int, since_ms: int) -> dict:
    """位置用列名 + 行数组返回：长比赛有几十万条，逐条字典的生成和 JSON 体积都太大。"""
    # 先取 tick，位置只取到最后一个 tick 为止：两次查询之间采集器写入的新 tick 留给下一轮。
    ticks = [dict(zip(_TICK_FIELDS, tick)) for tick in conn.execute(
        """
        SELECT tk.id, tk.timestamp_ms, at.value, vt.value, tk.is_player_air, tk.is_player_air_view
        FROM ticks tk
        LEFT JOIN enum_army_types at ON at.id = tk.army_type_id
        LEFT JOIN enum_vehicle_types vt ON vt.id = tk.vehicle_type_id
        WHERE tk.match_id = ? AND tk.timestamp_ms >= ?
        ORDER BY tk.timestamp_ms, tk.id
        """,
        (match_id, since_ms),
    )]
    rows = conn.execute(
        """
        SELECT
            p.tick_id, p.x, p.y, c.value, t.value, i.value,
            p.is_poi, p.x_ground, p.y_ground, un.value, uv.value
        FROM positions p
        JOIN ticks tk ON tk.id = p.tick_id
        LEFT JOIN enum_colors c ON c.id = p.color_id
        LEFT JOIN enum_types t ON t.id = p.type_id
        LEFT JOIN enum_icons i ON i.id = p.icon_id
        LEFT JOIN enum_unit_names un ON un.id = p.unit_name_id
        LEFT JOIN enum_vehicle_types uv ON uv.id = p.unit_vehicle_id
        WHERE p.match_id = ? AND tk.timestamp_ms >= ? AND p.tick_id <= ?
        ORDER BY tk.timestamp_ms, p.id
        """,
        (match_id, since_ms, max((tick["id"] for tick in ticks), default=0)),
    )
    return {"ticks": ticks, "fields": POSITION_FIELDS, "rows": [tuple(row) for row in rows]}


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


def get_match_vehicles(conn: sqlite3.Connection, placeholders: tuple[str, ...]) -> dict[int, list[str]]:
    """按首次实际出场顺序返回每场比赛的出击载具（要求该 tick 有 Player 位置，跳过选车界面点击）。"""
    marks = ", ".join("?" * len(placeholders))
    rows = conn.execute(
        f"""
        SELECT tk.match_id, vt.value AS vehicle_type
        FROM ticks tk
        JOIN enum_vehicle_types vt ON vt.id = tk.vehicle_type_id
        WHERE vt.value != '' AND vt.value NOT IN ({marks})
          AND EXISTS (
              SELECT 1 FROM positions p
              WHERE p.tick_id = tk.id AND p.icon_id IN (SELECT id FROM enum_icons WHERE value = 'Player')
          )
        GROUP BY tk.match_id, vt.value
        ORDER BY tk.match_id, MIN(tk.timestamp_ms), MIN(tk.id)
        """,
        placeholders,
    )
    vehicles: dict[int, list[str]] = {}
    for row in rows:
        vehicles.setdefault(row["match_id"], []).append(row["vehicle_type"])
    return vehicles


def has_air_view(conn: sqlite3.Connection, match_id: int) -> bool:
    """检查比赛是否包含空中视角 tick。"""
    row = conn.execute(
        "SELECT 1 FROM ticks WHERE match_id = ? AND is_player_air_view = 1 LIMIT 1",
        (match_id,),
    ).fetchone()
    return row is not None


def get_naval_spawn_match_ids(conn: sqlite3.Connection, spawn_types: tuple[str, ...]) -> set[int]:
    """有海战出生点的比赛，用于未知地图的战局类型兜底。"""
    marks = ", ".join("?" * len(spawn_types))
    rows = conn.execute(
        f"SELECT DISTINCT match_id FROM positions WHERE type_id IN (SELECT id FROM enum_types WHERE value IN ({marks}))",
        spawn_types,
    )
    return {row["match_id"] for row in rows}


def get_position_counts(conn: sqlite3.Connection) -> dict[int, int]:
    rows = conn.execute("SELECT match_id, COUNT(*) AS count FROM positions GROUP BY match_id")
    return {row["match_id"]: row["count"] for row in rows}


_NUKE_EVENT_SQL = "msg LIKE '%☢%' OR msg LIKE '%核%武%器%' OR LOWER(msg) LIKE '%nuclear%'"


def get_nuke_event_match_ids(conn: sqlite3.Connection) -> set[int]:
    """返回播报中出现过核武器消息的比赛 ID 集合。"""
    rows = conn.execute(f"SELECT DISTINCT match_id FROM events WHERE {_NUKE_EVENT_SQL}")
    return {row["match_id"] for row in rows}


def has_nuke_event(conn: sqlite3.Connection, match_id: int) -> bool:
    """检查单场比赛播报中是否出现核武器消息。"""
    row = conn.execute(
        f"SELECT 1 FROM events WHERE match_id = ? AND ({_NUKE_EVENT_SQL}) LIMIT 1",
        (match_id,),
    ).fetchone()
    return row is not None


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


def _delete_replay_rows(conn: sqlite3.Connection, where: str, params: tuple) -> None:
    ids = f"SELECT id FROM replays WHERE {where}"
    for table in ("replay_players", "replay_kills", "replay_chat"):
        conn.execute(f"DELETE FROM {table} WHERE replay_id IN ({ids})", params)
    conn.execute(f"DELETE FROM replays WHERE {where}", params)


def delete_match(conn: sqlite3.Connection, match_id: int) -> None:
    with conn:
        _delete_replay_rows(conn, "match_id = ?", (match_id,))
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


def create_finished_match(conn: sqlite3.Connection, started_at: str, ended_at: str, map_hash: str | None) -> int:
    """为没有 8111 记录的录像建一场已结束的比赛。"""
    with conn:
        cursor = conn.execute(
            "INSERT INTO matches (started_at, ended_at, map_hash) VALUES (?, ?, ?)",
            (started_at, ended_at, map_hash),
        )
    return cursor.lastrowid


def extend_match_end(conn: sqlite3.Connection, match_id: int, ended_at: str) -> None:
    """录像比本地记录更长时（服务器录像含完整战局），把结束时间推后。"""
    with conn:
        conn.execute("UPDATE matches SET ended_at = MAX(ended_at, ?) WHERE id = ?", (ended_at, match_id))


def find_match_near(conn: sqlite3.Connection, started_at: str, tolerance_s: float, session_id: str) -> int | None:
    """找开始时间最接近且在容差内的已结束比赛，跳过已关联其它场次录像的比赛。"""
    row = conn.execute(
        """
        SELECT id FROM matches
        WHERE ended_at IS NOT NULL
          AND ABS(julianday(started_at) - julianday(?)) * 86400 <= ?
          AND id NOT IN (SELECT match_id FROM replays WHERE session_id != ?)
        ORDER BY ABS(julianday(started_at) - julianday(?))
        LIMIT 1
        """,
        (started_at, tolerance_s, session_id, started_at),
    ).fetchone()
    return row["id"] if row is not None else None


def save_map_bounds(conn: sqlite3.Connection, map_key: str, bounds: tuple[float, float, float, float]) -> None:
    """记录地图图片对应的世界坐标范围 (min_x, min_z, max_x, max_z)；与图片一样，以第一次为准。"""
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO map_bounds (map_key, min_x, min_z, max_x, max_z) VALUES (?, ?, ?, ?, ?)",
            (map_key, *bounds),
        )


def get_map_bounds(conn: sqlite3.Connection, map_key: str) -> tuple[float, float, float, float] | None:
    row = conn.execute(
        "SELECT min_x, min_z, max_x, max_z FROM map_bounds WHERE map_key = ?", (map_key,)
    ).fetchone()
    return tuple(row) if row is not None else None


def find_session_author(conn: sqlite3.Connection, session_id: str) -> str | None:
    """同一场的本地录像记录了是谁录的。"""
    row = conn.execute(
        "SELECT author_user_id FROM replays WHERE session_id = ? AND author_user_id IS NOT NULL LIMIT 1",
        (session_id,),
    ).fetchone()
    return row["author_user_id"] if row is not None else None


def tracks_writer(conn: sqlite3.Connection, match_id: int) -> int | None:
    """本场轨迹由哪类录像写入：1 服务器录像，0 本地录像，None 不是录像写的。"""
    row = conn.execute(
        "SELECT MAX(is_server) AS is_server FROM replays WHERE match_id = ? AND wrote_tracks = 1", (match_id,)
    ).fetchone()
    return row["is_server"]


def clear_match_data(conn: sqlite3.Connection, match_id: int) -> None:
    """删掉比赛的 tick、位置和播报（录像重新写入轨迹前调用）。"""
    with conn:
        conn.execute("DELETE FROM events WHERE match_id = ?", (match_id,))
        conn.execute("DELETE FROM positions WHERE match_id = ?", (match_id,))
        conn.execute("DELETE FROM ticks WHERE match_id = ?", (match_id,))


def replay_parser_version(conn: sqlite3.Connection, session_id: str, is_server: bool) -> int | None:
    """已导入录像的解析版本；没导入过返回 None。"""
    row = conn.execute(
        "SELECT parser_version FROM replays WHERE session_id = ? AND is_server = ?", (session_id, int(is_server))
    ).fetchone()
    return None if row is None else row["parser_version"]


def replays_to_parse(conn: sqlite3.Connection, match_id: int, parser_version: int) -> list[str]:
    """这场比赛里解析版本低于 parser_version 的录像来源，本地录像在前。"""
    rows = conn.execute(
        "SELECT source FROM replays WHERE match_id = ? AND parser_version < ? ORDER BY is_server",
        (match_id, parser_version),
    ).fetchall()
    return [row["source"] for row in rows]


def mark_replay_failed(conn: sqlite3.Connection, source: str, parser_version: int, error: str) -> None:
    """记下完整解析失败：同一解析版本不再重试。"""
    with conn:
        conn.execute(
            "UPDATE replays SET parser_version = ?, parse_error = ? WHERE source = ?", (parser_version, error, source)
        )


def find_replay_match(conn: sqlite3.Connection, session_id: str) -> int | None:
    row = conn.execute("SELECT match_id FROM replays WHERE session_id = ? LIMIT 1", (session_id,)).fetchone()
    return row["match_id"] if row is not None else None


def save_replay(
    conn: sqlite3.Connection, match_id: int, replay: ReplayRecord,
    players: list[ReplayPlayer], kills: list[ReplayKill], chat: list[ReplayChat],
) -> int:
    """保存录像；同一场同类型的录像重新导入时整体替换。"""
    with conn:
        _delete_replay_rows(conn, "session_id = ? AND is_server = ?", (replay.session_id, replay.is_server))
        fields = list(asdict(replay))
        cursor = conn.execute(
            f"INSERT INTO replays (match_id, {', '.join(fields)}) VALUES ({', '.join('?' * (len(fields) + 1))})",
            (match_id, *asdict(replay).values()),
        )
        replay_id = cursor.lastrowid
        _insert_rows(conn, "replay_players", replay_id, [asdict(player) for player in players])
        _insert_rows(conn, "replay_kills", replay_id, [_with_ms(asdict(kill)) for kill in kills])
        _insert_rows(conn, "replay_chat", replay_id, [_with_ms(asdict(line)) for line in chat])
    return replay_id


def _with_ms(row: dict) -> dict:
    row["timestamp_ms"] = round(row.pop("timestamp") * 1000)
    return row


def _insert_rows(conn: sqlite3.Connection, table: str, replay_id: int, rows: list[dict]) -> None:
    if not rows:
        return
    fields = list(rows[0])
    conn.executemany(
        f"INSERT INTO {table} (replay_id, {', '.join(fields)}) VALUES ({', '.join('?' * (len(fields) + 1))})",
        ((replay_id, *row.values()) for row in rows),
    )


def get_replay_report(conn: sqlite3.Connection, match_id: int) -> dict | None:
    """本场录像战报；服务器录像信息完整，优先使用。"""
    replay = conn.execute(
        "SELECT * FROM replays WHERE match_id = ? ORDER BY is_server DESC, id DESC LIMIT 1", (match_id,)
    ).fetchone()
    if replay is None:
        return None

    def rows(table, order):
        query = f"SELECT * FROM {table} WHERE replay_id = ? ORDER BY {order}"
        return [dict(row) for row in conn.execute(query, (replay["id"],))]

    errors = conn.execute(
        "SELECT source, parse_error FROM replays WHERE match_id = ? AND parse_error IS NOT NULL", (match_id,)
    ).fetchall()
    return {
        "replay": dict(replay),
        "errors": [dict(row) for row in errors],
        "players": rows("replay_players", "team, score DESC"),
        "kills": rows("replay_kills", "timestamp_ms, id"),
        "chat": rows("replay_chat", "timestamp_ms, id"),
    }


def get_replay_levels(conn: sqlite3.Connection) -> dict[int, tuple[str, str]]:
    """有录像的比赛 -> (关卡, 战斗类别)。"""
    rows = conn.execute("SELECT match_id, level, battle_class FROM replays")
    return {row["match_id"]: (row["level"], row["battle_class"]) for row in rows}
