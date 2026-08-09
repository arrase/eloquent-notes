# Eloquent Notes — Architecture & Module Documentation

---

## 1. Application Overview

**Eloquent Notes** is a Linux system-tray utility for offline dictation into Obsidian vaults. The application comprises five subsystems: a CLI entry point that manages daemon lifecycle via Unix-domain socket IPC, an Obsidian integration layer that converts structured dictation output into formatted vault entries, a UI module that renders recording-state icons, and a configuration GUI subsystem that aggregates six tab widgets around an in-memory `config_data` dictionary. Data flow proceeds from user input through the CLI or dialog to one of three operational paths: autostart installation, configuration persistence (disk), or daemon invocation for recording control.

---

## 2. Configuration Management (`eloquent_notes.config`)

**Responsibility:** Directory initialization, default file seeding, config loading with recursive merge (defaults + user overrides), atomic persistence via write-to-temp + rename pattern. All operations are synchronous and raise exceptions on failure — no silent swallowing.

### Constants & Paths

- `CONFIG_DIR` = `~/.config/eloquent-notes`
- `CONFIG_PATH` = `{CONFIG_DIR}/config.yaml`
- Prompt paths: transcription, rewriting, classification system/user prompts + retry prompt — 10 total files in `PROMPTS_DIR`.
- Template paths: standalone, daily-new, daily-append — 3 files in `TEMPLATES_DIR`.
- All bundled defaults live at package-relative paths referenced by `_FILES_TO_COPY` (11 source files).

### Algorithms

**`init_config_dir()`**: `os.makedirs(..., exist_ok=True)` × 3 → `shutil.copy(src, dst)` × 11. First error in the copy loop aborts the entire function; no recovery logic exists for mid-list failures.

**`load_config()`**: calls `init_config_dir()` → reads default YAML (package-bundled) and user YAML (`CONFIG_PATH`) → validates both are dicts via `isinstance(..., dict)` or equivalent check → raises `ValueError` if either is not a mapping → recursive merge with defaults under user overrides.

**`load_file(path)`**: synchronous text-mode read; no try/except — `FileNotFoundError` / `PermissionError` propagate directly.

**`save_config(config_data)` / `save_file(path, content)`**: write-to-temp + `os.replace()` atomic pattern. On exception between temp-write and rename, a `.tmp` file remains on disk with no cleanup logic.

---

## 3. LLM Integration (`eloquent_notes.llm`)

**Responsibility:** Three-phase audio-to-structured-note pipeline: preload model weights → transcribe raw audio bytes → rewrite into clean note content → classify (type + wikilinks + tags). All calls use `requests.post(f"{ollama_url}/api/chat", ...)` against a local Ollama instance.

### Shared Retry Mechanism (`_execute_ollama_json_request`)

- Validates JSON response; on malformed JSON or missing required keys, logs error and retries up to `max_retries + 1` total attempts (initial + retries).
- On exhausted retry budget: re-raises the last observed exception uncaught.
- HTTP errors (`response.raise_for_status()`): **not** retried — propagated immediately.

### Phase Functions

| Function | Input | Output Dict Keys | Default `keep_alive` |
|----------|-------|-------------------|----------------------|
| `preload_model(ollama_url, model, ...)` | empty chat request | None (raises on error) | `"5m"` |
| `transcribe_audio(...)` | raw WAV bytes + system/user prompts | `empty`, `transcription` | `"5m"`; timeout=300s |
| `rewrite_transcription(...)` | transcription text + prompts | `title`, `content` | `"5m"`; timeout=300s |
| `classify_transcription(...)` | transcription + vault context + prompts | `type`, `wikilinks`, `tags` | `"0"` (unload after) |

### Type Constraint (Phase 3)

The classification phase constrains `type` to an enum of six categories: task, idea, note, reminder, question, decision. Output is expected as JSON with these keys; on malformed response the same retry logic applies.

---

## 4. Audio Subsystem (`eloquent_notes.audio`)

**Responsibility:** Microphone capture as WAV bytes, audible feedback beeps, lazy WAV encoding from raw PCM chunks. All operations are synchronous with `threading.Lock` around state transitions.

### Recording Pipeline

