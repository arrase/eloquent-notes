"""Main window: a day-grouped timeline of voice notes and a note reader.

The window is a pure view. It renders the notes handed to it by the
controller and reports user intent through signals; all file, audio and
model work happens in EloquentApp.
"""

from __future__ import annotations

import html
from datetime import date, datetime, timedelta

from PyQt6.QtCore import QDateTime, QLocale, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QGuiApplication, QKeySequence, QMouseEvent, QPalette, QResizeEvent, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from eloquent_notes import IDLE, PROCESSING, RECORDING, ui
from eloquent_notes.notes import NOTE_TYPES, Note, parse_tags

CONTENT_MAX_WIDTH = 720
COLUMN_WIDTH = 440
DEFAULT_COLUMNS = 2
PREVIEW_CHARS = 180

TYPE_COLORS = {
    "note": "#64748b",
    "task": "#2563eb",
    "idea": "#d97706",
    "reminder": "#dc2626",
    "question": "#7c3aed",
    "decision": "#059669",
}

RECORD_STATES = {
    IDLE: ("gray", "Click to record a note"),
    RECORDING: ("red", "Recording… click to stop"),
    PROCESSING: ("orange", "Writing your note…"),
}

# Dates follow the English UI rather than the system locale.
_UI_LOCALE = QLocale(QLocale.Language.English, QLocale.Country.UnitedKingdom)

DICTATE_LABELS = {
    IDLE: "Add dictation",
    RECORDING: "Stop dictation",
    PROCESSING: "Processing…",
}

STYLESHEET = """
QLabel#appTitle { font-size: 20px; font-weight: 700; }
QLineEdit#search {
    padding: 8px 12px; border: 1px solid palette(mid); border-radius: 8px; background: palette(base);
}
QPushButton#chip {
    padding: 4px 12px; border: 1px solid palette(mid); border-radius: 12px; background: transparent;
}
QPushButton#chip:checked {
    background: palette(highlight); color: palette(highlighted-text); border-color: palette(highlight);
}
QFrame#card { background: palette(base); border: 1px solid palette(mid); border-radius: 10px; }
QFrame#card:hover { border-color: palette(highlight); }
QLabel#cardTitle { font-size: 15px; font-weight: 600; }
QLabel#dayHeader { font-size: 11px; font-weight: 700; padding-top: 14px; }
QPushButton#record { border: none; background: transparent; }
QLineEdit#titleEdit { font-size: 22px; font-weight: 700; border: none; background: transparent; }
QLineEdit#tagsEdit, QPlainTextEdit#bodyEdit { border: none; background: transparent; }
QPlainTextEdit#bodyEdit { font-size: 14px; }
QFrame#separator { border: none; background: palette(mid); }
QScrollArea { border: none; background: transparent; }
"""


def format_time(moment: datetime, pattern: str) -> str:
    """Format a datetime with a Qt date-time pattern in the UI locale."""
    return _UI_LOCALE.toString(QDateTime.fromSecsSinceEpoch(int(moment.timestamp())), pattern)


def day_label(day: date, today: date) -> str:
    """Human-friendly heading for a timeline day."""
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    return _UI_LOCALE.toString(day, "dddd, d MMMM" if day.year == today.year else "dddd, d MMMM yyyy")


def _muted(label: QLabel) -> QLabel:
    label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
    return label


def _plain(text: str, object_name: str = "") -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setObjectName(object_name)
    return label


