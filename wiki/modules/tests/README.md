# Eloquent Notes — Architecture Documentation

## Application Layer (`eloquent_notes.app`)

### `EloquentApp`

**Responsibility:** Maintains discrete application states (IDLE → STARTING_RECORDING → RECORDING → PROCESSING), orchestrates the audio capture and processing pipeline, manages IPC connections for remote daemon control, handles shutdown sequences, and coordinates system-tray notifications.

**State Machine Transitions:**
- `toggle_action()` — triggers state transitions between IDLE/RECORDING/PROCESSING; dispatches to `_notify`, `_update_icon` for UI feedback
- `reload_config()` — re-loads configuration (state reset implied)
- `exit_app()` — stops active recording if any, closes IPC server, quits underlying QApplication; if no system tray exists, only quits the app

**Signals:**
- `processing_completed(status, detail)` — emitted when audio processing completes successfully or fails. Connected to `_on_processing_completed` callback.

**IPC Protocol Handling:** Listens on a TCP socket for incoming commands from remote clients. Each connection reads bytes, dispatches the corresponding action (toggle, reload), disconnects, and cleans up the client socket. Multiple simultaneous connections are handled independently per-socket.

**Shutdown Sequence:** On exit, regardless of current state: stop recording if active, close the IPC server, quit the underlying application; if no system tray exists, only quit the app. Config dialog closure also triggers cleanup via `deleteLater`.

## Audio System (`eloquent_notes.audio`)

### `AudioRecorder`

**Responsibility:** Captures live microphone input via streaming callbacks, converts captured float32 samples into WAV file bytes, and plays synthesized tones.

**Internal State:**
- `_stream`: Active `sounddevice.InputStream` instance (set by `start()`, cleared by `stop()`/`wav_bytes`)
- `_wav_bytes`: Cached WAV output; reset to `None` on re-start
- `q`: Internal audio data queue (`queue.Queue`)

**Lifecycle:**
1. `__init__(sample_rate, channels)` — initializes with sample rate and channel count; sets `_stream = None`, `_wav_bytes = None`
2. `.start()` — opens a `sounddevice.InputStream`; assigns to `.stream`. If called while existing stream is active, stops and closes previous stream first; resets `_wav_bytes` to `None`. Raises `RuntimeError` on failure (e.g., "Device unavailable").
3. `.callback(chunk, num_channels, indev=None, outdev=None)` — pushes chunk into internal queue `q`
4. `.stop()` — stops the current stream via `.stop()`, then calls `.close()`. Sets `.stream = None`. Raises any exception from stop/close; cleanup runs before propagation so resources are released even on error.
5. `.wav_bytes` (property) — generates WAV file bytes from queued audio data using `wave` module and `io.BytesIO`; returns cached value on subsequent access. If queue is empty, produces valid WAV header with 0 frames. Calls `.stop()` and `.close()` on stream before generation.

### `play_beep(frequency, duration, sample_rate)`

**Responsibility:** Synthesizes a sine wave tone and plays it via sound device. Returns `None` on success. No action taken when `duration == 0`. Uses `sounddevice.play()` and `sounddevice.wait()`.

## Configuration System (`eloquent_notes.config`)

### Functions

**`init_config_dir()`** — Creates directories for config, prompts, and templates; copies default files into them. Does not overwrite existing destination files.

**`load_config()`** — Loads user configuration from `CONFIG_PATH`, recursively merges it with the default config source (`DEFAULT_CONFIG_SRC`), returns a unified dictionary. Raises `ValueError` if user config is not a valid YAML mapping (message: "is not a valid YAML mapping").

**`save_file(path, content)`** — Writes *content* to *path*. If path has no directory component (flat), saves relative to current working directory.

**`load_file(path)`** — Reads and returns contents of a text file at *path*.

**`save_config(data)`** — Serializes *data* as YAML and writes it to `CONFIG_PATH`.

### Module Attributes

