"""Obsidian integration tab for configuration."""

import os

from PyQt6.QtWidgets import (
    QCheckBox,
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

from eloquent_notes.config_gui.tabs.base import ConfigTab


class ObsidianTab(ConfigTab):
    """Obsidian configuration tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        grp_obsidian = QGroupBox("Obsidian Integration")
        form_layout = QFormLayout(grp_obsidian)
        form_layout.setSpacing(10)

        path_widget = QWidget()
        path_layout = QHBoxLayout(path_widget)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(5)

        self.txt_vault_path = QLineEdit()
        self.txt_vault_path.setToolTip(
            "Absolute or user-relative path to your Obsidian vault folder."
        )
        self.btn_browse_vault = QPushButton("Browse...")
        self.btn_browse_vault.clicked.connect(self._browse_vault_path)
        path_layout.addWidget(self.txt_vault_path)
        path_layout.addWidget(self.btn_browse_vault)

        form_layout.addRow(QLabel("Vault Path:"), path_widget)

        self.txt_obs_folder = QLineEdit()
        self.txt_obs_folder.setToolTip(
            "Target folder inside the vault where dictations will be saved."
        )
        form_layout.addRow(QLabel("Target Folder:"), self.txt_obs_folder)

        self.chk_daily_notes = QCheckBox("Append dictations to daily note (YYYY-MM-DD.md)")
        self.chk_daily_notes.setToolTip(
            "If enabled, dictations are appended to the daily journal instead of"
            " creating new standalone files."
        )
        form_layout.addRow(self.chk_daily_notes)

        self.chk_vault_context = QCheckBox("Suggest vault note names as wikilinks")
        self.chk_vault_context.setToolTip(
            "If enabled, scans the vault for note names to suggest as wiki links in"
            " the classification phase."
        )
        form_layout.addRow(self.chk_vault_context)

        layout.addWidget(grp_obsidian)
        layout.addStretch()

    def _browse_vault_path(self):
        initial_dir = os.path.expanduser(self.txt_vault_path.text())
        if not os.path.exists(initial_dir):
            initial_dir = os.path.expanduser("~/")

        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Obsidian Vault Directory", initial_dir
        )
        if dir_path:
            self.txt_vault_path.setText(dir_path)

    def load_settings(self, config_data: dict) -> None:
        obs_cfg = config_data["obsidian"]
        self.txt_vault_path.setText(obs_cfg["vault_path"])
        self.txt_obs_folder.setText(obs_cfg["folder"])
        self.chk_daily_notes.setChecked(obs_cfg["daily_notes"])
        self.chk_vault_context.setChecked(obs_cfg["vault_context"])

    def save_settings(self, config_data: dict) -> bool:
        vault = self.txt_vault_path.text().strip()
        if not vault:
            QMessageBox.warning(self, "Validation Error", "Obsidian Vault Path cannot be empty.")
            return False

        vault_abs = os.path.abspath(os.path.expanduser(vault))
        if not os.path.exists(vault_abs):
            confirm = QMessageBox.question(
                self,
                "Directory Does Not Exist",
                f"The vault path '{vault}' does not exist on disk.\n\nDo you want to use this path anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return False

        config_data["obsidian"].update({
            "vault_path": vault,
            "folder": self.txt_obs_folder.text().strip(),
            "daily_notes": self.chk_daily_notes.isChecked(),
            "vault_context": self.chk_vault_context.isChecked(),
        })
        return True
