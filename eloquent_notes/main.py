import argparse
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
from eloquent_notes.autostart import install_autostart

class EloquentApp(QObject):
    update_icon_signal = pyqtSignal(str, str)
    show_message_signal = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.state = "IDLE"
        self.recorder = None
        
        # Initialize PyQt application
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        # Connect thread-safe UI update signals
        self.update_icon_signal.connect(self._update_icon_slot)
        self.show_message_signal.connect(self._show_message_slot)
        
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
        self.beep_freq = audio_cfg["beep_frequency"]
        self.beep_dur = audio_cfg["beep_duration"]
        self.beep_enabled = audio_cfg["beep_enabled"]

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

    def _show_message_slot(self, title, message):
        if self.tray:
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)
        else:
            print(f"[{title}] {message}")

    def update_icon(self, color, tooltip):
        self.update_icon_signal.emit(color, tooltip)

    def send_notification(self, title, message):
        self.show_message_signal.emit(title, message)

    def toggle_action(self):
        if self.state == "IDLE":
            self.start_recording()
        elif self.state == "RECORDING":
            self.stop_recording_and_process()
        elif self.state == "PROCESSING":
            self.send_notification("Eloquent Notes", "The application is processing the previous dictation. Please wait.")

    def _preload_model_task(self):
        ai_cfg = self.config["ai"]
        ollama_url = ai_cfg.get("ollama_url", "http://localhost:11434")
        model = ai_cfg.get("model", "gemma4:12b-it-qat")
        preload_keep_alive = ai_cfg.get("preload_keep_alive", "5m")
        context_length = ai_cfg.get("context_length")

        try:
            llm.preload_model(ollama_url, model, context_length, preload_keep_alive)
        except Exception as e:
            self.send_notification("Preload Error", f"Failed to preload model: {str(e)}")

    def start_recording(self):
        self.state = "RECORDING"
        self.update_icon("red", "Eloquent Notes (Recording...)")
        
        try:
            if self.beep_enabled:
                audio.play_beep(frequency=self.beep_freq, duration=self.beep_dur, sample_rate=self.sample_rate)
                
            self.recorder = audio.AudioRecorder(
                sample_rate=self.sample_rate,
                channels=self.channels
            )
            self.recorder.start()

            # Start preloading the model in the background to reduce cold start time
            threading.Thread(target=self._preload_model_task, daemon=True).start()
        except Exception as e:
            self.state = "IDLE"
            self.update_icon("gray", "Eloquent Notes (Idle)")
            self.send_notification("Recording Error", f"Could not start recording: {str(e)}")

    def stop_recording_and_process(self):
        self.state = "PROCESSING"
        self.update_icon("orange", "Eloquent Notes (Processing...)")
        
        try:
            if self.recorder:
                self.recorder.stop()
            if self.beep_enabled:
                audio.play_beep(frequency=self.beep_freq, duration=self.beep_dur, sample_rate=self.sample_rate)
            threading.Thread(target=self.process_audio, daemon=True).start()
        except Exception as e:
            self.state = "IDLE"
            self.update_icon("gray", "Eloquent Notes (Idle)")
            self.send_notification("Processing Error", f"Failed to stop recording or start processing: {str(e)}")

    def process_audio(self):
        try:
            ai_cfg = self.config["ai"]
            obs_cfg = self.config["obsidian"]
            
            ollama_url = ai_cfg["ollama_url"]
            model = ai_cfg["model"]
            
            system_prompt = config.load_prompt_template()
            user_prompt = config.load_user_prompt_template()
            context_length = ai_cfg["context_length"]
            keep_alive = ai_cfg.get("keep_alive", "5m")
            
            audio_bytes = self.recorder.wav_bytes if self.recorder else b""
            
            result = llm.send_audio_to_ollama(
                ollama_url=ollama_url,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                context_length=context_length,
                audio_bytes=audio_bytes,
                keep_alive=keep_alive
            )
            
            if result.get("empty") or not result.get("text", "").strip():
                self.send_notification("Dictation Empty", "No note was created because the audio was empty.")
                return
            
            polished_text = result["text"]
            
            vault_path = obs_cfg["vault_path"]
            folder = obs_cfg["folder"]
            daily_notes = obs_cfg["daily_notes"]
            
            template_standalone = config.load_standalone_template()
            template_daily_new = config.load_daily_new_template()
            template_daily_append = config.load_daily_append_template()

            saved_path = obsidian.save_note(
                vault_path=vault_path,
                folder=folder,
                daily_notes=daily_notes,
                text=polished_text,
                template_standalone=template_standalone,
                template_daily_new=template_daily_new,
                template_daily_append=template_daily_append
            )
            
            filename = os.path.basename(saved_path)
            self.send_notification("Dictation Saved", f"Saved dictation to Obsidian ({filename})")
            
        except Exception as e:
            self.send_notification("Processing Error", f"An error occurred while processing dictation: {str(e)}")
            
        finally:
            self.state = "IDLE"
            self.update_icon("gray", "Eloquent Notes (Idle)")

    def reload_config(self):
        try:
            self._apply_config()
            self.send_notification("Eloquent Notes", "Configuration reloaded successfully.")
        except Exception as e:
            self.send_notification("Configuration Error", f"Failed to reload configuration: {str(e)}")

    def exit_app(self):
        if self.state == "RECORDING" and self.recorder:
            self.recorder.stop()
        if self.tray:
            self.tray.hide()
        self.app.quit()
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description="Eloquent Notes - Linux system tray utility for offline dictation into Obsidian."
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["install-autostart"],
        help="Command to execute (e.g., 'install-autostart' to install autostart desktop entry)."
    )
    
    args = parser.parse_args()
    
    if args.command == "install-autostart":
        install_autostart()
        sys.exit(0)
        
    # Initialize configuration directories and copy defaults
    config.init_config_dir()
        
    app = EloquentApp()
    app.run()

if __name__ == "__main__":
    main()
