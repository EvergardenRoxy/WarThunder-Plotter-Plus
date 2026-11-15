import os
from pathlib import Path
import shutil
import subprocess
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


def test_update_script_replaces_exe_on_non_ascii_path(tmp_path):
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    current = tmp_path / "中文 한글" / "app.exe"
    new = tmp_path / "下载" / "new.exe"
    for path in (current, new):
        path.parent.mkdir()
        shutil.copyfile(system32 / "whoami.exe", path)
    current.write_bytes(current.read_bytes() + b"OLD")

    # 进程号不存在，脚本不等待，直接替换。
    script = updater._write_update_script(current, new, 4194000)
    subprocess.run(
        ["cmd", "/d", "/c", str(script)], env={**os.environ, "PATH": str(system32)},
        creationflags=subprocess.CREATE_NO_WINDOW, timeout=30, check=True,
    )
    assert not current.read_bytes().endswith(b"OLD")
    assert current.with_name("app.exe.old").read_bytes().endswith(b"OLD")
    assert not new.exists()
