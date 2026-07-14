# Eloquent Notes — Architecture Documentation

## Module Responsibility & Data Flow Overview

**Eloquent Notes** is a persistent system-tray dictation tool that captures spoken audio from the default microphone, transforms it into structured Markdown notes via a three-phase Ollama LLM pipeline (transcription → rewriting → classification), and saves the resulting note to an Obsidian vault at `~/Obsidian/Dictations`. The application runs as a PyQt6 `QObject`-based daemon with IPC-based single-instance messaging.

### Data Flow Pipeline

```
User Action (tray click / IPC "toggle")
    │
    ▼
┌─────────────┐     ┌──────────┐
│  EloquentApp │────▶│ AudioRecorder │   (background thread)
│  (QObject)   │◀────│            │   → WAV bytes in memory
└─────────────┘     └──────────┘
    │                         │
    │          ┌──────────────┘
    ▼          ▼
┌─────────────────────────────────────┐
│  _process_audio (daemon thread)      │
│  ├─ Phase 1: transcribe_audio       │
│  ├─ Phase 2: rewrite_transcription  │
│  └─ Phase 3: classify_transcription │
└─────────────────────────────────────┘
    │
    ▼
Vault context scan (Obsidian vault read) → combined prompt → LLM call
    │
    ▼
Note assembly via template substitution → `obsidian.save_note()` write to disk
    │
    ▼
Signal emission: "success" / "empty" / "error" → GUI thread notification
```

### Configuration & Initialization Flow

1. CLI parses arguments (`install-autostart`, `config`, `toggle`, default).
2. If no running daemon is reachable via IPC socket, a new process launches; if one exists, it receives `"toggle"` or `"notify_running"`.
3. On startup: `config.init_config_dir()` seeds user directories with bundled defaults; `load_config()` merges default YAML with user overrides (recursive merge).
4. Logging setup writes to XDG STATE_HOME via `logging_utils.setup_logging()`.
5. If `config` subcommand → launch `ConfigurationDialog`; if no argument or `toggle` → IPC connect.

---

## Subsystem: `eloquent_notes.app` — Application Controller

**Responsibility:** Central controller for the PyQt6 GUI application. Owns recording state, background processing thread coordination, tray icon management, and signal-based communication between worker threads and the main GUI thread via a custom `pyqtSignal`.

### Public API Surface

#### Class: `EloquentApp(QObject)`

