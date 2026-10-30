"""Unit tests for eloquent_notes.window (timeline and reader)."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QGuiApplication, QMouseEvent
from PyQt6.QtWidgets import QAbstractButton, QApplication, QLabel, QMessageBox, QPushButton, QWidget

from eloquent_notes import notes, ui
from eloquent_notes.window import PAGE_MARGIN, MainWindow, NoteCard, day_label, format_time


@pytest.fixture
def sample_notes(tmp_path: Path) -> list[notes.Note]:
    now = datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
    specs = [
        (0, "Launch decision", "decision", ["work"], "Ship on Friday."),
        (0, "Buy milk", "task", ["home"], "Milk and eggs."),
        (1, "Offline mode", "idea", ["work", "app"], "Queue recordings locally."),
        (400, "Old memo", "note", [], ""),
    ]
    result = []
    for index, (days, title, note_type, tags, body) in enumerate(specs):
        note = notes.Note(
            tmp_path / f"{index}.md",
            title,
            now - timedelta(days=days, minutes=index),
            note_type,
            tags,
            body,
        )
        notes.save_note(note)
        result.append(note)
    return result


@pytest.fixture
def window(qapp: QApplication, sample_notes: list[notes.Note]) -> Iterator[MainWindow]:
    del qapp
    win = MainWindow()
    win.set_notes(sample_notes)
    yield win
    win.close()


def list_widgets(win: MainWindow) -> list[QWidget]:
    grid = win.timeline._grid
    result: list[QWidget] = []
    for i in range(grid.count()):
        item = grid.itemAt(i)
        if item is not None:
            widget = item.widget()
            if widget is not None:
                result.append(widget)
    return result


def grid_positions(win: MainWindow) -> list[tuple[int | None, int | None, int | None, int | None]]:
    grid = win.timeline._grid
    return [
        grid.getItemPosition(i)
        for i in range(grid.count())
        if (item := grid.itemAt(i)) is not None and item.widget() is not None
    ]


def card_titles(win: MainWindow) -> list[str]:
    return [w.note.title for w in list_widgets(win) if isinstance(w, NoteCard)]


def list_texts(win: MainWindow) -> list[str]:
    return [w.text() for w in list_widgets(win) if isinstance(w, QLabel)]


def click(widget: QWidget) -> None:
    for event_type in (QMouseEvent.Type.MouseButtonPress, QMouseEvent.Type.MouseButtonRelease):
        widget.event(
            QMouseEvent(
                event_type,
                QPointF(5, 5),
                QPointF(5, 5),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )


def chip(win: MainWindow, label: str) -> QAbstractButton:
    return next(button for button in win.timeline.type_filter.buttons() if button.text() == label)


# --- Helpers -----------------------------------------------------------------


def test_day_label() -> None:
    today = date(2026, 10, 22)
    assert day_label(today, today) == "Today"
    assert day_label(date(2026, 10, 21), today) == "Yesterday"
    assert day_label(date(2026, 10, 19), today) == "Monday, 19 October"
    assert day_label(date(2025, 1, 3), today) == "Friday, 3 January 2025"


def test_format_time_uses_english_local_time() -> None:
    moment = datetime.fromisoformat("2026-10-22T21:05:00").astimezone()
    assert format_time(moment, "dddd, d MMM yyyy, HH:mm") == "Thursday, 22 Oct 2026, 21:05"


# --- Timeline ------------------------------------------------------------------


def test_timeline_groups_notes_by_day(window: MainWindow) -> None:
    today = datetime.now().astimezone().date()
    old_day = today - timedelta(days=400)

    assert card_titles(window) == ["Launch decision", "Buy milk", "Offline mode", "Old memo"]
    assert list_texts(window) == ["TODAY", "YESTERDAY", day_label(old_day, today).upper()]
    assert grid_positions(window) == [
        (0, 0, 1, 2),
        (1, 0, 1, 1),
        (1, 1, 1, 1),
        (2, 0, 1, 2),
        (3, 0, 1, 1),
        (4, 0, 1, 2),
        (5, 0, 1, 1),
    ]


def test_timeline_columns_can_be_configured(window: MainWindow) -> None:
    window.set_columns(2)  # unchanged column count is a no-op
    window.set_columns(1)
    assert grid_positions(window) == [
        (0, 0, 1, 1),
        (1, 0, 1, 1),
        (2, 0, 1, 1),
        (3, 0, 1, 1),
        (4, 0, 1, 1),
        (5, 0, 1, 1),
        (6, 0, 1, 1),
    ]


def test_timeline_type_colors_can_be_configured(window: MainWindow) -> None:
    window.set_type_colors(dict(ui.DEFAULT_TYPE_COLORS))
    window.set_type_colors({**ui.DEFAULT_TYPE_COLORS, "decision": "#112233"})
    card = next(w for w in list_widgets(window) if isinstance(w, NoteCard) and w.note.title == "Launch decision")
    assert "#112233" in card.findChildren(QLabel)[0].text()


def test_empty_timeline_invites_recording(qapp: QApplication) -> None:
    del qapp
    win = MainWindow()
    win.set_notes([])
    assert not win.windowIcon().isNull()
    assert list_texts(win) == ["No notes yet. Click the tray icon to record your first one."]
    win.close()


def test_type_filter(window: MainWindow) -> None:
    chip(window, "Ideas").click()
    assert card_titles(window) == ["Offline mode"]

    chip(window, "Questions").click()
    assert list_texts(window) == ["No notes match these filters."]

    chip(window, "All").click()
    assert len(card_titles(window)) == 4


def test_tag_filter_lists_every_tag(window: MainWindow) -> None:
    combo = window.timeline.tag_filter
    assert [combo.itemText(i) for i in range(combo.count())] == ["All tags", "#app", "#home", "#work"]

    window.timeline.select_tag("work")
    assert card_titles(window) == ["Launch decision", "Offline mode"]

    chip(window, "Ideas").click()
    assert card_titles(window) == ["Offline mode"]


def test_tag_selection_survives_refresh_and_resets_when_gone(
    window: MainWindow,
    sample_notes: list[notes.Note],
) -> None:
    window.timeline.select_tag("home")
    window.set_notes(sample_notes)
    assert window.timeline.tag_filter.currentData() == "home"

    window.set_notes(sample_notes[2:])
    assert window.timeline.tag_filter.currentData() == ""


def test_clicking_tag_link_filters(window: MainWindow) -> None:
    card = next(w for w in list_widgets(window) if isinstance(w, NoteCard) and w.note.title == "Buy milk")
    card.tag_clicked.emit("home")
    assert card_titles(window) == ["Buy milk"]


def test_card_shows_type_preview_and_tags(window: MainWindow) -> None:
    card = next(w for w in list_widgets(window) if isinstance(w, NoteCard) and w.note.title == "Offline mode")
    texts = [label.text() for label in card.findChildren(QLabel)]

    assert "● Idea" in texts[0]
    assert texts[1:3] == ["Offline mode", "Queue recordings locally."]
    assert "#work" in texts[3]
    assert "#app" in texts[3]


def test_card_preview_is_truncated(qapp: QApplication, tmp_path: Path) -> None:
    del qapp
    note = notes.Note(tmp_path / "x.md", "Long", datetime.now().astimezone(), "note", [], "word " * 100)
    card = NoteCard(note, show_date=True, type_color=ui.DEFAULT_TYPE_COLORS["note"])
    preview = card.findChildren(QLabel)[2].text()
    assert preview.endswith("…")
    assert len(preview) <= 181


def test_card_title_is_plain_text(qapp: QApplication, tmp_path: Path) -> None:
    del qapp
    note = notes.Note(tmp_path / "x.md", "<b>bold</b>", datetime.now().astimezone(), "note", [], "")
    card = NoteCard(note, show_date=False, type_color=ui.DEFAULT_TYPE_COLORS["note"])
    title = card.findChildren(QLabel)[1]
    assert title.textFormat() == Qt.TextFormat.PlainText


def test_clicking_card_opens_reader(window: MainWindow) -> None:
    card = next(w for w in list_widgets(window) if isinstance(w, NoteCard))

    click(card)

    assert window.stack.currentWidget() is window.reader
    assert window.reader.title_edit.text() == "Launch decision"


def test_set_state_updates_dictate_and_delete_buttons(window: MainWindow) -> None:
    window.set_state("RECORDING")
    assert window.reader.btn_dictate.text() == "Stop dictation"
    assert window.reader.btn_dictate.isEnabled()
    assert not window.reader.btn_delete.isEnabled()

    window.set_state("PROCESSING")
    assert window.reader.btn_dictate.text() == "Processing…"
    assert not window.reader.btn_dictate.isEnabled()
    assert not window.reader.btn_delete.isEnabled()

    window.set_state("IDLE")
    assert window.reader.btn_dictate.text() == "Add dictation"
    assert window.reader.btn_dictate.isEnabled()
    assert window.reader.btn_delete.isEnabled()


def test_settings_button(window: MainWindow) -> None:
    clicked = MagicMock()
    window.settings_clicked.connect(clicked)
    next(b for b in window.timeline.findChildren(QPushButton) if b.text() == "Settings").click()
    clicked.assert_called_once()


# --- Search ----------------------------------------------------------------------


def test_search_flow(window: MainWindow, sample_notes: list[notes.Note]) -> None:
    requested = MagicMock()
    window.search_requested.connect(requested)

    window.timeline.search.setText("  shopping  ")
    window.timeline.search.returnPressed.emit()

    requested.assert_called_once_with("shopping")
    assert list_texts(window) == ["Searching…"]

    window.show_search_results("stale query", sample_notes)
    assert list_texts(window) == ["Searching…"]

    window.show_search_results("shopping", [sample_notes[1], sample_notes[0]])
    assert card_titles(window) == ["Buy milk", "Launch decision"]
    assert list_texts(window) == ["2 results"]

    chip(window, "Tasks").click()
    assert card_titles(window) == ["Buy milk"]
    assert list_texts(window) == ["1 result"]

    window.timeline.search.clear()
    assert len(card_titles(window)) == 1  # back to the timeline, still filtered by type
    assert "TODAY" in list_texts(window)


def test_blank_search_is_ignored(window: MainWindow) -> None:
    requested = MagicMock()
    window.search_requested.connect(requested)
    window.timeline.search.setText("   ")
    window.timeline.search.returnPressed.emit()
    requested.assert_not_called()


def test_search_without_matches_and_errors(window: MainWindow) -> None:
    window.timeline.search.setText("nothing")
    window.timeline.search.returnPressed.emit()
    window.show_search_results("nothing", [])
    assert list_texts(window) == ["No matching notes."]

    window.timeline.search.setText("broken")
    window.timeline.search.returnPressed.emit()
    window.show_search_error("other", "ignored")
    window.show_search_error("broken", "Ollama is down")
    assert list_texts(window) == ["Search failed: Ollama is down"]

    # Error persists across filter, column, and theme re-renders until search is cleared or re-run
    chip(window, "Tasks").click()
    assert list_texts(window) == ["Search failed: Ollama is down"]
    window.set_columns(1)
    assert list_texts(window) == ["Search failed: Ollama is down"]
    chip(window, "All").click()
    window.timeline.search.clear()
    assert "TODAY" in list_texts(window)


def test_search_results_follow_refreshed_notes(window: MainWindow, sample_notes: list[notes.Note]) -> None:
    window.timeline.search.setText("work")
    window.timeline.search.returnPressed.emit()
    window.show_search_results("work", [sample_notes[0], sample_notes[2]])

    renamed = notes.Note(sample_notes[0].path, "Renamed", sample_notes[0].created, "decision", [], "")
    window.set_notes([renamed, *sample_notes[1:2]])

    assert card_titles(window) == ["Renamed"]


def test_show_search_results_reconciles_with_current_notes(
    window: MainWindow,
    sample_notes: list[notes.Note],
) -> None:
    window.timeline.search.setText("work")
    window.timeline.search.returnPressed.emit()

    # While search is in flight, note 0 is renamed and note 2 is deleted.
    renamed = notes.Note(sample_notes[0].path, "Updated while searching", sample_notes[0].created, "decision", [], "")
    window.set_notes([renamed, sample_notes[1]])

    # Search completes with stale Note instances from before the edit/deletion.
    window.show_search_results("work", [sample_notes[0], sample_notes[2]])

    assert card_titles(window) == ["Updated while searching"]
    assert window.timeline._results == [renamed]


# --- Reader ----------------------------------------------------------------------


def test_reader_shows_all_fields(window: MainWindow, sample_notes: list[notes.Note]) -> None:
    window.show_note(sample_notes[2])
    reader = window.reader

    assert reader.type_box.currentData() == "idea"
    assert reader.title_edit.text() == "Offline mode"
    assert reader.tags_edit.text() == "work, app"
    assert reader.body_edit.toPlainText() == "Queue recordings locally."
    assert reader.date_label.text() == format_time(sample_notes[2].created, "dddd, d MMMM yyyy, HH:mm")


def test_set_notes_refreshes_open_reader_note(window: MainWindow, sample_notes: list[notes.Note]) -> None:
    window.show_note(sample_notes[0])
    updated = notes.Note(
        sample_notes[0].path,
        "Updated title",
        sample_notes[0].created,
        "task",
        ["updated"],
        "New body.",
    )
    window.set_notes([updated, *sample_notes[1:]])

    assert window.reader.note is updated
    assert window.reader.title_edit.text() == "Updated title"
    assert window.reader.type_box.currentData() == "task"
    assert window.reader.tags_edit.text() == "updated"
    assert window.reader.body_edit.toPlainText() == "New body."


def test_set_notes_preserves_unsaved_reader_edits(window: MainWindow, sample_notes: list[notes.Note]) -> None:
    window.show_note(sample_notes[0])
    window.reader.title_edit.setText("In-progress title")
    window.reader.body_edit.setPlainText("In-progress body")

    stale = notes.Note(
        sample_notes[0].path,
        "Launch decision",
        sample_notes[0].created,
        "decision",
        ["work"],
        "Ship on Friday.",
    )
    window.set_notes([stale, *sample_notes[1:]])

    assert window.reader.title_edit.text() == "In-progress title"
    assert window.reader.body_edit.toPlainText() == "In-progress body"

    edited = MagicMock()
    window.note_edited.connect(edited)
    window.show_timeline()
    edited.assert_called_once()
    assert sample_notes[0].title == "In-progress title"
    assert sample_notes[0].body == "In-progress body"


def test_set_notes_returns_to_timeline_when_open_note_disappears(
    window: MainWindow,
    sample_notes: list[notes.Note],
) -> None:
    window.show_note(sample_notes[0])
    assert window.stack.currentWidget() is window.reader

    window.set_notes(sample_notes[1:])
    assert window.stack.currentWidget() is window.timeline


def test_commit_rejects_empty_title_and_restores_original(
    window: MainWindow,
    sample_notes: list[notes.Note],
    tmp_path: Path,
) -> None:
    edited = MagicMock()
    window.note_edited.connect(edited)
    window.show_note(sample_notes[0])

    # Clearing only the title restores it without emitting note_edited.
    window.reader.title_edit.setText("   ")
    window.show_timeline()
    edited.assert_not_called()
    assert sample_notes[0].title == "Launch decision"
    assert window.reader.title_edit.text() == "Launch decision"

    # Clearing the title while editing the body keeps the original title and saves the body.
    window.show_note(sample_notes[0])
    window.reader.title_edit.setText("")
    window.reader.body_edit.setPlainText("Updated body with kept title.")
    window.show_timeline()
    edited.assert_called_once_with(sample_notes[0])
    assert sample_notes[0].title == "Launch decision"
    assert sample_notes[0].body == "Updated body with kept title."
    assert window.reader.title_edit.text() == "Launch decision"

    notes.save_note(sample_notes[0])
    loaded = notes.load_notes(tmp_path)
    assert any(n.path == sample_notes[0].path and n.title == "Launch decision" for n in loaded)


def test_copy_and_dictate_preserve_cursor_selection_and_undo(
    window: MainWindow,
    sample_notes: list[notes.Note],
    tmp_path: Path,
) -> None:
    def on_edited(note: notes.Note) -> None:
        notes.save_note(note)
        window.set_notes(notes.load_notes(tmp_path))

    window.note_edited.connect(on_edited)
    window.show_note(sample_notes[0])
    window.reader.tags_edit.setText("work, ")
    body_edit = window.reader.body_edit

    cursor = body_edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    cursor.insertText(" Extra text.")
    cursor.setPosition(0)
    cursor.setPosition(4, cursor.MoveMode.KeepAnchor)
    body_edit.setTextCursor(cursor)

    assert body_edit.document().isUndoAvailable()

    with patch.object(body_edit, "setPlainText", wraps=body_edit.setPlainText) as spy_set_plain:
        window.reader.copy_clicked.emit()
        window.reader.btn_dictate.click()

    spy_set_plain.assert_not_called()
    assert body_edit.document().isUndoAvailable()
    assert body_edit.textCursor().selectionStart() == 0
    assert body_edit.textCursor().selectionEnd() == 4
    assert window.reader.tags_edit.text() == "work, "


def test_show_note_resets_body_edit_when_switching_notes(
    window: MainWindow,
    sample_notes: list[notes.Note],
) -> None:
    window.show_note(sample_notes[0])
    cursor = window.reader.body_edit.textCursor()
    cursor.select(cursor.SelectionType.Document)
    cursor.insertText("   ")
    assert window.reader.body_edit.document().isUndoAvailable()
    window.show_timeline()

    # sample_notes[3] also has body == ""; opening it must reset text and undo stack.
    window.show_note(sample_notes[3])
    assert window.reader.body_edit.toPlainText() == ""
    assert not window.reader.body_edit.document().isUndoAvailable()


def test_back_saves_edits(window: MainWindow, sample_notes: list[notes.Note]) -> None:
    edited = MagicMock()
    window.note_edited.connect(edited)
    window.show_note(sample_notes[1])
    reader = window.reader

    reader.title_edit.setText("  Buy milk and bread ")
    reader.type_box.setCurrentIndex(reader.type_box.findData("reminder"))
    reader.tags_edit.setText("#Home, shopping")
    reader.body_edit.setPlainText("Milk, eggs and bread.\n")
    window.show_timeline()

    edited.assert_called_once_with(sample_notes[1])
    note = sample_notes[1]
    assert (note.title, note.type, note.tags, note.body) == (
        "Buy milk and bread",
        "reminder",
        ["home", "shopping"],
        "Milk, eggs and bread.",
    )
    assert window.stack.currentWidget() is window.timeline


def test_back_without_changes_does_not_save(window: MainWindow, sample_notes: list[notes.Note]) -> None:
    edited = MagicMock()
    window.note_edited.connect(edited)
    window.show_note(sample_notes[0])
    window.reader.back_clicked.emit()
    edited.assert_not_called()


def test_closing_window_saves_open_note(window: MainWindow, sample_notes: list[notes.Note]) -> None:
    edited = MagicMock()
    window.note_edited.connect(edited)
    window.show_note(sample_notes[0])
    window.reader.body_edit.setPlainText("Changed")
    window.close()
    edited.assert_called_once_with(sample_notes[0])


def test_dictate_saves_then_emits_note(window: MainWindow, sample_notes: list[notes.Note]) -> None:
    events: list[tuple[str, str]] = []
    window.note_edited.connect(lambda note: events.append(("edited", note.title)))
    window.dictate_clicked.connect(lambda note: events.append(("dictate", note.title)))
    window.show_note(sample_notes[0])
    window.reader.title_edit.setText("Edited")

    window.reader.btn_dictate.click()

    assert events == [("edited", "Edited"), ("dictate", "Edited")]


def test_copy_puts_markdown_on_clipboard(window: MainWindow, sample_notes: list[notes.Note]) -> None:
    window.show_note(sample_notes[0])
    window.reader.copy_clicked.emit()
    assert QGuiApplication.clipboard().text() == "# Launch decision\n\nShip on Friday."


def test_delete_requires_confirmation(window: MainWindow, sample_notes: list[notes.Note]) -> None:
    events: list[tuple[str, str]] = []
    window.note_edited.connect(lambda note: events.append(("edited", note.title)))
    deleted = MagicMock()
    window.delete_requested.connect(deleted)
    window.show_note(sample_notes[0])
    window.reader.title_edit.setText("Renamed before delete")

    with patch(
        "eloquent_notes.window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.No,
    ) as mock_question:
        window.reader.delete_clicked.emit()
    assert events == [("edited", "Renamed before delete")]
    assert "Renamed before delete" in mock_question.call_args.args[2]
    deleted.assert_not_called()
    assert window.stack.currentWidget() is window.reader

    with patch("eloquent_notes.window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
        window.reader.delete_clicked.emit()
    deleted.assert_called_once_with(sample_notes[0])
    assert window.stack.currentWidget() is window.timeline


def test_window_palette_change_updates_theme(qapp: QApplication, sample_notes: list[notes.Note]) -> None:
    del qapp
    with patch("eloquent_notes.ui.is_dark_theme", return_value=False):
        win = MainWindow()
        win.set_notes(sample_notes)

    assert win.styleSheet() == ui.window_stylesheet(ui.LIGHT_THEME)

    with patch("eloquent_notes.ui.is_dark_theme", return_value=True):
        win.changeEvent(QEvent(QEvent.Type.PaletteChange))

    assert win.styleSheet() == ui.window_stylesheet(ui.DARK_THEME)
    card = next(w for w in list_widgets(win) if isinstance(w, NoteCard) and w.note.title == "Launch decision")
    assert ui.DEFAULT_TYPE_COLORS["decision"] in card.findChildren(QLabel)[0].text()
    win.close()


def test_scroll_content_aligns_right_margin_with_scrollbar(window: MainWindow) -> None:
    scroll = window.timeline._scroll
    content = scroll.widget()
    assert content is not None
    scroll.resize(960, 600)
    content.resize(952, 600)
    content.resizeEvent(None)

    margins = content.column.contentsMargins()  # type: ignore[attr-defined]
    assert margins.left() == PAGE_MARGIN
    assert margins.right() == PAGE_MARGIN - 8


def test_timeline_preserves_vertical_scroll_position_on_rerender(
    window: MainWindow,
    sample_notes: list[notes.Note],
) -> None:
    scrollbar = window.timeline._scroll.verticalScrollBar()
    target_scroll = min(80, scrollbar.maximum())
    assert target_scroll > 0
    scrollbar.setValue(target_scroll)
    assert scrollbar.value() == target_scroll

    window.set_notes(sample_notes)
    assert scrollbar.value() == target_scroll