| Attribute | Description |
|---|---|
| `CONFIG_DIR` | Absolute path of the config directory |
| `PROMPTS_DIR` | Absolute path of the prompts subdirectory within the config directory |
| `TEMPLATES_DIR` | Absolute path of the templates subdirectory within the config directory |
| `CONFIG_PATH` | Absolute path to the user configuration file (e.g., `config.yaml`) |
| `DEFAULT_CONFIG_SRC` | Absolute path to the default/seed configuration source file |

### Data Flow: Configuration Initialization and Loading

1. **Initialize** — Create three folders (`config/`, `prompts/`, `templates/`) and copy default source files (base YAML config, system prompt template) into target paths on first run. If destination exists, leave untouched.
2. **Load Default Config** — Read a default YAML file to form baseline config.
3. **Load User Config** — Read user's own YAML file if present; validate as valid YAML mapping; raise `ValueError` otherwise.
4. **Merge** — Recursively merge two nested dictionaries (walk both in parallel, replace base value with override where keys match at any depth). Never mutate inputs.
5. **Persist** — Write merged config back to user's config path as formatted YAML.

## Configuration GUI (`eloquent_notes.config_gui`)

### `ConfigurationDialog`

**Responsibility:** Central preferences/settings interface for configuring multiple subsystems: general app behavior, Obsidian integration (vault path), AI settings (Ollama URL, model, timeouts, retries), audio output (sample rate, beep alerts), logging levels.

**Internal Widget References (not public API):**
- `ai_tab.txt_ollama_url` — QLineEdit for Ollama server URL
- `ai_tab.cmb_model` — QComboBox for model selection
- `ai_tab.cmb_language` — QComboBox for language
- `audio_tab.spn_sample_rate` — QSpinBox for sample rate
- `general_tab.cmb_log_level` — QComboBox for log level
- `obsidian_tab.txt_vault_path` — QLineEdit for vault path

**Methods:**
- `cleanup_tabs()` — Cleans up tabs during close/accept/reject; called exactly once regardless of success or failure on reject, accept, or QCloseEvent
- `save_settings_from_ui()` — Saves settings from current widget values into config dictionary; validates required fields (e.g., Ollama URL not empty); returns `True` on success, `False` on validation failure. Validation failure triggers warning dialog then question dialog for abort confirmation.
- `restore_defaults()` — When user clicks "Reset to Default," prompts for confirmation via QMessageBox; if accepted, loads factory defaults and applies across all tabs. If declined, leaves settings untouched.

**Close Behavior:** Calls cleanup routine that resets internal state and closes child widgets on close/accept/reject/QCloseEvent.

### `OllamaModelLoader` (`eloquent_notes.config_gui.loader`)

**Responsibility:** Loads and manages LLM models from an Ollama-compatible local server API. Enumerates available models, fetches capabilities per model, handles failures/resilience gracefully.

**Constructor:** `OllamaModelLoader(url)` — base URL for the Ollama server (e.g., `http://localhost:11434`).

**Signals:**
- `models_fetched` (`Signal`) — emitted when model fetch completes successfully; payload is a list of model names
- `error_occurred` (`Signal`) — emitted when an error occurs during loading

**Methods/Properties:**
- `run()` — executes the background loader worker thread
- `isInterruptionRequested` (property) — returns `bool`; indicates whether user has requested cancellation

**Algorithm Steps:**
1. **Interruption Check at Start** — Immediately abort if a cancellation signal is active before any network calls are made
2. **Query Model List** — Send GET request to retrieve all available models from server
3. **Iterate Over Each Model:**
   - Fetch capabilities via POST request for model details (e.g., audio support, completion)
   - Skip on failure: network exception → skip; malformed JSON response → skip; invalid JSON structure → skip
4. **Collect Results** — Only models completing capability fetch successfully are added to output list
5. **Signal Errors or Interruptions** — Connection-level failures (e.g., server unreachable) or interruption mid-process reported via error signal

**Error Handling:** GET request failure propagates via `error_occurred` signal. POST timeout/swallowed malformed responses allow batch processing of subsequent models; only hard catalog fetch failures surface externally. Invalid JSON from `.json()` parsing (non-dict response) is swallowed internally, proceeding to next model.

