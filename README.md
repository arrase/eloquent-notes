# Eloquent Notes for Linux

Eloquent Notes is a system tray utility for Linux inspired by [Google Eloquent](https://developers.google.com/edge/eloquent) that operates silently in the background. It allows you to record quick dictations, automatically cleans and formats them using a local Gemma 4 model (via Ollama), and writes the resulting structured Markdown notes directly to your Obsidian vault.

## Key Features

- **System Tray Centric UX:** Control recording easily by clicking the system tray icon (click to start, click again to stop and process).
- **Offline & Private:** Transcribes and refines audio locally on your machine using Gemma 4 via Ollama.
- **Dynamic Icons:** Status indicators (Idle, Recording, Processing) are rendered dynamically in memory.
- **Obsidian Integration:** Appends to daily notes or creates new individual notes with tags and frontmatter metadata.
- **Customizable Prompts:** Custom Markdown system prompts loaded from your user config directory.

---

## Usage

Start the background service by running:
```bash
eloquent-notes
```

### How to use:
1. **Idle:** A gray microphone icon is shown in the system tray.
2. **Start Dictation:** Click the tray icon. A beep plays, and the icon turns **red** to indicate it is recording.
3. **Stop & Process:** Click the tray icon again. A beep plays, the icon turns **orange**, and the app starts processing the audio via the local Ollama API.
4. **Finished:**
   - **Success**: Once processed, the cleaned transcription is saved to your Obsidian vault, a desktop notification is displayed, and the icon returns to **gray**.
   - **Empty Audio**: If the audio contains only silence or background noise, a "Dictation Empty" notification is displayed, and no note is created. The icon returns to **gray**.

---

## Prerequisites

1. **Ollama & Gemma 4 Model:**
   Make sure you have Ollama running locally and have pulled the optimized `gemma4:12b-it-qat` model:
   ```bash
   ollama pull gemma4:12b-it-qat
   ```

2. **System Dependencies:**
   Install PortAudio (required for audio capture and beep playback) and libnotify (required for desktop notifications):
   ```bash
   # On Ubuntu/Debian/Pop!_OS:
   sudo apt install libportaudio2 libnotify-bin
   ```

---

## Installation

### Option A: Install from GitHub (Recommended)
You can install the utility directly from GitHub using `pipx` or `uv`:
```bash
# Using uv
uv tool install git+https://github.com/arrase/eloquent-notes.git

# Or using pipx
pipx install git+https://github.com/arrase/eloquent-notes.git
```

### Option B: Local Installation (For Developers)
If you want to modify the source code or run in development mode:
```bash
# Clone the repository and navigate inside
git clone https://github.com/arrase/eloquent-notes.git
cd eloquent-notes

# Create virtual environment and install in editable mode
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## Configuration

Upon the first execution, Eloquent Notes will automatically initialize a configuration directory at `~/.config/eloquent-notes/`.

### 1. `config.yaml`
Edit `~/.config/eloquent-notes/config.yaml` to specify your Obsidian vault path:
```yaml
obsidian:
  vault_path: "~/Documents/Obsidian/MyVault"
  folder: "Inbox/Dictations"     # Target folder inside the vault
  daily_notes: true            # If true, appends to YYYY-MM-DD.md files

ai:
  ollama_url: "http://localhost:11434"
  model: "gemma4:12b-it-qat"
  context_length: 10000        # Context length limit (null or not set defaults to model max)
  keep_alive: "0"             # Time to keep model loaded after note generation (e.g. "5m", "10m", or "0" to unload immediately)
  preload_keep_alive: "5m"     # Time to keep model weights loaded in VRAM during recording to reduce note generation time

audio:
  sample_rate: 16000           # Audio sample rate (16kHz is ideal for Gemma 4)
  channels: 1                  # 1 channel (mono)
  temp_file: "/tmp/eloquent_temp.wav"
  beep_frequency: 440          # Sound beep frequency (Hz)
  beep_duration: 0.1           # Beep duration (seconds)
```

### 2. Custom System and User Prompts
You can edit the system and user prompts used to clean up and structure your notes:
- **System Prompt**: `~/.config/eloquent-notes/prompts/system_prompt.md`
- **User Prompt**: `~/.config/eloquent-notes/prompts/user_prompt.md`

---

## Autostart on Boot

To run Eloquent Notes automatically when logging in, execute:
```bash
eloquent-notes install-autostart
```
This generates a desktop autostart entry at `~/.config/autostart/eloquent-notes.desktop`.
