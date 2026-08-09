# Eloquent Notes — Quickstart & Architecture Overview

## System Boundary

`eloquent_notes` is a Python package that runs as a **system-tray daemon** on Linux (or any platform with a Qt GUI toolkit). Its purpose: capture live microphone input, transcribe via a local Ollama-compatible LLM, and persist structured notes into an Obsidian-style vault. Three entry points exist — CLI/IPC for remote control, in-process GUI configuration dialog, and the system-tray icon driven by the main state machine.

---

## Module Interaction Map

```
┌────────────── CLI / IPC ───────────────┐  ┌─────────────── GUI ───────────────────┐
│ run_cli() → parse_args()               │  │ ConfigurationDialog                    │
│ send_ipc_command() ← QLocalSocket      │  │ save_settings_from_ui()                │
│ EloquentApp.toggle_action()           │  │ restore_defaults()                     │
│ EloquentApp.reload_config()           │  │ OllamaModelLoader.run()                 │
└────────────────────────────────────────┘  └─────────────────────────────────────────┘

                    │ IPC / Config I/O
                    ▼
┌──────────────────────────────────────────────────────────────────┐
│ EloquentApp (state machine: IDLE → STARTING_RECORDING →          │
│  RECORDING → PROCESSING)                                          │
│   ├─ AudioRecorder.start() / stop()                               │
│   │    └─ sounddevice.InputStream                                 │
│   ├─ LLM pipeline: transcribe → rewrite → classify                │
│   │    └─ requests.post to Ollama `/api/chat`                     │
│   ├─ Obsidian vault write-back                                    │
│   └─ System tray notifications                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Entry Points

### CLI / Daemon IPC (`eloquent_notes.main`)

- `run_cli(argv)` — dispatches `install-autostart`, `toggle`, `-t`, `config`.
- `send_ipc_command(command, timeout_ms=300)` — writes over Unix socket `eloquent_notes_ipc`; returns `True` on success, `False` on failure. Raises `RuntimeError` if write fails (disconnect called before raise).
- `parse_args(args)` — parses CLI arguments; returns object with `.command` and `.toggle`.
- Daemon toggle: first attempt IPC; if already running → notify and exit 0; if false/failed → spawn subprocess via `python -m eloquent_notes.app`.

### GUI Configuration (`eloquent_notes.config_gui`)

- `ConfigurationDialog(QDialog)` — modal dialog with six tabs (General, Obsidian, AI Settings, Audio, Prompts, Templates).
- `save_settings_from_ui()` — iterates every tab; if any returns validation failure → focus that tab and abort. Otherwise writes merged config to disk.
- `restore_defaults()` — confirms via QMessageBox; reloads factory-default YAML into all tabs.

### System Tray / Main App (`eloquent_notes.app`)

- `EloquentApp` — state machine: IDLE → STARTING_RECORDING → RECORDING → PROCESSING.
- `_on_tray_activated(reason)` → either starts recording (daemon thread: `preload_model()` warmup) or stops and processes audio through the three-phase LLM pipeline.
- IPC listener (`QLocalServer`, socket name `eloquent_notes_ipc`) handles `"toggle"`, `"reload"`, `"notify_running"` commands.

---

## Audio Subsystem (`eloquent_notes.audio`)

**`AudioRecorder(sample_rate=16000, channels=1)`** — captures microphone input as WAV bytes via `sounddevice.InputStream` with callback that appends chunks to an internal queue.

| Method | Behavior |
|--------|----------|
| `.start()` | acquires lock → calls `_stop_unlocked()` if active stream exists → resets queue → opens new `sounddevice.InputStream`; no lock held during chunk enqueue (relies on GIL + Queue sync) |
| `.stop()` | acquires lock → calls `_stop_unlocked()`. Sets `self.stream = None` before cleanup. Raises propagate to caller; `finally` also calls `.close()`. |
| `.wav_bytes` property | acquires lock → stops active stream via `_stop_unlocked()` → drains queue without locking → concatenates chunks along axis 0 → scales float32 to int16 PCM (`×32767`, clip [-32768, 32767]) → writes WAV via `wave.open(BytesIO, "wb")` + `.writeframes()` |
| `play_beep(frequency=440, duration=0.1, sample_rate=16000)` | computes total samples; returns immediately if ≤ 0 → generates sine wave with fade-in/out envelopes → plays via `sd.play()` + waits via `sd.wait()`. No try/except wraps playback calls — hardware errors propagate directly. |

**Thread safety:** `_state` and `_recorder` protected by `threading.Lock` via properties; no lock guards `self.active_config` reads — relies on single-threaded assumption since only main thread mutates it. Signal emission from background daemon thread uses Qt's `pyqtSignal` for cross-thread safety.

---

## LLM Integration (`eloquent_notes.llm`)

Three-phase pipeline: **preload → transcribe → rewrite → classify**. All calls use `requests.post(f"{ollama_url}/api/chat", ...)` against a local Ollama instance.

### Shared Retry (`_execute_ollama_json_request`)
- Validates JSON response; on malformed JSON or missing required keys, retries up to `max_retries + 1` total attempts (initial + retries).
- On exhausted retry budget: re-raises last observed exception uncaught.
- HTTP errors (`response.raise_for_status()`): **not** retried — propagated immediately.

### Phase Functions

| Function | Input | Output Dict Keys | Default `keep_alive` |
|----------|-------|-------------------|----------------------|
| `preload_model(ollama_url, model, ...)` | empty chat request | None (raises on error) | `"5m"` |
| `transcribe_audio(...)` | raw WAV bytes + system/user prompts | `empty`, `transcription` | `"5m"`; timeout=300s |
| `rewrite_transcription(...)` | transcription text + prompts | `title`, `content` | `"5m"`; timeout=300s |
| `classify_transcription(...)` | transcription + vault context + prompts | `type`, `wikilinks`, `tags` | `"0"` (unload after) |

**Type constraint:** classification constrains `type` to an enum of six categories: task, idea, note, reminder, question, decision. Malformed responses use the same retry logic.

---

## Obsidian Integration (`eloquent_notes.obsidian`)

Converts structured dictation output into formatted vault entries. Three core operations: **vault topic discovery**, **wikilink injection**, and **structured note generation/persistence**.

### Public API

| Function | Returns | Description |
|----------|---------|-------------|
| `scan_vault_topics(vault_path, max_topics=200)` | `list[str]` | Scans vault for note basenames usable as wikilinks. Skips date-named files and hidden directories starting with '.'; caps to `max_topics`. |
| `_inject_wikilinks(text, wikilinks)` | `str` | Appends `[[link]]` at first occurrence per link name (case-insensitive). Skips code blocks, fenced regions, markdown links `[text](url)`, backtick-wrapped identifiers. |
| `_update_frontmatter_tags(content, tags)` | `str` | Merges new tags with existing YAML frontmatter. Returns original unchanged if YAML is unparseable or parsed structure is not a dict. |
| `format_note_content(note_type, content, wikilinks)` | `str` | Wraps lines in callout syntax for `"task"` (`> [!todo]`) and `"idea"`. Other types inject `[[tag]]` wikilinks into plain text. Returns `""` if content is falsy. |
| `save_note(vault_path, folder, daily_notes, title, text, tags, template_standalone, template_daily_new, template_daily_append)` | `str \| None` | File path for saved note; returns `None` on failure. Daily notes use either `template_daily_new` (first entry) or `template_daily_append` (subsequent). Standalone uses `template_standalone`. |

### Atomic Write Pattern
For both daily and standalone paths: write to `.tmp` file first, then atomically rename into place (`os.replace()`). Encoding: UTF-8. Only one error type is caught — YAML parse errors in frontmatter updates return original content silently. All other disk I/O errors propagate as raw exceptions.

---

## Configuration System (`eloquent_notes.config`)

**Functions:**
- `init_config_dir()` — creates directories for config, prompts, templates; copies default files into them. First error in copy loop aborts entire function.
- `load_config()` — calls `init_config_dir()` → reads default YAML (package-bundled) and user YAML (`CONFIG_PATH`) → validates both are dicts via `isinstance(...)` check → raises `ValueError` if either is not a mapping → recursive merge with defaults under user overrides.
- `save_file(path, content)` / `save_config(config_data)` — write-to-temp + `os.replace()` atomic pattern. On exception between temp-write and rename, `.tmp` file remains on disk with no cleanup logic.
- `load_file(path)` — synchronous text-mode read; no try/except — `FileNotFoundError` / `PermissionError` propagate directly.

**Constants:**
| Name | Value |
|------|-------|
| `CONFIG_DIR` | `~/.config/eloquent-notes` |
| `CONFIG_PATH` | `{CONFIG_DIR}/config.yaml` |
| `PROMPTS_DIR` | prompts subdirectory within config dir (10 files) |
| `TEMPLATES_DIR` | templates subdirectory within config dir (3 files) |

---

## Configuration GUI (`eloquent_notes.config_gui`)

**Entry points:** `ConfigurationDialog` and `OllamaModelLoader`.

### `ConfigurationDialog(QDialog)`
- Six tab widgets: General, Obsidian, AI Settings, Audio, Prompts, Templates.
- Data flow proceeds from user interaction through tab UIs into an in-memory `config_data` dictionary (partitioned by key: `"ai"`, `"audio"`, `"general"`, `"obsidian"`), which is then diffed against a factory-default YAML schema and persisted to disk via `eloquent_notes.config.save_config`.
- No synchronization primitives detected. Operates on a single GUI thread (PyQt6's main event loop). Any future extension introducing background threads or multi-threaded access would require explicit coordination — scope beyond this file alone.

### `OllamaModelLoader(QThread)` (`eloquent_notes.config_gui.loader`)
- Signals: `models_fetched(models: list)`, `error_occurred(error_msg: str)`.
- Queries available models via GET `/api/tags`; parses response defensively. For each model name, POST to `/api/show` and examines returned capabilities for `"audio"`. Models containing this capability are collected into output list. Each inner call is individually wrapped in try/except — failures silently swallowed.
- Outer `run()` body wrapped in bare `except Exception as e:` block; any uncaught exception (including HTTP errors from initial GET) caught, converted to `str(e)`, emitted via `self.error_occurred.emit(str(e))`.

### Configuration Tabs (`eloquent_notes.config_gui.tabs`)

| Tab | Key Controls |
|-----|-------------|
| `AITab` | Ollama URL, model combo, context length, keep-alive durations, max retries (0–10), preload/request timeouts, output language. Fetches models via `OllamaModelLoader`. |
| `AudioTab` | Sample rate (8–96 kHz), channel count (mono/stereo), beep-on-record toggle, beep frequency/duration selectors. |
| `GeneralTab` | Autostart checkbox, logging level (DEBUG/INFO/WARNING/ERROR/CRITICAL), log file size limit (1–100 MB), backup retention count (0–10). |
| `ObsidianTab` | Vault directory path, target folder name, append-to-daily-notes toggle, vault-context wikilinks toggle. |
| `PromptsTab(TextFilesTab)` | Views/edits editable prompts stored in an application constant list (`eloquent_notes.config_gui.constants.PROMPTS`). |
| `TemplatesTab(TextFilesTab)` | Views/edits editable templates stored in an application constant list (`eloquent_notes.config_gui.constants.TEMPLATES`). |

### `TextFilesTab(ConfigTab)` (intermediate base)
- Constructor signature: `__init__(self, items, editor_label, placeholder, parent=None)`; `items` is iterable of `(label, path, default_path)` tuples.
- On every list selection change (`_on_item_changed`), previous active editor's contents are written into `loaded_contents` before switching focus. New item content read from disk via external `config.load_file(path)` call; if no file exists at either path or default_path, empty string is cached.
- **Commit** (`commit_active_editor()`): flushes current item's in-memory text into `loaded_contents`.
- **Persist** (`save_settings`): writes every entry of `loaded_contents` back to disk via `config.save_file(path, content)`. Returns hardcoded `True` regardless of write outcome — no per-file error detection visible; failures propagate as uncaught exceptions from underlying config module.

### `ConfigurationDiff` (`eloquent_notes.config_gui.utils`)
- Recursively diffs the `current` configuration against a known default, returning only overrides (settings that differ between factory defaults and user state). No external I/O. Assumes dict-shaped input at all recursion levels without validation; unexpected types propagate as uncaught exceptions.

---

## Templates (`eloquent_notes.templates`)

Static Markdown template definitions consumed by an external renderer at parse time. No runtime logic, error handling, or mutable state within any template file.

| Template | Placeholder Set | Frontmatter | Body Format | Tags |
|----------|-----------------|-------------|-------------|------|
| `daily_append.md` | `{time}`, `{title}`, `{text}` | None | Markdown heading + body | N/A |
| `daily_new.md` | `{date}`, `{tags}`, `{time}`, `{title}`, `{text}` | YAML block | Markdown heading + body | Yes |
| `standalone.md` | `{tags}`, `{date}`, `{time}`, `{title}`, `{text}` | YAML block | Markdown heading + body | Yes |

---

## Logging (`eloquent_notes.logging_utils`)

- `get_log_dir()` — returns platform-specific log directory path, respecting `XDG_STATE_HOME`; otherwise falls back to `~/.local/state/eloquent-notes`.
- `setup_logging(level, max_mb, backup_count)` — attaches both console stream handler and rotating file handler. Returns the logger instance (same one passed through internally). If log directory resolution fails or file handler initialization errors occur, report error to stderr but still return configured logger so callers continue operating.

---

## Autostart (`eloquent_notes.autostart`)

- `install_autostart()` — creates a desktop entry at `~/.config/autostart/eloquent-notes.desktop`. Writes `[Desktop Entry]` header, `Name=Eloquent Notes`, and an `Exec=` line (resolved absolute path or bare command name depending on whether executable found in PATH). File permissions set to `0o644`.

---

## Error Propagation Summary

| Module | Pattern |
|--------|---------|
| `eloquent_notes.config` | Raises exceptions on failure — no silent swallowing. Atomic writes leave `.tmp` files on disk if rename fails (no cleanup). |
| `eloquent_notes.llm` | Retry logic only for malformed JSON/missing keys; HTTP errors not retried, propagated immediately. Exhausted retries re-raise last exception uncaught. |
| `eloquent_notes.audio` | Cascading close errors propagate directly. No try/except wraps raw wave operations or concatenation. Hardware/driver errors in beep propagation to caller. |
| `eloquent_notes.obsidian` | Only YAML parse errors caught (returns original content silently). All other disk I/O and template errors propagate as raw exceptions. |
| `eloquent_notes.config_gui` | Individual tab POST failures silently swallowed; outer failures emit error signal. Validation failure in any tab aborts save flow immediately. |
| `eloquent_notes.ui` | No external side effects. Errors propagate via standard Python exceptions (from failed assertions or Qt object creation). |