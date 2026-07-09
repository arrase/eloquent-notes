# `eloquent_notes.config_gui` — Module Architecture

## 1. Responsibility & Data Flow

The **config_gui** subsystem provides the full-stack configuration management surface for Eloquent Notes: a multi-tab PyQt6 dialog (`ConfigurationDialog`) that aggregates domain-specific tab widgets, persists state to an application-wide configuration dictionary, and dispatches asynchronous background jobs (Ollama model fetching) via `QThread` subclasses.

### Data Flow Diagram

```
User Interaction ──► ConfigurationDialog.accept() / reject()
    │                         │
    ▼                         ▼
┌──────────────┐      ┌──────────────────┐
│  Per-Tab Tab │      │   save_settings  │
│  Widget Tree │◄────►│ config_data:dict │
└──────────────┘      └──────────────────┘
    │                         │
    ▼                         ▼
┌──────────────┐      ┌──────────────────┐
│  cleanup()   │      │ diff_configs     │
│ stop threads │      │ (optional)       │
└──────────────┘      └──────────────────┘
```

1. **Initialize** — `ConfigurationDialog` is constructed; each tab subclass (`GeneralTab`, `AudioTab`, `AITab`, `ObsidianTab`, `TextFilesTab`/`PromptsTab`/`TemplatesTab`) runs `_init_ui()` to build its internal widget hierarchy.
2. **Load State** — On dialog open or restore, `load_settings_to_ui(config_data)` is invoked; the base class delegates to each tab's `load_settings(config_data)`, which reads key-value pairs from a standardized configuration dictionary and populates corresponding UI widgets.
3. **User Modification** — Widgets accept input; tabs capture state via their own `save_settings()`.
4. **Persist** — On dialog acceptance (`accept()`), `save_settings_from_ui` aggregates per-tab states, validates inputs (e.g., regex-normalizes keep-alive durations in the AI tab), and writes resolved values back into the config dictionary before returning success status.
5. **Cleanup** — `cleanup_tabs` iterates all tabs to release resources; the dialog's `reject()` path cancels pending changes and stops background threads without persisting state.

### Constants & Styles

- **`constants.py`** exports `PROMPTS` (display-name → file-path + default-source string mappings for transcription, rewriting, classification, retry) and `TEMPLATES` (label → path + source mappings for note templates).
- **`styles.py`** — `QSS_STYLESHEET`: a raw Qt Style Sheets string covering all dialog controls (`QDialog`, `QWidget`, `QTabWidget`, `QLineEdit`, `QPushButton`, `QListWidget`, `QGroupBox`, `QScrollBar`).

---

## 2. Base Infrastructure

### `base.py` — `ConfigTab` (Abstract Contract)

```python
class ConfigTab(QWidget):
    """Enforces a common interface for all configuration tabs."""

    def load_settings(self, config_data: dict) -> None: ...
    def save_settings(self, config_data: dict) -> bool: ...
    def restore_defaults(self) -> None: ...
    def cleanup(self) -> None: pass  # no-op default
```

- **`load_settings(config_data)`** — Populates UI widgets from the provided configuration dictionary; overridden by every tab subclass.
- **`save_settings(config_data)` → bool** — Collects current widget state, validates inputs (e.g., regex pattern matching on keep-alive durations in `AITab`), writes resolved values into `config_data`, returns `True` only when all persisted data is valid.
- **`restore_defaults()`** — Resets interface to factory state without raising exceptions.
- **`cleanup()`** — Releases background threads and resources prior to destruction; no-op by default, overridden in tabs running async jobs (`AITab`).

---

## 3. Tab Implementations

### 3.1 General Application Settings — `general.py`

| Class | File | Responsibility |
|-------|------|---------------|
| `GeneralTab` | `config_gui/tabs/general.py` | Manages startup options and logging settings. |

**Widget Hierarchy**: Vertical layout containing `QGroupBox` controls for:
- Autostart checkboxes (desktop entry creation/deletion)
- Logging level, size, backup spinboxes
- Log file viewer button (`_view_log_file`)

**Behavior**:
- `_init_ui()` — Constructs the vertical layout.
- `_view_log_file()` — Opens the background daemon log file in the system editor if it exists; otherwise displays an informational message indicating dictations must run first.
- `load_settings(config_data)` — Populates UI widgets from `config_data` and checks for existing autostart entries on disk.
- `save_settings(config_data)` → bool — Updates `config_data["logging"]`; manages creation/deletion of the desktop autostart entry based on user input.

---

### 3.2 Audio Capture — `audio.py`

| Class | File | Responsibility |
|-------|------|---------------|
| `AudioTab` | `config_gui/tabs/audio.py` | Manages audio capture settings (sample rate, feedback beep). |

**Behavior**:
- `load_settings(config_data)` — Reads from the config dictionary and populates internal UI widgets.
- `save_settings(config_data)` → bool — Collects current values from all audio UI widgets and writes them into `config_data` before returning success status.
- Implements the standard `ConfigTab` contract with dedicated persistence methods.

---

### 3.3 AI Pipeline Integration — `ai.py`

| Class | File | Responsibility |
|-------|------|---------------|
| `AITab` | `config_gui/tabs/ai.py` | Manages Ollama connection details and AI pipeline settings; runs background model loading via `OllamaModelLoader`. |

