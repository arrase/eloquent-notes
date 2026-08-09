# `eloquent_notes.config_gui` — Configuration GUI Subsystem Architecture

## Module Responsibility

The `config_gui` package establishes the user-facing configuration infrastructure for Eloquent Notes. It exposes two public entry points: `ConfigurationDialog`, which provides a centralized settings management window, and `OllamaModelLoader`, which asynchronously discovers Ollama-compatible LLM models with audio generation capability. The dialog aggregates six independent tab widgets—General, Obsidian, AI Settings, Audio, Prompts, Templates—each responsible for one configuration domain. Data flow proceeds from user interaction through tab UIs into an in-memory `config_data` dictionary (partitioned by key: `"ai"`, `"audio"`, `"general"`, `"obsidian"`), which is then diffed against a factory-default YAML schema and persisted to disk via `eloquent_notes.config.save_config`.

---

## External I/O & Dependencies

| Source | Interaction Type | Details |
|--------|-----------------|---------|
| `config_gui.loader` (`OllamaModelLoader`) | HTTP GET `/api/tags`, timeout=2.0s; HTTP POST `/api/show` per model, timeout=2.0s | Network calls against a local Ollama inference server. Inner-loop failures are silently swallowed; outer failures propagate via `error_occurred` signal. |
| `config_gui.dialog` (`ConfigurationDialog`) | Disk read/write on `config.DEFAULT_CONFIG_SRC` (YAML) | Default config loaded in `__init__`; user overrides diffed and written back only if all tabs validate. Errors caught by try-except emit `QMessageBox.critical`. |
| `config_gui.tabs.general` (`GeneralTab`) | `os.path.exists()`, `~/.config/autostart/eloquent-notes.desktop` creation/deletion, `QDesktopServices.openUrl()` | Autostart management and log viewer. No try-except wraps the editor open call or file existence check—failure propagates as unhandled exception. |
| `config_gui.tabs.obsidian` (`ObsidianTab`) | `os.path.expanduser()`, `os.path.abspath()`, `QFileDialog.getExistingDirectory()` | Vault path resolution and directory picker. Path normalization has no explicit error handling; errors propagate uncaught. |

---

## Constants (`eloquent_notes.config_gui.constants`)

| Name | Type | Description |
|------|------|-------------|
| `PROMPTS` | `list[tuple[str, Any, Any]]` | Prompt configuration tuples: `(label, system_prompt_path, default_source)`. Covers Transcription (System/User), Rewriting (System/User), Classification (System/User), and Retry prompts. |
| `TEMPLATES` | `list[tuple[str, Any, Any]]` | Template configuration tuples: `(label, standalone_template_path, default_source)`. Covers Standalone Note Template, Daily Note - New, Daily Note - Append. |

No external side effects. No exception handling in this file. The only import is internal (`from eloquent_notes import config`).

---

## Styles (`eloquent_notes.config_gui.styles`)

| Element | Type | Description |
|---------|------|-------------|
| `QSS_STYLESHEET` | Module-level `str` | Qt Style Sheets string defining visual appearance for the configuration dialog: base colors/fonts, tab pane and tab states (selected/hovered/active), input controls (line edits, spin boxes, combo boxes) including focus indicators, list widget hover/selection feedback, push button variants (normal, hover, pressed, "Save"), group box borders/titles, checkbox indicator size/shape/state, vertical scrollbar dimensions and handle colors. |

Static string constant only. No executable logic or error handling.

---

## Utilities (`eloquent_notes.config_gui.utils`)

### `diff_configs(default: dict, current: dict) -> dict`

Recursively diffs the `current` configuration against a known default, returning only overrides—i.e., settings that differ between factory defaults and user state. No external I/O. The function assumes dict-shaped input at all recursion levels without validation; unexpected types (non-dict values, missing `.items()` method) would propagate as uncaught exceptions.

**Algorithm:**
1. Initialize empty result dictionary.
2. Iterate every key in `current`: if absent from `default`, copy directly into result. If both values are dicts, recurse. If one value is a boolean and the other is not, treat as type-mismatch override. Otherwise, if scalar values differ, record current value.
3. Return collected overrides only.

---

## Loader (`eloquent_notes.config_gui.loader`)

### Class: `OllamaModelLoader` (inherits `QThread`)

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

---

## Base Contracts (`eloquent_notes.config_gui.tabs.base`, `eloquent_notes.config_gui.tabs.text_files`)

### Class: `ConfigTab` (abstract base)

Enforces the lifecycle contract for every configuration tab widget. Subclasses must implement at minimum:

- **`load_settings(config_data: dict) -> None`** — populate UI from caller-supplied config dictionary
- **`save_settings(config_data: dict) -> bool`** — read current UI state back into the dictionary; return `True` on success, `False` when validation fails (caller uses this to decide whether to show an error dialog)

Optional no-op implementations for:
- **`restore_defaults() -> None`**
- **`cleanup() -> None`**

