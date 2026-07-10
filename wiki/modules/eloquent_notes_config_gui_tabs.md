# Module Architecture — `eloquent_notes.config_gui.tabs`

## Responsibility & Data Flow

This package aggregates six domain-specific configuration-tab types under a single namespace so that callers can instantiate tab widgets from one import rather than per-submodule. Each tab is a Qt widget (`QWidget`) subclass responsible for reading from and writing to a shared external `config_data: dict`. The caller (typically the settings dialog or mainframe) owns this dictionary; the tabs treat it as source-of-truth storage, mutating only the slice keyed by their domain name.

All six tabs inherit from an abstract base class that enforces two interface contracts:
- **`load_settings(config_data)`** — hydrates internal UI state from a caller-provided dict and returns `None`.
- **`save_settings(config_data)`** — captures current widget state back into the same dict, returning `True` when persistence is considered valid.

The base class also provides no-op stubs for **`restore_defaults()`** (resets widgets to initial values) and **`cleanup()`** (releases background resources). Subclasses override these methods; unimplemented ones raise `NotImplementedError` so the contract is enforced at runtime rather than compile-time.

## Base Layer: `base.py` — `ConfigTab`

The abstract anchor for all tab widgets. The class hierarchy is:

```
QWidget (PyQt6)
  └── ConfigTab (abstract interface: load_settings, save_settings, restore_defaults, cleanup)
        ├── ai.AITab           # Ollama integration
        ├── audio.AudioTab     # microphone capture settings
        ├── general.GeneralTab # autostart + logging
        ├── obsidian.ObsidianTab  # vault routing
        ├── text_files.TextFilesTab (framework tab)
        │       ├── prompts.PromptsTab      # thin facade
        │       └── templates.TemplatesTab  # thin facade
```

### Interface Contract

| Method | Returns | Notes |
|--------|---------|-------|
| `load_settings(config_data: dict)` | `None` | Raises `NotImplementedError` if subclass does not override. Subclasses must read nested keys from the caller's dict and populate their widgets accordingly. |
| `save_settings(config_data: dict) -> bool` | `bool` | Must return `True` to signal valid state, `False` when validation fails (empty fields, invalid formats, user cancellation). The returned value is consumed by the settings dialog to decide whether to commit or discard changes. |
| `restore_defaults(self)` | `None` | Resets widgets to initial values. Base implementation is a no-op; subclasses implement per-domain defaults. |
| `cleanup(self)` | `None` | Releases background resources (threads, loaders). Base implementation is a no-op; subclasses override when they own long-running operations. |

### Concurrency & State

- No global variables or instance attributes mutate in this file.
- The base class itself performs zero I/O: no threading primitives, no locks (`QMutex`, `threading.Lock`), and no synchronization channels. All state mutations are encapsulated within subclasses' widget fields and the caller-provided dict reference.

### Error Handling

- Errors from underlying implementations propagate raw to callers — no wrapping, no sentinels, no logging.
- `restore_defaults()` and `cleanup()` produce no observable output when called on the base class; a direct call yields nothing unless a subclass overrides them.

## Domain Tabs: Specialized Implementations

### `ai.py` — `AITab` (Ollama Integration)

**Responsibility:** Expose configuration for an Ollama-based LLM backend used for voice-to-text dictation tasks. The tab manages connection parameters, model selection, context length tuning, keep-alive durations, and retry logic.

### API Surface

| Method | Input | Output |
|--------|-------|--------|
| `__init__(self, parent=None)` | `parent`: Optional QWidget | None |
| `_toggle_context_default(self, checked)` | `checked`: bool | None |
| `_fetch_models(self)` | None | None (asynchronous) |
| `_on_loader_finished(self)` | None | None |
| `_on_models_fetched(self, models)` | `models`: list of str | None |
| `_on_models_fetch_failed(self, error_msg)` | `error_msg`: str | None |
| `cleanup(self)` | None | None |
| `load_settings(self, config_data: dict) -> None` | `config_data`: dict with `"ai"` key | None |
| `save_settings(self, config_data: dict) -> bool` | `config_data`: dict with `"ai"` key | bool (True/False per validation) |

