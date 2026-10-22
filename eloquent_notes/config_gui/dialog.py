"""Configuration GUI dialog for Eloquent Notes."""

import yaml
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)

from eloquent_notes import config
from eloquent_notes.config_gui.constants import PROMPTS
from eloquent_notes.config_gui.tabs import (
    AITab,
    AudioTab,
    GeneralTab,
    NotesTab,
    TextFilesTab,
)
from eloquent_notes.config_gui.utils import diff_configs

RESTORE_DEFAULTS_TITLE = "Restore Defaults"


class ConfigurationDialog(QDialog):
    """Dialogue window for full application settings management."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Eloquent Notes Configuration")
        self.setMinimumSize(850, 650)
        try:
            self.config_data = config.load_config()
        except (OSError, yaml.YAMLError, TypeError) as e:
            QMessageBox.warning(
                self,
                "Configuration Error",
                f"Failed to load user configuration: {e}\n\nLoaded default settings.",
            )
            self.config_data = config.load_default_config()

        self._tabs = []
        self._init_ui()
        self.load_settings_to_ui()

    def _init_ui(self):
        """Build the GUI widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        self.tab_widget = QTabWidget()

        self.general_tab = GeneralTab()
        self.notes_tab = NotesTab()
        self.ai_tab = AITab()
        self.audio_tab = AudioTab()
        self.prompts_tab = TextFilesTab(
            PROMPTS, "Prompt Content:", "Select a prompt to edit..."
        )

        self._tabs = [
            (self.general_tab, "General"),
            (self.notes_tab, "Notes"),
            (self.ai_tab, "AI Settings"),
            (self.audio_tab, "Audio"),
            (self.prompts_tab, "Prompts"),
        ]

        for tab_widget, title in self._tabs:
            self.tab_widget.addTab(tab_widget, title)

        layout.addWidget(self.tab_widget)

        btn_layout = QHBoxLayout()
        self.btn_defaults = QPushButton(RESTORE_DEFAULTS_TITLE)
        self.btn_defaults.clicked.connect(self.restore_defaults)
        btn_layout.addWidget(self.btn_defaults)

        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save")
        self.btn_save.setObjectName("btnSave")
        self.btn_save.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

    def load_settings_to_ui(self):
        """Populate widget states from loaded configuration dict."""
        for tab_widget, _ in self._tabs:
            tab_widget.load_settings(self.config_data)

    def restore_defaults(self):
        """Overwrite current edits with factory defaults after confirmation."""
        confirm = QMessageBox.question(
            self,
            RESTORE_DEFAULTS_TITLE,
            "Are you sure you want to restore all configuration settings,"
            " and prompts to their default values?\n\nThis will"
            " overwrite current edits.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            default_data = config.load_default_config()
            self.config_data = default_data

            for tab_widget in (
                self.general_tab,
                self.notes_tab,
                self.ai_tab,
                self.audio_tab,
            ):
                tab_widget.load_settings(default_data)

            self.prompts_tab.restore_defaults()

            QMessageBox.information(
                self,
                RESTORE_DEFAULTS_TITLE,
                "Defaults restored. Click 'Save' to apply changes to disk.",
            )
        except (OSError, yaml.YAMLError) as e:
            QMessageBox.critical(
                self, "Error", f"Failed to restore defaults: {e}"
            )

    def save_settings_from_ui(self):
        """Gather settings from widgets and persist them to files on disk."""
        save_order = (
            self.notes_tab,
            self.ai_tab,
            self.audio_tab,
            self.general_tab,
            self.prompts_tab,
        )
        try:
            for tab_widget in save_order:
                if not tab_widget.save_settings(self.config_data):
                    self.tab_widget.setCurrentWidget(tab_widget)
                    return False

            default_config = config.load_default_config()
            overrides = diff_configs(default_config, self.config_data)
            config.save_config(overrides)
        except (OSError, yaml.YAMLError) as e:
            QMessageBox.critical(
                self, "Save Error", f"Failed to save settings: {e}"
            )
            return False
        else:
            return True

    def cleanup_tabs(self):
        """Clean up resources before closing."""
        self.ai_tab.cleanup()

    def closeEvent(self, event):
        """Ensure background threads and resources are cleaned up on window close."""
        if not self.isVisible():
            self.cleanup_tabs()
        super().closeEvent(event)

    def reject(self):
        """Cancel changes and close, ensuring threads are stopped."""
        self.cleanup_tabs()
        super().reject()

    def accept(self):
        """Save settings and close the dialog with Accepted code, ensuring threads are stopped."""
        if self.save_settings_from_ui():
            self.cleanup_tabs()
            super().accept()

