# Eloquent Notes — Quickstart & Architecture Overview

## System Boundaries

`eloquent_notes` is a voice-dictation note-taking system composed of three public subsystems plus template definitions:

| Subsystem | Module | Responsibility |
|---|---|---|
| Vault / Dictation Pipeline | `eloquent_notes.obsidian` | Vault filesystem scanning, wikilink injection, dictation-to-note persistence (daily or standalone) |
| System Tray Icon Generation | `eloquent_notes.ui` | PIL-based 64×64 icon rendering for idle / recording / processing states |
| Configuration GUI | `eloquent_notes.config_gui` | Qt configuration dialog aggregating six domain tabs, Ollama model loader running in a `QThread`, diff-based YAML persistence |

Templates (`eloquent_notes/templates`) are passive Markdown definitions consumed by an external rendering engine. They contain no executable code or mutable state.

### Module Interaction Map

```
obsidian.scan_vault_topics() ──► topics: list[str] (sorted basenames)
       │
       ▼
save_note(vault_path, folder, daily_notes, title, text, tags, ...)
       │  delegates to _save_daily or _save_standalone based on daily_notes flag
       │  _update_frontmatter_tags() merges new_tags into existing frontmatter in-memory
       │  _inject_wikilinks() wraps vault topic basenames matching content terms with [[wikilink]] syntax
       ▼
obsidian.save_note() returns str (path to .md file written via open("w"))

config_gui.ConfigurationDialog ──► load_settings() / save_settings_from_ui()
       │  config_data: dict shared across six tab widgets (caller-owned reference, no copy semantics)
       │  diff_configs(default, current) computes override set for YAML persistence
       ▼
templates/daily_append.md | daily_new.md | standalone.md ──► external engine resolves {time}/{title}/{text} placeholders
```

## Developer Overview

### `eloquent_notes.obsidian` — Vault & Dictation Pipeline

**Public API:**

- **`scan_vault_topics(vault_path, max_topics=200)`** — Walks the vault filesystem via `os.walk`, excludes date-named files (YYYY-MM-DD pattern), collects basenames into a set, returns up to `max_topics` results sorted alphabetically. Vault path that is not a directory yields `[]` silently.
- **`format_note_content(note_type, content, wikilinks)`** — Wraps dictation output in Obsidian Markdown. Based on `note_type`, content receives an optional callout block prefix (`> [!todo]`, `> [!tip]`, etc.); plain "note" type passes through unmodified. Wikilink terms are injected via `_inject_wikilinks`.
- **`_inject_wikilinks(text, wikilinks)`** — Scans free-text content for terms matching the known vault topic set. Longer terms processed first to avoid substring collisions (e.g., "Go" inside "Google"). Already-wrapped `[[wikilink]]` syntax is skipped. Returns text with injected `[[WikiLink]]` wrappers.
- **`_update_frontmatter_tags(content, new_tags)`** — Parses/rewrites YAML frontmatter *in-memory* from content strings; no disk access. If content starts with `---`, a second `---` marker must be present; otherwise the entire content is returned unchanged. New tags are appended to an existing `tags` list only if not already present; duplicate tags preserved as-is. Side effect: `yaml.SafeDumper.ignore_aliases = lambda self, data: True` is set inside this function on every call. If frontmatter parsing fails (malformed YAML, encoding issues), exceptions propagate uncaught.
- **`_save_daily(target_dir, date_str, time_str, title, text, tags, template_new, template_append)`** — Writes a new daily note from `template_daily_new` if none exists; otherwise reads existing content via `open(path, "r")`, merges tags into frontmatter, appends new entry text with `\n` separator. Path is created via `os.makedirs(target_dir, exist_ok=True)`. No error handling around I/O failures—`PermissionError`, `IsADirectoryError`, disk-full conditions propagate uncaught.
- **`_save_standalone(target_dir, date_str, time_str, title, text, tags, template)`** — Generates a timestamped filename (`Dictation-{YYYY-MM-DD-HHMMSS}.md`) and writes single-entry content directly via `open(path, "w")`. No merge logic; overwrites on each call. Same I/O error propagation as `_save_daily`.
- **`save_note(vault_path, folder, daily_notes, title, text, tags, template_standalone, template_daily_new, template_daily_append)`** — Public entry point for dictation persistence. Computes current date/time strings. Delegates to `_save_daily` or `_save_standalone` based on `daily_notes`. Returns path string. No error handling; all downstream exceptions propagate up through the call chain.