1. `AudioRecorder.__init__(sample_rate=16000, channels=1)` initializes queue and parameters; locks are never held during `__init__`.
2. `start()` acquires lock → calls `_stop_unlocked()` (cascading close) → resets `self.q` → opens new `sounddevice.InputStream` with callback that appends chunks to the queue via `queue.Queue.put(indata.copy())`. No lock is held during chunk enqueue — relies on CPython GIL and internal Queue synchronization.
3. During recording, audio arrives asynchronously into `self.q`; no external lock required for append operations.
4. `stop()` acquires lock → calls `_stop_unlocked()`. Sets `self.stream = None` before any cleanup call. If `stop()` raises, control falls to `finally` which also calls `.close()` — produces cascading exceptions on the already-closed stream.
5. Property `wav_bytes`: acquires lock → stops any active stream via `_stop_unlocked()` → drains queue without locking (risk: reader observes partially-drained state) → concatenates chunks along axis 0 → scales float32 to int16 PCM (`×32767`, clip to [-32768, 32767]) → writes WAV via `wave.open(BytesIO, "wb")` + `.writeframes()` → caches in `self._wav_bytes`.

### Beep Playback

- `play_beep(frequency=440, duration=0.1, sample_rate=16000)`: computes total samples; returns immediately if ≤ 0 → generates sine wave → applies fade-in/out envelopes (first/last `sample_rate × 0.01` samples) → plays via `sd.play()` + waits via `sd.wait()`. No try/except wraps the playback calls — hardware errors propagate directly to caller.

### Error Propagation Pattern

- `start()` re-raises after cleanup before exception propagation.
- `_stop_unlocked()` cascades close errors (uncaught).
- `wav_bytes` property: raw wave operations and concatenation uncaught — no try/except.
- `play_beep()`: hardware/driver errors propagate directly.

---

## 5. Application Controller (`eloquent_notes.app`)

**Responsibility:** Orchestrates the full lifecycle of hands-free dictation: system-tray presence, recording state machine, IPC single-instance control, and the three-phase LLM processing pipeline (transcription → rewriting → classification). All user-facing behavior flows through `EloquentApp`.

### Data Flow Overview

```
main() → EloquentApp.__init__ → run() → QLocalServer.listen + system tray setup
    │
    ├── _on_tray_activated(reason) ──→ _start_recording() ──→ AudioRecorder.start() + beep playback
    │                                    │
    │                                   └── daemon thread: preload_model() (background LLM warmup)
    │
    └── toggle_action → exit_app() ──→ QLocalServer.removeServer + join(_processing_thread, timeout=5.0)
                                          ↑ IPC client sends "toggle" over Unix socket

_on_tray_activated → _stop_recording_and_process() ──→ daemon thread: _process_audio()
    │                                                    ├── Phase 1: transcribe audio bytes via Ollama (retry on malformed JSON)
    │                                                    ├── Phase 2: rewrite transcription into structured note content
    │                                                    ├── Phase 3: classify (type + wikilinks + tags from vault context)
    │                                                    └── save_note() → Obsidian vault file with daily/standalone template
    │
    └── _on_processing_completed(status, detail) ──→ emit signal → update tray icon + notify()
```

### State Machine (`self._state`, guarded by `threading.Lock`)

| Transition | Trigger | Guarded? |
|-----------|---------|----------|
| IDLE → STARTING_RECORDING | `_start_recording()` user action | Yes (lock) |
| STARTING_RECORDING → RECORDING | recorder stream open + callback active | Implicit (same lock scope) |
| RECORDING → PROCESSING | `_stop_recording_and_process()` signal | Yes (lock) |
| PROCESSING → IDLE | `_on_processing_completed` signal handler | **No** — direct attribute assignment bypasses property setter's lock |

### Thread Safety Assessment

- `self._state` and `self._recorder`: protected by `threading.Lock` via properties.
- `self.active_config`: deep-copied once in `_start_recording`; read-only thereafter, but **no lock** guards access — relies on single-threaded assumption since only the main thread mutates it.
- Signal emission from background daemon thread: Qt's `pyqtSignal` provides cross-thread safety; direct attribute mutations inside the handler bypass the property lock (observed race window between `_stop_recording_and_process` and `_on_processing_completed`).

---

## 6. IPC Single-Instance Control (`eloquent_notes.app` — `_handle_ipc_connection`)

**Responsibility:** Unix domain socket listener (`QLocalServer`, socket name `eloquent_notes_ipc`) for external commands: `"toggle"`, `"reload"`, `"notify_running"`. If `listen()` fails, only a `logger.error` is emitted; the app continues. Socket disconnects are cleaned up in `finally` blocks (`disconnectFromServer`, `deleteLater`). No lock guards reads/writes of `self.server` — mutation occurs only once in `run()`.

### CLI Entry Point Integration

The application exposes three public entry points: a CLI that manages daemon lifecycle via IPC, an Obsidian integration layer that converts structured dictation output into formatted vault entries, and a UI module that renders recording-state icons. Data flow proceeds from user input through the CLI or dialog to one of three operational paths: autostart installation, configuration persistence (disk), or daemon invocation for recording control.

