import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
TABLE_PATH = ROOT / "wt_plotter" / "maps" / "table.py"
NAMES_PATH = ROOT / "tests" / "fixtures" / "map_names_en.json"


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
    lines.append("}")

    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TABLE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    NAMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    NAMES_PATH.write_text(json.dumps(names, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Ported {len(ALL_MAPS)} map hashes.")


if __name__ == "__main__":
    main()
