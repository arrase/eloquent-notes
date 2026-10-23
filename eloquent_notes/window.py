"""Main window: a day-grouped timeline of voice notes and a note reader.

The window is a pure view. It renders the notes handed to it by the
controller and reports user intent through signals; all file, audio and
model work happens in EloquentApp.
"""

import html
from datetime import date, datetime, timedelta

from PyQt6.QtCore import QDateTime, QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QGuiApplication, QKeySequence, QMouseEvent, QResizeEvent, QShortcut
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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from eloquent_notes import IDLE, PROCESSING, RECORDING, ui
from eloquent_notes.i18n import _, ngettext, ui_locale
from eloquent_notes.notes import NOTE_TYPES, Note, parse_tags

PAGE_MARGIN = 20
DEFAULT_COLUMNS = 2
PREVIEW_CHARS = 180

DICTATE_STATES = {
    IDLE: ("gray", "Add dictation"),
    RECORDING: ("red", "Stop dictation"),
    PROCESSING: ("orange", "Processing…"),
}

_TYPE_LABELS = {
    "note": "Note",
    "task": "Task",
    "idea": "Idea",
    "reminder": "Reminder",
    "question": "Question",
    "decision": "Decision",
}

_TYPE_FILTER_LABELS = (
    ("", "All"),
    ("note", "Notes"),
    ("task", "Tasks"),
    ("idea", "Ideas"),
    ("reminder", "Reminders"),
    ("question", "Questions"),
    ("decision", "Decisions"),
)


def format_time(moment: datetime, pattern: str) -> str:
    """Format a datetime with a Qt date-time pattern in the UI locale."""
    return ui_locale().toString(QDateTime.fromSecsSinceEpoch(int(moment.timestamp())), pattern)


def day_label(day: date, today: date) -> str:
    """Human-friendly heading for a timeline day."""
    if day == today:
        return _("Today")
    if day == today - timedelta(days=1):
        return _("Yesterday")
    return ui_locale().toString(day, "dddd, d MMMM" if day.year == today.year else "dddd, d MMMM yyyy")


