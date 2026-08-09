# `eloquent_notes.config_gui.tabs` — Configuration GUI Package

## Overview

The `config_gui/tabs` package provides a unified configuration dialog composed of independent tab widgets, each responsible for one settings domain: AI/Ollama, audio capture, general startup/logging, Obsidian integration, and editable text collections (prompts, templates). All tabs inherit from `ConfigTab`, which enforces the lifecycle contract (`load_settings`, `save_settings`, `restore_defaults`, `cleanup`). The package exposes each tab class via `__all__` so downstream code imports them as `eloquent_notes.config_gui.tabs.AITab`, etc.

---

## Base Contracts

### `base.py::ConfigTab`

Abstract base for every configuration tab widget. Subclasses must implement:

- `load_settings(config_data: dict) -> None` — populate UI from caller-supplied config dictionary
- `save_settings(config_data: dict) -> bool` — read current UI state back into the dictionary; return `True` on success, `False` when validation fails (caller uses this to decide whether to show an error dialog)

Optional no-op implementations for:

- `restore_defaults() -> None`
- `cleanup() -> None`

No mutable instance state. No external I/O. Methods that are not overridden raise `NotImplementedError`; `restore_defaults()` and `cleanup()` silently swallow errors via bare `pass`.

### `text_files.py::TextFilesTab(ConfigTab)`

Intermediate base for tabs that manage a list of editable text files (prompts, templates). Constructor signature: `__init__(self, items, editor_label, placeholder, parent=None)`, where `items` is an iterable of `(label, path, default_path)` tuples.

State and lifecycle:

- **Mutable instance state**: `_block_cache` (bool toggle used to block cache writes during load/restore), `loaded_contents` (dict mapping file paths to cached strings), `current_item` (the currently selected list widget item).
- **Selection change handler** (`_on_item_changed`): on every list selection, the previous active editor's contents are written into `loaded_contents` before switching focus. The new item's content is read from disk via an external `config.load_file(path)` call; if no file exists at either path or default_path, empty string is cached.
- **Commit** (`commit_active_editor()`): flushes the current item's in-memory text into `loaded_contents` so it survives a subsequent switch.
- **Persist** (`save_settings`): writes every entry of `loaded_contents` back to disk via `config.save_file(path, content)`. Returns hardcoded `True` regardless of write outcome — no per-file error detection is visible here; failures propagate as uncaught exceptions from the underlying config module.
- **Load/restore**: reads each path that exists and populates cache; missing paths default to empty string.

No synchronization primitives are present. File I/O errors (permission denied, disk full, etc.) are not wrapped — they crash at call site.

---

## Domain Tabs

### `ai.py::AITab(ConfigTab)`

**Responsibility**: Configure the Ollama LLM pipeline for local dictation-to-note tasks. Manages connection URL, available model list, context window size, keep-alive durations, max retries on JSON parse failures, and output language selection.

**Data flow**:
1. `_init_ui()` builds a form with: Ollama URL text field (`txt_ollama_url`), editable model combo box, context length spinbox + "use default" toggle, keep-alive time fields, max retries spinbox (0–10), preload/request timeout spinboxes, output language dropdown.
2. `_fetch_models()` constructs a fresh `OllamaModelLoader` from `eloquent_notes.config_gui.loader`, calls `.start()`, and begins tracking it in `self._running_loaders`. The loader communicates completion via three signal handlers:
   - **`finished`** → `_on_loader_finished`: discards the completed loader from `_running_loaders`, clears `self._model_loader`, re-enables refresh button.
   - **`models_fetched(models)`** → `_on_models_fetched`: populates combo box; if a previously selected model is no longer in the fetched list, it is added back and re-selected. Status label set to green text `"Audio models loaded successfully."`.
   - **`error_occurred(error_msg)`** → `_on_models_fetch_failed`: status label becomes red with `f"Connection failed: {error_msg}"`.

All three handlers are guarded by `if self.sender() is not self._model_loader: return` to prevent queued signals from stale loaders executing on new state.

3. **Cleanup**: `cleanup()` calls `.wait(2500)` on each loader in `_running_loaders`; if a loader hangs beyond the timeout, it returns silently — no explicit exception handling is visible.
4. **Load persisted settings** (`load_settings`): restores all widget values from `config_data["ai"]`. Defaults include Ollama URL `http://localhost:11434`, model `gemma4:12b-it-qat`, context length 10000.
5. **Save** (`save_settings`): collects widget state into `config_data["ai"]`. Validation rejects empty Ollama URL (shows QMessageBox warning) and keep-alive durations that don't match the regex `^-?\d+[smh]?$`; each invalid field triggers its own QMessageBox. Returns `False` on any validation failure, `True` otherwise.

Mutable state: `self._model_loader` (OllamaModelLoader instance or None), `self._running_loaders` (set of loaders in progress). No synchronization mechanism protects these across signal-driven threads. The retry count (`spn_max_retries`) is persisted but the actual retry logic lives downstream; this tab only stores the value.

### `audio.py::AudioTab(ConfigTab)`

