from unittest.mock import Mock

import pytest
import requests

from wt_plotter.capture.client import TelemetryClient


@pytest.fixture
def response(monkeypatch):
    response = Mock(status_code=200, content=b"png")
    get = Mock(return_value=response)
    monkeypatch.setattr(requests.Session, "get", get)
    return response, get


def test_connection_refused_returns_none(response):
    _, get = response
    get.side_effect = requests.ConnectionError
    client = TelemetryClient()
    assert client.fetch_map_info() is None
    assert client.fetch_indicators() is None
    assert client.fetch_objects() is None
    assert client.fetch_map_image() is None
    assert client.fetch_damage(0) is None


def test_timeout_returns_none(response):
    _, get = response
    get.side_effect = requests.Timeout
    assert TelemetryClient().fetch_map_info() is None


def test_non_200_returns_none(response):
    resp, _ = response
    resp.status_code = 500
    assert TelemetryClient().fetch_map_info() is None
    resp.json.assert_not_called()


def test_other_errors_propagate(response):
    _, get = response
    get.side_effect = ValueError
    with pytest.raises(ValueError):
        TelemetryClient().fetch_map_info()


def test_objects_must_be_list(response):
    resp, _ = response
    resp.json.return_value = {}
    assert TelemetryClient().fetch_objects() is None


def test_urls(response):
    _, get = response
    client = TelemetryClient()
    client.fetch_map_info()
    client.fetch_indicators()
    client.fetch_objects()
    assert client.fetch_map_image() == b"png"
    assert [call.args[0] for call in get.call_args_list] == [
        f"http://127.0.0.1:8111/{endpoint}"
        for endpoint in ("map_info.json", "indicators", "map_obj.json", "map.img")
    ]


# 社区资料中的 /hudmsg 格式，尚未用真实游戏数据核对。
HUDMSG = {"events": [], "damage": [
    {"id": 5, "msg": "A (Tiger E) destroyed B (M4A3)", "sender": "", "enemy": False, "mode": "", "time": 95},
]}


def test_fetch_damage(response):
    resp, get = response
    resp.json.return_value = HUDMSG
    assert TelemetryClient().fetch_damage(4) == HUDMSG["damage"]
    assert get.call_args.args[0] == "http://127.0.0.1:8111/hudmsg?lastEvt=0&lastDmg=4"


@pytest.mark.parametrize("payload", [{"events": []}, {"damage": None}, []])
def test_fetch_damage_skips_invalid_payload(response, payload):
    resp, _ = response
    resp.json.return_value = payload
    assert TelemetryClient().fetch_damage(0) is None


def test_fetch_damage_skips_invalid_json(response):
    resp, _ = response
    resp.json.side_effect = requests.exceptions.JSONDecodeError("Invalid JSON", "", 0)
    assert TelemetryClient().fetch_damage(0) is None


def test_fetch_damage_keeps_valid_entries_in_a_partial_response(response):
    resp, _ = response
    resp.json.return_value = {"damage": [{}, {"id": "6", "msg": "invalid"}, *HUDMSG["damage"]]}
    assert TelemetryClient().fetch_damage(0) == HUDMSG["damage"]
