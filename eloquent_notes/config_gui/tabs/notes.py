"""Notes storage tab for configuration."""

import os

from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from eloquent_notes.i18n import _


class NotesTab(QWidget):
    """Notes folder configuration tab."""

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        grp_notes = QGroupBox(_("Notes Storage"))
        form_layout = QFormLayout(grp_notes)
        form_layout.setSpacing(10)

        path_widget = QWidget()
        path_layout = QHBoxLayout(path_widget)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(5)

        self.txt_folder = QLineEdit()
        self.txt_folder.setToolTip(
            _(
                "Folder where each voice note is saved as a Markdown file."
                " Point it inside an Obsidian vault to see your notes there too."
            )
        )
        self.btn_browse_folder = QPushButton(_("Browse..."))
        self.btn_browse_folder.clicked.connect(self._browse_folder)
        path_layout.addWidget(self.txt_folder, 1)
        path_layout.addWidget(self.btn_browse_folder)

        form_layout.addRow(QLabel(_("Notes Folder:")), path_widget)

        layout.addWidget(grp_notes)
        layout.addStretch()

    def _browse_folder(self):
        initial_dir = os.path.expanduser(self.txt_folder.text())
        if not os.path.exists(initial_dir):
            initial_dir = os.path.expanduser("~/")

        dir_path = QFileDialog.getExistingDirectory(
            self, _("Select Notes Folder"), initial_dir
        )
        if dir_path:
            self.txt_folder.setText(dir_path)

    def load_settings(self, config_data: dict) -> None:
        self.txt_folder.setText(config_data["notes"]["folder"])

    def save_settings(self, config_data: dict) -> bool:
        folder = self.txt_folder.text().strip()
        if not folder:
            QMessageBox.warning(self, _("Validation Error"), _("Notes Folder cannot be empty."))
            return False

        config_data["notes"]["folder"] = folder
        return True
