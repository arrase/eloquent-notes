# Eloquent Notes — Architecture Documentation

---

## Module Responsibility & Data Flow Overview

Eloquent Notes is a Qt-based desktop application that captures microphone input as WAV bytes, transcribes audio via an Ollama-hosted LLM through a three-phase pipeline (transcription → rewriting → classification), and persists the output into an Obsidian vault with wikilinks and callouts. The architecture separates concerns into: **application lifecycle** (`app.py`), **audio capture** (`audio.py`), **configuration persistence** (`config.py`, `templates/`), **LLM orchestration** (`llm.py`), **Obsidian integration** (`obsidian.py`), **system tray / IPC** (`ui.py`, implicit in `app.py`), and **logging** (`logging_utils.py`).

Data flows from user input through `_start_recording()` → audio queue buffer → `_stop_recording_and_process()` → daemon-threaded LLM pipeline (`llm.py` transcribe/rewrite/classify) → Obsidian write path (`obsidian.py` save_note). Configuration is loaded once via `config.load_config()`, merged, and persisted via `save_config()`. The app communicates with system tray (via `_update_icon()` / Pillow icon generation in `ui.py`) and local IPC socket ("eloquent_notes_ipc") for toggle/reload/notify_running commands.

---

## Entry Point & CLI Dispatch (`main.py`)

**`main()`** — Parses CLI arguments, dispatches to IPC toggle handler, configuration GUI dialog (via `ConfigurationDialog` from `config_gui.dialog`), or daemon launch. **`install_autostart()`** — re-exports from `eloquent_notes.autostart`; registers a `.desktop` entry in `~/.config/autostart/` using the executable resolved via `shutil.which()`, file permissions 0o644.

```
CLI argument ──► main() ──► dispatch { IPC toggle | config GUI | daemon }
```

---

## Application Lifecycle Controller (`app.py`)

**`EloquentApp(QObject)`** — Central controller managing recording lifecycle, IPC communication, system tray UI, and three-phase Ollama pipeline orchestration. State machine: **IDLE → RECORDING → PROCESSING → IDLE**.

| Method | Responsibility |
|--------|---------------|
| `__init__(qapp, start_recording_immediately=False)` | Initializes with QApplication reference; connects processing-completion signal handlers. |
| `run()` | Sets up system tray icon, local IPC server on "eloquent_notes_ipc", context menu actions; enters Qt event loop until exit. |
| `_on_tray_activated(reason)` | Delegates to `toggle_action` when tray icon clicked directly. |
| `_handle_ipc_connection()` | Reads incoming socket messages; dispatches "toggle" / "reload" / "notify_running". |
| `_update_icon(color, tooltip)` | Qt QIcon from Pillow-rendered 64×64 RGBA image (red/orange/gray based on state). |
| `_notify(title, message)` | System tray informational notification. |
| `toggle_action()` | Routes: IDLE→start recording; RECORDING→stop & process; BUSY→busy notification. |
| `_preload_model()` | Loads AI model using config values (context length, keep-alive duration, timeout). |
| `_start_recording()` | Audio recorder in daemon thread after preloading prompt files into active config to avoid main/worker race conditions. |
| `_stop_recording_and_process()` | Stops recorder; launches background processing daemon thread for transcription → rewriting → classification → note saving. |
| `_build_vault_context()` | Scans Obsidian vault for known topics; returns formatted context string usable as WikiLink references in interpretation prompts. |
| `_process_audio()` | Executes complete three-phase LLM pipeline: transcribe audio to text → rewrite into structured note → classify with metadata extraction → format & save as Obsidian note. Emits `processing_completed` signal on completion or error. |
| `_on_processing_completed(status, detail)` | Updates app state back to IDLE; updates tray icon; notifies user based on success/empty/error status. |
| `reload_config()` | Reloads config from disk; reinitializes logging with new level settings; notifies of success or errors. |
| `show_config_dialog()` | Creates/displays ConfigurationDialog if not shown; raises and activates existing dialog to prevent duplicates. |
| `_on_config_dialog_closed(_result)` | Deletes config dialog reference after closure; schedules QTimer single-shot cleanup for thread safety. |
| `_clear_config_dialog_reference()` | Clears stored config dialog reference for garbage collection eligibility. |
| `exit_app()` | Gracefully shuts down recording, processing threads, config dialogs, IPC server, system tray before calling `QApplication::quit()` and `sys.exit()`. |

---

## Audio Capture (`audio.py`)

