"""Base class for configuration tabs editing a list of files."""

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
from eloquent_notes.config_gui.tabs.base import ConfigTab


class TextFilesTab(ConfigTab):
    """Generic tab for editing a list of text files (prompts or templates)."""

    def __init__(self, items, editor_label, placeholder, parent=None):
        super().__init__(parent)
        self.items = items
        self._block_cache = False
        self.loaded_contents = {}
        self.current_item = None
        self.editor_label_text = editor_label
        self.placeholder_text = placeholder
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.lst_items = QListWidget()
        for label, path, _ in self.items:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.lst_items.addItem(item)

        splitter.addWidget(self.lst_items)

        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(self.editor_label_text)
        self.editor = QTextEdit()
        font = QFont("Courier New", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(font)
        self.editor.setPlaceholderText(self.placeholder_text)
        self.editor.setEnabled(False)

        editor_layout.addWidget(lbl)
        editor_layout.addWidget(self.editor)
        splitter.addWidget(editor_widget)

        splitter.setSizes([250, 550])
        layout.addWidget(splitter)

        self.lst_items.currentItemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, current, previous):
        if previous and not self._block_cache:
            prev_path = previous.data(Qt.ItemDataRole.UserRole)
            self.loaded_contents[prev_path] = self.editor.toPlainText()

        if current:
            path = current.data(Qt.ItemDataRole.UserRole)
            self.editor.setPlainText(self.loaded_contents.get(path, ""))
            self.editor.setEnabled(True)
            self.current_item = current
        else:
            self.editor.clear()
            self.editor.setEnabled(False)
            self.current_item = None

    def commit_active_editor(self):
        """Commit current editor contents to memory cache."""
        if self.current_item:
            path = self.current_item.data(Qt.ItemDataRole.UserRole)
            self.loaded_contents[path] = self.editor.toPlainText()

    def load_settings(self, config_data: dict) -> None:
        self._block_cache = True
        self.loaded_contents.clear()

        for _, path, default_path in self.items:
            if os.path.exists(path):
                self.loaded_contents[path] = config.load_file(path)
            elif os.path.exists(default_path):
                self.loaded_contents[path] = config.load_file(default_path)
            else:
                self.loaded_contents[path] = ""

        if self.lst_items.count() > 0:
            self.lst_items.setCurrentRow(0)

        self._block_cache = False

    def restore_defaults(self) -> None:
        self._block_cache = True
        self.loaded_contents.clear()
        for _, path, default_path in self.items:
            if os.path.exists(default_path):
                self.loaded_contents[path] = config.load_file(default_path)
            else:
                self.loaded_contents[path] = ""
        if self.current_item:
            path = self.current_item.data(Qt.ItemDataRole.UserRole)
            self.editor.setPlainText(self.loaded_contents.get(path, ""))
        self._block_cache = False

    def save_settings(self, config_data: dict) -> bool:
        self.commit_active_editor()
        for _, path, _ in self.items:
            content = self.loaded_contents.get(path, "")
            config.save_file(path, content)
        return True
