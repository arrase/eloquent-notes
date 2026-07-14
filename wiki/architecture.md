# Architecture — Eloquent Notes

## 1. Purpose & Boundaries

**Eloquent Notes** is a persistent system-tray dictation tool. It captures audio from the default microphone, converts it to structured Markdown notes through an Ollama LLM pipeline (transcription → rewrite → classification), and stores the result in an Obsidian vault at `~/Obsidian/Dictations`. The application runs as a PyQt6-based daemon with IPC-based single-instance messaging.

**System boundary:** Desktop application — no networking server, no web frontend, no cloud storage. All processing is local; all data persists on disk under user-controlled directories (`~/.config/Eloquent Notes`, `~/Obsidian/Dictations`).

---

## 2. Module Interaction Map

```
┌───────────────┐   IPC socket      ┌─────────────────────────────────┐
│ CLI / scripts │ ◀──────────────▶ │  EloquentApp (QObject)          │
└───────────────┘                  │  – tray icon activation         │
                                   │  – background processing       │
                                   │  – configuration dialog         │
                                   └──────────┬───────────────────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
          ┌──────────────────┐     ┌──────────────────┐    ┌────────────────────┐
          │  AudioRecorder   │     │   _process_audio  │    │  ConfigurationDialog│
          │                  │     │                   │    │                    │
          │ sd.InputStream   │     │ Phase 1: LLM      │    │ Tab-based YAML UI  │
          │ WAV bytes        │     │ transcribe       │    │ (ai, audio,         │
          └────────┬─────────┘     │ rewrite          │    │  general, prompts,   │
                   │               │ classify         │    │  templates)        │
                   ▼               └────────┬─────────┘    └──────────┬──────────┘
              ┌─────────────────────────────┴───────┐                │
              │   LLM pipeline (Ollama HTTP)         │                │
              │   – preload_model                    │                ▼
              │   – transcribe_audio                 │    ┌────────────────────┐
              │   – rewrite_transcription            │    │  Obsidian vault    │
              │   – classify_transcription          │    │  scan_vault_topics │
              └─────────────────────────────┬───────┘    └────────┬───────────┘
                                            │                   │
                                            ▼                   │
                                       Vault context → prompt combined with LLM calls
                                            │                   │
                                            ▼                   │
                                       Note assembly (template substitution) → obsidian.save_note() write to disk
```

**Module interaction rules:**

- `EloquentApp` owns lifecycle and state. Worker threads (`AudioRecorder`, `_process_audio`) are spawned by it; results return through PyQt signals/slots.
- `ConfigurationDialog` reads/writes a shared YAML config dict via the `ConfigTab` abstract contract. Tabs are independent instances of subclasses that read from/write to the same caller-owned dictionary.
- IPC (via `QLocalServer`, socket name `eloquent_notes_ipc`) carries four recognized commands: `"toggle"`, `"reload"`, `"notify_running"` — plus an unknown-message fallback path. CLI scripts connect to this socket or launch a new daemon if none is reachable.

---

## 3. Subsystem Interfaces

### `eloquent_notes.audio`

| Interface | Direction | Notes |
|-----------|-----------|-------|
| `AudioRecorder.__init__(sample_rate, channels)` | Constructor | Initializes input stream queue. No error handling around device discovery. |
| `AudioRecorder.start()` / `stop()` | Method pair | `start()` opens `sd.InputStream`; incoming samples enqueue chunks. `stop()` closes the stream; calling on an already-stopped recorder is a no-op rather than an error. |
| `wav_bytes` (property) | Lazy access | Drains queued chunks, concatenates along time axis, scales to 16-bit PCM, writes in-memory WAV via `io.BytesIO`/`wave`. No disk I/O during recording; only at property read. |
| `play_beep(frequency, duration)` | Stateless helper | Sine wave with fade envelopes (≤1% of sample rate or half wave length). Uses fresh NumPy arrays per call. Errors propagate unhandled. |

### `eloquent_notes.llm`

All public functions communicate via HTTP POST to `{ollama_url}/api/chat`. Shared retry/validation: if the response is not valid JSON, lacks required keys, or contains code-fence markdown wrappers, failures are logged and re-prompts occur up to `max_retries` times before raising.

