import socket
from threading import Thread
from time import monotonic, sleep

from click.testing import CliRunner
import pytest
import requests

from wt_plotter.cli import another_instance_running, cli, run_server
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
    assert another_instance_running(HOST, port)
    requests.post(f"{url}/shutdown", timeout=1).raise_for_status()
    thread.join(timeout=3)
    assert not another_instance_running(HOST, port)


def test_help_lists_commands():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert all(name in result.output for name in ("watch", "serve", "capture"))
