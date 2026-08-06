# System Tray & Shortcuts

Eloquent Notes is designed as a background Linux system tray utility. It runs unobtrusively in your desktop panel and can be controlled either via system tray mouse clicks or global system-wide keyboard shortcuts.

---

## System Tray Interaction Flow

The system tray icon provides immediate visual status feedback and quick access to application controls.

### Mouse Interactions

* **Left Click (Trigger)**: Toggles recording state.
  * If **Idle** $\rightarrow$ Starts audio recording.
  * If **Recording** $\rightarrow$ Stops audio recording and initiates background LLM processing.
  * If **Processing** $\rightarrow$ Shows a DBus desktop notification informing that the system is busy.
* **Right Click (Context Menu)**: Opens the context menu with the following options:
  * **Start/Stop Recording** *(Bold)*: Toggles dictation recording.
  * **Configuration**: Opens the PyQt6 Configuration GUI dialog.
  * **Reload Configuration**: Dynamically reloads settings from `config.yaml` without restarting the daemon.
  * **Quit**: Safely stops ongoing recordings/threads, closes IPC servers, and exits the application.

---

## Visual Status Indicators

The tray icon dynamically changes color and symbol to indicate the active state:

| Status | Icon Appearance | Tooltip Label | Description |
| :--- | :--- | :--- | :--- |
| **Idle** | Gray Circle + White Microphone | `Eloquent Notes (Idle)` | The daemon is listening for input commands. No audio input is active. |
| **Recording** | Red Circle + White Recording Dot | `Eloquent Notes (Recording...)` | Audio input stream is open. Microphone audio is being recorded into memory buffer. Model preloading is dispatched. |
| **Processing** | Orange Circle + White Hourglass | `Eloquent Notes (Processing...)` | Audio recording is closed. The 3-phase Ollama AI pipeline is executing (transcription, rewriting, classification). |

---

## Audible Feedback Beeps

To allow seamless hands-free dictation without looking at your desktop tray icon, Eloquent Notes provides audible tone feedback when recording starts and stops.

### Technical Implementation

Audio beeps are generated dynamically using NumPy sound wave synthesis:

1. **Sine-Wave Generation**: Generates a pure audio frequency (default `440` Hz, A4 note) over the configured duration (default `0.1` seconds / 100 ms).
2. **Anti-Click Linear Fades**: Applies a 10 ms linear fade-in (`0.0` to `1.0`) at the start and a 10 ms linear fade-out (`1.0` to `0.0`) at the end of the waveform array. This eliminates sharp voltage steps that cause harsh speaker clicking artifacts.
3. **Sound Playback**: Output is played asynchronously through `sounddevice` using float32 PCM precision.

```python
# Pure sine wave with 10ms anti-click envelope
t = np.linspace(0, duration, int(sample_rate * duration), False)
sine_wave = np.sin(frequency * t * 2 * np.pi)

fade_len = min(int(sample_rate * 0.01), len(sine_wave) // 2)
if fade_len > 0:
    sine_wave[:fade_len] *= np.linspace(0.0, 1.0, fade_len)
    sine_wave[-fade_len:] *= np.linspace(1.0, 0.0, fade_len)
```

Audible beeps can be customized or disabled entirely in the **Audio** tab of the Configuration GUI or in `config.yaml`.

---

## Global Keyboard Shortcuts Setup

Because Linux desktop environments handle global hotkeys independently, Eloquent Notes provides the decoupled `eloquent-notes toggle` CLI command. You can bind this command to your preferred global shortcut key in any desktop environment.

### 1. GNOME Desktop (Ubuntu, Fedora, Workstation)

1. Open **Settings** $\rightarrow$ **Keyboard**.
2. Scroll down and click **View and Customize Shortcuts** $\rightarrow$ **Custom Shortcuts**.
3. Click **+** (Add Shortcut).
4. Fill out the dialog:
   * **Name**: `Eloquent Notes Toggle`
   * **Command**: `eloquent-notes toggle` (or `~/.local/bin/eloquent-notes toggle` if installed via `uv` / `pipx`)
   * **Shortcut**: Press your preferred key combination (e.g. <kbd>Super</kbd> + <kbd>Alt</kbd> + <kbd>R</kbd> or <kbd>Ctrl</kbd> + <kbd>Alt</kbd> + <kbd>Space</kbd>).
5. Click **Add**.

### 2. KDE Plasma Desktop

1. Open **System Settings** $\rightarrow$ **Shortcuts** (or **Custom Shortcuts**).
2. Click **Add New** $\rightarrow$ **Global Shortcut** $\rightarrow$ **Command/URL**.
3. Set the trigger key in the **Trigger** tab (e.g. <kbd>Meta</kbd> + <kbd>Shift</kbd> + <kbd>R</kbd>).
4. Set the command in the **Action** tab: `eloquent-notes toggle`.
5. Click **Apply**.

### 3. i3 / Sway Window Managers

Add the execution rule to your window manager configuration file:

**For i3 (`~/.config/i3/config`):**

```config
# Toggle Eloquent Notes Dictation
bindsym $mod+Mod1+r exec --no-startup-id eloquent-notes toggle
```

**For Sway (`~/.config/sway/config`):**

```config
# Toggle Eloquent Notes Dictation
bindsym $mod+Mod1+r exec eloquent-notes toggle
```

Reload your window manager configuration (`$mod+Shift+r` for i3 or `swaymsg reload`). Pressing the shortcut will instantly start or stop dictation.