| Method | Signature | Description |
|--------|-----------|-------------|
| `__init__(self, qapp, start_recording_immediately=False)` | — | Initializes the application controller. Connects to tray icon activation events and registers a local `QLocalServer` (socket: `eloquent_notes_ipc`) for cross-process commands (`toggle`, `reload`, `notify_running`). If `start_recording_immediately=True`, recording begins on first run. |
| `run(self)` | — → None | Starts the main application loop. Exits via `sys.exit`. |
| `_on_tray_activated(self, reason)` | `reason: QSystemTrayIcon.ActivationReason` → None | Handles tray icon clicks and context-menu selections (toggle recording, open config dialog, reload config, quit). Dispatches accordingly. |
| `_handle_ipc_connection(self)` | — → None | Processes incoming IPC messages from other processes or scripts. Recognized strings: `"toggle"`, `"reload"`, `"notify_running"`. Unknown messages fall through silently. |
| `_update_icon(self, color, tooltip)` | `color: str`, `tooltip: str` → None | Updates the system tray icon's visual state and tooltip text. Used to reflect recording/processing status visually in the tray. |
| `_notify(self, title, message)` | `title: str`, `message: str` → None | Emits a desktop notification (tray balloon). Called on processing completion (success/empty/error) and config reload errors. |
| `toggle_action(self)` | — → None | Public toggle handler exposed to the main window or IPC. Triggers recording start if idle, stop+process if recording, busy notification otherwise. |
| `_preload_model(self)` | — → None | Launches an LLM preloading call in a daemon thread (non-blocking relative to GUI). Loads model weights into VRAM before recording begins. Warnings logged but non-fatal on failure. |
| `_start_recording(self)` | — → None | Spawns a background `threading.Thread` that starts the audio recorder. Emits an optional startup beep via `audio.play_beep()`. Transitions state to `RECORDING`; simultaneously triggers model preloading thread. On failure: reverts to `IDLE`, emits error signal. |
| `_stop_recording_and_process(self)` | — → None | Spawns a background `threading.Thread` that stops the recorder, retrieves WAV bytes, and executes the full LLM processing pipeline. Emits a processing-start beep. State transitions from `RECORDING` to `PROCESSING`. |
| `_build_vault_context(self)` | — → `str` | Scans the Obsidian vault directory structure (if `vault_context` is true in config) and returns a string of existing note names for inclusion in the classification prompt. Empty string returned if no topics found. |
| `_process_audio(self)` | — → None (emits `processing_completed`) | Executes the three-phase LLM pipeline: (1) transcription, (2) rewriting, (3) classification. Each phase uses a configurable timeout (`request_timeout`). Wrapped in try/except; any exception is caught and converted to `"error"` status signal. |
| `_on_processing_completed(self, status, detail)` | `status: str`, `detail: str` → None | Receives the result from the processing thread via `processing_completed` signal. Sets state to `IDLE`. On success: displays notification with filename. On empty: shows "Empty" notification. On error: surfaces failure message via tray notification. |
| `reload_config(self)` | — → None | Reloads configuration from disk, re-initializes logging (via `setup_logging`), and notifies the user if errors occur during reload. |
| `show_config_dialog(self)` | — → None | Instantiates and shows a GUI `ConfigurationDialog`. Sets reference in `self._config_dialog`. |
| `_on_config_dialog_closed(self, _result)` | `_result: int` → None | Handles configuration dialog close event (accepted/rejected). |
| `_clear_config_dialog_reference(self)` | — → None | Clears the stored `ConfigurationDialog` reference. Called on exit or explicit cleanup. |
| `exit_app(self)` | — → None | Cleans up lifecycle: stops recorder if state is `RECORDING`/`STARTING_RECORDING`, joins processing thread with 5s timeout, closes IPC server, hides tray icon, exits via `sys.exit`. |

### Thread Safety Notes

No synchronization mechanisms (locks, mutexes) are present. Direct attribute access (`self.state`, `self.recorder`) from worker threads occurs without protection. The `threading.Thread` objects spawned in `_start_recording` and `_stop_recording_and_process` read/write application state attributes directly. PyQt signals/slots provide implicit synchronization for passing results back to the GUI thread but do not protect mutable attributes accessed during transition phases.

---

## Subsystem: `eloquent_notes.audio` — Audio Capture & Playback Utilities

**Responsibility:** Provides microphone audio capture as WAV bytes (lazy, compiled on first access) and short sine-wave feedback beeps with anti-click envelopes. No external disk/network I/O; all processing is in-memory.

### Public API Surface

#### Class: `AudioRecorder`

| Element | Signature | Description |
|---------|-----------|-------------|
| **Constructor** | `__init__(self, sample_rate=16000, channels=1) → None` | Initializes the recorder with configurable sample rate and channel count. Creates an internal queue for chunk accumulation. |
| **Method** | `start(self) → None` | Opens a sounddevice input stream (`sd.InputStream`) and begins recording. Incoming samples trigger a callback that enqueues chunks into the internal queue. |
| **Method** | `stop(self) → None` | Halts and closes the audio input stream. No explicit guard against double-stop — calling on an already-stopped recorder is a no-op. |
| **Property** | `wav_bytes` | Lazy-loaded property that, on first access, drains all queued chunks from `self.q`, concatenates them along the time axis, scales float values to 16-bit PCM range, and writes an in-memory WAV file using `io.BytesIO`/`wave`. Returns raw bytes. No disk I/O occurs during recording; only at property access. |

#### Function: `play_beep(frequency=440, duration=0.1, sample_rate=16000) → None`

