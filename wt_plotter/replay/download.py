"""按场次号从录像 CDN 下载服务器录像分段（无需登录）。"""

from __future__ import annotations

import logging
from pathlib import Path
import re

import requests

from wt_plotter.config import REPLAY_SETTINGS


logger = logging.getLogger(__name__)

_HEX_SESSION = re.compile(r"[0-9a-fA-F]{16}")


def parse_session(text: str) -> str:
    """接受 16 位十六进制场次号、十进制场次号或末尾带场次号的链接，返回 16 位十六进制。"""
    token = text.strip().rstrip("/").rsplit("/", 1)[-1]
    if _HEX_SESSION.fullmatch(token):
        return token.lower()
    if token.isdigit():
        return f"{int(token):016x}"
    raise ValueError(f"not a session id: {text!r}")


def download_server_replay(session: str, target_dir: Path) -> Path:
    """依次下载 0000、0001……直到返回 404，返回分段所在目录。"""
    folder = target_dir / session
    folder.mkdir(parents=True, exist_ok=True)
    part = 0
    with requests.Session() as http:
        while True:
            url = REPLAY_SETTINGS.part_url.format(session=session, part=part)
            response = http.get(url, timeout=REPLAY_SETTINGS.timeout)
            if response.status_code == 404:
                break
            response.raise_for_status()
            (folder / f"{part:04d}.wrpl").write_bytes(response.content)
            logger.info("Downloaded %s", url)
            part += 1
    if part == 0:
        raise FileNotFoundError(f"server replay {session} is not available")
    return folder