---

## 7. Obsidian Integration (`eloquent_notes.obsidian`)

**Responsibility:** Converts structured dictation output into formatted Obsidian vault entries. Performs vault scanning for wikilink targets, injects wikilinks via `[[term]]` syntax, wraps content in callout blocks based on note type, and saves notes atomically using write-to-temp + rename pattern.

### Functions

| Function | Parameters | Returns | Description |
|----------|-----------|---------|-------------|
| `scan_vault_topics` | `vault_path`, `max_topics=200` | `list[str]` | Scans the Obsidian vault for note basenames usable as wikilinks. Skips date-named files and hidden directories starting with '.'; caps results to at most `max_topics` entries. |
| `format_note_content` | `note_type`, `content`, `wikilinks` | `str` | Assembles Obsidian Markdown from structured output: injects wikilinks into `content`, then wraps it in the appropriate callout based on `note_type`. Notes of type `'note'` are returned as plain prose. Returns `""` if `content` is falsy. |
| `save_note` | `vault_path`, `folder`, `daily_notes`, `title`, `text`, `tags`, `template_standalone`, `template_daily_new`, `template_daily_append` | `str` | Saves a dictation note to the Obsidian vault. Delegates to `_save_daily` or `_save_standalone` based on the `daily_notes` setting; returns the resulting file path. |

### External I/O & Side Effects

| Function | Read | Write | Atomicity Pattern |
|----------|------|-------|-------------------|
| `scan_vault_topics` | Walks directory tree via `os.walk(vault_path)` | None | No error handling around walk; returns `[]` if path is invalid/missing. |
| `_save_daily` (new daily) | None | Writes to `.tmp`, then `os.replace(tmp, note_path).md` | Atomic rename: write temp file → `os.replace()` atomically swaps into place. Encoding: UTF-8. |
| `_save_daily` (append to existing) | Reads existing content from `.md` file | Writes updated+appended content to `.tmp`, then `os.replace(tmp, note_path).md` | Atomic rename on append path as well. Encoding: UTF-8. |
| `_save_standalone` | None | Writes to `.tmp`, then `os.replace(tmp, note_path).md` | Atomic rename. Handles collision via counter loop (`Dictation-{ts}.md`, `Dictation-{ts}_1.md`, etc.). Encoding: UTF-8. |
| `save_note` | None | Calls `_save_daily` or `_save_standalone` which perform the actual writes; also calls `os.makedirs(target_dir, exist_ok=True)` | Delegates to above functions. |

### High-Level Algorithm Steps

1. **Vault Scanning** — Walk the vault directory to collect basenames of markdown files (excluding date-named and hidden files) as a candidate set for wikilink targets.
2. **Wikilink Injection** — For each candidate term, replace its occurrences in the input text with `[[term]]` Obsidian syntax. Skip existing code blocks, inline code, and already-wrapped links to avoid collisions.
3. **Note Formatting** — Based on note type (task, idea, reminder, question, decision), wrap the wikilink-enriched content inside an Obsidian callout block (`> [!type]`). Notes of type `note` are left as plain prose without wrapping.
4. **Frontmatter Tag Merging** — When updating a daily note that already exists, parse the YAML frontmatter header, append any new tags to the existing tag list (preserving order and avoiding duplicates), and rewrite only the frontmatter section while keeping the rest of the file intact.
5. **Daily vs. Standalone Save Decision** — If `daily_notes` is enabled, save under today's date string (`YYYY-MM-DD.md`). Otherwise, create a standalone note with a timestamped filename like `Dictation-2024-01-15-134506.md`, incrementing the counter if the file already exists.
6. **Atomic Writes** — For both daily and standalone paths, write to a `.tmp` file first, then atomically rename into place to prevent partial writes from being visible in the vault.

### Error Propagation Analysis

| Scenario | Handling Strategy |
|----------|-------------------|
| File read failure on existing daily note (`_save_daily`) | Opens existing `.md` for reading via `with open(note_path, "r", ...)`. If this fails (permission denied, disk full, I/O error), the exception propagates up unhandled to the caller — **no try/except wraps this**. |
| File write failure | All `open(tmp_path, "w")` and `os.replace()` calls have no try/except. A write failure or rename failure (e.g., cross-device rename) results in an unhandled exception propagating up to the caller. |
| Directory walk errors (`scan_vault_topics`) | Wraps nothing around `os.walk`. If a permission error occurs during traversal, it is not caught — propagates as raw `OSError` to caller. |
| Frontmatter YAML parse failure (`_update_frontmatter_tags`) | Catches `yaml.YAMLError` and returns the original content unchanged (swallowed). This is the only explicitly handled error in the module. |
| Template formatting errors | No try/except around `.format_map()` calls. A `KeyError` from missing format placeholders would propagate as a raw `KeyError`. |
| `os.makedirs` failure (`save_note`) | No error handling around `os.makedirs(target_dir, exist_ok=True)`. Propagates as `OSError` to caller. |