**Concurrency & State:** No mutable module-level state beyond `_CALLOUT_MAP` (dict literal, never mutated) and `_DATE_FILENAME_RE` (compiled regex constant). All other variables are local to their respective functions. No locks, threads, or channels present—only standard library I/O calls. Concurrent callers see results undefined by this code; no synchronization exists.

**I/O Side Effects:**

| Function | Operation | Details |
|---|---|---|
| `scan_vault_topics` | Read (`os.walk`) | Reads filenames only; returns sorted list capped at 200 entries |
| `_save_daily`, `_save_standalone` | Write (`open("w")`) | Creates/overwrites note files; no merge for standalone mode |
| `_update_frontmatter_tags` | None (string-only) | Parses frontmatter in-memory; mutates global `yaml.SafeDumper.ignore_aliases` |

### `eloquent_notes.ui` — System Tray Icon Generation

**Public API:**

- **`create_icon_image(color)`** — Pure in-memory computation. Creates a 64×64 RGBA image buffer with transparent black fill via `Image.new(...)`, draws the appropriate shape (microphone circle, recording dot, or hourglass) into an `ImageDraw.Draw(image)` context. All drawing operations (`draw.ellipse()`, `draw.polygon()`, `draw.rounded_rectangle()`, `draw.arc()`, `draw.line()`) operate on the in-memory image object only—no disk, network, or DB I/O. Relies on Pillow's internal validation; errors propagate uncaught if draw calls or color values are invalid.
- **`get_qicon(color)`** — Serializes the PIL image to PNG bytes via `pil_img.save(byte_arr, format='PNG')` into a `BytesIO()` buffer (no disk file created). Reads the serialized PNG bytes back as a Qt `QPixmap` via `pixmap.loadFromData(byte_arr.getvalue(), 'PNG')`. Entire pipeline runs between PIL image → BytesIO → QPixmap with no persistent storage I/O. Errors propagate uncaught if Pillow or Qt operations fail internally.

**Concurrency & State:** No module-level or persistent mutable state exists in this file. All variables (`image`, `draw`, `pil_img`, `byte_arr`, `pixmap`) are local to their respective function scopes and created/destroyed per call. No locks, channels, or synchronization primitives present.

### `eloquent_notes.config_gui` — Configuration Dialog & Tabs

**Module Responsibility:** Exposes a Qt-based configuration UI for Eloquent Notes:
- **`ConfigurationDialog(QDialog)`** loads settings from disk, presents them across six tab widgets, persists only divergent values back to YAML on save.
- **`OllamaModelLoader(QThread)`** runs in a dedicated `QThread` to discover audio-capable models from the remote `/api/tags` endpoint without blocking the UI.
- **Tab subsystem (`eloquent_notes.config_gui.tabs`)** aggregates six domain-specific tab widgets under one namespace, each inheriting from an abstract base class and communicating through a caller-owned shared dictionary.

**Data Flow:**

```
Disk (YAML) ──config.load_config()──►  config_data: dict  ──load_settings()──►  Tab widgets
                                                              │
                                                              ▼
User edits ──save_settings_from_ui()──►  Per-tab save_settings()  ◄── validation gates
                                                              │
                                                              ▼
                                              diff_configs(default, current)
                                                              │
                                                              ▼
Disk (YAML)  ◄──config.save_config(overrides)────

OllamaModelLoader ──QThread.run()──►  GET /api/tags  ──►  model names
                                                              │
                                                              ├── POST /api/show per name ──►  capabilities check ──► "audio" filter
                                                              │
                                                              ▼
                                              models_fetched(list)  ◄── main thread signal

Tabs  ◄── shared config_data dict (caller-owned reference, no copy semantics)
```

**Configuration Dialog — `eloquent_notes.config_gui.dialog`**

- **`__init__(self, parent=None)`**: Optional[QDialog]. Loads factory defaults from YAML once; populates six tabs.
- **`load_settings_to_ui(self)`**: Populates tabs from current disk state (called externally).
- **`restore_defaults(self)`**: Bare `try/except Exception`; on failure shows `QMessageBox.critical` with `"Failed to restore defaults: {e}"`, returns normally. On success reloads factory YAML into all tabs and emits info message. A confirmation prompt must be accepted before overwriting current edits; if cancelled, no state change occurs.
- **`save_settings_from_ui(self)`**: Iterates each tab's `save_settings()` for validation; if any return `False`, rejects without writing. On full success computes diff between loaded defaults (`self.config_data`) and current UI state, writes only differing keys via `config.save_config(overrides)`. Wraps entire pipeline in bare `try/except Exception`; on failure shows critical message with `"Failed to save settings: {e}"` and returns `False`.
- **`cleanup_tabs(self)`**: Releases tab resources; called unconditionally in `reject()` and conditionally (only when save succeeded) in `accept()`.
- **`reject(self)`** / **`accept(self)`**: Standard Qt lifecycle hooks with cleanup integration.

