"""Unit tests for eloquent_notes.app module."""

import threading
from unittest.mock import MagicMock, patch

import pytest

from eloquent_notes import config
from eloquent_notes.app import EloquentApp


@pytest.fixture
def mock_config(tmp_path):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    return {
        "ai": {
            "ollama_url": "http://localhost:11434",
            "model": "gemma",
            "context_length": 2048,
            "preload_keep_alive": "5m",
            "preload_timeout": 10,
            "max_retries": 1,
            "request_timeout": 10,
            "keep_alive": "0",
            "output_language": "English",
        },
        "audio": {
            "sample_rate": 16000,
            "channels": 1,
            "capture_duration": 30,
            "beep_enabled": False,
            "beep_frequency": 440,
            "beep_duration": 0.1,
        },
        "obsidian": {
            "vault_path": str(vault_dir),
            "folder": "Notes",
            "daily_notes": False,
            "vault_context": False,
        },
        "logging": {
            "level": "INFO",
            "max_mb": 5,
            "backup_count": 3,
        },
    }


@patch("eloquent_notes.app.config.load_config")
def test_app_init_and_thread_safe_properties(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    assert eloquent_app.state == "IDLE"
    assert eloquent_app.recorder is None

    # Test thread safety / getters & setters
    eloquent_app.state = "RECORDING"
    assert eloquent_app.state == "RECORDING"

    dummy_recorder = MagicMock()
    eloquent_app.recorder = dummy_recorder
    assert eloquent_app.recorder is dummy_recorder


@patch("eloquent_notes.app.config.load_config")
def test_toggle_action_state_transitions(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    eloquent_app._notify = MagicMock()
    eloquent_app._update_icon = MagicMock()

    # From IDLE -> STARTING_RECORDING
    with patch("eloquent_notes.app.config.load_file", return_value="prompt"):
        eloquent_app.toggle_action()
        assert eloquent_app.state == "STARTING_RECORDING"

    # Set to RECORDING -> should trigger _stop_recording_and_process
    eloquent_app.state = "RECORDING"
    mock_rec = MagicMock()
    eloquent_app.recorder = mock_rec

    with patch("threading.Thread") as mock_thread_cls:
        eloquent_app.toggle_action()
        assert eloquent_app.state == "PROCESSING"
        mock_rec.stop.assert_called_once()
        mock_thread_cls.assert_called()

    # From PROCESSING -> should notify busy
    eloquent_app.toggle_action()
    eloquent_app._notify.assert_called_with("Eloquent Notes", "System is busy. Please wait.")


@patch("eloquent_notes.app.config.load_config")
def test_ipc_connection_handling(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    eloquent_app.toggle_action = MagicMock()
    eloquent_app.reload_config = MagicMock()
    eloquent_app._notify = MagicMock()

    mock_socket = MagicMock()
    mock_socket.bytesAvailable.return_value = 6
    mock_socket.readAll.return_value = b"toggle"

    mock_server = MagicMock()
    mock_server.hasPendingConnections.side_effect = [True, False]
    mock_server.nextPendingConnection.return_value = mock_socket
    eloquent_app.server = mock_server

    eloquent_app._handle_ipc_connection()
    eloquent_app.toggle_action.assert_called_once()
    mock_socket.disconnectFromServer.assert_called_once()
    mock_socket.deleteLater.assert_called_once()


@patch("eloquent_notes.app.config.load_config")
def test_ipc_connection_handling_multiple_messages(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    eloquent_app.toggle_action = MagicMock()
    eloquent_app.reload_config = MagicMock()

    socket1 = MagicMock()
    socket1.bytesAvailable.return_value = 6
    socket1.readAll.return_value = b"toggle"

    socket2 = MagicMock()
    socket2.bytesAvailable.return_value = 6
    socket2.readAll.return_value = b"reload"

    mock_server = MagicMock()
    mock_server.hasPendingConnections.side_effect = [True, True, False]
    mock_server.nextPendingConnection.side_effect = [socket1, socket2]
    eloquent_app.server = mock_server

    eloquent_app._handle_ipc_connection()
    eloquent_app.toggle_action.assert_called_once()
    eloquent_app.reload_config.assert_called_once()
    socket1.disconnectFromServer.assert_called_once()
    socket2.disconnectFromServer.assert_called_once()


@patch("eloquent_notes.app.config.load_config")
def test_process_audio_empty(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    mock_rec = MagicMock()
    mock_rec.wav_bytes = b"header_only"  # <= 44 bytes
    eloquent_app.recorder = mock_rec

    completed_signals = []
    eloquent_app.processing_completed.connect(lambda status, detail: completed_signals.append((status, detail)))

    eloquent_app._process_audio()
    assert len(completed_signals) == 1
    assert completed_signals[0] == ("empty", "")


@patch("eloquent_notes.app.config.load_config")
@patch("eloquent_notes.app.llm.transcribe_audio")
@patch("eloquent_notes.app.llm.rewrite_transcription")
@patch("eloquent_notes.app.llm.classify_transcription")
@patch("eloquent_notes.app.obsidian.save_note")
def test_process_audio_success(
    mock_save, mock_classify, mock_rewrite, mock_transcribe, mock_load_cfg, qapp, mock_config
):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    mock_rec = MagicMock()
    mock_rec.wav_bytes = b"0" * 100
    eloquent_app.recorder = mock_rec

    eloquent_app.active_config["_loaded_files"] = {
        config.RETRY_PROMPT_PATH: "retry",
        config.TRANSCRIPTION_SYSTEM_PROMPT_PATH: "sys1",
        config.TRANSCRIPTION_USER_PROMPT_PATH: "usr1",
        config.REWRITING_SYSTEM_PROMPT_PATH: "sys2",
        config.REWRITING_USER_PROMPT_PATH: "{transcription} {language_instruction}",
        config.CLASSIFICATION_SYSTEM_PROMPT_PATH: "sys3",
        config.CLASSIFICATION_USER_PROMPT_PATH: "{transcription} {vault_context} {language_instruction}",
        config.STANDALONE_TEMPLATE_PATH: "tmpl1",
        config.DAILY_NEW_TEMPLATE_PATH: "tmpl2",
        config.DAILY_APPEND_TEMPLATE_PATH: "tmpl3",
    }

    mock_transcribe.return_value = {"empty": False, "transcription": "Recorded audio text"}
    mock_rewrite.return_value = {"title": "Note Title", "content": "Note Content"}
    mock_classify.return_value = {"type": "idea", "wikilinks": ["Link"], "tags": ["tag"]}
    mock_save.return_value = "/path/to/Note Title.md"

    completed_signals = []
    eloquent_app.processing_completed.connect(lambda status, detail: completed_signals.append((status, detail)))

    eloquent_app._process_audio()
    assert len(completed_signals) == 1
    assert completed_signals[0] == ("success", "/path/to/Note Title.md")


@patch("eloquent_notes.app.config.load_config")
def test_on_processing_completed(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    eloquent_app._notify = MagicMock()
    eloquent_app._update_icon = MagicMock()
    eloquent_app.state = "PROCESSING"
    mock_rec = MagicMock()
    eloquent_app.recorder = mock_rec

    eloquent_app._on_processing_completed("success", "/path/to/Note.md")
    assert eloquent_app.state == "IDLE"
    assert eloquent_app.recorder is None
    eloquent_app._update_icon.assert_called_with("gray", "Eloquent Notes (Idle)")
    eloquent_app._notify.assert_called_with("Dictation Saved", "Saved dictation to Obsidian (Note.md)")


@patch("eloquent_notes.app.config.load_config")
def test_config_dialog_closed_cleans_up(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    mock_dialog = MagicMock()
    eloquent_app._config_dialog = mock_dialog

    eloquent_app._on_config_dialog_closed(0)
    assert eloquent_app._config_dialog is None
    mock_dialog.deleteLater.assert_called_once()


@patch("eloquent_notes.app.config.load_config")
def test_exit_app_cleans_up(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    mock_rec = MagicMock()
    eloquent_app.recorder = mock_rec
    eloquent_app.state = "RECORDING"

    mock_server = MagicMock()
    eloquent_app.server = mock_server
    eloquent_app.tray = MagicMock()
    eloquent_app.app = MagicMock()

    with pytest.raises(SystemExit):
        eloquent_app.exit_app()

    assert eloquent_app.state == "IDLE"
    assert eloquent_app.recorder is None
    mock_rec.stop.assert_called_once()
    mock_server.close.assert_called_once()


@patch("eloquent_notes.app.config.load_config")
def test_exit_app_when_tray_is_none(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    eloquent_app.app = MagicMock()
    eloquent_app.tray = None

    with pytest.raises(SystemExit):
        eloquent_app.exit_app()

    eloquent_app.app.quit.assert_called_once()


@patch("eloquent_notes.app.config.load_config")
def test_start_recording_emits_recording_started(mock_load_cfg, qapp, mock_config):
    mock_config["audio"]["capture_duration"] = 45
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    eloquent_app._update_icon = MagicMock()
    mock_started_slot = MagicMock()
    eloquent_app.recording_started.connect(mock_started_slot)

    with patch("eloquent_notes.app.config.load_file", return_value="prompt"), \
         patch("eloquent_notes.app.audio.AudioRecorder") as mock_recorder_cls, \
         patch("eloquent_notes.app.threading.Thread") as mock_thread_cls:

        mock_rec = MagicMock()
        mock_recorder_cls.return_value = mock_rec

        def fake_thread_init(target=None, daemon=None):
            t = MagicMock()
            t.start.side_effect = lambda: target() if target else None
            return t

        mock_thread_cls.side_effect = fake_thread_init

        eloquent_app._start_recording()

        mock_started_slot.assert_called_with(45)


@patch("eloquent_notes.app.config.load_config")
def test_on_recording_started_initializes_timer_and_hud(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    eloquent_app._hud = MagicMock()

    eloquent_app._on_recording_started(30)

    assert eloquent_app._recording_max_duration == 30.0
    assert eloquent_app._recording_tick_timer.isActive()
    eloquent_app._hud.show_recording.assert_called_with(30.0)
    eloquent_app._recording_tick_timer.stop()


@patch("eloquent_notes.app.config.load_config")
def test_on_recording_tick_updates_hud_progress(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    eloquent_app.state = "RECORDING"
    eloquent_app._hud = MagicMock()
    eloquent_app._hud.isVisible.return_value = True

    eloquent_app._recording_max_duration = 30.0
    # Simulate 10 seconds elapsed
    with patch("eloquent_notes.app.time.monotonic", return_value=100.0):
        eloquent_app._recording_start_time = 90.0
        eloquent_app._on_recording_tick()

    eloquent_app._hud.update_progress.assert_called_with(10.0, 20.0, 30.0)


@patch("eloquent_notes.app.config.load_config")
def test_on_recording_tick_triggers_timeout_when_expired(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    eloquent_app.state = "RECORDING"
    eloquent_app._update_icon = MagicMock()
    eloquent_app._on_capture_timeout = MagicMock()

    eloquent_app._recording_max_duration = 30.0
    # Simulate 30.1 seconds elapsed (expired)
    with patch("eloquent_notes.app.time.monotonic", return_value=130.1):
        eloquent_app._recording_start_time = 100.0
        eloquent_app._on_recording_tick()

    eloquent_app._on_capture_timeout.assert_called_once()
    assert not eloquent_app._recording_tick_timer.isActive()


@patch("eloquent_notes.app.config.load_config")
def test_manual_stop_stops_tick_timer_and_shows_processing(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    eloquent_app.state = "RECORDING"
    mock_rec = MagicMock()
    eloquent_app.recorder = mock_rec
    eloquent_app._recording_tick_timer.start(100)
    eloquent_app._update_icon = MagicMock()
    eloquent_app._hud = MagicMock()
    eloquent_app._hud.isVisible.return_value = True

    with patch("threading.Thread"):
        eloquent_app._stop_recording_and_process()

        assert not eloquent_app._recording_tick_timer.isActive()
        eloquent_app._hud.show_processing.assert_called_once()
        assert eloquent_app.state == "PROCESSING"


@patch("eloquent_notes.app.config.load_config")
def test_on_processing_completed_hides_hud(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    eloquent_app.state = "PROCESSING"
    eloquent_app._hud = MagicMock()
    eloquent_app._update_icon = MagicMock()
    eloquent_app._notify = MagicMock()

    eloquent_app._on_processing_completed("success", "/path/to/note.md")

    assert eloquent_app.state == "IDLE"
    eloquent_app._hud.hide_hud.assert_called_once()
    eloquent_app._update_icon.assert_called_with("gray", "Eloquent Notes (Idle)")


@patch("eloquent_notes.app.config.load_config")
def test_on_recording_started_zero_or_negative_duration(mock_load_cfg, qapp, mock_config):
    mock_load_cfg.return_value = mock_config

    eloquent_app = EloquentApp(qapp)
    eloquent_app._on_recording_started(0)
    assert eloquent_app._recording_max_duration == 0.0
    assert eloquent_app._recording_tick_timer.isActive()
    eloquent_app._recording_tick_timer.stop()

