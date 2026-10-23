"""General tab for application configuration."""

import os

from PyQt6.QtCore import Qt, QUrl
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
    QWidget,
)

from eloquent_notes.autostart import (
    install_autostart,
    is_autostart_enabled,
    remove_autostart,
)
from eloquent_notes.i18n import _
from eloquent_notes.logging_utils import _LOG_LEVELS, get_log_file_path


class GeneralTab(QWidget):
    """General settings and logs tab."""

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        grp_startup = QGroupBox(_("Startup Options"))
        startup_layout = QVBoxLayout(grp_startup)
        self.chk_autostart = QCheckBox(_("Start Eloquent Notes automatically on login"))
        self.chk_autostart.setToolTip(
            _("Creates a desktop autostart entry in the XDG autostart directory")
        )
        startup_layout.addWidget(self.chk_autostart)
        layout.addWidget(grp_startup)

        grp_logging = QGroupBox(_("Logging Settings"))
        form_layout = QFormLayout(grp_logging)
        form_layout.setSpacing(10)

        self.cmb_log_level = QComboBox()
        self.cmb_log_level.addItems(list(_LOG_LEVELS))
        self.cmb_log_level.setToolTip(_("Verbosity level for app logging."))
        form_layout.addRow(QLabel(_("Logging Level:")), self.cmb_log_level)

        self.spn_log_max_mb = QSpinBox()
        self.spn_log_max_mb.setRange(1, 100)
        self.spn_log_max_mb.setSuffix(_(" MB"))
        self.spn_log_max_mb.setToolTip(_("Maximum size of the log file before rotating."))
        form_layout.addRow(QLabel(_("Max Log File Size:")), self.spn_log_max_mb)

        self.spn_log_backups = QSpinBox()
        self.spn_log_backups.setRange(0, 10)
        self.spn_log_backups.setToolTip(_("Number of backup log files to retain."))
        form_layout.addRow(QLabel(_("Backup Count:")), self.spn_log_backups)

        layout.addWidget(grp_logging)

        self.btn_view_logs = QPushButton(_("View Log File"))
        self.btn_view_logs.setToolTip(
            _("Open the background daemon log file in your system editor.")
        )
        self.btn_view_logs.clicked.connect(self._view_log_file)
        layout.addWidget(self.btn_view_logs, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()

    def _view_log_file(self):
        log_file_path = get_log_file_path()
        if not os.path.exists(log_file_path):
            QMessageBox.information(
                self,
                _("Log File"),
                _("Log file does not exist yet. Run some dictations first!"),
            )
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(log_file_path))

    def load_settings(self, config_data: dict) -> None:
        self.chk_autostart.setChecked(is_autostart_enabled())

        log_cfg = config_data["logging"]
        self.cmb_log_level.setCurrentText(str(log_cfg["level"]).upper())
        self.spn_log_max_mb.setValue(int(log_cfg["max_mb"]))
        self.spn_log_backups.setValue(int(log_cfg["backup_count"]))

    def save_settings(self, config_data: dict) -> bool:
        config_data["logging"].update({
            "level": self.cmb_log_level.currentText(),
            "max_mb": self.spn_log_max_mb.value(),
            "backup_count": self.spn_log_backups.value(),
        })

        if self.chk_autostart.isChecked():
            install_autostart()
        else:
            remove_autostart()
        return True