**Responsibility**: Configure audio capture parameters before voice recording. Exposes sample rate (8–96 kHz), channel count (mono/stereo), beep-on-record toggle, and beep frequency/duration selectors.

**Data flow**:
1. `_init_ui()` creates five widgets: `QSpinBox` for sample rate with range/setSingleStep configured, `QComboBox` for channels, `QCheckBox` for beep enable, two spinboxes for beep frequency (int) and duration (double).
2. **Load** (`load_settings`): reads from `config_data.get("audio", {})`. Sample rate is parsed as int with default 16000 Hz; if parsing raises ValueError/TypeError it is caught and the spinbox reverts to 16000. Channels defaults to index 1 (mono). Beep frequency defaults to 1000 Hz, beep duration to 0.1 s — both have try/except fallbacks. The **channels** field has no explicit type guard; a non-int value propagates as an unhandled error when `setCurrentIndex` evaluates it.
3. **Save** (`save_settings`): writes current widget values back into `config_data["audio"]`. Returns `True` unconditionally — if any Qt widget access raises (e.g., `.value()` on a destroyed widget), the exception propagates to caller without being caught here.

Mutable state: five widgets (`spn_sample_rate`, `cmb_channels`, `chk_beep_enabled`, `spn_beep_freq`, `spn_beep_duration`) store user-facing configuration values that survive across calls. No synchronization primitives are present.

### `general.py::GeneralTab(ConfigTab)`

**Responsibility**: Configure startup/autostart behavior and logging verbosity, file size limits, backup retention count, and log viewer.

**Data flow**:
1. **Autostart management**: a QCheckBox toggles whether the app launches on login. On save: if checked → `install_autostart()` creates `~/.config/autostart/eloquent-notes.desktop`; if unchecked → `os.remove(autostart_path)` deletes it (only called when file exists).
2. **Logging level**: QComboBox with five options (DEBUG, INFO, WARNING, ERROR, CRITICAL); persisted as `logging.level`.
3. **Log file size limit**: spinbox range 1–100 MB; persisted as `logging.max_mb`.
4. **Backup retention**: spinbox range 0–10; persisted as `logging.backup_count`.
5. **View log** (`_view_log_file`): opens `<log_dir>/app.log` in the system editor via `QDesktopServices.openUrl()`. If the file does not exist, an informational message is shown instead of opening anything. No try/except wraps the open call or existence check — failure propagates as unhandled exception.
6. **Load**: reads autostart path with `os.path.exists()` to populate checkbox state; no write operation during load.

Mutable state: four widgets (`chk_autostart`, `cmb_log_level`, `spn_log_max_mb`, `spn_log_backups`) store user-facing values and are updated via Qt signals. No synchronization primitives.

### `obsidian.py::ObsidianTab(ConfigTab)`

**Responsibility**: Configure Obsidian vault integration — vault directory, target folder name within the vault, append-to-daily-notes toggle, and vault-context wikilinks toggle.

**Data flow**:
1. `_init_ui()` builds a form with four controls: vault path line edit, browse button, folder name line edit, two checkboxes (daily notes, context).
2. **Browse** (`_browse_vault_path`): opens a directory picker via `QFileDialog.getExistingDirectory()`, pre-filled with the current vault path or user home if empty. Returns empty string on cancel — treated as "no selection" and path remains unchanged.
3. **Load**: restores all four values from `config_data["obsidian"]`. Path normalization uses `os.path.expanduser()` and `os.path.abspath()`. No exception handling is visible for these calls; errors propagate uncaught.
4. **Save** (`save_settings`): writes the four values into `config_data["obsidian"]`. If vault path is empty, a warning dialog appears and returns `False`. If the directory does not exist on disk, `os.path.exists()` check triggers a confirmation dialog; user denial → return `False`, acceptance proceeds without re-checking existence. Returns `True` on successful save.

Mutable state: five widgets (`txt_vault_path`, `btn_browse_vault`, `txt_obs_folder`, `chk_daily_notes`, `chk_vault_context`) store user-facing values and are updated via Qt signals. No synchronization primitives present. All external I/O is confined to the local filesystem — no network, database, or API interactions.

### `prompts.py::PromptsTab(TextFilesTab)`

**Responsibility**: Provide a tab for viewing and editing editable prompts stored in an application constant list (`eloquent_notes.config_gui.constants.PROMPTS`). Delegates all text-file UI logic to the inherited `TextFilesTab`.

Constructor forwards `items=PROMPTS`, `editor_label="Prompt Content:"`, placeholder `"Select a prompt to edit..."` to `TextFilesTab.__init__()`. No additional state, no external I/O, no error handling visible in this file.

### `templates.py::TemplatesTab(TextFilesTab)`

**Responsibility**: Provide a tab for viewing and editing editable templates stored in an application constant list (`eloquent_notes.config_gui.constants.TEMPLATES`). Delegates all text-file UI logic to the inherited `TextFilesTab`.

Constructor forwards `items=TEMPLATES`, `editor_label="Template Content:"`, placeholder `"Select a template to edit..."` to `TextFilesTab.__init__()`. No additional state, no external I/O, no error handling visible in this file.