**Summary of error propagation:** The module uses the "atomic rename" pattern consistently for writes (write temp → `os.replace()`). Only one error type is caught: YAML parse errors in frontmatter updates return original content silently. All other disk I/O errors and template errors propagate as raw exceptions to the caller. No logging, no fallback behavior, no crash recovery — failures are propagated as Python exceptions.

---

## 8. UI Icons (`eloquent_notes.ui`)

**Responsibility:** Generates recording-state icons for system-tray presence. Two public functions: `create_icon_image(color)` produces a PIL Image (RGBA, 64×64), and `get_qicon(color)` converts it into a Qt `QIcon`. Supported colors: `"red"` (recording dot), `"orange"` (hourglass), or any other value (default state with microphone).

### External I/O Interactions

**No external side effects.** All operations in this file are confined to in-memory computation:

- **Pillow (`Image`, `ImageDraw`)**: Used exclusively for constructing RGBA pixel data in memory. No disk read/write is performed on the icon generation path.
- **`io.BytesIO`**: Creates an in-memory buffer (`byte_arr`) that receives PNG-encoded bytes from `pil_img.save()`. This is an in-memory stream, not a filesystem operation.
- **Qt (`QPixmap.loadFromData()`)**: Decodes the PNG bytes into Qt's pixmap system entirely within memory.

### Error Propagation

**Errors propagate unhandled upward.** No `try/except` blocks exist in this file:

- If an invalid color string is passed to `create_icon_image()`, the function reaches the end of its conditional chain without returning. Python raises a `NameError` implicitly if no branch matches and the function falls off, or more accurately—Python raises nothing unless there's unhandled logic; in this case, every path returns an image object.
- If any Pillow operation fails internally (`Image.new()`, drawing primitives, `save()`), it raises a Python exception.
- If `pixmap.loadFromData()` encounters invalid PNG data, it raises a Qt/Python exception.

All exceptions propagate to the caller of `get_qicon()` or `create_icon_image()`. The file does not catch, log, or translate any errors.

---

## 9. Configuration GUI (`eloquent_notes.config_gui`)

**Responsibility:** User-facing configuration infrastructure for Eloquent Notes. Exposes two public entry points: `ConfigurationDialog`, which provides a centralized settings management window, and `OllamaModelLoader`, which asynchronously discovers Ollama-compatible LLM models with audio generation capability. The dialog aggregates six independent tab widgets—General, Obsidian, AI Settings, Audio, Prompts, Templates—each responsible for one configuration domain. Data flow proceeds from user interaction through tab UIs into an in-memory `config_data` dictionary (partitioned by key: `"ai"`, `"audio"`, `"general"`, `"obsidian"`), which is then diffed against a factory-default YAML schema and persisted to disk via `eloquent_notes.config.save_config`.

### Constants (`eloquent_notes.config_gui.constants`)

| Name | Type | Description |
|------|------|-------------|
| `PROMPTS` | `list[tuple[str, Any, Any]]` | Prompt configuration tuples: `(label, system_prompt_path, default_source)`. Covers Transcription (System/User), Rewriting (System/User), Classification (System/User), and Retry prompts. |
| `TEMPLATES` | `list[tuple[str, Any, Any]]` | Template configuration tuples: `(label, standalone_template_path, default_source)`. Covers Standalone Note Template, Daily Note - New, Daily Note - Append. |

### Styles (`eloquent_notes.config_gui.styles`)

| Element | Type | Description |
|---------|------|-------------|
| `QSS_STYLESHEET` | Module-level `str` | Qt Style Sheets string defining visual appearance for the configuration dialog: base colors/fonts, tab pane and tab states (selected/hovered/active), input controls (line edits, spin boxes, combo boxes) including focus indicators, list widget hover/selection feedback, push button variants (normal, hover, pressed, "Save"), group box borders/titles, checkbox indicator size/shape/state, vertical scrollbar dimensions and handle colors. |

Static string constant only. No executable logic or error handling.

### Utilities (`eloquent_notes.config_gui.utils`)

