# Configuration

Eloquent Notes can be configured visually through the built-in **PyQt6 Configuration GUI** or by editing the YAML configuration and Markdown prompt files directly.

All configuration lives under `~/.config/eloquent-notes/` (or `$XDG_CONFIG_HOME/eloquent-notes/`). On first run, the packaged defaults are copied there; existing files are never overwritten.

```
~/.config/eloquent-notes/
├── config.yaml
└── prompts/
    ├── transcription_system.md
    ├── transcription_user.md
    ├── rewriting_system.md
    ├── rewriting_user.md
    ├── classification_system.md
    ├── classification_user.md
    └── retry_prompt.md
```

User values in `config.yaml` are merged over the packaged defaults, so missing keys fall back to the defaults. A section that is not a mapping is rejected with an error notification.

---

## Built-in PyQt6 Configuration GUI

Open the dialog with:

```bash
eloquent-notes config
```

Alternatively, choose **Configuration** in the tray menu or click **Settings** in the notes window.

![Configuration GUI (Dark)](screenshots/configuration-dark.png#only-dark)
![Configuration GUI (Light)](screenshots/configuration-light.png#only-light)

The dialog has six tabs plus **Restore Defaults**, **Cancel** and **Save** buttons. Saving writes the prompt files and the settings that differ from the defaults to `config.yaml`, then reloads the running daemon. The dialog follows the desktop's light or dark theme and updates live when the system palette changes.

### Tab Breakdown

#### 1. General
* **Start automatically on login**: installs or removes `~/.config/autostart/eloquent-notes.desktop`.
* **Logging Level**: `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`.
* **Max Log File Size**: size in MB before rotation (default `5`).
* **Backup Count**: rotated log files to keep (default `3`).
* **View Log File**: opens `app.log`.

#### 2. Notes
* **Notes Folder**: folder where each note is saved as a Markdown file (default `~/Documents/Eloquent Notes`). It may point inside an Obsidian vault; files without Eloquent Notes frontmatter are ignored. See [Notes & Search](notes.md).

#### 3. Appearance
* **Timeline Columns**: number of columns in the notes timeline grid (default `2`).
* **Note Type Colors**: badge color for each note type (`note`, `task`, `idea`, `reminder`, `question`, `decision`), chosen with a color picker and saved under `notes.type_colors`.

#### 4. AI Settings
**Ollama & AI Pipeline Settings**
* **Ollama URL**: endpoint of the Ollama server (default `http://localhost:11434`).
* **AI Model (Audio)**: multimodal model used for all three pipeline phases (default `gemma4:e4b-it-qat`). **Refresh** queries Ollama and lists the installed models that report the `audio` capability.
* **Context Length**: `num_ctx` for requests (default `8192`). **Use default context length** stores `null` so Ollama uses the model's maximum.
* **Keep Alive Time**: how long the model stays loaded after a note is generated (default `"0"`, unload immediately).
* **Preload Keep Alive**: how long the model stays loaded while recording and between phases (default `"5m"`).
* **Max Retries**: retries when a response fails JSON validation (default `3`).
* **Preload Timeout** / **Request Timeout**: seconds allowed for model loading (default `180`) and for each pipeline request (default `300`).
* **Output Language**: language for titles, rewritten prose and tags (default `English`; editable).

**Semantic Search**
* **Embedding Model**: Ollama embedding model used for search (default `embeddinggemma-2:latest`). **Refresh** also lists installed models that report the `embedding` capability.
* **Keep Alive Time**: how long the embedding model (`search.keep_alive`) stays loaded between searches (default `"5m"`).
* **Minimum Similarity**: cosine similarity below which search results are hidden (default `0.6`).

#### 5. Audio
* **Sample Rate**: recording rate in Hz (default `16000`).
* **Audio Channels**: `1` (mono) or `2` (stereo).
* **Capture Duration**: maximum recording length in seconds before recording stops automatically (default `30`, the Gemma 4 audio limit).
* **Show floating countdown HUD**: overlay with the remaining time while recording; clicking it stops the recording.
* **Play beep on recording start and stop**: audio cues, with **Beep Frequency** (default `440` Hz) and **Beep Duration** (default `0.1` s).

#### 6. Prompts
Editor for the Markdown prompts of each pipeline phase and the retry prompt (see below).

![Prompts Editor (Dark)](screenshots/configuration-prompts-dark.png#only-dark)
![Prompts Editor (Light)](screenshots/configuration-prompts-light.png#only-light)

---

## Manual YAML Configuration Reference (`config.yaml`)

Default configuration:

```yaml
notes:
  folder: "~/Documents/Eloquent Notes"   # One Markdown file per voice note.
  columns: 2                             # Number of columns in the timeline grid.
  type_colors:
    note: "#64748B"
    task: "#3B76B6"
    idea: "#C27821"
    reminder: "#C94A4D"
    question: "#8258B8"
    decision: "#2A8567"

ai:
  ollama_url: "http://localhost:11434"
  model: "gemma4:e4b-it-qat"
  output_language: "English" # Output language for rewritten notes, titles, and tags.
  context_length: 8192 # If null or not set, the maximum allowed by the model is used.
  keep_alive: "0"       # Time to keep model loaded after note generation (e.g. "5m", "10m", or "0" to unload immediately).
  preload_keep_alive: "5m" # Time to keep model weights loaded in VRAM during recording to reduce note generation time.
  max_retries: 3        # Number of times to retry LLM execution if the output is not valid JSON.
  preload_timeout: 180  # Timeout in seconds for preloading the model weights.
  request_timeout: 300  # Timeout in seconds for note generation requests.

search:
  embedding_model: "embeddinggemma-2:latest"
  keep_alive: "5m"      # Time to keep the embedding model loaded between searches.
  min_similarity: 0.6   # Hide search results below this cosine similarity.

audio:
  sample_rate: 16000
  channels: 1
  capture_duration: 30
  recording_hud_enabled: true
  beep_frequency: 440
  beep_duration: 0.1
  beep_enabled: true

logging:
  level: "INFO"
  max_mb: 5
  backup_count: 3
```

After editing the file by hand, choose **Reload Configuration** in the tray menu. Changes apply from the next recording or search; a dictation in progress keeps the settings and prompts that were active when it started.

---

## Custom Markdown Prompts

Prompts reside in `~/.config/eloquent-notes/prompts/`:

| File Name | Purpose | Placeholders |
| :--- | :--- | :--- |
| `transcription_system.md` | System instructions for Phase 1 (audio transcription). | — |
| `transcription_user.md` | User prompt sent with the audio. | — |
| `rewriting_system.md` | System instructions for Phase 2 (title and note prose). | — |
| `rewriting_user.md` | User prompt for Phase 2. | `{transcription}`, `{language_instruction}` |
| `classification_system.md` | System instructions for Phase 3 (type and tags). | — |
| `classification_user.md` | User prompt for Phase 3. | `{transcription}` (the rewritten content), `{language_instruction}` |
| `retry_prompt.md` | Correction sent when a response is not valid JSON. | — |

Unknown placeholders are left untouched. The JSON output shapes are fixed by the schemas in `llm.py` (see [Three-Phase AI Pipeline](pipeline.md)); prompts change the model's behavior, not the fields it returns.
