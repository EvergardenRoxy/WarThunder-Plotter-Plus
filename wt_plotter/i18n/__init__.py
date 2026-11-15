import ctypes
from functools import lru_cache
import json
from pathlib import Path
import sys


LOCALES_DIR = Path(__file__).with_name("locales")
# 每个语言文件就是一种受支持的语言。
LANGUAGES = tuple(sorted(path.stem for path in LOCALES_DIR.glob("*.json")))
DEFAULT_LANGUAGE = "en"
# Windows 主语言 ID 对应的语言代码，未列出的用默认语言。
WINDOWS_LANGUAGES = {0x04: "zh"}


@lru_cache
def load_catalog(lang: str) -> dict[str, str]:
    if lang not in LANGUAGES:
        raise ValueError(f"Unknown language: {lang}")
    return json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def translate(lang: str, key: str, **params) -> str:
    return load_catalog(lang)[key].format(**params)


def language_names() -> dict[str, str]:
    """各语言的自称，供语言下拉框使用。"""
    return {lang: load_catalog(lang)["nav.language_name"] for lang in LANGUAGES}


def detect_system_language() -> str:
    if sys.platform == "win32":
        language_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return WINDOWS_LANGUAGES.get(language_id & 0x3FF, DEFAULT_LANGUAGE)
    return DEFAULT_LANGUAGE


def get_language(settings_path: Path) -> str:
    try:
        settings = settings_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return detect_system_language()
    language = json.loads(settings)["language"]
    # 其它版本保存的语言在本版本不存在时，按首次运行处理。
    return language if language in LANGUAGES else detect_system_language()


def set_language(settings_path: Path, lang: str) -> None:
    if lang not in LANGUAGES:
        raise ValueError(f"Unknown language: {lang}")
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({"language": lang}) + "\n", encoding="utf-8")
