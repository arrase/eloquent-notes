# Configuration GUI Tabs Module

## Overview

The `eloquent_notes.config_gui.tabs` package provides a graphical configuration interface organized as separate tab widgets, each responsible for one category of application settings. A shared abstract base class (`ConfigTab`) defines the lifecycle contract every tab must implement: loading persisted values from a configuration dictionary into UI controls, writing current widget state back out to the same structure on save, restoring defaults, and releasing background resources. Each concrete tab subclass encapsulates its domain — AI model pipeline parameters, audio capture settings, general/autostart/logging behavior, Obsidian vault integration, or editable text files (prompts and templates). The package entry point aggregates all tab classes under `__all__`, exposing them through the top-level import path.

### Data Flow

```
config_data dict  ←→  ConfigTab subclasses  ←→  Qt widget state
     │                         │                        │
     ▼                         ▼                        ▼
  caller-owned                instance-scoped           user interaction
  settings container         mutable UI controls        event loop
```

The `config_data` dictionary is the single source of truth shared across all tabs. `load_settings()` reads from it; `save_settings()` writes back into it (mutating by reference). Each tab operates on a distinct sub-dictionary key (`"ai"`, `"audio"`, `"general"` / `"logging"`, `"obsidian"`, or the text-files cache keyed by path).

---

## Base Classes

### `ConfigTab` — `eloquent_notes.config_gui.tabs.base`

**Responsibility**: Abstract contract for configuration tab widgets. Defines four lifecycle methods; two are abstract (must be overridden), two have no-op defaults.

| Method | Contract |
|--------|----------|
| `load_settings(config_data: dict) -> None` | **Abstract**. Subclasses must populate UI controls from the caller-supplied dictionary. No return value defined. |
| `save_settings(config_data: dict) -> bool` | **Abstract**. Subclasses must write current widget state back into `config_data`. Returns `True` when the saved configuration is valid; returns `False` to signal invalidity (caller may surface a dialog). |
| `restore_defaults() -> None` | Default body is `pass`. Optional override for tabs that need custom default restoration. |
| `cleanup() -> None` | Default body is `pass`. Optional override for tabs with background resources (e.g., model loaders in `AITab`). |

**State**: No mutable instance state. Pure interface definition.

---

### `TextFilesTab` — `eloquent_notes.config_gui.tabs.text_files`

**Responsibility**: Generic tab that displays a list of independent text files, allows per-item selection, supports in-memory editing via a monospace editor, and persists contents to disk through the application's `config.save_file()` abstraction. The UI is built as a vertical splitter: left pane lists file entries (`QListWidget`), right pane hosts an editable `QTextEdit`.

**Constructor**: `__init__(self, items, editor_label, placeholder, parent=None)`
- `items`: list of `(label, path)` tuples defining the files this tab manages.
- `editor_label`: text shown above the editor widget (e.g., `"Prompt Content:"` or `"Template Content:"`).
- `placeholder`: instructional string displayed in the empty editor area until an item is selected.

**State**:

| Variable | Type | Mutated In | Notes |
|---|---|---|---|
| `self.items` | list of tuples | Constructor only, read-only thereafter | Passed via constructor; never reassigned |
| `_block_cache` | bool | `_on_item_changed`, `load_settings`, `restore_defaults` | Guard flag for batch-mode writes to `loaded_contents`. Set `True` before bulk operations, reverted to `False` after. No synchronization used. |
| `loaded_contents` | dict (path → str) | All public methods: `_on_item_changed`, `commit_active_editor`, `load_settings`, `restore_defaults`, `save_settings` (via commit) | Primary shared state. Read and written across multiple methods with no locking or atomic protection. |
| `current_item` | `QListWidgetItem` / None | Constructor, `_on_item_changed`, `restore_defaults` | Reference to the currently selected list item; cleared when selection is empty. |

**Methods**:

