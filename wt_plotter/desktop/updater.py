import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import requests

from wt_plotter import __version__


UPDATE_REPO = "EvergardenRoxy/WarThunder-Plotter-Plus"
UPDATE_TIMEOUT = 4.0
PRODUCT_NAME = "WT Plotter Plus"


def parse_version(tag: str) -> tuple[int, int, int]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", tag)
    if match is None:
        return (0, 0, 0)
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def is_newer(current: str, latest: str) -> bool:
    return parse_version(latest) > parse_version(current)


def latest_release_url() -> str:
    return f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"


def select_asset(assets: list[dict]) -> dict | None:
    executables = [asset for asset in assets if asset.get("name", "").lower().endswith(".exe")]
    return next((asset for asset in executables if "portable" in asset["name"].lower()), None) or (
        executables[0] if executables else None
    )


def _write_update_script(
    current_exe: Path,
    new_exe: Path,
    pid: int,
) -> Path:
    """退出后替换并启动程序。"""
    script_path = new_exe.parent / "wt_plotter_update.cmd"
    current = str(current_exe).replace("%", "%%")
    replacement = str(new_exe).replace("%", "%%")
    script_content = (
        "@echo off\n"
        "setlocal\n"
        f"set CURRENT=\"{current}\"\n"
        f"set NEW=\"{replacement}\"\n"
        f"set OLD=\"{current}.old\"\n"
        "set PID=" + str(pid) + "\n"
        ":wait\n"
        "tasklist /FI \"PID eq %PID%\" | find \"%PID%\" >nul\n"
        "if not errorlevel 1 (\n"
        "  timeout /t 1 >nul\n"
        "  goto wait\n"
        ")\n"
        "if exist %OLD% del /f /q %OLD%\n"
        "move /y %CURRENT% %OLD% >nul\n"
        "move /y %NEW% %CURRENT% >nul\n"
        "start \"\" %CURRENT%\n"
        "endlocal\n"
    )
    script_path.write_text(script_content, encoding="utf-8")
    return script_path


def _launch_update_script(script_path: Path) -> None:
    """在后台运行更新脚本。"""
    subprocess.Popen(
        ["cmd", "/d", "/c", script_path.name],
        cwd=script_path.parent,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def check_and_update_on_start() -> None:
    if not getattr(sys, "frozen", False) or os.environ.get("WT_PLOTTER_SKIP_UPDATE"):
        return

    try:
        response = requests.get(
            latest_release_url(), headers={"User-Agent": PRODUCT_NAME}, timeout=UPDATE_TIMEOUT,
        )
        if response.status_code != 200:
            return
        release = response.json()
        if not is_newer(__version__, release["tag_name"]):
            return
        asset = select_asset(release["assets"])
        if asset is None:
            return

        directory = Path(tempfile.gettempdir()) / "wt_plotter_update"
        directory.mkdir(parents=True, exist_ok=True)
        downloaded_exe = directory / "WarThunderPlotterPlus-portable.exe"
        with requests.get(asset["browser_download_url"], stream=True, timeout=UPDATE_TIMEOUT) as download:
            download.raise_for_status()
            with downloaded_exe.open("wb") as handle:
                for chunk in download.iter_content(chunk_size=1024 * 1024):
                    handle.write(chunk)
    except requests.RequestException:
        return

    script = _write_update_script(Path(sys.executable), downloaded_exe, os.getpid())
    _launch_update_script(script)
    sys.exit(0)
