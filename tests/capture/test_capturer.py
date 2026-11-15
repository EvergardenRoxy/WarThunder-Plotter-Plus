from threading import Event
import threading
from time import monotonic, sleep
from unittest.mock import Mock

import pytest

from wt_plotter.capture.capturer import Capturer
from wt_plotter.storage import db


@pytest.fixture
def client():
    return Mock(**{
        "fetch_map_info.return_value": None,
        "fetch_indicators.return_value": None,
        "fetch_objects.return_value": None,
        "fetch_map_image.return_value": None,
        "fetch_damage.return_value": None,
    })


@pytest.fixture
def capturer(tmp_path, client):
    capturer = Capturer(tmp_path / "matches.db", tmp_path / "maps", client)
    yield capturer
    capturer.stop()


def test_idle_fetches_only_map_info(capturer, client, conn):
    capturer.run_once(0)
    client.fetch_map_info.assert_called_once_with()
    client.fetch_indicators.assert_not_called()
    client.fetch_objects.assert_not_called()
    client.fetch_map_image.assert_not_called()
    assert db.get_active_match(conn) is None


def test_valid_tick_records(capturer, client, conn, obj):
    client.fetch_map_info.return_value = {"valid": True}
    client.fetch_objects.return_value = [obj(0.5, 0.5)]
    capturer.run_once(0)
    stored = db.get_active_match(conn)
    assert db.count_positions(conn, stored.id) == 1


def test_stop_ends_active_match(capturer, client, conn):
    client.fetch_map_info.return_value = {"valid": True}
    capturer.start()
    deadline = monotonic() + 2
    stored = db.get_active_match(conn)
    while stored is None and monotonic() < deadline:
        sleep(0.01)
        stored = db.get_active_match(conn)
    assert stored is not None
    capturer.stop()
    assert db.get_match(conn, stored.id).ended_at
    assert capturer.is_running is False


def test_thread_dies_on_error(capturer, client, monkeypatch):
    unhandled = Event()
    errors = []

    def excepthook(args):
        errors.append(args.exc_value)
        unhandled.set()

    monkeypatch.setattr(threading, "excepthook", excepthook)
    client.fetch_map_info.side_effect = RuntimeError("telemetry error")
    capturer.start()
    deadline = monotonic() + 2
    assert unhandled.wait(timeout=2)
    while capturer.is_running and monotonic() < deadline:
        sleep(0.01)
    assert capturer.is_running is False
    assert len(errors) == 1 and isinstance(errors[0], RuntimeError)


def test_damage_unavailable_keeps_tracking(capturer, client, conn, obj):
    client.fetch_map_info.return_value = {"valid": True}
    client.fetch_objects.return_value = [obj(0.5, 0.5)]
    capturer.run_once(0)
    capturer.run_once(1)
    match = db.get_active_match(conn)
    assert db.count_positions(conn, match.id) == 2
    client.fetch_damage.assert_called_with(0)


def test_damage_fetched_with_cursor(capturer, client, conn, obj):
    client.fetch_map_info.return_value = {"valid": True}
    client.fetch_objects.return_value = [obj(0.5, 0.5)]
    client.fetch_damage.return_value = [{"id": 7, "msg": "m", "time": 1}]
    capturer.run_once(0)
    client.fetch_damage.return_value = []
    capturer.run_once(1)
    client.fetch_damage.assert_called_with(7)
