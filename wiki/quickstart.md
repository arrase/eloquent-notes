# Eloquent Notes — Quickstart & Architecture

## What It Does

Eloquent Notes is a Qt/PyQt6 desktop app that records microphone input, transcribes it via an Ollama-hosted LLM through a three-phase pipeline (transcribe → rewrite → classify), and saves the result as an Obsidian note with wikilinks and callouts.

---

## System Boundaries

### What's In Scope
- **Recording** — `audio.py` captures mic input as WAV bytes; `config_gui/tabs/audio.py` exposes sample rate, channels, beep settings.
- **LLM pipeline** — `llm.py` orchestrates three-phase Ollama calls (transcription → rewriting → classification); model preloading and retry logic are handled in-process.
- **Obsidian export** — `obsidian.py` scans vault topics for wikilink context, formats notes with callouts, saves to daily or standalone files based on config.
- **Configuration** — `config.py` loads/saves YAML; defaults bundled in package, user overrides merged at runtime. GUI tabs persist via `config_gui/`.
- **Lifecycle & IPC** — `app.py` manages state machine (IDLE → RECORDING → PROCESSING), system tray icon (Pillow-generated), and a local TCP socket (`eloquent_notes_ipc`) for toggle/reload/notify commands.
- **Autostart** — `autostart.py` writes a `.desktop` file to `~/.config/autostart/`.

### What's Out of Scope
- No network server, no cloud sync, no plugin system. Everything runs locally on the host machine. Ollama must be reachable at the configured URL (default: `http://localhost:11434`). Obsidian vault path is absolute and validated at save time.

---

## Module Interaction Map

```
main.py ──► EloquentApp(app.py)
              │
         ┌────┴──────────────────┐
         ▼                       ▼
  config_gui/               audio.py / ui.py
  (ConfigurationDialog)     (recorder + tray icon)
         │                       │
         ▼                       ▼
    config.py                 llm.py ──► obsidian.py
       │                         │           │
       ▼                         ▼           ▼
   templates/              QThread loader  save_note()
```

### Core Data Flow

```
Microphone → AudioRecorder (queue buffer) → WAV bytes
                                                    │
Microphone click / tray icon                       ▼
  └──► EloquentApp.toggle_action() ──► _start_recording()
                                        │
                              recorder running in daemon thread
                                        │
                           Microphone release / stop command
                                        │
                              _stop_recording_and_process()
                                        │
                              llm.py: transcribe → rewrite → classify
                                        │
                              obsidian.py: save_note (daily/standalone)
                                        │
                              processing_completed signal → IDLE state
```

### IPC Protocol

Local TCP socket `eloquent_notes_ipc`:
- **`toggle`** — start/stop recording
- **`reload`** — reload config from disk, reinitialize logging
- **`notify_running`** — send status notification to tray

---

## Entry Point & CLI

```python
# main.py dispatches three modes:
#   1) IPC toggle handler (tray icon click → socket message)
#   2) Configuration GUI dialog (ConfigurationDialog from config_gui.dialog)
#   3) Daemon launch (run() → QApplication event loop)
```

**Autostart**: `install_autostart()` writes `.desktop` to `~/.config/autostart/`, executable resolved via `shutil.which()`.

---

## Configuration Schema (`~/.config/eloquent-notes/config.yaml`)

| Section | Keys | Purpose |
|---------|------|---------|
| `obsidian` | vault, folder, daily_notes, context | Vault path and note organization |
| `ai` | url, model, context_length, keep_alive, retry, timeout | Ollama connection + pipeline tuning |
| `audio` | sample_rate, channels, beep_freq, beep_dur, beep_enabled | Capture settings |
| `logging` | level, max_mb, backup_count | Log rotation config |

**Init flow**: `config.load_config()` reads bundled defaults → merges with user YAML. `save_config()` writes resolved dict back via YAML serialization.

---

## Key Module Responsibilities

### `app.py` — EloquentApp
Central controller. State machine: **IDLE ↔ RECORDING ↔ PROCESSING**. Manages tray icon (Pillow 64×64 RGBA, color-coded state), IPC server, and three-phase pipeline orchestration. Emits `processing_completed(status, detail)` on finish/error.

### `audio.py` — AudioRecorder
Queue-based buffer with lazy encoding. `play_beep()` synthesizes sine-wave tone with fade envelopes for click-free feedback.

### `llm.py` — Three-Phase Pipeline
All three phases use identical invocation pattern: system prompt + user prompt + retry prompt templates + context length + keep-alive duration + timeout. Response parsing strips markdown code fences before JSON extraction. Model preloading sends empty chat request to warm VRAM.

### `obsidian.py` — Vault Exporter
- `scan_vault_topics()` recursively finds wikilink candidates, skips date-named files
- `_inject_wikilinks()` processes longer terms first to avoid substring collisions
- `format_note_content()` wraps in callout syntax (task/idea types) or leaves plain
- `save_note()` routes to daily-aggregated or standalone file based on config flag

### `logging_utils.py` — Logger Setup
XDG-compliant log directory, console handler + optional rotating file handler.

---

## Configuration GUI (`config_gui/`)

**Contract**: Every tab implements `ConfigTab`:
- `load_settings(config_data)` — populate UI from loaded config
- `save_settings(config_data)` → bool — collect state, validate (e.g., regex-normalize keep-alive), write back
- `restore_defaults()` — reset to factory state
- `cleanup()` — release threads/resources before destruction

**Tabs**:
| Tab | File | Notes |
|-----|------|-------|
| General | `config_gui/tabs/general.py` | Autostart checkbox, logging spinboxes, log viewer button |
| Audio | `config_gui/tabs/audio.py` | Sample rate, beep settings |
| AI | `config_gui/tabs/ai.py` | Ollama URL/model/keep-alive; runs `OllamaModelLoader` in QThread for model fetch with signal emission (`models_fetched`, `error_occurred`) |
| Obsidian | `config_gui/tabs/obsidian.py` | Vault browse dialog, daily notes toggle |
| Prompts/Templates | `prompts.py`, `templates.py` | Extend `TextFilesTab`; list-view for editing multiple files |

**Dialog**: `ConfigurationDialog` wires all tabs, handles accept/reject → save/cancel with thread cleanup.

---

## Development Notes

- **Threading model**: Recorder and processing run in daemon threads; main UI stays on Qt event loop. Never block the GUI during LLM calls.
- **Race condition guard**: Prompt files are preloaded into active config before `_start_recording()` to avoid main/worker read/write conflicts.
- **Tray icon**: Generated via Pillow at 64×64 RGBA, converted to `QIcon` by saving as PNG then loading into `QPixmap`. Three states: red (error), orange (recording/busy), gray (idle).
- **Template registry**: Static Markdown/YAML files under `templates/`; no runtime compilation. Interpolation substitutes `{...}` placeholders in document order.
- **Autostart**: Uses `shutil.which()` to resolve executable path; permissions set to 0o644.