| Function | Return shape | Notes |
|----------|-------------|-------|
| `preload_model(url, model, context_length, keep_alive="5m", timeout=180)` | None (raises on HTTP error) | Empty chat request; reduces cold-start latency. |
| `transcribe_audio(...)` | `{"empty": bool, "transcription": str}` | Audio base64-encoded into an `images` array field. |
| `rewrite_transcription(...)` | `{"title": str, "content": str}` | Title ≤8 words; polished prose content. |
| `classify_transcription(...)` | `{"type": str, "wikilinks": list[str], "tags": list[str]}` | `type` ∈ {task, idea, note, reminder, question, decision}. `keep_alive="0"` after classification completes. |

### `eloquent_notes.obsidian`

| Function | Purpose | Notes |
|----------|---------|-------|
| `scan_vault_topics(vault_path, max_topics=200)` → `list[str]` | Walks markdown tree; collects basenames as wikilink candidates. Skips YYYY-MM-DD files. Returns empty list if path is not a directory. No exception raised on failure. |
| `format_note_content(note_type, content, wikilinks)` → `str` | Replaces plain-text topic mentions with `[[Topic]]` syntax using word boundaries and case-insensitive matching. Longer terms processed first to prevent substring conflicts. Terms already wrapped are skipped during substitution. |
| `save_note(vault_path, folder, daily_notes, title, text, tags, ...)` → `str` (path) | Delegates to `_save_daily` or `_save_standalone`. Ensures target directory exists via `os.makedirs()`. Returns saved file path. No synchronization primitives in filesystem writes. |

**Internal paths within `save_note`:**

- `_save_daily`: checks if today's daily note exists; creates from `template_new` or appends to existing using `template_append`; merges new tags into frontmatter via YAML parse/dump (malformed YAML → `{}` silently).
- `_save_standalone`: generates `Dictation-YYYY-MM-DD-HHMMSS.md`; writes full note from standalone template.
- `_update_frontmatter_tags`: appends new tags not already present; returns content unchanged if no frontmatter exists.

### `eloquent_notes.app` (`EloquentApp(QObject)`)

| Method | Purpose | Notes |
|--------|---------|-------|
| `__init__(qapp, start_recording_immediately)` | Initializes tray icon activation and local IPC server (socket: `eloquent_notes_ipc`). If `start_recording_immediately=True`, recording begins on first run. |
| `run()` / `exit_app()` | Main loop entry and cleanup. Cleanup stops recorder if in RECORDING/STARTING_RECORDING, joins processing thread with 5s timeout, closes IPC server, hides tray icon, exits via `sys.exit`. |
| `_on_tray_activated(reason)` | Handles tray clicks/context-menu: toggle recording, open config dialog, reload config, quit. Dispatches accordingly. |
| `_handle_ipc_connection()` | Processes `"toggle"`, `"reload"`, `"notify_running"` — unknown messages fall through silently. |
| `_update_icon(color, tooltip)` | Updates tray icon visual state and tooltip text to reflect recording/processing status. |
| `_notify(title, message)` | Emits desktop notification (tray balloon). Called on processing completion (success/empty/error) and config reload errors. |
| `toggle_action()` | Exposed to main window or IPC. Triggers start if idle, stop+process if recording, busy notification otherwise. |
| `_preload_model()` | Launches LLM preload in daemon thread (non-blocking relative to GUI). Warnings logged but non-fatal on failure. |
| `_start_recording()` | Spawns `threading.Thread` that starts audio recorder; emits optional startup beep via `audio.play_beep()`. Transitions state → RECORDING; simultaneously triggers model preloading thread. On failure: reverts to IDLE, emits error signal. |
| `_stop_recording_and_process()` | Spawns background thread that stops recorder, retrieves WAV bytes, executes full LLM pipeline. Emits processing-start beep. State → PROCESSING. |
| `_build_vault_context()` → `str` | Scans Obsidian vault directory structure (if `vault_context` is true in config) and returns note names for inclusion in classification prompt. Empty string if no topics found. |
| `_process_audio()` | Executes three-phase LLM pipeline: transcribe, rewrite, classify. Each phase uses configurable timeout (`request_timeout`). Wrapped in try/except; exceptions → `"error"` status signal. Emits `processing_completed`. |
| `_on_processing_completed(status, detail)` | Receives result via `processing_completed` signal. Sets state → IDLE. On success: notification with filename. Empty: shows "Empty". Error: surfaces failure via tray. |
| `reload_config()` / `show_config_dialog()` / `_on_config_dialog_closed(_result)` | Configuration lifecycle managed through GUI dialog and IPC-triggered reloads. |

