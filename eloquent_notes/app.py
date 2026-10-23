"""Eloquent Notes daemon — system tray application and notes window.

Owns the recording lifecycle (IDLE → RECORDING → PROCESSING → IDLE),
the single-instance IPC server, the three-phase Ollama pipeline
(transcription → rewriting → classification) that turns dictations into
Markdown notes, and the notes window.

All state changes happen on the Qt main thread; only model preloading,
audio processing and semantic search run on background threads and report
back through signals.
"""

import argparse
import copy
import logging
import sys
import threading
import time
from pathlib import Path

import requests
from PyQt6.QtCore import QFile, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from eloquent_notes import (
    IDLE,
    IPC_SERVER_NAME,
    PROCESSING,
    RECORDING,
    audio,
    autostart,
    config,
    config_gui,
    llm,
    notes,
    recording_hud,
    ui,
)
from eloquent_notes.i18n import _
from eloquent_notes.logging_utils import setup_logging
from eloquent_notes.search import SemanticIndex
from eloquent_notes.window import MainWindow

logger = logging.getLogger("eloquent_notes.app")

APP_NAME = "Eloquent Notes"


class SafeDict(dict):
    """Dict that leaves unknown prompt placeholders untouched (e.g. {unknown} stays {unknown})."""

    def __missing__(self, key):
        return f"{{{key}}}"