**`AudioRecorder`** — Captures microphone input as WAV bytes using a queue-based buffer with lazy encoding strategy. **`play_beep()`** — Synthesizes short sine-wave tone with fade envelopes to prevent audible clicks; plays via system audio.

```
Microphone ──► AudioRecorder (queue buffer) ──► WAV bytes ──► llm.py transcribe_audio()
                                        │
                                      play_beep() (feedback tone)
```

---

## Autostart Registration (`autostart.py`)

**`install_autostart()`** — Writes `.desktop` file to `~/.config/autostart/`, executable path resolved via `shutil.which()`, permissions 0o644. Invoked from `main.py` install_autostart re-export.

---

## Configuration Management (`config.py`)

### Path Constants

| Constant | Description |
|----------|-------------|
| `CONFIG_DIR` | Base user config directory: `~/.config/eloquent-notes`. |
| `CONFIG_PATH` | Absolute path to main YAML configuration within `CONFIG_DIR`. |
| `PROMPTS_DIR`, `TEMPLATES_DIR` | Subdirectories under `CONFIG_DIR` for prompt templates and note templates. |
| `PACKAGE_DIR`, `DEFAULT_CONFIG_SRC`, etc. | Bundled defaults inside the package, used as fallback sources during initialization. |

### Functions

**`init_config_dir()`** — Creates `CONFIG_DIR`, `PROMPTS_DIR`, `TEMPLATES_DIR`; copies bundled default files if absent. **`load_config()`** — Reads bundled default YAML + existing user config from `~/.config/eloquent-notes/config.yaml`; returns recursively merged result. **`save_config(config_data)`** — Writes configuration dict to `CONFIG_PATH` via YAML serialization. **`load_file(path)`**, **`save_file(path, content)`** — File I/O wrappers with parent directory creation.

### Configuration Schema (`config.yaml`)

Static YAML organized into four sections:
- **`obsidian`** — vault path, folder, daily notes flag, vault context
- **`ai`** — Ollama URL, model name, context length, keep-alive durations, retry/timeout values
- **`audio`** — sample rate, channels, beep frequency/duration/enabled
- **`logging`** — level, max file size (MB), backup count

---

## LLM Pipeline Orchestration (`llm.py`)

### Model Preload & Request Execution

| Function | Responsibility |
|----------|---------------|
| `_CODE_FENCE_RE`, `_strip_code_fences(text)` | Regex for matching markdown code fences wrapping structured Ollama responses; strips before JSON parsing. |
| `preload_model(ollama_url, model, context_length, keep_alive="5m", timeout=180)` | Sends empty chat request to preload model weights into VRAM; reduces cold-start latency. |
| `_execute_ollama_json_request(...)` | Structured JSON-output Ollama chat request with retry logic for malformed responses or missing required keys. |

### Three-Phase Pipeline

All three functions follow identical invocation pattern: `system_prompt`, `user_prompt`, `retry_prompt` templates + context length + keep-alive duration + timeout.

| Function | Phase | Responsibility |
|----------|-------|---------------|
| `transcribe_audio(...)` | Phase 1 | Transcribes audio through Ollama; returns dict with `'empty'` boolean and clean transcription text. |
| `_rewrite_transcription(ollama_url, model, system_prompt, user_prompt, retry_prompt, context_length, keep_alive="5m", max_retries=3, timeout=300)` | Phase 2 | Rewrites raw transcription into structured note prose with title + content fields. |
| `classify_transcription(...)` | Phase 3 | Classifies note into type category; extracts wikilinks for key concepts; assigns relevant tags. |

---

## Logging Infrastructure (`logging_utils.py`)

**`get_log_dir()`** — Returns absolute path to Eloquent Notes log directory by resolving `XDG_STATE_HOME`, falling back to `~/.local/state`. **`setup_logging(log_level_str, max_mb, backup_count)`** — Configures `eloquent_notes` logger with console handler + optional rotating file handler under XDG-compliant log directory.

---

## Obsidian Integration (`obsidian.py`)

### Data Structures

| Structure | Description |
|-----------|-------------|
| `_CALLOUT_MAP` | Dict mapping note types (task, idea) to Obsidian callout syntax identifiers for wrapping formatted dictation output. |
| `_DATE_FILENAME_RE` | Compiled regex matching `YYYY-MM-DD` filenames; excludes from vault topic scanning results. |

### Functions

