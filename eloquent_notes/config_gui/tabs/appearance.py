"""Appearance tab for timeline layout and note type colors."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QColorDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from eloquent_notes import ui
from eloquent_notes.i18n import _
from eloquent_notes.notes import NOTE_TYPES
from eloquent_notes.window import _TYPE_LABELS


class AppearanceTab(QWidget):
    """Timeline grid columns and note type color customization tab."""

    def __init__(self) -> None:
        super().__init__()
        self._colors: dict[str, str] = dict(ui.DEFAULT_TYPE_COLORS)
        self.color_buttons: dict[str, QPushButton] = {}
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        grp_timeline = QGroupBox(_("Timeline Layout"))
        timeline_layout = QFormLayout(grp_timeline)
        timeline_layout.setSpacing(10)

        self.spn_columns = QSpinBox()
        self.spn_columns.setRange(1, 6)
        self.spn_columns.setToolTip(_("Number of columns in the notes timeline grid."))
        timeline_layout.addRow(QLabel(_("Timeline Columns:")), self.spn_columns)
        layout.addWidget(grp_timeline)

        grp_colors = QGroupBox(_("Note Type Colors"))
        colors_layout = QFormLayout(grp_colors)
        colors_layout.setSpacing(10)

        for note_type in NOTE_TYPES:
            btn = QPushButton()
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedWidth(120)
            btn.clicked.connect(lambda _checked=False, nt=note_type: self._pick_color(nt))
            self.color_buttons[note_type] = btn
            self._set_color(note_type, self._colors[note_type])
            colors_layout.addRow(QLabel(f"{_(_TYPE_LABELS[note_type])}:"), btn)

        layout.addWidget(grp_colors)
        layout.addStretch()

    def _set_color(self, note_type: str, hex_color: str) -> None:
        normalized = hex_color.upper()
        self._colors[note_type] = normalized
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(normalized))
        btn = self.color_buttons[note_type]
        btn.setIcon(QIcon(pixmap))
        btn.setText(normalized)

    def _pick_color(self, note_type: str) -> None:
        color = QColorDialog.getColor(
            QColor(self._colors[note_type]),
            self,
            _(_TYPE_LABELS[note_type]),
        )
        if color.isValid():
            self._set_color(note_type, color.name())

    def load_settings(self, config_data: dict) -> None:
        notes_cfg = config_data["notes"]
        self.spn_columns.setValue(int(notes_cfg["columns"]))
        type_colors = notes_cfg["type_colors"]
        for note_type in NOTE_TYPES:
            self._set_color(note_type, str(type_colors[note_type]))

    def save_settings(self, config_data: dict) -> bool:
        config_data["notes"]["columns"] = self.spn_columns.value()
        config_data["notes"]["type_colors"] = dict(self._colors)
        return True