Generates a sine wave at the specified frequency over the requested duration with fade-in and fade-out envelopes (up to 1% of sample rate or half the wave length) applied to suppress click artifacts. Plays via `sd.play` followed by `sd.wait`. Stateless — no global variables mutated; uses NumPy arrays created fresh per call.

### Error Propagation

No explicit error handling exists in this module. Errors from external I/O (missing microphone device, sounddevice backend unavailable) propagate as unhandled exceptions to the caller. The `.stop()` method does not validate whether the stream is already stopped/closed; calling it twice attempts to stop a `None` stream, which is effectively a no-op rather than an error.

---

## Subsystem: `eloquent_notes.llm` — LLM API Interactions with Ollama

**Responsibility:** Converts raw audio recordings into structured, classified notes by bridging three gaps: speech-to-text, prose polishing, and automatic metadata extraction. All functions communicate via HTTP POST to `{ollama_url}/api/chat`. Shared retry/validation loop: if the response is not valid JSON, lacks required keys, or contains code-fence markdown wrappers, the system logs the failure and re-prompts up to `max_retries` times before raising an error.

### Public API Surface

#### Functions

| Function | Signature | Description |
|----------|-----------|-------------|
| `preload_model(ollama_url, model, context_length, keep_alive="5m", timeout=180)` | — → None (raises on HTTP error) | Preloads model weights into VRAM via an empty Ollama chat request. Reduces cold-start latency when the user stops recording and triggers generation later. Sets `timeout` to 180s default. |
| `transcribe_audio(ollama_url, model, system_prompt, user_prompt, retry_prompt, context_length, audio_bytes, keep_alive="5m", max_retries=3, timeout=300)` | — → `dict[str, Any]` with keys `"empty"` (bool) and `"transcription"` (str) | Phase 1: Transcribes raw audio through Ollama. Audio is base64-encoded in-memory before being sent as an `images` array field. Returns whether the input contained speech (`empty` flag) along with cleaned transcript text. |
| `rewrite_transcription(ollama_url, model, system_prompt, user_prompt, retry_prompt, context_length, keep_alive="5m", max_retries=3, timeout=300)` | — → `dict[str, Any]` with keys `"title"` (str) and `"content"` (str) | Phase 2: Passes the raw transcript to a second LLM call that produces a concise title (max 8 words) and polished content prose. Uses same timeout as transcription phase. |
| `classify_transcription(ollama_url, model, system_prompt, user_prompt, retry_prompt, context_length, keep_alive="0", max_retries=3, timeout=300)` | — → `dict[str, Any]` with keys `"type"` (str), `"wikilinks"` (`list[str]`), `"tags"` (`list[str]`) | Phase 3: Emits three metadata fields. `type`: one of six categories (`task`, `idea`, `note`, `reminder`, `question`, `decision`). `wikilinks`: array of key concepts, proper nouns, or tools worth linking. `tags`: 2–5 lowercase English tags. Resets keep_alive to `"0"` after classification completes. |

#### Internal Helper: `_execute_ollama_json_request`

Performs HTTP POST to `{ollama_url}/api/chat`. Payload structure varies per phase (full chat with format schema). Sets `timeout` based on function defaults. Called by all three public functions and preload model.

### Error Propagation Summary

| Concern | Handling |
|---------|----------|
| HTTP failures (non-2xx) | Uncaught `HTTPError` from `raise_for_status()` — propagates up |
| Malformed JSON / missing keys | Retry up to `max_retries + 1`; final attempt re-raises original error. Caught: `json.JSONDecodeError`, `TypeError`, `ValueError`. Logged at ERROR level with attempt number, task name, raw content, and inner error message. |
| Timeout | Uncaught; propagates directly as `requests.Timeout` |
| Code fence wrapping response | Stripped silently via `_strip_code_fences(text)` before parsing — no error handling; silent pass-through if no match found |
| Other unexpected errors (base64 encoding, regex matching) | Propagate unhandled |

---

## Subsystem: `eloquent_notes.obsidian` — Vault Integration & Note Generation

**Responsibility:** Convert structured dictation output into Obsidian Markdown notes. Handles two storage modes (daily append vs standalone), wikilink injection from vault scans, callout wrapping by note type, and frontmatter tag merging.

