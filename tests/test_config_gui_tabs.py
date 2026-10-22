"""Unit tests for configuration GUI tabs (AITab, AudioTab, GeneralTab, NotesTab, TextFilesTab)."""

import os
from unittest.mock import MagicMock, patch

from eloquent_notes.config_gui.tabs.ai import AITab
from eloquent_notes.config_gui.tabs.audio import AudioTab
from eloquent_notes.config_gui.tabs.general import GeneralTab
from eloquent_notes.config_gui.tabs.notes import NotesTab
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
        },
        "search": {"embedding_model": "embeddinggemma-2:latest", "keep_alive": "5m", "min_similarity": 0.3},
    }

    with patch.object(AITab, "_fetch_models"):
        tab.load_settings(config_data)

    assert tab.txt_ollama_url.text() == "http://localhost:11434/"
    assert tab.cmb_model.currentText() == "gemma"
    assert tab.cmb_language.currentText() == "French"
    assert tab.spn_context_length.value() == 8192
    assert not tab.chk_context_default.isChecked()
    assert tab.spn_preload_timeout.value() == 50
    assert tab.spn_request_timeout.value() == 100

    assert tab.cmb_embedding_model.currentText() == "embeddinggemma-2:latest"
    assert tab.spn_min_similarity.value() == 0.3

    tab.cmb_embedding_model.setCurrentText("other-embed")
    tab.spn_min_similarity.setValue(0.45)
    res = tab.save_settings(config_data)
    assert res is True
    assert config_data["ai"]["ollama_url"] == "http://localhost:11434"
    assert config_data["ai"]["keep_alive"] == "10m"
    assert config_data["ai"]["output_language"] == "French"
    assert config_data["search"] == {"embedding_model": "other-embed", "keep_alive": "5m", "min_similarity": 0.45}

    tab.cleanup()


