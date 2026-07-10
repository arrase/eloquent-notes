# Configuration GUI — `eloquent_notes.config_gui`

## Module Responsibility

This package exposes a Qt-based configuration UI for Eloquent Notes. It provides:

- A **dialog** (`ConfigurationDialog`) that loads settings from disk, presents them across six tab widgets, and persists only divergent values back to the YAML config file on save.
- An **async Ollama model loader** (`OllamaModelLoader`) that runs in a `QThread` to discover audio-capable models from the remote `/api/tags` endpoint without blocking the UI.
- A **tab subsystem** (`eloquent_notes.config_gui.tabs`) aggregating six domain-specific tab widgets under one namespace, each inheriting from an abstract base class and communicating through a caller-owned shared dictionary.

---

## Data Flow Overview

```
Disk (YAML)  ──config.load_config()──►  config_data: dict  ──load_settings()──►  Tab widgets
                                                              │
                                                              ▼
User edits ──save_settings_from_ui()──►  Per-tab save_settings()  ◄── validation gates
                                                              │
                                                              ▼
                                              diff_configs(default, current)
                                                              │
                                                              ▼
Disk (YAML)  ◄──config.save_config(overrides)────

OllamaModelLoader ──QThread.run()──►  GET /api/tags  ──►  model names
                                                              │
                                                              ├── POST /api/show per name ──►  capabilities check ──► "audio" filter
                                                              │
                                                              ▼
                                              models_fetched(list)  ◄── main thread signal

Tabs  ◄── shared config_data dict (caller-owned reference, no copy semantics)
```

---

## Public Surface Area

### `eloquent_notes.config_gui.__init__`

- **Exports:** `ConfigurationDialog`, `OllamaModelLoader`.
- No logic; purely declarative. Bare imports from `.dialog` and `.loader`; failures propagate as raw `ImportError` / `ModuleNotFoundError`.

---

## Configuration Dialog — `eloquent_notes.config_gui.dialog`

### `ConfigurationDialog(QDialog)`

| Method | Signature | Notes |
|--------|-----------|-------|
| `__init__(self, parent=None)` | Optional[QDialog] | Loads factory defaults from YAML once; populates six tabs. |
| `load_settings_to_ui(self)` | — | Populates tabs from current disk state (called externally). |
| `restore_defaults(self)` | — | Bare `try/except Exception`; on failure shows `QMessageBox.critical` with `"Failed to restore defaults: {e}"`, returns normally. On success reloads factory YAML into all tabs and emits info message. |
| `save_settings_from_ui(self)` | — | Iterates each tab's `save_settings()` for validation; if any return `False`, rejects without writing. On full success computes diff between loaded defaults (`self.config_data`) and current UI state, writes only differing keys via `config.save_config(overrides)`. Wraps entire pipeline in bare `try/except Exception`; on failure shows critical message with `"Failed to save settings: {e}"` and returns `False`. |
| `cleanup_tabs(self)` | — | Releases tab resources; called unconditionally in `reject()` and conditionally (only when save succeeded) in `accept()`. |
| `reject(self)` | — | Calls cleanup, then `super().reject()`. No error wrapping. |
| `accept(self)` | — | Calls `save_settings_from_ui()`. If it returns `True`, calls `cleanup_tabs()` then `super().accept()` (Qt event loop shutdown). On failure the outer except in `save_settings_from_ui` swallows the exception before this method is reached. |

### Business Rules

1. **Diff-based persistence.** Only values that differ from factory defaults are written to disk on save. Unchanged settings retain their defaults without rewriting.
2. **Per-tab validation gates.** Each tab implements its own `save_settings()` returning a boolean. If any fails, the dialog rejects and highlights the offending tab.
3. **Defaults restoration is opt-in.** A confirmation prompt must be accepted before overwriting current edits with factory defaults. If cancelled, no state change occurs.
4. **Thread cleanup on both exit paths.** Regardless of Accept/Reject/Save/Cancel outcome, tab resources are cleaned up and running threads stopped before the dialog closes.

---

## Ollama Model Loader — `eloquent_notes.config_gui.loader`

### `OllamaModelLoader(QThread)`

| Method | Signature | Notes |
|--------|-----------|-------|
| `__init__(self, url, parent=None)` | None | Sets `self.url`; no return. |
| `run(self)` | — (signals) | Async worker: GET `/api/tags` (2s timeout), extracts model names from `data["models"]`. For each name, POST to `/api/show` with `{"name": <model>}`; inspects `capabilities` array for `"audio"`. Per-model exceptions are silently swallowed. If any HTTP call fails with non-200 status or a top-level exception occurs (and interruption not requested), emits `error_occurred(str)`. On success, accumulates audio-capable model names and emits `models_fetched(list)`. |

### Concurrency Model

- Runs in a dedicated `QThread` (`run()` is called via `start()`).
- Communicates results to the main thread via PyQt6 signals: `models_fetched(list)`, `error_occurred(str)`.
- No locks or mutexes; signal emission handles thread-safe delivery.

---

