"""Unit tests for eloquent_notes.i18n and all packaged gettext catalogs."""

import ast
import gettext
import glob
import os
import re
from datetime import date, datetime
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QLocale

from eloquent_notes import i18n
from eloquent_notes.config_gui.dialog import RESTORE_DEFAULTS_TITLE, ConfigurationDialog
from eloquent_notes.config_gui.tabs import text_files
from eloquent_notes.config_gui.tabs.ai import VALIDATION_ERROR_TITLE, AITab
from eloquent_notes.recording_hud import RecordingHUD
from eloquent_notes.window import (
    DICTATE_STATES,
    TYPE_LABELS,
    _TYPE_FILTER_LABELS,
    MainWindow,
    day_label,
    format_time,
)

EXPECTED_LOCALES = (
    "ar", "bg", "bn", "cs", "da", "de", "el", "es", "et", "fa",
    "fi", "fr", "he", "hi", "hr", "hu", "id", "it", "ja", "ko",
    "lt", "lv", "ms", "nl", "no", "pl", "pt", "ro", "ru", "sk",
    "sr", "sv", "th", "tl", "tr", "uk", "ur", "vi", "zh_CN", "zh_TW",
)

PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z0-9_]+\}")


@pytest.fixture(autouse=True)
def restore_english_locale():
    """Ensure every test starts and ends with the default English locale active."""
    i18n.load_translations(["en"])
    yield
    i18n.load_translations(["en"])


def _extract_codebase_msgids() -> tuple[set[str], set[tuple[str, str]]]:
    strings: set[str] = set()
    plurals: set[tuple[str, str]] = set()

    pkg_dir = os.path.dirname(os.path.abspath(i18n.__file__))
    for path in sorted(glob.glob(os.path.join(pkg_dir, "**", "*.py"), recursive=True)):
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "_" and node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        strings.add(arg.value)
                elif node.func.id == "ngettext" and len(node.args) >= 2:
                    a0, a1 = node.args[0], node.args[1]
                    if isinstance(a0, ast.Constant) and isinstance(a1, ast.Constant):
                        plurals.add((str(a0.value), str(a1.value)))

    for _color, label in DICTATE_STATES.values():
        strings.add(label)
    for label in TYPE_LABELS.values():
        strings.add(label)
    for _note_type, label in _TYPE_FILTER_LABELS:
        strings.add(label)
    strings.add(RESTORE_DEFAULTS_TITLE)
    strings.add(VALIDATION_ERROR_TITLE)
    for label, _path, _default in text_files.PROMPTS:
        strings.add(label)

    return strings, plurals


def test_detect_system_languages_posix_c(monkeypatch):
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.setenv("LANGUAGE", "es:fr")
    assert i18n.detect_system_languages() == ["en"]

    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.setenv("LC_MESSAGES", "POSIX")
    assert i18n.detect_system_languages() == ["en"]

    monkeypatch.delenv("LC_MESSAGES", raising=False)
    monkeypatch.setenv("LANG", "C.UTF-8")
    assert i18n.detect_system_languages() == ["en"]


def test_detect_system_languages_env_and_aliases(monkeypatch):
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("LANG", "es_ES.UTF-8@euro")
    assert i18n.detect_system_languages() == ["es_ES", "es"]

    monkeypatch.setenv("LANGUAGE", "nb_NO:zh_HK:fil_PH:C")
    monkeypatch.setenv("LANG", "iw_IL.UTF-8")
    langs = i18n.detect_system_languages()
    assert "no" in langs
    assert "zh_TW" in langs
    assert "tl" in langs
    assert "he" in langs


def test_detect_system_languages_falls_back_to_qlocale(monkeypatch):
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)

    fake_locale = QLocale(QLocale.Language.Russian, QLocale.Country.Russia)
    with patch("eloquent_notes.i18n.QLocale.system", return_value=fake_locale):
        assert i18n.detect_system_languages() == ["ru_RU", "ru"]

    c_locale = QLocale.c()
    with patch("eloquent_notes.i18n.QLocale.system", return_value=c_locale):
        assert i18n.detect_system_languages() == ["en"]


def test_detect_system_languages_posix_precedence(monkeypatch):
    monkeypatch.delenv("LANGUAGE", raising=False)
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    monkeypatch.setenv("LC_MESSAGES", "fr_FR.UTF-8")
    monkeypatch.setenv("LANG", "es_ES.UTF-8")
    assert i18n.detect_system_languages() == ["en_US", "en"]

    monkeypatch.delenv("LC_ALL", raising=False)
    assert i18n.detect_system_languages() == ["fr_FR", "fr"]


