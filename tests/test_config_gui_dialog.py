"""Unit tests for ConfigurationDialog."""

from unittest.mock import patch

import pytest
import yaml
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QMessageBox

from eloquent_notes import config, ui
from eloquent_notes.config_gui.dialog import ConfigurationDialog
from eloquent_notes.config_gui.tabs.ai import AITab


@pytest.fixture(autouse=True)
def mock_fetch_models():
    """Autouse fixture to prevent network requests during dialog tests."""
    with patch.object(AITab, "_fetch_models"):
        yield


def test_dialog_init(qapp):
    dummy_config = config.load_default_config()

    with patch("eloquent_notes.config.load_config", return_value=dummy_config):
        dialog = ConfigurationDialog()

    assert dialog.tab_widget.count() == 6
    titles = [dialog.tab_widget.tabText(i) for i in range(6)]
    assert titles == [
        "General",
        "Notes",
        "Appearance",
        "AI Settings",
        "Audio",
        "Prompts",
    ]
    assert dialog.styleSheet() == ui.dialog_stylesheet(ui.current_theme())
    assert not dialog.windowIcon().isNull()


def test_dialog_palette_change_updates_stylesheet(qapp):
    dummy_config = config.load_default_config()

    with (
        patch("eloquent_notes.config.load_config", return_value=dummy_config),
        patch("eloquent_notes.ui.is_dark_theme", return_value=False),
    ):
        dialog = ConfigurationDialog()

    assert dialog.styleSheet() == ui.dialog_stylesheet(ui.LIGHT_THEME)

    with patch("eloquent_notes.ui.is_dark_theme", return_value=True):
        dialog.changeEvent(QEvent(QEvent.Type.PaletteChange))

    assert dialog.styleSheet() == ui.dialog_stylesheet(ui.DARK_THEME)


def test_dialog_init_falls_back_to_default_on_corrupt_config(qapp):
    default_config = config.load_default_config()

    with (
        patch(
            "eloquent_notes.config.load_config",
            side_effect=yaml.YAMLError("Corrupt YAML"),
        ),
        patch(
            "eloquent_notes.config.load_default_config",
            return_value=default_config,
        ),
        patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn,
    ):
        dialog = ConfigurationDialog()

    mock_warn.assert_called_once()
    assert dialog.config_data == default_config


def test_dialog_load_settings(qapp):
    dummy_config = config.load_default_config()
    dummy_config["ai"].update(
        {
            "ollama_url": "http://127.0.0.1:11434",
            "model": "gemma4:e4b",
            "output_language": "Spanish",
            "context_length": 4096,
            "keep_alive": "10m",
            "preload_keep_alive": "2m",
            "max_retries": 5,
            "preload_timeout": 30,
            "request_timeout": 60,
        }
    )
    dummy_config["audio"].update(
        {
            "sample_rate": 44100,
            "channels": 2,
            "capture_duration": 45,
            "beep_enabled": False,
            "beep_frequency": 800,
            "beep_duration": 0.2,
        }
    )
    dummy_config["logging"].update({"level": "DEBUG", "max_mb": 20, "backup_count": 2})
    dummy_config["notes"]["folder"] = "/home/user/notes"
    dummy_config["notes"]["columns"] = 3
    dummy_config["notes"]["type_colors"]["idea"] = "#112233"
    dummy_config["search"].update({"embedding_model": "my-embed", "keep_alive": "15m", "min_similarity": 0.5})

    with patch("eloquent_notes.config.load_config", return_value=dummy_config):
        dialog = ConfigurationDialog()

    assert dialog.ai_tab.txt_ollama_url.text() == "http://127.0.0.1:11434"
    assert dialog.ai_tab.cmb_model.currentText() == "gemma4:e4b"
    assert dialog.ai_tab.cmb_language.currentText() == "Spanish"
    assert dialog.audio_tab.spn_sample_rate.value() == 44100
    assert dialog.general_tab.cmb_log_level.currentText() == "DEBUG"
    assert dialog.notes_tab.txt_folder.text() == "/home/user/notes"
    assert dialog.appearance_tab.spn_columns.value() == 3
    assert dialog.appearance_tab.color_buttons["idea"].text() == "#112233"
    assert dialog.ai_tab.cmb_embedding_model.currentText() == "my-embed"
    assert dialog.ai_tab.txt_search_keep_alive.text() == "15m"
    assert dialog.ai_tab.spn_min_similarity.value() == 0.5