class Column(QWidget):
    """Container whose content stays centered and no wider than max_width."""

    def __init__(self, max_width: int = CONTENT_MAX_WIDTH) -> None:
        super().__init__()
        self.max_width = max_width
        self.column = QVBoxLayout(self)
        self.column.setSpacing(8)

    def set_max_width(self, max_width: int) -> None:
        self.max_width = max_width
        self._update_margins()

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        self._update_margins()
        super().resizeEvent(event)

    def _update_margins(self) -> None:
        side = max(20, (self.width() - self.max_width) // 2)
        self.column.setContentsMargins(side, 12, side, 12)


class NoteCard(QFrame):
    """Clickable timeline summary of one note."""

    opened = pyqtSignal(object)
    tag_clicked = pyqtSignal(str)

    def __init__(self, note: Note, show_date: bool) -> None:
        super().__init__()
        self.note = note
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        when = format_time(note.created, "d MMM yyyy, HH:mm" if show_date else "HH:mm")
        meta = _muted(QLabel(
            f'{when} · <span style="color: {TYPE_COLORS[note.type]}; font-weight: 600;">'
            f"● {note.type.capitalize()}</span>"
        ))
        layout.addWidget(meta)
        layout.addWidget(_plain(note.title, "cardTitle"))

        if note.body:
            flat = " ".join(note.body.split())
            preview = flat if len(flat) <= PREVIEW_CHARS else f"{flat[:PREVIEW_CHARS].rstrip()}…"
            layout.addWidget(_muted(_plain(preview)))

        if note.tags:
            tags = QLabel(" &nbsp; ".join(
                f'<a href="{html.escape(tag)}" style="text-decoration: none;">#{html.escape(tag)}</a>'
                for tag in note.tags
            ))
            tags.setWordWrap(True)
            tags.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
            tags.linkActivated.connect(self.tag_clicked)
            layout.addWidget(tags)

        layout.addStretch()

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self.opened.emit(self.note)
        super().mouseReleaseEvent(event)


class TimelinePage(QWidget):
    """Search box, filters, day-grouped note cards and the record button."""

    record_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    search_requested = pyqtSignal(str)
    note_opened = pyqtSignal(object)

    def __init__(self, columns: int = DEFAULT_COLUMNS) -> None:
        super().__init__()
        self._columns = columns
        self._notes: list[Note] = []
        self._type = ""
        self._query = ""
        self._results: list[Note] | None = None
        self._grid = QGridLayout()
        self._init_ui()
        self.set_state(IDLE)

    def _max_width(self) -> int:
        return max(CONTENT_MAX_WIDTH, self._columns * COLUMN_WIDTH)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 12)
        layout.setSpacing(0)

        self._top = Column(self._max_width())
        self._top.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        header = QHBoxLayout()
        title = QLabel("Eloquent Notes")
        title.setObjectName("appTitle")
        header.addWidget(title)
        header.addStretch()
        btn_settings = QPushButton("Settings")
        btn_settings.setFlat(True)
        btn_settings.clicked.connect(self.settings_clicked)
        header.addWidget(btn_settings)
        self._top.column.addLayout(header)

        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Search your notes by meaning…")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self._on_search)
        self.search.textChanged.connect(self._on_search_text_changed)
        self._top.column.addWidget(self.search)

        filters = QHBoxLayout()
        filters.setSpacing(6)
        self.type_filter = QButtonGroup(self)
        for note_type, label in [("", "All"), *((t, f"{t.capitalize()}s") for t in NOTE_TYPES)]:
            chip = QPushButton(label)
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setChecked(not note_type)
            chip.setProperty("noteType", note_type)
            self.type_filter.addButton(chip)
            filters.addWidget(chip)
        self.type_filter.buttonClicked.connect(self._on_type_clicked)
        filters.addStretch()
        self.tag_filter = QComboBox()
        self.tag_filter.addItem("All tags", "")
        self.tag_filter.currentIndexChanged.connect(self._render)
        filters.addWidget(self.tag_filter)
        self._top.column.addLayout(filters)
        layout.addWidget(self._top)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(Column(self._max_width()))
        layout.addWidget(self._scroll, stretch=1)

        self.record_button = QPushButton()
        self.record_button.setObjectName("record")
        self.record_button.setFixedSize(72, 72)
        self.record_button.setIconSize(self.record_button.size())
        self.record_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.record_button.clicked.connect(self.record_clicked)
        layout.addWidget(self.record_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.record_status = _muted(QLabel())
        layout.addWidget(self.record_status, alignment=Qt.AlignmentFlag.AlignHCenter)

    # --- Public API ------------------------------------------------------

    def set_columns(self, columns: int) -> None:
        if columns != self._columns:
            self._columns = columns
            self._top.set_max_width(self._max_width())
            self._render()

    def set_notes(self, notes: list[Note]) -> None:
        self._notes = notes
        if self._results is not None:
            by_path = {note.path: note for note in notes}
            self._results = [by_path[note.path] for note in self._results if note.path in by_path]
        self._refresh_tag_filter()
        self._render()

    def show_search_results(self, query: str, results: list[Note]) -> None:
        if query == self._query:
            self._results = results
            self._render()

    def show_search_error(self, query: str, message: str) -> None:
        if query == self._query:
            self._results = []
            self._show([self._message(f"Search failed: {message}")])

    def select_tag(self, tag: str) -> None:
        self.tag_filter.setCurrentIndex(self.tag_filter.findData(tag))

    def set_state(self, state: str) -> None:
        color, status = RECORD_STATES[state]
        self.record_button.setIcon(ui.get_qicon(color))
        self.record_button.setEnabled(state != PROCESSING)
        self.record_status.setText(status)

    # --- Search & filters --------------------------------------------------

    def _on_search(self) -> None:
        query = self.search.text().strip()
        if query:
            self._query = query
            self._results = None
            self._render()
            self.search_requested.emit(query)

    def _on_search_text_changed(self, text: str) -> None:
        if not text.strip() and self._query:
            self._query = ""
            self._results = None
            self._render()

    def _on_type_clicked(self, chip: QPushButton) -> None:
        self._type = chip.property("noteType")
        self._render()

    def _refresh_tag_filter(self) -> None:
        current = self.tag_filter.currentData()
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem("All tags", "")
        for tag in sorted({tag for note in self._notes for tag in note.tags}):
            self.tag_filter.addItem(f"#{tag}", tag)
        self.tag_filter.setCurrentIndex(max(0, self.tag_filter.findData(current)))
        self.tag_filter.blockSignals(False)

    def _matches(self, note: Note) -> bool:
        tag = self.tag_filter.currentData()
        return (not self._type or note.type == self._type) and (not tag or tag in note.tags)

    # --- Rendering ---------------------------------------------------------

    @staticmethod
    def _message(text: str) -> QLabel:
        label = _muted(_plain(text))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _card(self, note: Note, show_date: bool) -> NoteCard:
        card = NoteCard(note, show_date)
        card.opened.connect(self.note_opened)
        card.tag_clicked.connect(self.select_tag)
        return card

    def _list_widgets(self) -> list[QWidget]:
        if not self._query:
            source = self._notes
        elif self._results is None:
            return [self._message("Searching…")]
        else:
            source = self._results

        notes = [note for note in source if self._matches(note)]
        if not notes:
            if self._query:
                return [self._message("No matching notes.")]
            if self._notes:
                return [self._message("No notes match these filters.")]
            return [self._message("No notes yet. Click the microphone to record your first one.")]

        if self._query:
            header = _muted(_plain(f"{len(notes)} result{'' if len(notes) == 1 else 's'}", "dayHeader"))
            return [header, *(self._card(note, show_date=True) for note in notes)]

        widgets: list[QWidget] = []
        today = date.today()
        current_day = None
        for note in notes:
            day = note.created.date()
            if day != current_day:
                current_day = day
                widgets.append(_muted(_plain(day_label(day, today).upper(), "dayHeader")))
            widgets.append(self._card(note, show_date=False))
        return widgets

    def _render(self) -> None:
        self._show(self._list_widgets())

    def _show(self, widgets: list[QWidget]) -> None:
        """Swap in a freshly built grid; setWidget makes the scroll area re-measure it."""
        column = Column(self._max_width())
        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)
        for col in range(self._columns):
            self._grid.setColumnStretch(col, 1)

        row = 0
        col = 0
        for widget in widgets:
            if isinstance(widget, NoteCard):
                self._grid.addWidget(widget, row, col)
                col += 1
                if col == self._columns:
                    row += 1
                    col = 0
            else:
                if col > 0:
                    row += 1
                    col = 0
                self._grid.addWidget(widget, row, 0, 1, self._columns)
                row += 1

        column.column.addLayout(self._grid)
        column.column.addStretch()
        # Deferred: a card's own signal may have triggered this render.
        self._scroll.takeWidget().deleteLater()  # type: ignore[union-attr]
        self._scroll.setWidget(column)