### `eloquent_notes.config_gui` (`ConfigurationDialog`)

**Data flow:** `config_data` dict (caller-owned) ←→ `ConfigTab` subclasses (instance-scoped UI) ←→ disk (YAML config / text files). Each tab's `load_settings()` reads from the shared dict; `save_settings()` writes back into it. The dialog aggregates across tabs and persists only differences (via `diff_configs`) to disk on accept.

**Utility: `utils.py` — `diff_configs(default, current) -> dict`:** Recursively computes overrides needed to transform baseline config into active config. Walks every key in `current`; absent from `default` → new; both dicts → recurse; otherwise leaf-level difference recorded. Empty sub-diffs pruned before merging upward. Returns empty dict when no differences exist. No error handling — uncaught exceptions propagate.

**Styles: `styles.py`:** Qt Style Sheets (QSS) for all widget types used in the configuration dialog (`QDialog`, `QWidget`, `QTabWidget::pane`, `QTabBar::tab`, `QPushButton`, `QCheckBox`, `QListWidget`, `QComboBox`, scrollbars, etc.). Static constant `QSS_STYLESHEET` covers base colors, fonts, borders, padding, interactive states (hover/pressed/selected), and scrollbar dimensions. No executable logic; no external I/O.

**Constants: `constants.py`:** Module-level constants consumed by tabs that manage editable text files.

| Constant | Type | Contents |
|----------|------|----------|
| `PROMPTS` | `list[tuple[str, Any]]` | Tuples of `(label, system_prompt_path, default_source)` for Transcription/System, Transcription/User, Rewriting/System, Rewriting/User, Classification/System, Classification/User, Retry prompts. |
| `TEMPLATES` | `list[tuple[str, Any]]` | Tuples of `(label, path, default_source)` for Standalone Note Template, Daily Note - New, Daily Note - Append. |

**Base contract: `ConfigTab` (`eloquent_notes.config_gui.tabs.base`):**

| Method | Contract |
|--------|----------|
| `load_settings(config_data) -> None` | Subclasses populate UI from `config_data`. No return value. |
| `save_settings(config_data) -> bool` | Write current widget state back into `config_data`. Returns `True` on valid, `False` to signal invalidity (caller surfaces a dialog). |
| `restore_defaults() -> None` | Default body is `pass`. Optional override for custom default restoration. |
| `cleanup() -> None` | Default body is `pass`. Override for tabs with background resources (e.g., model loaders). |

**Text Files Tab hierarchy (`eloquent_notes.config_gui.tabs.text_files`):** Generic tab displaying a list of independent text files, allowing per-item selection and in-memory editing via `QTextEdit`. UI built as vertical splitter: left pane lists file entries (`QListWidget`), right pane hosts the editable editor.

| Variable | Mutated In | Notes |
|----------|------------|--------|
| `self.items` | Constructor only | Read-only thereafter; list of `(label, path)` tuples. |
| `_block_cache` | `_on_item_changed`, `load_settings`, `restore_defaults` | Guard flag for batch-mode writes to `loaded_contents`. No synchronization. |
| `loaded_contents` | All public methods | Dict (path → str). Primary shared state; read/written across multiple methods with no locking. |
| `current_item` | Constructor, `_on_item_changed`, `restore_defaults` | Cleared when selection is empty. |

**Methods:**
- `_init_ui()` — Builds vertical splitter layout.
- `_on_item_changed(current, previous)` — Saves content of previously active item into `loaded_contents` keyed by path; loads new item's cached or empty content into editor.
- `commit_active_editor()` — Forces current editor contents back into `loaded_contents`. Called before bulk save to flush in-flight edits.
- `load_settings(config_data)` — Reads each configured path via `config.load_file()`, populates `loaded_contents`; auto-selects first item if any exist. Missing files fall back to default path (if present) or empty string.
- `restore_defaults()` — Clears working state; reloads only from default paths; updates editor view for whichever item is currently selected.
- `save_settings(config_data)` — Commits active editor contents via `commit_active_editor()`, then writes every cached file path back to disk using stored content. Always returns `True`.

