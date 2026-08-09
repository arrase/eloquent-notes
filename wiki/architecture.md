# Architecture — Eloquent Notes

## System Boundaries

`eloquent_notes` is a Python package that implements a desktop application for hands-free dictation into an Obsidian-style vault. The system has three user-facing entry points:

- **CLI / IPC** (`eloquent_notes.main`) — remote daemon control via Unix-domain socket and local command-line interface
- **GUI Configuration Dialog** (`eloquent_notes.config_gui`) — settings management window
- **System Tray Icon** (`eloquent_notes.app`) — tray-driven recording state machine

All three entry points converge on a single application state managed by `EloquentApp`. The package is composed of eight submodules, each with clearly separated concerns:

| Module | Responsibility | Entry Points |
|---|---|---|
| `eloquent_notes.main` | CLI parsing, IPC protocol handling, daemon lifecycle | `run_cli`, `send_ipc_command`, `main` |
| `eloquent_notes.app` | Application state machine, tray setup, recording orchestration | `EloquentApp.__init__`, `run`, `toggle_action`, `exit_app` |
| `eloquent_notes.audio` | Microphone capture (WAV bytes), beep playback | `AudioRecorder.start/stop/wav_bytes`, `play_beep` |
| `eloquent_notes.llm` | Three-phase audio-to-structured-note pipeline via Ollama HTTP API | `transcribe_audio`, `rewrite_transcription`, `classify_transcription`, `preload_model` |
| `eloquent_notes.obsidian` | Vault scanning, wikilink injection, note formatting and persistence | `scan_vault_topics`, `_inject_wikilinks`, `format_note_content`, `save_note` |
| `eloquent_notes.config` | Configuration file management (load/save/merge) | `init_config_dir`, `load_config`, `save_config` |
| `eloquent_notes.config_gui` | Settings dialog with six tab widgets, model discovery loader | `ConfigurationDialog`, `OllamaModelLoader` |
| `eloquent_notes.ui` | System-tray icon generation (PIL → Qt QIcon) | `create_icon_image`, `get_qicon` |

---

## Data Flow

```
┌────────────────────── CLI ──────────────────────┐
│ run_cli() ──► parse_args()                      │
│ send_ipc_command(command=...) ← QLocalSocket    │
│ EloquentApp.toggle_action()                    │
└────────────────────── GUI ──────────────────────┘
  ConfigurationDialog.save_settings_from_ui()
  OllamaModelLoader.run()

                     │ IPC / Config I/O
                     ▼
┌──────────────────────────────────────────────────┐
│ EloquentApp (state machine: IDLE → STARTING_     │
│  RECORDING → RECORDING → PROCESSING)              │
│   ├─ AudioRecorder.start() / stop()              │
│   │    └─ sounddevice.InputStream                │
│   ├─ LLM pipeline: transcribe → rewrite →        │
│   │    classify                                  │
│   │    └─ requests.post to Ollama `/api/chat`    │
│   ├─ Obsidian vault write-back                   │
│   └─ System tray notifications                   │
└──────────────────────────────────────────────────┘

  config.load_config() ◄──► config.save_config()
```

The CLI entry point (`main`) is the primary orchestrator. It dispatches to `run_cli` which either: (1) sends an IPC command over a Unix socket if the daemon is already running, (2) spawns a new daemon process via subprocess when the toggle fails, or (3) opens the configuration dialog for initial setup.

---

## Module Interaction Map

```
eloquent_notes.main ──► eloquent_notes.app    (IPC commands: toggle/reload/notify_running)
                      │
                      ▼
              EloquentApp._on_tray_activated()
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
     AudioRecorder  LLM pipeline Obsidian vault write-back
          │           │           │
          ▼           ▼           ▼
   sounddevice    requests.post  save_note → format_note_content
                  /api/chat      → scan_vault_topics → _inject_wikilinks
```

### Configuration Flow

`eloquent_notes.config_gui.ConfigurationDialog` initializes `self.config_data` via `config.load_config()` in its constructor. All six tab widgets read from and write to this shared dictionary on load/save cycles. On save, the dialog computes a diff between factory defaults and current state, then persists only overrides through `config.save_config`.

### LLM Pipeline Flow

Three sequential HTTP POST calls are made against a local Ollama instance:
1. **`transcribe_audio`** — raw WAV bytes → text transcription (system + user prompts)
2. **`rewrite_transcription`** — transcription text → structured title and content fields
3. **`classify_transcription`** — transcription + vault context → type label, wikilinks, tags

A shared retry mechanism (`_execute_ollama_json_request`) validates JSON responses; malformed JSON or missing required keys trigger retries up to `max_retries + 1` total attempts. HTTP errors are not retried and propagate immediately.

---

## Error Propagation Summary

| Module | Pattern |
|---|---|
| `config` | Atomic write-to-temp + rename for persistence; no silent swallowing except in `load_config` which catches invalid YAML with a clear error message |
| `llm` | Malformed JSON retries up to budget; HTTP errors propagate immediately without retry |
| `audio` | Cascading close on stop; no try/except around core operations — hardware/driver errors propagate directly |
| `obsidian` | Atomic rename for all writes; only YAML parse failures are explicitly swallowed (return original content) |
| `config_gui` | Dialog catches disk I/O and YAML errors with QMessageBox critical dialogs; individual tab validation failures short-circuit save |
| `ui` | No error handling — PIL/Qt exceptions propagate to caller |

---

## Thread Model

- The main thread runs the Qt event loop and owns all GUI widget state
- Background daemon threads handle LLM inference (`_processing_thread`) via `pyqtSignal` emission for cross-thread safety
- `OllamaModelLoader` inherits from `QThread` and communicates completion via signals; inner POST failures are individually swallowed while outer failures emit an error signal
- `AudioRecorder` uses a threading lock around state transitions (start/stop) but relies on CPython GIL and internal Queue synchronization for chunk enqueue during recording

---

## Configuration Lifecycle

1. **First run** — `init_config_dir()` creates three directories (`config/`, `prompts/`, `templates/`) and copies bundled defaults
2. **Load** — `load_config()` reads user YAML from disk, validates as dict, recursively merges with default YAML
3. **Persist** — `save_config()` serializes merged data to YAML using write-to-temp + atomic rename pattern

Paths: config directory is `~/.config/eloquent-notes`, configuration file is `{CONFIG_DIR}/config.yaml`. Prompt files are in a subdirectory under the same base; template files follow similar structure.