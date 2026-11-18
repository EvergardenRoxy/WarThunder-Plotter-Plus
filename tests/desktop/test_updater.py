import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, Mock

import pytest
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


@pytest.mark.parametrize("missing_replacement", [False, True])
def test_installs_updates_on_non_ascii_path_and_preserves_current_on_failure(tmp_path, missing_replacement):
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    current = tmp_path / "中文 한글" / "app.exe"
    new = current.parent / ".wtp-update-test" / "update.exe"
    new.parent.mkdir(parents=True)
    image = (system32 / "whoami.exe").read_bytes()
    current.write_bytes(image + b"OLD")
    if not missing_replacement:
        new.write_bytes(image)

    process = updater._launch_update(current, new, 4194000, 4194004)
    result = process.wait(timeout=30)
    assert not new.parent.exists()
    if missing_replacement:
        assert result != 0
        assert current.read_bytes() == image + b"OLD"
    else:
        assert result == 0
        assert current.read_bytes() == image
        assert current.with_name("app.exe.old").read_bytes() == image + b"OLD"


def test_restart_preserves_windows_arguments_and_working_directory(tmp_path, monkeypatch):
    plan = {}

    def launch(command, *, env, creationflags):
        plan.update(json.loads(Path(env["WT_PLOTTER_UPDATE_PLAN"]).read_text(encoding="utf-8")))

    args = ["serve", "--host", "0.0.0.0", "--port", "5250", 'a "quoted" value', "中文 한글"]
    monkeypatch.setattr(sys, "argv", ["app.exe", *args])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(subprocess, "Popen", launch)
    updater._launch_update(tmp_path / "app.exe", tmp_path / "update.exe", 123, 456)
    assert plan["arguments"] == subprocess.list2cmdline(args)
    assert plan["cwd"] == str(tmp_path)
    assert (plan["pid"], plan["parent_pid"]) == (123, 456)


def test_each_start_stages_the_update_separately(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app.exe"))
    monkeypatch.delenv("WT_PLOTTER_SKIP_UPDATE", raising=False)
    release = Mock(status_code=200)
    release.json.return_value = {
        "tag_name": "v999.0.0",
        "assets": [{"name": "portable.exe", "browser_download_url": "fixture"}],
    }
    response = MagicMock()
    download = response.__enter__.return_value
    download.iter_content.return_value = [b"new contents"]
    monkeypatch.setattr(requests, "get", Mock(side_effect=[release, response, release, response]))
    launch = Mock()
    monkeypatch.setattr(updater, "_launch_update", launch)

    for _ in range(2):
        with pytest.raises(SystemExit) as error:
            updater.check_and_update_on_start()
        assert error.value.code == 0
    staged = [call.args[1] for call in launch.call_args_list]
    assert staged[0].parent != staged[1].parent
    assert all(path.parent.parent == tmp_path and path.read_bytes() == b"new contents" for path in staged)
