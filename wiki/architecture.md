# Eloquent Notes — Global Architecture Overview

## System Boundaries

Eloquent Notes is a voice-dictation note-taking system that bridges three external concerns: Obsidian vaults, Qt-based configuration management, and Markdown template rendering. The public surface area exposes exactly three subsystems:

| Subsystem | Module Path | Responsibility |
|---|---|---|
| Vault & Dictation Pipeline | `eloquent_notes.obsidian` | Vault filesystem scanning, wikilink injection, dictation-to-note persistence (standalone or daily-aggregated) |
| System Tray Icon Generation | `eloquent_notes.ui` | System-tray icon generation for application state visualization (idle / recording / processing) |
| Configuration Dialog & Tabs | `eloquent_notes.config_gui` | Qt configuration dialog aggregating six domain tabs, Ollama model loader running in a QThread, diff-based YAML persistence |

A fourth concern exists as pure format contract: **`eloquent_notes.templates`**, which provides Markdown templates consumed by external rendering engines (Go `text/template`, Jinja2, or equivalent placeholder substitution). This module contains no executable code, no mutable state, and no error handling paths.

## Module Interaction Map

### Vault Pipeline → Dictation Persistence

The primary persistence path flows through `obsidian.scan_vault_topics()` into topic basenames, then into `save_note()`. The entry point delegates to either `_save_daily` or `_save_standalone` based on the `daily_notes` flag. `_update_frontmatter_tags()` merges new tags into existing frontmatter YAML in-memory; `_inject_wikilinks()` wraps vault topic basenames matching content terms with `[[wikilink]]` syntax.

### Configuration GUI → Vault Pipeline

The configuration subsystem exposes a shared dictionary (`config_data`) across six tab widgets. The caller owns this reference without copy semantics. When the user saves, each tab's `save_settings()` is called for validation; if any return `False`, the dialog rejects without writing. On full success, `diff_configs(default, current)` computes an override set and writes only differing keys to YAML.

### Configuration GUI → Ollama Loader

`OllamaModelLoader(QThread)` runs in a dedicated QThread to discover audio-capable models from `/api/tags`. It communicates results back via PyQt6 signals: `models_fetched(list)` and `error_occurred(str)`. The AITab consumes these signals to populate or clear its model combo box.

### Configuration GUI → Templates

Templates are resolved externally by whichever runtime reads the files (`daily_append.md`, `daily_new.md`, `standalone.md`). Placeholders (`{time}`, `{title}`, `{text}`, `{tags}`, `{date}`) are bare strings awaiting resolution. No template engine is defined within the project itself.

## Concurrency Model

| Concern | Mechanism | Notes |
|---|---|---|
| Ollama loader | QThread with signals | Communicates via `models_fetched(list)` and `error_occurred(str)`. No locks or mutexes; signal emission handles thread-safe delivery. |
| Vault pipeline | Standard library I/O only | Concurrent callers see results undefined by this code; no synchronization exists. |
| Configuration tabs | Caller-owned shared dict | No copy semantics; all six domain tabs read/write the same `config_data` reference. |

## Error Handling Summary

Across subsystems, four distinct patterns exist:

1. **Swallowed with user notification** — `restore_defaults` and `save_settings_from_ui` wrap entire pipelines in bare `try/except Exception`; on failure shows a critical message and returns normally (or sentinel `False`).
2. **Per-tab validation gate** — All tabs implement `save_settings()` returning a boolean; the caller decides commit/reject.
3. **Silent swallow on per-model failure** — Per-model exceptions in the Ollama loader are caught and ignored; only top-level or connection errors surface as `error_occurred`.
4. **No wrapping, no sentinels** — File I/O failures in obsidian and general tabs propagate uncaught up through the call chain unless Qt event loop catches them at a higher level.

## Side Effects Summary

| Function | Operation | Details |
|---|---|---|
| `scan_vault_topics` | Read (`os.walk`) | Reads filenames only; returns sorted list capped at 200 entries |
| `_save_daily`, `_save_standalone` | Write (`open("w")`) | Creates/overwrites note files; no merge for standalone mode |
| `_update_frontmatter_tags` | None (string-only) | Parses frontmatter in-memory; mutates global `yaml.SafeDumper.ignore_aliases` on every call |
| `_browse_vault_path` | Read + optional write | Calls `QFileDialog.getExistingDirectory()`. If current text is non-empty, calls `os.path.expanduser()` + `os.path.exists()`. Non-existent path falls back to `~/` silently. Empty vault path triggers a warning returning `False`. Path that does not exist on disk prompts via `QMessageBox.question()` with Yes/No; if **Yes**, validation passes anyway. |

## Styling

A single module-level constant (`eloquent_notes.config_gui.styles.QSS_STYLESHEET`) holds the raw Qt Style Sheet string defining visual appearance for every widget type in the configuration GUI: QDialog, QWidget, QTabWidget, QTabBar, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QListWidget, QPushButton, QGroupBox, QCheckBox, QScrollBar. Catppuccin Mocha palette (#1e1e2e background, #89b4fa accent). No runtime behavior beyond string literal definition; no imports or function calls.

## Notes on Unhandled Paths

- If frontmatter parsing fails (malformed YAML, encoding issues), exceptions propagate uncaught from `_update_frontmatter_tags`.
- If `default` or `current` is not iterable/dict-like at top level in `diff_configs`, `.items()` raises a Python exception (`TypeError`, `AttributeError`). No try/except blocks; all exceptions propagate to callers.
- If a template engine fails to resolve any placeholder, the template file contains no mechanism to catch or report the failure.
- Non-atomic autostart update in `general.py`: logging config updated first, then `.desktop` file created/removed separately. If write fails after logging config was committed, dict holds inconsistent state.