### Public API Surface

```python
scan_vault_topics(vault_path: str, max_topics: int = 200) -> list[str]
format_note_content(note_type: str, content: str, wikilinks: list[str]) -> str
save_note(vault_path: str, folder: str, daily_notes: bool, title: str, text: str, tags: list[str], template_standalone: str, template_daily_new: str, template_daily_append: str) -> str
```

### Vault Topic Scan (`scan_vault_topics`)

Walks the markdown file tree under `vault_path`, collects basenames as wikilink candidates. Skips files matching a YYYY-MM-DD date pattern (e.g., `2024-01-15.md`). Results are capped at `max_topics` entries (default 200). Returns an empty list if the path is not a directory; no exception raised — silent fallback per defensive rule.

### Wikilink Injection (`format_note_content`)

Replaces plain-text mentions of collected topics with `[[Topic]]` syntax using word boundaries and case-insensitive matching. Longer terms are processed first to prevent substring conflicts. Terms already wrapped in wikilinks are skipped during substitution. Regex compilation or substitution errors propagate as exceptions without try/except guards.

### Callout Wrapping (within `format_note_content`)

Maps note type — task, idea, reminder, question, decision — to an Obsidian callout variant; wraps content lines with `>` prefix characters inside a `[!type]` block header. Notes of type `"note"` remain unwrapped prose without any callout wrapper.

### Callout Reference State (`_CALLOUT_MAP`)

Module-level dict initialized once at import time. Never reassigned or modified in any function body. Read-only from the caller's perspective (only accessed via `.get()`). No synchronization mechanisms — no locks, mutexes, `async/await`, or atomic types are used anywhere in this module.

### Daily Save Path (`_save_daily`)

Determines whether a daily note file exists for today's date. If missing, creates from `template_new` (includes formatted date, time, title, text, tags). If present, appends using `template_append` after merging any new tags into frontmatter. Opens `.md` files for both read (`"r"`) and write (`"w"`); write failures are not verified — no exception handling around disk I/O.

### Standalone Save Path (`_save_standalone`)

Generates a unique filename based on current timestamp (`Dictation-YYYY-MM-DD-HHMMSS.md`) and writes the full note from the standalone template (includes date, time, title, text, tags). File handle scoped to each call — no shared mutable objects or synchronization primitives.

### Frontmatter Tag Merge (`_update_frontmatter_tags`)

If existing YAML frontmatter is present (`---...---`), loads it and appends any new tags not already in the list; otherwise returns content unchanged. If `yaml.safe_load()` fails on malformed YAML, silently returns `{}` via the `or {}` fallback. Re-dumps with sorted keys disabled and default flow style.

### Delegation (`save_note`)

Public function selects between daily or standalone paths based on a boolean flag. Ensures the target directory exists before writing — calls `os.makedirs()` if needed. Returns the path of the saved note file. No synchronization primitives involved in filesystem writes.

---

## Subsystem: `eloquent_notes.config_gui` — Configuration Dialog & Lifecycle Management

**Responsibility:** Provide a tabbed graphical configuration interface for **Eloquent Notes**, centralizing all user-facing settings management into a single dialog window (`ConfigurationDialog`). Settings are persisted to a YAML configuration file on disk. The subsystem is organized around an abstract contract (`ConfigTab`) that every category-specific tab class implements, ensuring uniform lifecycle behavior across AI model pipeline, audio capture, general/logging, Obsidian integration, prompts, and templates domains.

### Data Flow

```
config_data dict (caller-owned)  ←→  ConfigTab subclasses (instance-scoped UI)  ←→  disk (YAML config / text files)
```

`ConfigurationDialog.__init__` loads the runtime configuration via `eloquent_notes.config.load_config()` into an in-memory dictionary. Each tab's `load_settings()` reads from this shared dict; `save_settings()` writes back into it. The dialog aggregates results across all tabs and persists only differences (via `diff_configs`) to disk on accept.

### Utility Module