**Business Rules:**

1. **Diff-based persistence.** Only values differing from factory defaults are written to disk on save. Unchanged settings retain their defaults without rewriting.
2. **Per-tab validation gates.** Each tab implements its own `save_settings()` returning a boolean; if any fails, the dialog rejects and highlights the offending tab.
3. **Defaults restoration is opt-in.** A confirmation prompt must be accepted before overwriting current edits with factory defaults. If cancelled, no state change occurs.
4. **Thread cleanup on both exit paths.** Regardless of Accept/Reject/Save outcome, tab resources are cleaned up and running threads stopped before the dialog closes.

**Ollama Model Loader — `eloquent_notes.config_gui.loader`**

- **`__init__(self, url, parent=None)`**: Sets `self.url`; no return.
- **`run(self)`** (signals): Async worker: GET `/api/tags` (2s timeout), extracts model names from `data["models"]`. For each name, POST to `/api/show` with `{"name": <model>}`; inspects `capabilities` array for `"audio"`. Per-model exceptions are silently swallowed. If any HTTP call fails with non-200 status or a top-level exception occurs (and interruption not requested), emits `error_occurred(str)`. On success, accumulates audio-capable model names and emits `models_fetched(list)`.

**Tab Subsystem — `eloquent_notes.config_gui.tabs`**

#### Base Class — `ConfigTab(QWidget)` (abstract)

All six domain tabs inherit from this abstract anchor, enforcing two interface contracts:
- **`load_settings(config_data: dict)`** → `None`. Subclasses must read nested keys and hydrate widgets. Base raises `NotImplementedError`.
- **`save_settings(config_data: dict) -> bool`** → `bool`. Must return `True` for valid state, `False` on validation failure (empty fields, invalid formats, cancellation).

#### Domain Tabs

| Tab | Responsibility | Key Details |
|---|---|---|
| `AITab` (`ai.py`) | Ollama integration: connection parameters, model selection, context length tuning, keep-alive durations, retry logic for voice-to-text dictation tasks. | `_fetch_models(self)` constructs `OllamaModelLoader`, connects three signals (`finished`, `models_fetched`, `error_occurred`), calls `loader.start()`. Signal handlers populate or clear the combo box; stale sender check returns silently. `cleanup(self)` cancels in-flight loaders via `loader.requestInterruption()`, waits 500ms per loader synchronously (no timeout enforcement), clears references. Validation: `save_settings()` returns `False` if URL is empty or keep-alive duration formats are invalid; two regex checks enforce `^-?\d+[smh]?$`. |
| `AudioTab` (`audio.py`) | Microphone capture settings: sample rate, channel mode, recording feedback control via optional audible beep. | Widgets: `QSpinBox` (8000–96000 Hz, steps of 8000; tooltip calls out 16000 Hz recommended for speech recognition), `QComboBox` (Mono vs Stereo), `QCheckBox` (beep enable with frequency/duration fields below), `QDoubleSpinBox` (0.01–2.0 sec). Always returns `True` from `save_settings()`. No external I/O; no try/except blocks in this file. |
| `GeneralTab` (`general.py`) | Autostart behavior on desktop session login, logging verbosity and retention policy, log inspection via system editor. | `_view_log_file` reads `~/.config/autostart/eloquent-notes.desktop` via `os.path.exists()` to check autostart state; calls `QDesktopServices.openUrl(...)` to open the log file in user's default editor (swallowed by Qt if unavailable). Non-atomic save: logging config updated first, then `.desktop` entry created or removed separately via `install_autostart()`. If write fails after logging config was committed to `config_data`, dict holds inconsistent state. Broad `try/except` wraps autostart logic; on any failure displays `QMessageBox.critical` and returns `False`. Missing log file case handled silently with `QMessageBox.information`. |
| `ObsidianTab` (`obsidian.py`) | Vault root path, target subfolder, daily note vs standalone file routing, optional vault-aware wikilink suggestions during classification. | `_browse_vault_path()` calls `QFileDialog.getExistingDirectory(self, ...)`. If current text is non-empty, calls `os.path.expanduser()` + `os.path.exists()`. Non-existent path falls back to `~/` silently (not an error). Empty vault path after `.strip()` triggers `QMessageBox.warning(...)` returning `False`. Path that does not exist on disk prompts via `QMessageBox.question(...)` with Yes/No; if **Yes**, validation passes anyway. No exceptions are caught anywhere in this file—`os.path.expanduser()`, `QFileDialog.getExistingDirectory()`, and `.text()` all propagate uncaught up to the caller. |
| `TextFilesTab` (`text_files.py`) | Framework for managing multiple named text files as configuration entries. Each entry has a display label, primary storage path, and optional fallback/default path. All six tabs (`prompts`, `templates`) are thin subclasses delegating to this base with different constants. | `_init_ui(self)` renders horizontal splitter: `QListWidget` on left (entries by label), monospace-text editor on right for currently selected entry's content. `_on_item_changed(self, current, previous)` caches previous item's in-memory content back into `loaded_contents`. New item's path is looked up; if cached text exists it loads into the editor, otherwise starts empty. Editor disabled when no item selected and cleared on deselection. **Cache-first persistence**: All edits go through in-memory dictionary (`loaded_contents`) before being flushed to disk—ensures atomicity, changes never partially persisted. Write-blocking during restore/defaults: cache is locked during `load_settings` and `restore_defaults`, preventing writes while rehydrating state from files. Graceful degradation if primary file missing: fallback path tried; if that fails, empty string stored as entry content. |
| `PromptsTab` / `TemplatesTab` (`prompts.py` / `templates.py`) | Thin facades delegating to `TextFilesTab`. No instance attributes or mutable state defined in these files. | Depend entirely on constants imported from `.eloquent_notes.config_gui.constants`. If those constants are undefined or raise errors during instantiation, exceptions propagate uncaught. |

