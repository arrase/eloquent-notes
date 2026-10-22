"""Unit tests for eloquent_notes.window (timeline and reader)."""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QGuiApplication, QMouseEvent
from PyQt6.QtWidgets import QLabel, QMessageBox

from eloquent_notes import notes
from eloquent_notes.window import MainWindow, NoteCard, day_label, format_time


@pytest.fixture
def sample_notes(tmp_path):
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
            tmp_path / f"{index}.md", title, now - timedelta(days=days, minutes=index), note_type, tags, body,
        )
        notes.save_note(note)
        result.append(note)
    return result


@pytest.fixture
def window(qapp, sample_notes):
    win = MainWindow()
    win.set_notes(sample_notes)
    yield win
    win.close()


def list_widgets(win):
    grid = win.timeline._grid
    return [grid.itemAt(i).widget() for i in range(grid.count()) if grid.itemAt(i).widget() is not None]


def grid_positions(win):
    grid = win.timeline._grid
    return [grid.getItemPosition(i) for i in range(grid.count()) if grid.itemAt(i).widget() is not None]


def card_titles(win):
    return [w.note.title for w in list_widgets(win) if isinstance(w, NoteCard)]


def list_texts(win):
    return [w.text() for w in list_widgets(win) if isinstance(w, QLabel)]


def click(widget):
    for event_type in (QMouseEvent.Type.MouseButtonPress, QMouseEvent.Type.MouseButtonRelease):
        widget.event(QMouseEvent(
            event_type, QPointF(5, 5), QPointF(5, 5),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        ))


def chip(win, label):
    return next(button for button in win.timeline.type_filter.buttons() if button.text() == label)


# --- Helpers -----------------------------------------------------------------


def test_day_label():
    today = date(2026, 10, 22)
    assert day_label(today, today) == "Today"
    assert day_label(date(2026, 10, 21), today) == "Yesterday"
    assert day_label(date(2026, 10, 19), today) == "Monday, 19 October"
    assert day_label(date(2025, 1, 3), today) == "Friday, 3 January 2025"


def test_format_time_uses_english_local_time():
    moment = datetime(2026, 10, 22, 21, 5).astimezone()
    assert format_time(moment, "dddd, d MMM yyyy, HH:mm") == "Thursday, 22 Oct 2026, 21:05"


# --- Timeline ------------------------------------------------------------------


def test_timeline_groups_notes_by_day(window):
    old_day = (datetime.now() - timedelta(days=400)).date()

    assert card_titles(window) == ["Launch decision", "Buy milk", "Offline mode", "Old memo"]
    assert list_texts(window) == ["TODAY", "YESTERDAY", day_label(old_day, date.today()).upper()]
    assert grid_positions(window) == [
        (0, 0, 1, 2),
        (1, 0, 1, 1),
        (1, 1, 1, 1),
        (2, 0, 1, 2),
        (3, 0, 1, 1),
        (4, 0, 1, 2),
        (5, 0, 1, 1),
    ]


def test_timeline_columns_can_be_configured(window):
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


def test_empty_timeline_invites_recording(qapp):
    win = MainWindow()
    win.set_notes([])
    assert list_texts(win) == ["No notes yet. Click the microphone to record your first one."]
    win.close()


def test_type_filter(window):
    chip(window, "Ideas").click()
    assert card_titles(window) == ["Offline mode"]

    chip(window, "Questions").click()
    assert list_texts(window) == ["No notes match these filters."]

    chip(window, "All").click()
    assert len(card_titles(window)) == 4


def test_tag_filter_lists_every_tag(window):
    combo = window.timeline.tag_filter
    assert [combo.itemText(i) for i in range(combo.count())] == ["All tags", "#app", "#home", "#work"]

    window.timeline.select_tag("work")
    assert card_titles(window) == ["Launch decision", "Offline mode"]

    chip(window, "Ideas").click()
    assert card_titles(window) == ["Offline mode"]


def test_tag_selection_survives_refresh_and_resets_when_gone(window, sample_notes):
    window.timeline.select_tag("home")
    window.set_notes(sample_notes)
    assert window.timeline.tag_filter.currentData() == "home"

    window.set_notes(sample_notes[2:])
    assert window.timeline.tag_filter.currentData() == ""


def test_clicking_tag_link_filters(window):
    card = next(w for w in list_widgets(window) if isinstance(w, NoteCard) and w.note.title == "Buy milk")
    card.tag_clicked.emit("home")
    assert card_titles(window) == ["Buy milk"]


def test_card_shows_type_preview_and_tags(window):
    card = next(w for w in list_widgets(window) if isinstance(w, NoteCard) and w.note.title == "Offline mode")
    texts = [label.text() for label in card.findChildren(QLabel)]

    assert "● Idea" in texts[0]
    assert texts[1:3] == ["Offline mode", "Queue recordings locally."]
    assert "#work" in texts[3] and "#app" in texts[3]


def test_card_preview_is_truncated(qapp, tmp_path):
    note = notes.Note(tmp_path / "x.md", "Long", datetime.now().astimezone(), "note", [], "word " * 100)
    card = NoteCard(note, show_date=True)
    preview = card.findChildren(QLabel)[2].text()
    assert preview.endswith("…")
    assert len(preview) <= 181


