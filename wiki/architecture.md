# Eloquent Notes — Architecture Overview

```
wiki/architecture.md
```

---

## 1. System Boundaries & Interaction Model

**Eloquent Notes** is a Qt-based desktop application that captures microphone input as WAV bytes, transcribes audio via an Ollama-hosted LLM through a three-phase pipeline (transcription → rewriting → classification), and persists the output into an Obsidian vault with wikilinks and callouts.

### Core Boundary: Application Layer

```
┌─────────────────────────────────────────────────────────┐
│                    Eloquent Notes App                     │
│  Entry → main() │ Lifecycle → app.py │ Config → config.py │
│  Audio     → audio.py │ LLM    → llm.py │ Obsidian → obsidian.py │
│  Tray/IPC → ui.py │ Logging   → logging_utils.py         │
├─────────────────────────────────────────────────────────┤
│                  Configuration GUI Subsystem              │
│  Dialog (Qt) → config_gui/ │ Tabs: general, audio, ai, obsidian, text_files │
│  Background Threads → QThread subclasses                 │
├─────────────────────────────────────────────────────────┤
│                   External Dependencies                   │
│  Ollama API │ Obsidian Vault │ System Tray │ Microphone │ XDG │
└─────────────────────────────────────────────────────────┘
```

### Data Flow: Recording → Processing → Persist

```
User (Mic) ──► AudioRecorder (queue buffer) ──► WAV bytes
                                                      │
                                              play_beep() feedback tone
                                                      ▼
                                       app.py: _stop_recording_and_process()
                                                      │
                                          llm.py three-phase pipeline (daemon thread)
                                                      │
                                       Phase 1: transcribe_audio() → dict with 'empty' bool + text
                                       Phase 2: rewrite_transcription() → structured note prose (title + content)
                                       Phase 3: classify_transcription() → type, wikilinks, tags
                                                      │
                                          obsidian.py save_note()
                                                      │
                                              _save_daily / _save_standalone
                                                      ▼
                                           Obsidian vault (markdown + frontmatter)
```

### Configuration Flow

```
main.py ──► config_gui.dialog.ConfigurationDialog.accept()
                              │
              ┌──────────────┘
              ▼
config_gui/tabs/* load_settings(config_data)  ← populate from disk
config_gui/tabs/* save_settings(config_data)  → persist to YAML
         │
         ▼
config.py: load_config() / save_config()  (recursive merge, fallback defaults)
```

### IPC & Tray Communication

```
System tray icon (64×64 RGBA via Pillow) ──► QIcon ──► QSystemTrayIcon
    │                                         │
    ▼                                         ▼
_click_                                    _update_icon(state)
    │                                         │
    ▼                                         ▼
app.py: toggle_action()               app.py: _on_tray_activated(reason)
    │                                         │
    ▼                                         ▼
IPC socket "eloquent_notes_ipc" ──► _handle_ipc_connection()
    │
    ▼
_dispatch { toggle | reload | notify_running }
```

---

## 2. Module Responsibility Matrix

| Module | Path | Role |
|--------|------|------|
| **Entry Point** | `main.py` | CLI parsing, IPC dispatch, autostart registration |
| **Lifecycle Controller** | `app.py` | State machine (IDLE→RECORDING→PROCESSING→IDLE), tray/IPC orchestration, three-phase pipeline invocation |
| **Audio Capture** | `audio.py`, `config_gui/tabs/audio.py` | Mic → WAV queue buffer, lazy encoding, feedback beep synthesis |
| **Configuration Persistence** | `config.py`, `templates/`, `config_gui/` | YAML load/save with recursive merge, default fallbacks, path constants |
| **LLM Orchestration** | `llm.py` | Model preload, three-phase pipeline (transcribe → rewrite → classify), JSON response parsing with code-fence stripping |
| **Obsidian Integration** | `obsidian.py` | Vault topic scanning, wikilink injection, daily/standalone note saving, callout wrapping |
| **System Tray / IPC** | `ui.py`, implicit in `app.py` | Pillow icon generation, Qt QIcon conversion, local socket server on "eloquent_notes_ipc" |
| **Logging** | `logging_utils.py` | XDG-compliant log directory, console + rotating file handler setup |
| **Autostart** | `autostart.py` (re-exported) | `.desktop` file writing to `~/.config/autostart/` |
| **Configuration Dialog** | `config_gui/dialog.py` | Multi-tab PyQt6 dialog aggregating domain tabs, async background jobs via QThread |
| **Background Threads** | `OllamaModelLoader` (QThread subclass) | Async Ollama model fetch/validate; signals: `models_fetched`, `error_occurred` |