- **`_init_ui(self)`** — Private. Builds the vertical splitter layout containing a `QListWidget` and an editable `QTextEdit`.
- **`_on_item_changed(self, current, previous)`** — Handles selection changes: saves content of the previously active item into `loaded_contents` keyed by its path, loads the new item's cached or empty content into the editor, and enables it.
- **`commit_active_editor(self)`** — Forces current editor contents back into `loaded_contents`. Called before bulk save to ensure in-flight edits are flushed.
- **`load_settings(config_data: dict) -> None`** — Reads each configured path via `config.load_file()`, populates `loaded_contents`, and auto-selects the first item if any exist. Missing files fall back to a default path (if present) or an empty string.
- **`restore_defaults(self) -> None`** — Clears working state and reloads only from default paths, optionally updating the editor view for whichever item is currently selected.
- **`save_settings(config_data: dict) -> bool`** — Commits active editor contents to cache via `commit_active_editor()`, then writes every cached file path back to disk using its stored content. Always returns `True`.

**Error Propagation**: No explicit error handling for any file I/O. Every `config.load_file()` and `config.save_file()` call runs without a `try`/`except`. A read failure propagates up to the Qt event loop; a write failure is silently swallowed (return value is `True` regardless). Any unhandled exception in this class crashes the UI thread.

---

### `PromptsTab` — `eloquent_notes.config_gui.tabs.prompts`

**Responsibility**: Configuration tab for editable prompt templates. Extends `TextFilesTab` and reuses its file-editor layout; only the constructor differs from the base text-files implementation.

**Constructor**: `__init__(self, parent=None)`
- Delegates to `TextFilesTab.__init__()` with `items=PROMPTS`, `editor_label="Prompt Content:"`, and `placeholder="Select a prompt to edit..."`.
- `PROMPTS` is imported from `eloquent_notes.config_gui.constants`; not re-exported by this module.

**State**: No mutable state beyond what `TextFilesTab` inherits.

**Error Propagation**: None explicitly handled. If the parent constructor raises, it propagates unhandled to the caller.

---

### `TemplatesTab` — `eloquent_notes.config_gui.tabs.templates`

**Responsibility**: Configuration tab for editable template files. Extends `TextFilesTab` with the same file-editor layout; differs only in initialization parameters.

**Constructor**: `__init__(self, parent=None)`
- Delegates to `TextFilesTab.__init__()` with `items=TEMPLATES`, `editor_label="Template Content:"`, and `placeholder="Select a template to edit..."`.
- `TEMPLATES` is imported from the constants module within this package.

**State**: No mutable state beyond what `TextFilesTab` inherits.

**Error Propagation**: None explicitly handled. Parent constructor errors propagate unhandled.

---

## AI Configuration Tab

### `AITab` — `eloquent_notes.config_gui.tabs.ai`

**Responsibility**: Manages the AI model pipeline for a dictation/voice-to-text application that uses an Ollama-compatible local or remote LLM server. Configures connection URL, selected model, context length (with optional default override), keep-alive durations, retry count, and request timeouts. Tracks background model-loader lifecycle via signal/slot connections without explicit synchronization primitives.

**Constructor**: `__init__(self, parent=None)`
- Accepts an optional Qt parent widget. Initializes UI form controls for all pipeline parameters. Sets up initial state including `_model_loader` reference (cleared on exit) and `_running_loaders` set (initially empty).

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `cleanup(self)` | — | Asynchronously cancels active loaders via `loader.requestInterruption()` with a 500 ms wait each, then clears the loader set and model loader references. No exception handling around `.wait()`. |
| `load_settings(config_data: dict) -> None` | `config_data: dict` | Populates all widgets from an `ai` sub-dict of `config_data`. Triggers an initial model fetch at the end, which populates a combo box and preserves any previously selected model across reloads. |
| `save_settings(config_data: dict) -> bool` | `config_data: dict` | Reads widget values back into `config_data["ai"]`, validates URL non-emptiness and that keep-alive durations match regex `^-?\d+[smh]?`. Returns `False` on validation failure with a warning dialog. |