#### `utils.py` — `diff_configs(default, current) -> dict`

Recursively computes the set of overrides needed to transform a baseline configuration into the active configuration. Walks every key in `current`; if absent from `default`, records as new; if both values are dicts, recurses; otherwise records leaf-level differences. Empty sub-diffs are pruned before merging upward. Returns an empty dict when no differences exist. No error handling — uncaught exceptions propagate to the caller.

### Styles Module (`styles.py`)

Defines Qt Style Sheets (QSS) for all widget types used in the configuration dialog: `QDialog`, `QWidget`, `QTabWidget::pane`, `QTabBar::tab`, `QPushButton`, `QCheckBox`, `QListWidget`, `QComboBox`, scrollbars, etc. Static string constant `QSS_STYLESHEET` covers base colors, fonts, borders, padding, interactive states (hover/pressed/selected), and scrollbar dimensions. No executable logic; no external I/O.

### Constants Module (`constants.py`)

Module-level constants consumed by tabs that manage editable text files:

| Constant | Type | Contents |
|----------|------|----------|
| `PROMPTS` | `list[tuple[str, Any]]` | Tuples of `(label, system_prompt_path, default_source)` for Transcription/System, Transcription/User, Rewriting/System, Rewriting/User, Classification/System, Classification/User, and Retry prompts. |
| `TEMPLATES` | `list[tuple[str, Any]]` | Tuples of `(label, path, default_source)` for Standalone Note Template, Daily Note - New, Daily Note - Append. |

No external I/O or error handling in this file.

### Base Class Contract (`ConfigTab`) — `eloquent_notes.config_gui.tabs.base`

Abstract base defining the lifecycle contract for every category-specific tab:

| Method | Signature | Contract |
|--------|-----------|----------|
| `load_settings(config_data: dict) -> None` | **abstract**. Subclasses must populate UI controls from `config_data`. No return value. |
| `save_settings(config_data: dict) -> bool` | **abstract**. Write current widget state back into `config_data`. Returns `True` on valid, `False` to signal invalidity (caller surfaces a dialog). |
| `restore_defaults() -> None` | Default body is `pass`. Optional override for custom default restoration. |
| `cleanup() -> None` | Default body is `pass`. Override for tabs with background resources (e.g., model loaders). |

No mutable instance state; pure interface definition. No synchronization mechanisms.

### Text Files Tab Hierarchy (`eloquent_notes.config_gui.tabs.text_files`)

Generic tab for displaying a list of independent text files, allowing per-item selection and in-memory editing via a monospace editor (`QTextEdit`). UI is built as a vertical splitter: left pane lists file entries (`QListWidget`), right pane hosts the editable editor.

**State:**
| Variable | Type | Mutated In | Notes |
|---|------|------------|--------|
| `self.items` | list of `(label, path)` tuples | Constructor only | Read-only thereafter |
| `_block_cache` | bool | `_on_item_changed`, `load_settings`, `restore_defaults` | Guard flag for batch-mode writes to `loaded_contents`. No synchronization. |
| `loaded_contents` | dict (path → str) | All public methods | Primary shared state; read/written across multiple methods with no locking |
| `current_item` | `QListWidgetItem` / None | Constructor, `_on_item_changed`, `restore_defaults` | Cleared when selection is empty |

**Methods:**
- `_init_ui(self)` — Builds the vertical splitter layout.
- `_on_item_changed(self, current, previous)` — Saves content of the previously active item into `loaded_contents` keyed by its path; loads new item's cached or empty content into the editor.
- `commit_active_editor(self)` — Forces current editor contents back into `loaded_contents`. Called before bulk save to flush in-flight edits.
- `load_settings(config_data: dict) -> None` — Reads each configured path via `config.load_file()`, populates `loaded_contents`; auto-selects the first item if any exist. Missing files fall back to a default path (if present) or empty string.
- `restore_defaults(self) -> None` — Clears working state and reloads only from default paths; updates the editor view for whichever item is currently selected.
- `save_settings(config_data: dict) -> bool` — Commits active editor contents via `commit_active_editor()`, then writes every cached file path back to disk using its stored content. Always returns `True`.

