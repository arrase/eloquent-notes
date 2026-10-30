"""Voice notes stored as plain Markdown files with YAML frontmatter.

Each note is one file in the notes folder named ``YYYY-MM-DD HHMMSS Title.md``.
The timestamp keeps file names unique and chronological, so editing a title
never renames its file. Files without the expected frontmatter are ignored,
which lets the folder live inside an Obsidian vault.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from eloquent_notes.config import atomic_write

logger = logging.getLogger("eloquent_notes.notes")

NOTE_TYPES = ("note", "task", "idea", "reminder", "question", "decision")

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
_UNSAFE_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|#^\[\]]')
_MAX_FILENAME_TITLE = 80


@dataclass
class Note:
    path: Path
    title: str
    created: datetime
    type: str
    tags: list[str]
    body: str

    @property
    def markdown(self) -> str:
        """Title and body as a standalone Markdown document."""
        return f"# {self.title}\n\n{self.body}"


def normalize_tags(raw_tags: list[str]) -> list[str]:
    """Lowercase tags, dropping '#' prefixes, blanks and duplicates."""
    tags: list[str] = []
    for raw in raw_tags:
        tag = raw.strip().lstrip("#").strip().lower()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def parse_tags(text: str) -> list[str]:
    """Split and normalize comma-separated tags."""
    return normalize_tags(text.split(","))


def _filename(created: datetime, title: str) -> str:
    safe_title = " ".join(_UNSAFE_FILENAME_CHARS_RE.sub("", title).split())[:_MAX_FILENAME_TITLE]
    return f"{created:%Y-%m-%d %H%M%S} {safe_title}".strip() + ".md"


def _render(note: Note) -> str:
    frontmatter = yaml.safe_dump(
        {
            "title": note.title,
            "created": note.created.isoformat(),
            "type": note.type,
            "tags": note.tags,
        },
        allow_unicode=True,
        sort_keys=False,
    )
    return f"---\n{frontmatter}---\n{note.body}\n"


def _parse_created(raw_created: object) -> datetime | None:
    if isinstance(raw_created, str):
        try:
            raw_created = datetime.fromisoformat(raw_created)
        except ValueError:
            return None
    return raw_created.astimezone() if isinstance(raw_created, datetime) else None


def _parse_frontmatter(text: str) -> tuple[dict[str, object], str] | None:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict) or not {"title", "created", "type"} <= meta.keys():
        return None
    return meta, match.group(2).strip()


def parse_note(path: Path) -> Note | None:
    """Parse a Markdown note file with YAML frontmatter, or return None if invalid."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    parsed = _parse_frontmatter(text)
    if parsed is None:
        return None
    meta, body = parsed
    title = meta["title"]
    note_type = str(meta["type"]).lower()
    created = _parse_created(meta["created"])
    raw_tags = meta.get("tags")
    if (
        not isinstance(title, str)
        or not title.strip()
        or note_type not in NOTE_TYPES
        or created is None
        or (raw_tags is not None and not isinstance(raw_tags, list))
    ):
        return None
    return Note(
        path=path,
        title=title.strip(),
        created=created,
        type=note_type,
        tags=normalize_tags([str(tag) for tag in raw_tags or []]),
        body=body,
    )


def load_notes(folder: Path) -> list[Note]:
    """Return every note in folder, newest first."""
    notes = []
    for path in folder.glob("*.md"):
        note = parse_note(path)
        if note is None:
            logger.warning("Ignoring %s: missing or invalid Eloquent Notes frontmatter", path)
            continue
        notes.append(note)
    return sorted(notes, key=lambda note: (note.created, note.path.name), reverse=True)


def create_note(folder: Path, title: str, note_type: str, tags: list[str], body: str) -> Note:
    """Write a new note timestamped now and return it."""
    title = title.strip()
    created = datetime.now().astimezone().replace(microsecond=0)
    path = folder / _filename(created, title)
    stem = path.stem
    suffix = 2
    while path.exists():
        path = folder / f"{stem} ({suffix}).md"
        suffix += 1
    note = Note(
        path=path,
        title=title,
        created=created,
        type=note_type,
        tags=normalize_tags(tags),
        body=body.strip(),
    )
    save_note(note)
    return note


def save_note(note: Note) -> None:
    """Write the note to its file atomically."""
    atomic_write(str(note.path), _render(note))


def append_to_note(note: Note, text: str) -> None:
    """Append dictated text to the note body as a new paragraph and save it."""
    note.body = f"{note.body.strip()}\n\n{text.strip()}".strip()
    save_note(note)