def _plain(text: str, object_name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


class _ScrollContent(QWidget):
    """Scroll area body that keeps its right edge aligned with the header when the scrollbar appears."""

    def __init__(self, scroll: QScrollArea) -> None:
        super().__init__()
        self.setObjectName("columnContainer")
        self._scroll = scroll
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(PAGE_MARGIN, 14, PAGE_MARGIN, 14)
        self.column.setSpacing(10)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        right = max(0, PAGE_MARGIN - max(0, self._scroll.width() - self.width()))
        self.column.setContentsMargins(PAGE_MARGIN, 14, right, 14)
        super().resizeEvent(event)


class NoteCard(QFrame):
    """Clickable timeline summary of one note."""

    opened = pyqtSignal(object)
    tag_clicked = pyqtSignal(str)

    def __init__(self, note: Note, show_date: bool, type_color: str) -> None:
        super().__init__()
        self.note = note
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        theme = ui.current_theme()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        when = format_time(note.created, "d MMM yyyy, HH:mm" if show_date else "HH:mm")
        meta = QLabel(
            f'{when} &nbsp;·&nbsp; <span style="color: {type_color}; font-weight: 600;">'
            f"● {_(_TYPE_LABELS[note.type])}</span>"
        )
        meta.setObjectName("mutedLabel")
        layout.addWidget(meta)
        layout.addWidget(_plain(note.title, "cardTitle"))

        if note.body:
            flat = " ".join(note.body.split())
            preview = flat if len(flat) <= PREVIEW_CHARS else f"{flat[:PREVIEW_CHARS].rstrip()}…"
            layout.addWidget(_plain(preview, "cardPreview"))

        layout.addStretch()

        if note.tags:
            tags = QLabel(" &nbsp; ".join(
                f'<a href="{html.escape(tag)}" style="text-decoration: none; color: {theme.tag}; font-weight: 500;">'
                f"#{html.escape(tag)}</a>"
                for tag in note.tags
            ))
            tags.setObjectName("cardTags")
            tags.setWordWrap(True)
            tags.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
            tags.linkActivated.connect(self.tag_clicked)
            layout.addWidget(tags)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self.opened.emit(self.note)
        super().mouseReleaseEvent(event)


class TimelinePage(QWidget):
    """Search box, filters and day-grouped note cards."""

    settings_clicked = pyqtSignal()
    search_requested = pyqtSignal(str)
    note_opened = pyqtSignal(object)

    def __init__(
        self,
        columns: int = DEFAULT_COLUMNS,
        type_colors: dict[str, str] = ui.DEFAULT_TYPE_COLORS,
    ) -> None:
        super().__init__()
        self.setObjectName("timelinePage")
        self._columns = columns
        self._type_colors = dict(type_colors)
        self._notes: list[Note] = []
        self._type = ""
        self._query = ""
        self._error = ""
        self._results: list[Note] | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top = QVBoxLayout()
        top.setContentsMargins(PAGE_MARGIN, 16, PAGE_MARGIN, 14)
        top.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Eloquent Notes")
        title.setObjectName("appTitle")
        header.addWidget(title)
        header.addStretch()
        btn_settings = QPushButton(_("Settings"))
        btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_settings.clicked.connect(self.settings_clicked)
        header.addWidget(btn_settings)
        top.addLayout(header)

        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText(_("Search your notes by meaning…"))
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self._on_search)
        self.search.textChanged.connect(self._on_search_text_changed)
        top.addWidget(self.search)

        filters = QHBoxLayout()
        filters.setSpacing(6)
        self.type_filter = QButtonGroup(self)
        for note_type, label in _TYPE_FILTER_LABELS:
            chip = QPushButton(_(label))
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setChecked(not note_type)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setProperty("noteType", note_type)
            self.type_filter.addButton(chip)
            filters.addWidget(chip)
        self.type_filter.buttonClicked.connect(self._on_type_clicked)
        filters.addStretch()
        self.tag_filter = QComboBox()
        self.tag_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tag_filter.addItem(_("All tags"), "")
        self.tag_filter.currentIndexChanged.connect(self._render)
        filters.addWidget(self.tag_filter)
        top.addLayout(filters)
        layout.addLayout(top)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(QWidget())
        layout.addWidget(self._scroll, stretch=1)

    # --- Public API ------------------------------------------------------

    def set_columns(self, columns: int) -> None:
        if columns != self._columns:
            self._columns = columns
            self._render()

    def set_type_colors(self, type_colors: dict[str, str]) -> None:
        if type_colors != self._type_colors:
            self._type_colors = dict(type_colors)
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
            self._error = ""
            self._results = results
            self._render()

    def show_search_error(self, query: str, message: str) -> None:
        if query == self._query:
            self._error = message
            self._results = []
            self._render()

    def select_tag(self, tag: str) -> None:
        self.tag_filter.setCurrentIndex(self.tag_filter.findData(tag))

    # --- Search & filters --------------------------------------------------

    def _on_search(self) -> None:
        query = self.search.text().strip()
        if query:
            self._query = query
            self._error = ""
            self._results = None
            self._render()
            self.search_requested.emit(query)

    def _on_search_text_changed(self, text: str) -> None:
        if not text.strip() and self._query:
            self._query = ""
            self._error = ""
            self._results = None
            self._render()

    def _on_type_clicked(self, chip: QPushButton) -> None:
        self._type = chip.property("noteType")
        self._render()

    def _refresh_tag_filter(self) -> None:
        current = self.tag_filter.currentData()
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem(_("All tags"), "")
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
        label = _plain(text, "mutedLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setContentsMargins(0, 32, 0, 32)
        return label

    def _card(self, note: Note, show_date: bool) -> NoteCard:
        card = NoteCard(note, show_date, self._type_colors[note.type])
        card.opened.connect(self.note_opened)
        card.tag_clicked.connect(self.select_tag)
        return card

    def _list_widgets(self) -> list[QWidget]:
        if not self._query:
            source = self._notes
        elif self._error:
            return [self._message(_("Search failed: {error}").format(error=self._error))]
        elif self._results is None:
            return [self._message(_("Searching…"))]
        else:
            source = self._results

        notes = [note for note in source if self._matches(note)]
        if not notes:
            if self._query:
                return [self._message(_("No matching notes."))]
            if self._notes:
                return [self._message(_("No notes match these filters."))]
            return [self._message(_("No notes yet. Click the tray icon to record your first one."))]

        if self._query:
            count = len(notes)
            header = _plain(
                ngettext("{count} result", "{count} results", count).format(count=count),
                "dayHeader",
            )
            return [header, *(self._card(note, show_date=True) for note in notes)]

        widgets: list[QWidget] = []
        today = date.today()
        current_day = None
        for note in notes:
            day = note.created.date()
            if day != current_day:
                current_day = day
                widgets.append(_plain(day_label(day, today).upper(), "dayHeader"))
            widgets.append(self._card(note, show_date=False))
        return widgets

    def _render(self) -> None:
        self._show(self._list_widgets())

    def _show(self, widgets: list[QWidget]) -> None:
        """Swap in a freshly built grid; setWidget makes the scroll area re-measure it."""
        content = _ScrollContent(self._scroll)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(12)
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

        content.column.addLayout(self._grid)
        content.column.addStretch(1)
        # Deferred: a card's own signal may have triggered this render.
        self._scroll.takeWidget().deleteLater()  # type: ignore[union-attr]
        self._scroll.setWidget(content)


class ReaderPage(QWidget):
    """Editable view of a single note."""

    note: Note

    back_clicked = pyqtSignal()
    dictate_clicked = pyqtSignal()
    copy_clicked = pyqtSignal()
    delete_clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("readerPage")
        self._init_ui()
        self.set_state(IDLE)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PAGE_MARGIN, 16, PAGE_MARGIN, PAGE_MARGIN)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        btn_back = QPushButton(_("← Back"))
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.clicked.connect(self.back_clicked)
        toolbar.addWidget(btn_back)
        toolbar.addStretch()
        self.btn_dictate = QPushButton()
        self.btn_dictate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dictate.clicked.connect(self.dictate_clicked)
        toolbar.addWidget(self.btn_dictate)
        btn_copy = QPushButton(_("Copy"))
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(self.copy_clicked)
        toolbar.addWidget(btn_copy)
        self.btn_delete = QPushButton(_("Delete"))
        self.btn_delete.setObjectName("dangerButton")
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.clicked.connect(self.delete_clicked)
        toolbar.addWidget(self.btn_delete)
        layout.addLayout(toolbar)

        card = QFrame()
        card.setObjectName("readerCard")
        sheet = QVBoxLayout(card)
        sheet.setContentsMargins(24, 20, 24, 20)
        sheet.setSpacing(10)

        meta = QHBoxLayout()
        meta.setSpacing(12)
        self.type_box = QComboBox()
        self.type_box.setCursor(Qt.CursorShape.PointingHandCursor)
        for note_type in NOTE_TYPES:
            self.type_box.addItem(_(_TYPE_LABELS[note_type]), note_type)
        meta.addWidget(self.type_box)
        meta.addStretch()
        self.date_label = QLabel()
        self.date_label.setObjectName("mutedLabel")
        meta.addWidget(self.date_label)
        sheet.addLayout(meta)

        self.title_edit = QLineEdit()
        self.title_edit.setObjectName("titleEdit")
        self.title_edit.setPlaceholderText(_("Title"))
        sheet.addWidget(self.title_edit)

        self.tags_edit = QLineEdit()
        self.tags_edit.setObjectName("tagsEdit")
        self.tags_edit.setPlaceholderText(_("Tags, separated by commas"))
        sheet.addWidget(self.tags_edit)

        separator = QFrame()
        separator.setObjectName("separator")
        separator.setFixedHeight(1)
        sheet.addWidget(separator)

        self.body_edit = QPlainTextEdit()
        self.body_edit.setObjectName("bodyEdit")
        self.body_edit.document().setDocumentMargin(0)  # type: ignore[union-attr]
        sheet.addWidget(self.body_edit, stretch=1)

        layout.addWidget(card, stretch=1)

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
        color, label = DICTATE_STATES[state]
        self.btn_dictate.setText(_(label))
        self.btn_dictate.setIcon(ui.get_qicon(color))
        self.btn_dictate.setEnabled(state != PROCESSING)
        self.btn_delete.setEnabled(state == IDLE)


