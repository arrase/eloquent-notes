"""Unit tests for eloquent_notes.notes (Markdown note storage)."""

from datetime import datetime, timedelta, timezone

from eloquent_notes import notes


def test_create_note_round_trip(tmp_path):
    note = notes.create_note(tmp_path, "Reunión con Marta", "decision", ["equipo", "lanzamiento"], "Lanzamos el viernes.")

    [loaded] = notes.load_notes(tmp_path)

    assert loaded == note
    assert note.path.parent == tmp_path
    assert note.path.name == f"{note.created:%Y-%m-%d %H%M%S} Reunión con Marta.md"
    assert note.created.tzinfo is not None
    assert note.created.microsecond == 0


def test_note_file_is_readable_markdown(tmp_path):
    note = notes.create_note(tmp_path, "Idea", "idea", ["app"], "- one\n- two")

    text = note.path.read_text(encoding="utf-8")

    assert text.startswith("---\ntitle: Idea\n")
    assert "type: idea\ntags:\n- app\n---\n- one\n- two\n" in text


def test_filename_strips_unsafe_characters(tmp_path):
    note = notes.create_note(tmp_path, 'What: is/this? <[#^]> "x" | y*', "question", [], "")

    assert note.path.name.endswith(" What isthis x y.md")
    assert note.path.exists()


def test_filename_title_is_truncated(tmp_path):
    note = notes.create_note(tmp_path, "word " * 40, "note", [], "")

    assert len(note.path.stem) == len("2026-01-01 000000 ") + 80 - 1


def test_load_notes_newest_first(tmp_path):
    base = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
    for offset, title in [(0, "oldest"), (2, "newest"), (1, "middle")]:
        notes.save_note(notes.Note(tmp_path / f"{title}.md", title, base + timedelta(hours=offset), "note", [], ""))

    assert [note.title for note in notes.load_notes(tmp_path)] == ["newest", "middle", "oldest"]


def test_load_notes_missing_folder_is_empty(tmp_path):
    assert notes.load_notes(tmp_path / "missing") == []


def test_load_notes_ignores_foreign_files(tmp_path, caplog):
    (tmp_path / "plain.md").write_text("# Just markdown\n", encoding="utf-8")
    (tmp_path / "other.md").write_text("---\naliases: [x]\n---\nbody\n", encoding="utf-8")
    (tmp_path / "broken.md").write_text("---\ntitle: [unclosed\n---\n", encoding="utf-8")
    (tmp_path / "list.md").write_text("---\n- a\n---\n", encoding="utf-8")
    (tmp_path / "badtype.md").write_text(
        "---\ntitle: T\ncreated: 2026-10-22T10:00:00+02:00\ntype: memo\n---\n", encoding="utf-8",
    )
    (tmp_path / "notes.txt").write_text("not markdown", encoding="utf-8")
    notes.create_note(tmp_path, "Mine", "task", [], "")

    assert [note.title for note in notes.load_notes(tmp_path)] == ["Mine"]
    assert caplog.text.count("Ignoring") == 5


def test_load_notes_accepts_edits_from_other_tools(tmp_path):
    """Obsidian may unquote dates, drop tags or capitalize the type."""
    (tmp_path / "edited.md").write_text(
        "---\ntitle: Edited\ncreated: 2026-10-22 10:00:00\ntype: Task\n---\n\nBody text\n\n",
        encoding="utf-8",
    )

    [note] = notes.load_notes(tmp_path)

    assert note.type == "task"
    assert note.tags == []
    assert note.body == "Body text"
    assert note.created.tzinfo is not None
    assert (note.created.hour, note.created.minute) == (10, 0)


def test_save_note_rewrites_in_place(tmp_path):
    note = notes.create_note(tmp_path, "Old", "note", ["a"], "Body")
    note.title, note.type, note.tags, note.body = "New title", "task", ["b"], "New body"

    notes.save_note(note)

    [loaded] = notes.load_notes(tmp_path)
    assert loaded == note
    assert loaded.path == note.path


def test_append_to_note(tmp_path):
    note = notes.create_note(tmp_path, "List", "task", [], "Buy milk.")

    notes.append_to_note(note, "Also eggs.")

    assert note.body == "Buy milk.\n\nAlso eggs."
    assert notes.load_notes(tmp_path)[0].body == "Buy milk.\n\nAlso eggs."


def test_append_to_empty_note(tmp_path):
    note = notes.create_note(tmp_path, "Empty", "note", [], "")

    notes.append_to_note(note, "First words.")

    assert note.body == "First words."


def test_markdown_property(tmp_path):
    note = notes.create_note(tmp_path, "Title", "note", [], "Body")

    assert note.markdown == "# Title\n\nBody"


def test_parse_and_normalize_tags():
    assert notes.parse_tags(" #Work, home ,, work,  #  ") == ["work", "home"]
    assert notes.parse_tags("") == []
    assert notes.normalize_tags(["#Rust", "rust", " CLI "]) == ["rust", "cli"]