**`scan_vault_topics(vault_path, max_topics=200)`** — Recursively scans Obsidian vault for markdown basenames usable as wikilinks; skips date-named files; caps output to configurable limit. **`_inject_wikilinks(text, wikilinks)`** — Converts plain-text mentions into `[[WikiLink]]` syntax by processing longer terms first with word boundaries to avoid substring collisions. **`format_note_content(note_type, content, wikilinks)`** — Injects wikilinks and wraps in Obsidian callout based on note type; leaves plain notes unwrapped. **`_update_frontmatter_tags(content, new_tags)`** — Merges new tags into existing YAML frontmatter preserving surrounding content; avoids duplicates.

### Note Saving

| Function | Responsibility |
|----------|---------------|
| `_save_daily(target_dir, date_str, time_str, title, text, tags, template_new, template_append)` | Saves to daily-aggregated note: creates from `template_new` if missing or appends via `template_append`. |
| `_save_standalone(...)` | Writes standalone timestamped markdown file for single dictation entry. |
| **`save_note(vault_path, folder, daily_notes, title, text, tags, template_standalone, template_daily_new, template_daily_append)`** | Main export function: routes to `_save_daily` or `_save_standalone` based on `daily_notes` flag. |

---

## System Tray Icon Generation (`ui.py`)

**`create_icon_image(color)`** — Creates 64×64 RGBA icon image for specified state color (red/orange/gray) using Pillow drawing primitives. **`get_qicon(color)`** — Converts Pillow-rendered icon into Qt `QIcon` by saving as PNG and loading into `QPixmap`.

---

## Configuration GUI Subsystem (`config_gui`)

### Responsibility & Data Flow

Multi-tab PyQt6 dialog (`ConfigurationDialog`) aggregates domain-specific tab widgets, persists state to application-wide configuration dictionary, dispatches asynchronous background jobs (Ollama model fetching) via `QThread` subclasses.

```
User Interaction ──► ConfigurationDialog.accept() / reject()
    │                         │
    ▼                         ▼
┌──────────────┐      ┌──────────────────┐
│  Per-Tab Tab │◄────►│   save_settings  │
│  Widget Tree │      │ config_data:dict │
└──────────────┘      └──────────────────┘
    │                         │
    ▼                         ▼
┌──────────────┐      ┌──────────────────┐
│  cleanup()   │      │ diff_configs     │
│ stop threads │      │ (optional)       │
└──────────────┘      └──────────────────┘
```

### Constants & Styles

**`constants.py`** — Exports `PROMPTS` (display-name → file-path + default-source string mappings for transcription, rewriting, classification, retry) and `TEMPLATES` (label → path + source mappings for note templates). **`styles.py`** — `QSS_STYLESHEET`: raw Qt Style Sheets string covering all dialog controls (`QDialog`, `QWidget`, `QTabWidget`, `QLineEdit`, `QPushButton`, `QListWidget`, `QGroupBox`, `QScrollBar`).

### Base Infrastructure: `ConfigTab` (Abstract Contract)

| Method | Description |
|--------|-------------|
| `load_settings(config_data)` → None | Populates UI widgets from configuration dictionary. |
| `save_settings(config_data)` → bool | Collects current widget state, validates inputs (e.g., regex-normalizes keep-alive durations in AITab), writes resolved values into config_data; returns True only when all persisted data is valid. |
| `restore_defaults()` → None | Resets interface to factory state without raising exceptions. |
| `cleanup()` → None | Releases background threads and resources prior to destruction; no-op by default, overridden in tabs running async jobs (AITab). |

### Tab Implementations

#### 3.1 General Application Settings — `general.py`

**`GeneralTab`** (`config_gui/tabs/general.py`) — Manages startup options and logging settings. Widget hierarchy: Vertical layout with `QGroupBox` controls for autostart checkboxes, logging level/size/backup spinboxes, log file viewer button. **`_view_log_file()`** opens background daemon log in system editor if it exists; otherwise displays informational message indicating dictations must run first.

#### 3.2 Audio Capture — `audio.py` (config_gui)

**`AudioTab`** (`config_gui/tabs/audio.py`) — Manages audio capture settings (sample rate, feedback beep). Standard `ConfigTab` contract with dedicated persistence methods.

#### 3.3 AI Pipeline Integration — `ai.py`

**`AITab`** (`config_gui/tabs/ai.py`) — Manages Ollama connection details and pipeline settings; runs background model loading via `OllamaModelLoader`. Widget hierarchy: form layouts, text inputs, spin boxes, group boxes for AI settings. **`_fetch_models()`** constructs `OllamaModelLoader`; connects signal handlers (`models_fetched`, `error_occurred`) to update UI state. **`cleanup()`** asynchronously cancels all active background loaders and clears internal state to prevent orphaned processes during tab disposal/destruction.

