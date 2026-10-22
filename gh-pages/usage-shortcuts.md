# System Tray & Shortcuts

Eloquent Notes runs in your desktop panel. Recording is controlled from the tray icon, the notes window, the floating HUD or a global keyboard shortcut; notes are browsed and edited in the notes window.

---

## System Tray Interaction Flow

### Mouse Interactions

* **Left Click**: Toggles recording.
  * If **Idle** $\rightarrow$ Starts recording a new note.
  * If **Recording** $\rightarrow$ Stops recording and starts background processing.
  * If **Processing** $\rightarrow$ Shows a "System is busy" notification.
* **Middle Click**: Shows the notes window, or closes it if it is visible.
* **Right Click (Context Menu)**:
  * **Start/Stop Recording** *(Bold)*: Toggles recording.
  * **Open Notes**: Shows the notes window.
  * **Configuration**: Opens the configuration dialog.
  * **Reload Configuration**: Reloads `config.yaml` and prompts without restarting the daemon.
  * **Quit**: Stops any recording, waits briefly for processing, closes the IPC server and exits.

Clicking a desktop notification (e.g. **Note Saved**) opens the notes window. While recording, clicking the floating HUD also stops the recording.

### Notifications

| Notification | When |
| :--- | :--- |
| **Note Saved** | A new note was written (shows its title). |
| **Dictation Added** | An add-dictation was appended to a note. |
| **Dictation Empty** | The recording was silent or the transcription empty; nothing was saved. |
| **Processing Error** / **Delete Failed** / **Configuration Error** | Something failed; the message contains the reason. |

---

## Notes Window

The window shows a single centered column:

* **Header**: app title and a **Settings** button.
* **Search box**: press <kbd>Enter</kbd> to search notes by meaning; clear it to return to the timeline.
* **Filters**: type chips (All, Notes, Tasks, Ideas, Reminders, Questions, Decisions) and a tag selector.
* **Timeline**: note cards grouped by day (Today, Yesterday, "Monday, 19 October"). Click a card to open it; click a `#tag` to filter by it.
* **Record button**: the large round button at the bottom records a new note. The text below shows *Click to record a note*, *Recording… click to stop* or *Writing your note…*.

In the **reader**, title, type, tags and body are editable. The toolbar offers **← Back** (<kbd>Esc</kbd>), **Add dictation** (becomes *Stop dictation* while recording), **Copy** and **Delete**. See [Notes & Search](notes.md) for details.

---

## Visual Status Indicators

The tray icon changes color and symbol to indicate the active state:

| Status | Icon Appearance | Tooltip Label | Description |
| :--- | :--- | :--- | :--- |
| **Idle** | Gray Circle + White Microphone | `Eloquent Notes (Idle)` | Waiting for input. No audio input is active. |
| **Recording** | Red Circle + White Recording Dot | `Eloquent Notes (Recording...)` | Microphone audio is recorded into memory; the model is preloaded in the background. |
| **Processing** | Orange Circle + White Hourglass | `Eloquent Notes (Processing...)` | The Ollama pipeline is writing the note (transcription, rewriting, classification). |

The same icons appear on the record button and the **Add dictation** button in the notes window.

---

## Audible Feedback Beeps

Eloquent Notes plays a short tone when recording starts and stops, so you know the state without looking at the screen.

### Technical Implementation

Audio beeps are generated dynamically using NumPy sound wave synthesis:

1. **Sine-Wave Generation**: Generates a pure audio frequency (default `440` Hz, A4 note) over the configured duration (default `0.1` seconds / 100 ms).
2. **Anti-Click Linear Fades**: Applies a 10 ms linear fade-in (`0.0` to `1.0`) at the start and a 10 ms linear fade-out (`1.0` to `0.0`) at the end of the waveform array. This eliminates sharp voltage steps that cause harsh speaker clicking artifacts.
3. **Sound Playback**: Output is played through `sounddevice` using float32 PCM precision. The start beep is played synchronously (`wait=True`) before opening the microphone so the tone cannot leak into the recording, while the stop beep is played asynchronously (`wait=False`) after closing the microphone.

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

### Opening the Notes Window

Bind `eloquent-notes open` the same way to show the notes window from anywhere. Both commands start the daemon first if it is not running.
