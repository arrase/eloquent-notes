"""Internationalization (i18n) support using standard gettext catalogs."""

import gettext
import os
from pathlib import Path

from PyQt6.QtCore import QLocale

DOMAIN = "eloquent_notes"
LOCALES_DIR = str(Path(__file__).resolve().parent / "locales")

_EN_LOCALE = QLocale(QLocale.Language.English, QLocale.Country.UnitedKingdom)

_LANGUAGE_ALIASES = {
    "nb": "no",
    "nn": "no",
    "zh": "zh_CN",
    "zh_hans": "zh_CN",
    "zh_sg": "zh_CN",
    "zh_hant": "zh_TW",
    "zh_hk": "zh_TW",
    "zh_mo": "zh_TW",
    "fil": "tl",
    "iw": "he",
    "in": "id",
}

OUTPUT_LANGUAGES = [
    "English",
    "Arabic",
    "Bengali",
    "Bulgarian",
    "Chinese (Simplified)",
    "Chinese (Traditional)",
    "Croatian",
    "Czech",
    "Danish",
    "Dutch",
    "Estonian",
    "Filipino",
    "Finnish",
    "French",
    "German",
    "Greek",
    "Hebrew",
    "Hindi",
    "Hungarian",
    "Indonesian",
    "Italian",
    "Japanese",
    "Korean",
    "Latvian",
    "Lithuanian",
    "Malay",
    "Norwegian",
    "Persian",
    "Polish",
    "Portuguese",
    "Romanian",
    "Russian",
    "Serbian",
    "Slovak",
    "Spanish",
    "Swedish",
    "Thai",
    "Turkish",
    "Ukrainian",
    "Urdu",
    "Vietnamese",
]


def _expand_tag(raw: str) -> list[str]:
    base = raw.split(".", maxsplit=1)[0].split("@", maxsplit=1)[0].replace("-", "_").strip()
    if not base or base.upper() in ("C", "POSIX"):
        return []
    lang = base.split("_", maxsplit=1)[0].lower()
    candidates: list[str] = []
    for candidate in (
        _LANGUAGE_ALIASES.get(base.lower()),
        base,
        _LANGUAGE_ALIASES.get(lang),
        lang,
    ):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _env_locale() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    return ""


def detect_system_languages() -> list[str]:
    """Return ordered gettext language codes detected from the system environment."""
    locale_val = _env_locale()
    if locale_val.split(".", maxsplit=1)[0].upper() in ("C", "POSIX"):
        return ["en"]

    raw_tags: list[str] = []
    language_env = os.environ.get("LANGUAGE", "").strip()
    if language_env:
        raw_tags.extend(language_env.split(":"))
    if locale_val:
        raw_tags.append(locale_val)

    if not raw_tags:
        raw_tags.append(QLocale.system().name())

    languages: list[str] = []
    for raw in raw_tags:
        for tag in _expand_tag(raw):
            if tag not in languages:
                languages.append(tag)
    return languages or ["en"]


_translation: gettext.NullTranslations = gettext.NullTranslations()
_ui_locale: QLocale = _EN_LOCALE


def load_translations(languages: list[str] | None = None) -> gettext.NullTranslations:
    """Load the gettext catalog for the given languages or the system locale."""
    global _translation, _ui_locale
    raw_langs = detect_system_languages() if languages is None else languages
    langs = [tag for raw in raw_langs for tag in _expand_tag(raw)]
    if "en" in langs:
        langs = langs[: langs.index("en")]
    _translation = gettext.translation(
        DOMAIN,
        localedir=LOCALES_DIR,
        languages=langs,
        fallback=True,
    )
    active_lang = _translation.info().get("language")
    _ui_locale = QLocale(active_lang) if active_lang else _EN_LOCALE
    return _translation


def _(message: str) -> str:
    """Translate a singular UI string."""
    return _translation.gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    """Translate a singular/plural UI string according to count n."""
    return _translation.ngettext(singular, plural, n)


def ui_locale() -> QLocale:
    """Return the QLocale matching the active UI translation."""
    return _ui_locale


load_translations()