### Configuration Tabs (`eloquent_notes.config_gui.tabs`)

**Responsibility:** Multiple independent configuration tabs (AI, Audio, General, Obsidian, Text Files, Prompts, Templates), each providing UI controls and persistence logic. Load/save cycle reads from/writes to a shared `config_data` dictionary with graceful handling of missing/invalid values through fallback defaults.

**Algorithm Steps:**
1. **Tab Instantiation** — Each tab created as independent widget instance per test
2. **Settings Loading (`load_settings`)** — Populate UI widgets from config dictionary; missing or unparseable values fall back to built-in default constants (e.g., sample rate 16000, max retries 3, context length 10000)
3. **Settings Saving (`save_settings`)** — Write current widget state back into config dictionary; returns boolean success indicator. Validation failures cause abort with warning dialog
4. **Obsidian Vault Browsing** — When saving with no valid vault path, invoke directory picker for user selection
5. **Text File Editing Flow** — For TextFilesTab, prompts stored as individual files on disk; selecting a row loads content into editor widget; committing writes modified text back to same file
6. **None-config Tolerance** — Tabs accept `config_data` where section key is absent or explicitly `None`, returning success without error
7. **Autostart Installation** — General tab conditionally triggers system-level autostart registration when user enables it during save

### Configuration Diff (`eloquent_notes.config_gui.utils`)

**Responsibility:** Compares default configuration against user-modified configuration, returns only keys whose values differ — effectively computing a config diff as dictionary of changed paths mapped to their new values.

**Algorithm Steps:**
1. Accept two dictionaries (`default`, `current`) representing same hierarchical config structure
2. Recursively traverse both structures key-by-key: if key exists in both and values equal, skip; if only one side has key, include with value from whichever side has it
3. For nested dictionaries, recurse into them; return inner dict of differences when they diverge (e.g., `{"ai": {"model": "whisper"}}`)
4. For lists, compare element-by-element; if identical, skip; otherwise include entire current list as changed value
5. Handle scalar types directly — booleans and integers compared as-is (`0` vs `False`, `1` vs `True` treated as distinct)
6. Return empty dict `{}` when no differences found across any nesting level

## LLM Integration (`eloquent_notes.llm`)

### Functions

**`preload_model(ollama_url, model, context_length)`** — Model warmup/provisioning call with empty message list, 5m keep-alive, temperature=0.0, num_ctx configurable via `/api/chat`.

**`transcribe_audio(ollama_url, model, system_prompt, user_prompt, retry_prompt, context_length, audio_bytes)`** — Converts raw audio bytes into text transcription via LLM using system + user prompts; returns dict.

**`rewrite_transcription(ollama_url, model, system_prompt, user_prompt, retry_prompt, context_length)`** — Rewrites transcription output into structured format (title + content fields); returns dict.

**`classify_transcription(ollama_url, model, system_prompt, user_prompt, retry_prompt, context_length)`** — Classifies rewritten transcription by assigning type label, wikilinks, and tags; produces final categorized result object; returns dict.

### Internal Functions (inferred from tests)

**`_execute_ollama_json_request(...)`** — JSON-RPC style chat completion request carrying user/system prompts and `format_schema` for structured output. Re-invokes `requests.post` when parsing fails or required keys are absent. Exposes retry with prompt correction: up to configurable maximum retries; if exhausted, raises `ValueError` with message "missing required keys". HTTP-level errors (4xx/5xx) appear unhandled—no recovery path tested.

**`_strip_code_fences(...)`** — Strips markdown code fences from raw LLM text responses before parsing as JSON, supporting fenced blocks with or without language declarations, inline fences, and surrounding prose.

### External System: Local Ollama API (HTTP POST)

| Function | Endpoint | Purpose |
|---|---|---|
| `preload_model` | `/api/chat` | Model warmup/provisioning |
| `_execute_ollama_json_request` | `/api/chat` (inferred) | JSON-RPC style chat completion with structured output schema |