#### Function: `diff_configs(default: dict, current: dict) -> dict`

Recursively diffs the `current` configuration against a known default, returning only overrides—i.e., settings that differ between factory defaults and user state. No external I/O. The function assumes dict-shaped input at all recursion levels without validation; unexpected types (non-dict values, missing `.items()` method) would propagate as uncaught exceptions.

**Algorithm:**
1. Initialize empty result dictionary.
2. Iterate every key in `current`: if absent from `default`, copy directly into result. If both values are dicts, recurse. If one value is a boolean and the other is not, treat as type-mismatch override. Otherwise, if scalar values differ, record current value.
3. Return collected overrides only.

### Loader (`eloquent_notes.config_gui.loader`)

#### Class: `OllamaModelLoader` (inherits `QThread`)

Asynchronously discovers and filters Ollama-compatible LLM models that support audio generation. Returns filtered results via the `models_fetched` signal; errors via `error_occurred`. No mutable instance state.

**Signals:**
- `models_fetched(models: list)` — emitted on successful completion with filtered model names.
- `error_occurred(error_msg: str)` — emitted when an uncaught exception occurs during execution.

**Algorithm:**
1. Subclass `QThread` with two signals (see above).
2. Query available models via GET `/api/tags`; parse response payload defensively.
3. For each discovered model name, POST to `/api/show` with `{"name": name}` and examine returned capabilities for the presence of `"audio"`. Models containing this capability are collected into an output list. Each inner call is individually wrapped in try/except—failures silently swallowed.
4. On completion (or interruption), emit either the filtered model names via `models_fetched` or pass any caught exception through `error_occurred`.

**Error propagation:**
- Inner-loop failures: Individual POST responses that fail are caught by `except (requests.RequestException, ValueError, AttributeError): pass`. No signal emission.
- Outer failures: The entire `run()` body is wrapped in a bare `except Exception as e:` block. Any uncaught exception—including HTTP errors from the initial GET—is caught, converted to `str(e)`, and emitted via `self.error_occurred.emit(str(e))`.
- Interruption checks (`self.isInterruptionRequested()`) return cleanly with no signal emission—effective graceful cancellation.

### Base Contracts (`eloquent_notes.config_gui.tabs.base`, `eloquent_notes.config_gui.tabs.text_files`)

#### Class: `ConfigTab` (abstract base)

Enforces the lifecycle contract for every configuration tab widget. Subclasses must implement at minimum:

- **`load_settings(config_data: dict) -> None`** — populate UI from caller-supplied config dictionary
- **`save_settings(config_data: dict) -> bool`** — read current UI state back into the dictionary; return `True` on success, `False` when validation fails (caller uses this to decide whether to show an error dialog)

Optional no-op implementations for:
- **`restore_defaults() -> None`**
- **`cleanup() -> None`**

No mutable instance state. No external I/O. Methods that are not overridden raise `NotImplementedError`; `restore_defaults()` and `cleanup()` silently swallow errors via bare `pass`.

#### Class: `TextFilesTab(ConfigTab)` (intermediate base)

Manages a list of editable text files (prompts, templates). Constructor signature: `__init__(self, items, editor_label, placeholder, parent=None)`, where `items` is an iterable of `(label, path, default_path)` tuples.

**Mutable instance state:**
- `_block_cache` — bool toggle used to block cache writes during load/restore
- `loaded_contents` — dict mapping file paths to cached strings
- `current_item` — the currently selected list widget item

**Algorithm:**
1. Constructor forwards label/path/default_path tuples; no additional state, no external I/O.
2. On every list selection change (`_on_item_changed`), previous active editor's contents are written into `loaded_contents` before switching focus. New item content is read from disk via an external `config.load_file(path)` call; if no file exists at either path or default_path, empty string is cached.
3. **Commit** (`commit_active_editor()`): flushes the current item's in-memory text into `loaded_contents` so it survives a subsequent switch.
4. **Persist** (`save_settings`): writes every entry of `loaded_contents` back to disk via `config.save_file(path, content)`. Returns hardcoded `True` regardless of write outcome—no per-file error detection is visible; failures propagate as uncaught exceptions from the underlying config module.
5. **Load/restore**: reads each path that exists and populates cache; missing paths default to empty string.

No synchronization primitives are present. File I/O errors (permission denied, disk full, etc.) crash at call site without being wrapped.

### Domain Tabs (`eloquent_notes.config_gui.tabs`)

#### Class: `AITab(ConfigTab)`

**Responsibility:** Configure the Ollama LLM pipeline for local dictation-to-note tasks. Manages connection URL, available model list, context window size, keep-alive durations, max retries on JSON parse failures, and output language selection.

