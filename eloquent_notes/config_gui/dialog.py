"""Configuration GUI dialog for Eloquent Notes."""

import copy

import yaml
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)

from eloquent_notes import config, ui
from eloquent_notes.config import diff_configs
from eloquent_notes.config_gui.tabs import (
    AITab,
    AppearanceTab,
    AudioTab,
    GeneralTab,
    NotesTab,
    TextFilesTab,
)
from eloquent_notes.i18n import _

RESTORE_DEFAULTS_TITLE = "Restore Defaults"


class ConfigurationDialog(QDialog):
    """Dialogue window for full application settings management."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(_("Eloquent Notes Configuration"))
        self.setWindowIcon(ui.get_app_icon())
        self.setMinimumSize(850, 700)
        self._dark = ui.is_dark_theme()
        self.setStyleSheet(ui.dialog_stylesheet(ui.current_theme()))
        self._tabs = []
        self._init_ui()

        try:
            self.config_data = config.load_config()
            self.load_settings_to_ui()
        except (OSError, yaml.YAMLError, TypeError, ValueError, KeyError) as e:
            QMessageBox.warning(
                self,
                _("Configuration Error"),
                _("Failed to load user configuration: {error}\n\nLoaded default settings.").format(error=e),
            )
            self.config_data = config.load_default_config()
            self.load_settings_to_ui()

    def changeEvent(self, event):
        """Update theme stylesheet when the system palette changes."""
        if event.type() == QEvent.Type.PaletteChange:
            dark = ui.is_dark_theme()
            if dark != self._dark:
                self._dark = dark
                self.setStyleSheet(ui.dialog_stylesheet(ui.current_theme()))
        super().changeEvent(event)

    def _init_ui(self):
        """Build the GUI widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        self.tab_widget = QTabWidget()

        self.general_tab = GeneralTab()
        self.notes_tab = NotesTab()
        self.appearance_tab = AppearanceTab()
        self.ai_tab = AITab()
        self.audio_tab = AudioTab()
        self.prompts_tab = TextFilesTab()

        self._tabs = [
            (self.general_tab, _("General")),
            (self.notes_tab, _("Notes")),
            (self.appearance_tab, _("Appearance")),
            (self.ai_tab, _("AI Settings")),
            (self.audio_tab, _("Audio")),
            (self.prompts_tab, _("Prompts")),
        ]

        for tab_widget, title in self._tabs:
            self.tab_widget.addTab(tab_widget, title)

        layout.addWidget(self.tab_widget)

        btn_layout = QHBoxLayout()
        self.btn_defaults = QPushButton(_(RESTORE_DEFAULTS_TITLE))
        self.btn_defaults.clicked.connect(self.restore_defaults)
        btn_layout.addWidget(self.btn_defaults)

        btn_layout.addStretch()

        self.btn_cancel = QPushButton(_("Cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton(_("Save"))
        self.btn_save.setObjectName("btnSave")
        self.btn_save.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

    def load_settings_to_ui(self):
        """Populate widget states from loaded configuration dict."""
        for tab_widget, _title in self._tabs:
            tab_widget.load_settings(self.config_data)

    def restore_defaults(self):
        """Overwrite current edits with factory defaults after confirmation."""
        confirm = QMessageBox.question(
            self,
            _(RESTORE_DEFAULTS_TITLE),
            _(
                "Are you sure you want to restore all configuration settings"
                " and prompts to their default values?\n\nThis will"
                " overwrite current edits."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.config_data = config.load_default_config()
        self.load_settings_to_ui()
        self.general_tab.chk_autostart.setChecked(False)
        self.prompts_tab.restore_defaults()

        QMessageBox.information(
            self,
            _(RESTORE_DEFAULTS_TITLE),
            _("Defaults restored. Click 'Save' to apply changes to disk."),
        )

    def save_settings_from_ui(self):
        """Gather settings from widgets and persist them to files on disk."""
        save_order = (
            self.notes_tab,
            self.appearance_tab,
            self.ai_tab,
            self.audio_tab,
            self.general_tab,
            self.prompts_tab,
        )
        new_config = copy.deepcopy(self.config_data)
        try:
            for tab_widget in save_order:
                if not tab_widget.save_settings(new_config):
                    self.tab_widget.setCurrentWidget(tab_widget)
                    return False

            default_config = config.load_default_config()
            overrides = diff_configs(default_config, new_config)
            config.save_config(overrides)
        except (OSError, yaml.YAMLError) as e:
            QMessageBox.critical(self, _("Save Error"), _("Failed to save settings: {error}").format(error=e))
            return False
        else:
            self.config_data = new_config
            return True

    def accept(self):
        """Save settings and close the dialog with Accepted code."""
        if self.save_settings_from_ui():
            super().accept()