def test_load_translations_defaults_to_system_detection(monkeypatch):
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    monkeypatch.delenv("LANGUAGE", raising=False)
    monkeypatch.setenv("LANG", "es_ES.UTF-8")

    tr = i18n.load_translations()
    assert isinstance(tr, gettext.GNUTranslations)
    assert tr.info().get("language") == "es"
    assert i18n._("Settings") == "Ajustes"
    assert i18n.ui_locale().language() == QLocale.Language.Spanish


def test_load_translations_stops_at_english_before_later_languages(monkeypatch):
    monkeypatch.delenv("LANGUAGE", raising=False)
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    monkeypatch.setenv("LANG", "es_ES.UTF-8")

    tr = i18n.load_translations()
    assert type(tr) is gettext.NullTranslations
    assert i18n._("Settings") == "Settings"
    assert i18n.ui_locale() == i18n._EN_LOCALE

    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.setenv("LANGUAGE", "en:es")
    tr = i18n.load_translations()
    assert type(tr) is gettext.NullTranslations
    assert i18n._("Settings") == "Settings"
    assert i18n.ui_locale() == i18n._EN_LOCALE

    tr = i18n.load_translations(["en_US", "es"])
    assert type(tr) is gettext.NullTranslations
    assert i18n._("Settings") == "Settings"
    assert i18n.ui_locale() == i18n._EN_LOCALE

    tr = i18n.load_translations(["xx_YY", "en", "es"])
    assert type(tr) is gettext.NullTranslations
    assert i18n._("Settings") == "Settings"

    tr = i18n.load_translations(["es_ES", "en", "fr"])
    assert isinstance(tr, gettext.GNUTranslations)
    assert tr.info().get("language") == "es"


def test_all_40_catalogs_cover_every_codebase_string():
    msgids, plurals = _extract_codebase_msgids()
    assert len(msgids) == 173
    assert plurals == {("{count} result", "{count} results")}

    installed_locales = sorted(
        d for d in os.listdir(i18n.LOCALES_DIR)
        if os.path.isdir(os.path.join(i18n.LOCALES_DIR, d))
    )
    assert tuple(installed_locales) == EXPECTED_LOCALES

    for lang in EXPECTED_LOCALES:
        tr = i18n.load_translations([lang])
        assert isinstance(tr, gettext.GNUTranslations), f"Catalog failed to load for {lang}"
        assert tr.info().get("language") == lang

        for msgid in msgids:
            translated = i18n._(msgid)
            assert translated, f"Empty translation in {lang} for {msgid!r}"
            assert msgid in tr._catalog, f"Missing msgid in {lang} catalog: {msgid!r}"
            assert PLACEHOLDER_RE.findall(translated) or not PLACEHOLDER_RE.findall(msgid)
            assert set(PLACEHOLDER_RE.findall(translated)) == set(PLACEHOLDER_RE.findall(msgid)), (
                f"Placeholder mismatch in {lang} for {msgid!r}: {translated!r}"
            )

        for count in (0, 1, 2, 5, 11, 21, 100):
            rendered = i18n.ngettext("{count} result", "{count} results", count).format(count=count)
            assert str(count) in rendered


def test_ui_components_render_translated_strings(qapp):
    i18n.load_translations(["ru"])

    hud = RecordingHUD()
    assert hud.lbl_status.text() == i18n._("Recording Note...")
    assert hud.lbl_status.text() != "Recording Note..."
    hud.close()

    win = MainWindow()
    win.set_notes([])
    assert win.timeline.search.placeholderText() == i18n._("Search your notes by meaning…")
    assert win.reader.btn_dictate.text() == i18n._("Add dictation")
    win.close()

    today = date(2026, 10, 22)
    assert day_label(today, today) == i18n._("Today")
    assert day_label(date(2026, 10, 21), today) == i18n._("Yesterday")
    moment = datetime(2026, 10, 22, 21, 5).astimezone()
    assert format_time(moment, "HH:mm") == "21:05"

    with patch.object(AITab, "_fetch_models"):
        dialog = ConfigurationDialog()
    assert dialog.windowTitle() == i18n._("Eloquent Notes Configuration")
    assert dialog.btn_save.text() == i18n._("Save")
    dialog.close()
