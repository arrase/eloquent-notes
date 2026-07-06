"""General tab for application configuration."""

import os

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from eloquent_notes.autostart import install_autostart
from eloquent_notes.config_gui.tabs.base import ConfigTab
from eloquent_notes.logging_utils import get_log_dir


class GeneralTab(ConfigTab):
    """General settings and logs tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        grp_startup = QGroupBox("Startup Options")
        startup_layout = QVBoxLayout(grp_startup)
        self.chk_autostart = QCheckBox("Start Eloquent Notes automatically on login")
        self.chk_autostart.setToolTip(
            "Creates a desktop autostart entry in ~/.config/autostart"
        )
        startup_layout.addWidget(self.chk_autostart)
        layout.addWidget(grp_startup)

        grp_logging = QGroupBox("Logging Settings")
        form_layout = QFormLayout(grp_logging)
        form_layout.setSpacing(10)

        self.cmb_log_level = QComboBox()
        self.cmb_log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.cmb_log_level.setToolTip("Verbosity level for app logging.")
        form_layout.addRow(QLabel("Logging Level:"), self.cmb_log_level)

        self.spn_log_max_mb = QSpinBox()
        self.spn_log_max_mb.setRange(1, 100)
        self.spn_log_max_mb.setSuffix(" MB")
        self.spn_log_max_mb.setToolTip("Maximum size of the log file before rotating.")
        form_layout.addRow(QLabel("Max Log File Size:"), self.spn_log_max_mb)

        self.spn_log_backups = QSpinBox()
        self.spn_log_backups.setRange(0, 10)
        self.spn_log_backups.setToolTip("Number of backup log files to retain.")
        form_layout.addRow(QLabel("Backup Count:"), self.spn_log_backups)

        layout.addWidget(grp_logging)

        self.btn_view_logs = QPushButton("View Log File")
        self.btn_view_logs.setToolTip(
            "Open the background daemon log file in your system editor."
        )
        self.btn_view_logs.clicked.connect(self._view_log_file)
        layout.addWidget(self.btn_view_logs)

        layout.addStretch()

    def _view_log_file(self):
        log_file_path = os.path.join(get_log_dir(), "app.log")
        if not os.path.exists(log_file_path):
            QMessageBox.information(
                self,
                "Log File",
                "Log file does not exist yet. Run some dictations first!",
            )
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(log_file_path))

    def load_settings(self, config_data: dict) -> None:
        autostart_path = os.path.expanduser("~/.config/autostart/eloquent-notes.desktop")
        self.chk_autostart.setChecked(os.path.exists(autostart_path))

        log_cfg = config_data["logging"]
        self.cmb_log_level.setCurrentText(log_cfg["level"])
        self.spn_log_max_mb.setValue(log_cfg["max_mb"])
        self.spn_log_backups.setValue(log_cfg["backup_count"])

    def save_settings(self, config_data: dict) -> bool:
        config_data["logging"].update({
            "level": self.cmb_log_level.currentText(),
            "max_mb": self.spn_log_max_mb.value(),
            "backup_count": self.spn_log_backups.value(),
        })

        try:
            autostart_path = os.path.expanduser("~/.config/autostart/eloquent-notes.desktop")
            if self.chk_autostart.isChecked():
                install_autostart()
            else:
                if os.path.exists(autostart_path):
                    os.remove(autostart_path)
            return True
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to update autostart setting: {e}"
            )
            return False