def test_dialog_restore_defaults(qapp):
    dummy_config = config.load_default_config()
    with patch("eloquent_notes.config.load_config", return_value=dummy_config):
        dialog = ConfigurationDialog()

    dialog.general_tab.chk_autostart.setChecked(True)
    dialog.appearance_tab.spn_columns.setValue(4)

    # User declines prompt
    with patch("PyQt6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
        dialog.restore_defaults()
    assert dialog.general_tab.chk_autostart.isChecked() is True

    # User accepts prompt
    default_data = config.load_default_config()
    default_data["ai"]["ollama_url"] = "http://default:11434"
    default_data["notes"]["folder"] = "/default/notes"

    with (
        patch("PyQt6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes),
        patch("eloquent_notes.config.load_default_config", return_value=default_data),
        patch("eloquent_notes.config.load_file", return_value="sample prompt text"),
        patch("eloquent_notes.config_gui.tabs.general.is_autostart_enabled", return_value=True),
        patch("PyQt6.QtWidgets.QMessageBox.information"),
    ):
        dialog.restore_defaults()

    assert dialog.ai_tab.txt_ollama_url.text() == "http://default:11434"
    assert dialog.notes_tab.txt_folder.text() == "/default/notes"
    assert dialog.appearance_tab.spn_columns.value() == 2
    assert dialog.appearance_tab.color_buttons["idea"].text() == ui.DEFAULT_TYPE_COLORS["idea"]
    assert dialog.general_tab.chk_autostart.isChecked() is False


def test_dialog_save_settings(qapp):
    dummy_config = config.load_default_config()

    with (
        patch("eloquent_notes.config.load_config", return_value=dummy_config),
        patch("eloquent_notes.config.load_file", return_value=""),
        patch("pathlib.Path.exists", return_value=True),
    ):
        dialog = ConfigurationDialog()

    with (
        patch("eloquent_notes.config.load_default_config", return_value=dummy_config),
        patch("eloquent_notes.config.save_config") as mock_save,
        patch("eloquent_notes.config.atomic_write"),
        patch("eloquent_notes.config.load_file", return_value=""),
        patch("pathlib.Path.exists", return_value=True),
        patch("eloquent_notes.config_gui.tabs.general.install_autostart"),
    ):
        res = dialog.save_settings_from_ui()
        assert res is True
        mock_save.assert_called_once()

    with (
        patch("eloquent_notes.config.load_default_config", return_value=dummy_config),
        patch("eloquent_notes.config.save_config", side_effect=OSError("disk full")),
        patch("eloquent_notes.config.load_file", return_value=""),
        patch("pathlib.Path.exists", return_value=True),
        patch("eloquent_notes.config_gui.tabs.general.install_autostart"),
        patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_crit,
    ):
        assert dialog.save_settings_from_ui() is False
        mock_crit.assert_called_once()


def test_dialog_save_validation_failure_does_not_mutate_disk(qapp):
    dummy_config = config.load_default_config()

    with (
        patch("eloquent_notes.config.load_config", return_value=dummy_config),
        patch("eloquent_notes.config.load_file", return_value=""),
        patch("pathlib.Path.exists", return_value=True),
    ):
        dialog = ConfigurationDialog()

    original_folder = dialog.config_data["notes"]["folder"]
    original_columns = dialog.config_data["notes"]["columns"]

    dialog.notes_tab.txt_folder.setText("/mutated/folder")
    dialog.appearance_tab.spn_columns.setValue(5)
    dialog.ai_tab.txt_ollama_url.setText("")
    with (
        patch("PyQt6.QtWidgets.QMessageBox.warning"),
        patch("eloquent_notes.config_gui.tabs.general.install_autostart") as mock_install,
        patch("eloquent_notes.config_gui.tabs.general.remove_autostart") as mock_remove,
        patch("eloquent_notes.config.atomic_write") as mock_write,
    ):
        res = dialog.save_settings_from_ui()
        assert res is False
        assert dialog.tab_widget.currentWidget() is dialog.ai_tab
        assert dialog.config_data["notes"]["folder"] == original_folder
        assert dialog.config_data["notes"]["columns"] == original_columns
        mock_install.assert_not_called()
        mock_remove.assert_not_called()
        mock_write.assert_not_called()


def test_dialog_accept(qapp):
    dummy_config = config.load_default_config()

    with patch("eloquent_notes.config.load_config", return_value=dummy_config):
        dialog = ConfigurationDialog()

    with patch.object(dialog, "save_settings_from_ui", return_value=False):
        dialog.accept()
        assert dialog.result() != ConfigurationDialog.DialogCode.Accepted

    with patch.object(dialog, "save_settings_from_ui", return_value=True):
        dialog.accept()
        assert dialog.result() == ConfigurationDialog.DialogCode.Accepted