### Business Rules & Flow

1. **UI construction** — Build a form with fields for Ollama URL, model selection combo box, context length spin box, keep-alive duration fields, and timeout/retry limits.
2. **Model refresh** — Construct an `OllamaModelLoader` from the loader module, connect three signals (`finished`, `models_fetched`, `error_occurred`), then call `loader.start()`. The signal handlers populate or clear the combo box accordingly while preserving any previously selected text. If the sender on a signal is stale (not the current `_model_loader` reference), the handler returns silently without cleaning up state.
3. **State persistence** — `save_settings()` serializes all AI fields into `config_data["ai"]`. Returns `False` when URL validation fails or keep-alive duration formats are invalid; otherwise `True`. Two separate regex checks enforce the pattern `^-?\d+[smh]?$` on duration fields.
4. **Configuration restoration** — `load_settings()` reads from `config_data["ai"]`, applies values to widgets, toggles default-vs-explicit context mode based on whether the stored value is `None`, then triggers a model refresh. If the URL was empty at load time, `_fetch_models` returns silently and no models populate the combo box; there is no UI feedback beyond the label text change.
5. **Cleanup** — Cancel any in-flight loaders via `loader.requestInterruption()`, wait 500ms per loader synchronously (no timeout enforcement), then clear references.

### Mutable State & Concurrency

| Field | Type | Mutated In | Notes |
|-------|------|------------|-------|
| `self._model_loader` | `OllamaModelLoader` ref | `_fetch_models`, `_on_loader_finished`, `cleanup` | Replaced atomically in `_fetch_models`; set to `None` on finish/error/cleanup. A failed loader is treated identically to a successful one — no error inspection before clearing references. |
| `self._running_loaders` | `set[OllamaModelLoader]` | `_fetch_models` (add), `_on_loader_finished` (discard), `cleanup` (iterate+clear) | Tracks active loaders; cleared in cleanup regardless of whether interruption actually completed. |

All Qt widget fields (`self.txt_ollama_url`, `self.cmb_model`, etc.) are mutable UI state managed by the Qt framework internally.

### External Communication & Errors

- **No direct external I/O** — all outside-world communication is delegated to `OllamaModelLoader` from `.eloquent_notes.config_gui.loader`.
- **Signal-based async pipeline**: Three distinct error-handling patterns coexist:
  - Silent swallow on empty URL (no user notification).
  - `QMessageBox.warning` + `return False` for invalid duration formats.
  - Signal propagation to `_on_models_fetch_failed`, which writes the error string to a status label in red with no user prompt — silent UI-only feedback.
- **No exception handling** anywhere in this file. All errors are expected to propagate via Qt signals from the loader module.

### Side Effects

- Import-time behavior: 6 submodule imports at package level; each may trigger side effects depending on submodule implementation. The `__init__.py` itself contains no direct I/O operations.
- Active model loaders can be interrupted before cleanup completes (e.g., user changes settings).

---

### `audio.py` — `AudioTab` (Microphone Capture Settings)

**Responsibility:** Expose configuration for audio capture used by whisper/dictation models. The tab manages sample rate selection, channel mode, and recording feedback control via an optional audible beep at start/stop events.

### API Surface

| Method | Input | Output |
|--------|-------|--------|
| `__init__(parent=None)` | `parent`: Optional QWidget | None (void) |
| `load_settings(config_data: dict) -> None` | `config_data`: Dict with `"audio"` key containing sample_rate, channels, beep_enabled, beep_frequency, beep_duration | None |
| `save_settings(config_data: dict) -> bool` | `config_data`: Dict with `"audio"` sub-dict to populate in-place | `bool` — always returns `True` |

### Business Rules & Flow

