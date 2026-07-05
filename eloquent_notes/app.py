"""Eloquent Notes daemon — system tray application.

Manages the recording lifecycle (IDLE → RECORDING → PROCESSING → IDLE),
IPC for single-instance communication, and Obsidian note generation
through Ollama.
"""

import argparse
import logging
import os
import sys
import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from eloquent_notes import audio, config, llm, obsidian, ui
from eloquent_notes.logging_utils import setup_logging

logger = logging.getLogger("eloquent_notes.app")


class EloquentApp(QObject):
    """Main application controller for the system tray dictation tool."""

    processing_completed = pyqtSignal(str, str)

    def __init__(self, qapp, start_recording_immediately=False):
        super().__init__()
        self.app = qapp
        self.state = "IDLE"
        self.recorder = None
        self.config = config.load_config()
        self.start_recording_immediately = start_recording_immediately

        self.processing_completed.connect(self._on_processing_completed)

    def run(self):
        """Set up the system tray, IPC server, and enter the event loop."""
        self.tray = QSystemTrayIcon()

        self.server = QLocalServer(self)
        self.server.removeServer("eloquent_notes_ipc")
        if not self.server.listen("eloquent_notes_ipc"):
            logger.error("Failed to start local IPC server.")
        self.server.newConnection.connect(self._handle_ipc_connection)

        self.menu = QMenu()

        toggle_action = QAction("Start/Stop Recording", self.menu)
        font = toggle_action.font()
        font.setBold(True)
        toggle_action.setFont(font)
        toggle_action.triggered.connect(self.toggle_action)
        self.menu.addAction(toggle_action)

        reload_action = QAction("Reload Configuration", self.menu)
        reload_action.triggered.connect(self.reload_config)
        self.menu.addAction(reload_action)

        self.menu.addSeparator()

        quit_action = QAction("Quit", self.menu)
        quit_action.triggered.connect(self.exit_app)
        self.menu.addAction(quit_action)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)

        self._update_icon("gray", "Eloquent Notes (Idle)")
        self.tray.show()

        if self.start_recording_immediately:
            QTimer.singleShot(100, self.toggle_action)

        sys.exit(self.app.exec())

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_action()

    def _handle_ipc_connection(self):
        socket = self.server.nextPendingConnection()
        if socket and socket.waitForReadyRead(500):
            message = socket.readAll().data().decode("utf-8")
            if message == "toggle":
                self.toggle_action()
            elif message == "notify_running":
                self._notify(
                    "Eloquent Notes",
                    "Eloquent Notes is already running in the background.",
                )
        if socket:
            socket.disconnectFromServer()

    def _update_icon(self, color, tooltip):
        self.tray.setIcon(ui.get_qicon(color))
        self.tray.setToolTip(tooltip)

    def _notify(self, title, message):
        self.tray.showMessage(
            title, message,
            QSystemTrayIcon.MessageIcon.Information, 5000,
        )

    def toggle_action(self):
        """Handle toggle: start, stop, or notify if already processing."""
        if self.state == "IDLE":
            self._start_recording()
        elif self.state == "RECORDING":
            self._stop_recording_and_process()
        elif self.state == "PROCESSING":
            self._notify(
                "Eloquent Notes",
                "Processing the previous dictation. Please wait.",
            )

    def _preload_model(self):
        ai_cfg = self.config["ai"]
        try:
            llm.preload_model(
                ollama_url=ai_cfg["ollama_url"],
                model=ai_cfg["model"],
                context_length=ai_cfg["context_length"],
                keep_alive=ai_cfg["preload_keep_alive"],
                timeout=ai_cfg["preload_timeout"],
            )
        except Exception as e:
            logger.warning("Preload warning: %s", e, exc_info=True)

    def _start_recording(self):
        self.state = "RECORDING"
        self._update_icon("red", "Eloquent Notes (Recording...)")
        logger.info("Starting audio recording...")

        audio_cfg = self.config["audio"]
        try:
            if audio_cfg["beep_enabled"]:
                audio.play_beep(
                    frequency=audio_cfg["beep_frequency"],
                    duration=audio_cfg["beep_duration"],
                    sample_rate=audio_cfg["sample_rate"],
                )

            self.recorder = audio.AudioRecorder(
                sample_rate=audio_cfg["sample_rate"],
                channels=audio_cfg["channels"],
            )
            self.recorder.start()

            threading.Thread(
                target=self._preload_model, daemon=True,
            ).start()
        except Exception as e:
            self.state = "IDLE"
            self._update_icon("gray", "Eloquent Notes (Idle)")
            logger.exception("Failed to start recording")
            self._notify("Recording Error", f"Could not start recording: {e}")

    def _stop_recording_and_process(self):
        self.state = "PROCESSING"
        self._update_icon("orange", "Eloquent Notes (Processing...)")
        logger.info("Stopping recording and starting processing...")

        audio_cfg = self.config["audio"]
        self.recorder.stop()
        if audio_cfg["beep_enabled"]:
            audio.play_beep(
                frequency=audio_cfg["beep_frequency"],
                duration=audio_cfg["beep_duration"],
                sample_rate=audio_cfg["sample_rate"],
            )
        threading.Thread(target=self._process_audio, daemon=True).start()

    def _process_audio(self):
        """Process recorded audio via LLM and save to Obsidian.

        Runs in a background thread. Emits processing_completed signal
        to communicate results back to the GUI thread.
        """
        logger.info("Processing recorded audio...")
        try:
            ai_cfg = self.config["ai"]
            obs_cfg = self.config["obsidian"]

            result = llm.send_audio_to_ollama(
                ollama_url=ai_cfg["ollama_url"],
                model=ai_cfg["model"],
                system_prompt=config.load_file(config.SYSTEM_PROMPT_PATH),
                user_prompt=config.load_file(config.USER_PROMPT_PATH),
                retry_prompt=config.load_file(config.RETRY_PROMPT_PATH),
                context_length=ai_cfg["context_length"],
                audio_bytes=self.recorder.wav_bytes,
                keep_alive=ai_cfg["keep_alive"],
                max_retries=ai_cfg["max_retries"],
                timeout=ai_cfg["request_timeout"],
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
                template_standalone=config.load_file(
                    config.STANDALONE_TEMPLATE_PATH,
                ),
                template_daily_new=config.load_file(
                    config.DAILY_NEW_TEMPLATE_PATH,
                ),
                template_daily_append=config.load_file(
                    config.DAILY_APPEND_TEMPLATE_PATH,
                ),
            )
            self.processing_completed.emit("success", saved_path)

        except Exception as e:
            logger.exception("Error during audio processing/saving")
            self.processing_completed.emit("error", str(e))

    def _on_processing_completed(self, status, detail):
        self.state = "IDLE"
        self._update_icon("gray", "Eloquent Notes (Idle)")

        if status == "success":
            filename = os.path.basename(detail)
            logger.info("Dictation saved successfully: %s", filename)
            self._notify(
                "Dictation Saved",
                f"Saved dictation to Obsidian ({filename})",
            )
        elif status == "empty":
            logger.info("Dictation processing finished: Audio was empty")
            self._notify(
                "Dictation Empty",
                "No note was created because the audio was empty.",
            )
        elif status == "error":
            logger.error("Dictation processing failed: %s", detail)
            self._notify(
                "Processing Error",
                f"Error processing dictation: {detail}",
            )

    def reload_config(self):
        """Reload configuration from disk."""
        try:
            self.config = config.load_config()
            logger.info("Configuration reloaded successfully")
            self._notify(
                "Eloquent Notes",
                "Configuration reloaded successfully.",
            )
        except Exception as e:
            logger.exception("Failed to reload configuration")
            self._notify(
                "Configuration Error",
                f"Failed to reload configuration: {e}",
            )

    def exit_app(self):
        """Clean up and exit the application."""
        logger.info("Exiting application...")
        if self.state == "RECORDING":
            self.recorder.stop()
        self.server.close()
        self.server.removeServer("eloquent_notes_ipc")
        self.tray.hide()
        self.app.quit()
        sys.exit(0)


def main():
    """Daemon entry point — set up logging and launch the tray app."""
    parser = argparse.ArgumentParser(description="Eloquent Notes Daemon")
    parser.add_argument(
        "command", nargs="?", choices=["toggle"], metavar="command",
    )
    args = parser.parse_args()

    config.init_config_dir()

    cfg = config.load_config()
    log_cfg = cfg["logging"]
    setup_logging(
        log_level_str=log_cfg["level"],
        max_mb=log_cfg["max_mb"],
        backup_count=log_cfg["backup_count"],
    )
    logger.info("Starting Eloquent Notes daemon...")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    eloquent_app = EloquentApp(app, start_recording_immediately=(
        args.command == "toggle"
    ))
    eloquent_app.run()


if __name__ == "__main__":
    main()