**Error Propagation:** No explicit error handling for any file I/O. Every `config.load_file()` and `config.save_file()` call runs without a `try`/`except`. Read failures propagate up to the Qt event loop; write failures are silently swallowed (return value is `True` regardless). Any unhandled exception crashes the UI thread.

#### `PromptsTab` — `eloquent_notes.config_gui.tabs.prompts`

Extends `TextFilesTab`; differs only in constructor parameters:
- `items=PROMPTS` (imported from constants module)
- `editor_label="Prompt Content:"`
- `placeholder="Select a prompt to edit..."`

#### `TemplatesTab` — `eloquent_notes.config_gui.tabs.templates`

Extends `TextFilesTab`; differs only in constructor parameters:
- `items=TEMPLATES` (imported from constants module)
- `editor_label="Template Content:"`
- `placeholder="Select a template to edit..."`

### AI Configuration Tab (`eloquent_notes.config_gui.tabs.ai`) — `AITab`

Manages the AI model pipeline for dictation/voice-to-text using an Ollama-compatible local or remote LLM server. Configures connection URL, selected model, context length (with optional default override), keep-alive durations, retry count, and request timeouts. Tracks background `OllamaModelLoader` lifecycle via signal/slot connections.

**Constructor:** Accepts optional Qt parent widget; initializes UI form controls for all pipeline parameters; sets up initial state including `_model_loader` reference (cleared on exit) and `_running_loaders` set (initially empty).

**Methods:**
| Method | Description |
|--------|-------------|
| `cleanup(self)` | Asynchronously cancels active loaders via `loader.requestInterruption()` with 500 ms wait each; clears loader set and model loader references. No exception handling around `.wait()`. |
| `load_settings(config_data: dict) -> None` | Populates all widgets from an `ai` sub-dict of `config_data`; triggers an initial model fetch that populates a combo box and preserves any previously selected model across reloads. |
| `save_settings(config_data: dict) -> bool` | Reads widget values back into `config_data["ai"]`; validates URL non-emptiness and keep-alive durations against regex `^-?\d+[smh]?`. Returns `False` on validation failure with a warning dialog. |

**Private Methods:**
- `_init_ui(self)` — Builds form controls for all pipeline parameters.
- `_toggle_context_default(self, checked: bool)` — Checkbox disables/enables the context length spinner when checked/unchecked. Spinner range is 512–262144 with step 1024.
- `_fetch_models(self)` — Instantiates `OllamaModelLoader(url, QCoreApplication.instance())`, adds to `_running_loaders` via `.add()`, starts without try/except wrapping. Signal connections wire `finished`, `models_fetched`, and `error_occurred`.
- `_on_loader_finished(self)` — Removes loader from `_running_loaders` via `.discard()`; clears model loader reference.
- `_on_models_fetched(self, models)` | Updates UI label with fetched model list.
- `_on_models_fetch_failed(self, error_msg)` | Updates UI label to `"Connection failed: {error_msg}"` in red.

**State:**
| Variable | Type | Modified By | Notes |
|---|------|-------------|--------|
| `self._model_loader` | OllamaModelLoader / None | `_fetch_models`, cleared in `_on_loader_finished` and `cleanup` | Set in constructor, reassigned on fetch, cleared on completion or cleanup. No synchronization. |
| `self._running_loaders` | set of loaders | Added via `.add()` in `_fetch_models`; removed via `.discard()` or `.clear()` in `_on_loader_finished`/`cleanup`. No sync. | Tracks active background loaders for cancellation and lifecycle management. |

**External I/O:** Network — Ollama model list fetch via `OllamaModelLoader(url)`, outbound HTTP over TCP to the configured URL; errors surface through `loader.error_occurred` signal. Cancellation: `loader.requestInterruption()` + `loader.wait(500)` during cleanup, no timeout exception handling around `.wait()`.

