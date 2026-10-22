# Installation & Setup

This guide walks you through setting up system prerequisites, installing the local AI models with Ollama, installing Eloquent Notes, and configuring desktop autostart.

---

## System Requirements

Eloquent Notes is engineered for Linux desktop environments. Ensure your system meets the following prerequisites before proceeding:

| Component | Minimum Requirement | Notes |
| :--- | :--- | :--- |
| **Operating System** | Linux (Ubuntu, Debian, Fedora, Arch, openSUSE, etc.) | Uses XDG directory standards and X11/Wayland system tray. |
| **Python** | Python 3.11+ | Standard Python runtime environment. |
| **Audio Subsystem** | PortAudio (`libportaudio2`) | Required by `sounddevice` for microphone capture and sine tone playback. |
| **Notifications** | DBus Notification Server | Required for desktop status popups (`dunst`, `mako`, GNOME/KDE built-in). |
| **AI Runtime** | Ollama | Local inference service running on `http://localhost:11434`. |

### Installing System Dependencies

Install PortAudio and DBus notification utilities using your distribution package manager:

=== "Ubuntu / Debian"

    ```bash
    sudo apt update
    sudo apt install -y python3-pip libportaudio2 libnotify-bin
    ```

=== "Fedora"

    ```bash
    sudo dnf install -y python3-pip portaudio libnotify
    ```

=== "Arch Linux"

    ```bash
    sudo pacman -S python-pip portaudio libnotify
    ```

=== "openSUSE"

    ```bash
    sudo zypper install python3-pip portaudio libnotify-tools
    ```

---

## Local Ollama Setup & Model Download

Eloquent Notes relies on **Ollama** to run two models locally: the multimodal Gemma 4 model for transcription, rewriting and classification, and an EmbeddingGemma model for semantic search.

### 1. Install Ollama

If Ollama is not already installed, run the official Linux installer script:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Verify that the Ollama service is running:

```bash
systemctl status ollama
```

### 2. Download the Models

Download the quantized Gemma 4 model (`gemma4:e4b-it-qat`) and the embedding model (`embeddinggemma-2:latest`):

```bash
ollama pull gemma4:e4b-it-qat
ollama pull embeddinggemma-2:latest
```

*(Note: You can use other audio-capable or embedding models by updating `ai.model` / `search.embedding_model` in `config.yaml` or in the **AI Settings** tab of the GUI. The embedding model is only needed for search; recording works without it.)*

---

## Installation Methods

Eloquent Notes can be installed either as an isolated application tool using `uv` / `pipx` (recommended) or in editable mode for local development.

### Method 1: Using `uv` (Recommended)

[`uv`](https://github.com/astral-sh/uv) is a fast Python package installer.

```bash
uv tool install git+https://github.com/arrase/eloquent-notes.git
```

To update to the latest version in the future:

```bash
uv tool upgrade eloquent-notes
```

### Method 2: Using `pipx`

[`pipx`](https://pipx.pypa.io/) installs Python CLI tools into isolated virtual environments:

```bash
pipx install git+https://github.com/arrase/eloquent-notes.git
```

To update:

```bash
pipx upgrade eloquent-notes
```

### Method 3: Local Development Installation

If you want to contribute or modify the source code locally:

1. Clone the repository:

   ```bash
   git clone https://github.com/arrase/eloquent-notes.git
   cd eloquent-notes
   ```

2. Create and activate a Python virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install in editable mode with development dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

---

## Desktop Autostart Setup

To ensure Eloquent Notes runs in your system tray automatically whenever you log into your Linux desktop, execute the autostart installation command:

```bash
eloquent-notes install-autostart
```

### What This Does

This command resolves the executable path (`shutil.which("eloquent-notes")`) and creates a FreeDesktop desktop entry at:

```
~/.config/autostart/eloquent-notes.desktop
```

The entry runs `Exec=<path to eloquent-notes>` with `X-GNOME-Autostart-enabled=true`. The same file is created or removed by the **Start automatically on login** option in the **General** tab of the configuration dialog.

Eloquent Notes will now start silently in your system tray upon desktop login. Run `eloquent-notes` again (or middle-click the tray icon) to open the notes window.

---

## First Run

1. Start the daemon: `eloquent-notes &`.
2. Open **Configuration** from the tray menu and check the **Notes Folder** (default `~/Documents/Eloquent Notes`) and the models in **AI Settings**.
3. Left-click the tray icon, speak, and click again. The note appears in the notes window.