class ReaderPage(QWidget):
    """Editable view of a single note."""

    note: Note  # set by show_note before the page is ever displayed

    back_clicked = pyqtSignal()
    dictate_clicked = pyqtSignal()
    copy_clicked = pyqtSignal()
    delete_clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        content = Column()
        layout.addWidget(content)

        toolbar = QHBoxLayout()
        btn_back = QPushButton("← Back")
        btn_back.setFlat(True)
        btn_back.clicked.connect(self.back_clicked)
        toolbar.addWidget(btn_back)
        toolbar.addStretch()
        self.btn_dictate = QPushButton(DICTATE_LABELS[IDLE])
        self.btn_dictate.setIcon(ui.get_qicon("gray"))
        self.btn_dictate.clicked.connect(self.dictate_clicked)
        toolbar.addWidget(self.btn_dictate)
        btn_copy = QPushButton("Copy")
        btn_copy.clicked.connect(self.copy_clicked)
        toolbar.addWidget(btn_copy)
        btn_delete = QPushButton("Delete")
        btn_delete.clicked.connect(self.delete_clicked)
        toolbar.addWidget(btn_delete)
        content.column.addLayout(toolbar)

        meta = QHBoxLayout()
        self.type_box = QComboBox()
        for note_type in NOTE_TYPES:
            self.type_box.addItem(note_type.capitalize(), note_type)
        meta.addWidget(self.type_box)
        self.date_label = _muted(QLabel())
        meta.addWidget(self.date_label)
        meta.addStretch()
        content.column.addLayout(meta)

        self.title_edit = QLineEdit()
        self.title_edit.setObjectName("titleEdit")
        self.title_edit.setPlaceholderText("Title")
        content.column.addWidget(self.title_edit)

        self.tags_edit = QLineEdit()
        self.tags_edit.setObjectName("tagsEdit")
        self.tags_edit.setPlaceholderText("Tags, separated by commas")
        content.column.addWidget(self.tags_edit)

        separator = QFrame()
        separator.setObjectName("separator")
        separator.setFixedHeight(1)
        content.column.addWidget(separator)

        self.body_edit = QPlainTextEdit()
        self.body_edit.setObjectName("bodyEdit")
        content.column.addWidget(self.body_edit, stretch=1)

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self.back_clicked)

    def show_note(self, note: Note) -> None:
        self.note = note
        self.type_box.setCurrentIndex(self.type_box.findData(note.type))
        self.date_label.setText(format_time(note.created, "dddd, d MMMM yyyy, HH:mm"))
        self.title_edit.setText(note.title)
        self.tags_edit.setText(", ".join(note.tags))
        self.body_edit.setPlainText(note.body)

    def commit(self) -> bool:
        """Copy the edited fields into the note; return True if anything changed."""
        note = self.note
        edited = (
            self.title_edit.text().strip(),
            self.type_box.currentData(),
            parse_tags(self.tags_edit.text()),
            self.body_edit.toPlainText().strip(),
        )
        if edited == (note.title, note.type, note.tags, note.body):
            return False
        note.title, note.type, note.tags, note.body = edited
        return True

    def set_state(self, state: str) -> None:
        self.btn_dictate.setText(DICTATE_LABELS[state])
        self.btn_dictate.setIcon(ui.get_qicon(RECORD_STATES[state][0]))
        self.btn_dictate.setEnabled(state != PROCESSING)


