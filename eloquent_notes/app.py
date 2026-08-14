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
    capture_timeout = pyqtSignal()

    def __init__(self, qapp, start_recording_immediately=False):
        super().__init__()
        self.app = qapp
        self._lock = threading.Lock()
        self._state = "IDLE"
        self._recorder = None
        self._capture_timer = None
        self.config = config.load_config()
        self.active_config = self.config
        self._config_dialog = None
        self._processing_thread = None
        self.start_recording_immediately = start_recording_immediately
        self.server = None
        self.tray = None

        self.processing_completed.connect(self._on_processing_completed)
        self.capture_timeout.connect(self._stop_recording_and_process)

    @property
    def state(self):
        with self._lock:
            return self._state

    @state.setter
    def state(self, value):
        with self._lock:
            self._state = value

    @property
    def recorder(self):
        with self._lock:
            return self._recorder

    @recorder.setter
    def recorder(self, value):
        with self._lock:
            self._recorder = value

    def run(self):
        """Set up the system tray, IPC server, and enter the event loop."""
        self.tray = QSystemTrayIcon()
        self._init_ipc_server()
        self._init_tray_ui()

        if self.start_recording_immediately:
            QTimer.singleShot(100, self.toggle_action)

        sys.exit(self.app.exec())

    def _init_ipc_server(self):
        self.server = QLocalServer(self)
        self.server.removeServer("eloquent_notes_ipc")
        if not self.server.listen("eloquent_notes_ipc"):
            logger.error("Failed to start local IPC server.")
        self.server.newConnection.connect(self._handle_ipc_connection)

    def _init_tray_ui(self):
        self.menu = self._create_tray_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)
        self._update_icon("gray", "Eloquent Notes (Idle)")
        self.tray.show()

    def _create_tray_menu(self):
        menu = QMenu()

        toggle_action = QAction("Start/Stop Recording", menu)
        font = toggle_action.font()
        font.setBold(True)
        toggle_action.setFont(font)
        toggle_action.triggered.connect(self.toggle_action)
        menu.addAction(toggle_action)

        config_action = QAction("Configuration", menu)
        config_action.triggered.connect(self.show_config_dialog)
        menu.addAction(config_action)

        reload_action = QAction("Reload Configuration", menu)
        reload_action.triggered.connect(self.reload_config)
        menu.addAction(reload_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.exit_app)
        menu.addAction(quit_action)

        return menu

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_action()

    def _handle_ipc_connection(self):
        if self.server is None:
            return
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is None:
                break
            try:
                if socket.bytesAvailable() > 0 or socket.waitForReadyRead(50):
                    message = bytes(socket.readAll()).decode("utf-8")
                    if message == "toggle":
                        self.toggle_action()
                    elif message == "reload":
                        self.reload_config()
                    elif message == "notify_running":
                        self._notify(
                            "Eloquent Notes",
                            "Eloquent Notes is already running in the background.",
                        )
            finally:
                socket.disconnectFromServer()
                socket.deleteLater()

    def _update_icon(self, color, tooltip):
        if self.tray is not None:
            self.tray.setIcon(ui.get_qicon(color))
            self.tray.setToolTip(tooltip)

    def _notify(self, title, message):
        if self.tray is not None:
            self.tray.showMessage(
                title, message,
                QSystemTrayIcon.MessageIcon.Information, 5000,
            )

    def toggle_action(self):
        """Handle toggle: start, stop, or notify if already processing."""
        current_state = self.state
        if current_state == "IDLE":
            self._start_recording()
        elif current_state == "RECORDING":
            self._stop_recording_and_process()
        elif current_state in ("STARTING_RECORDING", "PROCESSING"):
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
        with self._lock:
            if self._state != "IDLE":
                return
            self._state = "STARTING_RECORDING"

        self._update_icon("red", "Eloquent Notes (Recording...)")
        logger.info("Starting audio recording...")

        self.active_config = copy.deepcopy(self.config)
        self.active_config["_loaded_files"] = {
            path: config.load_file(path)
            for path in config.PROMPT_AND_TEMPLATE_PATHS
        }

        audio_cfg = self.active_config["audio"]

        def run():
            try:
                if audio_cfg["beep_enabled"]:
                    audio.play_beep(
                        frequency=audio_cfg["beep_frequency"],
                        duration=audio_cfg["beep_duration"],
                        sample_rate=audio_cfg["sample_rate"],
                    )
                with self._lock:
                    if self._state == "STARTING_RECORDING":
                        rec = audio.AudioRecorder(
                            sample_rate=audio_cfg["sample_rate"],
                            channels=audio_cfg["channels"],
                        )
                        self._recorder = rec
                    else:
                        rec = None

                if rec is not None:
                    rec.start()
                    with self._lock:
                        if self._state == "STARTING_RECORDING":
                            self._state = "RECORDING"
                            should_preload = True
                        else:
                            should_preload = False
                            rec.stop()
                    if should_preload:
                        self._start_capture_timer(audio_cfg["capture_duration"])
                        threading.Thread(
                            target=self._preload_model, daemon=True,
                        ).start()
            except Exception as e:
                logger.exception("Failed to start recording")
                self.processing_completed.emit("error", f"Could not start recording: {e}")

        threading.Thread(target=run, daemon=True).start()

    def _start_capture_timer(self, duration):
        """Start timer to automatically stop recording after max duration."""
        with self._lock:
            if self._capture_timer is not None:
                self._capture_timer.cancel()
            if duration > 0:
                self._capture_timer = threading.Timer(duration, self._on_capture_timeout)
                self._capture_timer.daemon = True
                self._capture_timer.start()
            else:
                self._capture_timer = None

    def _cancel_capture_timer(self):
        """Cancel active capture timer if any."""
        with self._lock:
            timer = self._capture_timer
            self._capture_timer = None
        if timer is not None:
            timer.cancel()

    def _on_capture_timeout(self):
        """Handle maximum capture duration timeout."""
        logger.info("Maximum capture duration reached, stopping recording...")
        self.capture_timeout.emit()

    def _stop_recording_and_process(self):
        self._cancel_capture_timer()
        with self._lock:
            if self._state != "RECORDING":
                return
            self._state = "PROCESSING"
            rec = self._recorder

        self._update_icon("orange", "Eloquent Notes (Processing...)")
        logger.info("Stopping recording and starting processing...")

        if rec is not None:
            rec.stop()

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

    def _get_recorded_wav_bytes(self):
        with self._lock:
            rec = self._recorder
        return rec.wav_bytes if rec is not None else None

    def _format_language_instruction(self, target_language):
        return (
            f"IMPORTANT: You MUST write the title, content, wikilinks, and tags in {target_language}. "
            f"DO NOT translate to any other language."
        )

    def _transcribe(self, ai_cfg, wav_bytes, retry_prompt):
        return llm.transcribe_audio(
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

    def _rewrite(self, ai_cfg, transcription, language_instruction, retry_prompt):
        rewriting_user_template = self.active_config["_loaded_files"][
            config.REWRITING_USER_PROMPT_PATH
        ]
        rewriting_user_prompt = rewriting_user_template.format(
            transcription=transcription,
            language_instruction=language_instruction,
        )
        return llm.rewrite_transcription(
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

    def _classify(self, ai_cfg, transcription, language_instruction, retry_prompt):
        vault_context = self._build_vault_context()
        classification_user_template = self.active_config["_loaded_files"][
            config.CLASSIFICATION_USER_PROMPT_PATH
        ]
        classification_user_prompt = classification_user_template.format(
            transcription=transcription,
            vault_context=vault_context,
            language_instruction=language_instruction,
        )
        return llm.classify_transcription(
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

    def _save_formatted_note(self, obs_cfg, rewrite_result, classification_result):
        formatted_text = obsidian.format_note_content(
            note_type=classification_result["type"],
            content=rewrite_result["content"],
            wikilinks=classification_result["wikilinks"],
        )
        return obsidian.save_note(
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

            wav_bytes = self._get_recorded_wav_bytes()
            if not wav_bytes or len(wav_bytes) <= 44:
                self.processing_completed.emit("empty", "")
                return

            retry_prompt = self.active_config["_loaded_files"][config.RETRY_PROMPT_PATH]

            # --- Phase 1: Transcription ---
            logger.info("Phase 1: Transcribing audio...")
            transcription_result = self._transcribe(ai_cfg, wav_bytes, retry_prompt)
            transcription = transcription_result["transcription"].strip()
            if transcription_result["empty"] or not transcription:
                self.processing_completed.emit("empty", "")
                return

            logger.info("Transcription: %s", transcription)

            target_language = ai_cfg.get("output_language", "English")
            language_instruction = self._format_language_instruction(target_language)

            # --- Phase 2: Rewriting ---
            logger.info("Phase 2: Rewriting transcription...")
            rewrite_result = self._rewrite(
                ai_cfg, transcription, language_instruction, retry_prompt,
            )
            logger.info("Rewriting: title=%s", rewrite_result["title"])

            # --- Phase 3: Classification ---
            logger.info("Phase 3: Classifying transcription...")
            classification_result = self._classify(
                ai_cfg, transcription, language_instruction, retry_prompt,
            )
            logger.info(
                "Classification: type=%s, wikilinks=%s, tags=%s",
                classification_result["type"],
                classification_result["wikilinks"],
                classification_result["tags"],
            )

            # --- Assemble and save ---
            saved_path = self._save_formatted_note(
                obs_cfg, rewrite_result, classification_result,
            )
            self.processing_completed.emit("success", saved_path)

        except Exception as e:
            logger.exception("Error during audio processing/saving")
            self.processing_completed.emit("error", str(e))


    def _on_processing_completed(self, status, detail):
        self._cancel_capture_timer()
        self.state = "IDLE"
        self.recorder = None
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
            dialog = self._config_dialog
            self._config_dialog = None
            dialog.deleteLater()

    def exit_app(self):
        """Clean up and exit the application."""
        logger.info("Exiting application...")
        self._cancel_capture_timer()
        with self._lock:
            prev_state = self._state
            self._state = "IDLE"
            rec = self._recorder
            self._recorder = None

        if prev_state in ("RECORDING", "STARTING_RECORDING") and rec is not None:
            rec.stop()
        elif prev_state == "PROCESSING" and self._processing_thread is not None:
            self._processing_thread.join(timeout=5.0)

        if self._config_dialog is not None:
            self._config_dialog.close()
        if self.server is not None:
            self.server.close()
            QLocalServer.removeServer("eloquent_notes_ipc")
        if self.tray is not None:
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
