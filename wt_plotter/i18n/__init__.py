import ctypes
from functools import lru_cache
import json
from pathlib import Path
import sys


LANGUAGES = ("en", "zh")
LOCALES_DIR = Path(__file__).with_name("locales")


@lru_cache
def load_catalog(lang: str) -> dict[str, str]:
    if lang not in LANGUAGES:
        raise ValueError(f"Unknown language: {lang}")
    return json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def translate(lang: str, key: str, **params) -> str:
    return load_catalog(lang)[key].format(**params)


def detect_system_language() -> str:
    if sys.platform == "win32":
        language_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        if language_id & 0x3FF == 0x04:
            return "zh"
    return "en"


def get_language(settings_path: Path) -> str:
    try:
        settings = settings_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return detect_system_language()
    return json.loads(settings)["language"]


def set_language(settings_path: Path, lang: str) -> None:
    if lang not in LANGUAGES:
        raise ValueError(f"Unknown language: {lang}")
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({"language": lang}) + "\n", encoding="utf-8")