**`PromptsTab`:** Extends `TextFilesTab`; differs only in constructor parameters: `items=PROMPTS` (from constants module), `editor_label="Prompt Content:"`, `placeholder="Select a prompt to edit..."`.

**`TemplatesTab`:** Extends `TextFilesTab`; differs only in constructor parameters: `items=TEMPLATES` (from constants module), `editor_label="Template Content:"`, `placeholder="Select a template to edit..."`.

**`AITab` (`eloquent_notes.config_gui.tabs.ai`):** Manages AI model pipeline for dictation/voice-to-text using an Ollama-compatible local or remote LLM server. Configures connection URL, selected model, context length (with optional default override), keep-alive durations, retry count, and request timeouts. Tracks background `OllamaModelLoader` lifecycle via signal/slot connections.

| Method | Notes |
|--------|-------|
| `cleanup()` | Asynchronously cancels active loaders via `loader.requestInterruption()` with 500 ms wait each; clears loader set and model loader references. No exception handling around `.wait()`. |
| `load_settings(config_data)` | Populates widgets from `config_data["ai"]` sub-dict; triggers initial model fetch that populates combo box and preserves any previously selected model across reloads. |
| `save_settings(config_data)` | Reads widget values back into `config_data["ai"]`; validates URL non-emptiness and keep-alive durations against regex `^-?\d+[smh]?`. Returns `False` on validation failure with a warning dialog. |

**State (AITab):**

| Variable | Modified By | Notes |
|----------|-------------|-------|
| `self._model_loader` | `_fetch_models`, cleared in `_on_loader_finished` and `cleanup` | Set in constructor, reassigned on fetch, cleared on completion or cleanup. No synchronization. |
| `self._running_loaders` | Added via `.add()` in `_fetch_models`; removed via `.discard()` or `.clear()` in `_on_loader_finished`/`cleanup`. No sync. | Tracks active background loaders for cancellation and lifecycle management. |

**External I/O (AITab):** Network — Ollama model list fetch via `OllamaModelLoader(url)`, outbound HTTP over TCP to configured URL; errors surface through `loader.error_occurred` signal. Cancellation: `loader.requestInterruption()` + `loader.wait(500)` during cleanup, no timeout exception handling around `.wait()`.

**`AudioTab` (`eloquent_notes.config_gui.tabs.audio`):** Graphical configuration panel for microphone/audio capture parameters (sample rate, channel count, audible feedback beeps). No audio processing; only user preference persistence.

| Method | Notes |
|--------|-------|
| `load_settings(config_data)` | Reads `"audio"` sub-dict from `config_data`; populates each widget (sample rate → spinbox value; channel count → combo index mapped 1→0 or 2→1; boolean flags, beep frequency/duration directly). |
| `save_settings(config_data)` | Writes current widget values back into `"audio"` sub-dict under matching keys (`"sample_rate"`, `"channels"` mapped from index to 1/2, `"beep_enabled"`, `"beep_frequency"`, `"beep_duration"`). Always returns `True`. |

**State (AudioTab):**

| Attribute | Mutated By |
|-----------|------------|
| `self.spn_sample_rate` | `_init_ui()` (setValue), `save_settings()` (value()) |
| `self.cmb_channels` | `_init_ui()` (addItems, setCurrentIndex), `save_settings()` (currentIndex) |
| `self.chk_beep_enabled` | `_init_ui()`, `load_settings()` (setChecked), `save_settings()` (isChecked) |
| `self.spn_beep_freq` | `_init_ui()` (setRange), `load_settings()` (setValue), `save_settings()` (value()) |
| `self.spn_beep_duration` | `_init_ui()` (setRange, setDecimals), `load_settings()` (setValue), `save_settings()` (value()) |

**External I/O:** None. All interactions confined to Qt widget instantiation and caller-supplied `config_data`. No locks or synchronization mechanisms.

**Error Propagation (AudioTab):** Errors silently swallowed — `_init_ui()` has no try/except, `load_settings()` has no fallback for missing keys (a single `KeyError` crashes), `save_settings()` returns hardcoded `True`. The only error path is a bare Python crash on unhandled exceptions during widget construction or dict access.

**`GeneralTab` (`eloquent_notes.config_gui.tabs.general`):** Manages two categories: whether the application launches automatically on system login, and how logging behaves (verbosity level, file size cap, number of retained backups). Persists settings under `"logging"` key. Provides an action to open the background daemon log file in the system editor.

