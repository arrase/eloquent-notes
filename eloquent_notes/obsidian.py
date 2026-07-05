"""Obsidian note saving module.

Handles creating and appending dictation notes in an Obsidian vault,
supporting both standalone notes and daily-aggregated notes.
"""

import os
from datetime import datetime

import yaml


def _update_frontmatter_tags(content, new_tags):
    """Merge new_tags into an existing note's YAML frontmatter.

    Returns the full note content with updated frontmatter.
    If the note has no valid frontmatter, returns it unchanged.
    """
    if not content.startswith("---"):
        return content

    end_frontmatter = content.find("---", 3)
    if end_frontmatter == -1:
        return content

    frontmatter_str = content[3:end_frontmatter]
    frontmatter = yaml.safe_load(frontmatter_str) or {}

    existing_tags = frontmatter.get("tags", [])
    for tag in new_tags:
        if tag not in existing_tags:
            existing_tags.append(tag)
    frontmatter["tags"] = existing_tags

    yaml.SafeDumper.ignore_aliases = lambda self, data: True
    new_frontmatter = yaml.safe_dump(
        frontmatter, default_flow_style=False, sort_keys=False,
    )

    remainder = content[end_frontmatter + 3:]
    if remainder.startswith('\n'):
        remainder = remainder[1:]

    return f"---\n{new_frontmatter}---\n{remainder}"


def _save_daily(target_dir, date_str, time_str, text, tags,
                template_new, template_append):
    """Save a dictation entry to a daily-aggregated note.

    Creates a new daily note from template_new if none exists for today,
    or appends to the existing one using template_append.
    """
    note_path = os.path.join(target_dir, f"{date_str}.md")
    tags_formatted = "\n".join(f"  - {tag}" for tag in tags) if tags else ""

    if not os.path.exists(note_path):
        content = template_new.format(
            date=date_str, time=time_str, text=text, tags=tags_formatted,
        )
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(content)
        return note_path

    with open(note_path, "r", encoding="utf-8") as f:
        existing_content = f.read()

    updated_content = _update_frontmatter_tags(existing_content, tags)
    append_content = template_append.format(
        date=date_str, time=time_str, text=text,
    )

    with open(note_path, "w", encoding="utf-8") as f:
        f.write(updated_content)
        f.write("\n" + append_content)

    return note_path


def _save_standalone(target_dir, date_str, time_str, text, tags,
                     template):
    """Save a dictation as a standalone timestamped note."""
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    note_path = os.path.join(target_dir, f"Dictation-{timestamp}.md")
    tags_formatted = "\n".join(f"  - {tag}" for tag in tags) if tags else ""

    content = template.format(
        date=date_str, time=time_str, text=text, tags=tags_formatted,
    )
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(content)

    return note_path


def save_note(vault_path, folder, daily_notes, text, tags,
              template_standalone, template_daily_new,
              template_daily_append):
    """Save a dictation note to the Obsidian vault.

    Delegates to _save_daily or _save_standalone based on the
    daily_notes setting.
    """
    target_dir = os.path.join(os.path.expanduser(vault_path), folder)
    os.makedirs(target_dir, exist_ok=True)

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    if daily_notes:
        return _save_daily(
            target_dir, date_str, time_str, text, tags,
            template_daily_new, template_daily_append,
        )

    return _save_standalone(
        target_dir, date_str, time_str, text, tags, template_standalone,
    )
