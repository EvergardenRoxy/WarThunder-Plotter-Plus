import pytest

from wt_plotter import i18n


def test_translate_params(monkeypatch):
    monkeypatch.setattr(i18n, "load_catalog", lambda lang: {"a": "x {n}"})
    assert i18n.translate("en", "a", n=3) == "x 3"


def test_missing_key_raises():
    with pytest.raises(KeyError):
        i18n.translate("en", "missing")


def test_get_language_reads_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"language": "zh"}', encoding="utf-8")
    assert i18n.get_language(path) == "zh"


def test_get_language_first_run(tmp_path):
    path = tmp_path / "settings.json"
    assert i18n.get_language(path) == i18n.detect_system_language()
    assert not path.exists()


def test_set_language_roundtrip(tmp_path):
    path = tmp_path / "data" / "settings.json"
    i18n.set_language(path, "en")
    assert i18n.get_language(path) == "en"


def test_set_language_unknown(tmp_path):
    with pytest.raises(ValueError):
        i18n.set_language(tmp_path / "settings.json", "fr")


def test_languages_come_from_locale_files():
    assert set(i18n.LANGUAGES) == {path.stem for path in i18n.LOCALES_DIR.glob("*.json")}
    assert i18n.DEFAULT_LANGUAGE in i18n.LANGUAGES
    assert set(i18n.WINDOWS_LANGUAGES.values()) <= set(i18n.LANGUAGES)


def test_language_names_are_native():
    names = i18n.language_names()
    assert names.keys() == set(i18n.LANGUAGES)
    assert (names["en"], names["zh"]) == ("English", "中文")


def test_get_language_unsupported_falls_back(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"language": "xx"}', encoding="utf-8")
    assert i18n.get_language(path) == i18n.detect_system_language()