class EloquentApp(QObject):
    """Main application controller for the system tray dictation tool."""

    processing_completed = pyqtSignal(str, str)
    search_completed = pyqtSignal(str, list)
    search_failed = pyqtSignal(str, str)

    def __init__(self, qapp, start_recording_immediately=False, open_window_immediately=False, app_config=None):
        super().__init__()
        self.app = qapp
        self.app.setApplicationName("eloquent-notes")
        self.app.setApplicationDisplayName(APP_NAME)
        self.app.setDesktopFileName("eloquent-notes")
        self.app.setWindowIcon(ui.get_app_icon())
        self.state = IDLE
        self.config = app_config if app_config is not None else config.load_config()
        self.tray = None
        self.menu = None
        self.server = None
        self.window = None

        self._start_recording_immediately = start_recording_immediately
        self._open_window_immediately = open_window_immediately
        self._snapshot = None  # config + prompt files frozen at recording start
        self._recorder = None
        self._append_target = None  # note that receives the current dictation, if any
        self._preload_thread = None
        self._processing_thread = None
        self._config_dialog = None
        self._capture_duration = 0.0
        self._recording_started_at = 0.0
        self._index = SemanticIndex()

        self._hud = recording_hud.RecordingHUD()
        self._hud.clicked.connect(self.toggle_action)

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._on_recording_tick)

        self.processing_completed.connect(self._on_processing_completed)
        self.search_completed.connect(self._on_search_completed)
        self.search_failed.connect(self._on_search_failed)

    # --- UI setup ---------------------------------------------------------

    def run(self):
        """Set up the system tray, IPC server, and enter the event loop."""
        self.tray = QSystemTrayIcon()
        self._init_ipc_server()
        self._init_tray_ui()
        if self._start_recording_immediately:
            QTimer.singleShot(100, self.toggle_action)
        if self._open_window_immediately:
            QTimer.singleShot(100, self.show_window)
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
        self.tray.messageClicked.connect(self.show_window)
        self._update_icon("gray", _("Eloquent Notes (Idle)"))
        self.tray.show()

    def _create_tray_menu(self):
        menu = QMenu()

        toggle_action = QAction(_("Start/Stop Recording"), menu)
        font = toggle_action.font()
        font.setBold(True)
        toggle_action.setFont(font)
        toggle_action.triggered.connect(self.toggle_action)
        menu.addAction(toggle_action)

        open_action = QAction(_("Open Notes"), menu)
        open_action.triggered.connect(self.show_window)
        menu.addAction(open_action)

        settings_action = QAction(_("Configuration"), menu)
        settings_action.triggered.connect(self.show_config_dialog)
        menu.addAction(settings_action)

        reload_action = QAction(_("Reload Configuration"), menu)
        reload_action.triggered.connect(self.reload_config)
        menu.addAction(reload_action)

        menu.addSeparator()

        quit_action = QAction(_("Quit"), menu)
        quit_action.triggered.connect(self.exit_app)
        menu.addAction(quit_action)

        return menu

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_action()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            if self.window is not None and self.window.isVisible():
                self.window.close()
            else:
                self.show_window()

    def _handle_ipc_connection(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            try:
                if socket.bytesAvailable() > 0 or socket.waitForReadyRead(50):
                    message = bytes(socket.readAll()).decode("utf-8", errors="replace")
                    if message == "toggle":
                        self.toggle_action()
                    elif message == "open":
                        self.show_window()
                    elif message == "reload":
                        self.reload_config()
            finally:
                socket.disconnectFromServer()
                socket.deleteLater()

    def _update_icon(self, color, tooltip):
        if self.tray is not None:
            self.tray.setIcon(ui.get_qicon(color))
            self.tray.setToolTip(tooltip)
        if self.window is not None:
            self.window.set_state(self.state)

    def _notify(self, title, message):
        if self.tray is not None:
            self.tray.showMessage(
                title, message,
                QSystemTrayIcon.MessageIcon.Information, 5000,
            )

    @staticmethod
    def _play_beep(audio_cfg, wait):
        if not audio_cfg["beep_enabled"]:
            return
        try:
            audio.play_beep(
                frequency=audio_cfg["beep_frequency"],
                duration=audio_cfg["beep_duration"],
                sample_rate=audio_cfg["sample_rate"],
                wait=wait,
            )
        except Exception as e:
            logger.warning("Audio feedback beep failed: %s", e)

    # --- Notes window (main thread) ----------------------------------------

    def _notes_folder(self):
        return Path(self.config["notes"]["folder"]).expanduser()

    def show_window(self):
        """Show the notes window, creating it on first use."""
        if self.window is None:
            self.window = MainWindow(columns=self.config["notes"]["columns"])
            self.window.dictate_clicked.connect(self.dictate_into)
            self.window.note_edited.connect(self._on_note_edited)
            self.window.delete_requested.connect(self._on_delete_requested)
            self.window.search_requested.connect(self._start_search)
            self.window.settings_clicked.connect(self.show_config_dialog)
            self.window.set_state(self.state)
        self.window.show_timeline()
        self._refresh_window()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _refresh_window(self):
        if self.window is not None:
            self.window.set_columns(self.config["notes"]["columns"])
            self.window.set_notes(notes.load_notes(self._notes_folder()))

    def _on_note_edited(self, note):
        notes.save_note(note)
        self._refresh_window()

    def _on_delete_requested(self, note):
        if self._append_target is not None and self._append_target.path == note.path:
            self._append_target = None
        if not QFile.moveToTrash(str(note.path)):
            self._notify(
                _("Delete Failed"),
                _("Could not move {name} to the trash.").format(name=note.path.name),
            )
        self._refresh_window()

    def _start_search(self, query):
        threading.Thread(
            target=self._run_search,
            args=(query, self._notes_folder(), copy.deepcopy(self.config)),
            daemon=True,
        ).start()

    def _run_search(self, query, folder, cfg):
        try:
            results = self._index.search(notes.load_notes(folder), query, cfg)
        except Exception as e:
            logger.exception("Semantic search failed")
            self.search_failed.emit(query, str(e))
            return
        self.search_completed.emit(query, results)

    def _on_search_completed(self, query, results):
        if self.window is not None:
            self.window.show_search_results(query, results)

    def _on_search_failed(self, query, message):
        if self.window is not None:
            self.window.show_search_error(query, message)

    # --- Recording lifecycle (main thread) ---------------------------------

    def toggle_action(self):
        """Start recording a new note, stop and process, or notify that we are busy."""
        if self.state == IDLE:
            self._append_target = None
            self._start_recording()
        elif self.state == RECORDING:
            self._stop_and_process()
        else:
            self._notify(APP_NAME, _("System is busy. Please wait."))

    def dictate_into(self, note):
        """Start recording a dictation that will be appended to note, or stop the current one."""
        if self.state == IDLE:
            self._append_target = note
            self._start_recording()
        else:
            self.toggle_action()

    def _start_recording(self):
        logger.info("Starting audio recording...")
        try:
            snapshot = copy.deepcopy(self.config)
            snapshot["_loaded_files"] = {
                path: config.load_file(path)
                for path in config.PROMPT_PATHS
            }
            audio_cfg = snapshot["audio"]
            # Played synchronously so the tone finishes before the
            # microphone opens and cannot leak into the recording.
            self._play_beep(audio_cfg, wait=True)
            recorder = audio.AudioRecorder(
                sample_rate=audio_cfg["sample_rate"],
                channels=audio_cfg["channels"],
            )
            recorder.start()
        except Exception as e:
            logger.exception("Failed to start recording")
            self.processing_completed.emit("error", _("Could not start recording: {error}").format(error=e))
            return

        self.state = RECORDING
        self._snapshot = snapshot
        self._recorder = recorder
        self._capture_duration = float(audio_cfg["capture_duration"])
        self._recording_started_at = time.monotonic()

        self._update_icon("red", _("Eloquent Notes (Recording...)"))
        if audio_cfg["recording_hud_enabled"]:
            self._hud.show_recording(self._capture_duration)
        self._tick_timer.start(100)

        if self._preload_thread is None or not self._preload_thread.is_alive():
            self._preload_thread = threading.Thread(
                target=self._preload_model, args=(snapshot,), daemon=True,
            )
            self._preload_thread.start()

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
        except (requests.RequestException, ValueError) as e:
            logger.warning("Model preload skipped: %s", e)

    def _on_recording_tick(self):
        if self.state != RECORDING:
            self._tick_timer.stop()
            return

        elapsed = time.monotonic() - self._recording_started_at
        remaining = max(0.0, self._capture_duration - elapsed)
        if self._hud.isVisible():
            self._hud.update_progress(elapsed, remaining, self._capture_duration)

        if elapsed >= self._capture_duration:
            logger.info("Maximum capture duration reached, stopping recording...")
            self._stop_and_process()

    def _stop_and_process(self):
        self.state = PROCESSING
        self._tick_timer.stop()
        self._hud.hide()

        recorder, snapshot = self._recorder, self._snapshot
        self._recorder = None
        self._snapshot = None

        logger.info("Stopping recording and starting processing...")
        try:
            recorder.stop()
        except Exception as e:
            logger.exception("Failed to stop recording")
            self.processing_completed.emit("error", _("Could not stop recording: {error}").format(error=e))
            return

        self._play_beep(snapshot["audio"], wait=False)
        self._update_icon("orange", _("Eloquent Notes (Processing...)"))

        self._processing_thread = threading.Thread(
            target=self._process_audio,
            args=(recorder, snapshot, self._append_target is not None),
            daemon=True,
        )
        self._processing_thread.start()

    # --- Processing pipeline (background thread) ---------------------------

    @staticmethod
    def _language_instruction(target_language):
        return (
            f"IMPORTANT: You MUST write the title, content, and tags "
            f"in {target_language}, translating from the transcription language if necessary."
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
    def _rewrite(ai_cfg, loaded, transcription, language_instruction, keep_alive):
        user_prompt = loaded[config.REWRITING_USER_PROMPT_PATH].format_map(
            SafeDict(
                transcription=transcription,
                language_instruction=language_instruction,
            )
        )
        return llm.rewrite_transcription(
            ollama_url=ai_cfg["ollama_url"],
            model=ai_cfg["model"],
            system_prompt=loaded[config.REWRITING_SYSTEM_PROMPT_PATH],
            user_prompt=user_prompt,
            retry_prompt=loaded[config.RETRY_PROMPT_PATH],
            context_length=ai_cfg["context_length"],
            keep_alive=keep_alive,
            max_retries=ai_cfg["max_retries"],
            timeout=ai_cfg["request_timeout"],
        )

    @staticmethod
    def _classify(ai_cfg, loaded, content, language_instruction):
        user_prompt = loaded[config.CLASSIFICATION_USER_PROMPT_PATH].format_map(
            SafeDict(
                transcription=content,
                content=content,
                language_instruction=language_instruction,
            )
        )
        return llm.classify_note(
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

    def _reset_keep_alive(self, ai_cfg):
        if self._preload_thread is not None and self._preload_thread.is_alive():
            self._preload_thread.join(timeout=ai_cfg["preload_timeout"])
        try:
            llm.preload_model(
                ollama_url=ai_cfg["ollama_url"],
                model=ai_cfg["model"],
                context_length=ai_cfg["context_length"],
                keep_alive=ai_cfg["keep_alive"],
                timeout=ai_cfg["preload_timeout"],
            )
        except (requests.RequestException, ValueError) as e:
            logger.warning("Model keep_alive reset skipped: %s", e)

    def _process_audio(self, recorder, snapshot, append):
        """Run the pipeline over the recorded audio.

        Executes on a background thread with the state frozen at recording
        start, and reports the outcome via processing_completed. Appended
        dictations stop after rewriting: the target note keeps its type and
        tags, and the main thread writes the text into it.
        """
        logger.info("Processing recorded audio...")
        loaded = snapshot["_loaded_files"]
        ai_cfg = snapshot["ai"]
        completed_final_phase = False
        status, detail = "empty", ""
        try:
            if recorder.is_silent:
                return

            wav_bytes = recorder.wav_bytes

            logger.info("Phase 1: Transcribing audio...")
            transcription_result = self._transcribe(ai_cfg, loaded, wav_bytes)
            if transcription_result["empty"]:
                return
            transcription = transcription_result["transcription"].strip()
            if not transcription:
                return
            logger.info("Transcription: %s", transcription)

            language_instruction = self._language_instruction(ai_cfg["output_language"])

            logger.info("Phase 2: Rewriting transcription...")
            rewrite = self._rewrite(
                ai_cfg,
                loaded,
                transcription,
                language_instruction,
                ai_cfg["keep_alive"] if append else ai_cfg["preload_keep_alive"],
            )
            completed_final_phase = append
            title = rewrite["title"].strip()
            content = rewrite["content"].strip()
            if not content or (not append and not title):
                raise ValueError(_("Model returned empty note content"))
            logger.info("Rewriting: title=%s", title)

            if append:
                status, detail = "appended", content
                return

            logger.info("Phase 3: Classifying note...")
            classification = self._classify(ai_cfg, loaded, content, language_instruction)
            completed_final_phase = True
            logger.info(
                "Classification: type=%s, tags=%s",
                classification["type"],
                classification["tags"],
            )

            note = notes.create_note(
                folder=Path(snapshot["notes"]["folder"]).expanduser(),
                title=title,
                note_type=classification["type"],
                tags=notes.normalize_tags(classification["tags"]),
                body=content,
            )
            status, detail = "success", note.title
        except Exception as e:
            logger.exception("Error during audio processing/saving")
            status, detail = "error", str(e)
        finally:
            self.processing_completed.emit(status, detail)
            if not completed_final_phase and ai_cfg["keep_alive"] != ai_cfg["preload_keep_alive"]:
                self._reset_keep_alive(ai_cfg)

    # --- Completion, reload and shutdown -----------------------------------

    def _on_processing_completed(self, status, detail):
        self.state = IDLE
        self._update_icon("gray", _("Eloquent Notes (Idle)"))
        target, self._append_target = self._append_target, None

        if status == "success":
            logger.info("Note saved: %s", detail)
            self._notify(_("Note Saved"), detail)
            self._refresh_window()
        elif status == "appended":
            self._append_dictation(target, detail)
        elif status == "empty":
            logger.info("Dictation processing finished: Audio was empty")
            self._notify(
                _("Dictation Empty"),
                _("No note was created because the audio was empty."),
            )
        elif status == "error":
            logger.error("Dictation processing failed: %s", detail)
            self._notify(
                _("Processing Error"),
                _("Error processing dictation: {detail}").format(detail=detail),
            )

    def _append_dictation(self, target, text):
        """Append dictated text to target, keeping any edits pending in the reader."""
        if target is None or not target.path.exists():
            return
        if self.window is not None:
            self.window.save_open_note()
            if self.window.stack.currentWidget() is self.window.reader and self.window.reader.note.path == target.path:
                target = self.window.reader.note
        notes.append_to_note(target, text)
        logger.info("Dictation appended to %s", target.path.name)
        self._notify(_("Dictation Added"), target.title)
        self._refresh_window()

    def reload_config(self):
        """Reload configuration from disk."""
        try:
            new_config = config.load_config()
            log_cfg = new_config["logging"]
            setup_logging(
                log_level_str=log_cfg["level"],
                max_mb=log_cfg["max_mb"],
                backup_count=log_cfg["backup_count"],
            )
            self.config = new_config
            logger.info("Configuration reloaded successfully")
            self._notify(
                APP_NAME,
                _("Configuration reloaded successfully."),
            )
            self._refresh_window()
        except Exception as e:
            logger.exception("Failed to reload configuration")
            self._notify(
                _("Configuration Error"),
                _("Failed to reload configuration: {error}").format(error=e),
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
        self._hud.close()

        if self.state == RECORDING and self._recorder is not None:
            try:
                self._recorder.stop()
            except Exception:
                logger.exception("Error stopping recorder on exit")
        elif self.state == PROCESSING and self._processing_thread is not None:
            self._processing_thread.join(timeout=5.0)

        if self.window is not None:
            self.window.close()
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
    parser = argparse.ArgumentParser(description=_("Eloquent Notes Daemon"))
    parser.add_argument(
        "command", nargs="?", choices=["toggle", "open"], metavar="command",
    )
    args = parser.parse_args()

    cfg = config.load_config()
    log_cfg = cfg["logging"]
    setup_logging(
        log_level_str=log_cfg["level"],
        max_mb=log_cfg["max_mb"],
        backup_count=log_cfg["backup_count"],
    )
    autostart.install_desktop_entry()
    logger.info("Starting Eloquent Notes daemon...")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    eloquent_app = EloquentApp(
        app,
        start_recording_immediately=(args.command == "toggle"),
        open_window_immediately=(args.command == "open"),
        app_config=cfg,
    )
    eloquent_app.run()


if __name__ == "__main__":
    main()
