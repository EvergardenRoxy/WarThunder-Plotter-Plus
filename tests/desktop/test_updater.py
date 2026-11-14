import sys
from unittest.mock import Mock

import requests

from wt_plotter.desktop import updater


def test_repo():
    assert updater.latest_release_url() == "https://api.github.com/repos/EvergardenRoxy/WarThunder-Plotter-Plus/releases/latest"


def test_version_compare():
    assert updater.is_newer("0.3.0", "v0.3.1")
    assert not updater.is_newer("0.3.0", "v0.3.0")
    assert not updater.is_newer("0.3.0", "v0.2.9")


def test_select_asset():
    assets = [{"name": "a.zip"}, {"name": "X.exe"}, {"name": "X-portable.exe"}]
    assert updater.select_asset(assets) is assets[2]
    assert updater.select_asset(assets[:1]) is None


def test_skipped_from_source(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    get = Mock(side_effect=AssertionError("Unexpected request"))
    monkeypatch.setattr(requests, "get", get)
    updater.check_and_update_on_start()
    get.assert_not_called()


def test_offline_is_no_update(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("WT_PLOTTER_SKIP_UPDATE", raising=False)
    get = Mock(side_effect=requests.ConnectionError)
    monkeypatch.setattr(requests, "get", get)
    updater.check_and_update_on_start()
    get.assert_called_once()
