# CLI & Logging

Eloquent Notes includes a command-line interface (CLI) that acts both as the application daemon launcher and as a client to send control IPC commands to an already running background instance.

---

## CLI Command Suite

When installed, the `eloquent-notes` executable binary is added to your environment path.

### Command Usage Overview

```bash
eloquent-notes [command] [options]
```

| Command | Short Flag | Purpose |
| :--- | :--- | :--- |
| *(None)* | | Starts the background system tray daemon. If already running, notifies user. |
| `toggle` | `-t` | Toggles recording (IDLE $\rightarrow$ RECORDING or RECORDING $\rightarrow$ PROCESSING). |
| `config` | | Launches the standalone PyQt6 Configuration GUI window. |
| `install-autostart` | | Installs the desktop autostart entry into `~/.config/autostart/`. |

---

## Detailed Command Descriptions

### 1. `eloquent-notes` (Daemon Launch / Single-Instance Check)

Launching `eloquent-notes` without subcommands will attempt to establish a local IPC connection to `eloquent_notes_ipc`.
* If a background daemon is **already running**, it sends a `notify_running` signal, triggering a desktop notification and exiting immediately.
* If **no daemon is running**, it executes `eloquent_notes.app` to start the tray application, system tray icon, and IPC server listener.

### 2. `eloquent-notes toggle` (or `eloquent-notes -t`)

Toggles the recording state. This command is intended to be called by desktop keyboard shortcuts, global hotkey daemons, or terminal scripts.
* If daemon is **running**, sends a `toggle` message via IPC.
* If daemon is **not running**, automatically launches the daemon in background mode and immediately starts recording (`os.execv` fallback).

### 3. `eloquent-notes config`

Opens the graphical configuration management dialog.
* Runs independently as a PyQt6 application window.
* Upon clicking **Save**, if an active daemon is detected on `eloquent_notes_ipc`, it sends a `reload` IPC signal to reload configuration in-memory without restarting the daemon process.

### 4. `eloquent-notes install-autostart`

Creates a system autostart file `~/.config/autostart/eloquent-notes.desktop` pointing to your current executable installation path (`shutil.which("eloquent-notes")`).

---

## Decoupled CLI Architecture & Low-Latency IPC

To ensure that pressing a global keyboard shortcut provides instantaneous audio feedback without UI lag or heavy memory allocation, Eloquent Notes separates the CLI launcher from heavy GUI widgets.

```
                  +--------------------------+
                  |  eloquent-notes toggle   |
                  +-------------+------------+
                                |
                   QCoreApplication (No GUI)
                                |
                     QLocalSocket ("eloquent_notes_ipc")
                                |
           +--------------------+--------------------+
           | (Socket Connected)                      | (Connection Failed)
           v                                         v
   Send "toggle" bytes                     os.execv(sys.executable, ...)
   to Running Daemon (<5ms)                Spawn Daemon Process
```

### Key Architectural Benefits

1. **Lightweight Core App (`QCoreApplication`)**: When executing `eloquent-notes toggle`, the CLI instantiates `QCoreApplication` rather than `QApplication`. This avoids initializing display server widget libraries, window managers, or heavy graphics contexts, keeping memory footprint minimal (~15 MB).
2. **Unix Domain Socket (`QLocalSocket`)**: Communication between the CLI process and daemon occurs over named Unix local sockets (`eloquent_notes_ipc`). The IPC handshake, message transfer (`"toggle"`), and socket disconnection complete in under 5 milliseconds.
3. **Automatic Daemon Spawning (`os.execv`)**: If `QLocalSocket.connectToServer()` fails or times out after 500 ms, `main.py` detects that the background daemon is inactive. It replaces the current process image using `os.execv(sys.executable, daemon_args)` to start `eloquent_notes.app` directly.

---

## XDG Base Directory Compliant Logging

Eloquent Notes strictly follows the **XDG Base Directory Specification** for application state and logging.

### Log File Location

Log files are written to:

```
$XDG_STATE_HOME/eloquent-notes/app.log
```

If `$XDG_STATE_HOME` is unset, it defaults to:

```
~/.local/state/eloquent-notes/app.log
```

### Rotating File Handler

To prevent log files from growing indefinitely, Eloquent Notes implements a `RotatingFileHandler`:

* **Max File Size (`max_mb`)**: Default is `5` MB (5,242,880 bytes). When `app.log` reaches this threshold, it is closed and renamed.
* **Backup Count (`backup_count`)**: Preserves up to `3` historical log archives (`app.log.1`, `app.log.2`, `app.log.3`).
* **Console Sync**: Log records are simultaneously output to `sys.stdout` for interactive shell inspection.

### Log Format

Logs format timestamps, levels, thread names, module functions, and line numbers:

```text
2026-08-06 14:30:00 [INFO] (MainThread) eloquent_notes.app._start_recording:146 - Starting audio recording...
2026-08-06 14:30:05 [INFO] (Thread-1) eloquent_notes.app._process_audio:257 - Phase 1: Transcribing audio...
2026-08-06 14:30:08 [INFO] (Thread-1) eloquent_notes.app._process_audio:308 - Rewriting: title=Daily Standup Notes
2026-08-06 14:30:10 [INFO] (Thread-1) eloquent_notes.app._on_processing_completed:378 - Dictation saved successfully: 2026-08-06-Daily-Standup-Notes.md
```

Log level and rotation limits can be changed in the **General** tab of the GUI or directly inside `config.yaml`:

```yaml
logging:
  level: "INFO"       # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
  max_mb: 5           # Log file size limit before rotation
  backup_count: 3     # Maximum rotated log archives
```
