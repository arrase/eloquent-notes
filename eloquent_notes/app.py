import argparse
import os
import sys
import threading
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtNetwork import QLocalServer

import logging
from eloquent_notes import config
from eloquent_notes import audio
from eloquent_notes import llm
from eloquent_notes import obsidian
from eloquent_notes import ui
from eloquent_notes.logging_utils import setup_logging

logger = logging.getLogger("eloquent_notes.app")

class EloquentApp(QObject):
    processing_completed = pyqtSignal(str, str)

    def __init__(self, qapp, start_recording_immediately=False):
        super().__init__()
        self.app = qapp
        self.state = "IDLE"
        self.recorder = None
        self.start_recording_immediately = start_recording_immediately
        
        self.processing_completed.connect(self._on_processing_completed)
        
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
        self.tray = QSystemTrayIcon()
        
        self.server = QLocalServer(self)
        self.server.removeServer("eloquent_notes_ipc")
        if not self.server.listen("eloquent_notes_ipc"):
            logger.error("Failed to start local IPC server.")
        self.server.newConnection.connect(self._handle_ipc_connection)
        
        self.menu = QMenu()
        
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
        self.tray.activated.connect(self.on_tray_activated)
        
        self.update_icon("gray", "Eloquent Notes (Idle)")
        self.tray.show()
        
        if self.start_recording_immediately:
            QTimer.singleShot(100, self.toggle_action)
        
        sys.exit(self.app.exec())

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_action()

    def _handle_ipc_connection(self):
        socket = self.server.nextPendingConnection()
        if socket:
            if socket.waitForReadyRead(500):
                message = socket.readAll().data().decode("utf-8")
                if message == "toggle":
                    self.toggle_action()
                elif message == "notify_running":
                    self.send_notification(
                        "Eloquent Notes",
                        "Eloquent Notes is already running in the background."
                    )
            socket.disconnectFromServer()

    def update_icon(self, color, tooltip):
        self.tray.setIcon(ui.get_qicon(color))
        self.tray.setToolTip(tooltip)

    def send_notification(self, title, message):
        self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def toggle_action(self):
        if self.state == "IDLE":
            self.start_recording()
        elif self.state == "RECORDING":
            self.stop_recording_and_process()
        elif self.state == "PROCESSING":
            self.send_notification("Eloquent Notes", "The application is processing the previous dictation. Please wait.")

    def _preload_model_task(self):
        ai_cfg = self.config["ai"]
        try:
            llm.preload_model(
                ollama_url=ai_cfg["ollama_url"],
                model=ai_cfg["model"],
                context_length=ai_cfg["context_length"],
                keep_alive=ai_cfg["preload_keep_alive"],
                timeout=ai_cfg["preload_timeout"]
            )
        except Exception as e:
            logger.warning("Preload warning: %s", e, exc_info=True)

    def start_recording(self):
        self.state = "RECORDING"
        self.update_icon("red", "Eloquent Notes (Recording...)")
        logger.info("Starting audio recording...")
        
        try:
            if self.beep_enabled:
                audio.play_beep(frequency=self.beep_freq, duration=self.beep_dur, sample_rate=self.sample_rate)
                
            self.recorder = audio.AudioRecorder(
                sample_rate=self.sample_rate,
                channels=self.channels
            )
            self.recorder.start()

            threading.Thread(target=self._preload_model_task, daemon=True).start()
        except Exception as e:
            self.state = "IDLE"
            self.update_icon("gray", "Eloquent Notes (Idle)")
            logger.exception("Failed to start recording")
            self.send_notification("Recording Error", f"Could not start recording: {str(e)}")

    def stop_recording_and_process(self):
        self.state = "PROCESSING"
        self.update_icon("orange", "Eloquent Notes (Processing...)")
        logger.info("Stopping recording and starting processing...")
        
        try:
            self.recorder.stop()
            if self.beep_enabled:
                audio.play_beep(frequency=self.beep_freq, duration=self.beep_dur, sample_rate=self.sample_rate)
            threading.Thread(target=self.process_audio, daemon=True).start()
        except Exception as e:
            self.state = "IDLE"
            self.update_icon("gray", "Eloquent Notes (Idle)")
            logger.exception("Failed to stop recording or start processing")
            self.send_notification("Processing Error", f"Failed to stop recording or start processing: {str(e)}")

    def process_audio(self):
        logger.info("Processing recorded audio...")
        try:
            ai_cfg = self.config["ai"]
            obs_cfg = self.config["obsidian"]
            
            result = llm.send_audio_to_ollama(
                ollama_url=ai_cfg["ollama_url"],
                model=ai_cfg["model"],
                system_prompt=config.load_prompt_template(),
                user_prompt=config.load_user_prompt_template(),
                retry_prompt=config.load_retry_prompt_template(),
                context_length=ai_cfg["context_length"],
                audio_bytes=self.recorder.wav_bytes,
                keep_alive=ai_cfg["keep_alive"],
                max_retries=ai_cfg["max_retries"],
                timeout=ai_cfg["request_timeout"]
            )
            
            if result["empty"] or not result["text"].strip():
                self.processing_completed.emit("empty", "")
                return

            saved_path = obsidian.save_note(
                vault_path=obs_cfg["vault_path"],
                folder=obs_cfg["folder"],
                daily_notes=obs_cfg["daily_notes"],
                text=result["text"],
                tags=result["tags"],
                template_standalone=config.load_standalone_template(),
                template_daily_new=config.load_daily_new_template(),
                template_daily_append=config.load_daily_append_template()
            )
            self.processing_completed.emit("success", saved_path)
            
        except Exception as e:
            logger.exception("Error during audio processing/saving")
            self.processing_completed.emit("error", str(e))


    def _on_processing_completed(self, status, detail):
        self.state = "IDLE"
        self.update_icon("gray", "Eloquent Notes (Idle)")
        
        if status == "success":
            filename = os.path.basename(detail)
            logger.info("Dictation saved successfully: %s", filename)
            self.send_notification("Dictation Saved", f"Saved dictation to Obsidian ({filename})")
        elif status == "empty":
            logger.info("Dictation processing finished: Audio was empty")
            self.send_notification("Dictation Empty", "No note was created because the audio was empty.")
        elif status == "error":
            logger.error("Dictation processing failed: %s", detail)
            self.send_notification("Processing Error", f"An error occurred while processing dictation: {detail}")

    def reload_config(self):
        try:
            self._apply_config()
            logger.info("Configuration reloaded successfully")
            self.send_notification("Eloquent Notes", "Configuration reloaded successfully.")
        except Exception as e:
            logger.exception("Failed to reload configuration")
            self.send_notification("Configuration Error", f"Failed to reload configuration: {str(e)}")

    def exit_app(self):
        logger.info("Exiting application...")
        if self.state == "RECORDING":
            self.recorder.stop()
        self.server.close()
        self.server.removeServer("eloquent_notes_ipc")
        self.tray.hide()
        self.app.quit()
        sys.exit(0)

def main():
    parser = argparse.ArgumentParser(
        description="Eloquent Notes Daemon"
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["toggle"],
        metavar="command",
    )
    parser.add_argument(
        "-t", "--toggle",
        action="store_true",
    )
    args = parser.parse_args()

    config.init_config_dir()
    
    cfg = config.load_config()
    log_cfg = cfg["logging"]
    setup_logging(
        log_level_str=log_cfg["level"],
        max_mb=log_cfg["max_mb"],
        backup_count=log_cfg["backup_count"]
    )
    logger.info("Starting Eloquent Notes daemon...")
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    start_recording_immediately = (args.command == "toggle" or args.toggle)
    eloquent_app = EloquentApp(app, start_recording_immediately)
    eloquent_app.run()

if __name__ == "__main__":
    main()
