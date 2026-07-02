import os
import sys
import threading
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QObject, pyqtSignal
from eloquent_notes import config
from eloquent_notes import audio
from eloquent_notes import llm
from eloquent_notes import obsidian
from eloquent_notes import ui

class Signaler(QObject):
    update_icon_signal = pyqtSignal(str, str)

class EloquentApp:
    def __init__(self):
        self.state = "IDLE"
        self.recorder = None
        
        # Initialize PyQt application
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        # Thread-safe UI update signaler
        self.signaler = Signaler()
        self.signaler.update_icon_signal.connect(self._update_icon_slot)
        
        # Tray icon and menu variables
        self.tray = None
        self.menu = None
        self.toggle_action_item = None
        self.reload_action = None
        self.quit_action = None
        
        self._apply_config()

    def _apply_config(self):
        self.config = config.load_config()
        audio_cfg = self.config["audio"]
        self.sample_rate = audio_cfg["sample_rate"]
        self.channels = audio_cfg["channels"]
        self.temp_file = audio_cfg["temp_file"]
        self.beep_freq = audio_cfg["beep_frequency"]
        self.beep_dur = audio_cfg["beep_duration"]

    def run(self):
        # Create tray icon
        self.tray = QSystemTrayIcon()
        
        # Create context menu
        self.menu = QMenu()
        
        # Add actions
        self.toggle_action_item = QAction("Start/Stop Recording", self.menu)
        font = self.toggle_action_item.font()
        font.setBold(True)
        self.toggle_action_item.setFont(font)
        self.toggle_action_item.triggered.connect(self.toggle_action)
        self.menu.addAction(self.toggle_action_item)
        
        self.reload_action = QAction("Reload Configuration", self.menu)
        self.reload_action.triggered.connect(self.reload_config)
        self.menu.addAction(self.reload_action)
        
        self.menu.addSeparator()
        
        self.quit_action = QAction("Quit", self.menu)
        self.quit_action.triggered.connect(self.exit_app)
        self.menu.addAction(self.quit_action)
        
        self.tray.setContextMenu(self.menu)
        
        # Handle left-click activate event
        self.tray.activated.connect(self.on_tray_activated)
        
        # Initialise icon and tooltip
        self._update_icon_slot("gray", "Eloquent Notes (Idle)")
        
        self.tray.show()
        
        sys.exit(self.app.exec())

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_action()

    def _update_icon_slot(self, color, tooltip):
        if self.tray:
            self.tray.setIcon(ui.get_qicon(color))
            self.tray.setToolTip(tooltip)

    def update_icon(self, color, tooltip):
        self.signaler.update_icon_signal.emit(color, tooltip)

    def toggle_action(self):
        if self.state == "IDLE":
            self.start_recording()
        elif self.state == "RECORDING":
            self.stop_recording_and_process()
        elif self.state == "PROCESSING":
            ui.send_notification("Eloquent Notes", "The application is processing the previous dictation. Please wait.")

    def start_recording(self):
        self.state = "RECORDING"
        self.update_icon("red", "Eloquent Notes (Recording...)")
        
        try:
            audio.play_beep_async(frequency=self.beep_freq, duration=self.beep_dur, sample_rate=self.sample_rate)
                
            self.recorder = audio.AudioRecorder(
                filename=self.temp_file,
                sample_rate=self.sample_rate,
                channels=self.channels
            )
            self.recorder.start()
        except Exception as e:
            self.state = "IDLE"
            self.update_icon("gray", "Eloquent Notes (Idle)")
            ui.send_notification("Recording Error", f"Could not start recording: {str(e)}")

    def stop_recording_and_process(self):
        self.state = "PROCESSING"
        self.update_icon("orange", "Eloquent Notes (Processing...)")
        
        try:
            if self.recorder:
                self.recorder.stop()
            audio.play_beep_async(frequency=self.beep_freq, duration=self.beep_dur, sample_rate=self.sample_rate)
            threading.Thread(target=self.process_audio, daemon=True).start()
        except Exception as e:
            self.state = "IDLE"
            self.update_icon("gray", "Eloquent Notes (Idle)")
            ui.send_notification("Processing Error", f"Failed to stop recording or start processing: {str(e)}")

    def process_audio(self):
        try:
            ai_cfg = self.config["ai"]
            obs_cfg = self.config["obsidian"]
            
            ollama_url = ai_cfg["ollama_url"]
            model = ai_cfg["model"]
            
            system_prompt = config.load_prompt_template()
            user_prompt = config.load_user_prompt_template()
            context_length = ai_cfg["context_length"]
            
            result = llm.send_audio_to_ollama(
                ollama_url=ollama_url,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                context_length=context_length,
                wav_file_path=self.temp_file
            )
            
            if result.get("empty") or not result.get("text", "").strip():
                ui.send_notification("Dictation Empty", "No note was created because the audio was empty.")
                return
            
            polished_text = result["text"]
            
            vault_path = obs_cfg["vault_path"]
            folder = obs_cfg["folder"]
            daily_notes = obs_cfg["daily_notes"]
            
            saved_path = obsidian.save_note(
                vault_path=vault_path,
                folder=folder,
                daily_notes=daily_notes,
                text=polished_text
            )
            
            filename = os.path.basename(saved_path)
            ui.send_notification("Dictation Saved", f"Saved dictation to Obsidian ({filename})")
            
        except Exception as e:
            ui.send_notification("Processing Error", f"An error occurred while processing dictation: {str(e)}")
            
        finally:
            self.state = "IDLE"
            self.update_icon("gray", "Eloquent Notes (Idle)")

    def reload_config(self):
        try:
            self._apply_config()
            ui.send_notification("Eloquent Notes", "Configuration reloaded successfully.")
        except Exception as e:
            ui.send_notification("Configuration Error", f"Failed to reload configuration: {str(e)}")

    def exit_app(self):
        if self.state == "RECORDING" and self.recorder:
            self.recorder.stop()
        if self.tray:
            self.tray.hide()
        self.app.quit()
        sys.exit(0)

def install_autostart():
    autostart_dir = os.path.expanduser("~/.config/autostart")
    desktop_file_path = os.path.join(autostart_dir, "eloquent-notes.desktop")

    desktop_entry_content = """[Desktop Entry]
Type=Application
Exec=eloquent-notes
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Eloquent Notes
Comment=Background dictation utility for Obsidian
Icon=accessories-text-editor
Categories=Utility;
"""
    print("Installing autostart desktop entry...")
    os.makedirs(autostart_dir, exist_ok=True)
    with open(desktop_file_path, "w", encoding="utf-8") as f:
        f.write(desktop_entry_content)
    os.chmod(desktop_file_path, 0o755)
    print(f"Autostart desktop entry created successfully at: {desktop_file_path}")
    print("Eloquent Notes will now start automatically upon login!")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "install-autostart":
        install_autostart()
        sys.exit(0)
        
    app = EloquentApp()
    app.run()

if __name__ == "__main__":
    main()