**Private Methods**:
- `_init_ui(self)` — Builds the form controls for all pipeline parameters.
- `_toggle_context_default(self, checked: bool)` — Checkbox disables/enables the context length spinner when checked/unchecked respectively. Spinner range is 512–262144 with step 1024.
- `_fetch_models(self)` — Instantiates `OllamaModelLoader(url, QCoreApplication.instance())`, adds to `_running_loaders` set via `.add()`, starts it without try/except wrapping. Signal connections wire `finished`, `models_fetched`, and `error_occurred`.
- `_on_loader_finished(self)` — Removes the loader from `_running_loaders` via `.discard()`; clears the model loader reference.
- `_on_models_fetched(self, models)` — Updates UI label with fetched model list.
- `_on_models_fetch_failed(self, error_msg)` — Updates UI label to `"Connection failed: {error_msg}"` in red.

**State**:

| Variable | Type | Modified By | Notes |
|---|---|---|---|
| `self._model_loader` | OllamaModelLoader / None | `_fetch_models`, cleared in `_on_loader_finished` and `cleanup` | Set in constructor, reassigned on fetch, cleared on completion or cleanup. No synchronization. |
| `self._running_loaders` | set of loaders | Added via `.add()` in `_fetch_models`; removed via `.discard()` or `.clear()` in `_on_loader_finished`/`cleanup`. No sync. | Tracks active background loaders for cancellation and lifecycle management. |

**External I/O**:
- **Network**: Ollama model list fetch via `OllamaModelLoader(url)` — outbound HTTP/gRPC over TCP to the configured URL. Errors surface through `loader.error_occurred` signal.
- **Cancellation**: `loader.requestInterruption()` + `loader.wait(500)` during cleanup. No timeout exception handling around `.wait()`.

**Error Propagation**:
1. Loader creation in `_fetch_models()` has no try/except — synchronous exceptions propagate uncaught to the GUI thread.
2. Cleanup's `loader.wait(500)` is not wrapped; if stuck or timed out, an unhandled exception may propagate to the GUI thread.
3. Unexpected signals on the loader (beyond the three wired) go to default Qt behavior (likely ignored).

---

## Audio Configuration Tab

### `AudioTab` — `eloquent_notes.config_gui.tabs.audio`

**Responsibility**: Graphical configuration panel for microphone/audio capture parameters. Users define sample rate, channel count, audible feedback beeps (toggled and tuned), before any recording occurs. No audio processing is performed here; only user preference persistence.

**Constructor**: `__init__(self, parent=None)`
- Accepts an optional Qt parent widget. Calls `_init_ui`.

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `load_settings(config_data: dict) -> None` | `config_data: dict` | Reads the `"audio"` sub-dict from `config_data`, populates each widget (sample rate → spinbox value; channel count → combo index mapped 1→0 or 2→1; boolean flags, beep frequency/duration directly). |
| `save_settings(config_data: dict) -> bool` | `config_data: dict` | Writes current widget values back into the `"audio"` sub-dict under matching keys (`"sample_rate"`, `"channels"` mapped from index to 1/2, `"beep_enabled"`, `"beep_frequency"`, `"beep_duration"`). Always returns `True`. |

**Private Methods**:
- `_init_ui(self)` — Builds a `QGroupBox` containing five controls: sample rate (`8000–96000 Hz`, step 8000), channel count (Mono/Stereo combo), beep-on-start/stop toggle, beep frequency (`100–5000 Hz`), and beep duration (`0.01–2 sec`).

**State**:

| Attribute | Type | Modified By |
|---|---|---|
| `self.spn_sample_rate` | QSpinBox | `_init_ui()` (setValue), `save_settings()` (value()) |
| `self.cmb_channels` | QComboBox | `_init_ui()` (addItems, setCurrentIndex), `save_settings()` (currentIndex) |
| `self.chk_beep_enabled` | QCheckBox | `_init_ui()`, `load_settings()` (setChecked), `save_settings()` (isChecked) |
| `self.spn_beep_freq` | QSpinBox | `_init_ui()` (setRange), `load_settings()` (setValue), `save_settings()` (value()) |
| `self.spn_beep_duration` | QDoubleSpinBox | `_init_ui()` (setRange, setDecimals), `load_settings()` (setValue), `save_settings()` (value()) |

**External I/O**: None. All interactions are confined to Qt widget instantiation and the caller-supplied `config_data` parameter. No locks or synchronization mechanisms.

**Error Propagation**: Errors are silently swallowed — `_init_ui()` has no try/except, `load_settings()` has no fallback for missing keys (a single `KeyError` crashes), and `save_settings()` returns hardcoded `True`. The only error path is a bare Python crash on unhandled exceptions during widget construction or dict access.

---

## General Configuration Tab

### `GeneralTab` — `eloquent_notes.config_gui.tabs.general`

**Responsibility**: Manages two categories of general behavior: whether the application launches automatically on system login, and how logging behaves (verbosity level, file size cap, number of retained backups). Persists settings to/from the configuration dictionary under a `"logging"` key. Provides an action to open the background daemon log file in the system editor.

**Constructor**: `__init__(self, parent=None)`
- Accepts an optional Qt parent widget. Constructs UI for autostart and logging groups.

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `_view_log_file(self)` | — | Resolves the log file path in the app's log directory, confirms it exists (otherwise returns without feedback), then opens it with `QDesktopServices.openUrl()`. No write to disk from this function. |
| `load_settings(config_data: dict) -> None` | `config_data: dict` | Populates UI controls from a configuration dictionary. Reads values for autostart path, logging level, max log size (MB), and backup count. Checks whether the autostart file exists at runtime via `os.path.exists()`. |
| `save_settings(config_data: dict) -> bool` | `config_data: dict` | Writes current widget state back into the configuration dictionary under a `"logging"` key. Returns `True` on success; returns `False` if autostart update fails (surfaces a critical message box). Catches unexpected errors from sibling module calls and path operations with bare `except Exception as e:`. |

**State**:

| Variable | Scope | Mutated In | Details |
|---|---|---|---|
| `self.chk_autostart` (QCheckBox) | Instance | `_init_ui`, `load_settings`, `save_settings` | `.setChecked()` in load; read via `.isChecked()` / `.toolTipText` in save and init |
| `self.cmb_log_level` (QComboBox) | Instance | `_init_ui`, `load_settings`, `save_settings` | Items added once in init; `.setCurrentText()` in load; read via `.currentText()` in save |
| `self.spn_log_max_mb` (QSpinBox) | Instance | `_init_ui`, `load_settings`, `save_settings` | Range/setSuffix fixed in init; `.setValue()` in load; read via `.value()` in save |
| `self.spn_log_backups` (QSpinBox) | Instance | `_init_ui`, `load_settings`, `save_settings` | Same pattern as max_mb above |

**External I/O**:
- Filesystem read: `os.path.exists(autostart_path)` to check autostart file existence.
- Path expansion for autostart location via `os.path.expanduser()`.
- External application launch via `QDesktopServices.openUrl()` — OS-level only, no write from this function.
- Filesystem write/delete: `os.remove(autostart_path)` to remove autostart entry on save.

**Error Propagation**:
- `_view_log_file()`: If the log file does not exist at runtime, silently returns via early return — no user feedback.
- `_view_log_file()`: If `QDesktopServices.openUrl()` or `QUrl.fromLocalFile()` raises, exception bubbles up unhandled (crash).
- `save_settings()`: Unexpected errors from sibling module calls and path operations are caught by bare `except Exception as e:` — user sees a critical QMessageBox with the exception string; returns `False`.
- Missing config keys (`KeyError` on `"logging"` etc.) propagate without catch.

---

## Obsidian Integration Tab