def test_ai_tab_context_default_toggle(qapp):
    with patch.object(AITab, "_fetch_models"):
        tab = AITab()

    config_data = {
        "ai": {
            "ollama_url": "http://localhost:11434",
            "model": "gemma",
            "output_language": "English",
            "context_length": None,
            "keep_alive": "5m",
            "preload_keep_alive": "5m",
            "max_retries": 3,
            "preload_timeout": 60,
            "request_timeout": 120,
        },
        "search": {"embedding_model": "embeddinggemma-2:latest", "keep_alive": "5m", "min_similarity": 0.3},
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

    config_data = {
        "ai": {
            "ollama_url": "http://localhost:11434",
            "model": "gemma",
            "output_language": "English",
            "context_length": 8192,
            "keep_alive": "5m",
            "preload_keep_alive": "5m",
            "max_retries": 3,
            "preload_timeout": 60,
            "request_timeout": 120,
        },
        "search": {"embedding_model": "embeddinggemma-2:latest", "keep_alive": "5m", "min_similarity": 0.3},
    }
    with patch.object(AITab, "_fetch_models"):
        tab.load_settings(config_data)

    # Empty URL
    tab.txt_ollama_url.setText("")
    with patch("PyQt6.QtWidgets.QMessageBox.warning"):
        assert tab.save_settings(config_data) is False

    # Invalid URL scheme
    tab.txt_ollama_url.setText("localhost:11434")
    with patch("PyQt6.QtWidgets.QMessageBox.warning"):
        assert tab.save_settings(config_data) is False

    # Empty model
    tab.txt_ollama_url.setText("http://localhost:11434")
    tab.cmb_model.setCurrentText("   ")
    with patch("PyQt6.QtWidgets.QMessageBox.warning"):
        assert tab.save_settings(config_data) is False

    # Empty embedding model
    tab.cmb_model.setCurrentText("gemma")
    tab.cmb_embedding_model.setCurrentText("   ")
    with patch("PyQt6.QtWidgets.QMessageBox.warning"):
        assert tab.save_settings(config_data) is False

    # Empty output language
    tab.cmb_embedding_model.setCurrentText("embeddinggemma-2:latest")
    tab.cmb_language.setCurrentText("   ")
    with patch("PyQt6.QtWidgets.QMessageBox.warning"):
        assert tab.save_settings(config_data) is False

    # Invalid keep alive format
    tab.cmb_language.setCurrentText("English")
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
    tab._running_loaders.add(mock_loader)

    with patch.object(tab, "sender", return_value=mock_loader):
        tab._on_models_fetched(["model_a", "model_b"], ["embed_a"])
        assert tab.cmb_model.count() == 2
        assert tab.cmb_embedding_model.count() == 1
        assert tab.lbl_model_status.text() == "Models loaded successfully."

        # Unknown current selections are kept alongside the fetched models
        tab.cmb_model.setCurrentText("custom-model")
        tab._on_models_fetched([], ["embed_a"])
        assert tab.lbl_model_status.text() == "No audio-capable models found."
        assert tab.cmb_model.currentText() == "custom-model"

        tab._on_models_fetch_failed("Server error 500")
        assert "Connection failed: Server error 500" in tab.lbl_model_status.text()

    tab.cleanup()
    mock_loader.models_fetched.disconnect.assert_called_once_with(tab._on_models_fetched)
    mock_loader.error_occurred.disconnect.assert_called_once_with(tab._on_models_fetch_failed)
    mock_loader.finished.disconnect.assert_called_once_with(tab._on_loader_finished)
    mock_loader.requestInterruption.assert_called_once()
    mock_loader.wait.assert_called_once_with(2500)


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


def test_general_tab_autostart_removal(qapp):
    tab = GeneralTab()
    config_data = {
        "logging": {"level": "INFO", "max_mb": 5, "backup_count": 3}
    }

    with patch("os.path.exists", return_value=True):
        tab.load_settings(config_data)
    assert tab.chk_autostart.isChecked()

    tab.chk_autostart.setChecked(False)
    with patch("os.path.exists", return_value=True), patch("os.remove") as mock_remove:
        res = tab.save_settings(config_data)
        assert res is True
        mock_remove.assert_called_once()


def test_general_tab_view_log_file(qapp, tmp_path):
    tab = GeneralTab()
    log_dir = str(tmp_path / "logs")
    log_file = os.path.join(log_dir, "app.log")

    # Missing log file
    with patch("eloquent_notes.config_gui.tabs.general.get_log_file_path", return_value=log_file), patch(
        "PyQt6.QtWidgets.QMessageBox.information"
    ) as mock_info:
        tab._view_log_file()
        mock_info.assert_called_once()

    # Existing log file
    os.makedirs(log_dir, exist_ok=True)
    with open(log_file, "w") as f:
        f.write("Log line")

    with patch("eloquent_notes.config_gui.tabs.general.get_log_file_path", return_value=log_file), patch(
        "PyQt6.QtGui.QDesktopServices.openUrl"
    ) as mock_open:
        tab._view_log_file()
        mock_open.assert_called_once()


def test_general_tab_lowercase_log_level(qapp):
    tab = GeneralTab()
    config_data = {"logging": {"level": "debug", "max_mb": 5, "backup_count": 3}}
    tab.load_settings(config_data)
    assert tab.cmb_log_level.currentText() == "DEBUG"


# --- NOTES TAB TESTS ---

def test_notes_tab_load_and_save(qapp):
    tab = NotesTab()
    config_data = {"notes": {"folder": "~/Notes"}}

    tab.load_settings(config_data)
    assert tab.txt_folder.text() == "~/Notes"

    tab.txt_folder.setText("  ~/Voice Notes  ")
    assert tab.save_settings(config_data) is True
    assert config_data["notes"]["folder"] == "~/Voice Notes"


def test_notes_tab_rejects_empty_folder(qapp):
    tab = NotesTab()
    config_data = {"notes": {"folder": "~/Notes"}}
    tab.txt_folder.setText("  ")

    with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn:
        assert tab.save_settings(config_data) is False
    mock_warn.assert_called_once()
    assert config_data["notes"]["folder"] == "~/Notes"


def test_notes_tab_browse_folder(qapp, tmp_path):
    tab = NotesTab()
    tab.txt_folder.setText(str(tmp_path))

    with patch("PyQt6.QtWidgets.QFileDialog.getExistingDirectory", return_value="/selected/notes") as mock_dialog:
        tab._browse_folder()
    assert tab.txt_folder.text() == "/selected/notes"
    assert mock_dialog.call_args.args[2] == str(tmp_path)

    tab.txt_folder.setText("/nonexistent/folder")
    with patch("PyQt6.QtWidgets.QFileDialog.getExistingDirectory", return_value="") as mock_dialog:
        tab._browse_folder()
    assert tab.txt_folder.text() == "/nonexistent/folder"
    assert mock_dialog.call_args.args[2] == os.path.expanduser("~/")


# --- TEXT FILES TAB TESTS ---

def test_text_files_tab_flow(qapp, tmp_path):
    f1 = str(tmp_path / "prompt1.md")
    f2 = str(tmp_path / "prompt2.md")
    def1 = str(tmp_path / "def1.md")
    def2 = str(tmp_path / "def2.md")

    with open(f1, "w") as f:
        f.write("Custom Prompt 1")
    with open(def1, "w") as f:
        f.write("Default Prompt 1")
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
    with patch("eloquent_notes.config.atomic_write") as mock_write:
        tab.save_settings(config_data)
        assert mock_write.call_count == 2

    # Restore defaults
    tab.restore_defaults()
    assert tab.loaded_contents[f1] == "Default Prompt 1"
    assert tab.loaded_contents[f2] == "Default Prompt 2"


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
