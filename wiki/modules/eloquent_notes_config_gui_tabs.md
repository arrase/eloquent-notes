# Configuration GUI Tabs Module

## Overview

The `config_gui/tabs` module implements a tabbed configuration dialog system for **Eloquent Notes**, providing independent PyQt6 widget interfaces for managing application settings across multiple domains: AI pipeline integration, audio capture, general startup/logging behavior, Obsidian vault connectivity, and editable text file management (prompts/templates). Each tab encapsulates its own UI hierarchy, state persistence logic, and resource lifecycle management. All tabs conform to the `ConfigTab` abstract contract defined in `base.py`, ensuring uniform serialization through a configuration dictionary interface.

## Data Flow

Each tab maintains an internal widget tree constructed during `_init_ui`. On initialization or restore, the application invokes `load_settings(config_data: dict)`, which reads key-value pairs from a standardized configuration dictionary and populates corresponding UI widgets. User modifications are captured by `save_settings(config_data: dict) → bool`, which validates inputs, formats values (e.g., keep-alive duration regex normalization), and writes resolved state back into the provided dictionary before returning success status. Tabs implement `cleanup()` to release background threads during disposal, preventing orphaned processes.

---

## Base Configuration Tab Infrastructure

### File: `base.py`

**ConfigTab** — Abstract base class enforcing a common interface for all configuration tabs within the dialog system. Subclasses must override `load_settings`, `save_settings`, and optionally `restore_defaults`. The base provides default implementations of `cleanup()` (no-op) and raises `NotImplementedError` on abstract methods to prevent incomplete overrides.

| Method | Responsibility |
|--------|---------------|
| `load_settings(config_data)` | Populates UI widgets from the provided configuration dictionary; must be overridden by subclasses |
| `save_settings(config_data) → bool` | Collects current widget state, returns `True` only when all persisted data is valid |
| `restore_defaults()` | Resets interface to factory state without raising exceptions |
| `cleanup()` | Releases background threads and resources prior to destruction; no-op by default |

---

## Text Files Configuration Tab (Shared Foundation)

### File: `text_files.py`

**TextFilesTab** — GUI configuration tab providing a list-view interface for editing and managing multiple text files. Implements the `ConfigTab` contract, serving as the base class for both prompt and template management tabs. Subclasses extend this interface by initializing with predefined item lists and specialized editor labels.

---

## Prompt and Template Management Tabs (Text Files Extensions)

### File: `prompts.py`

**PromptsTab** — Extends `TextFilesTab` to manage prompt content editing, maintaining a predefined set of items and associated editor labels for each configurable prompt entry. Inheriting the list-view structure from `TextFilesTab`, this subclass adds domain-specific initialization logic while preserving the base tab's persistence contract.

### File: `templates.py`

**TemplatesTab** — Extends `TextFilesTab` to manage template-specific settings, initializing with a predefined set of items and specialized UI labels tailored for template content editing. Follows the same inheritance pattern as `PromptsTab`, leveraging the shared list-view infrastructure while maintaining independent state management.

---

## AI Pipeline Configuration Tab

### File: `ai.py`

**AITab** — PyQt6 configuration tab widget responsible for managing Ollama connection details and AI pipeline settings. Constructs an internal hierarchy including form layouts, text inputs, spin boxes, and group boxes during `_init_ui`. Implements background model loading via `OllamaModelLoader`, with signal handlers tracking fetch status and populating a combo box with available audio models.