### `ObsidianTab` — `eloquent_notes.config_gui.tabs.obsidian`

**Responsibility**: User-configurable integration layer between the dictation application and the Obsidian note-taking ecosystem. Lets users specify where their vault lives, control how dictated content gets persisted to a target folder, and optionally enrich suggestions with context from existing notes (daily-notes toggle and vault-context toggle).

**Constructor**: `__init__(self, parent=None)`
- Inherits from `ConfigTab`. Builds UI layout containing four controls: vault path field with browse button, target folder field for dictation output location, daily-notes toggle (append to `YYYY-MM-DD.md` vs standalone files), and vault-context toggle (scan vault names and suggest as wikilinks during classification).

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `_browse_vault_path(self) -> None` | — | Expands user-relative paths in current text, falls back to `~/`, then lets a Qt directory picker return an absolute path which gets written back into the field. No error handling for malformed input. |
| `load_settings(config_data: dict) -> None` | `config_data: dict` | Reads stored configuration dictionary and populates each widget (vault path, target folder, both checkboxes). |
| `save_settings(config_data: dict) -> bool` | `config_data: dict` | Collects current UI state and updates the `"obsidian"` sub-dict. Validates vault path non-emptiness — if empty shows a warning dialog; if directory does not exist offers a confirmation dialog (user decline aborts save). Returns `True` on success, `False` otherwise. |

**State**: All `self.*` attributes are Qt widget instances (`QLineEdit`, `QPushButton`, `QCheckBox`). No dedicated configuration variables or tracked counters exist on the instance. The only externally modified object is the caller-provided `config_data: dict`.

**External I/O**:
- `_browse_vault_path()`: `os.path.expanduser()` expands home; `os.path.exists()` validates before dialog; falls back to `~/` if validation fails. No error handling for empty text or malformed paths — will raise unhandled.
- Qt directory picker via `QFileDialog.getExistingDirectory(...)` returns empty string on cancel (swallowed by default).

**Error Propagation**: Only explicit error flow is the existence check in `save_settings()` — if directory does not exist and user denies, returns `False`. No validation of other fields (e.g., empty target folder). Qt dialog errors are swallowed.

---

## Package Entry Point

### `eloquent_notes.config_gui.tabs` — `__init__.py`

**Responsibility**: Aggregates all tab classes into this package's public API surface, making each accessible from the top-level import path. Performs only internal relative imports (`from .ai import AITab`, etc.); no network calls, disk access, database operations, or API interactions are present. No custom exception handling is defined — if any submodule import fails at runtime, Python raises `ImportError` directly with no catch.

**Exported Classes**:
- `AITab` (from `.ai`)
- `AudioTab` (from `.audio`)
- `GeneralTab` (from `.general`)
- `ObsidianTab` (from `.obsidian`)
- `PromptsTab` (from `.prompts`)
- `TemplatesTab` (from `.templates`)

**State**: No mutable state. Pure module-level aggregation.

---

## Summary of Module Relationships

```
ConfigTab (abstract base)
├── AITab            — AI/Ollama model pipeline configuration; manages background loader lifecycle via signals
├── AudioTab         — Microphone capture parameters; static preferences, no audio processing
├── GeneralTab       — Autostart and logging behavior; filesystem ops on ~/.config/autostart/*
├── ObsidianTab      — Vault integration with daily-notes/context toggles; directory picker for vault selection
└── (inherited) TextFilesTab → PromptsTab / TemplatesTab
     └── config.load_file() / config.save_file() abstraction for persistent text file editing
```

All tabs share the same `load_settings(config_data)` / `save_settings(config_data) -> bool` contract defined by `ConfigTab`. The `config_data` dict is the central state container; each tab writes to a distinct sub-dictionary key or an in-memory cache keyed by path (for text files). No synchronization primitives, locks, mutexes, atomics, or async/await are used across any of these modules. All mutable instance state is scoped to individual tab widgets and accessed within the Qt event loop's single-threaded model.