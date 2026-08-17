"""Unit tests for ConfigurationDialog."""

from unittest.mock import mock_open, patch

import pytest
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QMessageBox

from eloquent_notes.config_gui.dialog import ConfigurationDialog
from eloquent_notes.config_gui.tabs.ai import AITab


@pytest.fixture(autouse=True)
def mock_fetch_models():
    """Autouse fixture to prevent network requests during dialog tests."""
    with patch.object(AITab, "_fetch_models"):
        yield


def _make_valid_config(overrides=None):
    base = {
        "ai": {
            "ollama_url": "http://localhost:11434",
            "model": "gemma4:e4b-it-qat",
            "output_language": "English",
            "context_length": 8192,
            "keep_alive": "0",
            "preload_keep_alive": "5m",
            "max_retries": 3,
            "preload_timeout": 180,
            "request_timeout": 300,
        },
        "audio": {
            "sample_rate": 16000,
            "channels": 1,
            "capture_duration": 30,
            "recording_hud_enabled": True,
            "beep_enabled": True,
            "beep_frequency": 440,
            "beep_duration": 0.1,
        },
        "logging": {
            "level": "INFO",
            "max_mb": 5,
            "backup_count": 3,
        },
        "obsidian": {
            "vault_path": "/tmp/vault",
            "folder": "Dictations",
            "folder_organization": "none",
            "daily_notes": True,
            "vault_context": True,
        },
    }
    if overrides:
        for section, sec_data in overrides.items():
            if isinstance(sec_data, dict) and section in base:
                base[section].update(sec_data)
            else:
                base[section] = sec_data
    return base


def test_dialog_init(qapp):
    dummy_config = _make_valid_config()

    with patch("eloquent_notes.config.load_config", return_value=dummy_config):
        dialog = ConfigurationDialog()

    assert dialog.tab_widget.count() == 6
    titles = [dialog.tab_widget.tabText(i) for i in range(6)]
    assert titles == [
        "General",
        "Obsidian",
        "AI Settings",
        "Audio",
        "Prompts",
        "Templates",
    ]
    dialog.cleanup_tabs()


def test_dialog_load_settings(qapp):
    dummy_config = _make_valid_config({
        "ai": {
            "ollama_url": "http://127.0.0.1:11434",
            "model": "whisper",
            "output_language": "Spanish",
            "context_length": 4096,
            "keep_alive": "10m",
            "preload_keep_alive": "2m",
            "max_retries": 5,
            "preload_timeout": 30,
            "request_timeout": 60,
        },
        "audio": {
            "sample_rate": 44100,
            "channels": 2,
            "capture_duration": 45,
            "beep_enabled": False,
            "beep_frequency": 800,
            "beep_duration": 0.2,
        },
        "logging": {"level": "DEBUG", "max_mb": 20, "backup_count": 2},
        "obsidian": {
            "vault_path": "/home/user/vault",
            "folder": "MyNotes",
            "folder_organization": "month",
            "daily_notes": False,
            "vault_context": False,
        },
    })

    with patch("eloquent_notes.config.load_config", return_value=dummy_config):
        dialog = ConfigurationDialog()

    assert dialog.ai_tab.txt_ollama_url.text() == "http://127.0.0.1:11434"
    assert dialog.ai_tab.cmb_model.currentText() == "whisper"
    assert dialog.ai_tab.cmb_language.currentText() == "Spanish"
    assert dialog.audio_tab.spn_sample_rate.value() == 44100
    assert dialog.general_tab.cmb_log_level.currentText() == "DEBUG"
    assert dialog.obsidian_tab.txt_vault_path.text() == "/home/user/vault"
    assert dialog.obsidian_tab.txt_obs_folder.text() == "MyNotes"
    assert dialog.obsidian_tab.cmb_folder_organization.currentData() == "month"

    dialog.cleanup_tabs()


def test_dialog_restore_defaults(qapp):
    dummy_config = _make_valid_config()
    with patch("eloquent_notes.config.load_config", return_value=dummy_config):
        dialog = ConfigurationDialog()

    # User declines prompt
    with patch("PyQt6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
        dialog.restore_defaults()

    # User accepts prompt
    default_data = _make_valid_config({
        "ai": {"ollama_url": "http://default:11434", "model": "def-model"},
        "obsidian": {"vault_path": "/default/vault"},
    })

    with patch("PyQt6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes), patch(
        "yaml.safe_load", return_value=default_data
    ), patch("builtins.open", mock_open(read_data="sample prompt text")), patch(
        "eloquent_notes.config.load_file", return_value="sample prompt text"
    ), patch("PyQt6.QtWidgets.QMessageBox.information"):
        dialog.restore_defaults()

    assert dialog.ai_tab.txt_ollama_url.text() == "http://default:11434"
    dialog.cleanup_tabs()


def test_dialog_save_settings(qapp):
    dummy_config = _make_valid_config()

    with patch("eloquent_notes.config.load_config", return_value=dummy_config), patch(
        "os.path.exists", return_value=True
    ):
        dialog = ConfigurationDialog()

    with patch("yaml.safe_load", return_value=dummy_config), patch(
        "builtins.open", mock_open(read_data="")
    ), patch("eloquent_notes.config.save_config") as mock_save, patch(
        "eloquent_notes.config.save_file"
    ), patch("os.path.exists", return_value=True), patch(
        "eloquent_notes.config_gui.tabs.general.install_autostart"
    ):
        res = dialog.save_settings_from_ui()
        assert res is True
        mock_save.assert_called_once()

    dialog.cleanup_tabs()


def test_dialog_save_validation_failure(qapp):
    dummy_config = _make_valid_config({"ai": {"ollama_url": ""}})

    with patch("eloquent_notes.config.load_config", return_value=dummy_config), patch(
        "os.path.exists", return_value=True
    ):
        dialog = ConfigurationDialog()

    dialog.ai_tab.txt_ollama_url.setText("")
    with patch("PyQt6.QtWidgets.QMessageBox.warning"), patch(
        "PyQt6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes
    ):
        res = dialog.save_settings_from_ui()
        assert res is False
        assert dialog.tab_widget.currentWidget() is dialog.ai_tab

    dialog.cleanup_tabs()


def test_dialog_cleanup_on_close(qapp):
    dummy_config = _make_valid_config()

    with patch("eloquent_notes.config.load_config", return_value=dummy_config):
        dialog = ConfigurationDialog()

    with patch.object(dialog, "cleanup_tabs") as mock_cleanup:
        dialog.reject()
        mock_cleanup.assert_called_once()

    with patch.object(dialog, "cleanup_tabs") as mock_cleanup, patch.object(
        dialog, "save_settings_from_ui", return_value=True
    ):
        dialog.accept()
        mock_cleanup.assert_called_once()

    with patch.object(dialog, "cleanup_tabs") as mock_cleanup:
        event = QCloseEvent()
        dialog.closeEvent(event)
        mock_cleanup.assert_called_once()