**Constants — `eloquent_notes.config_gui.constants`**

| Constant | Type (Inferred) | Purpose |
|---|---|---|
| `PROMPTS` | `List[Tuple[str, str, str]]` | 3-tuples of label + config source path for prompt definitions. |
| `TEMPLATES` | `List[Tuple[str, str, str]]` | 3-tuples of label + config source path for note template types (Standalone Note, Daily Note - New, Daily Note - Append). |

No runtime logic; no mutable state beyond these module-level constants. Import-time side effect: bare import of parent package `eloquent_notes.config_gui`; if absent, raises unhandled `ImportError`.

**Utilities — `eloquent_notes.config_gui.utils`**

#### `diff_configs(default, current) -> dict`

Recursively compares two nested configuration dictionaries. For each key in `current`:
- If absent from `default` → new override; include it.
- If both values are dicts → recurse into nested comparison.
- If either value differs → mark as override; include it.
- Discard branches with no differences (prune empty results).

Returns only non-empty overrides—what changed between default and current. Pure in-memory dict traversal; zero external communication. Unhandled: if `default` or `current` is not iterable/dict-like at top level, `.items()` raises a Python exception (`TypeError`, `AttributeError`). If `k` is missing from `default`, `default[k]` raises `KeyError`. No try/except blocks; all exceptions propagate to callers.

**Styling — `eloquent_notes.config_gui.styles`**

#### `QSS_STYLESHEET` (constant)

