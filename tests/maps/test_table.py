from dataclasses import fields
import re

from wt_plotter.maps.table import MAPS, BattleType, MapInfo


def test_no_map_present():
    assert any(info.map_id == "no_map" for info in MAPS.values())


def test_hash_length_uniform():
    assert len({len(key) for key in MAPS}) == 1
    assert all(re.fullmatch(r"[0-9a-f]+", key) for key in MAPS)


def test_nuke_pairs_share_location():
    ground = {info.location for info in MAPS.values() if info.battle_type is BattleType.GROUND}
    air = {info.location for info in MAPS.values() if info.battle_type is BattleType.AIR}
    assert (ground & air) - {""}


def test_no_display_name_field():
    assert {field.name for field in fields(MapInfo)} == {"map_id", "battle_type", "location"}
