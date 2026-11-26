import pytest

from builders import aircraft_state_body
from wt_plotter.replay import aircraft, messages, positions, tracks, wrpl
from wt_plotter.storage import db


def test_aircraft_entries_read_uids_and_positions():
    body = aircraft_state_body([(300, (1234.5, 300.0, -4567.25)), (301, (-8000.0, 1500.0, 9000.0)), (305, None),
                                (400, (1.0, 2.0, 3.0))])
    assert aircraft.aircraft_entries(body) == [
        (300, (1234.5, 300.0, -4567.25)), (301, (-8000.0, 1500.0, 9000.0)), (400, (1.0, 2.0, 3.0)),
    ]


def flight(start, step, frames):
    return [(start[0] + step * i, start[1], start[2]) for i in range(frames)]


def build_packets(frames, b_from=0):
    """飞机 200 与 201 平行飞行，每 0.25 秒一包；201 从第 b_from 帧起才出现。"""
    a = flight((1000.0, 500.0, 1000.0), 20.0, frames)
    b = flight((1000.0, 500.0, 1100.0), 20.0, frames)
    return [
        wrpl.Packet(1 + i * 0.25, aircraft.AIRCRAFT_STATE, aircraft_state_body([(200, a[i])] + ([(201, b[i])] if i >= b_from else [])))
        for i in range(frames)
    ]


def test_read_tracks_by_uid():
    result = aircraft.read_tracks(build_packets(20), messages.Battle({}, {}, []))
    assert [(t.eid, len(t.points), t.air) for t in result] == [(200, 20, True), (201, 20, True)]
    assert result[0].points[-1] == (5.75, 1380.0, 500.0, 1000.0)


def test_read_tracks_drops_falling_wreck_after_death():
    battle = messages.Battle({}, {}, [messages.Kill(3.0, None, "", None, 201)])
    result = {t.eid: t for t in aircraft.read_tracks(build_packets(20), battle)}
    assert max(p[0] for p in result[201].points) == 3.0


def test_split_lives_starts_new_life_after_gap_or_jump():
    samples = [(1.0, 0.0, 0.0, 0.0), (2.0, 100.0, 0.0, 0.0), (3.0, 160.0, 0.0, 0.0), (9.0, 5000.0, 0.0, 0.0)]
    # 空战：第 3 秒是连续坠落的残骸，6 秒断档后复活。
    assert tracks.split_lives(samples, [2.0], 400.0, 3.0) == [samples[:2], samples[3:]]
    # 陆战：残骸原地不动；开出 50 米以外就是新的一命。
    assert tracks.split_lives(samples, [2.0], 0.0, float("inf")) == [samples[:2], samples[2:]]


def test_projector_maps_north_up():
    project = positions.projector((-100.0, -100.0, 100.0, 100.0))
    assert project(-100.0, 100.0) == (0.0, 0.0)
    assert project(100.0, -100.0) == (1.0, 1.0)
    assert project(0.0, 50.0) == (0.5, 0.25)


def test_extent_bounds_is_square_with_margin():
    track = tracks.UnitTrack(1, [(0.0, 0.0, 0.0, 0.0), (1.0, 2000.0, 0.0, 500.0)], True)
    min_x, min_z, max_x, max_z = positions.extent_bounds([track])
    assert max_x - min_x == pytest.approx(2200.0) and max_z - min_z == pytest.approx(2200.0)
    assert (min_x + max_x) / 2 == pytest.approx(1000.0) and (min_z + max_z) / 2 == pytest.approx(250.0)


def test_extent_bounds_of_a_single_point_has_minimum_size():
    min_x, _, max_x, _ = positions.extent_bounds([tracks.UnitTrack(1, [(0.0, 5.0, 0.0, 5.0)], True)])
    assert max_x - min_x == pytest.approx(1100.0)


def test_build_ticks_groups_by_time_with_relation_styles():
    a = tracks.UnitTrack(1, [(1.0, 0.0, 0.0, 0.0), (2.0, 10.0, 0.0, 0.0)], True)
    b = tracks.UnitTrack(2, [(1.0, 5.0, 0.0, 5.0)], True)
    labels = [("Alice", "yak-3"), (None, None)]
    ticks = positions.build_ticks([a, b], ["player", "enemy"], labels, "yak-3", (-10.0, -10.0, 10.0, 10.0), False)
    assert [tick.timestamp for tick, _ in ticks] == [1.0, 2.0]
    first_tick, first_positions = ticks[0]
    assert first_tick == db.TickRecord(1.0, "air", "yak-3", 1, 0)
    assert [(p.icon, p.color) for p in first_positions] == [("Player", "#faC81E"), ("Fighter", "#fa0C00")]
    assert (first_positions[1].x, first_positions[1].y) == (0.75, 0.25)


def test_build_ticks_ground_battle_mixes_tanks_and_aircraft():
    tank = tracks.UnitTrack(1, [(1.0, 0.0, 0.0, 0.0)], False)
    plane = tracks.UnitTrack(2, [(1.0, 5.0, 0.0, 5.0)], True)
    labels = [("Bob", "us_m4a1"), ("Carol", "p-47d")]
    (tick, records), = positions.build_ticks([tank, plane], ["ally", "enemy"], labels, "us_m4a1", (-10.0, -10.0, 10.0, 10.0), True)
    assert tick == db.TickRecord(1.0, "tank", "us_m4a1", 0, 0)
    assert [(r.obj_type, r.icon, r.unit_name, r.unit_vehicle) for r in records] == [
        ("ground_model", "MediumTank", "Bob", "us_m4a1"), ("aircraft", "Fighter", "Carol", "p-47d"),
    ]


def test_resample_interpolates_on_grid_and_skips_long_gaps():
    points = [(0.5, 0.0, 0.0, 0.0), (2.5, 20.0, 0.0, 0.0), (30.0, 0.0, 0.0, 0.0)]
    assert tracks.resample(points, 1.0, 15.0) == [(1.0, 5.0, 0.0, 0.0), (2.0, 15.0, 0.0, 0.0)]