**Error Propagation:** Loader creation in `_fetch_models()` has no try/except — synchronous exceptions propagate uncaught to the GUI thread. Cleanup's `loader.wait(500)` is not wrapped; if stuck or timed out, an unhandled exception may propagate to the GUI thread. Unexpected signals on the loader (beyond the three wired) go to default Qt behavior (likely ignored).

### Audio Configuration Tab (`eloquent_notes.config_gui.tabs.audio`) — `AudioTab`

Graphical configuration panel for microphone/audio capture parameters: sample rate, channel count, audible feedback beeps. No audio processing is performed; only user preference persistence.

**Constructor:** Accepts optional Qt parent widget; calls `_init_ui`.

**Methods:**
| Method | Description |
|--------|-------------|
| `load_settings(config_data: dict) -> None` | Reads `"audio"` sub-dict from `config_data`; populates each widget (sample rate → spinbox value; channel count → combo index mapped 1→0 or 2→1; boolean flags, beep frequency/duration directly). |
| `save_settings(config_data: dict) -> bool` | Writes current widget values back into `"audio"` sub-dict under matching keys (`"sample_rate"`, `"channels"` mapped from index to 1/2, `"beep_enabled"`, `"beep_frequency"`, `"beep_duration"`). Always returns `True`. |

**Private Methods:**
- `_init_ui(self)` — Builds a `QGroupBox` containing five controls: sample rate (`8000–96000 Hz`, step 8000), channel count (Mono/Stereo combo), beep-on-start/stop toggle, beep frequency (`100–5000 Hz`), and beep duration (`0.01–2 sec`).

**State:**
| Attribute | Type | Modified By |
|---|------|-------------|
| `self.spn_sample_rate` | QSpinBox | `_init_ui()` (setValue), `save_settings()` (value()) |
| `self.cmb_channels` | QComboBox | `_init_ui()` (addItems, setCurrentIndex), `save_settings()` (currentIndex) |
| `self.chk_beep_enabled` | QCheckBox | `_init_ui()`, `load_settings()` (setChecked), `save_settings()` (isChecked) |
| `self.spn_beep_freq` | QSpinBox | `_init_ui()` (setRange), `load_settings()` (setValue), `save_settings()` (value()) |
| `self.spn_beep_duration` | QDoubleSpinBox | `_init_ui()` (setRange, setDecimals), `load_settings()` (setValue), `save_settings()` (value()) |

**External I/O:** None. All interactions confined to Qt widget instantiation and the caller-supplied `config_data` parameter. No locks or synchronization mechanisms.

**Error Propagation:** Errors are silently swallowed — `_init_ui()` has no try/except, `load_settings()` has no fallback for missing keys (a single `KeyError` crashes), and `save_settings()` returns hardcoded `True`. The only error path is a bare Python crash on unhandled exceptions during widget construction or dict access.

### General Configuration Tab (`eloquent_notes.config_gui.tabs.general`) — `GeneralTab`

Manages two categories of general behavior: whether the application launches automatically on system login, and how logging behaves (verbosity level, file size cap, number of retained backups). Persists settings under a `"logging"` key. Provides an action to open the background daemon log file in the system editor.

**Constructor:** Accepts optional Qt parent widget; constructs UI for autostart and logging groups.

**Methods:**
| Method | Description |
|--------|-------------|
| `_view_log_file(self)` | Resolves the log file path in the app's log directory, confirms existence (otherwise returns without feedback), then opens with `QDesktopServices.openUrl()`. No write to disk from this function. |
| `load_settings(config_data: dict) -> None` | Populates UI controls from a configuration dictionary; reads values for autostart path, logging level, max log size (MB), and backup count. Checks whether the autostart file exists at runtime via `os.path.exists()`. |
| `save_settings(config_data: dict) -> bool` | Writes current widget state back into the configuration dictionary under a `"logging"` key. Returns `True` on success; returns `False` if autostart update fails (surfaces a critical message box). Catches unexpected errors from sibling module calls and path operations with bare `except Exception as e:`. |

**State:**
| Variable | Scope | Mutated In | Details |
|---|-------|------------|--------|
| `self.chk_autostart` (QCheckBox) | Instance | `_init