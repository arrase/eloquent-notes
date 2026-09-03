"""Eloquent Notes daemon — system tray application.

Owns the recording lifecycle (IDLE → RECORDING → PROCESSING → IDLE),
the single-instance IPC server, and the three-phase Ollama pipeline
(transcription → rewriting → classification) that produces Obsidian notes.

All state changes happen on the Qt main thread; only model preloading and
audio processing run on background threads and report back through the
processing_completed signal.
"""

import argparse
import copy
import logging
import os
import sys
import threading
import time

import requests
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from eloquent_notes import (
    IPC_SERVER_NAME,
    audio,
    config,
    config_gui,
    llm,
    obsidian,
    recording_hud,
    ui,
)
from eloquent_notes.logging_utils import setup_logging

logger = logging.getLogger("eloquent_notes.app")

IDLE = "IDLE"
RECORDING = "RECORDING"
PROCESSING = "PROCESSING"


class EloquentApp(QObject):
    """Main application controller for the system tray dictation tool."""

    processing_completed = pyqtSignal(str, str)

    def __init__(self, qapp, start_recording_immediately=False, app_config=None):
        super().__init__()
        self.app = qapp
        self.state = IDLE
        self.config = app_config if app_config is not None else config.load_config()
        self.tray = None
        self.menu = None
        self.server = None

        self._snapshot = None  # config + prompt files frozen at recording start
        self._recorder = None
        self._processing_thread = None
        self._config_dialog = None
        self._capture_duration = 0.0
        self._recording_started_at = 0.0

        self._hud = recording_hud.RecordingHUD()
        self._hud.clicked.connect(self.toggle_action)

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._on_recording_tick)

        self.processing_completed.connect(self._on_processing_completed)

        if start_recording_immediately:
            QTimer.singleShot(100, self.toggle_action)

    # --- UI setup ---------------------------------------------------------

    def run(self):
        """Set up the system tray, IPC server, and enter the event loop."""
        self.tray = QSystemTrayIcon()
        self._init_ipc_server()
        self._init_tray_ui()
        sys.exit(self.app.exec())

    def _init_ipc_server(self):
        self.server = QLocalServer(self)
        QLocalServer.removeServer(IPC_SERVER_NAME)
        if not self.server.listen(IPC_SERVER_NAME):
            error_msg = f"Failed to start local IPC server: {self.server.errorString()}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
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

        settings_action = QAction("Configuration", menu)
        settings_action.triggered.connect(self.show_config_dialog)
        menu.addAction(settings_action)

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

    # --- Recording lifecycle (main thread) ---------------------------------

    def toggle_action(self):
        """Start recording, stop and process, or notify that we are busy."""
        if self.state == IDLE:
            self._start_recording()
        elif self.state == RECORDING:
            self._stop_and_process()
        else:
            self._notify("Eloquent Notes", "System is busy. Please wait.")

    def _start_recording(self):
        snapshot = copy.deepcopy(self.config)
        snapshot["_loaded_files"] = {
            path: config.load_file(path)
            for path in config.PROMPT_AND_TEMPLATE_PATHS
        }
        audio_cfg = snapshot["audio"]

        self._update_icon("red", "Eloquent Notes (Recording...)")
        logger.info("Starting audio recording...")
        try:
            if audio_cfg["beep_enabled"]:
                # Played synchronously so the tone finishes before the
                # microphone opens and cannot leak into the recording.
                audio.play_beep(
                    frequency=audio_cfg["beep_frequency"],
                    duration=audio_cfg["beep_duration"],
                    sample_rate=audio_cfg["sample_rate"],
                )
            recorder = audio.AudioRecorder(
                sample_rate=audio_cfg["sample_rate"],
                channels=audio_cfg["channels"],
            )
            recorder.start()
        except Exception as e:
            logger.exception("Failed to start recording")
            self.processing_completed.emit("error", f"Could not start recording: {e}")
            return

        self.state = RECORDING
        self._snapshot = snapshot
        self._recorder = recorder
        self._capture_duration = float(audio_cfg["capture_duration"])
        self._recording_started_at = time.monotonic()

        if audio_cfg["recording_hud_enabled"]:
            self._hud.show_recording(self._capture_duration)
        self._tick_timer.start(100)

        threading.Thread(
            target=self._preload_model, args=(snapshot,), daemon=True,
        ).start()

    def _preload_model(self, snapshot):
        """Warm the model weights while the user dictates (best effort)."""
        ai_cfg = snapshot["ai"]
        try:
            llm.preload_model(
                ollama_url=ai_cfg["ollama_url"],
                model=ai_cfg["model"],
                context_length=ai_cfg["context_length"],
                keep_alive=ai_cfg["preload_keep_alive"],
                timeout=ai_cfg["preload_timeout"],
            )
        except requests.RequestException as e:
            logger.warning("Model preload skipped: %s", e)

    def _on_recording_tick(self):
        if self.state != RECORDING:
            self._tick_timer.stop()
            return

        elapsed = time.monotonic() - self._recording_started_at
        remaining = max(0.0, self._capture_duration - elapsed)
        if self._hud.isVisible():
            self._hud.update_progress(elapsed, remaining, self._capture_duration)

        if self._capture_duration > 0 and elapsed >= self._capture_duration:
            logger.info("Maximum capture duration reached, stopping recording...")
            self._stop_and_process()

    def _stop_and_process(self):
        if self.state != RECORDING:
            return
        self.state = PROCESSING
        self._tick_timer.stop()
        self._hud.hide_hud()

        recorder, snapshot = self._recorder, self._snapshot
        self._recorder = None
        self._snapshot = None

        self._update_icon("orange", "Eloquent Notes (Processing...)")
        logger.info("Stopping recording and starting processing...")

        audio_cfg = snapshot["audio"]
        if audio_cfg["beep_enabled"]:
            audio.play_beep(
                frequency=audio_cfg["beep_frequency"],
                duration=audio_cfg["beep_duration"],
                sample_rate=audio_cfg["sample_rate"],
                wait=False,
            )
        recorder.stop()

        self._processing_thread = threading.Thread(
            target=self._process_audio, args=(recorder, snapshot), daemon=True,
        )
        self._processing_thread.start()

    # --- Processing pipeline (background thread) ---------------------------

    @staticmethod
    def _language_instruction(target_language):
        return (
            f"IMPORTANT: You MUST write the title, content, wikilinks, and tags "
            f"in {target_language}. DO NOT translate to any other language."
        )

    @staticmethod
    def _build_vault_context(obs_cfg):
        """Build the vault context string for the classification prompt."""
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

    @staticmethod
    def _transcribe(ai_cfg, loaded, wav_bytes):
        return llm.transcribe_audio(
            ollama_url=ai_cfg["ollama_url"],
            model=ai_cfg["model"],
            system_prompt=loaded[config.TRANSCRIPTION_SYSTEM_PROMPT_PATH],
            user_prompt=loaded[config.TRANSCRIPTION_USER_PROMPT_PATH],
            retry_prompt=loaded[config.RETRY_PROMPT_PATH],
            context_length=ai_cfg["context_length"],
            audio_bytes=wav_bytes,
            keep_alive=ai_cfg["preload_keep_alive"],
            max_retries=ai_cfg["max_retries"],
            timeout=ai_cfg["request_timeout"],
        )

    @staticmethod
    def _rewrite(ai_cfg, loaded, transcription, language_instruction):
        user_prompt = loaded[config.REWRITING_USER_PROMPT_PATH].format(
            transcription=transcription,
            language_instruction=language_instruction,
        )
        return llm.rewrite_transcription(
            ollama_url=ai_cfg["ollama_url"],
            model=ai_cfg["model"],
            system_prompt=loaded[config.REWRITING_SYSTEM_PROMPT_PATH],
            user_prompt=user_prompt,
            retry_prompt=loaded[config.RETRY_PROMPT_PATH],
            context_length=ai_cfg["context_length"],
            keep_alive=ai_cfg["preload_keep_alive"],
            max_retries=ai_cfg["max_retries"],
            timeout=ai_cfg["request_timeout"],
        )

    def _classify(self, ai_cfg, obs_cfg, loaded, transcription, language_instruction):
        user_prompt = loaded[config.CLASSIFICATION_USER_PROMPT_PATH].format(
            transcription=transcription,
            vault_context=self._build_vault_context(obs_cfg),
            language_instruction=language_instruction,
        )
        return llm.classify_transcription(
            ollama_url=ai_cfg["ollama_url"],
            model=ai_cfg["model"],
            system_prompt=loaded[config.CLASSIFICATION_SYSTEM_PROMPT_PATH],
            user_prompt=user_prompt,
            retry_prompt=loaded[config.RETRY_PROMPT_PATH],
            context_length=ai_cfg["context_length"],
            keep_alive=ai_cfg["keep_alive"],
            max_retries=ai_cfg["max_retries"],
            timeout=ai_cfg["request_timeout"],
        )

    @staticmethod
    def _save_note(snapshot, obs_cfg, rewrite, classification):
        formatted_text = obsidian.format_note_content(
            note_type=classification["type"],
            content=rewrite["content"],
            wikilinks=classification["wikilinks"],
        )
        loaded = snapshot["_loaded_files"]
        return obsidian.save_note(
            vault_path=obs_cfg["vault_path"],
            folder=obs_cfg["folder"],
            daily_notes=obs_cfg["daily_notes"],
            folder_organization=obs_cfg["folder_organization"],
            title=rewrite["title"],
            text=formatted_text,
            tags=classification["tags"],
            template_standalone=loaded[config.STANDALONE_TEMPLATE_PATH],
            template_daily_new=loaded[config.DAILY_NEW_TEMPLATE_PATH],
            template_daily_append=loaded[config.DAILY_APPEND_TEMPLATE_PATH],
        )

    def _process_audio(self, recorder, snapshot):
        """Run the three-phase pipeline over the recorded audio.

        Executes on a background thread with the state frozen at recording
        start, and reports the outcome via processing_completed.
        """
        logger.info("Processing recorded audio...")
        loaded = snapshot["_loaded_files"]
        try:
            ai_cfg = snapshot["ai"]
            obs_cfg = snapshot["obsidian"]

            wav_bytes = recorder.wav_bytes
            if not wav_bytes:
                self.processing_completed.emit("empty", "")
                return

            logger.info("Phase 1: Transcribing audio...")
            transcription_result = self._transcribe(ai_cfg, loaded, wav_bytes)
            transcription = transcription_result["transcription"].strip()
            if transcription_result["empty"] or not transcription:
                self.processing_completed.emit("empty", "")
                return
            logger.info("Transcription: %s", transcription)

            language_instruction = self._language_instruction(ai_cfg["output_language"])

            logger.info("Phase 2: Rewriting transcription...")
            rewrite = self._rewrite(ai_cfg, loaded, transcription, language_instruction)
            logger.info("Rewriting: title=%s", rewrite["title"])

            logger.info("Phase 3: Classifying transcription...")
            classification = self._classify(
                ai_cfg, obs_cfg, loaded, transcription, language_instruction,
            )
            logger.info(
                "Classification: type=%s, wikilinks=%s, tags=%s",
                classification["type"],
                classification["wikilinks"],
                classification["tags"],
            )

            saved_path = self._save_note(snapshot, obs_cfg, rewrite, classification)
            self.processing_completed.emit("success", saved_path)
        except Exception as e:
            logger.exception("Error during audio processing/saving")
            self.processing_completed.emit("error", str(e))

    # --- Completion, reload and shutdown -----------------------------------

    def _on_processing_completed(self, status, detail):
        self._tick_timer.stop()
        self._hud.hide_hud()
        self.state = IDLE
        self._recorder = None
        self._snapshot = None
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
        self._tick_timer.stop()
        self._hud.hide_hud()
        self._hud.close()

        if self.state == RECORDING and self._recorder is not None:
            self._recorder.stop()
        elif self.state == PROCESSING and self._processing_thread is not None:
            self._processing_thread.join(timeout=5.0)

        if self._config_dialog is not None:
            self._config_dialog.close()
        if self.server is not None:
            self.server.close()
            QLocalServer.removeServer(IPC_SERVER_NAME)
        if self.tray is not None:
            self.tray.hide()
        self.app.quit()
        sys.exit(0)


def main():
    """Daemon entry point — configure logging and launch the tray app."""
    parser = argparse.ArgumentParser(description="Eloquent Notes Daemon")
    parser.add_argument(
        "command", nargs="?", choices=["toggle"], metavar="command",
    )
    args = parser.parse_args()

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

    eloquent_app = EloquentApp(
        app,
        start_recording_immediately=(args.command == "toggle"),
        app_config=cfg,
    )
    eloquent_app.run()


if __name__ == "__main__":
    main()
