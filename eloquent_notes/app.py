"""Eloquent Notes daemon — system tray application.

Manages the recording lifecycle (IDLE → RECORDING → PROCESSING → IDLE),
IPC for single-instance communication, and Obsidian note generation
through a three-phase Ollama pipeline (transcription → rewriting → classification).
"""

import argparse
import copy
import logging
import os
import sys
import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from eloquent_notes import audio, config, config_gui, llm, obsidian, ui
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
        self.active_config = self.config
        self._config_dialog = None
        self._processing_thread = None
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

        config_action = QAction("Configuration", self.menu)
        config_action.triggered.connect(self.show_config_dialog)
        self.menu.addAction(config_action)

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
        if socket and socket.waitForReadyRead(50):
            message = socket.readAll().data().decode("utf-8")
            if message == "toggle":
                self.toggle_action()
            elif message == "reload":
                self.reload_config()
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
        elif self.state in ("STARTING_RECORDING", "PROCESSING"):
            self._notify(
                "Eloquent Notes",
                "System is busy. Please wait.",
            )

    def _preload_model(self):
        ai_cfg = self.active_config["ai"]
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
        self.state = "STARTING_RECORDING"
        self._update_icon("red", "Eloquent Notes (Recording...)")
        logger.info("Starting audio recording...")

        self.active_config = copy.deepcopy(self.config)
        
        # Preload prompts and templates on the main thread to avoid concurrent read/write race conditions
        loaded_files = {}
        for path in [
            config.RETRY_PROMPT_PATH,
            config.TRANSCRIPTION_SYSTEM_PROMPT_PATH,
            config.TRANSCRIPTION_USER_PROMPT_PATH,
            config.REWRITING_SYSTEM_PROMPT_PATH,
            config.REWRITING_USER_PROMPT_PATH,
            config.CLASSIFICATION_SYSTEM_PROMPT_PATH,
            config.CLASSIFICATION_USER_PROMPT_PATH,
            config.STANDALONE_TEMPLATE_PATH,
            config.DAILY_NEW_TEMPLATE_PATH,
            config.DAILY_APPEND_TEMPLATE_PATH,
        ]:
            loaded_files[path] = config.load_file(path)
        self.active_config["_loaded_files"] = loaded_files

        audio_cfg = self.active_config["audio"]

        def run():
            try:
                if audio_cfg["beep_enabled"]:
                    audio.play_beep(
                        frequency=audio_cfg["beep_frequency"],
                        duration=audio_cfg["beep_duration"],
                        sample_rate=audio_cfg["sample_rate"],
                    )
                if self.state == "STARTING_RECORDING":
                    self.recorder = audio.AudioRecorder(
                        sample_rate=audio_cfg["sample_rate"],
                        channels=audio_cfg["channels"],
                    )
                    self.recorder.start()
                    if self.state == "STARTING_RECORDING":
                        self.state = "RECORDING"
                        threading.Thread(
                            target=self._preload_model, daemon=True,
                        ).start()
                    else:
                        self.recorder.stop()
            except Exception as e:
                logger.exception("Failed to start recording")
                self.state = "IDLE"
                self._update_icon("gray", "Eloquent Notes (Idle)")
                self.processing_completed.emit("error", f"Could not start recording: {e}")

        threading.Thread(target=run, daemon=True).start()

    def _stop_recording_and_process(self):
        self.state = "PROCESSING"
        self._update_icon("orange", "Eloquent Notes (Processing...)")
        logger.info("Stopping recording and starting processing...")

        if self.recorder is not None:
            self.recorder.stop()

        self._processing_thread = threading.Thread(target=self._process_audio, daemon=True)
        self._processing_thread.start()

    def _build_vault_context(self):
        """Build the vault context string for the interpretation prompt."""
        obs_cfg = self.active_config["obsidian"]
        if not obs_cfg["vault_context"]:
            return ""

        topics = obsidian.scan_vault_topics(obs_cfg["vault_path"])
        if not topics:
            return ""

        topics_str = ", ".join(topics)
        return (
            f"Known topics in the vault (use as [[WikiLink]] if"
            f" mentioned): {topics_str}\n\n"
        )

    def _process_audio(self):
        """Process recorded audio via the three-phase LLM pipeline.

        Phase 1: Transcribe audio to clean text.
        Phase 2: Rewrite transcription to a structured clean note.
        Phase 3: Classify transcription and extract metadata.
        Then format and save as an Obsidian note.

        Runs in a background thread. Emits processing_completed signal
        to communicate results back to the GUI thread.
        """
        logger.info("Processing recorded audio...")
        try:
            ai_cfg = self.active_config["ai"]
            obs_cfg = self.active_config["obsidian"]
            audio_cfg = self.active_config["audio"]

            if audio_cfg["beep_enabled"]:
                audio.play_beep(
                    frequency=audio_cfg["beep_frequency"],
                    duration=audio_cfg["beep_duration"],
                    sample_rate=audio_cfg["sample_rate"],
                )

            wav_bytes = self.recorder.wav_bytes if self.recorder is not None else None
            if not wav_bytes or len(wav_bytes) <= 44:
                self.processing_completed.emit("empty", "")
                return

            retry_prompt = self.active_config["_loaded_files"][config.RETRY_PROMPT_PATH]

            # --- Phase 1: Transcription ---
            logger.info("Phase 1: Transcribing audio...")
            transcription_result = llm.transcribe_audio(
                ollama_url=ai_cfg["ollama_url"],
                model=ai_cfg["model"],
                system_prompt=self.active_config["_loaded_files"][
                    config.TRANSCRIPTION_SYSTEM_PROMPT_PATH
                ],
                user_prompt=self.active_config["_loaded_files"][
                    config.TRANSCRIPTION_USER_PROMPT_PATH
                ],
                retry_prompt=retry_prompt,
                context_length=ai_cfg["context_length"],
                audio_bytes=wav_bytes,
                keep_alive=ai_cfg["preload_keep_alive"],
                max_retries=ai_cfg["max_retries"],
                timeout=ai_cfg["request_timeout"],
            )

            if (
                transcription_result["empty"]
                or not transcription_result["transcription"].strip()
            ):
                self.processing_completed.emit("empty", "")
                return

            transcription = transcription_result["transcription"]
            logger.info("Transcription: %s", transcription)

            # --- Phase 2: Rewriting ---
            logger.info("Phase 2: Rewriting transcription...")
            rewriting_user_template = self.active_config["_loaded_files"][
                config.REWRITING_USER_PROMPT_PATH
            ]
            rewriting_user_prompt = rewriting_user_template.format(
                transcription=transcription,
            )

            rewrite_result = llm.rewrite_transcription(
                ollama_url=ai_cfg["ollama_url"],
                model=ai_cfg["model"],
                system_prompt=self.active_config["_loaded_files"][
                    config.REWRITING_SYSTEM_PROMPT_PATH
                ],
                user_prompt=rewriting_user_prompt,
                retry_prompt=retry_prompt,
                context_length=ai_cfg["context_length"],
                keep_alive=ai_cfg["preload_keep_alive"],
                max_retries=ai_cfg["max_retries"],
                timeout=ai_cfg["request_timeout"],
            )

            logger.info("Rewriting: title=%s", rewrite_result["title"])

            # --- Phase 3: Classification ---
            logger.info("Phase 3: Classifying transcription...")
            vault_context = self._build_vault_context()
            classification_user_template = self.active_config["_loaded_files"][
                config.CLASSIFICATION_USER_PROMPT_PATH
            ]
            classification_user_prompt = classification_user_template.format(
                transcription=transcription,
                vault_context=vault_context,
            )

            classification_result = llm.classify_transcription(
                ollama_url=ai_cfg["ollama_url"],
                model=ai_cfg["model"],
                system_prompt=self.active_config["_loaded_files"][
                    config.CLASSIFICATION_SYSTEM_PROMPT_PATH
                ],
                user_prompt=classification_user_prompt,
                retry_prompt=retry_prompt,
                context_length=ai_cfg["context_length"],
                keep_alive=ai_cfg["keep_alive"],
                max_retries=ai_cfg["max_retries"],
                timeout=ai_cfg["request_timeout"],
            )

            logger.info(
                "Classification: type=%s, wikilinks=%s, tags=%s",
                classification_result["type"],
                classification_result["wikilinks"],
                classification_result["tags"],
            )

            # --- Assemble and save ---
            formatted_text = obsidian.format_note_content(
                note_type=classification_result["type"],
                content=rewrite_result["content"],
                wikilinks=classification_result["wikilinks"],
            )

            saved_path = obsidian.save_note(
                vault_path=obs_cfg["vault_path"],
                folder=obs_cfg["folder"],
                daily_notes=obs_cfg["daily_notes"],
                title=rewrite_result["title"],
                text=formatted_text,
                tags=classification_result["tags"],
                template_standalone=self.active_config["_loaded_files"][
                    config.STANDALONE_TEMPLATE_PATH
                ],
                template_daily_new=self.active_config["_loaded_files"][
                    config.DAILY_NEW_TEMPLATE_PATH
                ],
                template_daily_append=self.active_config["_loaded_files"][
                    config.DAILY_APPEND_TEMPLATE_PATH
                ],
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
            log_cfg = self.config["logging"]
            setup_logging(
                log_level_str=log_cfg["level"],
                max_mb=log_cfg["max_mb"],
                backup_count=log_cfg["backup_count"],
            )
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

    def show_config_dialog(self):
        """Show the configuration dialog, creating it if necessary."""
        if self._config_dialog is not None:
            self._config_dialog.raise_()
            self._config_dialog.activateWindow()
            return

        self._config_dialog = config_gui.ConfigurationDialog()
        self._config_dialog.accepted.connect(self.reload_config)
        self._config_dialog.finished.connect(self._on_config_dialog_closed)
        self._config_dialog.show()

    def _on_config_dialog_closed(self, _result):
        if self._config_dialog is not None:
            self._config_dialog.deleteLater()
            QTimer.singleShot(0, self._clear_config_dialog_reference)

    def _clear_config_dialog_reference(self):
        self._config_dialog = None

    def exit_app(self):
        """Clean up and exit the application."""
        logger.info("Exiting application...")
        prev_state = self.state
        self.state = "IDLE"

        if prev_state in ("RECORDING", "STARTING_RECORDING"):
            if self.recorder is not None:
                self.recorder.stop()
        elif prev_state == "PROCESSING" and self._processing_thread is not None:
            self._processing_thread.join(timeout=5.0)

        if self._config_dialog is not None:
            self._config_dialog.close()
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