#### 3.4 Obsidian Integration — `obsidian.py` (config_gui)

**`ObsidianTab`** (`config_gui/tabs/obsidian.py`) — Manages vault path, target folder, daily notes appending, wikilink suggestions. **`_browse_vault_path()`** opens system file dialog prompting user selection of existing Obsidian vault directory. Validates vault path existence on disk (with optional confirmation dialog) during save.

#### 3.5 Text File Management — `text_files.py`, `prompts.py`, `templates.py`

| Class | File | Responsibility |
|-------|------|---------------|
| `TextFilesTab` | `config_gui/tabs/text_files.py` | Base class for prompt and template tabs; provides list-view interface for editing/managing multiple text files. |
| `PromptsTab` | `config_gui/tabs/prompts.py` | Manages prompt content editing; maintains predefined items + associated editor labels per configurable prompt entry. |
| `TemplatesTab` | `config_gui/tabs/templates.py` | Manages template-specific settings; initializes with predefined items and specialized UI labels for template content editing. |

Both `PromptsTab` and `TemplatesTab` extend `TextFilesTab`, inheriting list-view structure while adding domain-specific initialization logic. Persistence contract delegated to base class.

### Orchestration Layer: `ConfigurationDialog`

**`__init__(self)`** — Constructs and wires all tab instances; registers signal/slot connections for accept/reject/cleanup lifecycle. **`load_settings_to_ui(config_data)`** populates all tab widget states by reading values from previously loaded configuration dictionary, delegating to each tab's `load_settings()`. **`save_settings_from_ui(config_data)`** validates and persists all current widget states back to disk by calculating overrides against default configuration file; returns boolean success indicator. **`cleanup_tabs()`** iterates through all tab widgets to release resources before dialog window closes. **`accept()` / `reject()`** trigger save/cancel respectively with thread cleanup guarantees.

### Background Thread Infrastructure: `OllamaModelLoader` (`QThread` Subclass)

| Signal | Emitted When | Payload |
|--------|-------------|---------|
| `models_fetched` | Loading process finishes without interruption | List of audio-capable model names (str) |
| `error_occurred` | Exception occurs during API interaction or processing | Error message string (str) |

Subclasses `QThread`; runs fetch-and-validate logic in worker thread; emits signals on completion/failure; connected to `AITab._fetch_models()` which tracks loader instances and updates UI state based on signal payloads.

---

## Template Registry (`templates/`)

### Module Responsibility & Data Flow

Static collection of Markdown/YAML frontmatter templates consumed by the note-generation engine at render time. Each template defines a document schema via YAML metadata followed by interpolation placeholders delimited by `{...}`. At runtime, the rendering pipeline substitutes each placeholder with the corresponding context value supplied by the originating service (dictation client, CLI flag, or REST payload). Templates are not compiled; loaded as-is and interpolated on demand.

**Data flow:**
1. Renderer resolves `template_name` from user input or default configuration.
2. Template file is read from this module's filesystem directory.
3. Context map `{title, text, date, time, tags}` constructed by upstream caller.
4. String interpolation substitutes all `{...}` placeholders in a single pass.
5. Resulting Markdown document returned to caller for persistence or streaming.

### Templates

| Template | File | Placeholder Contract |
|----------|------|---------------------|
| `daily_append.md` | `eloquent_notes/templates/daily_append.md` | Used when appending to existing day's entry; omits frontmatter date/time metadata, relying on caller to inject via context substitution. Placeholders: `{time}`, `{title}`, `{text}`. |
| `daily_new.md` | `eloquent_notes/templates/daily_new.md` | Full-featured template for initializing new daily dictation note with YAML frontmatter and structured body sections; canonical entry point when starting fresh day's recording session. Placeholders: `{tags}`, `{date}`, `{time}`, `{title}`, `{text}`. |
| `standalone.md` | `eloquent_notes/templates/standalone.md` | Independent note documents detached from daily-entry lifecycle; suitable for ad-hoc notes, reminders, reference entries. Placeholders: `{title}`, `{text}`, `{date}`, `{time}` (optional). |

All three templates share identical interpolation pipeline: filesystem loader resolves requested template path within module's directory → content read as raw string without compilation or caching → context map built from caller-supplied values with missing keys defaulting to empty strings unless overridden by configuration → string replacement iterates all `{...}` placeholders in document order, substituting each with corresponding context value → rendered Markdown returned for downstream persistence (local disk, remote API, internal store). No runtime state, functions, classes, interfaces, or data structures are exported from any of these files; module operates entirely as a template data registry consumed by the upstream rendering layer.