1. **Sample Rate Selection** — User selects a sample rate within 8000 Hz to 96000 Hz, stepping by 8000 Hz. A tooltip explicitly calls out that 16000 Hz is the recommended value for speech recognition models — domain knowledge encoded into the UI hint.
2. **Channel Mode Selection** — Binary choice between Mono (single channel) and Stereo (two channels).
3. **Recording Feedback Control** — Boolean toggle controls whether an audible beep plays at recording start/stop events. When enabled, two additional parameters are exposed:
   - **Beep frequency** (100 Hz to 5000 Hz) — pitch of the feedback tone.
   - **Beep duration** (0.01 sec to 2.0 sec) — length of each beep.

### Mutable State & Concurrency

| Variable | Type | Mutability | Notes |
|---|---|-----------|-------|
| `self.spn_sample_rate` (QSpinBox) | Widget | Mutable | Value set via `setValue()` / `value()`. |
| `self.cmb_channels` (QComboBox) | Widget | Mutable | Index changed by `setCurrentIndex()`. |
| `self.chk_beep_enabled` (QCheckBox) | Widget | Mutable | Checked state toggled by user; read via `isChecked()`. |
| `self.spn_beep_freq` (QSpinBox) | Widget | Mutable | Value set via `setValue()` / `value()`. |
| `self.spn_beep_duration` (QDoubleSpinBox) | Widget | Mutable | Value set via `setValue()` / `value()`. |

All mutable state is encapsulated in UI widgets. The only externally written state is the caller-provided `config_data["audio"]` dict, which this module does not own or protect.

### Concurrency & Errors

- **No external I/O** — zero network, disk, DB, or system-level communication. All "communication" is strictly through method parameters and return values.
- **No try/except blocks** anywhere; no custom exceptions or sentinels defined or used. If `config_data["audio"]` does not exist, `load_settings` will raise a `KeyError`; `save_settings` assumes it exists and would raise `AttributeError` if missing.

---

### `general.py` — `GeneralTab` (Application Configuration Management)

**Responsibility:** Manage three distinct configuration domains: autostart behavior (launch on desktop session login), logging verbosity & retention policy, and log inspection via system editor.

### API Surface

| Method | Input | Output |
|--------|-------|--------|
| `load_settings(config_data: dict) -> None` | `config_data`: Dict with `"logging"` key containing level, max_mb, backups, autostart state | None |
| `save_settings(config_data: dict) -> bool` | `config_data`: Dict to populate in-place | bool (True on success, False on failure) |

### Business Rules & Flow

1. **UI construction** — Build three grouped sections: Startup Options (autostart checkbox), Logging Settings (three form controls for level/size cap/backup count), and a View Logs action button.
2. **State load** — Read stored configuration from `config_data["logging"]`, hydrate each widget accordingly. If `config_data["logging"]` lacks expected keys, it will raise an unhandled `KeyError`.
3. **State save** — Collect current widget values into `config_data["logging"]`; if autostart is enabled, install the `.desktop` entry via `install_autostart()` (imported from `.eloquent_notes.autostart`); otherwise remove it; return success/failure.

### Mutable State & Concurrency

| Variable | Type | Mutability | Notes |
|---|---|-----------|-------|
| `self.chk_autostart` — checked state | Widget | Mutable | Set via `setChecked`/`isChecked`. |
| `self.cmb_log_level` — current text | Widget | Mutable | Set via `setCurrentText`/`currentText`. |
| `self.spn_log_max_mb` — integer value | Widget | Mutable | Set via `setValue`/`.value()`. |
| `self.spn_log_backups` — integer value | Widget | Mutable | Set via `setValue`/`.value()`. |

No concurrency mechanisms. No locks, no channels, no threading primitives used.

### External Communication & Errors

| Method | I/O Type | Details |
|---|---|---|
| `_view_log_file` | File system read | Reads `~/.config/autostart/eloquent-notes.desktop` via `os.path.exists()` to check autostart state. |
| `_view_log_file` | Desktop environment I/O | Calls `QDesktopServices.openUrl(QUrl.fromLocalFile(...))` — opens the log file in the user's default system editor/browser. Swallowed by Qt if unavailable. |
| `save_settings` | File system write | Removes autostart entry at `~/.config/autostart/eloquent-notes.desktop` via `os.remove()` when unchecked. Destructive operation. |
| `save_settings` | Autostart install | Calls `install_autostart()` to write the `.desktop` file when checked. Exact behavior of that module is not visible here; it presumably writes the referenced path. |

