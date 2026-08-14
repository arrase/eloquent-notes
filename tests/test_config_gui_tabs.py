"""Unit tests for configuration GUI tabs (AITab, AudioTab, GeneralTab, ObsidianTab, TextFilesTab, PromptsTab, TemplatesTab)."""

from unittest.mock import MagicMock, patch
import os
import pytest
from PyQt6.QtWidgets import QMessageBox

from eloquent_notes.config_gui.tabs.ai import AITab
from eloquent_notes.config_gui.tabs.audio import AudioTab
from eloquent_notes.config_gui.tabs.general import GeneralTab
from eloquent_notes.config_gui.tabs.obsidian import ObsidianTab
from eloquent_notes.config_gui.tabs.prompts import PromptsTab
from eloquent_notes.config_gui.tabs.templates import TemplatesTab
from eloquent_notes.config_gui.tabs.text_files import TextFilesTab


# --- AI TAB TESTS ---

def test_ai_tab_load_and_save_valid(qapp):
    with patch.object(AITab, "_fetch_models"):
        tab = AITab()

    config_data = {
        "ai": {
            "ollama_url": "http://localhost:11434/",
            "model": "gemma",
            "output_language": "French",
            "context_length": 8192,
            "keep_alive": "10m",
            "preload_keep_alive": "5m",
            "max_retries": 4,
            "preload_timeout": 50,
            "request_timeout": 100,
        }
    }

    with patch.object(AITab, "_fetch_models"):
        tab.load_settings(config_data)

    assert tab.txt_ollama_url.text() == "http://localhost:11434/"
    assert tab.cmb_model.currentText() == "gemma"
    assert tab.cmb_language.currentText() == "French"
    assert tab.spn_context_length.value() == 8192
    assert not tab.chk_context_default.isChecked()

    res = tab.save_settings(config_data)
    assert res is True
    assert config_data["ai"]["ollama_url"] == "http://localhost:11434"
    assert config_data["ai"]["keep_alive"] == "10m"
    assert config_data["ai"]["output_language"] == "French"

    tab.cleanup()


def test_ai_tab_load_missing_or_invalid_fields(qapp):
    with patch.object(AITab, "_fetch_models"):
        tab = AITab()

    config_data = {
        "ai": {
            "context_length": "invalid_int",
            "max_retries": "invalid_int",
            "preload_timeout": "invalid_int",
            "request_timeout": "invalid_int",
        }
    }

    with patch.object(AITab, "_fetch_models"):
        tab.load_settings(config_data)

    assert tab.spn_context_length.value() == 8192
    assert tab.spn_max_retries.value() == 3
    assert tab.spn_preload_timeout.value() == 60
    assert tab.spn_request_timeout.value() == 120

    tab.cleanup()


def test_ai_tab_context_default_toggle(qapp):
    with patch.object(AITab, "_fetch_models"):
        tab = AITab()

    config_data = {
        "ai": {
            "ollama_url": "http://localhost:11434",
            "model": "gemma",
            "context_length": None,
            "keep_alive": "5m",
            "preload_keep_alive": "5m",
        }
    }

    with patch.object(AITab, "_fetch_models"):
        tab.load_settings(config_data)

    assert tab.chk_context_default.isChecked()
    assert not tab.spn_context_length.isEnabled()

    tab.save_settings(config_data)
    assert config_data["ai"]["context_length"] is None

    tab.chk_context_default.setChecked(False)
    assert tab.spn_context_length.isEnabled()

    tab.cleanup()


def test_ai_tab_save_validation_failures(qapp):
    with patch.object(AITab, "_fetch_models"):
        tab = AITab()

    config_data = {"ai": {}}
    tab.load_settings(config_data)

    # Empty URL
    tab.txt_ollama_url.setText("")
    with patch("PyQt6.QtWidgets.QMessageBox.warning"):
        assert tab.save_settings(config_data) is False

    # Invalid keep alive format
    tab.txt_ollama_url.setText("http://localhost:11434")
    tab.txt_keep_alive.setText("invalid_duration")
    with patch("PyQt6.QtWidgets.QMessageBox.warning"):
        assert tab.save_settings(config_data) is False

    # Invalid preload keep alive format
    tab.txt_keep_alive.setText("5m")
    tab.txt_preload_keep_alive.setText("invalid_preload")
    with patch("PyQt6.QtWidgets.QMessageBox.warning"):
        assert tab.save_settings(config_data) is False

    tab.cleanup()


