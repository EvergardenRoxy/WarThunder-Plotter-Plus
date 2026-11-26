from dataclasses import replace
import socket
from threading import Thread
from time import monotonic, sleep
from unittest.mock import Mock

from click.testing import CliRunner
import pytest
import requests

from wt_plotter import cli as cli_module
from wt_plotter.cli import cli, run_server, running_instance_status
from wt_plotter.process_lock import LockHeld, hold_lock
from wt_plotter.web.app import create_app


HOST = "127.0.0.1"


@pytest.fixture
def running_server(tmp_path):
    with socket.socket() as server_socket:
        server_socket.bind((HOST, 0))
        port = server_socket.getsockname()[1]

    app = create_app(tmp_path / "matches.db", tmp_path / "maps", tmp_path / "settings.json", None)
    thread = Thread(target=run_server, args=(app, HOST, port), daemon=True)
    thread.start()
    url = f"http://{HOST}:{port}"
    try:
        deadline = monotonic() + 3
        while monotonic() < deadline:
            try:
                if requests.get(f"{url}/api/status", timeout=0.2).ok:
                    break
            except requests.ConnectionError:
                sleep(0.02)
        else:
            pytest.fail("Server never became ready")
        yield port, url, thread
    finally:
        if thread.is_alive() and "SHUTDOWN" in app.config:
            app.config["SHUTDOWN"]()
        thread.join(timeout=3)


def test_run_server_stops_on_shutdown(running_server):
    _, url, thread = running_server
    assert requests.get(f"{url}/api/status", timeout=1).status_code == 200
    assert requests.post(f"{url}/shutdown", timeout=1).status_code == 200
    thread.join(timeout=3)
    assert not thread.is_alive()


def test_instance_probe(running_server):
    port, url, thread = running_server
    assert running_instance_status(HOST, port)["capturing"] is False
    requests.post(f"{url}/shutdown", timeout=1).raise_for_status()
    thread.join(timeout=3)
    assert running_instance_status(HOST, port) is None


def test_help_lists_commands():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert all(name in result.output for name in ("watch", "serve", "capture"))


def test_lock_is_exclusive_and_released(tmp_path):
    path = tmp_path / "data" / "capture.lock"
    with hold_lock(path):
        with pytest.raises(LockHeld):
            with hold_lock(path):
                pass
    with hold_lock(path):
        pass


def test_second_capture_is_refused(tmp_path, monkeypatch):
    paths = replace(cli_module.PATHS, data_dir=tmp_path, capture_lock=tmp_path / "capture.lock")
    monkeypatch.setattr(cli_module, "PATHS", paths)
    capturer = Mock()
    monkeypatch.setattr(cli_module, "Capturer", capturer)
    with hold_lock(paths.capture_lock):
        result = CliRunner().invoke(cli, ["capture"])
    assert result.exit_code == 1
    assert "Another capture" in result.output
    capturer.assert_not_called()


def test_watch_warns_when_running_instance_is_not_capturing(running_server, monkeypatch, caplog):
    port, _, _ = running_server
    monkeypatch.setattr(cli_module.webbrowser, "open", Mock())
    capturer = Mock()
    monkeypatch.setattr(cli_module, "Capturer", capturer)
    with caplog.at_level("WARNING"):
        result = CliRunner().invoke(cli, ["watch", "--port", str(port)])
    assert result.exit_code == 0
    assert "not capturing" in caplog.text
    capturer.assert_not_called()
    cli_module.webbrowser.open.assert_called_once()


def test_import_replay_command(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli_module, "PATHS", replace(cli_module.PATHS, db_path=tmp_path / "m.db"))
    monkeypatch.setattr(cli_module.importer, "load_path", lambda path: path.name)
    monkeypatch.setattr(cli_module.importer, "import_replay", lambda conn, replay, source, lang: calls.append(replay) or 7)
    (tmp_path / "a.wrpl").write_bytes(b"")
    result = CliRunner().invoke(cli, ["import-replay", str(tmp_path / "a.wrpl")])
    assert result.exit_code == 0, result.output
    assert calls == ["a.wrpl"] and "match 7" in result.output


def test_download_replay_command(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_module, "PATHS", replace(cli_module.PATHS, db_path=tmp_path / "m.db", replays_dir=tmp_path))
    monkeypatch.setattr(cli_module.download, "download_server_replay", lambda session, target: target / session)
    monkeypatch.setattr(cli_module.importer, "load_path", lambda path: path)
    monkeypatch.setattr(cli_module.importer, "import_replay", lambda conn, replay, source, lang: 3)
    result = CliRunner().invoke(cli, ["download-replay", "72C412C1002817AE"])
    assert result.exit_code == 0, result.output
    assert "72c412c1002817ae -> match 3" in result.output