No mutable instance state. No external I/O. Methods that are not overridden raise `NotImplementedError`; `restore_defaults()` and `cleanup()` silently swallow errors via bare `pass`.

### Class: `TextFilesTab(ConfigTab)` (intermediate base)

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

---

## Domain Tabs (`eloquent_notes.config_gui.tabs`)

### Class: `AITab(ConfigTab)`

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

### Class: `AudioTab(ConfigTab)`

**Responsibility:** Configure audio capture parameters before voice recording. Exposes sample rate (8–96 kHz), channel count (mono/stereo), beep-on-record toggle, and beep frequency/duration selectors.

**Data flow:**
1. `_init_ui()` creates five widgets: `QSpinBox` for sample rate with range/setSingleStep configured, `QComboBox` for channels, `QCheckBox` for beep enable, two spinboxes for beep frequency (int) and duration (double).
2. **Load** (`load_settings`): reads from `config_data.get("audio", {})`. Sample rate is parsed as int with default 16000 Hz; if parsing raises ValueError/TypeError it is caught and the spinbox reverts to 16000. Channels defaults to index 1 (mono). Beep frequency defaults to 1000 Hz, beep duration to 0.1 s—both have try/except fallbacks. The **channels** field has no explicit type guard; a non-int value propagates as an unhandled error when `setCurrentIndex` evaluates it.
3. **Save** (`save_settings`): writes current widget values back into `config_data["audio"]`. Returns `True` unconditionally—if any Qt widget access raises (e.g., `.value()` on a destroyed widget), the exception propagates to caller without being caught here.

### Class: `GeneralTab(ConfigTab)`

**Responsibility:** Configure startup/autostart behavior and logging verbosity, file size limits, backup retention count, and log viewer.

**Data flow:**
1. **Autostart management**: a QCheckBox toggles whether the app launches on login. On save: if checked → `install_autostart()` creates `~/.config/autostart/eloquent-notes.desktop`; if unchecked → `os.remove(autostart_path)` deletes it (only called when file exists).
2. **Logging level**: QComboBox with five options (DEBUG, INFO, WARNING, ERROR, CRITICAL); persisted as `logging.level`.
3. **Log file size limit**: spinbox range 1–100 MB; persisted as `logging.max_mb`.
4. **Backup retention**: spinbox range 0–10; persisted as `logging.backup_count`.
5. **View log** (`_view_log_file`): opens `<log_dir>/app.log` in the system editor via `QDesktopServices.openUrl()`. If the file does not exist, an informational message is shown instead of opening anything. No try/except wraps the open call or existence check—failure propagates as unhandled exception.
6. **Load**: reads autostart path with `os.path.exists()` to populate checkbox state; no write operation during load.

### Class: `ObsidianTab(ConfigTab)`

**Responsibility:** Configure Obsidian vault integration—vault directory, target folder name within the vault, append-to-daily-notes toggle, and vault-context wikilinks toggle.

**Data flow:**
1. `_init_ui()` builds a form with four controls: vault path line edit, browse button, folder name line edit, two checkboxes (daily notes, context).
2. **Browse** (`_browse_vault_path`): opens a directory picker via `QFileDialog.getExistingDirectory()`, pre-filled with the current vault path or user home if empty. Returns empty string on cancel—treated as "no selection" and path remains unchanged.
3. **Load**: restores all four values from `config_data["obsidian"]`. Path normalization uses `os.path.expanduser()` and `os.path.abspath()`. No exception handling visible for these calls; errors propagate uncaught.
4. **Save** (`save_settings`): writes the four values into `config_data["obsidian"]`. If vault path is empty, a warning dialog appears and returns `False`. If the directory does not exist on disk, `os.path.exists()` check triggers a confirmation dialog; user denial → return `False`, acceptance proceeds without re-checking existence. Returns `True` on successful save.

### Class: `PromptsTab(TextFilesTab)`

**Responsibility:** Provide a tab for viewing and editing editable prompts stored in an application constant list (`eloquent_notes.config_gui.constants.PROMPTS`). Delegates all text-file UI logic to the inherited `TextFilesTab`.

Constructor forwards `items=PROMPTS`, `editor_label="Prompt Content:"`, placeholder `"Select a prompt to edit..."` to `TextFilesTab.__init__()`. No additional state, no external I/O, no error handling visible in this file.

### Class: `TemplatesTab(TextFilesTab)`

**Responsibility:** Provide a tab for viewing and editing editable templates stored in an application constant list (`eloquent_notes.config_gui.constants.TEMPLATES`). Delegates all text-file UI logic to the inherited `TextFilesTab`.

Constructor forwards `items=TEMPLATES`, `editor_label="Template Content:"`, placeholder `"Select a template to edit..."` to `TextFilesTab.__init__()`. No additional state, no external I/O, no error handling visible in this file.

---

## Dialog (`eloquent_notes.config_gui.dialog`)

### Class: `ConfigurationDialog(QDialog)`

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