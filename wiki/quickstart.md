---

# Quickstart — Eloquent Notes Architecture

## System Boundary

**Eloquent Notes** is a persistent system-tray dictation tool. It captures spoken audio from the default microphone, transforms it into structured Markdown notes via a three-phase Ollama LLM pipeline (transcription → rewriting → classification), and saves the resulting note to an Obsidian vault at `~/Obsidian/Dictations`. The application runs as a PyQt6 `QObject`-based daemon with IPC-based single-instance messaging.

## Module Interaction Map

```
eloquent_notes.app            ── owns recording state, tray icon, signals, IPC server
        │
        ▼
  ┌──────────────┐    ┌────────────────┐   ┌──────────────────────┐
  │ audio         │    │ llm           │   │ obsidian             │
  │ AudioRecorder │◀──▶│ transcribe     │──▶│ save_note            │
  │ play_beep     │    │ rewrite       │   │ scan_vault_topics    │
  └──────────────┘    │ classify      │   └──────────────────────┘
                      └────────────────┘        │
                                                ▼
                                         format_note_content
```

- **`app`** is the central controller. It owns recording state, spawns background threads for audio capture and LLM processing, manages a system tray icon, and exposes IPC via `QLocalServer`.
- **`audio`** provides microphones as WAV bytes (lazy, compiled on first access) and short sine-wave feedback beeps with anti-click envelopes. All processing is in-memory; no external disk/network I/O during recording.
- **`llm`** bridges three gaps: speech-to-text, prose polishing, and automatic metadata extraction. Every public function communicates via HTTP POST to `{ollama_url}/api/chat`. Shared retry/validation loop: if the response is not valid JSON, lacks required keys, or contains code-fence markdown wrappers, the system logs the failure and re-prompts up to `max_retries` times before raising an error.
- **`obsidian`** converts structured dictation output into Obsidian Markdown notes. Handles daily append vs standalone save modes, wikilink injection from vault scans, callout wrapping by note type, and frontmatter tag merging.

### Thread Coordination

The application controller spawns `threading.Thread` instances for recording and processing. Results flow back to the GUI thread via custom `pyqtSignal`. Direct attribute access (`self.state`, `self.recorder`) from worker threads occurs without explicit synchronization protection; PyQt signals/slots provide implicit synchronization only for passing results back to the main GUI thread.

## Configuration Initialization Flow

1. CLI parses arguments (`install-autostart`, `config`, `toggle`, default).
2. If no running daemon is reachable via IPC socket, a new process launches; if one exists, it receives `"toggle"` or `"notify_running"`.
3. On startup: `config.init_config_dir()` seeds user directories with bundled defaults; `load_config()` merges default YAML with user overrides (recursive merge).
4. Logging setup writes to XDG STATE_HOME via `logging_utils.setup_logging()`.
5. If `config` subcommand → launch `ConfigurationDialog`; if no argument or `toggle` → IPC connect.

## Configuration Dialog — Tab Architecture

The configuration dialog (`ConfigurationDialog`) aggregates settings from category-specific tabs. Settings are persisted to a YAML configuration file on disk. The subsystem is organized around an abstract contract (`ConfigTab`) that every tab class implements, ensuring uniform lifecycle behavior across AI model pipeline, audio capture, general/logging, Obsidian integration, prompts, and templates domains.

| Tab | Responsibility |
|-----|---------------|
| `PromptsTab` / `TemplatesTab` | Display/edit text files (prompts and templates) via a vertical splitter with file list + monospace editor |
| `AITab` | Manages Ollama connection URL, selected model, context length, keep-alive durations, retry count, request timeouts. Tracks background `OllamaModelLoader` lifecycle via signal/slot connections |
| `AudioTab` | Microphone/audio capture parameters: sample rate, channel count, beep feedback toggles and levels |
| `GeneralTab` | Autostart behavior (login auto-launch) and logging configuration (verbosity level, file size cap, backup count). Provides action to open the background daemon log file in system editor |

## Error Handling Patterns

Across subsystems, error handling follows a few consistent patterns:

- **LLM module**: HTTP failures propagate as uncaught `HTTPError`; malformed JSON / missing keys retry up to `max_retries + 1` then re-raise; code fence wrapping is stripped silently via `_strip_code_fences(text)` before parsing.
- **Audio module**: No explicit error handling exists in this module. Errors from external I/O (missing microphone device, sounddevice backend unavailable) propagate as unhandled exceptions to the caller. The `.stop()` method does not validate whether the stream is already stopped/closed; calling it twice attempts to stop a `None` stream, which is effectively a no-op rather than an error.
- **Obsidian module**: File open/write failures are not verified — no exception handling around disk I/O. Regex compilation or substitution errors propagate as exceptions without try/except guards.
- **Config tabs**: `_init_ui()` calls have no try/except; `load_settings()` has no fallback for missing keys (a single `KeyError` crashes); `save_settings()` returns hardcoded `True`. Only unhandled exceptions during widget construction or dict access crash the UI thread.

## Data Flow Summary

```
User Action (tray click / IPC "toggle")
    │
    ▼
┌─────────────┐     ┌──────────┐
│  EloquentApp │────▶│ AudioRecorder │   (background thread)
│  (QObject)   │◀────│            │   → WAV bytes in memory
└─────────────┘     └──────────┘
    │                         │
    ▼          ┌──────────────┘
┌─────────────────────────────────────┐
│  _process_audio (daemon thread)      │
│  ├─ Phase 1: transcribe_audio       │
│  ├─ Phase 2: rewrite_transcription  │
│  └─ Phase 3: classify_transcription │
└─────────────────────────────────────┘
    │
    ▼
Vault context scan (Obsidian vault read) → combined prompt → LLM call
    │
    ▼
Note assembly via template substitution → save_note() write to disk
    │
    ▼
Signal emission: "success" / "empty" / "error" → GUI thread notification
```