**Data flow:**
1. `_init_ui()` builds a form with: Ollama URL text field (`txt_ollama_url`), editable model combo box, context length spinbox + "use default" toggle, keep-alive time fields, max retries spinbox (0–10), preload/request timeout spinboxes, output language dropdown.
2. `_fetch_models()` constructs a fresh `OllamaModelLoader` from `eloquent_notes.config_gui.loader`, calls `.start()`, and begins tracking it in `self._running_loaders`. The loader communicates completion via three signal handlers:
   - **`finished`** → `_on_loader_finished`: discards the completed loader from `_running_loaders`, clears `self._model_loader`, re-enables refresh button.
   - **`models_fetched(models)`** → `_on_models_fetched`: populates combo box; if a previously selected model is no longer in the fetched list, it is added back and re-selected. Status label set to green text `"Audio models loaded successfully."`.
   - **`error_occurred(error_msg)`** → `_on_models_fetch_failed`: status label becomes red with `f"Connection failed: {error_msg}"`.
3. All three handlers are guarded by `if self.sender() is not self._model_loader: return` to prevent queued signals from stale loaders executing on new state.
4. **Cleanup**: `cleanup()` calls `.wait(2500)` on each loader in `_running_loaders`; if a loader hangs beyond the timeout, it returns silently—no explicit exception handling visible.
5. **Load persisted settings** (`load_settings`): restores all widget values from `config_data["ai"]`. Defaults include Ollama URL `http://localhost:11434`, model `gemma4:12b-it-qat`, context length 10000.
6. **Save** (`save_settings`): collects widget state into `config_data["ai"]`. Validation rejects empty Ollama URL (shows QMessageBox warning) and keep-alive durations that don't match the regex `^-?\d+[smh]?$`; each invalid field triggers its own QMessageBox. Returns `False` on any validation failure, `True` otherwise.

**Mutable state:** `self._model_loader` (OllamaModelLoader instance or None), `self._running_loaders` (set of loaders in progress). No synchronization mechanism protects these across signal-driven threads. The retry count (`spn_max_retries`) is persisted but the actual retry logic lives downstream; this tab only stores the value.

#### Class: `AudioTab(ConfigTab)`

**Responsibility:** Configure audio capture parameters before voice recording. Exposes sample rate (8–96 kHz), channel count (mono/stereo), beep-on-record toggle, and beep frequency/duration selectors.

**Data flow:**
1. `_init_ui()` creates five widgets: `QSpinBox` for sample rate with range/setSingleStep configured, `QComboBox` for channels, `QCheckBox` for beep enable, two spinboxes for beep frequency (int) and duration (double).
2. **Load** (`load_settings`): reads from `config_data.get("audio", {})`. Sample rate is parsed as int with default 16000 Hz; if parsing raises ValueError/TypeError it is caught and the spinbox reverts to 16000. Channels defaults to index 1 (mono). Beep frequency defaults to 1000 Hz, beep duration to 0.1 s—both have try/except fallbacks. The **channels** field has no explicit type guard; a non-int value propagates as an unhandled error when `setCurrentIndex` evaluates it.
3. **Save** (`save_settings`): writes current widget values back into `config_data["audio"]`. Returns `True` unconditionally—if any Qt widget access raises (e.g., `.value()` on a destroyed widget), the exception propagates to caller without being caught here.

#### Class: `GeneralTab(ConfigTab)`

**Responsibility:** Configure startup/autostart behavior and logging verbosity, file size limits, backup retention count, and log viewer.

**Data flow:**
1. **Autostart management**: a QCheckBox toggles whether the app launches on login. On save: if checked → `install_autostart()` creates `~/.config/autostart/eloquent-notes.desktop`; if unchecked → `os.remove(autostart_path)` deletes it (only called when file exists).
2. **Logging level**: QComboBox with five options (DEBUG, INFO, WARNING, ERROR, CRITICAL); persisted as `logging.level`.
3. **Log file size limit**: spinbox range 1–100 MB; persisted as `logging.max_mb`.
4. **Backup retention**: spinbox range 0–10; persisted as `logging.backup_count`.
5. **View log** (`_view_log_file`): opens `<log_dir>/app.log` in the system editor via `QDesktopServices.openUrl()`. If the file does not exist, an informational message is shown instead of opening anything. No try/except wraps the open call or existence check—failure propagates as unhandled exception.
6. **Load**: reads autostart path with `os.path.exists()` to populate checkbox state; no write operation during load.

#### Class: `ObsidianTab(ConfigTab)`

