import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import requests

from wt_plotter import __version__


UPDATE_REPO = "EvergardenRoxy/WarThunder-Plotter-Plus"
UPDATE_TIMEOUT = 4.0
PRODUCT_NAME = "WT Plotter Plus"
logger = logging.getLogger(__name__)


_INSTALL_UPDATE = """
$ErrorActionPreference = 'Stop'
$planPath = $env:WT_PLOTTER_UPDATE_PLAN
Remove-Item Env:WT_PLOTTER_UPDATE_PLAN
$plan = Get-Content -LiteralPath $planPath -Raw -Encoding UTF8 | ConvertFrom-Json
$backup = $plan.executable + '.old'
$start = @{FilePath = $plan.executable; WorkingDirectory = $plan.cwd; WindowStyle = 'Hidden'}
if ($plan.arguments) { $start.ArgumentList = $plan.arguments }
$installed = $false

try {
    Wait-Process -Id $plan.pid -ErrorAction SilentlyContinue
    $parent = Get-Process -Id $plan.parent_pid -ErrorAction SilentlyContinue
    if ($parent.Path -eq $plan.executable) {
        Wait-Process -InputObject $parent -ErrorAction SilentlyContinue
    }

    [IO.File]::Replace($plan.replacement, $plan.executable, $backup)
    $installed = $true
    Start-Process @start
} catch {
    if ($installed) {
        [IO.File]::Replace($backup, $plan.executable, $plan.replacement)
    } elseif (![IO.File]::Exists($plan.executable) -and [IO.File]::Exists($backup)) {
        [IO.File]::Move($backup, $plan.executable)
    }
    if ([IO.File]::Exists($plan.executable)) {
        $env:WT_PLOTTER_SKIP_UPDATE = '1'
        Start-Process @start
    }
    throw
} finally {
    [IO.File]::Delete($plan.replacement)
    [IO.File]::Delete($planPath)
    [IO.Directory]::Delete([IO.Path]::GetDirectoryName($planPath))
}
"""


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


def _launch_update(
    current_exe: Path, new_exe: Path, pid: int, parent_pid: int,
) -> subprocess.Popen:
    """把启动参数交给等待旧进程退出的 Windows 更新进程。"""
    plan_path = new_exe.with_name("update.json")
    plan_path.write_text(json.dumps({
        "executable": str(current_exe),
        "replacement": str(new_exe),
        "cwd": os.getcwd(),
        "pid": pid,
        "parent_pid": parent_pid,
        "arguments": subprocess.list2cmdline(sys.argv[1:]),
    }), encoding="utf-8")
    return subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _INSTALL_UPDATE],
        env={**os.environ, "WT_PLOTTER_UPDATE_PLAN": str(plan_path), "PYINSTALLER_RESET_ENVIRONMENT": "1"},
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def check_and_update_on_start() -> None:
    if not getattr(sys, "frozen", False) or os.environ.get("WT_PLOTTER_SKIP_UPDATE"):
        return

    directory = None
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

        executable = Path(sys.executable)
        # 同卷的独立暂存目录可直接替换 EXE，也不会被另一次更新覆盖。
        directory = Path(tempfile.mkdtemp(prefix=".wtp-update-", dir=executable.parent))
        downloaded_exe = directory / "update.exe"
        with requests.get(asset["browser_download_url"], stream=True, timeout=UPDATE_TIMEOUT) as download:
            download.raise_for_status()
            with downloaded_exe.open("wb") as handle:
                for chunk in download.iter_content(chunk_size=1024 * 1024):
                    handle.write(chunk)
        _launch_update(executable, downloaded_exe, os.getpid(), os.getppid())
    except (OSError, requests.RequestException) as error:
        if directory is not None:
            shutil.rmtree(directory, ignore_errors=True)
        logger.warning("Update could not be prepared: %s", error)
        return

    sys.exit(0)