---

## 3. Key Architectural Patterns

### State Machine in app.py

```
IDLE ──► RECORDING ──► PROCESSING ──► IDLE
 │        │              │             │
 toggle  stop + process  signal       reload / tray event
 ```

### Lazy Encoding for Audio Capture

Audio bytes accumulate in a queue buffer; WAV encoding happens at `_stop_recording_and_process()`, preventing main-thread blocking during capture.

### Model Preload Pattern (llm.py)

`preload_model()` sends an empty chat request to warm model weights into VRAM before first real inference, reducing cold-start latency for the three-phase pipeline.

### Vault Context Building

`_build_vault_context()` scans Obsidian vault for known topics → returns formatted context string usable as WikiLink references in interpretation prompts. Enables LLM output to reference existing notes.

### Wikilink Injection (obsidian.py)

`_inject_wikilinks(text, wikilinks)` processes longer terms first with word boundaries to avoid substring collisions. `format_note_content()` wraps based on note type using `_CALLOUT_MAP`.

### Template Interpolation Pipeline

Templates are loaded as-is from filesystem; placeholders delimited by `{...}` substituted in document order via string replacement. No compilation or caching at runtime. Context map built from caller-supplied values with missing keys defaulting to empty strings.

---

## 4. Configuration Schema (`config.yaml`)

```yaml
obsidian:   # vault path, folder, daily notes flag, vault context
ai:         # Ollama URL, model name, context length, keep-alive durations, retry/timeout
audio:      # sample rate, channels, beep frequency/duration/enabled
logging:    # level, max file size (MB), backup count
```

### Path Constants (`config.py`)

| Constant | Description |
|----------|-------------|
| `CONFIG_DIR` | Base user config directory: `~/.config/eloquent-notes` |
| `CONFIG_PATH` | Absolute path to main YAML configuration within `CONFIG_DIR` |
| `PROMPTS_DIR`, `TEMPLATES_DIR` | Subdirectories under `CONFIG_DIR` for prompt templates and note templates |

---

## 5. Background Thread Infrastructure

`OllamaModelLoader` (QThread subclass) runs fetch-and-validate logic in worker thread:

- **Signal**: `models_fetched` — list of audio-capable model names
- **Signal**: `error_occurred` — error message string
- Connected to `AITab._fetch_models()` which tracks loader instances and updates UI state based on signal payloads.

---

## 6. Template Registry (`templates/`)

| Template | File | Placeholder Contract |
|----------|------|---------------------|
| `daily_append.md` | `eloquent_notes/templates/daily_append.md` | Appends to existing day's entry; omits frontmatter date/time metadata. Placeholders: `{time}`, `{title}`, `{text}` |
| `daily_new.md` | `eloquent_notes/templates/daily_new.md` | Full-featured template for initializing new daily dictation note with YAML frontmatter and structured body sections. Placeholders: `{tags}`, `{date}`, `{time}`, `{title}`, `{text}` |
| `standalone.md` | `eloquent_notes/templates/standalone.md` | Independent note documents detached from daily-entry lifecycle; suitable for ad-hoc notes, reminders. Placeholders: `{title}`, `{text}`, `{date}`, `{time}` (optional) |

---

## 7. Dependency Map

```
main.py ──► app.py │ config_gui/ │ autostart.py
app.py ──► audio.py │ llm.py │ obsidian.py │ ui.py │ logging_utils.py
config_gui/dialog.py ──► config_gui/tabs/* (general, audio, ai, obsidian, text_files)
config_gui/tabs/ai.py ──► OllamaModelLoader (QThread)
```

All modules are importable from the `eloquent_notes` package; CLI entry point re-exports autostart functionality for convenience.