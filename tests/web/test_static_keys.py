from pathlib import Path
import re

from wt_plotter.i18n import load_catalog


WEB = Path(__file__).resolve().parents[2] / "wt_plotter" / "web"
TRANSLATION_KEY = re.compile(r"""\bt\(\s*(['"])([^'"]+)\1""")


def test_template_keys_exist():
    for path in (WEB / "templates").glob("*.html"):
        keys = {key for _, key in TRANSLATION_KEY.findall(path.read_text(encoding="utf-8"))}
        assert keys <= load_catalog("en").keys(), path.name


def test_js_keys_exist():
    for path in (WEB / "static").glob("*.js"):
        keys = {key for _, key in TRANSLATION_KEY.findall(path.read_text(encoding="utf-8"))}
        assert keys <= load_catalog("en").keys(), path.name


def test_no_innerhtml():
    for path in (WEB / "static").glob("*.js"):
        assert "innerHTML" not in path.read_text(encoding="utf-8"), path.name


def test_templates_have_no_literal_text():
    for page in ("index.html", "match.html", "waiting.html"):
        source = (WEB / "templates" / page).read_text(encoding="utf-8")
        text = re.sub(r"<script\b[^>]*>.*?</script>|{%.*?%}|{{.*?}}|{#.*?#}|<[^>]+>", "", source, flags=re.DOTALL)
        assert re.search(r"\b[a-zA-Z]{3,}\b", text) is None, page


def test_no_spread_over_position_arrays():
    # 整场位置可达几十万条，展开成函数参数会超出引擎上限。
    for path in (WEB / "static").glob("*.js"):
        assert re.search(r"Math\.(max|min)\(\s*\.\.\.", path.read_text(encoding="utf-8")) is None, path.name


def test_unit_shapes_have_names():
    # 悬停提示按 unit.<icon> 动态取译名。
    source = (WEB / "static" / "viewer.js").read_text(encoding="utf-8")
    block = re.search(r"unitShapes: \{(.*?)\n    \},", source, re.DOTALL).group(1)
    icons = set(re.findall(r"^\s*(\w+): \{", block, re.MULTILINE)) | {"Player"}
    for lang in ("en", "zh"):
        assert {f"unit.{icon}" for icon in icons} <= load_catalog(lang).keys(), lang