## Tab Subsystem — `eloquent_notes.config_gui.tabs`

### Base Class — `ConfigTab(QWidget)` (abstract)

All six domain tabs inherit from this abstract anchor, which enforces two interface contracts:

| Method | Returns | Notes |
|--------|---------|-------|
| `load_settings(config_data: dict)` | `None` | Subclasses must read nested keys and hydrate widgets. Base raises `NotImplementedError`. |
| `save_settings(config_data: dict) -> bool` | `bool` | Must return `True` for valid state, `False` on validation failure (empty fields, invalid formats, cancellation). |
| `restore_defaults(self)` | `None` | Resets widgets to initial values. Base is no-op; subclasses override. Unimplemented raises `NotImplementedError`. |
| `cleanup(self)` | `None` | Releases background resources. Base is no-op; subclasses override when owning long-running operations. |

The base class itself performs zero I/O and mutates nothing beyond the caller-provided dict reference.

### Domain Tabs

#### `ai.py` — `AITab` (Ollama Integration)

Manages connection parameters, model selection, context length tuning, keep-alive durations, and retry logic for Ollama-based LLM voice-to-text dictation tasks.

| Method | Notes |
|--------|-------|
| `_fetch_models(self)` | Constructs `OllamaModelLoader` from `.eloquent_notes.config_gui.loader`, connects three signals (`finished`, `models_fetched`, `error_occurred`), calls `loader.start()`. Signal handlers populate or clear the combo box; stale sender check returns silently. |
| `_on_loader_finished(self)` | Discards current loader reference. |
| `_on_models_fetched(self, models)` | Populates combo box from returned list while preserving any previously selected text. |
| `_on_models_fetch_failed(self, error_msg)` | Writes error string to a status label in red; no user prompt. |
| `cleanup(self)` | Cancels in-flight loaders via `loader.requestInterruption()`, waits 500ms per loader synchronously (no timeout enforcement), clears references. |

**Validation:** `save_settings()` returns `False` if URL is empty or keep-alive duration formats are invalid. Two regex checks enforce `^-?\d+[smh]?$`.

#### `audio.py` — `AudioTab` (Microphone Capture Settings)

Manages sample rate selection, channel mode, and recording feedback control via an optional audible beep at start/stop events.

| Widget | Type | Notes |
|--------|------|-------|
| `spn_sample_rate` | QSpinBox | 8000–96000 Hz in steps of 8000; tooltip calls out 16000 Hz as recommended for speech recognition. |
| `cmb_channels` | QComboBox | Mono (single) vs Stereo (two). |
| `chk_beep_enabled` | QCheckBox | When checked, exposes beep frequency and duration fields below. |
| `spn_beep_freq` | QSpinBox | 100–5000 Hz. |
| `spn_beep_duration` | QDoubleSpinBox | 0.01–2.0 sec. |

Always returns `True` from `save_settings()`. No external I/O; no try/except blocks in this file.

#### `general.py` — `GeneralTab` (Autostart + Logging)

Manages three configuration domains: autostart behavior on desktop session login, logging verbosity and retention policy, and log inspection via system editor.

| Method | Notes |
|--------|-------|
| `_view_log_file` | Reads `~/.config/autostart/eloquent-notes.desktop` via `os.path.exists()` to check autostart state; calls `QDesktopServices.openUrl(...)` to open the log file in user's default editor. Swallowed by Qt if unavailable. |

**Non-atomic save:** Logging config is updated first, then the `.desktop` entry is created or removed separately via `install_autostart()` (imported from `.eloquent_notes.autostart`). If autostart write fails after logging config was committed to `config_data`, the dict holds inconsistent state. Broad `try/except` wraps autostart logic; on any failure displays `QMessageBox.critical` and returns `False`. Missing log file case handled silently with `QMessageBox.information`.

#### `obsidian.py` — `ObsidianTab` (Vault Routing)

Manages vault root path, target subfolder, daily note vs standalone file routing, and optional vault-aware wikilink suggestions during classification.

| Operation | Notes |
|-----------|-------|
| `_browse_vault_path()` | Calls `QFileDialog.getExistingDirectory(self, ...)`. If current text is non-empty, calls `os.path.expanduser()` + `os.path.exists()`. Non-existent path falls back to `~/` silently (not an error). |

**Validation:** Empty vault path after `.strip()` triggers `QMessageBox.warning(...)` returning `False`. Path that does not exist on disk prompts via `QMessageBox.question(...)` with Yes/No; if **Yes**, validation passes anyway. No exceptions are caught anywhere in this file—`os.path.expanduser()`, `QFileDialog.getExistingDirectory()`, and `.text()` all propagate uncaught up to the caller.

#### `text_files.py` — `TextFilesTab` (Generic Text Files Framework)

Framework for managing multiple named text files as configuration entries. Each entry has a display label, primary storage path, and optional fallback/default path. All six tabs (`prompts`, `templates`) are thin subclasses delegating to this base with different constants.

