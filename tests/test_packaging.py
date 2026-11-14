from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def test_build_script_bundles_resources():
    script = (SCRIPTS / "build_windows.bat").read_text(encoding="ascii")
    for resource in ("wt_plotter/web/templates", "wt_plotter/web/static", "wt_plotter/i18n/locales"):
        assert re.search(rf'--add-data\s+"{resource}[:;][^"]+"', script)
    assert "WarThunderPlotterPlus" in script


def test_scripts_ascii():
    for name in ("setup.bat", "run.bat", "build_windows.bat"):
        assert (SCRIPTS / name).read_bytes().isascii(), name


def test_no_forbidden_patterns():
    forbidden = re.compile(r"except\s+Exception|except\s*:|ElBartt|import numpy|import aiohttp|os\._exit")
    for file in (ROOT / "wt_plotter").rglob("*.py"):
        match = forbidden.search(file.read_text(encoding="utf-8"))
        assert match is None, (file, match)
