from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
READMES = [ROOT / "README.md", ROOT / "README.zh-CN.md"]


def test_doc_pairs():
    en, zh = [{path.name for path in (ROOT / "docs" / lang).glob("*.md")} for lang in ("en", "zh")]
    assert en and en == zh


def test_readme_cross_links():
    for source, target in (READMES, READMES[::-1]):
        assert f"]({target.name})" in source.read_text(encoding="utf-8")


def test_readme_credits_upstream():
    for file in READMES:
        content = file.read_text(encoding="utf-8")
        for credit in ("ElBartt/WarThunder-Plotter", "Sgambe33", "ValerieOSD"):
            assert credit in content


def test_readme_structure_current():
    for file in READMES:
        content = file.read_text(encoding="utf-8")
        for path in re.findall(r"\bwt_plotter/(?:[A-Za-z_]\w*/)+", content):
            assert (ROOT / path).is_dir(), path


def test_zh_docs_are_chinese():
    for file in [READMES[1], *sorted((ROOT / "docs" / "zh").glob("*.md"))]:
        assert re.search(r"[\u4e00-\u9fff]", file.read_text(encoding="utf-8")), file.name
