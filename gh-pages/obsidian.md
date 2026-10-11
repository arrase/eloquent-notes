# Obsidian Vault Integration

Eloquent Notes is built specifically to integrate seamlessly into personal knowledge management workflows powered by [Obsidian](https://obsidian.md). It transforms raw voice dictations into richly formatted Markdown notes complete with callouts, wikilinks, and clean YAML frontmatter.

---

## 1. Callout Formatting by Note Type

Obsidian supports custom visual callouts using the `> [!type]` blockquote syntax. Based on the classification produced in Phase 3 of the AI pipeline, Eloquent Notes automatically wraps the generated note prose in an appropriate native Obsidian callout.

| Classified Note Type | Mapped Callout Identifier | Rendered Markdown Callout Block | Visual Purpose in Obsidian |
| :--- | :--- | :--- | :--- |
| `task` | `todo` | `> [!todo]` | Actionable items and to-do lists |
| `idea` | `tip` | `> [!tip]` | Brainstorming insights and creative concepts |
| `reminder` | `warning` | `> [!warning]` | High-priority warnings or critical reminders |
| `question` | `question` | `> [!question]` | Open inquiries or items needing follow-up |
| `decision` | `important` | `> [!important]` | Architectural or personal decisions made |
| `note` | *(None)* | Plain text prose | Standard observations (no callout wrapper) |

### Implementation Detail
In `eloquent_notes/obsidian.py`:
```python
_CALLOUT_MAP = {
    "task": "todo",
    "idea": "tip",
    "reminder": "warning",
    "question": "question",
    "decision": "important",
}

def format_note_content(note_type, content, wikilinks):
    text = _inject_wikilinks(content, wikilinks)
    callout_type = _CALLOUT_MAP.get(note_type)
    if callout_type:
        lines = text.split("\n")
        quoted = "\n".join(f"> {line}" if line.strip() else ">" for line in lines)
        return f"> [!{callout_type}]\n{quoted}"
    return text
```

---

## 2. Vault-Wide Scanning & Smart Wikilink Injection

Eloquent Notes automatically turns mentioned topics and concepts into Obsidian `[[Wikilinks]]`.

### Vault Scanning (`scan_vault_topics`)
When `vault_context: true` is enabled in `config.yaml`, the application recursively scans your Obsidian vault directory prior to Phase 3 classification:
- It discovers all `.md` note basenames across subdirectories.
- It automatically ignores daily journal notes matching the `YYYY-MM-DD` regex pattern (e.g., `2026-08-06.md`).
- It caps the discovered topics at 200 items to fit comfortably within LLM context windows.
- The list of topics is passed to Gemma 4 in Phase 3 to inform topic identification.

### Substring Collision Protection (`_inject_wikilinks`)
Once Phase 3 returns a list of candidate wikilinks, `_inject_wikilinks()` replaces matches in the note body using regular expressions:

```python
def _inject_wikilinks(text, wikilinks):
    # Sort by length descending so longer terms match first
    sorted_links = sorted(wikilinks, key=len, reverse=True)
    for link in sorted_links:
        pattern = re.compile(
            r"(?<!\[\[)\b" + re.escape(link) + r"\b(?!\]\])",
            re.IGNORECASE,
        )
        text = pattern.sub(f"[[{link}]]", text)
    return text
```

#### Key Safeguards
1. **Longest Terms First:** Links are sorted by string length in descending order before replacement. This prevents shorter terms from corrupting longer terms (for example, matching `"Postgres"` inside `"PostgreSQL"`, or `"Go"` inside `"Google"`).
2. **Word Boundaries (`\b`):** Uses regex word boundaries to prevent matching inside unrelated words.
3. **Negative Lookbehind/Lookahead:** Ensures terms that are already enclosed inside `[[ ... ]]` are skipped to prevent duplicate wrapping (e.g., `[[[[Topic]]]]`).
4. **Case Insensitivity:** Matches words regardless of spoken capitalization while preserving the canonical vault topic casing in the link target.

---

## 3. Storage Modes: Daily Journals vs Standalone Notes

Eloquent Notes supports two distinct saving workflows controlled by the `obsidian.daily_notes` boolean setting in `config.yaml`:

### Mode A: Daily Journal Appending (`daily_notes: true`)
All dictations recorded throughout the day are aggregated into a single daily note named `YYYY-MM-DD.md` inside your designated vault target folder.

- **First Dictation of the Day:** If `YYYY-MM-DD.md` does not exist, Eloquent Notes creates it using `templates/daily_new.md`, initializing YAML frontmatter, tags, date, and the first entry under a time header.
- **Subsequent Dictations:** If `YYYY-MM-DD.md` already exists, Eloquent Notes reads the file, parses and merges tags in the YAML frontmatter, and appends the new dictation entry using `templates/daily_append.md` under a new timestamp header (e.g., `### 14:32:05 - Note Title`).

### Mode B: Standalone Dictation Files (`daily_notes: false`)
Each dictation creates a separate timestamped file in your vault target directory using `templates/standalone.md`:
- **Naming Pattern:** `Dictation-YYYY-MM-DD-HHMMSS.md` (e.g., `Dictation-2026-08-06-143205.md`).
- Each note contains its own complete YAML frontmatter, tags, and callout content.

### Subfolder Organization (`folder_organization`)
You can control whether notes are placed directly in the target directory or organized into time-based subdirectories:
- **`none`** (Default): Directly in the target folder (e.g. `Dictations/2026-08-17.md` or `Dictations/Dictation-2026-08-17-143205.md`).
- **`month`**: Subfolders by month `YYYY-MM` (e.g. `Dictations/2026-08/2026-08-17.md`).
- **`week`**: Subfolders by ISO week `YYYY-Www` (e.g. `Dictations/2026-W34/2026-08-17.md`).
- **`month_week`**: Subfolders by month and ISO week `YYYY-MM/Www` (e.g. `Dictations/2026-08/W34/2026-08-17.md`).

---

## 4. Smart PyYAML Frontmatter Parsing & Tag Deduplication

When appending new dictations to an existing daily note (`daily_notes: true`), existing metadata must be preserved cleanly.

`_update_frontmatter_tags()` parses and updates YAML frontmatter without breaking existing notes:

```python
def _update_frontmatter_tags(content, new_tags):
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
```

### Frontmatter Preservation Guarantees
- **Tag Merging:** New tags extracted by Phase 3 are appended to the existing `tags` list while eliminating duplicates.
- **Key Retention:** All pre-existing YAML keys (such as `date`, `aliases`, `author`, or custom properties) are preserved intact.
- **No Alias Anchors:** `yaml.SafeDumper.ignore_aliases` is set to ensure PyYAML does not insert unwanted YAML pointer anchors (`*id001`) into arrays.
- **Clean Structure:** The existing frontmatter block is cleanly replaced while keeping the body of the daily note untouched before appending the new dictation entry.
