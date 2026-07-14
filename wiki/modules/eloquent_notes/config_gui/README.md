# `eloquent_notes.config_gui` — Configuration GUI Subsystem Architecture

## Module Responsibility & Data Flow

The `config_gui` subsystem provides a tabbed graphical configuration interface for **Eloquent Notes**, centralizing all user-facing settings management into a single dialog window (`ConfigurationDialog`). Settings are persisted to a YAML configuration file on disk. The subsystem is organized around an abstract contract (`ConfigTab`) that every category-specific tab class implements, ensuring uniform lifecycle behavior across AI model pipeline, audio capture, general/logging, Obsidian integration, prompts, and templates domains.

**Data flow:**
```
config_data dict (caller-owned)  ←→  ConfigTab subclasses (instance-scoped UI)  ←→  disk (YAML config / text files)
```
`ConfigurationDialog.__init__` loads the runtime configuration via `eloquent_notes.config.load_config()` into an in-memory dictionary. Each tab's `load_settings()` reads from this shared dict; `save_settings()` writes back into it. The dialog aggregates results across all tabs and persists only differences (via `diff_configs`) to disk on accept.

**Public API surface** — exported classes:
| Name | Source Module | Role |
|------|---------------|------|
| `ConfigurationDialog` | `eloquent_notes.config_gui.dialog` | Top-level settings dialog; orchestrates tab lifecycle and persistence |
| `OllamaModelLoader` | `eloquent_notes.config_gui.loader` | Background worker thread that queries Ollama `/api/tags` + `/api/show` to discover audio-capable models |

---

## Styles & Constants

### `styles.py` — Visual Theming

Defines Qt Style Sheets (QSS) for all widget types used in the configuration dialog: `QDialog`, `QWidget`, `QTabWidget::pane`, `QTabBar::tab`, `QPushButton`, `QCheckBox`, `QListWidget`, `QComboBox`, scrollbars, etc. Static string constant `QSS_STYLESHEET` covers base colors, fonts, borders, padding, interactive states (hover/pressed/selected), and scrollbar dimensions. No executable logic; no external I/O.

### `constants.py` — Static Reference Data

Module-level constants consumed by tabs that manage editable text files:

| Constant | Type | Contents |
|----------|------|----------|
| `PROMPTS` | `list[tuple[str, Any]]` | Tuples of `(label, system_prompt_path, default_source)` for Transcription/System, Transcription/User, Rewriting/System, Rewriting/User, Classification/System, Classification/User, and Retry prompts. |
| `TEMPLATES` | `list[tuple[str, Any]]` | Tuples of `(label, path, default_source)` for Standalone Note Template, Daily Note - New, Daily Note - Append. |

No external I/O or error handling in this file.

---

## Utility Module

### `utils.py` — `diff_configs(default, current) -> dict`

Recursively computes the set of overrides needed to transform a baseline configuration into the active configuration. Walks every key in `current`; if absent from `default`, records as new; if both values are dicts, recurses; otherwise records leaf-level differences. Empty sub-diffs are pruned before merging upward. Returns an empty dict when no differences exist. No error handling — uncaught exceptions propagate to the caller.

---

## Base Class Contract

### `ConfigTab` — `eloquent_notes.config_gui.tabs.base`

Abstract base defining the lifecycle contract for every category-specific tab:

| Method | Signature | Contract |
|--------|-----------|----------|
| `load_settings(config_data: dict) -> None` | **abstract**. Subclasses must populate UI controls from `config_data`. No return value. |
| `save_settings(config_data: dict) -> bool` | **abstract**. Write current widget state back into `config_data`. Returns `True` on valid, `False` to signal invalidity (caller surfaces a dialog). |
| `restore_defaults() -> None` | Default body is `pass`. Optional override for custom default restoration. |
| `cleanup() -> None` | Default body is `pass`. Override for tabs with background resources (e.g., model loaders). |

No mutable instance state; pure interface definition.

---

## Text Files Tab Hierarchy

### `TextFilesTab` — `eloquent_notes.config_gui.tabs.text_files`

Generic tab for displaying a list of independent text files, allowing per-item selection and in-memory editing via a monospace editor (`QTextEdit`). UI is built as a vertical splitter: left pane lists file entries (`QListWidget`), right pane hosts the editable editor.

**State:**
| Variable | Type | Mutated In | Notes |
|---|------|------------|------|
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

### `PromptsTab` — `eloquent_notes.config_gui.tabs.prompts`

Extends `TextFilesTab`; differs only in constructor parameters:
- `items=PROMPTS` (imported from constants module)
- `editor_label="Prompt Content:"`
- `placeholder="Select a prompt to edit..."`

### `TemplatesTab` — `eloquent_notes.config_gui.tabs.templates`