A single module-level constant holding the raw Qt Style Sheet string defining visual appearance for every widget type in the configuration GUI: `QDialog`, `QWidget`, `QTabWidget`, `QTabBar`, `QLineEdit`, `QSpinBox`, `QDoubleSpinBox`, `QComboBox`, `QTextEdit`, `QListWidget`, `QPushButton`, `QGroupBox`, `QCheckBox`, `QScrollBar`. Catppuccin Mocha palette (#1e1e2e background, #89b4fa accent). No runtime behavior beyond string literal definition; no imports or function calls.

**Error Handling Summary — config_gui**

| Pattern | Where | Mechanism |
|---|---|---|
| **Swallowed with user notification** | `dialog.py` — `restore_defaults`, `save_settings_from_ui` | Bare `try/except Exception`; shows `QMessageBox.critical`, returns normally (or sentinel `False`). |
| **Per-tab validation gate** | All tabs — `save_settings()` | Returns boolean; caller (`ConfigurationDialog`) decides commit/reject. |
| **Silent swallow on per-model failure** | `loader.py` — inner loop | Per-model exception caught and ignored; only top-level or connection errors surface as `error_occurred`. |
| **Signal-based async pipeline with silent state swallows** | `ai.py` | Three distinct patterns: empty URL (silent), invalid duration formats (`QMessageBox.warning` + return False), signal propagation to red status label. No exception handling anywhere in this file. |
| **No wrapping, no sentinels** | `text_files`, `general`, `obsidian` | File I/O failures surface as unhandled exceptions unless Qt event loop catches them at higher level. No try/except blocks; all propagate up to callers. |
| **Non-atomic autostart update** | `general.py` | Logging config updated first, then `.desktop` file created/removed separately. If write fails after logging config was committed, dict holds inconsistent state. |

### `eloquent_notes.templates` — Markdown Template Definitions

The `eloquent_notes/templates` module is a collection of Markdown templates designed for structured note capture across multiple use cases: daily journaling, dictation sessions, and standalone entries. The module contains no executable code, no mutable state, and no error handling paths. It exists purely as a format contract consumed by external rendering engines (Go `text/template`, Jinja2, or equivalent placeholder substitution).

All templates follow a consistent pattern: YAML frontmatter for metadata (where applicable), followed by interpolated body content using named placeholders. The module's data flow is entirely downstream-dependent — behavior is defined exclusively by whichever runtime reads and substitutes into the templates.

**Template Inventory:**

#### daily_append.md — Daily Journal Appender

- **Responsibility:** Generate individual daily journal entries where each entry is stored as an independent Markdown document. New entries accumulate over time rather than being overwritten (append pattern).
- **Data Model:** `{time}` = Timestamp when the note was created; `{title}` = Human-readable label for the entry; `{text}` = Body content of the note.
- **Template Shape:**

```markdown
## {time} — {title}
{text}
```

**Algorithmic Flow:**

1. User creates a new daily note → fresh Markdown file generated using this template
2. System captures three values: timestamp, title, body text
3. Formatted content written to disk as an independent document
4. Storage grows with each entry (append pattern)

---

#### daily_new.md — Dictation Session Tracker

- **Responsibility:** Capture dictation practice sessions organized by date and time periods for language learners. Supports multiple practice sessions per day through time-period segmentation.
- **Data Model:** `{tags}` = List of tags applied to the note (defaults to `dictation`); `{date}` = Date of the dictation session; `{time}` = Time slot label for the entry; `{title}` = Title/headline of the entry; `{text}` = Body text / content of the dictation.
- **Frontmatter:**

```yaml
tags: [dictation]
date: {date}
```

**Algorithmic Flow:**

1. Session initiation → user selects a date and assigns entries to specific time periods during that day
2. Entry capture → for each period: record `{time}` label, assign descriptive `{title}`, then capture raw `{text}` content
3. Daily compilation → all period-level entries aggregated under `# Dictations of {date}` heading and rendered sequentially

**Business Rule:** A dictation entry is scoped to a single day; cross-day organization relies on date navigation rather than temporal reordering within the file.

---

#### standalone.md — Standalone Note Template

- **Responsibility:** Generate structured, timestamped notes with metadata frontmatter and body content for general use cases outside daily or dictation workflows.
- **Data Model:** `{tags}` = Array of tag strings (YAML list); `{date}` = Date string; `{time}` = Time string; `{title}` = Markdown heading level 1; `{text}` = Main body content (paragraph).
- **Algorithmic Flow:**

1. Generate YAML frontmatter emitting `tags`, `date`, and `time` as key-value pairs
2. Render markdown body outputting a title heading followed by text content

---

**Cross-Template Patterns:** All three templates share structural characteristics:

| Characteristic | Observation |
|---|---|
| **State** | None — no global variables, struct fields, or mutable state defined in any file |
| **Concurrency** | None — no locks, channels, synchronization primitives present |
| **I/O** | None — no disk writes, network calls, database queries, subprocess invocations |
| **Error Handling** | None — no try/except blocks, sentinel values, panic handling, logging, or fallback logic |
| **Return Values** | N/A across all files — templates are passive definitions consumed externally |

All three communicate only through placeholder substitution. The placeholders (`{time}`, `{title}`, `{text}`, `{tags}`, `{date}`) are bare strings awaiting resolution by an external rendering engine. If a template engine fails to resolve any placeholder, this file contains no mechanism to catch or report the failure.