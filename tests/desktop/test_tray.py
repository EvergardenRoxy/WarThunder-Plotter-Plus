from wt_plotter.desktop.tray import menu_labels
from wt_plotter.i18n import LANGUAGES, set_language, translate


def test_labels_follow_language(tmp_path):
    settings = tmp_path / "settings.json"
    for lang in LANGUAGES:
        set_language(settings, lang)
        assert menu_labels(settings) == (translate(lang, "tray.open"), translate(lang, "tray.quit"))