def test_ai_tab_model_loader_callbacks(qapp):
    with patch.object(AITab, "_fetch_models"):
        tab = AITab()

    # Mock running loader
    mock_loader = MagicMock()
    tab._model_loader = mock_loader

    with patch.object(tab, "sender", return_value=mock_loader):
        tab._on_models_fetched(["model_a", "model_b"])
        assert tab.cmb_model.count() == 2
        assert tab.lbl_model_status.text() == "Audio models loaded successfully."

        tab._on_models_fetch_failed("Server error 500")
        assert "Connection failed: Server error 500" in tab.lbl_model_status.text()

    tab.cleanup()


# --- AUDIO TAB TESTS ---

def test_audio_tab_load_and_save(qapp):
    tab = AudioTab()
    config_data = {
        "audio": {
            "sample_rate": 48000,
            "channels": 2,
            "capture_duration": 45,
            "recording_hud_enabled": False,
            "beep_enabled": False,
            "beep_frequency": 1200,
            "beep_duration": 0.25,
        }
    }

    tab.load_settings(config_data)
    assert tab.spn_sample_rate.value() == 48000
    assert tab.cmb_channels.currentIndex() == 1
    assert tab.spn_capture_duration.value() == 45
    assert not tab.chk_recording_hud_enabled.isChecked()
    assert not tab.chk_beep_enabled.isChecked()
    assert tab.spn_beep_freq.value() == 1200
    assert tab.spn_beep_duration.value() == 0.25

    res = tab.save_settings(config_data)
    assert res is True
    assert config_data["audio"]["channels"] == 2
    assert config_data["audio"]["capture_duration"] == 45
    assert config_data["audio"]["recording_hud_enabled"] is False
    assert config_data["audio"]["beep_enabled"] is False


def test_audio_tab_invalid_config_fallback(qapp):
    tab = AudioTab()
    config_data = {
        "audio": {
            "sample_rate": "bad_val",
            "capture_duration": "bad_val",
            "beep_frequency": "bad_val",
            "beep_duration": "bad_val",
        }
    }
    tab.load_settings(config_data)
    assert tab.spn_sample_rate.value() == 16000
    assert tab.spn_capture_duration.value() == 30
    assert tab.chk_recording_hud_enabled.isChecked()
    assert tab.spn_beep_freq.value() == 1000
    assert tab.spn_beep_duration.value() == 0.1


# --- GENERAL TAB TESTS ---

def test_general_tab_load_and_save(qapp):
    tab = GeneralTab()
    config_data = {
        "logging": {"level": "WARNING", "max_mb": 15, "backup_count": 3}
    }

    with patch("os.path.exists", return_value=False):
        tab.load_settings(config_data)

    assert tab.cmb_log_level.currentText() == "WARNING"
    assert tab.spn_log_max_mb.value() == 15
    assert tab.spn_log_backups.value() == 3

    tab.chk_autostart.setChecked(True)
    with patch("eloquent_notes.config_gui.tabs.general.install_autostart") as mock_install:
        res = tab.save_settings(config_data)
        assert res is True
        mock_install.assert_called_once()
        assert config_data["logging"]["level"] == "WARNING"


def test_general_tab_view_log_file(qapp, tmp_path):
    tab = GeneralTab()
    log_dir = str(tmp_path / "logs")
    log_file = os.path.join(log_dir, "app.log")

    # Missing log file
    with patch("eloquent_notes.config_gui.tabs.general.get_log_dir", return_value=log_dir), patch(
        "PyQt6.QtWidgets.QMessageBox.information"
    ) as mock_info:
        tab._view_log_file()
        mock_info.assert_called_once()

    # Existing log file
    os.makedirs(log_dir, exist_ok=True)
    with open(log_file, "w") as f:
        f.write("Log line")

    with patch("eloquent_notes.config_gui.tabs.general.get_log_dir", return_value=log_dir), patch(
        "PyQt6.QtGui.QDesktopServices.openUrl"
    ) as mock_open:
        tab._view_log_file()
        mock_open.assert_called_once()


# --- OBSIDIAN TAB TESTS ---

def test_obsidian_tab_load_and_save(qapp, tmp_path):
    tab = ObsidianTab()
    vault_dir = str(tmp_path / "MyVault")
    os.makedirs(vault_dir, exist_ok=True)

    config_data = {
        "obsidian": {
            "vault_path": vault_dir,
            "folder": "Daily",
            "daily_notes": True,
            "vault_context": True,
        }
    }

    tab.load_settings(config_data)
    assert tab.txt_vault_path.text() == vault_dir
    assert tab.txt_obs_folder.text() == "Daily"
    assert tab.chk_daily_notes.isChecked()
    assert tab.chk_vault_context.isChecked()

    res = tab.save_settings(config_data)
    assert res is True
    assert config_data["obsidian"]["folder"] == "Daily"