All calls use `requests.post`. All interactions mocked via `@patch("eloquent_notes.llm.requests.post")`.

## Logging (`eloquent_notes.logging_utils`)

### Functions

**`get_log_dir()`** — Returns platform-specific log directory path for eloquent-notes, respecting `XDG_STATE_HOME` environment variable when set; otherwise falls back to `~/.local/state/eloquent-notes`.

**`setup_logging(level, max_mb, backup_count)`** — Configures logging by attaching both a console stream handler and a rotating file handler. Returns the logger instance (same one passed through internally).

### Data Flow: Logging Setup

1. **Resolve Log Directory** — Read `XDG_STATE_HOME`; if absent, fall back to default location under user's local state directory
2. **Configure Logging Level** — Accept severity string (e.g., `"DEBUG"`, `"WARNING"`), set on application logger
3. **Attach Console Handler** — Add `StreamHandler` for real-time stdout/stderr output
4. **Attach Rotating File Handler** — Add `RotatingFileHandler` writing to resolved directory, with configurable max file size (`max_mb`) and number of backups kept (`backup_count`)

### Error Handling: Internal Swallowing Pattern

If log directory resolution fails (e.g., permission denied), report error to stderr but still return the configured logger so callers continue operating. `setup_logging` catches errors during file handler initialization, logs them to stderr ("Could not initialize file logging"), returns logger object unchanged rather than propagating as exception or raising. Console handler continues operating unaffected.

## Autostart (`eloquent_notes.autostart`)

### Functions

**`install_autostart()`** — Creates a desktop entry for autostart, returning the path of the created `.desktop` file. When no executable found in PATH, uses `"eloquent-notes"`; when found, uses its absolute path.

**Algorithm Steps:**
1. Locate executable (`eloquent-notes`) using `shutil.which` to check if absolute path available
2. Construct `.desktop` file at `~/.config/autostart/eloquent-notes.desktop` (using `os.path.expanduser`)
3. Write `[Desktop Entry]` header, `Name=Eloquent Notes`, and an `Exec=` line — either resolved absolute path or bare command name depending on step 1
4. Set file permissions to `0o644`

### External Interactions:
- **Filesystem Writes**: Creates `.desktop` file in user's autostart directory (e.g., `~/.config/autostart/eloquent-notes.desktop`)
- **PATH Lookup**: Calls `shutil.which("eloquent-notes")` to check if executable exists in system PATH; monkeypatched away in both tests

## Main/CLI Entry Point (`eloquent_notes.main`)

### Functions

**`parse_args(args: list[str]) -> object`** — Parses CLI arguments. Returns object with `.command` (str | None) and `.toggle` (bool). Recognizes commands (`install-autostart`, `toggle`, `-t`, `config`).

**`send_ipc_command(command, timeout_ms=300) -> bool`** — Sends IPC command over local Unix socket (`eloquent_notes_ipc`). Returns True on success, False on failure. Raises RuntimeError if write fails (disconnect is called before raise).

**`run_cli(argv: list[str], sys_exit=None, launcher=None)`** — Dispatches CLI commands (`install-autostart`, `toggle`, `config`). Calls `sys.exit` with code 0 on accepted config or toggle; calls `launcher` only when daemon must be started.

**`main()`** — Entry point. Delegates to `run_cli`.

### Algorithm Steps:
1. **Parse CLI arguments** — recognize commands (`install-autostart`, `toggle`, `-t`, `config`) and boolean flags
2. **Send IPC to daemon** — connect via local Unix socket, write command bytes, wait for write completion with timeout, disconnect; return success/failure
3. **Toggle daemon state** — first attempt IPC toggle; if returns true (already running), notify it and exit 0; if false or fails, spawn new daemon process via `python -m eloquent_notes.app`
4. **Install autostart** — delegate to `install_autostart()`, exit 0 on success
5. **Open config dialog** — initialize configuration directory, show GUI dialog (`ConfigurationDialog`), send IPC "reload" if user accepts, exit 0 otherwise