### Error Handling

- **Not atomic** — logging config is updated first, then the autostart file is created or removed separately. If the autostart write fails after logging config was committed to `config_data`, the dict holds a state where autostart may be out of sync with what actually happened on disk.
- Broad `try/except` wraps autostart logic in `save_settings`. On any error (file read/write failure, autostart install failure), displays a `QMessageBox.critical` and returns `False`. The returned dict is left partially updated — logging values are written before the autostart block.
- Missing log file case handled silently with user notification via `QMessageBox.information`; no exception raised.

---

### `obsidian.py` — `ObsidianTab` (Vault Integration)

**Responsibility:** Expose configuration for routing dictation output into an Obsidian vault rather than standalone locations. The tab manages vault root path, target subfolder, daily note vs standalone file routing, and optional vault-aware wikilink suggestions during classification.

### API Surface

| Method | Input | Output |
|--------|-------|--------|
| `__init__(self, parent=None)` | `parent`: Optional QWidget | None |
| `_browse_vault_path(self)` | None | None (opens directory chooser) |
| `load_settings(self, config_data: dict) -> None` | `config_data`: Dict with `"obsidian"` key containing vault_path, folder, daily_notes, vault_context | None |
| `save_settings(self, config_data: dict) -> bool` | `config_data`: Dict to populate in-place | bool (True on success, False if user cancels or validation fails) |

### Business Rules & Flow

1. **UI initialization** — Build labeled input widgets for vault path, target folder, and two checkboxes (`daily_notes`, `vault_context`).
2. **On save**, the vault path undergoes validation: non-empty → directory exists. Failures are handled via modals; only confirmed paths are persisted.
3. All four settings are captured into `config_data["obsidian"]` for downstream consumption by other modules that handle dictation file I/O and wikilink generation.

### Mutable State & Concurrency

| Variable | Type | Mutability | Notes |
|---|---|-----------|-------|
| `self.txt_vault_path` — QLineEdit | Widget | Mutated by user input in `_browse_vault_path` (`setText`). |
| `self.btn_browse_vault` — QPushButton | Widget | Reference only, no mutation. |
| `self.txt_obs_folder` — QLineEdit | Widget | Mutated implicitly via Qt signals (user typing), read in `save_settings`. |
| `self.chk_daily_notes` — QCheckBox | Widget | State changed by user clicks (Qt-managed), read in `save_settings`. |
| `self.chk_vault_context` — QCheckBox | Widget | State changed by user clicks (Qt-managed), read in `save_settings`. |

No concurrency mechanisms. No `sync.Mutex`, no threading locks, no channels, no reentrant guards.

### External Communication & Errors

#### Disk I/O