| Method | Notes |
|--------|-------|
| `_view_log_file()` | Resolves log file path in app's log directory; confirms existence (otherwise returns without feedback); opens with `QDesktopServices.openUrl()`. No write to disk from this function. |
| `load_settings(config_data)` | Populates UI controls from configuration dictionary; reads values for autostart path, logging level, max log size (MB), and backup count. Checks whether the autostart file exists at runtime via `os.path.exists()`. |
| `save_settings(config_data)` | Writes current widget state back into configuration dictionary under `"logging"` key. Returns `True` on success; returns `False` if autostart update fails (surfaces a critical message box). Catches unexpected errors from sibling module calls and path operations with bare `except Exception as e:`. |

**State (GeneralTab):**

| Variable | Scope | Mutated In | Details |
|----------|-------|------------|---------|
| `self.chk_autostart` (QCheckBox) | Instance | `_init_ui()` (setChecked), `load_settings()` (isChecked), `save_settings()` (setChecked) | Controls autostart behavior. Checked state reflects whether an autostart file exists at runtime. |

---

## 4. Initialization & Configuration Lifecycle

1. CLI parses arguments (`install-autostart`, `config`, `toggle`, default).
2. If no running daemon is reachable via IPC socket, a new process launches; if one exists, it receives `"toggle"` or `"notify_running"`.
3. On startup: `config.init_config_dir()` seeds user directories with bundled defaults; `load_config()` merges default YAML with user overrides (recursive merge).
4. Logging setup writes to XDG STATE_HOME via `logging_utils.setup_logging()`.
5. If `config` subcommand → launch `ConfigurationDialog`; if no argument or `toggle` → IPC connect.

---

## 5. Thread Architecture

| Thread | Purpose | Notes |
|--------|---------|-------|
| Main GUI thread (Qt event loop) | Tray icon, signals/slots, configuration dialog UI | PyQt signals provide implicit synchronization for passing results back to the main thread but do not protect mutable attributes accessed during transition phases. |
| `AudioRecorder` (background thread spawned by `_start_recording()`) | Microphone capture as WAV bytes | Reads/writes application state attributes directly without protection; no locks or mutexes present. |
| `_process_audio` (daemon thread) | Three-phase LLM pipeline execution | Each phase uses configurable timeout (`request_timeout`). Wrapped in try/except; any exception is caught and converted to `"error"` status signal. |
| Model preloading (daemon thread from `_preload_model()`) | Loads model weights into VRAM before recording begins | Non-blocking relative to GUI. Warnings logged but non-fatal on failure. |

**Thread safety notes:** No synchronization mechanisms (locks, mutexes) are present anywhere in the codebase as documented. Direct attribute access (`self.state`, `self.recorder`) from worker threads occurs without protection. `threading.Thread` objects spawned in `_start_recording` and `_stop_recording_and_process` read/write application state attributes directly. PyQt signals/slots provide implicit synchronization for passing results back to the GUI thread but do not protect mutable attributes accessed during transition phases.

---

## 6. Error Handling Patterns (as documented)

| Concern | Handling |
|---------|----------|
| Missing microphone / sounddevice backend unavailable | Propagates as unhandled exceptions to caller. No try/except guards. |
| HTTP failures (non-2xx) in LLM calls | Uncaught `HTTPError` from `raise_for_status()` — propagates up. |
| Malformed JSON / missing keys in LLM responses | Retry up to `max_retries + 1`; final attempt re-raises original error. Caught: `json.JSONDecodeError`, `TypeError`, `ValueError`. Logged at ERROR level with attempt number, task name, raw content, and inner error message. |
| Timeout on LLM requests | Uncaught; propagates directly as `requests.Timeout`. |
| Code fence wrapping response | Stripped silently via `_strip_code_fences(text)` before parsing — no error handling; silent pass-through if no match found. |
| Other unexpected errors (base64 encoding, regex matching) | Propagate unhandled. |
| File I/O in `obsidian.save_note()` | Write failures are not verified — no exception handling around disk I/O. |
| Configuration tab widget construction / dict access | Bare Python crash on unhandled exceptions during widget construction or dict access. |
| AITab loader `.wait(500)` | Not wrapped; if stuck or timed out, an unhandled exception may propagate to the GUI thread. |