| Method | Notes |
|--------|-------|
| `_init_ui(self)` | Renders horizontal splitter: `QListWidget` on left (entries by label), monospace-text editor on right for currently selected entry's content. |
| `_on_item_changed(self, current, previous)` | Caches previous item's in-memory content back into `loaded_contents`. New item's path is looked up; if cached text exists it loads into the editor, otherwise starts empty. Editor disabled when no item selected and cleared on deselection. |
| `commit_active_editor(self)` | No-op when nothing selected. |

**Cache-first persistence:** All edits go through in-memory dictionary (`loaded_contents`) before being flushed to disk. Ensures atomicity—changes are never partially persisted. Write-blocking during restore/defaults: cache is locked during `load_settings` and `restore_defaults`, preventing writes while rehydrating state from files. Graceful degradation if primary file missing: fallback path tried; if that fails, empty string stored as entry content.

#### Thin Facades — `prompts.py` / `templates.py`

- **`PromptsTab`**: Subclass of `TextFilesTab`. Delegates to parent by supplying `items=PROMPTS`, `editor_label="Prompt Content:"`, `placeholder="Select a prompt to edit..."`. No instance attributes or mutable state defined in this file.
- **`TemplatesTab`**: Same delegation pattern with `items=TEMPLATES`, `editor_label="Template Content:"`, `placeholder="Select a template to edit..."`.

Both depend entirely on constants imported from `.eloquent_notes.config_gui.constants`. If those constants are undefined or raise errors during instantiation, exceptions propagate uncaught.

#### `__init__.py` — Package Entry Point

Re-exports six tab classes (`AITab`, `AudioTab`, `GeneralTab`, `ObsidianTab`, `PromptsTab`, `TemplatesTab`) from their submodules into a single namespace so callers can instantiate tabs via one import rather than per-submodule. Defines `__all__` listing all six class names. Bare imports; any submodule failure propagates as raw exception.

---

## Constants — `eloquent_notes.config_gui.constants`

### Module-Level Data Layer

| Constant | Type (Inferred) | Purpose |
|----------|------------------|---------|
| `PROMPTS` | `List[Tuple[str, str, str]]` | 3-tuples of label + config source path for prompt definitions. |
| `TEMPLATES` | `List[Tuple[str, str, str]]` | 3-tuples of label + config source path for note template types (Standalone Note, Daily Note - New, Daily Note - Append). |

No runtime logic; no mutable state beyond these module-level constants. Import-time side effect: bare import of parent package `eloquent_notes.config_gui`; if absent, raises unhandled `ImportError`.

---

## Utilities — `eloquent_notes.config_gui.utils`

### `diff_configs(default, current) -> dict`

Recursively compares two nested configuration dictionaries. For each key in `current`:
- If absent from `default` → new override; include it.
- If both values are dicts → recurse into nested comparison.
- If either value differs → mark as override; include it.
- Discard branches with no differences (prune empty results).

Returns only non-empty overrides—what changed between default and current. Pure in-memory dict traversal; zero external communication. Unhandled: if `default` or `current` is not iterable/dict-like at top level, `.items()` raises a Python exception (`TypeError`, `AttributeError`). If `k` is missing from `default`, `default[k]` raises `KeyError`. No try/except blocks; all exceptions propagate to callers.

---

## Styling — `eloquent_notes.config_gui.styles`

### `QSS_STYLESHEET` (constant)

A single module-level constant holding the raw Qt Style Sheet string defining visual appearance for every widget type in the configuration GUI: `QDialog`, `QWidget`, `QTabWidget`, `QTabBar`, `QLineEdit`, `QSpinBox`, `QDoubleSpinBox`, `QComboBox`, `QTextEdit`, `QListWidget`, `QPushButton`, `QGroupBox`, `QCheckBox`, `QScrollBar`. Catppuccin Mocha palette (#1e1e2e background, #89b4fa accent). No runtime behavior beyond string literal definition; no imports or function calls.

---

## Error Handling Summary

| Pattern | Where | Mechanism |
|---------|-------|-----------|
| **Swallowed with user notification** | `dialog.py` — `restore_defaults`, `save_settings_from_ui` | Bare `try/except Exception`; shows `QMessageBox.critical`, returns normally (or sentinel `False`). |
| **Per-tab validation gate** | All tabs — `save_settings()` | Returns boolean; caller (`ConfigurationDialog`) decides commit/reject. |
| **Silent swallow on per-model failure** | `loader.py` — inner loop | Per-model exception caught and ignored; only top-level or connection errors surface as `error_occurred`. |
| **Signal-based async pipeline with silent state swallows** | `ai.py` | Three distinct patterns: empty URL (silent), invalid duration formats (`QMessageBox.warning` + return False), signal propagation to red status label. No exception handling anywhere in this file. |
| **No wrapping, no sentinels** | `text_files`, `general`, `obsidian` | File I/O failures surface as unhandled exceptions unless Qt event loop catches them at higher level. No try/except blocks; all propagate up to callers. |
| **Non-atomic autostart update** | `general.py` | Logging config updated first, then `.desktop` file created/removed separately. If write fails after logging config was committed, dict holds inconsistent state. |