| Method | Responsibility |
|--------|---------------|
| `_init_ui()` | Builds the internal widget hierarchy: form layouts, text inputs, spin boxes, group boxes for AI settings interface |
| `_toggle_context_default()` | Disables/enables the context length spin box based on whether default context length is selected |
| `_fetch_models()` | Initiates background model loading; constructs `OllamaModelLoader` instance and connects signal handlers for status updates |
| `_on_loader_finished()` | Removes finished loader instances from tracking sets; re-enables refresh button if that specific loader was active during fetch |
| `_on_models_fetched()` | Populates the model combo box with available audio models retrieved by the loader; updates status label to reflect successful loading |
| `_on_models_fetch_failed()` | Updates status label with connection failure message when Ollama model fetch encounters an error |
| `load_settings(config_data)` | Reads AI-specific configuration values from dictionary and populates UI widgets on initialization or restore |
| `save_settings(config_data) → bool` | Validates user inputs; formats keep-alive durations via regex pattern matching; writes resolved AI configuration back into dictionary before returning success status |
| `cleanup()` | Asynchronously cancels all active background loaders and clears internal state to prevent orphaned processes during tab disposal or destruction |

---

## Audio Capture Configuration Tab

### File: `audio.py`

**AudioTab** — PyQt6-based configuration tab widget responsible for managing audio capture settings, including sample rate configuration and feedback beep toggles. Implements the standard `ConfigTab` contract with dedicated persistence methods.

| Method | Responsibility |
|--------|---------------|
| `load_settings(config_data)` | Reads a configuration dictionary to populate internal UI widgets with previously saved audio parameters |
| `save_settings(config_data) → bool` | Collects current values from all audio UI widgets and writes them into the provided configuration dictionary before returning success status |

---

## General Application Settings Tab

### File: `general.py`

**GeneralTab** — PyQt6-based configuration tab class providing a user interface for managing application startup options and logging settings. Constructs a vertical layout containing QGroupBox controls during `_init_ui`, including autostart checkboxes, logging level/size/backup spinboxes, and a button to open log files.

| Method | Responsibility |
|--------|---------------|
| `_init_ui()` | Constructs the vertical layout with QGroupBox controls for autostart checkboxes, logging level/size/backup spinboxes, and log file viewer button |
| `_view_log_file()` | Opens the background daemon log file in the system editor if it exists; displays an informational message indicating that dictations must be run first if no log file is present |
| `load_settings(config_data)` | Populates UI widgets with values from the provided configuration dictionary and checks for existing autostart entries on disk |
| `save_settings(config_data) → bool` | Updates the logging sub-dictionary in the config data structure; manages creation or deletion of the desktop autostart entry based on user input |

---

## Obsidian Integration Configuration Tab

### File: `obsidian.py`

**ObsidianTab** — PyQt configuration tab widget managing Obsidian integration settings, including vault path selection, target folder specification, daily notes appending behavior, and vault context options for dictation output. Constructs a Qt widget layout during `_init_ui` containing a group box with line edits, check boxes, and buttons for configuring all Obsidian-related parameters.

| Method | Responsibility |
|--------|---------------|
| `_init_ui(self)` | Constructs the Qt widget layout: group box with line edits, check boxes, and buttons to configure vault directory, note output folder, daily-note appending, and wikilink suggestions |
| `_browse_vault_path(self)` | Opens a system file dialog prompting user selection of an existing Obsidian vault directory on disk |
| `load_settings(config_data: dict) → None` | Reads stored configuration from `config_data["obsidian"]` dictionary and populates all form widgets with their previously saved values |
| `save_settings(config_data: dict) → bool` | Collects current widget state into `config_data["obsidian"]`; validates vault path existence on disk (with optional confirmation dialog); returns boolean success indicator |

---

## Module Summary

The module organizes configuration management through a hierarchical class structure: `ConfigTab` in `base.py` defines the abstract contract, `TextFilesTab` in `text_files.py` provides shared list-view infrastructure for text-based settings, and specialized tabs (`prompts.py`, `templates.py`) extend this base. Domain-specific tabs (`ai.py`, `audio.py`, `general.py`, `obsidian.py`) implement independent UI hierarchies while conforming to the same persistence interface. All tabs serialize state through configuration dictionaries, ensuring consistent data flow between the application's settings system and each tab's widget tree.