**Responsibility:** Configure Obsidian vault integration—vault directory, target folder name within the vault, append-to-daily-notes toggle, and vault-context wikilinks toggle.

**Data flow:**
1. `_init_ui()` builds a form with four controls: vault path line edit, browse button, folder name line edit, two checkboxes (daily notes, context).
2. **Browse** (`_browse_vault_path`): opens a directory picker via `QFileDialog.getExistingDirectory()`, pre-filled with the current vault path or user home if empty. Returns empty string on cancel—treated as "no selection" and path remains unchanged.
3. **Load**: restores all four values from `config_data["obsidian"]`. Path normalization uses `os.path.expanduser()` and `os.path.abspath()`. No exception handling visible for these calls; errors propagate uncaught.
4. **Save** (`save_settings`): writes the four values into `config_data["obsidian"]`. If vault path is empty, a warning dialog appears and returns `False`. If the directory does not exist on disk, `os.path.exists()` check triggers a confirmation dialog; user denial → return `False`, acceptance proceeds without re-checking existence. Returns `True` on successful save.

#### Class: `PromptsTab(TextFilesTab)`

**Responsibility:** Provide a tab for viewing and editing editable prompts stored in an application constant list (`eloquent_notes.config_gui.constants.PROMPTS`). Delegates all text-file UI logic to the inherited `TextFilesTab`.

Constructor forwards `items=PROMPTS`, `editor_label="Prompt Content:"`, placeholder `"Select a prompt to edit..."` to `TextFilesTab.__init__()`. No additional state, no external I/O, no error handling visible in this file.

#### Class: `TemplatesTab(TextFilesTab)`

**Responsibility:** Provide a tab for viewing and editing editable templates stored in an application constant list (`eloquent_notes.config_gui.constants.TEMPLATES`). Delegates all text-file UI logic to the inherited `TextFilesTab`.

Constructor forwards `items=TEMPLATES`, `editor_label="Template Content:"`, placeholder `"Select a template to edit..."` to `TextFilesTab.__init__()`. No additional state, no external I/O, no error handling visible in this file.

### Dialog (`eloquent_notes.config_gui.dialog`)

#### Class: `ConfigurationDialog(QDialog)`

Full application settings management dialog with tabbed interface (General, Obsidian, AI Settings, Audio, Prompts, Templates) and Save/Cancel/Restore Defaults actions.

**Mutable instance state:**
- `self.config_data` (dict) — Instance, set in `__init__` via `config.load_config()` or `{}`. Passed to tab widgets as input argument in `load_settings_to_ui()`, `restore_defaults()`, and `save_settings_from_ui()`. Tabs may mutate this dict in-place since Python passes dicts by reference.
- `_tabs` (list of tuples) — Instance, set in `_init_ui()`; read-only after initialization; not observed to be reassigned elsewhere in this file.

