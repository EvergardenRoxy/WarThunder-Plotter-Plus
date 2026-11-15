import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
TABLE_PATH = ROOT / "wt_plotter" / "maps" / "table.py"
NAMES_PATH = ROOT / "tests" / "fixtures" / "map_names_en.json"

# 上游表之外、用真实比赛核对过的哈希：(哈希, map_id, BattleType 名, location)。
LOCAL_MAPS = [
    # 2026-11-15 采集的 match 5，对应录像的关卡为 avg_krymsk（krymsk_dom）；游戏更新后的地面图。
    ("33d843f98ff212cce719ce03248de199430f4e1f91b356632bb4e5680", "avg_krymsk_tankmap", "GROUND", "krymsk"),
]


def main() -> None:
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "reference" / "upstream"))
    from map_hashes import ALL_MAPS, BattleType

    lines = [
        '"""由 scripts/port_map_table.py 生成。"""',
        "",
        "from dataclasses import dataclass",
        "from enum import Enum",
        "",
        "",
        "class BattleType(str, Enum):",
    ]
    lines.extend(f"    {kind.name} = {kind.value!r}" for kind in BattleType)
    lines.extend([
        "",
        "",
        "@dataclass(frozen=True)",
        "class MapInfo:",
        "    map_id: str",
        "    battle_type: BattleType",
        "    location: str",
        "",
        "",
        'UNKNOWN_MAP = MapInfo("unknown", BattleType.UNKNOWN, "")',
        "",
        "MAPS: dict[str, MapInfo] = {",
    ])

    names: dict[str, str] = {}
    for dhash, info in ALL_MAPS.items():
        name = re.sub(r"^[^A-Za-z0-9]+", "", info.display_name).strip()
        if names.setdefault(info.map_id, name) != name:
            raise ValueError(f"Conflicting names for {info.map_id}: {names[info.map_id]!r}, {name!r}")
        lines.append(
            f"    {dhash!r}: MapInfo({info.map_id!r}, BattleType.{info.battle_type.name}, {name.lower()!r}),"
        )
    for dhash, map_id, battle_type, location in LOCAL_MAPS:
        lines.append(f"    {dhash!r}: MapInfo({map_id!r}, BattleType.{battle_type}, {location!r}),")
    lines.append("}")

    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TABLE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    NAMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    NAMES_PATH.write_text(json.dumps(names, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Ported {len(ALL_MAPS)} map hashes.")


if __name__ == "__main__":
    main()
