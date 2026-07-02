# Eloquent Notes for Linux

Eloquent Notes is a system tray utility for Linux (inspired by Google Eloquent) that operates silently in the background. It allows you to record quick dictations, automatically cleans and formats them using a local Gemma 4 model (via Ollama), and writes the resulting structured Markdown notes directly to your Obsidian vault.

## Key Features

- **System Tray Centric UX:** Control recording easily by clicking the system tray icon (click to start, click again to stop and process).
- **Offline & Private:** Transcribes and refines audio locally on your machine using Gemma 4 via Ollama.
- **Dynamic Icons:** Status indicators (Idle, Recording, Processing) are rendered dynamically in memory.
- **Obsidian Integration:** Appends to daily notes or creates new individual notes with tags and frontmatter metadata.
- **Customizable Prompts:** Custom Jinja2/Markdown system prompts loaded from your user config directory.
- **Modern Standards:** Pure PEP 621 compliance (`pyproject.toml`) and zero inline imports.

---

## Prerequisites

1. **Ollama & Gemma 4 Model:**
   Make sure you have Ollama running locally and have pulled the optimized `gemma4:12b-it-qat` model:
   ```bash
   ollama pull gemma4:12b-it-qat
   ```

2. **System Dependencies:**
   Install PortAudio (for audio capture), libnotify (for desktop notifications), and AppIndicator libraries (for system tray support):
   ```bash
   # On Ubuntu/Debian/Pop!_OS:
   sudo apt install libportaudio2 libnotify-bin gir1.2-appindicator3-0.1 gir1.2-ayatanaappindicator3-0.1
   ```

---

## Installation

### Option A: Local Installation (from clone)
For local development, it is highly recommended to create a Python virtual environment with system site packages enabled. This allows the application to inherit precompiled system PyGObject bindings for the GTK/AppIndicator system tray:
```bash
# Clone the repository and navigate inside
git clone https://github.com/yourusername/eloquent-notes.git
cd eloquent-notes

# Create virtual environment and install in editable mode
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e .
```

### Option B: Global Installation (via pipx or uv)
Once the repository is pushed to GitHub, you can install it directly without cloning:
```bash
# Using uv
uv tool install git+https://github.com/yourusername/eloquent-notes.git

# Or using pipx
pipx install git+https://github.com/yourusername/eloquent-notes.git
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

audio:
  sample_rate: 16000           # Audio sample rate (16kHz is ideal for Gemma 4)
  channels: 1                  # 1 channel (mono)
  temp_file: "/tmp/eloquent_temp.wav"
  beep_frequency: 440          # Sound beep frequency (Hz)
  beep_duration: 0.1           # Beep duration (seconds)
```

### 2. Custom System Prompts
You can edit the prompt used by Gemma 4 to clean up and structure your notes at:
`~/.config/eloquent-notes/prompts/system_prompt.md`

This file is fully compatible with **Jinja2** templates, allowing dynamic template rendering if needed.

---

## Usage

Start the background service by running:
```bash
linux-eloquent
```

### How to use:
1. **Idle:** A gray microphone icon is shown in the system tray.
2. **Start Dictation:** Click the tray icon. A high beep will play, a system notification will appear, and the icon will turn **red** to indicate it is recording.
3. **Stop & Process:** Click the tray icon again. A beep plays, the icon turns **orange**, and the app starts sending the audio to Gemma 4 via the local Ollama API.
4. **Finished:** Once processed, the cleaned transcription is appended/saved into your Obsidian vault, a desktop notification is displayed, and the icon returns to **gray**.

---

## Autostart on Boot

To run Eloquent Notes automatically when logging in, execute:
```bash
linux-eloquent install-autostart
```
This generates a desktop autostart entry at `~/.config/autostart/linux-eloquent.desktop`.