def test_obsidian_tab_empty_and_nonexistent_vault(qapp):
    tab = ObsidianTab()
    config_data = {"obsidian": {}}

    tab.txt_vault_path.setText("")
    with patch("PyQt6.QtWidgets.QMessageBox.warning"):
        assert tab.save_settings(config_data) is False

    tab.txt_vault_path.setText("/nonexistent/vault/path")
    with patch("PyQt6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
        assert tab.save_settings(config_data) is False


def test_obsidian_tab_browse_vault(qapp, tmp_path):
    tab = ObsidianTab()
    tab.txt_vault_path.setText(str(tmp_path))

    with patch("PyQt6.QtWidgets.QFileDialog.getExistingDirectory", return_value="/selected/vault"):
        tab._browse_vault_path()
        assert tab.txt_vault_path.text() == "/selected/vault"


# --- TEXT FILES / PROMPTS / TEMPLATES TAB TESTS ---

def test_text_files_tab_flow(qapp, tmp_path):
    f1 = str(tmp_path / "prompt1.md")
    f2 = str(tmp_path / "prompt2.md")
    def1 = str(tmp_path / "def1.md")
    def2 = str(tmp_path / "def2.md")

    with open(f1, "w") as f:
        f.write("Custom Prompt 1")
    with open(def2, "w") as f:
        f.write("Default Prompt 2")

    items = [("Prompt 1", f1, def1), ("Prompt 2", f2, def2)]
    tab = TextFilesTab(items, "Edit Prompt:", "Select item...")

    config_data = {}
    tab.load_settings(config_data)

    assert tab.lst_items.count() == 2
    assert tab.loaded_contents[f1] == "Custom Prompt 1"
    assert tab.loaded_contents[f2] == "Default Prompt 2"

    # Select item 0
    tab.lst_items.setCurrentRow(0)
    assert tab.editor.toPlainText() == "Custom Prompt 1"

    # Edit text
    tab.editor.setPlainText("Modified Prompt 1")
    tab.commit_active_editor()
    assert tab.loaded_contents[f1] == "Modified Prompt 1"

    # Save settings writes file
    with patch("eloquent_notes.config.save_file") as mock_save:
        tab.save_settings(config_data)
        assert mock_save.call_count == 2

    # Restore defaults
    tab.restore_defaults()
    assert tab.loaded_contents[f1] == ""
    assert tab.loaded_contents[f2] == "Default Prompt 2"


def test_prompts_and_templates_tabs_init(qapp):
    p_tab = PromptsTab()
    assert p_tab.lst_items.count() > 0

    t_tab = TemplatesTab()
    assert t_tab.lst_items.count() > 0


def test_text_files_tab_load_settings_row0_already_selected(qapp, tmp_path):
    f1 = str(tmp_path / "prompt1.md")
    with open(f1, "w") as f:
        f.write("Initial Text")

    items = [("Prompt 1", f1, f1)]
    tab = TextFilesTab(items, "Edit Prompt:", "Select item...")
    tab.load_settings({})
    assert tab.lst_items.currentRow() == 0
    assert tab.editor.toPlainText() == "Initial Text"

    # User modifies text in editor
    tab.editor.setPlainText("Unsaved Dirty Edits")

    # Reload settings while row 0 is already selected
    with open(f1, "w") as f:
        f.write("Updated Disk Text")

    tab.load_settings({})
    assert tab.editor.toPlainText() == "Updated Disk Text"


def test_tabs_handle_none_config_sections(qapp, tmp_path):
    config_data = {
        "logging": None,
        "audio": None,
        "obsidian": None,
        "ai": None,
    }

    gen_tab = GeneralTab()
    gen_tab.load_settings(config_data)
    assert gen_tab.save_settings(config_data) is True

    aud_tab = AudioTab()
    aud_tab.load_settings(config_data)
    assert aud_tab.save_settings(config_data) is True

    obs_tab = ObsidianTab()
    vault_dir = str(tmp_path / "Vault")
    os.makedirs(vault_dir, exist_ok=True)
    obs_tab.txt_vault_path.setText(vault_dir)
    obs_tab.load_settings(config_data)
    obs_tab.txt_vault_path.setText(vault_dir)
    assert obs_tab.save_settings(config_data) is True

    with patch.object(AITab, "_fetch_models"):
        ai_tab = AITab()
        ai_tab.load_settings(config_data)
        assert ai_tab.save_settings(config_data) is True
        ai_tab.cleanup()


def test_general_tab_lowercase_log_level(qapp):
    tab = GeneralTab()
    config_data = {"logging": {"level": "debug"}}
    tab.load_settings(config_data)
    assert tab.cmb_log_level.currentText() == "DEBUG"

