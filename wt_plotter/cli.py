from contextlib import contextmanager
import logging
from pathlib import Path
import shutil
import sys
import threading
import time
import webbrowser

import click
from flask import Flask
import requests
from werkzeug.serving import make_server

from wt_plotter.capture.capturer import Capturer
from wt_plotter.capture.client import TelemetryClient
from wt_plotter.config import APP_SETTINGS, PATHS
from wt_plotter.desktop import tray, updater
from wt_plotter.process_lock import LockHeld, hold_lock
from wt_plotter.web.app import create_app


logger = logging.getLogger(__name__)


def run_server(app: Flask, host: str, port: int) -> None:
    with make_server(host, port, app, threaded=True) as server:
        app.config["SHUTDOWN"] = server.shutdown
        logger.info("Web server listening on http://%s:%s", host, port)
        server.serve_forever()


def running_instance_status(host: str, port: int) -> dict | None:
    """返回已在该地址运行的实例的状态，没有则返回 None。"""
    try:
        response = requests.get(f"http://{host}:{port}/api/status", timeout=1.0)
    except requests.RequestException:
        return None
    return response.json() if response.ok else None


@contextmanager
def single_capturer():
    """同一数据目录只允许一个采集器，否则会互相关闭对方的比赛。"""
    try:
        with hold_lock(PATHS.capture_lock):
            yield
    except LockHeld:
        logger.error("Another capture is already recording into %s", PATHS.data_dir)
        raise click.ClickException(f"Another capture is already recording into {PATHS.data_dir}.")


def _run_web_mode(host: str, port: int, capture_enabled: bool) -> None:
    local_host = "127.0.0.1" if host == "0.0.0.0" else host
    page = "/live" if capture_enabled else "/"
    url = f"http://{local_host}:{port}{page}"
    status = running_instance_status(local_host, port)
    if status is not None:
        if capture_enabled and not status["capturing"]:
            logger.warning("The instance at %s is not capturing; quit it to start recording.", url)
        if APP_SETTINGS.open_browser_on_start:
            webbrowser.open(url)
        return

    if capture_enabled:
        with single_capturer():
            _serve(host, port, local_host, url, Capturer(PATHS.db_path, PATHS.maps_dir, TelemetryClient()))
    else:
        _serve(host, port, local_host, url, None)


def _serve(host: str, port: int, local_host: str, url: str, capturer: Capturer | None) -> None:
    app = create_app(PATHS.db_path, PATHS.maps_dir, PATHS.settings_path, capturer)
    try:
        if capturer is not None:
            capturer.start()
        tray.start_tray(local_host, port, PATHS.settings_path)
        if APP_SETTINGS.open_browser_on_start:
            webbrowser.open(url)
        run_server(app, host, port)
    finally:
        try:
            if capturer is not None:
                capturer.stop()
        finally:
            tray.stop_tray()


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Record and view War Thunder match trajectories."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(watch, host=APP_SETTINGS.host, port=APP_SETTINGS.port)


@cli.command()
@click.option("--host", default=APP_SETTINGS.host, show_default=True, help="Address to bind to.")
@click.option("--port", default=APP_SETTINGS.port, show_default=True, help="Port to listen on.")
def watch(host: str, port: int) -> None:
    """Run the capture thread and web server."""
    _run_web_mode(host, port, capture_enabled=True)


@cli.command()
@click.option("--host", default=APP_SETTINGS.host, show_default=True, help="Address to bind to.")
@click.option("--port", default=APP_SETTINGS.port, show_default=True, help="Port to listen on.")
def serve(host: str, port: int) -> None:
    """View matches with the web server."""
    _run_web_mode(host, port, capture_enabled=False)


@cli.command()
def capture() -> None:
    """Record matches in the background until interrupted."""
    with single_capturer():
        capturer = Capturer(PATHS.db_path, PATHS.maps_dir, TelemetryClient())
        capturer.start()
        try:
            while capturer.is_running:
                time.sleep(0.2)
        finally:
            capturer.stop()


def _log_thread_failure(args: threading.ExceptHookArgs) -> None:
    logger.error(
        "Unhandled error in thread %s", args.thread.name,
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def main() -> None:
    PATHS.log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(PATHS.log_path, encoding="utf-8")],
    )
    threading.excepthook = _log_thread_failure
    updater.check_and_update_on_start()
    if getattr(sys, "frozen", False):
        # 首次运行时从包内补齐地图。
        PATHS.maps_dir.mkdir(parents=True, exist_ok=True)
        for image in (Path(sys._MEIPASS) / "data" / "maps").glob("*.png"):
            target = PATHS.maps_dir / image.name
            if not target.exists():
                shutil.copyfile(image, target)
    cli()