class MainWindow(QMainWindow):
    """Two-page window: the notes timeline and the note reader."""

    dictate_clicked = pyqtSignal(object)
    note_edited = pyqtSignal(object)
    delete_requested = pyqtSignal(object)
    search_requested = pyqtSignal(str)
    settings_clicked = pyqtSignal()

    def __init__(
        self,
        columns: int = DEFAULT_COLUMNS,
        type_colors: dict[str, str] = ui.DEFAULT_TYPE_COLORS,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Eloquent Notes")
        self.setWindowIcon(ui.get_app_icon())
        self.resize(960, 880)
        self.setMinimumWidth(720)
        self._dark = ui.is_dark_theme()
        self.setStyleSheet(ui.window_stylesheet(ui.current_theme()))

        self.timeline = TimelinePage(columns=columns, type_colors=type_colors)
        self.reader = ReaderPage()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.timeline)
        self.stack.addWidget(self.reader)
        self.setCentralWidget(self.stack)

        self.timeline.settings_clicked.connect(self.settings_clicked)
        self.timeline.search_requested.connect(self.search_requested)
        self.timeline.note_opened.connect(self.show_note)
        self.reader.back_clicked.connect(self.show_timeline)
        self.reader.dictate_clicked.connect(self._on_dictate)
        self.reader.copy_clicked.connect(self._on_copy)
        self.reader.delete_clicked.connect(self._on_delete)

    def changeEvent(self, event: QEvent | None) -> None:
        if event is not None and event.type() == QEvent.Type.PaletteChange:
            dark = ui.is_dark_theme()
            if dark != self._dark:
                self._dark = dark
                self.setStyleSheet(ui.window_stylesheet(ui.current_theme()))
                self.timeline._render()
        super().changeEvent(event)

    def set_columns(self, columns: int) -> None:
        self.timeline.set_columns(columns)

    def set_type_colors(self, type_colors: dict[str, str]) -> None:
        self.timeline.set_type_colors(type_colors)

    def set_notes(self, notes: list[Note]) -> None:
        self.timeline.set_notes(notes)
        if self.stack.currentWidget() is self.reader:
            for note in notes:
                if note.path == self.reader.note.path:
                    self.reader.show_note(note)
                    break

    def show_search_results(self, query: str, results: list[Note]) -> None:
        self.timeline.show_search_results(query, results)

    def show_search_error(self, query: str, message: str) -> None:
        self.timeline.show_search_error(query, message)

    def set_state(self, state: str) -> None:
        self.reader.set_state(state)

    def show_note(self, note: Note) -> None:
        self.save_open_note()
        self.stack.setCurrentWidget(self.reader)
        self.reader.show_note(note)

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
        confirm = QMessageBox.question(
            self,
            _("Delete Note"),
            _("Move “{title}” to the trash?").format(title=note.title),
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.stack.setCurrentWidget(self.timeline)
            self.delete_requested.emit(note)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self.save_open_note()
        super().closeEvent(event)