### External Interactions:
| Interaction | Mechanism | Details |
|---|---|---|
| Local IPC communication | Unix socket (`QLocalSocket`) | Connects to server `eloquent_notes_ipc`, writes command bytes, waits for write completion with timeout, disconnects. Used for daemon control (toggle/reload). |
| Subprocess execution | Python launcher subprocess | When IPC toggle fails, subprocess spawned using `sys.executable` running `-m eloquent_notes.app`. Arguments include CLI subcommand. |
| GUI dialog interaction | Qt Widgets (`ConfigurationDialog`) | Modal dialog instantiated and `.exec()` called to prompt user input for configuration. |

### Error Handling: Disconnect on Any Failure Pattern

When `write()` raises an exception (e.g., `RuntimeError`), `disconnectFromServer()` is called as teardown before exception propagates to caller. Daemon connection cleaned up even on error.

## Obsidian Module (`eloquent_notes.obsidian`)

### Responsibility

Implements a personal knowledge vault manager modeled after Obsidian's workflow. Three core operations are exposed: **vault topic discovery** (recursive directory traversal with hidden-path filtering), **wikilink injection** (case-insensitive first-occurrence matching against protected-element skipping rules), and **structured note generation/persistence** (daily dictation, standalone ideas, task callouts) using templates while preserving existing frontmatter tags.

### Data Flow

```
vault_path → scan_vault_topics() → list[str]  (topic basenames)
text + wikilinks → _inject_wikilinks() → str   (with [[link]] syntax)
content + tags → _update_frontmatter_tags() → str (YAML frontmatter merge, or passthrough)
note_type + content + tags → format_note_content() → str  (callout wrapping or plain)
vault_path + folder + daily_notes + title + text + tags + templates → save_note() → path | None
```

### Public API Surface

| Function | Signature | Returns |
|---|---|---|
| `scan_vault_topics(vault_path: str, max_topics: int \| None)` | `list[str]` | Topic basenames up to `max_topics`; empty list if vault path missing or invalid. |
| `_inject_wikilinks(text: str, wikilinks: list[str])` | `str` | Input text with `[[wikilink]]` appended at first occurrence per link name (case-insensitive). Skips code blocks, fenced regions, markdown links `[text](url)`, and backtick-wrapped identifiers. |
| `_update_frontmatter_tags(content: str, tags: list[str])` | `str` | Content with merged YAML frontmatter `tags`. Returns original unchanged if YAML is unparseable or parsed structure is not a dict. |
| `format_note_content(note_type: str, content: str \| None, tags: list[str] \| None)` | `str` | Wraps lines in callout syntax for `"task"` (`> [!todo]`) and `"idea"`. For other types, injects `[[tag]]` wikilinks into plain text. Empty input yields empty string. |
| `save_note(vault_path: str, folder: str, daily_notes: bool, title: str, text: str, tags: list[str], template_standalone: str, template_daily_new: str, template_daily_append: str)` | `str \| None` | File path for the saved note. Returns `None` if save fails. Daily notes use either `template_daily_new` (first entry) or `template_daily_append` (subsequent). Standalone uses `template_standalone`. |

### Vault Topic Discovery Algorithm

1. Walk directory tree recursively from `vault_path`.
2. Skip any path containing `.git`, `.obsidian`, `.trash`.
3. For each `.md` file, extract basename as topic name.
4. Yield up to `max_topics` results; return empty list if no files found or path invalid.

### Wikilink Injection Algorithm

1. Iterate over characters of input text.
2. When a candidate wikilink match is encountered, check whether the same link already appears in output at that position — skip on duplicate.
3. Skip injection inside backtick-delimited regions (code blocks).
4. Skip injection inside `[text](url)` markdown link syntax.
5. Append `[[link]]` form and advance past the match.

### Frontmatter Tag Management Algorithm

1. Split content at frontmatter markers to isolate YAML header from body.
2. Parse YAML only if it parses cleanly into a dict; otherwise return input unchanged.
3. Merge new tags with existing ones, preserving original order of existing entries.
4. Do not mutate any global YAML dumper state during processing.