def test_card_title_is_plain_text(qapp, tmp_path):
    note = notes.Note(tmp_path / "x.md", "<b>bold</b>", datetime.now().astimezone(), "note", [], "")
    card = NoteCard(note, show_date=False)
    title = card.findChildren(QLabel)[1]
    assert title.textFormat() == Qt.TextFormat.PlainText


def test_clicking_card_opens_reader(window):
    card = next(w for w in list_widgets(window) if isinstance(w, NoteCard))

    click(card)

    assert window.stack.currentWidget() is window.reader
    assert window.reader.title_edit.text() == "Launch decision"


def test_record_button_and_state(window):
    recorded = MagicMock()
    window.record_clicked.connect(recorded)

    window.timeline.record_button.click()
    recorded.assert_called_once()

    window.set_state("RECORDING")
    assert window.timeline.record_status.text() == "Recording… click to stop"
    assert window.reader.btn_dictate.text() == "Stop dictation"

    window.set_state("PROCESSING")
    assert not window.timeline.record_button.isEnabled()
    assert not window.reader.btn_dictate.isEnabled()

    window.set_state("IDLE")
    assert window.timeline.record_button.isEnabled()
    assert window.reader.btn_dictate.text() == "Add dictation"


def test_settings_button(window):
    clicked = MagicMock()
    window.settings_clicked.connect(clicked)
    next(b for b in window.timeline.findChildren(type(window.timeline.record_button)) if b.text() == "Settings").click()
    clicked.assert_called_once()


# --- Search ----------------------------------------------------------------------


def test_search_flow(window, sample_notes):
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


def test_blank_search_is_ignored(window):
    requested = MagicMock()
    window.search_requested.connect(requested)
    window.timeline.search.setText("   ")
    window.timeline.search.returnPressed.emit()
    requested.assert_not_called()


def test_search_without_matches_and_errors(window):
    window.timeline.search.setText("nothing")
    window.timeline.search.returnPressed.emit()
    window.show_search_results("nothing", [])
    assert list_texts(window) == ["No matching notes."]

    window.timeline.search.setText("broken")
    window.timeline.search.returnPressed.emit()
    window.show_search_error("other", "ignored")
    window.show_search_error("broken", "Ollama is down")
    assert list_texts(window) == ["Search failed: Ollama is down"]


def test_search_results_follow_refreshed_notes(window, sample_notes):
    window.timeline.search.setText("work")
    window.timeline.search.returnPressed.emit()
    window.show_search_results("work", [sample_notes[0], sample_notes[2]])

    renamed = notes.Note(sample_notes[0].path, "Renamed", sample_notes[0].created, "decision", [], "")
    window.set_notes([renamed, *sample_notes[1:2]])

    assert card_titles(window) == ["Renamed"]


# --- Reader ----------------------------------------------------------------------


def test_reader_shows_all_fields(window, sample_notes):
    window.show_note(sample_notes[2])
    reader = window.reader

    assert reader.type_box.currentData() == "idea"
    assert reader.title_edit.text() == "Offline mode"
    assert reader.tags_edit.text() == "work, app"
    assert reader.body_edit.toPlainText() == "Queue recordings locally."
    assert reader.date_label.text() == format_time(sample_notes[2].created, "dddd, d MMMM yyyy, HH:mm")


def test_back_saves_edits(window, sample_notes):
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
        "Buy milk and bread", "reminder", ["home", "shopping"], "Milk, eggs and bread.",
    )
    assert window.stack.currentWidget() is window.timeline


def test_back_without_changes_does_not_save(window, sample_notes):
    edited = MagicMock()
    window.note_edited.connect(edited)
    window.show_note(sample_notes[0])
    window.reader.back_clicked.emit()
    edited.assert_not_called()


def test_closing_window_saves_open_note(window, sample_notes):
    edited = MagicMock()
    window.note_edited.connect(edited)
    window.show_note(sample_notes[0])
    window.reader.body_edit.setPlainText("Changed")
    window.close()
    edited.assert_called_once_with(sample_notes[0])


def test_dictate_saves_then_emits_note(window, sample_notes):
    events = []
    window.note_edited.connect(lambda note: events.append(("edited", note.title)))
    window.dictate_clicked.connect(lambda note: events.append(("dictate", note.title)))
    window.show_note(sample_notes[0])
    window.reader.title_edit.setText("Edited")

    window.reader.btn_dictate.click()

    assert events == [("edited", "Edited"), ("dictate", "Edited")]


def test_copy_puts_markdown_on_clipboard(window, sample_notes):
    window.show_note(sample_notes[0])
    window.reader.copy_clicked.emit()
    assert QGuiApplication.clipboard().text() == "# Launch decision\n\nShip on Friday."


def test_delete_requires_confirmation(window, sample_notes):
    deleted = MagicMock()
    window.delete_requested.connect(deleted)
    window.show_note(sample_notes[0])

    with patch("eloquent_notes.window.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
        window.reader.delete_clicked.emit()
    deleted.assert_not_called()
    assert window.stack.currentWidget() is window.reader

    with patch("eloquent_notes.window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
        window.reader.delete_clicked.emit()
    deleted.assert_called_once_with(sample_notes[0])
    assert window.stack.currentWidget() is window.timeline