Extends `TextFilesTab`; differs only in constructor parameters:
- `items=TEMPLATES` (imported from constants module)
- `editor_label="Template Content:"`
- `placeholder="Select a template to edit..."`

---

## AI Configuration Tab

### `AITab` — `eloquent_notes.config_gui.tabs.ai`

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
|---|------|-------------|------|
| `self._model_loader` | OllamaModelLoader / None | `_fetch_models`, cleared in `_on_loader_finished` and `cleanup` | Set in constructor, reassigned on fetch, cleared on completion or cleanup. No synchronization. |
| `self._running_loaders` | set of loaders | Added via `.add()` in `_fetch_models`; removed via `.discard()` or `.clear()` in `_on_loader_finished`/`cleanup`. No sync. | Tracks active background loaders for cancellation and lifecycle management. |

**External I/O:** Network — Ollama model list fetch via `OllamaModelLoader(url)`, outbound HTTP over TCP to the configured URL; errors surface through `loader.error_occurred` signal. Cancellation: `loader.requestInterruption()` + `loader.wait(500)` during cleanup, no timeout exception handling around `.wait()`.

**Error Propagation:** Loader creation in `_fetch_models()` has no try/except — synchronous exceptions propagate uncaught to the GUI thread. Cleanup's `loader.wait(500)` is not wrapped; if stuck or timed out, an unhandled exception may propagate to the GUI thread. Unexpected signals on the loader (beyond the three wired) go to default Qt behavior (likely ignored).

---

## Audio Configuration Tab

### `AudioTab` — `eloquent_notes.config_gui.tabs.audio`

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

---

## General Configuration Tab

### `GeneralTab` — `eloquent_notes.config_gui.tabs.general`

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
|---|-------|------------|---------|
| `self.chk_autostart` (QCheckBox) | Instance | `_init_ui`, `load_settings`, `save_settings` | `.setChecked()` in load; read via `.isChecked()` / `.toolTipText` in save and init |
| `self.cmb_log_level` (QComboBox) | Instance | `_init_ui`, `load_settings`, `save_settings` | Items added once in init; `.setCurrentText()` in load; read via `.currentText()` in save |
| `self.spn_log_max_mb` (QSpinBox) | Instance | `_init_ui`, `load_settings`, `save_settings` | Range/setSuffix fixed in init; `.setValue()` in load; read via `.value()` in save |
| `self.spn_log_backups` (QSpinBox) | Instance | `_init_ui`, `load_settings`, `save_settings` | Same pattern as max_mb above |

**External I/O:** Filesystem read: `os.path.exists(autostart_path)` to check autostart file existence. Path expansion via `os.path.expanduser()`. External application launch via `QDesktopServices.openUrl()` — OS-level only, no write from this function. Filesystem write/delete: `os.remove(autostart_path)` to remove autostart entry on save.

**Error Propagation:** `_view_log_file()` silently returns if the log file does not exist at runtime (no user feedback). If `QDesktopServices.openUrl()` or `QUrl.fromLocalFile()` raises, exception bubbles up unhandled. `save_settings()` catches unexpected errors from sibling module calls and path operations with bare `except Exception as e:` — surfaces a critical QMessageBox; returns `False`. Missing config keys (`KeyError` on `"logging"` etc.) propagate without catch.

---

## Obsidian Integration Tab

### `ObsidianTab` — `eloquent_notes.config_gui.tabs.obsidian`

User-configurable integration layer between the dictation application and the Obsidian note-taking ecosystem. Lets users specify where their vault lives, control how dictated content gets persisted to a target folder, and optionally enrich suggestions with context from existing notes (daily-notes toggle and vault-context toggle). Inherits directly from `ConfigTab`.

**Constructor:** Builds UI layout containing four controls: vault path field with browse button, target folder field for dictation output location, daily-notes toggle (append to `YYYY-MM-DD.md` vs standalone files), and vault-context toggle (scan vault names and suggest as wikilinks during classification).

**Methods:**
| Method | Description |
|--------|-------------|
| `_browse_vault_path(self) -> None` | Expands user-relative paths in current text, falls back to `~/`, then lets a Qt directory picker return an absolute path which gets written back into the field. No error handling for malformed input. |
| `load_settings(config_data: dict) -> None` | Reads stored configuration dictionary and populates each widget (vault path, target folder, both checkboxes). |
| `save_settings(config_data: dict) -> bool` | Collects current UI state and updates the `"obsidian"` sub-dict. Validates vault path non-emptiness — if empty shows a warning dialog; if directory does not exist offers a confirmation dialog (user decline aborts save). Returns `True` on success, `False` otherwise. |

**External I/O:** `_browse_vault_path()`: `os.path.expanduser()` expands home; `os.path.exists()` validates before dialog; falls back to `~/` if validation fails. No error handling for empty text or malformed paths — will raise unhandled. Qt directory picker via `QFileDialog.getExistingDirectory(...)` returns empty string on cancel (swallowed by default).

