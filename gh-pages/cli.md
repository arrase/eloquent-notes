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
| *(None)* | | Starts the tray daemon. If it is already running, opens the notes window. |
| `toggle` | `-t`, `--toggle` | Toggles recording (IDLE $\rightarrow$ RECORDING or RECORDING $\rightarrow$ PROCESSING). |
| `open` | | Opens the notes window. |
| `config` | | Opens the configuration dialog. |
| `install-autostart` | | Installs the desktop autostart entry into `~/.config/autostart/`. |
| `--version` | | Prints the installed version and exits. |

---

## Detailed Command Descriptions

### 1. `eloquent-notes` (Daemon Launch / Single-Instance Check)

Launching `eloquent-notes` without a command connects to the local IPC socket `eloquent_notes_ipc`.
* If the daemon is **already running**, it sends `open`, which shows the notes window, and exits.
* If **no daemon is running**, it executes `eloquent_notes.app` to start the tray icon and the IPC server. The window is not opened; the app starts quietly in the tray.

### 2. `eloquent-notes toggle` (or `eloquent-notes -t`)

Toggles the recording state. This command is intended to be called by desktop keyboard shortcuts, global hotkey daemons, or terminal scripts.
* If daemon is **running**, sends a `toggle` message via IPC.
* If daemon is **not running**, automatically launches the daemon in background mode and immediately starts recording (`os.execv` fallback).

### 3. `eloquent-notes open`

Shows the notes window (timeline, search and reader).
* If daemon is **running**, sends an `open` message via IPC.
* If daemon is **not running**, launches the daemon and opens the window right away.

### 4. `eloquent-notes config`

Opens the graphical configuration management dialog.
* Runs in its own process, independent of the daemon.
* Upon clicking **Save**, if an active daemon is detected on `eloquent_notes_ipc`, it sends a `reload` IPC signal to reload configuration in-memory without restarting the daemon process.

### 5. `eloquent-notes install-autostart`

Creates the system autostart file `~/.config/autostart/eloquent-notes.desktop` (starts quietly in the tray on login) as well as the application launcher entry `~/.local/share/applications/eloquent-notes.desktop` (`Exec=<path> open`, which opens the notes list and starts the daemon if needed) and SVG icon `~/.local/share/icons/hicolor/scalable/apps/eloquent-notes.svg`.

### 6. `eloquent-notes --version`

Prints the installed version and exits, for example:

```bash
$ eloquent-notes --version
eloquent-notes 0.3.1
```

The value is read from the installed distribution metadata, so it always matches the release you actually have installed rather than a separately maintained constant.

---

## Decoupled CLI Architecture & Low-Latency IPC

To ensure that pressing a global keyboard shortcut provides instantaneous audio feedback without UI lag, Eloquent Notes uses a headless `QCoreApplication` and local socket IPC for control commands instead of creating GUI windows in the CLI client process.

The daemon accepts three IPC messages:

| Message | Sent by | Effect |
| :--- | :--- | :--- |
| `toggle` | `eloquent-notes toggle` / `-t` | `toggle_action()`: start or stop recording. |
| `open` | `eloquent-notes`, `eloquent-notes open` | `show_window()`: show and raise the notes window. |
| `reload` | `eloquent-notes config` after **Save** | `reload_config()`: reload settings, prompts and logging. |

```
                  +--------------------------+
                  |  eloquent-notes [open |  |
                  |          toggle]         |
                  +-------------+------------+
                                |
                   QCoreApplication (Headless)
                                |
                     QLocalSocket ("eloquent_notes_ipc")
                                |
           +--------------------+--------------------+
           | (Socket Connected)                      | (Connection Failed)
           v                                         v
   Send "toggle" / "open"                  os.execv(sys.executable, ...)
   to Running Daemon (<5ms)                Spawn Daemon Process
```

### Key Architectural Benefits

1. **Headless Core App (`QCoreApplication`)**: When executing `eloquent-notes`, `toggle` or `open`, `run_cli()` instantiates a headless `QCoreApplication` rather than `QApplication` or any GUI dialogs, avoiding display server window initialization and keeping the IPC client fast.
2. **Unix Domain Socket (`QLocalSocket`)**: Communication between the CLI process and daemon occurs over named Unix local sockets (`eloquent_notes_ipc`). The IPC handshake, message transfer (`"toggle"`), and socket disconnection complete in under 5 milliseconds.
3. **Automatic Daemon Spawning (`os.execv`)**: If `QLocalSocket.connectToServer()` fails or times out after 500 ms, `main.py` detects that the background daemon is inactive. It replaces the current process image using `os.execv(sys.executable, daemon_args)` to start `eloquent_notes.app` directly, passing `toggle` or `open` so the new daemon performs the requested action once its event loop starts.

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
2026-08-06 14:30:00 [INFO] (MainThread) eloquent_notes.app._start_recording:289 - Starting audio recording...
2026-08-06 14:30:05 [INFO] (Thread-2) eloquent_notes.app._process_audio:465 - Phase 1: Transcribing audio...
2026-08-06 14:30:08 [INFO] (Thread-2) eloquent_notes.app._process_audio:478 - Rewriting: title=Daily Standup Notes
2026-08-06 14:30:09 [INFO] (Thread-2) eloquent_notes.app._process_audio:484 - Phase 3: Classifying note...
2026-08-06 14:30:10 [INFO] (MainThread) eloquent_notes.app._on_processing_completed:528 - Note saved: Daily Standup Notes
```

Log level and rotation limits can be changed in the **General** tab of the GUI or directly inside `config.yaml`:

```yaml
logging:
  level: "INFO"       # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
  max_mb: 5           # Log file size limit before rotation
  backup_count: 3     # Maximum rotated log archives
```

---

## Other Files

| Path | Content |
| :--- | :--- |
| `$XDG_CONFIG_HOME/eloquent-notes/` (default `~/.config/eloquent-notes/`) | `config.yaml` and `prompts/` (see [Configuration](configuration.md)). |
| `$XDG_DATA_HOME/applications/eloquent-notes.desktop` (default `~/.local/share/applications/`) | Application menu / dock launcher (`eloquent-notes open`). |
| `$XDG_DATA_HOME/icons/hicolor/scalable/apps/eloquent-notes.svg` | Application SVG icon. |
| `$XDG_CACHE_HOME/eloquent-notes/embeddings.npz` (default `~/.cache/eloquent-notes/`) | Semantic search embedding cache; safe to delete (see [Notes & Search](notes.md)). |
| `notes.folder` (default `~/Documents/Eloquent Notes`) | The notes themselves, one Markdown file each. |
