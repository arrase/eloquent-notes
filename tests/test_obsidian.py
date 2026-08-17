"""Unit tests for eloquent_notes/obsidian.py."""

import os
from datetime import datetime

import yaml

from eloquent_notes.obsidian import (
    _FRONTMATTER_RE,
    _inject_wikilinks,
    _update_frontmatter_tags,
    format_note_content,
    get_target_directory,
    save_note,
    scan_vault_topics,
)


def test_scan_vault_topics_basic(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Note A.md").write_text("# Note A")
    (vault / "Note B.md").write_text("# Note B")
    (vault / "2026-08-09.md").write_text("# Daily")
    (vault / "image.png").write_bytes(b"data")

    topics = scan_vault_topics(str(vault))
    assert topics == ["Note A", "Note B"]


def test_scan_vault_topics_skips_hidden_dirs(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Visible.md").write_text("content")

    git_dir = vault / ".git"
    git_dir.mkdir()
    (git_dir / "HiddenInGit.md").write_text("content")

    obsidian_dir = vault / ".obsidian"
    obsidian_dir.mkdir()
    (obsidian_dir / "HiddenInObsidian.md").write_text("content")

    trash_dir = vault / ".trash"
    trash_dir.mkdir()
    (trash_dir / "HiddenInTrash.md").write_text("content")

    topics = scan_vault_topics(str(vault))
    assert topics == ["Visible"]


def test_scan_vault_topics_max_topics_limit(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    for i in range(10):
        (vault / f"Topic-{i:02d}.md").write_text("content")

    topics = scan_vault_topics(str(vault), max_topics=5)
    assert len(topics) == 5
    assert topics == [f"Topic-{i:02d}" for i in range(5)]


def test_scan_vault_topics_nonexistent_dir():
    assert scan_vault_topics("/nonexistent/path/for/vault") == []


def test_inject_wikilinks_basic_and_order():
    wikilinks = ["Google", "Google Search"]
    text = "Use Google Search or Google directly."
    result = _inject_wikilinks(text, wikilinks)
    assert result == "Use [[Google Search]] or [[Google]] directly."


def test_inject_wikilinks_non_alphanumeric():
    wikilinks = ["C++", "Node.js", "foo-bar"]
    text = "We use C++, Node.js and foo-bar in production."
    result = _inject_wikilinks(text, wikilinks)
    assert result == "We use [[C++]], [[Node.js]] and [[foo-bar]] in production."


def test_inject_wikilinks_skips_protected_elements():
    wikilinks = ["Python", "Go"]
    text = (
        "Check [[Python]] link and `Python` code.\n"
        "```python\nprint('Go')\n```\n"
        "[Go link](https://go.dev) but also Go language."
    )
    result = _inject_wikilinks(text, wikilinks)

    assert "[[Python]] link" in result
    assert "[[[Python]]]" not in result
    assert "`Python` code" in result
    assert "```python\nprint('Go')\n```" in result
    assert "[Go link](https://go.dev)" in result
    assert "also [[Go]] language." in result


def test_format_note_content_callout():
    content = "First line.\nSecond line."
    formatted = format_note_content("task", content, [])
    assert formatted == "> [!todo]\n> First line.\n> Second line."

    formatted_idea = format_note_content("idea", "Bright idea", [])
    assert formatted_idea == "> [!tip]\n> Bright idea"


def test_format_note_content_plain_note():
    content = "Just a regular note."
    formatted = format_note_content("note", content, ["regular"])
    assert formatted == "Just a [[regular]] note."


def test_update_frontmatter_tags_no_global_side_effect():
    original_ignore_aliases = getattr(yaml.SafeDumper, "ignore_aliases", None)

    initial_content = (
        "---\n"
        "title: Sample\n"
        "tags:\n"
        "  - existing\n"
        "---\n"
        "Note body"
    )
    updated = _update_frontmatter_tags(initial_content, ["new_tag", "existing"])

    # Verify global yaml.SafeDumper was not modified
    current_ignore_aliases = getattr(yaml.SafeDumper, "ignore_aliases", None)
    assert current_ignore_aliases == original_ignore_aliases

    parsed_fm = yaml.safe_load(updated.split("---")[1])
    assert parsed_fm["tags"] == ["existing", "new_tag"]
    assert "Note body" in updated


def test_update_frontmatter_tags_with_embedded_dashes():
    initial_content = (
        "---\n"
        "title: 'My Title --- Subtitle'\n"
        "tags:\n"
        "  - existing\n"
        "---\n"
        "Body containing --- horizontal rules --- inside."
    )
    updated = _update_frontmatter_tags(initial_content, ["new_tag"])
    assert "--- horizontal rules ---" in updated
    match = _FRONTMATTER_RE.match(updated)
    assert match is not None
    parsed_fm = yaml.safe_load(match.group(1))
    assert parsed_fm["tags"] == ["existing", "new_tag"]
    assert parsed_fm["title"] == "My Title --- Subtitle"


def test_update_frontmatter_tags_no_frontmatter():
    content = "Plain content without frontmatter"
    updated = _update_frontmatter_tags(content, ["tag1"])
    assert updated == content


def test_format_note_content_empty():
    assert format_note_content("task", "", ["tag"]) == ""


def test_save_note_daily_new_and_append(tmp_path):
    vault = tmp_path / "vault"
    template_new = "---\ntags:\n{tags}\n---\n# {title}\n{text}\n"
    template_append = "## {time} - {title}\n{text}\n"

    # 1. New daily note creation
    note_path = save_note(
        vault_path=str(vault),
        folder="Daily",
        daily_notes=True,
        title="Dictation 1",
        text="First text",
        tags=["tag1"],
        template_standalone="",
        template_daily_new=template_new,
        template_daily_append=template_append,
    )
    assert os.path.exists(note_path)
    content1 = open(note_path).read()
    assert "# Dictation 1" in content1
    assert "First text" in content1
    assert "tag1" in content1

    # 2. Append to existing daily note
    note_path_2 = save_note(
        vault_path=str(vault),
        folder="Daily",
        daily_notes=True,
        title="Dictation 2",
        text="Second text",
        tags=["tag2"],
        template_standalone="",
        template_daily_new=template_new,
        template_daily_append=template_append,
    )
    assert note_path_2 == note_path
    content2 = open(note_path_2).read()
    assert "tag1" in content2
    assert "tag2" in content2
    assert "Second text" in content2


def test_save_note_standalone(tmp_path):
    vault = tmp_path / "vault"
    template = "# {title}\n\n{text}\n\nTags:\n{tags}"

    note_path = save_note(
        vault_path=str(vault),
        folder="Notes",
        daily_notes=False,
        title="Standalone Title",
        text="Standalone body text",
        tags=["idea"],
        template_standalone=template,
        template_daily_new="",
        template_daily_append="",
    )
    assert os.path.exists(note_path)
    content = open(note_path).read()
    assert "# Standalone Title" in content
    assert "Standalone body text" in content
    assert "  - idea" in content


def test_safe_template_formatting(tmp_path):
    vault = tmp_path / "vault"
    template = "# {title}\n\n{text}\nUnmatched: {unknown_placeholder}"

    note_path = save_note(
        vault_path=str(vault),
        folder="Notes",
        daily_notes=False,
        title="Title with {braces}",
        text="Text with {custom_var} inside",
        tags=[],
        template_standalone=template,
        template_daily_new="",
        template_daily_append="",
    )
    content = open(note_path).read()
    assert "Title with {braces}" in content
    assert "Text with {custom_var} inside" in content
    assert "Unmatched: {unknown_placeholder}" in content


def test_update_frontmatter_tags_invalid_yaml():
    invalid_content = "---\nkey: : invalid yaml\n---\nbody"
    assert _update_frontmatter_tags(invalid_content, ["tag"]) == invalid_content


def test_update_frontmatter_tags_non_dict():
    non_dict_content = "---\njust a string\n---\nbody"
    assert _update_frontmatter_tags(non_dict_content, ["tag"]) == non_dict_content


def test_inject_wikilinks_duplicates():
    wikilinks = ["Python", "Python", ""]
    text = "We use Python."
    result = _inject_wikilinks(text, wikilinks)
    assert result == "We use [[Python]]."


def test_scan_vault_topics_empty():
    assert scan_vault_topics("") == []


def test_save_standalone_collision(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    template = "# {title}\n{text}"

    path1 = save_note(
        vault_path=str(vault),
        folder="Notes",
        daily_notes=False,
        title="N1",
        text="T1",
        tags=[],
        template_standalone=template,
        template_daily_new="",
        template_daily_append="",
    )
    path2 = save_note(
        vault_path=str(vault),
        folder="Notes",
        daily_notes=False,
        title="N2",
        text="T2",
        tags=[],
        template_standalone=template,
        template_daily_new="",
        template_daily_append="",
    )

    assert path1 != path2
    assert os.path.exists(path1)
    assert os.path.exists(path2)


def test_get_target_directory():
    dt = datetime(2026, 8, 17, 10, 0, 0)  # 2026-08-17 is Monday, Week 34
    vault = "/fake/vault"

    # None / default
    assert get_target_directory(vault, "Notes", "none", now=dt) == "/fake/vault/Notes"
    assert get_target_directory(vault, "", "none", now=dt) == "/fake/vault"

    # Month
    assert get_target_directory(vault, "Notes", "month", now=dt) == "/fake/vault/Notes/2026-08"
    assert get_target_directory(vault, "", "month", now=dt) == "/fake/vault/2026-08"

    # Week
    assert get_target_directory(vault, "Notes", "week", now=dt) == "/fake/vault/Notes/2026-W34"
    assert get_target_directory(vault, "", "week", now=dt) == "/fake/vault/2026-W34"

    # Month and Week
    assert get_target_directory(vault, "Notes", "month_week", now=dt) == "/fake/vault/Notes/2026-08/W34"
    assert get_target_directory(vault, "", "month_week", now=dt) == "/fake/vault/2026-08/W34"


def test_save_note_folder_organization_monthly(tmp_path):
    vault = tmp_path / "vault"
    template_new = "---\ntags:\n{tags}\n---\n# {title}\n{text}\n"

    note_path = save_note(
        vault_path=str(vault),
        folder="Daily",
        daily_notes=True,
        folder_organization="month",
        title="Monthly Dictation",
        text="Content",
        tags=["month-tag"],
        template_standalone="",
        template_daily_new=template_new,
        template_daily_append="",
    )
    now = datetime.now()
    expected_subdir = now.strftime("%Y-%m")
    assert f"Daily/{expected_subdir}" in note_path or f"Daily\\{expected_subdir}" in note_path
    assert os.path.exists(note_path)


def test_save_note_folder_organization_weekly(tmp_path):
    vault = tmp_path / "vault"
    template = "# {title}\n{text}"

    note_path = save_note(
        vault_path=str(vault),
        folder="Notes",
        daily_notes=False,
        folder_organization="week",
        title="Weekly Dictation",
        text="Content",
        tags=["week-tag"],
        template_standalone=template,
        template_daily_new="",
        template_daily_append="",
    )
    now = datetime.now()
    iso_year, iso_week, _ = now.isocalendar()
    expected_subdir = f"{iso_year}-W{iso_week:02d}"
    assert f"Notes/{expected_subdir}" in note_path or f"Notes\\{expected_subdir}" in note_path
    assert os.path.exists(note_path)


def test_save_note_folder_organization_month_week(tmp_path):
    vault = tmp_path / "vault"
    template_new = "---\ntags:\n{tags}\n---\n# {title}\n{text}\n"

    note_path = save_note(
        vault_path=str(vault),
        folder="Notes",
        daily_notes=True,
        folder_organization="month_week",
        title="Month Week Dictation",
        text="Content",
        tags=[],
        template_standalone="",
        template_daily_new=template_new,
        template_daily_append="",
    )
    now = datetime.now()
    month_str = now.strftime("%Y-%m")
    iso_week = now.isocalendar().week
    expected_sub = os.path.join(month_str, f"W{iso_week:02d}")
    assert expected_sub in note_path
    assert os.path.exists(note_path)