**Synchronization:** None detected. No locks, mutexes, `threading.Lock`, async/await, or atomic types are used anywhere in this module. The dialog operates on a single GUI thread (PyQt6's main event loop). Because `self.config_data` is passed by reference to tab widgets which may mutate it without synchronization primitives, any future extension introducing background threads or multi-threaded access would require explicit coordination—scope beyond this file alone.

**External I/O:**
- **Disk read/write**: `__init__` calls `config.load_config()`; errors or `None` return are swallowed via `or {}`. If an exception escapes, it crashes the application. `restore_defaults` and `save_settings_from_ui` both read default config YAML with `yaml.safe_load()`, wrapped in try-except—any error (file not found, parse failure) shows via `QMessageBox.critical`. `save_settings_from_ui` also writes merged config back to disk; errors shown via same critical dialog.
- **No network/API calls**: All interactions are local file system and YAML parsing only.

**Error propagation:**
| Code Path | Failure Mode | Handling Strategy |
|-----------|-------------|-------------------|
| `__init__` — `config.load_config()` | Returns `None`, raises exception, or yields invalid data | Swallowed via `or {}`. If an unhandled exception occurs (e.g., file not found), it propagates to the caller and crashes. |
| `restore_defaults` — YAML/file ops | File read failure, parse error, missing default config source | Caught by inner try-except; user sees a critical dialog with message prefix `"Failed to restore defaults: "`. |
| `save_settings_from_ui` — tab validation | Any individual tab's `save_settings()` returns `False` | Short-circuits immediately; focuses on the failing tab and aborts saving. No disk write occurs if validation fails mid-process. |
| `save_settings_from_ui` — YAML/file ops | File read failure, parse error | Caught by inner try-except; user sees a critical dialog with message prefix `"Failed to save settings: "`. Returns `False`. |
| `save_settings_from_ui` — write operation | Disk write failure | Caught by inner try-except; same critical dialog. Returns `False`. |
| `closeEvent` / `reject` / `accept` | Resource cleanup | Cleanup called unconditionally before standard close/reject/accept. No error handling around cleanup itself—any exception during cleanup is swallowed by the default Qt behavior (crash or silent swallow). |

**Lifecycle:**
1. Initialize state: load existing configuration from disk into memory; instantiate all tab widgets for each config category.
2. Populate UI on open: reflect current persisted settings into every tab widget so the user sees their active configuration.
3. User edits tabs freely (handled by individual tab implementations, not in this file).
4. Save flow: iterate through every tab; gather edited values back from each widget. If any tab fails validation, revert focus to that tab and abort saving. Otherwise, compute a diff between the factory-default config schema and the user's current edits—persist only the actual overrides to disk (so untouched settings remain unchanged).
5. Restore defaults flow: confirm with the user first; if confirmed, reload raw factory-default YAML into every tab widget and reset internal default-state flags on each tab.
6. Cleanup lifecycle hook: when closing/canceling/accepting the dialog, invoke cleanup routines on all tabs to release resources before the window destroys.

---

## 10. Templates (`eloquent_notes.templates`)

**Responsibility:** Provides static Markdown template definitions that encode output schemas for downstream note-generation systems. Each file is a non-executable, placeholder-driven artifact consumed by an external renderer at parse time. No runtime logic, error handling, or mutable state exists within any of the templates; all side-effect-bearing execution occurs outside this package's scope.

### Data Flow

1. **Template Selection** — The rendering engine selects a template file based on note type (append-only daily entry, new session with frontmatter tags, standalone document).
2. **Placeholder Resolution** — At render time, the engine substitutes `{time}`, `{date}`, `{title}`, `{text}`, and `{tags}` placeholders with concrete values supplied by the application layer.
3. **Output Emission** — The rendered Markdown is emitted to disk or forwarded via an I/O channel (not implemented within this module).

### Template Definitions

#### `daily_append.md`

Encodes a minimal daily append entry schema. Output structure:

```markdown
## {time} — {title}
{text}
```

- `{time}`: ISO-formatted date/time string injected at runtime.
- `{title}`: Descriptive title for the day's focus.
- `{text}`: Free-form body content (thoughts, tasks, reflections).

**Invariant:** Every entry must contain exactly three fields — time reference, title, and text body. Entries are ordered chronologically per the `{time}` convention. The structure enforces separation between metadata (`{time}`) and content (`{title}` + `{text}`).

#### `daily_new.md`

Encodes a daily dictation session schema with YAML frontmatter. Placeholder set: `{date}`, `{tags}`, `{time}`, `{title}`, `{text}`.

- **Frontmatter Block:** Declares tag support and timestamp placeholders (`{date}`, `{time}`).
- **Body Structure:** Timestamp, descriptive title, body text organized under the same markdown heading convention as `daily_append.md`.
- **Tag Attachment:** Classification tags are attached to each entry for grouping/filtering operations.

#### `standalone.md`

Encodes a self-contained note document schema. Placeholder set: `{tags}`, `{date}`, `{time}`, `{title}`, `{text}`.

- **Frontmatter Block:** YAML header declares tag and timestamp placeholders (`{date}`, `{time}`).
- **Title Slot:** `{title}` placeholder resolves during rendering into the document heading.
- **Content Area:** `{text}` placeholder reserves the main body field for free-form text input.
- **Render Output:** Metadata and content are combined into a final Markdown layout.

### Structural Comparison

| Template | Placeholder Set | Frontmatter | Body Format | Tags |
|----------|-----------------|-------------|-------------|------|
| `daily_append.md` | `{time}`, `{title}`, `{text}` | None | Markdown heading + body | N/A |
| `daily_new.md` | `{date}`, `{tags}`, `{time}`, `{title}`, `{text}` | YAML block | Markdown heading + body | Yes |
| `standalone.md` | `{tags}`, `{date}`, `{time}`, `{title}`, `{text}` | YAML block | Markdown heading + body | Yes |

### State and Concurrency Characteristics

- **No mutable state** across any template file. All placeholders are resolved externally.
- **No concurrency primitives.** Templates do not participate in locking, signaling, or coordination.

### Error Handling and Side Effects

- **Zero external I/O paths.** No network calls, disk operations, database queries, or API interactions are present.
- **No error propagation logic.** No exception handlers, return codes, panic paths, or conditional fallback