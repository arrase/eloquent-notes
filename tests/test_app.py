"""Unit tests for eloquent_notes.app module."""

import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QSystemTrayIcon

from eloquent_notes import config
from eloquent_notes.app import EloquentApp, main as app_main


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
            "recording_hud_enabled": True,
        },
        "obsidian": {
            "vault_path": str(vault_dir),
            "folder": "Notes",
            "folder_organization": "none",
            "daily_notes": False,
            "vault_context": False,
        },
        "logging": {
            "level": "INFO",
            "max_mb": 5,
            "backup_count": 3,
        },
    }


@pytest.fixture(autouse=True)
def default_app_config(mock_config):
    with patch("eloquent_notes.app.config.load_config", return_value=mock_config):
        yield mock_config


def test_app_init_and_thread_safe_properties(qapp):
    eloquent_app = EloquentApp(qapp)
    assert eloquent_app.state == "IDLE"
    assert eloquent_app.recorder is None

    # Test thread safety / getters & setters
    eloquent_app.state = "RECORDING"
    assert eloquent_app.state == "RECORDING"

    dummy_recorder = MagicMock()
    eloquent_app.recorder = dummy_recorder
    assert eloquent_app.recorder is dummy_recorder


def test_toggle_action_state_transitions(qapp):
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


def test_ipc_connection_handling(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app.toggle_action = MagicMock()
    eloquent_app.reload_config = MagicMock()
    eloquent_app._notify = MagicMock()

    mock_server = MagicMock()
    eloquent_app.server = mock_server

    # Simulate pending connection with 'toggle' message
    mock_socket_toggle = MagicMock()
    mock_socket_toggle.bytesAvailable.return_value = len(b"toggle")
    mock_socket_toggle.readAll.return_value = b"toggle"

    # Simulate pending connection with 'reload' message
    mock_socket_reload = MagicMock()
    mock_socket_reload.bytesAvailable.return_value = len(b"reload")
    mock_socket_reload.readAll.return_value = b"reload"

    # Simulate pending connection with 'notify_running' message
    mock_socket_notify = MagicMock()
    mock_socket_notify.bytesAvailable.return_value = len(b"notify_running")
    mock_socket_notify.readAll.return_value = b"notify_running"

    mock_server.hasPendingConnections.side_effect = [True, True, True, False]
    mock_server.nextPendingConnection.side_effect = [
        mock_socket_toggle,
        mock_socket_reload,
        mock_socket_notify,
        None,
    ]

    eloquent_app._handle_ipc_connection()

    eloquent_app.toggle_action.assert_called_once()
    eloquent_app.reload_config.assert_called_once()
    eloquent_app._notify.assert_called_once_with(
        "Eloquent Notes",
        "Eloquent Notes is already running in the background.",
    )
    mock_socket_toggle.disconnectFromServer.assert_called_once()
    mock_socket_reload.disconnectFromServer.assert_called_once()
    mock_socket_notify.disconnectFromServer.assert_called_once()


def test_update_icon_and_notify(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app.tray = MagicMock()

    with patch("eloquent_notes.app.ui.get_qicon") as mock_get_icon:
        eloquent_app._update_icon("red", "Recording...")
        mock_get_icon.assert_called_once_with("red")
        eloquent_app.tray.setIcon.assert_called_once()
        eloquent_app.tray.setToolTip.assert_called_once_with("Recording...")

    eloquent_app._notify("Title", "Message")
    eloquent_app.tray.showMessage.assert_called_once_with(
        "Title", "Message", QSystemTrayIcon.MessageIcon.Information, 5000
    )


def test_build_vault_context_disabled(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app.active_config = {
        "obsidian": {"vault_context": False, "vault_path": "/tmp"}
    }
    assert eloquent_app._build_vault_context() == ""


def test_build_vault_context_enabled(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app.active_config = {
        "obsidian": {"vault_context": True, "vault_path": "/tmp/vault"}
    }

    with patch("eloquent_notes.app.obsidian.scan_vault_topics", return_value=["TopicA", "TopicB"]):
        ctx = eloquent_app._build_vault_context()
        assert "TopicA, TopicB" in ctx
        assert "Known topics in the vault" in ctx


def test_process_audio_empty_audio(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app.processing_completed = MagicMock()

    with patch.object(eloquent_app, "_get_recorded_wav_bytes", return_value=b""):
        eloquent_app._process_audio()
        eloquent_app.processing_completed.emit.assert_called_once_with("empty", "")


def test_process_audio_empty_transcription(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app.processing_completed = MagicMock()
    eloquent_app.active_config["_loaded_files"] = {config.RETRY_PROMPT_PATH: "retry"}

    with patch.object(eloquent_app, "_get_recorded_wav_bytes", return_value=b"X" * 100), patch.object(
        eloquent_app, "_transcribe", return_value={"empty": True, "transcription": ""}
    ):
        eloquent_app._process_audio()
        eloquent_app.processing_completed.emit.assert_called_once_with("empty", "")


def test_process_audio_full_pipeline_success(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app.processing_completed = MagicMock()

    eloquent_app.active_config["_loaded_files"] = {
        config.RETRY_PROMPT_PATH: "retry prompt",
        config.STANDALONE_TEMPLATE_PATH: "template",
        config.DAILY_NEW_TEMPLATE_PATH: "daily new",
        config.DAILY_APPEND_TEMPLATE_PATH: "daily append",
        config.REWRITING_SYSTEM_PROMPT_PATH: "sys rewrite",
        config.REWRITING_USER_PROMPT_PATH: "{transcription}\n{language_instruction}",
        config.CLASSIFICATION_SYSTEM_PROMPT_PATH: "sys class",
        config.CLASSIFICATION_USER_PROMPT_PATH: "{transcription}\n{vault_context}\n{language_instruction}",
        config.TRANSCRIPTION_SYSTEM_PROMPT_PATH: "sys trans",
        config.TRANSCRIPTION_USER_PROMPT_PATH: "usr trans",
    }

    fake_wav = b"RIFF" + b"\x00" * 100
    with patch.object(eloquent_app, "_get_recorded_wav_bytes", return_value=fake_wav), patch(
        "eloquent_notes.app.llm.transcribe_audio",
        return_value={"empty": False, "transcription": "Hello note"},
    ), patch(
        "eloquent_notes.app.llm.rewrite_transcription",
        return_value={"title": "Note Title", "content": "Clean note"},
    ), patch(
        "eloquent_notes.app.llm.classify_transcription",
        return_value={"type": "idea", "wikilinks": ["Link"], "tags": ["tag1"]},
    ), patch(
        "eloquent_notes.app.obsidian.save_note",
        return_value="/tmp/vault/Dictation-1.md",
    ):
        eloquent_app._process_audio()
        eloquent_app.processing_completed.emit.assert_called_once_with(
            "success", "/tmp/vault/Dictation-1.md"
        )


def test_process_audio_exception_emits_error(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app.processing_completed = MagicMock()
    eloquent_app.active_config["_loaded_files"] = {config.RETRY_PROMPT_PATH: "retry"}

    with patch.object(eloquent_app, "_get_recorded_wav_bytes", return_value=b"X" * 100), patch.object(
        eloquent_app, "_transcribe", side_effect=RuntimeError("Ollama failed")
    ):
        eloquent_app._process_audio()
        eloquent_app.processing_completed.emit.assert_called_once_with(
            "error", "Ollama failed"
        )


def test_on_processing_completed_branches(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app._hud = MagicMock()
    eloquent_app._update_icon = MagicMock()
    eloquent_app._notify = MagicMock()

    # Success branch
    eloquent_app.state = "PROCESSING"
    eloquent_app._on_processing_completed("success", "/path/to/Note.md")
    assert eloquent_app.state == "IDLE"
    assert eloquent_app.recorder is None
    eloquent_app._notify.assert_called_with("Dictation Saved", "Saved dictation to Obsidian (Note.md)")

    # Empty branch
    eloquent_app.state = "PROCESSING"
    eloquent_app._on_processing_completed("empty", "")
    assert eloquent_app.state == "IDLE"
    eloquent_app._notify.assert_called_with("Dictation Empty", "No note was created because the audio was empty.")

    # Error branch
    eloquent_app.state = "PROCESSING"
    eloquent_app._on_processing_completed("error", "API timeout")
    assert eloquent_app.state == "IDLE"
    eloquent_app._notify.assert_called_with("Processing Error", "Error processing dictation: API timeout")


def test_reload_config_success_and_failure(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app._notify = MagicMock()

    with patch("eloquent_notes.app.config.load_config", return_value={"logging": {"level": "DEBUG", "max_mb": 10, "backup_count": 2}}), patch(
        "eloquent_notes.app.setup_logging"
    ) as mock_setup:
        eloquent_app.reload_config()
        mock_setup.assert_called_once_with(log_level_str="DEBUG", max_mb=10, backup_count=2)
        eloquent_app._notify.assert_called_with("Eloquent Notes", "Configuration reloaded successfully.")

    with patch("eloquent_notes.app.config.load_config", side_effect=ValueError("Corrupt YAML")):
        eloquent_app.reload_config()
        eloquent_app._notify.assert_called_with("Configuration Error", "Failed to reload configuration: Corrupt YAML")


def test_show_config_dialog(qapp):
    eloquent_app = EloquentApp(qapp)
    assert eloquent_app._config_dialog is None

    with patch("eloquent_notes.app.config_gui.ConfigurationDialog") as mock_dialog_cls:
        mock_dialog_instance = MagicMock()
        mock_dialog_cls.return_value = mock_dialog_instance

        # First call creates dialog
        eloquent_app.show_config_dialog()
        assert eloquent_app._config_dialog is mock_dialog_instance
        mock_dialog_instance.show.assert_called_once()

        # Second call raises existing dialog
        eloquent_app.show_config_dialog()
        mock_dialog_instance.raise_.assert_called_once()
        mock_dialog_instance.activateWindow.assert_called_once()

        # Closing callback cleans reference
        eloquent_app._on_config_dialog_closed(0)
        assert eloquent_app._config_dialog is None


def test_preload_model(qapp):
    eloquent_app = EloquentApp(qapp)

    with patch("eloquent_notes.app.llm.preload_model") as mock_preload:
        eloquent_app._preload_model()
        mock_preload.assert_called_once_with(
            ollama_url="http://localhost:11434",
            model="gemma",
            context_length=2048,
            keep_alive="5m",
            timeout=10,
        )

    # Preload failure logged as warning without raising
    with patch("eloquent_notes.app.llm.preload_model", side_effect=RuntimeError("Connection refused")):
        eloquent_app._preload_model()  # Should not raise


def test_tray_menu_creation_and_activation(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app.toggle_action = MagicMock()

    menu = eloquent_app._create_tray_menu()
    assert menu is not None
    assert len(menu.actions()) >= 4

    eloquent_app._on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
    eloquent_app.toggle_action.assert_called_once()


def test_exit_app_cleanup(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app.state = "RECORDING"
    mock_rec = MagicMock()
    eloquent_app.recorder = mock_rec
    eloquent_app._config_dialog = MagicMock()
    eloquent_app.server = MagicMock()
    eloquent_app.tray = MagicMock()
    eloquent_app.app = MagicMock()

    with pytest.raises(SystemExit):
        eloquent_app.exit_app()

    mock_rec.stop.assert_called_once()
    eloquent_app._config_dialog.close.assert_called_once()
    eloquent_app.server.close.assert_called_once()
    eloquent_app.tray.hide.assert_called_once()
    eloquent_app.app.quit.assert_called_once()


def test_start_recording_emits_recording_started(qapp, mock_config):
    custom_cfg = dict(mock_config)
    custom_cfg["audio"] = dict(mock_config["audio"])
    custom_cfg["audio"]["capture_duration"] = 45

    with patch("eloquent_notes.app.config.load_config", return_value=custom_cfg):
        eloquent_app = EloquentApp(qapp)

        mock_started_slot = MagicMock()
        eloquent_app.recording_started.connect(mock_started_slot)

        with patch("eloquent_notes.app.config.load_file", return_value="content"), patch(
            "eloquent_notes.app.audio.AudioRecorder"
        ) as mock_rec_cls, patch("threading.Thread") as mock_thread_cls:
            mock_rec_inst = MagicMock()
            mock_rec_cls.return_value = mock_rec_inst

            def fake_thread_init(target=None, daemon=None):
                thread_mock = MagicMock()
                thread_mock.start = lambda: target() if target else None
                return thread_mock

            mock_thread_cls.side_effect = fake_thread_init
            eloquent_app._start_recording()
            mock_started_slot.assert_called_with(45)


def test_on_recording_started_initializes_timer_and_hud(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app._hud = MagicMock()

    eloquent_app._on_recording_started(30)

    assert eloquent_app._recording_max_duration == 30.0
    assert eloquent_app._recording_tick_timer.isActive()
    eloquent_app._hud.show_recording.assert_called_with(30.0)
    eloquent_app._recording_tick_timer.stop()


def test_on_recording_tick_updates_hud_progress(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app.state = "RECORDING"
    eloquent_app._hud = MagicMock()
    eloquent_app._hud.isVisible.return_value = True

    eloquent_app._recording_max_duration = 30.0
    with patch("eloquent_notes.app.time.monotonic", return_value=100.0):
        eloquent_app._recording_start_time = 90.0
        eloquent_app._on_recording_tick()

    eloquent_app._hud.update_progress.assert_called_with(10.0, 20.0, 30.0)


def test_on_recording_tick_triggers_timeout_when_expired(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app.state = "RECORDING"
    eloquent_app._update_icon = MagicMock()
    eloquent_app._on_capture_timeout = MagicMock()

    eloquent_app._recording_max_duration = 30.0
    with patch("eloquent_notes.app.time.monotonic", return_value=130.1):
        eloquent_app._recording_start_time = 100.0
        eloquent_app._on_recording_tick()

    eloquent_app._on_capture_timeout.assert_called_once()
    assert not eloquent_app._recording_tick_timer.isActive()


def test_manual_stop_stops_tick_timer_and_shows_processing(qapp):
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


def test_app_main_entry_point(monkeypatch):
    mock_qapp = MagicMock()
    mock_eloquent_app = MagicMock()

    monkeypatch.setattr("eloquent_notes.app.QApplication", lambda args: mock_qapp)
    monkeypatch.setattr("eloquent_notes.app.EloquentApp", lambda app, start_recording_immediately: mock_eloquent_app)
    monkeypatch.setattr("eloquent_notes.app.setup_logging", MagicMock())
    monkeypatch.setattr(sys, "argv", ["eloquent-notes", "toggle"])

    app_main()

    mock_qapp.setQuitOnLastWindowClosed.assert_called_once_with(False)
    mock_eloquent_app.run.assert_called_once()
