"""Configuration GUI dialog for Eloquent Notes."""

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)
import yaml

from eloquent_notes import config
from eloquent_notes.config_gui.styles import QSS_STYLESHEET
from eloquent_notes.config_gui.tabs import (
    AITab,
    AudioTab,
    GeneralTab,
    ObsidianTab,
    PromptsTab,
    TemplatesTab,
)
from eloquent_notes.config_gui.utils import diff_configs


class ConfigurationDialog(QDialog):
    """Dialogue window for full application settings management."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Eloquent Notes Configuration")
        self.setMinimumSize(850, 650)
        self.config_data = config.load_config()

        self._tabs = []
        self._init_ui()
        self.load_settings_to_ui()

    def _init_ui(self):
        """Build the GUI widgets and apply the styling QSS."""
        self.setStyleSheet(QSS_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        self.tab_widget = QTabWidget()

        self.general_tab = GeneralTab()
        self.obsidian_tab = ObsidianTab()
        self.ai_tab = AITab()
        self.audio_tab = AudioTab()
        self.prompts_tab = PromptsTab()
        self.templates_tab = TemplatesTab()

        self._tabs = [
            (self.general_tab, "General"),
            (self.obsidian_tab, "Obsidian"),
            (self.ai_tab, "AI Settings"),
            (self.audio_tab, "Audio"),
            (self.prompts_tab, "Prompts"),
            (self.templates_tab, "Templates"),
        ]

        for tab_widget, title in self._tabs:
            self.tab_widget.addTab(tab_widget, title)

        layout.addWidget(self.tab_widget)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        self.btn_defaults = QPushButton("Restore Defaults")
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
            "Restore Defaults",
            "Are you sure you want to restore all configuration settings,"
            " prompts, and templates to their default values?\n\nThis will"
            " overwrite current edits.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            with open(config.DEFAULT_CONFIG_SRC, "r", encoding="utf-8") as f:
                default_data = yaml.safe_load(f) or {}

            # Load default data into UI
            for tab_widget, _ in self._tabs:
                tab_widget.load_settings(default_data)
                tab_widget.restore_defaults()

            QMessageBox.information(
                self,
                "Restore Defaults",
                "Defaults restored. Click 'Save' to apply changes to disk.",
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to restore defaults: {e}"
            )

    def save_settings_from_ui(self):
        """Gather settings from widgets and persist them to files on disk."""
        try:
            # Collect from all tabs inside try-except to catch OS/File errors
            for tab_widget, title in self._tabs:
                if not tab_widget.save_settings(self.config_data):
                    # A tab returned False, meaning validation failed
                    self.tab_widget.setCurrentWidget(tab_widget)
                    return False

            with open(config.DEFAULT_CONFIG_SRC, "r", encoding="utf-8") as f:
                default_config = yaml.safe_load(f) or {}

            overrides = diff_configs(default_config, self.config_data)
            config.save_config(overrides)

            return True
        except Exception as e:
            QMessageBox.critical(
                self, "Save Error", f"Failed to save settings: {e}"
            )
            return False

    def cleanup_tabs(self):
        """Clean up resources before closing."""
        for tab_widget, _ in self._tabs:
            tab_widget.cleanup()

    def reject(self):
        """Cancel changes and close, ensuring threads are stopped."""
        self.cleanup_tabs()
        super().reject()

    def accept(self):
        """Save settings and close the dialog with Accepted code, ensuring threads are stopped."""
        if self.save_settings_from_ui():
            self.cleanup_tabs()
            super().accept()