- **`_browse_vault_path()`** — User-triggered dialog opens via `QFileDialog.getExistingDirectory(self, ...)`. If `self.txt_vault_path.text()` is non-empty, it calls `os.path.expanduser()` and then `os.path.exists()`. If the path does not exist on disk, the initial directory falls back to `~/` (the user's home). This is a **silent fallback**, not an error.
- **`save_settings()`** — Writes to `config_data["obsidian"]` dict **in memory**. No disk/DB/network write is performed by this class. The path passed through is normalized via `os.path.abspath(os.path.expanduser(vault))`, which may change the string representation but does not touch the filesystem.

#### Error Handling Strategy

| Condition | Response |
|---|---|
| Vault path is empty after `.strip()` | `QMessageBox.warning(...)` with title `"Validation Error"` and body `"Obsidian Vault Path cannot be empty."` → function returns `False`. Not wrapped, not logged. |
| Normalized vault path does not exist on disk | `QMessageBox.question(...)` with title `"Directory Does Not Exist"`, body showing the actual path and a Yes/No prompt. If user clicks **Yes**, validation passes anyway and the settings are saved; if **No**, function returns `False`. Again, no wrapping or logging. |

- No exceptions are caught anywhere in this file. `_browse_vault_path()` calls `os.path.expanduser()`, `QFileDialog.getExistingDirectory()`, and `.text()` — none of these are wrapped in `try/except`. If any raise (e.g., user closes the dialog during an OS-level error), it **bubbles up** to the caller.
- `load_settings()` assumes `config_data` is a dict with nested `obsidian` key containing all four expected keys (`vault_path`, `folder`, `daily_notes`, `vault_context`). If any are missing, a `KeyError` would bubble up unhandled.

---

### `text_files.py` — `TextFilesTab` (Generic Text Files Framework)

**Responsibility:** Provide the generic UI framework for managing multiple named text files as configuration entries — likely prompts, templates, or user-editable config snippets. Each entry has a display label, primary storage path, and optional fallback/default path for restoring defaults when the primary is missing.

### API Surface

| Method | Input | Output |
|---|-------|--------|
| `__init__(self, items, editor_label, placeholder, parent=None)` | — | None |
| `_init_ui(self)` | None | None |
| `_on_item_changed(self, current, previous)` | — | None |
| `commit_active_editor(self)` | None | None |
| `load_settings(self, config_data: dict) -> None` | `config_data`: Dict | None |
| `restore_defaults(self) -> None` | None | None |
| `save_settings(self, config_data: dict) -> bool` | `config_data`: Dict | bool (always returns True) |

### Business Rules & Flow

1. **UI Initialization** — Render a horizontal splitter with a `QListWidget` on the left (listing all entries by label) and a monospace-text editor on the right for editing the currently selected entry's content.
2. **Item Selection Handling** (`_on_item_changed`): When switching from one item to another, the previous item's in-memory content is cached back into `loaded_contents`. The new item's path is looked up in `loaded_contents`; if found, that cached text is loaded into the editor; otherwise it starts empty. The editor is disabled when no item is selected and cleared on deselection.
3. **Setting Restoration** (`load_settings`): In-memory cache is blocked (no writes) while loading. For each entry, if the primary file exists, its content is loaded into memory; otherwise the fallback file is used; otherwise it remains empty. The first item in the list becomes selected after restoration.
4. **Default Restoration** (`restore_defaults`): Similar to `load_settings`, but always reads from the default/fallback path (ignoring existing primary files). Resets all entries to their default state.
5. **Saving Changes** (`save_settings`): The currently active editor's content is committed to memory first, then all cached contents are written back to their respective file paths on disk. Returns `True` unconditionally after the write loop completes.

### Key Business Rules

- **Cache-first persistence**: All edits go through an in-memory dictionary (`loaded_contents`) before being flushed to disk. This ensures atomicity — changes are never partially persisted.
- **Write-blocking during restore/defaults**: The cache is locked during `load_settings` and `restore_defaults`, preventing writes while the system is rehydrating state from files.
- **Graceful degradation**: If a file doesn't exist, the fallback path is tried; if that also fails, an empty string is stored as the entry's content.
- **No-op commit when nothing selected**: `commit_active_editor` safely does nothing if no item is active — no crash risk.

### Mutable State & Concurrency

| Variable | Type | Mutated? | Notes |
|---|---|---------|-------|
| `self.items` | list of tuples (passed to constructor) | No post-init change | Immutable after construction. |
| `self._block_cache` | bool | Yes | Toggled True/False in `_on_item_changed`, `load_settings`, `restore_defaults`. |
| `self.loaded_contents` | dict | Yes | Extensively mutated: assigned `{}`, `.clear()`, key-value writes across multiple methods. |
| `self.current_item` | QWidget or None | Yes | Set to current QListWidgetItem, cleared when selection changes. |
| `self.editor_label_text` | str | No post-init change | Assigned once in constructor. |
| `self.placeholder_text` | str | No post-init change | Assigned once in constructor. |

No explicit concurrency primitives (e.g., `sync.Mutex`, `threading.Lock`, asyncio locks, channels). The only implicit protection is Qt's single-threaded event loop for GUI operations, which is not an explicit synchronization mechanism in this code.

### External Communication & Errors

| Operation | Direction | Mechanism | Notes |
|---|---|---|-------|
| `os.path.exists(path)` | Disk read | OS filesystem stat | Synchronous; only checks existence, no data transfer. |
| `config.load_file(path)` | Disk read | File I/O via `eloquent_notes.config` | Path comes from Qt list item user-data. Errors are swallowed (no try/except in this file). |
| `config.save_file(path, content)` | Disk write | File I/O via `eloquent_notes.config` | Called once per item in `save_settings`. Errors are swallowed. |

**No network calls**, **no database operations** observed in this module. All I/O is filesystem-based through the `config` submodule.

### Error Handling Characterization

- **Errors are not wrapped, not sent as signals, and not logged.** File I/O failures surface as unhandled exceptions unless the Qt event loop catches them at a higher level.
- **No try/except blocks** in this file; all exceptions from `os.path.exists`, `config.load_file`, and `config.save_file` propagate up to callers uncaught within this module's scope.

---

### `prompts.py` — `PromptsTab` (Thin Facade)

**Responsibility:** Provide a first-class tab identity for prompt configuration within the existing generic text-files tab framework. No additional logic lives here beyond label differentiation; all structural behavior is delegated entirely to `TextFilesTab`.

### API Surface

| Method | Input | Output |
|---|-------|--------|
| `__init__(self, parent=None)` | `parent`: Optional QWidget | None (delegates to `TextFilesTab.__init__`) |

### Business Rules & Flow

- **Delegation Pattern**: `PromptsTab` is a thin subclass of `TextFilesTab`. It does not implement its own UI logic; instead, it delegates to the parent class by supplying specific configuration values:
  - `items=PROMPTS` — registers prompt definitions from `eloquent_notes.config_gui.constants`.
  - `editor_label="Prompt Content:"` — labels the editable text area for prompt input.
  - `placeholder="Select a prompt to edit..."` — guides user selection behavior.

### Mutable State & Concurrency

- **No directly observable mutable state.** This module defines a single class whose `__init__` forwards parameters to the parent constructor. No instance attributes, global variables, or changing struct fields are declared or modified within this file's scope. Any state mutations occur in the inherited parent class.
- **No concurrency mechanisms** (no locks, channels, no other concurrency primitives).

### External Communication & Errors

- **No direct external communication**: This file contains no network, disk, or database operations. Delegation for instantiation occurs via `super().__init__()` with specific arguments (`items=PROMPTS`, `editor_label`, `placeholder`, `parent`). Any I/O (e.g., reading prompt files) is handled by the parent class logic, which is not defined in this scope.
- **Dependency on imported constant**: The behavior depends entirely on `from eloquent_notes.config_gui.constants import PROMPTS`. If this constant is not defined or raises an error during instantiation, it will propagate up to the caller without interception in this file.

---

### `templates.py` — `TemplatesTab` (Thin Facade)

**Responsibility:** Provide a first-class tab identity for template management within the existing generic text-files tab framework. No additional logic lives here beyond label differentiation; all structural behavior is delegated entirely to `TextFilesTab`.

### API Surface

| Method | Input | Output |
|---|-------|--------|
| `__init__(self, parent=None)` | `parent`: Optional QWidget | None (delegates to `TextFilesTab.__init__`) |

### Business Rules & Flow

- **Delegation Pattern**: `TemplatesTab` is a thin subclass of `TextFilesTab`. It does not implement its own UI logic; instead, it delegates to the parent class by supplying specific configuration values:
  - `items=TEMPLATES` — registers template entries from `eloquent_notes.config_gui.constants`.
  - `editor_label="Template Content:"` — labels the editable text area for template input.
  - `placeholder="Select a template to edit..."` — guides user selection behavior.

### Mutable State & Concurrency

- **No detectable mutable state** within this file's scope. `TEMPLATES` is imported as a constant value (no mutation shown). No instance fields are modified after initialization in this file's scope.
- **No concurrency mechanisms**.

### External Communication & Errors

- **No direct file system operations**: This module does not contain any explicit calls to read from or write to disk within the provided scope.
- **No network communication** (no HTTP requests, socket usage, or URL parsing).
- **No database interaction** (no SQL queries, connection strings, or ORM calls).
- **Dependency on imported constant**: The behavior depends entirely on `from eloquent_notes.config_gui.constants import TEMPLATES`. If this constant is not defined or raises an error during instantiation, it will propagate up to the caller without interception.

---

### `__init__.py` — Package Entry Point & Re-export Namespace

**Responsibility:** Aggregate six distinct configuration-tab types into a single namespace so that callers can access them through one package rather than importing each sub-module individually. This is the entry point for the configuration-tab subsystem.

### API Surface (Re-exports)

| Name | Source Module | Notes |
|------|---------------|-------|
| `AITab` | `.ai` | Class — no method/property signatures visible from this file alone |
| `AudioTab` | `.audio` | Class — no method/property signatures visible from this file alone |
| `GeneralTab` | `.general` | Class — no method/property signatures visible from this file alone |
| `ObsidianTab` | `.obsidian` | Class — no method/property signatures visible from this file alone |
| `PromptsTab` | `.prompts` | Class — no method/property signatures visible from this file alone |
| `TemplatesTab` | `.templates` | Class — no method/property signatures visible from this file alone |

### Internal Constants

| Name | Value |
|------|-------|
| `__all__` | List of the 6 class names above, controlling module-level exports. |

### Algorithmic Flow

1. Import six tab classes from their respective sub-modules (`.ai`, `.audio`, `.general`, `.obsidian`, `.prompts`, `.templates`).
2. Register all six in `__all__` so they are importable and discoverable as public members of the package.

### State & Concurrency

- **No global variables or data structures** that are mutated. It only re-exports tab classes from submodules.
- **No concurrency mechanisms** (no locks, channels, or other synchronization primitives).

### Error Handling

- **Import-time behavior**: This module performs 6 submodule imports at import time. Each of those submodules may trigger side effects (lazy registration, hook setup, etc.) depending on their implementation. The `__init__.py` itself contains no direct I/O operations.
- **No error handling** is present. The imports are bare with no try/except blocks. If any submodule fails to import (missing file, syntax error in submodules, etc.), the exception propagates up uncaught and terminates the importing context.

---

## Summary of Data Flow & Error Patterns

| Pattern | Where | Mechanism |
|---------|-------|-----------|
| **Settings persistence** — read/write via shared dict | All tabs | `load_settings(config_data)` reads from caller's dict; `save_settings(config_data)` writes back. The caller owns the dict reference and is responsible for serialization (e.g., JSON, YAML). |
| **Validation on save** | `.ai`, `.general`, `.obsidian` | Returns `False` when validation fails (empty fields, invalid formats, user cancellation); caller decides whether to commit or discard changes. |
| **No atomicity in autostart** | `.general` | Logging config is updated first, then the autostart file is created/removed separately. If write fails after logging config was committed, dict holds inconsistent state. |
| **Cache-first persistence with graceful degradation** | `.text_files` (framework) | All edits go through in-memory cache before flush to disk; if primary file missing, fallback tried; if that fails, empty string stored. Errors swallowed — no try/except blocks. |
| **Signal-based async pipeline with silent state swallows** | `.ai` | Three distinct error-handling patterns coexist: silent swallow on empty URL, `QMessageBox.warning` + return False for invalid formats, signal propagation to status label in red (silent UI-only feedback). No exception handling anywhere. |
| **No external I/O except filesystem reads/writes via config submodule** | `.text_files`, `.general`, `.obsidian` | All disk operations go through `eloquent_notes.config` module's load/save functions; no direct file system calls in framework tabs. |