"""Obsidian note saving module.

Handles creating and appending dictation notes in an Obsidian vault,
supporting both standalone notes and daily-aggregated notes.

Includes Python-side Obsidian Markdown formatting: callout wrapping
based on note type, wikilink injection, and vault topic scanning
for contextual wikilink suggestions.
"""

import os
import re
from datetime import datetime

import yaml

_CALLOUT_MAP = {
    "task": "todo",
    "idea": "tip",
    "reminder": "warning",
    "question": "question",
    "decision": "important",
}

_DATE_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class _NoAliasDumper(yaml.SafeDumper):
    """YAML SafeDumper that disables aliases without modifying global SafeDumper state."""

    def ignore_aliases(self, data):
        return True


class SafeDict(dict):
    """Dictionary subclass that retains missing format placeholders during string formatting."""

    def __missing__(self, key):
        return f"{{{key}}}"


def scan_vault_topics(vault_path, max_topics=200):
    """Scan the Obsidian vault for note basenames usable as wikilinks.

    Skips date-named files (e.g., 2024-01-15.md) and hidden directories starting with '.',
    and caps results to max_topics entries to limit prompt size.
    """
    if not vault_path:
        return []
    vault_path = os.path.expanduser(vault_path)
    if not os.path.isdir(vault_path):
        return []

    topics = set()
    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for filename in files:
            if filename.endswith(".md") and not filename.startswith("."):
                name = os.path.splitext(filename)[0]
                if not _DATE_FILENAME_RE.match(name):
                    topics.add(name)

    return sorted(topics)[:max_topics]


def _inject_wikilinks(text, wikilinks):
    """Replace mentions of wikilink terms with [[WikiLink]] syntax.

    Processes longer terms first to avoid substring conflicts.
    Skips code blocks, inline code, and existing links.
    """
    if not wikilinks or not text:
        return text

    unique_links = {link for link in wikilinks if link}
    sorted_links = sorted(unique_links, key=len, reverse=True)
    for link in sorted_links:
        start_b = r"(?<!\w)" if re.match(r"\w", link[0]) else r""
        end_b = r"(?!\w)" if re.match(r"\w", link[-1]) else r""

        pattern = re.compile(
            r"(```[\s\S]*?```|`[^`\n]+`|\[\[[\s\S]*?\]\]|\[[^\]]*\]\([^)]*\))|"
            + f"({start_b}{re.escape(link)}{end_b})",
            re.IGNORECASE,
        )

        def replace_match(match):
            if match.group(1):
                return match.group(1)
            return f"[[{link}]]"

        text = pattern.sub(replace_match, text)

    return text


def format_note_content(note_type, content, wikilinks):
    """Assemble Obsidian Markdown from structured LLM output.

    Injects wikilinks into content and wraps it in the appropriate
    Obsidian callout based on note_type. Notes of type 'note' are
    left as plain prose without a callout wrapper.
    """
    if not content:
        return ""

    text = _inject_wikilinks(content, wikilinks)

    callout_type = _CALLOUT_MAP.get(note_type)
    if callout_type:
        lines = text.split("\n")
        quoted = "\n".join(f"> {line}" if line.strip() else ">" for line in lines)
        return f"> [!{callout_type}]\n{quoted}"

    return text


_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", re.DOTALL)


def _update_frontmatter_tags(content, new_tags):
    """Merge new_tags into an existing note's YAML frontmatter.

    Returns the full note content with updated frontmatter.
    If the note has no valid frontmatter, returns it unchanged.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return content

    frontmatter_str, remainder = match.group(1), match.group(2)
    try:
        frontmatter = yaml.safe_load(frontmatter_str)
    except yaml.YAMLError:
        return content

    if not isinstance(frontmatter, dict):
        return content

    existing_tags = frontmatter.setdefault("tags", [])
    if not isinstance(existing_tags, list):
        existing_tags = [existing_tags] if existing_tags else []
        frontmatter["tags"] = existing_tags

    for tag in new_tags:
        if tag not in existing_tags:
            existing_tags.append(tag)

    new_frontmatter = yaml.dump(
        frontmatter, Dumper=_NoAliasDumper, default_flow_style=False, sort_keys=False
    )
    return f"---\n{new_frontmatter}---\n{remainder}"


def _save_daily(target_dir, date_str, time_str, title, text, tags,
                template_new, template_append):
    """Save a dictation entry to a daily-aggregated note.

    Creates a new daily note from template_new if none exists for today,
    or appends to the existing one using template_append.
    """
    note_path = os.path.join(target_dir, f"{date_str}.md")
    tags_formatted = "\n".join(f"  - {tag}" for tag in tags) if tags else ""
    format_kwargs = SafeDict(
        date=date_str,
        time=time_str,
        title=title,
        text=text,
        tags=tags_formatted,
    )

    if not os.path.exists(note_path):
        content = template_new.format_map(format_kwargs)
        tmp_path = f"{note_path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, note_path)
        return note_path

    with open(note_path, "r", encoding="utf-8") as f:
        existing_content = f.read()

    updated_content = _update_frontmatter_tags(existing_content, tags)
    append_content = template_append.format_map(format_kwargs)

    tmp_path = f"{note_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(updated_content)
        if not updated_content.endswith("\n"):
            f.write("\n")
        f.write("\n" + append_content)
    os.replace(tmp_path, note_path)

    return note_path


def _save_standalone(target_dir, date_str, time_str, title, text, tags,
                     template):
    """Save a dictation as a standalone timestamped note."""
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    base_name = f"Dictation-{timestamp}"
    note_path = os.path.join(target_dir, f"{base_name}.md")
    counter = 1
    while os.path.exists(note_path):
        note_path = os.path.join(target_dir, f"{base_name}_{counter}.md")
        counter += 1

    tags_formatted = "\n".join(f"  - {tag}" for tag in tags) if tags else ""
    format_kwargs = SafeDict(
        date=date_str,
        time=time_str,
        title=title,
        text=text,
        tags=tags_formatted,
    )

    content = template.format_map(format_kwargs)
    tmp_path = f"{note_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, note_path)

    return note_path


def get_target_directory(vault_path, folder, folder_organization="none", now=None):
    """Compute the target directory path based on vault_path, folder, and folder_organization."""
    if now is None:
        now = datetime.now()

    vault_dir = os.path.expanduser(vault_path)
    base_dir = os.path.join(vault_dir, folder) if folder else vault_dir

    if folder_organization == "month":
        subfolder = now.strftime("%Y-%m")
    elif folder_organization == "week":
        iso_year, iso_week, _ = now.isocalendar()
        subfolder = f"{iso_year}-W{iso_week:02d}"
    elif folder_organization == "month_week":
        month_str = now.strftime("%Y-%m")
        _, iso_week, _ = now.isocalendar()
        subfolder = os.path.join(month_str, f"W{iso_week:02d}")
    else:
        subfolder = ""

    return os.path.join(base_dir, subfolder) if subfolder else base_dir


def save_note(vault_path, folder, daily_notes, title, text, tags,
              template_standalone, template_daily_new,
              template_daily_append, folder_organization="none"):
    """Save a dictation note to the Obsidian vault.

    Delegates to _save_daily or _save_standalone based on the
    daily_notes setting.
    """
    now = datetime.now()
    target_dir = get_target_directory(vault_path, folder, folder_organization, now=now)
    os.makedirs(target_dir, exist_ok=True)

    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    if daily_notes:
        return _save_daily(
            target_dir, date_str, time_str, title, text, tags,
            template_daily_new, template_daily_append,
        )

    return _save_standalone(
        target_dir, date_str, time_str, title, text, tags,
        template_standalone,
    )


