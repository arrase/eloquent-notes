# Installation & Setup

This guide walks you through setting up system prerequisites, installing local AI models with Ollama, installing Eloquent Notes, and configuring desktop autostart.

---

## System Requirements

Eloquent Notes is engineered for Linux desktop environments. Ensure your system meets the following prerequisites before proceeding:

| Component | Minimum Requirement | Notes |
| :--- | :--- | :--- |
| **Operating System** | Linux (Ubuntu, Debian, Fedora, Arch, openSUSE, etc.) | Uses XDG directory standards and X11/Wayland system tray. |
| **Python** | Python 3.8+ | Standard Python runtime environment. |
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

## Local Ollama Setup & Gemma 4 Model Download

Eloquent Notes relies on **Ollama** to run the multimodal Gemma 4 model locally on your hardware for transcription, note rewriting, and classification.

### 1. Install Ollama

If Ollama is not already installed, run the official Linux installer script:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Verify that the Ollama service is running:

```bash
systemctl status ollama
```

### 2. Download Gemma 4 Model

Download the recommended quantized Gemma 4 model (`gemma4:e4b-it-qat`):

```bash
ollama pull gemma4:e4b-it-qat
```

*(Note: You can also use other multimodal models compatible with audio dictation by updating the model name in your `config.yaml` or through the **AI Settings** tab in the GUI).*

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
   pip install -e .
   ```

---

## Desktop Autostart Setup

To ensure Eloquent Notes runs in your system tray automatically whenever you log into your Linux desktop, execute the autostart installation command:

```bash
eloquent-notes install-autostart
```

### What This Does

This command resolves the binary executable path and creates a FreeDesktop-compliant desktop entry file at:

```
~/.config/autostart/eloquent-notes.desktop
```

With the following content:

```ini
[Desktop Entry]
Type=Application
Exec=/home/username/.local/bin/eloquent-notes
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Eloquent Notes
Comment=Background dictation utility for Obsidian
Icon=accessories-text-editor
Categories=Utility;
```

Eloquent Notes will now start silently in your system tray upon desktop login.