**Widget Hierarchy**: Form layouts, text inputs, spin boxes, group boxes for AI settings.

**Methods**:
- `_init_ui()` — Builds the internal widget hierarchy: form layouts, text inputs, spin boxes, group boxes for AI settings interface.
- `_toggle_context_default()` — Disables/enables the context length spin box based on whether default context length is selected.
- `_fetch_models()` — Constructs `OllamaModelLoader` instance; connects signal handlers (`models_fetched`, `error_occurred`) to update UI state.
- `_on_loader_finished()` — Removes finished loader instances from tracking sets; re-enables refresh button if that specific loader was active during fetch.
- `_on_models_fetched()` — Populates the model combo box with available audio models; updates status label.
- `_on_models_fetch_failed()` — Updates status label with connection failure message when Ollama model fetch encounters an error.
- `load_settings(config_data)` — Reads AI-specific configuration values from dictionary and populates UI widgets on initialization or restore.
- `save_settings(config_data)` → bool — Validates user inputs; formats keep-alive durations via regex pattern matching; writes resolved AI configuration back into dictionary before returning success status.
- `cleanup()` — Asynchronously cancels all active background loaders and clears internal state to prevent orphaned processes during tab disposal or destruction.

---

### 3.4 Obsidian Integration — `obsidian.py`

| Class | File | Responsibility |
|-------|------|---------------|
| `ObsidianTab` | `config_gui/tabs/obsidian.py` | Manages Obsidian integration settings (vault path, target folder, daily notes appending, wikilink suggestions). |

**Widget Hierarchy**: Group box with line edits, check boxes, and buttons.

**Methods**:
- `_init_ui(self)` — Constructs the Qt widget layout: group box with line edits, check boxes, and buttons to configure vault directory, note output folder, daily-note appending, and wikilink suggestions.
- `_browse_vault_path(self)` — Opens a system file dialog prompting user selection of an existing Obsidian vault directory on disk.
- `load_settings(config_data: dict) → None` — Reads stored configuration from `config_data["obsidian"]` dictionary and populates all form widgets with their previously saved values.
- `save_settings(config_data: dict) → bool` — Collects current widget state into `config_data["obsidian"]`; validates vault path existence on disk (with optional confirmation dialog); returns boolean success indicator.

---

### 3.5 Text File Management — `text_files.py`, `prompts.py`, `templates.py`

#### Shared Base: `TextFilesTab`

| Class | File | Responsibility |
|-------|------|---------------|
| `TextFilesTab` | `config_gui/tabs/text_files.py` | Base class for prompt and template tabs; provides a list-view interface for editing/managing multiple text files. |

**Behavior**: Implements the `ConfigTab` contract, serving as the base class for both prompt and template management tabs. Subclasses extend this interface by initializing with predefined item lists and specialized editor labels.

#### Prompt & Template Extensions

| Class | File | Responsibility |
|-------|------|---------------|
| `PromptsTab` | `config_gui/tabs/prompts.py` | Manages prompt content editing; maintains predefined items + associated editor labels per configurable prompt entry. |
| `TemplatesTab` | `config_gui/tabs/templates.py` | Manages template-specific settings; initializes with predefined items and specialized UI labels for template content editing. |

**Inheritance Pattern**: Both `PromptsTab` and `TemplatesTab` extend `TextFilesTab`, inheriting the list-view structure while adding domain-specific initialization logic. Persistence contract remains delegated to the base class.

---

## 4. Orchestration Layer

### `dialog.py` — `ConfigurationDialog` (Main GUI Dialog)

| Method | Responsibility |
|--------|---------------|
| `__init__(self)` | Constructs and wires all tab instances; registers signal/slot connections for accept/reject/cleanup lifecycle. |
| `load_settings_to_ui(config_data: dict)` | Populates all tab widget states by reading values from a previously loaded configuration dictionary. Delegates to each tab's `load_settings()`. |
| `restore_defaults()` | Resets the dialog UI to factory defaults after prompting the user for confirmation via a modal message box (`QMessageBox.question`). |
| `save_settings_from_ui(config_data: dict) → bool` | Validates and persists all current widget states back to disk by calculating overrides against the default configuration file. Returns boolean success indicator. |
| `cleanup_tabs()` | Iterates through all tab widgets to release resources before the dialog window closes; invokes each tab's `cleanup()`. |
| `reject(self)` | Cancels any pending changes and ensures background threads are stopped when the dialog is dismissed without saving. |
| `accept(self)` | Triggers the save process if validation passes and guarantees thread cleanup upon successful acceptance of the dialog. |

---

## 5. Background Thread Infrastructure

### `loader.py` — `OllamaModelLoader` (`QThread` Subclass)

**Responsibility**: Executes asynchronous background jobs to fetch and validate Ollama models for audio pipeline integration.

| Signal | Emitted When | Payload |
|--------|-------------|---------|
| `models_fetched` | Loading process finishes without interruption | List of audio-capable model names (str) |
| `error_occurred` | Exception occurs during API interaction or processing | Error message string (str) |

**Behavior**: Subclasses `QThread`; runs fetch-and-validate logic in the worker thread; emits signals on completion/failure; connected to `AITab._fetch_models()` which tracks loader instances and updates UI state based on signal payloads.