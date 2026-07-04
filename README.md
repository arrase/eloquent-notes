# Eloquent Notes for Linux

Eloquent Notes is a lightweight, system-tray-centric utility for Linux inspired by [Google Eloquent](https://developers.google.com/edge/eloquent) that runs silently in the background. It allows you to record quick dictations, automatically cleans and structures them using a local **Gemma 4** model (via Ollama), and writes the resulting notes directly to your Obsidian vault.

---

## ✨ Features

- **System Tray Centric UX:** Control recording easily by clicking the system tray icon (click to start, click again to stop and process).
- **Context Menu Actions:** Right-click the system tray icon to reveal a menu with options to:
  - **Start/Stop Recording**
  - **Reload Configuration** (reloads settings and prompts on-the-fly without restarting the application)
  - **Quit**
- **CLI & Daemon Decoupling:** The CLI command (`eloquent-notes toggle`) is lightweight and decoupled from the heavy graphical interface (PyQt6). It uses a local Unix socket to immediately signal the running daemon to toggle recording.
- **Offline & Private:** Transcribes and refines audio locally on your machine using Gemma 4 via Ollama.
- **Dynamic Icons:** Status indicators are rendered dynamically in memory:
  - 🔘 **Idle (Gray):** A gray circle with a white microphone icon.
  - 🔴 **Recording (Red):** A red circle with a white recording dot.
  - 🟠 **Processing (Orange):** An orange circle with a white hourglass.
- **Obsidian Integration:** Appends notes to daily journals or creates new individual files inside your vault, complete with tags and frontmatter metadata.
- **Customizable Prompts:** Edit custom Markdown system and user prompts loaded directly from your user config directory.
- **Custom Note Templates:** You can customize the Markdown formatting of the generated notes, including frontmatter and headers.

---

## 📋 Prerequisites

1. **Ollama & Gemma 4 Model:**
   Ensure you have Ollama running locally and have pulled a Gemma 4 model (the default model configured is `gemma4:12b-it-qat`):
   ```bash
   ollama pull gemma4:12b-it-qat
   ```

2. **System Dependencies:**
   Install PortAudio (required for audio capture and beep playback) and a notification server (PyQt6 uses DBus/System notification services to display desktop alerts):
   ```bash
   # On Ubuntu/Debian/Pop!_OS:
   sudo apt install libportaudio2
   ```

---

## 🚀 Installation

### Option A: Install using `pipx` or `uv` (Recommended)
You can install the utility directly from GitHub:
```bash
# Using uv
uv tool install git+https://github.com/arrase/eloquent-notes.git

# Or using pipx
pipx install git+https://github.com/arrase/eloquent-notes.git
```

### Option B: Local Installation (For Development)
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

## ⚙️ Configuration

Upon the first execution, Eloquent Notes will automatically initialize a configuration directory at `~/.config/eloquent-notes/`.

### 1. `config.yaml`
Edit `~/.config/eloquent-notes/config.yaml` to specify your Obsidian vault path and adjust system parameters. Below is the default configuration:

```yaml
obsidian:
  vault_path: "~/Obsidian"     # Absolute or user-relative path to your Obsidian Vault
  folder: "Dictations"         # Target folder inside the vault where notes will be saved
  daily_notes: true            # If true, appends dictations to daily note files (YYYY-MM-DD.md)

ai:
  ollama_url: "http://localhost:11434"
  model: "gemma4:12b-it-qat"
  context_length: 10000        # Context length limit (null defaults to model maximum)
  keep_alive: "0"              # Time to keep model loaded in VRAM after note generation (e.g. "5m", "10m", or "0" to unload immediately)
  preload_keep_alive: "5m"     # Time to keep model weights loaded in VRAM during recording to minimize note generation cold-start
  max_retries: 3               # Number of times to retry LLM execution if the output is not valid JSON

audio:
  sample_rate: 16000           # Audio sample rate (16kHz is ideal for Gemma 4)
  channels: 1                  # Mono channel recording
  beep_frequency: 440          # Audio cue beep frequency (Hz)
  beep_duration: 0.1           # Beep duration (seconds)
  beep_enabled: true           # Enable/disable audio cues (beeps)
```

### 2. Custom Prompts
You can edit the system, user, and retry prompts used to clean up and structure your notes:
- **System Prompt:** `~/.config/eloquent-notes/prompts/system_prompt.md` (Instructs the model on how to format, structure, clean filler words, and output JSON)
- **User Prompt:** `~/.config/eloquent-notes/prompts/user_prompt.md` (Sends execution context for the specific audio file)
- **Retry Prompt:** `~/.config/eloquent-notes/prompts/retry_prompt.md` (Sends feedback to the model to correct its output if it fails to generate valid JSON)

### 3. Custom Note Templates
You can customize the Markdown formatting of the generated notes, including frontmatter and headers. Eloquent Notes provides three template files in `~/.config/eloquent-notes/templates/`:
- **`standalone.md`:** Used when `daily_notes: false` (creates an individual file per dictation).
- **`daily_new.md`:** Used when `daily_notes: true` and a new daily note is being created.
- **`daily_append.md`:** Used when `daily_notes: true` and the daily note already exists (useful for skipping frontmatter on subsequent entries).

You can use the following placeholders in these templates, which will be automatically replaced when saving the note:
- `{text}`: The cleaned text generated by the AI model.
- `{date}`: The current date (e.g., `2026-07-04`).
- `{time}`: The current time (e.g., `00:45:45`).

---

## 🎮 Usage

### 🔄 1. Setup Autostart on Boot
To ensure Eloquent Notes runs in the background automatically when you log in (allowing keyboard shortcuts to work instantly), execute:
```bash
eloquent-notes install-autostart
```
This generates a desktop autostart entry at `~/.config/autostart/eloquent-notes.desktop`.

*If you want to start the background service manually for the first time without logging out, run:*
```bash
eloquent-notes &
```

### ⌨️ 2. Global Keyboard Shortcut (Recommended)
Instead of clicking the system tray icon, you can toggle recording from anywhere (even inside fullscreen apps) using a global keyboard shortcut. Eloquent Notes exposes a toggle command:
```bash
eloquent-notes toggle
```
*(You can also use the shorthand: `eloquent-notes -t` or `eloquent-notes --toggle`)*

To bind this to a keyboard shortcut in your Linux desktop environment:

#### GNOME (Ubuntu, Debian, Pop!_OS, Fedora)
1. Go to **Settings** -> **Keyboard** -> **Keyboard Shortcuts** -> **View and Customise Shortcuts**.
2. Scroll to the bottom and select **Custom Shortcuts**.
3. Click the **+** button (or **Add Shortcut**) and enter:
   - **Name:** `Eloquent Notes Toggle`
   - **Command:** `eloquent-notes toggle`
   - **Shortcut:** Press your preferred keys (e.g., `Ctrl+Alt+N`)
4. Click **Add**.

#### KDE Plasma
1. Go to **System Settings** -> **Shortcuts** -> **Custom Shortcuts**.
2. Select **Edit** -> **New** -> **Global Shortcut** -> **Command/URL**.
3. Name it `Eloquent Notes Toggle`.
4. In the **Trigger** tab, record your shortcut.
5. In the **Action** tab, set the command to `eloquent-notes toggle`.
6. Click **Apply**.

#### i3 / Sway
Add the following keybinding to your config file (usually `~/.config/i3/config` or `~/.config/sway/config`):
```text
bindsym $mod+Ctrl+n exec --no-startup-id eloquent-notes toggle
```

### 🔘 3. Interaction Flow
1. **Idle State:** The gray microphone icon is shown in the system tray.
2. **Start Dictation:** Click the tray icon, trigger your custom global shortcut, or run `eloquent-notes toggle`. A beep plays, and the icon turns **red** to indicate it is recording.
   * *Note: The model starts preloading into VRAM in the background during recording to speed up processing.*
3. **Stop & Process:** Click the tray icon, trigger the shortcut, or run `eloquent-notes toggle` again. A beep plays, the icon turns **orange**, and the application starts processing the audio via the local Ollama API.
4. **Completion:**
   * **Success:** The cleaned transcription is saved to your Obsidian vault, a desktop notification is displayed, and the icon returns to **gray**.
   * **Empty Audio:** If the audio contains only silence or background noise, a "Dictation Empty" notification is displayed, and no note is created. The icon returns to **gray**.

---

## 🏗️ Architectural Overview

Eloquent Notes is built with a highly responsive, asynchronous, and memory-efficient architecture:

```mermaid
graph TD
    CLI[CLI: eloquent-notes toggle] -->|QLocalSocket / IPC| A[PyQt6 System Tray Event Loop]
    Tray[Left Click / Tray Menu] --> A
    A --> B{Recording State?}
    B -->|IDLE| C[Start Recording]
    B -->|RECORDING| D[Stop & Process]
    
    C -->|Background Thread| E[Preload Gemma 4 in Ollama]
    C -->|sounddevice| F[Capture Mic Input to Queue]
    
    D -->|sounddevice| G[Stop Capture & Convert to WAV in Memory]
    D -->|Background Thread| H[Send Base64 Audio to Ollama]
    
    H -->|Cleaned JSON Response| I{Empty Note?}
    I -->|No| J[Save to Obsidian Vault]
    I -->|Yes| K[Show Notification]
    
    J --> L[Show Success Notification]
    K --> M[Restore Gray Icon]
    L --> M
```

### Key Technical Details
* **CLI & GUI Decoupling:** The entry point (`eloquent-notes`) only loads PyQt's lightweight core components (`QCoreApplication` and `QLocalSocket`) when communicating with the running instance. If the daemon is already running, it sends an IPC command and exits immediately, avoiding loading any windows or graphical elements. If it is not running, it replaces the current process with the daemon (`eloquent_notes.app`) via `os.execv`.
* **In-Memory Audio Processing:** Audio is captured directly from your microphone using `sounddevice` and loaded into an in-memory queue. When recording stops, it is processed into 16-bit PCM WAV bytes in-memory (using `io.BytesIO`). No temporary audio files are written to the disk, maximizing privacy, speed, and disk lifespan.
* **Non-Blocking UI Threads:** Both the model preloading and the Ollama API request processing are offloaded to background threads. This ensures that the PyQt6 system tray UI loop remains entirely responsive without stuttering or freezing.
* **Dynamic Icon Generation:** Custom state icons are drawn dynamically in-memory using Pillow (`PIL`) and converted to `QIcon` objects at runtime. No external image assets are required.
* **Structured Model Output:** The transcription is sent to Ollama's `/api/chat` using structured JSON schema format instructions, guaranteeing robust parsing of transcription flags (`empty` and `text`).