### Note Saving Algorithm

1. Select template: `template_standalone` (non-daily), `template_daily_new` (first daily entry), or `template_daily_append` (subsequent).
2. Substitute `{title}`, `{text}`, and `{tags}` placeholders in chosen template.
3. If target path already exists, append rather than overwrite — return same path for both writes.
4. Route daily-notes and standalone saves to separate file paths to avoid collisions.

### Error Propagation Pattern

Errors are propagated by **returning the original input unchanged** instead of raising exceptions:

| Scenario | Behavior |
|---|---|
| Invalid YAML frontmatter | Returns `invalid_content` unchanged — no exception raised. |
| Non-dict YAML frontmatter | Returns `non_dict_content` unchanged — no exception raised. |
| Empty content for `format_note_content` | Returns empty string, no error path exercised in tests. |

### State and Concurrency

No mutable state is observed between calls. All functions are deterministic given identical inputs. No shared resources or global variables detected.

## UI Module (`eloquent_notes.ui`)

### Responsibility

Generates application visual icons programmatically from a named color parameter, validates the output for substantive content (non-transparent pixels), and converts the resulting PIL Image into a platform-independent Qt `QIcon` wrapper for use in GUI widgets.

### Data Flow

```
color → create_icon_image() → PIL.Image.Image (64×64 RGBA)
PIL.Image.Image + color → get_qicon() → PyQt6.QtGui.QIcon (non-null instance)
```

### Public API Surface

| Function | Signature | Returns |
|---|---|---|
| `create_icon_image(color: str)` | `PIL.Image.Image` | Image with size `(64, 64)` and mode `"RGBA"`. Populated according to color parameter. |
| `get_qicon(color: str)` | `PyQt6.QtGui.QIcon` | Non-null `QIcon` wrapping the rendered icon from `create_icon_image()`. |

### Icon Generation Algorithm

1. Accept a named color string (e.g., `"red"`, `"orange"`, `"gray"`).
2. Generate an RGBA image at 64×64 resolution with transparent channel populated per specified color.
3. Validate that the generated image contains non-transparent pixels — ensures visual substance rather than blank canvas.
4. Convert PIL Image into Qt `QIcon` for widget toolkit integration without loss of fidelity.
5. Reject unsupported color values gracefully — returns valid image structure (likely default/transparent fallback), maintaining API stability.

### State and Concurrency

PIL Image objects returned by `create_icon_image()` are created fresh per invocation and not shared across tests or threads. The Qt `QCoreApplication` / `QApplication` singleton maintains internal mutable state (registered widgets, pending events, style sheets) — instantiated via fixture calling `QApplication.instance()` (or `QCoreApplication.instance()`) and creating a new application if none exists via `QApplication(sys.argv)`.

### External I/O Analysis

**No external side effects.** All operations are in-memory:

- **PIL Image creation**: Returned by `create_icon_image(color)` is constructed in memory — not loaded from disk, not saved to storage. Tests assert dimensions and mode but do not write the image.
- **Qt QIcon conversion**: Wraps existing in-memory PIL Image into a Qt `QIcon`. No file I/O involved.
- **No network calls**, no database queries, no filesystem reads/writes, no API requests.

### Error Propagation Analysis

Error handling relies solely on `pytest` assertion-based checking. No explicit exception handling or error swallowing exists in this module:

- **Assertion failures**: Tests use standard `assert` statements (`isinstance`, equality checks, `isNull()`). If any precondition fails (wrong image size, invalid color passed to `create_icon_image`, `get_qicon` returning null), a `pytest.fail` exception is raised directly.
- **Qt application objects**: Do not raise exceptions on creation under normal conditions; initialization errors propagate as unhandled exceptions to the test runner.
- **No explicit error return codes**, no custom exception classes, and no `finally` blocks for cleanup.

**Summary**: Errors propagate via standard Python exceptions (from failed assertions or Qt object creation). No buffering, logging, or fallback paths exist — failures crash the test immediately unless caught by a parent test runner or `pytest`.