class MainWindow(QMainWindow):
    """Two-page window: the notes timeline and the note reader."""

    record_clicked = pyqtSignal()
    dictate_clicked = pyqtSignal(object)
    note_edited = pyqtSignal(object)
    delete_requested = pyqtSignal(object)
    search_requested = pyqtSignal(str)
    settings_clicked = pyqtSignal()

    def __init__(self, columns: int = DEFAULT_COLUMNS) -> None:
        super().__init__()
        self.setWindowTitle("Eloquent Notes")
        self.resize(960, 880)
        self.setMinimumWidth(720)
        self.setStyleSheet(STYLESHEET)

        self.timeline = TimelinePage(columns=columns)
        self.reader = ReaderPage()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.timeline)
        self.stack.addWidget(self.reader)
        self.setCentralWidget(self.stack)

        self.timeline.record_clicked.connect(self.record_clicked)
        self.timeline.settings_clicked.connect(self.settings_clicked)
        self.timeline.search_requested.connect(self.search_requested)
        self.timeline.note_opened.connect(self.show_note)
        self.reader.back_clicked.connect(self.show_timeline)
        self.reader.dictate_clicked.connect(self._on_dictate)
        self.reader.copy_clicked.connect(self._on_copy)
        self.reader.delete_clicked.connect(self._on_delete)

    def set_columns(self, columns: int) -> None:
        self.timeline.set_columns(columns)

    def set_notes(self, notes: list[Note]) -> None:
        self.timeline.set_notes(notes)

    def show_search_results(self, query: str, results: list[Note]) -> None:
        self.timeline.show_search_results(query, results)

    def show_search_error(self, query: str, message: str) -> None:
        self.timeline.show_search_error(query, message)

    def set_state(self, state: str) -> None:
        self.timeline.set_state(state)
        self.reader.set_state(state)

    def show_note(self, note: Note) -> None:
        self.save_open_note()
        self.reader.show_note(note)
        self.stack.setCurrentWidget(self.reader)

    def show_timeline(self) -> None:
        self.save_open_note()
        self.stack.setCurrentWidget(self.timeline)

    def save_open_note(self) -> None:
        """Emit note_edited if the note open in the reader has unsaved edits."""
        if self.stack.currentWidget() is self.reader and self.reader.commit():
            self.note_edited.emit(self.reader.note)

    def _on_dictate(self) -> None:
        self.save_open_note()
        self.dictate_clicked.emit(self.reader.note)

    def _on_copy(self) -> None:
        self.save_open_note()
        QGuiApplication.clipboard().setText(self.reader.note.markdown)  # type: ignore[union-attr]

    def _on_delete(self) -> None:
        note = self.reader.note
        confirm = QMessageBox.question(self, "Delete Note", f"Move “{note.title}” to the trash?")
        if confirm == QMessageBox.StandardButton.Yes:
            self.stack.setCurrentWidget(self.timeline)
            self.delete_requested.emit(note)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self.save_open_note()
        super().closeEvent(event)