**Error Propagation:** Only explicit error flow is the existence check in `save_settings()` — if directory does not exist and user denies, returns `False`. No validation of other fields (e.g., empty target folder). Qt dialog errors are swallowed.

---

## Top-Level Dialog Orchestration

### `ConfigurationDialog(QDialog)` — `eloquent_notes.config_gui.dialog`

Dialogue window for full application settings management. Initializes six tab widgets (`GeneralTab`, `ObsidianTab`, `AITab`, `AudioTab`, `PromptsTab`, `TemplatesTab`) and populates UI with settings loaded via `config.load_config()`. Sets minimum size to (850, 650). Applies stylesheet from `QSS_STYLESHEET` in `styles.py`.

**Instance State:**
| Variable | Location | Modification Pattern |
|---|----------|---------------------|
| `self.config_data` (dict) | Instance attribute, set in `__init__` via `config.load_config()` | Reassigned in `restore_defaults()` (`default_data = yaml.safe_load(f)` then reassigned). Read by `load_settings_to_ui()` and `save_settings_from_ui()`. |
| `self._tabs` (list of tuples) | Instance attribute, set in `_init_ui()` | Assigned once. Not modified after initialization. |

**Public Methods:**
| Method | Description |
|--------|-------------|
| `load_settings_to_ui(self) -> None` | Iterates over all tab widgets and calls their `load_settings()` method to populate widget states from the loaded configuration dict stored in `self.config_data`. |
| `restore_defaults(self) -> None` | Overwrites current edits with factory defaults after user confirmation via a `QMessageBox.question()`. On **Yes**: reads default config from `config.DEFAULT_CONFIG_SRC` using `yaml.safe_load()`; loads defaults into each tab widget via `load_settings()` and `restore_defaults()`. Shows informational message confirming restoration. On **No** or exception: returns early without changes (or shows critical error dialog). |
| `save_settings_from_ui(self) -> bool` | Gathers settings from all tab widgets and persists to disk via `config.save_config(overrides)`. Uses `diff_configs()` to compute differences between default config and current data. Returns **True** if all tabs return valid results and save succeeds; **False** if any tab returns False (validation failed), or an exception occurs during save. |
| `cleanup_tabs(self) -> None` | Iterates over all tab widgets and calls their internal `cleanup()` method to release resources before closing. |

**Inherited Public Methods (Overridden):**
| Method | Description |
|--------|-------------|
| `reject(self)` | Calls `cleanup_tabs()` first, then proceeds with standard dialog rejection. |
| `accept(self)` | Validates settings via `save_settings_from_ui()`. If successful, calls `cleanup_tabs()` and proceeds with standard dialog acceptance. |

**External I/O:** YAML config file read (load) via `config.load_config()`; YAML config file write on save via `config.save_config(overrides)`; default config file read for defaults (`DEFAULT_CONFIG_SRC`) and re-read before save. Both paths resolved via `eloquent_notes.config`.

**Error Propagation:**
| Method | Scope of `try`/except | Swallowed Errors (shown to user) | Unhandled Exceptions |
|--------|----------------------|----------------------------------|---------------------|
| `__init__` | None | — | Any exception from `config.load_config()` propagates up the call stack and crashes dialog construction. No parent window available, so no QMessageBox can be shown. |
| `_init_ui()` | None | — | Any exception (e.g., stylesheet load failure) propagates out of constructor. |
| `load_settings_to_ui()` | None | — | Propagates if any tab's `load_settings` raises unhandled exceptions. |
| `restore_defaults()` | `with open(...) + yaml.safe_load(...)` wrapped in bare `except Exception as e` | Swallowed and displayed via `QMessageBox.critical("Error", ...)` | Any exception from the YAML load is caught; no further propagation. |
| `save_settings_from_ui()` | Entire loop over tabs + file read + `diff_configs` + `config.save_config(...)` wrapped in bare `except Exception as e` | Swallowed and displayed via `QMessageBox.critical("Save Error", ...)` | Any exception (file I/O, YAML parse, tab validation) is caught; returns `False`. |
| `cleanup_tabs()` | None | — | Unhandled exceptions propagate out of the method. Called before `reject()`/`accept()`, so if it raises, the dialog may close anyway via base class. |

---

## Package Entry Point

### `eloquent_notes.config_gui.__init__.py`

Aggregates exports from submodules:
```python
from eloquent_notes.config_gui.dialog import ConfigurationDialog
from eloquent_notes.config_gui.loader import OllamaModelLoader

__all__ = ["ConfigurationDialog", "OllamaModelLoader"]
```
No external side effects. Performs only internal Python package imports and namespace declarations. The actual I/O interactions are in the imported modules (`eloquent_notes.config_gui.dialog` and `eloquent_notes.config_gui.loader`).