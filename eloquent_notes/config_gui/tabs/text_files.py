"""Configuration tab for editing a list of text files."""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from eloquent_notes import config
from eloquent_notes.i18n import _

PROMPTS = [
    (label, path, config.PROMPT_DEFAULTS[path])
    for label, path in (
        ("Transcription - System Prompt", config.TRANSCRIPTION_SYSTEM_PROMPT_PATH),
        ("Transcription - User Prompt", config.TRANSCRIPTION_USER_PROMPT_PATH),
        ("Rewriting - System Prompt", config.REWRITING_SYSTEM_PROMPT_PATH),
        ("Rewriting - User Prompt", config.REWRITING_USER_PROMPT_PATH),
        ("Classification - System Prompt", config.CLASSIFICATION_SYSTEM_PROMPT_PATH),
        ("Classification - User Prompt", config.CLASSIFICATION_USER_PROMPT_PATH),
        ("Retry Prompt", config.RETRY_PROMPT_PATH),
    )
]


class TextFilesTab(QWidget):
    """Tab for editing prompt files."""

    def __init__(self):
        super().__init__()
        self.loaded_contents = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(12)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel(_("Prompts:")))

        self.lst_items = QListWidget()
        for label, path, _default in PROMPTS:
            item = QListWidgetItem(_(label))
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.lst_items.addItem(item)

        left_layout.addWidget(self.lst_items)
        splitter.addWidget(left_widget)

        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(_("Prompt Content:"))
        self.editor = QTextEdit()
        font = QFont("Courier New", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(font)
        self.editor.setPlaceholderText(_("Select a prompt to edit..."))

        editor_layout.addWidget(lbl)
        editor_layout.addWidget(self.editor)
        splitter.addWidget(editor_widget)

        splitter.setSizes([250, 550])
        layout.addWidget(splitter)

        self.lst_items.currentItemChanged.connect(self._on_item_changed)

    def _load_current_into_editor(self) -> None:
        path = self.lst_items.currentItem().data(Qt.ItemDataRole.UserRole)
        self.editor.setPlainText(self.loaded_contents[path])

    def _on_item_changed(self, current, previous):
        if previous:
            prev_path = previous.data(Qt.ItemDataRole.UserRole)
            self.loaded_contents[prev_path] = self.editor.toPlainText()
        self._load_current_into_editor()

    def commit_active_editor(self):
        """Commit current editor contents to memory cache."""
        path = self.lst_items.currentItem().data(Qt.ItemDataRole.UserRole)
        self.loaded_contents[path] = self.editor.toPlainText()

    def load_settings(self, config_data: dict) -> None:
        self.lst_items.blockSignals(True)
        self.loaded_contents.clear()

        for _label, path, default_path in PROMPTS:
            src = path if os.path.exists(path) else default_path
            self.loaded_contents[path] = config.load_file(src)

        self.lst_items.setCurrentRow(0)
        self._load_current_into_editor()
        self.lst_items.blockSignals(False)

    def restore_defaults(self) -> None:
        self.loaded_contents.clear()
        for _label, path, default_path in PROMPTS:
            self.loaded_contents[path] = config.load_file(default_path)
        self._load_current_into_editor()

    def save_settings(self, config_data: dict) -> bool:
        self.commit_active_editor()
        for _label, path, _default in PROMPTS:
            content = self.loaded_contents[path]
            if not os.path.exists(path) or config.load_file(path) != content:
                config.atomic_write(path, content)
        return True

