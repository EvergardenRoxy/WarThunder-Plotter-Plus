import json
from pathlib import Path
import re
from string import Formatter

from wt_plotter.i18n import load_catalog
from wt_plotter.maps.table import MAPS, BattleType


MAP_IDS = {info.map_id for info in MAPS.values()}


def test_same_keys():
    assert load_catalog("en").keys() == load_catalog("zh").keys()


def test_every_map_named():
    keys = {f"map.{map_id}" for map_id in MAP_IDS | {"unknown"}}
    assert keys <= load_catalog("en").keys()
    assert keys <= load_catalog("zh").keys()


def test_en_map_names_match_upstream():
    path = Path(__file__).resolve().parents[1] / "fixtures" / "map_names_en.json"
    names = json.loads(path.read_text(encoding="utf-8"))
    en = load_catalog("en")
    for map_id, name in names.items():
        assert en[f"map.{map_id}"] == name


def test_zh_map_names_untranslated():
    en, zh = load_catalog("en"), load_catalog("zh")
    for map_id in MAP_IDS:
        assert zh[f"map.{map_id}"] == en[f"map.{map_id}"]


def test_battle_types_named():
    keys = {f"battle_type.{kind.value}" for kind in BattleType}
    assert keys <= load_catalog("en").keys()
    assert keys <= load_catalog("zh").keys()


def test_placeholders_match():
    formatter = Formatter()
    en, zh = load_catalog("en"), load_catalog("zh")
    for key in en:
        en_fields = {field for _, field, _, _ in formatter.parse(en[key]) if field is not None}
        zh_fields = {field for _, field, _, _ in formatter.parse(zh[key]) if field is not None}
        assert en_fields == zh_fields, key


def test_zh_has_chinese():
    values = [value for key, value in load_catalog("zh").items() if not key.startswith("map.")]
    assert sum(bool(re.search(r"[\u4e00-\u9fff]", value)) for value in values) / len(values) >= 0.9
