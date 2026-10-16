"""Unit tests for eloquent_notes.app module."""

import sys
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
import requests
from PyQt6.QtWidgets import QSystemTrayIcon

from eloquent_notes import config
from eloquent_notes.app import EloquentApp
from eloquent_notes.app import main as app_main


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


def make_app(qapp):
    """Create an EloquentApp with notification and icon side effects mocked."""
    eloquent_app = EloquentApp(qapp)
    eloquent_app._notify = MagicMock()
    eloquent_app._update_icon = MagicMock()
    eloquent_app._hud = MagicMock()
    eloquent_app._hud.isVisible.return_value = False
    return eloquent_app


def test_app_init_starts_idle(qapp):
    eloquent_app = EloquentApp(qapp)
    assert eloquent_app.state == "IDLE"
    assert eloquent_app._recorder is None
    assert eloquent_app._snapshot is None


def test_toggle_from_idle_starts_recording(qapp, mock_config):
    eloquent_app = make_app(qapp)
    recorder = MagicMock()

    with patch("eloquent_notes.app.audio.play_beep") as mock_beep, patch(
        "eloquent_notes.app.audio.AudioRecorder", return_value=recorder,
    ), patch("eloquent_notes.app.config.load_file", return_value="content"), patch(
        "eloquent_notes.app.threading.Thread",
    ) as mock_thread_cls:
        eloquent_app.toggle_action()

    assert eloquent_app.state == "RECORDING"
    assert eloquent_app._recorder is recorder
    recorder.start.assert_called_once()
    eloquent_app._update_icon.assert_called_with("red", "Eloquent Notes (Recording...)")
    eloquent_app._hud.show_recording.assert_called_once_with(30.0)
    assert eloquent_app._tick_timer.isActive()
    assert eloquent_app._capture_duration == 30.0

    # Prompts/templates are snapshotted at recording start
    loaded = eloquent_app._snapshot["_loaded_files"]
    assert set(loaded) == set(config.PROMPT_AND_TEMPLATE_PATHS)

    # A single background thread (model preload) is spawned with the snapshot
    mock_thread_cls.assert_called_once()
    assert mock_thread_cls.call_args.kwargs["target"] == eloquent_app._preload_model
    assert mock_thread_cls.call_args.kwargs["args"] == (eloquent_app._snapshot,)

    # Beeps are disabled in the fixture config
    mock_beep.assert_not_called()


def test_start_recording_plays_blocking_beep_when_enabled(qapp, mock_config):
    mock_config["audio"]["beep_enabled"] = True
    eloquent_app = make_app(qapp)

    with patch("eloquent_notes.app.audio.play_beep") as mock_beep, patch(
        "eloquent_notes.app.audio.AudioRecorder", return_value=MagicMock(),
    ), patch("eloquent_notes.app.config.load_file", return_value="c"), patch(
        "eloquent_notes.app.threading.Thread",
    ):
        eloquent_app.toggle_action()

    mock_beep.assert_called_once_with(
        frequency=440, duration=0.1, sample_rate=16000, wait=True,
    )


def test_beep_failure_does_not_abort_recording(qapp, mock_config):
    mock_config["audio"]["beep_enabled"] = True
    eloquent_app = make_app(qapp)
    recorder = MagicMock()

    with patch(
        "eloquent_notes.app.audio.play_beep",
        side_effect=RuntimeError("No output device"),
    ), patch(
        "eloquent_notes.app.audio.AudioRecorder", return_value=recorder,
    ), patch("eloquent_notes.app.config.load_file", return_value="c"), patch(
        "eloquent_notes.app.threading.Thread",
    ):
        eloquent_app.toggle_action()

    assert eloquent_app.state == "RECORDING"
    recorder.start.assert_called_once()


def test_start_recording_failure_notifies_and_stays_idle(qapp):
    eloquent_app = make_app(qapp)
    failing_recorder = MagicMock()
    failing_recorder.start.side_effect = RuntimeError("No mic")

    with patch("eloquent_notes.app.audio.AudioRecorder", return_value=failing_recorder), \
            patch("eloquent_notes.app.config.load_file", return_value="c"):
        eloquent_app.toggle_action()

    assert eloquent_app.state == "IDLE"
    assert eloquent_app._recorder is None
    eloquent_app._update_icon.assert_called_once_with("gray", "Eloquent Notes (Idle)")
    eloquent_app._notify.assert_called_once()
    assert eloquent_app._notify.call_args.args[0] == "Processing Error"
    assert "Could not start recording" in eloquent_app._notify.call_args.args[1]
    assert "No mic" in eloquent_app._notify.call_args.args[1]


def test_start_recording_missing_prompt_file_notifies_and_stays_idle(qapp):
    eloquent_app = make_app(qapp)

    with patch(
        "eloquent_notes.app.config.load_file",
        side_effect=FileNotFoundError("Prompt missing"),
    ):
        eloquent_app.toggle_action()

    assert eloquent_app.state == "IDLE"
    assert eloquent_app._recorder is None
    eloquent_app._update_icon.assert_called_once_with("gray", "Eloquent Notes (Idle)")
    eloquent_app._notify.assert_called_once()
    assert "Prompt missing" in eloquent_app._notify.call_args.args[1]


def test_start_recording_skips_preload_if_thread_alive(qapp):
    eloquent_app = make_app(qapp)
    alive_thread = MagicMock()
    alive_thread.is_alive.return_value = True
    eloquent_app._preload_thread = alive_thread

    with patch(
        "eloquent_notes.app.audio.AudioRecorder", return_value=MagicMock(),
    ), patch("eloquent_notes.app.config.load_file", return_value="c"), patch(
        "eloquent_notes.app.threading.Thread",
    ) as mock_thread_cls:
        eloquent_app.toggle_action()

    mock_thread_cls.assert_not_called()
    assert eloquent_app._preload_thread is alive_thread


def test_toggle_from_recording_stops_and_processes(qapp):
    eloquent_app = make_app(qapp)
    recorder = MagicMock()
    snapshot = {
        "audio": {
            "beep_enabled": True,
            "beep_frequency": 440,
            "beep_duration": 0.1,
            "sample_rate": 16000,
        },
    }
    call_order = []
    recorder.stop.side_effect = lambda: call_order.append("stop")

    eloquent_app.state = "RECORDING"
    eloquent_app._recorder = recorder
    eloquent_app._snapshot = snapshot
    eloquent_app._tick_timer.start(100)

    with patch(
        "eloquent_notes.app.audio.play_beep",
        side_effect=lambda **kwargs: call_order.append("beep"),
    ) as mock_beep, patch("eloquent_notes.app.threading.Thread") as mock_thread_cls:
        eloquent_app.toggle_action()

    assert call_order == ["stop", "beep"]
    mock_beep.assert_called_once_with(
        frequency=440, duration=0.1, sample_rate=16000, wait=False,
    )
    assert eloquent_app.state == "PROCESSING"
    assert not eloquent_app._tick_timer.isActive()
    eloquent_app._hud.hide.assert_called_once()
    eloquent_app._update_icon.assert_called_with(
        "orange", "Eloquent Notes (Processing...)",
    )
    recorder.stop.assert_called_once()
    assert eloquent_app._processing_thread is mock_thread_cls.return_value
    assert mock_thread_cls.call_args.kwargs["target"] == eloquent_app._process_audio
    assert mock_thread_cls.call_args.kwargs["args"] == (recorder, snapshot)


def test_stop_recording_failure_resets_to_idle(qapp):
    eloquent_app = make_app(qapp)
    recorder = MagicMock()
    recorder.stop.side_effect = RuntimeError("PortAudio stop error")
    eloquent_app.state = "RECORDING"
    eloquent_app._recorder = recorder
    eloquent_app._snapshot = {"audio": {"beep_enabled": False}}

    with patch("eloquent_notes.app.threading.Thread") as mock_thread_cls:
        eloquent_app.toggle_action()

    assert eloquent_app.state == "IDLE"
    assert eloquent_app._recorder is None
    assert eloquent_app._snapshot is None
    mock_thread_cls.assert_not_called()
    eloquent_app._update_icon.assert_called_with("gray", "Eloquent Notes (Idle)")
    eloquent_app._notify.assert_called_once()
    assert "Could not stop recording" in eloquent_app._notify.call_args.args[1]


def test_toggle_while_processing_notifies_busy(qapp):
    eloquent_app = make_app(qapp)
    eloquent_app.state = "PROCESSING"

    eloquent_app.toggle_action()

    eloquent_app._notify.assert_called_once_with(
        "Eloquent Notes", "System is busy. Please wait.",
    )


def test_recording_tick_timeout_stops_and_processes(qapp):
    eloquent_app = make_app(qapp)
    recorder = MagicMock()
    eloquent_app.state = "RECORDING"
    eloquent_app._recorder = recorder
    eloquent_app._snapshot = {"audio": {"beep_enabled": False}}
    eloquent_app._capture_duration = 30.0

    with patch("eloquent_notes.app.time.monotonic", return_value=100.0), patch(
        "eloquent_notes.app.threading.Thread",
    ):
        eloquent_app._recording_started_at = 60.0
        eloquent_app._on_recording_tick()

    assert eloquent_app.state == "PROCESSING"
    recorder.stop.assert_called_once()


def test_ipc_connection_handling(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app.toggle_action = MagicMock()
    eloquent_app.reload_config = MagicMock()
    eloquent_app._notify = MagicMock()

    mock_server = MagicMock()
    eloquent_app.server = mock_server

    def make_socket(message):
        socket = MagicMock()
        socket.bytesAvailable.return_value = len(message.encode())
        socket.readAll.return_value = message.encode()
        return socket

    sockets = [
        make_socket("toggle"),
        make_socket("reload"),
        make_socket("notify_running"),
    ]
    mock_server.hasPendingConnections.side_effect = [True, True, True, False]
    mock_server.nextPendingConnection.side_effect = [*sockets, None]

    eloquent_app._handle_ipc_connection()

    eloquent_app.toggle_action.assert_called_once()
    eloquent_app.reload_config.assert_called_once()
    eloquent_app._notify.assert_called_once_with(
        "Eloquent Notes",
        "Eloquent Notes is already running in the background.",
    )
    for socket in sockets:
        socket.disconnectFromServer.assert_called_once()


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


def test_build_vault_context_disabled():
    obs_cfg = {"vault_context": False, "vault_path": "/tmp"}
    assert EloquentApp._build_vault_context(obs_cfg) == ""


def test_build_vault_context_enabled():
    obs_cfg = {"vault_context": True, "vault_path": "/tmp/vault"}

    with patch(
        "eloquent_notes.app.obsidian.scan_vault_topics",
        return_value=["TopicA", "TopicB"],
    ):
        ctx = EloquentApp._build_vault_context(obs_cfg)

    assert "TopicA, TopicB" in ctx
    assert "Known topics in the vault" in ctx


def test_process_audio_empty_wav(qapp):
    eloquent_app = make_app(qapp)
    eloquent_app.processing_completed = MagicMock()

    recorder = MagicMock()
    recorder.wav_bytes = b""
    recorder.is_silent = True
    snapshot = _pipeline_snapshot()

    with patch("eloquent_notes.app.llm.preload_model") as mock_preload:
        eloquent_app._process_audio(recorder, snapshot)

    eloquent_app.processing_completed.emit.assert_called_once_with("empty", "")
    mock_preload.assert_called_once_with(
        ollama_url="http://localhost:11434",
        model="gemma",
        context_length=2048,
        keep_alive="0",
        timeout=10,
    )


def _pipeline_snapshot():
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
        "obsidian": {
            "vault_path": "/tmp/vault",
            "folder": "Notes",
            "folder_organization": "none",
            "daily_notes": False,
            "vault_context": False,
        },
        "_loaded_files": {
            config.RETRY_PROMPT_PATH: "retry prompt",
            config.STANDALONE_TEMPLATE_PATH: "template",
            config.DAILY_NEW_TEMPLATE_PATH: "daily new",
            config.DAILY_APPEND_TEMPLATE_PATH: "daily append",
            config.REWRITING_SYSTEM_PROMPT_PATH: "sys rewrite",
            config.REWRITING_USER_PROMPT_PATH: (
                "{transcription}\n{language_instruction}"
            ),
            config.CLASSIFICATION_SYSTEM_PROMPT_PATH: "sys class",
            config.CLASSIFICATION_USER_PROMPT_PATH: (
                "{transcription}\n{vault_context}\n{language_instruction}"
            ),
            config.TRANSCRIPTION_SYSTEM_PROMPT_PATH: "sys trans",
            config.TRANSCRIPTION_USER_PROMPT_PATH: "usr trans",
        },
    }


def test_process_audio_empty_transcription(qapp):
    eloquent_app = make_app(qapp)
    eloquent_app.processing_completed = MagicMock()
    preload_thread = MagicMock()
    preload_thread.is_alive.return_value = True
    eloquent_app._preload_thread = preload_thread

    recorder = MagicMock()
    recorder.wav_bytes = b"RIFF" + b"\x00" * 100
    recorder.is_silent = False
    snapshot = _pipeline_snapshot()

    with patch(
        "eloquent_notes.app.llm.transcribe_audio",
        return_value={"empty": False, "transcription": "   "},
    ) as mock_transcribe, patch("eloquent_notes.app.llm.preload_model") as mock_preload:
        eloquent_app._process_audio(recorder, snapshot)

    preload_thread.join.assert_called_once_with(timeout=10)
    eloquent_app.processing_completed.emit.assert_called_once_with("empty", "")
    mock_transcribe.assert_called_once()
    mock_preload.assert_called_once_with(
        ollama_url="http://localhost:11434",
        model="gemma",
        context_length=2048,
        keep_alive="0",
        timeout=10,
    )

    # Also verify empty=True returns before stripping transcription
    eloquent_app.processing_completed.reset_mock()
    preload_thread.is_alive.return_value = False
    with patch(
        "eloquent_notes.app.llm.transcribe_audio",
        return_value={"empty": True, "transcription": ""},
    ), patch("eloquent_notes.app.llm.preload_model"):
        eloquent_app._process_audio(recorder, snapshot)
    eloquent_app.processing_completed.emit.assert_called_once_with("empty", "")


def test_process_audio_local_silence_never_reaches_model(qapp):
    """A quiet trigger is rejected locally, without encoding WAV or calling the model."""
    eloquent_app = make_app(qapp)
    eloquent_app.processing_completed = MagicMock()

    recorder = MagicMock()
    wav_prop = PropertyMock(return_value=b"RIFF" + b"\x00" * 100)
    type(recorder).wav_bytes = wav_prop
    recorder.is_silent = True
    snapshot = _pipeline_snapshot()

    with patch("eloquent_notes.app.llm.transcribe_audio") as mock_transcribe, patch(
        "eloquent_notes.app.llm.preload_model"
    ) as mock_preload:
        eloquent_app._process_audio(recorder, snapshot)

    wav_prop.assert_not_called()
    eloquent_app.processing_completed.emit.assert_called_once_with("empty", "")
    mock_transcribe.assert_not_called()
    mock_preload.assert_called_once_with(
        ollama_url="http://localhost:11434",
        model="gemma",
        context_length=2048,
        keep_alive="0",
        timeout=10,
    )


def test_process_audio_full_pipeline_success(qapp, tmp_path):
    eloquent_app = make_app(qapp)
    eloquent_app.processing_completed = MagicMock()

    recorder = MagicMock()
    recorder.wav_bytes = b"RIFF" + b"\x00" * 100
    recorder.is_silent = False
    snapshot = _pipeline_snapshot()
    snapshot["obsidian"]["vault_path"] = str(tmp_path / "vault")
    saved_path = str(tmp_path / "vault" / "Dictation-1.md")

    with patch(
        "eloquent_notes.app.llm.transcribe_audio",
        return_value={"empty": False, "transcription": "Hello note"},
    ) as mock_transcribe, patch(
        "eloquent_notes.app.llm.rewrite_transcription",
        return_value={"title": "Note Title", "content": "Clean note"},
    ), patch(
        "eloquent_notes.app.llm.classify_transcription",
        return_value={"type": "idea", "wikilinks": ["Link"], "tags": ["tag1"]},
    ) as mock_classify, patch(
        "eloquent_notes.app.obsidian.save_note", return_value=saved_path,
    ) as mock_save, patch("eloquent_notes.app.llm.preload_model") as mock_preload:
        eloquent_app._process_audio(recorder, snapshot)

    eloquent_app.processing_completed.emit.assert_called_once_with("success", saved_path)

    # Audio bytes are forwarded to phase 1
    assert mock_transcribe.call_args.kwargs["audio_bytes"] == recorder.wav_bytes

    # Phase 3 receives the rewritten content rather than raw transcription
    assert "Clean note" in mock_classify.call_args.kwargs["user_prompt"]
    assert "Hello note" not in mock_classify.call_args.kwargs["user_prompt"]

    # Since Phase 3 completed, preload_model is not called in finally
    mock_preload.assert_not_called()

    # Rewritten content is formatted (idea -> tip callout) before saving
    saved_text = mock_save.call_args.kwargs["text"]
    assert "Clean note" in saved_text
    assert "[!tip]" in saved_text
    assert mock_save.call_args.kwargs["title"] == "Note Title"


def test_process_audio_exception_emits_error(qapp):
    eloquent_app = make_app(qapp)
    eloquent_app.processing_completed = MagicMock()

    recorder = MagicMock()
    recorder.wav_bytes = b"RIFF" + b"\x00" * 100
    recorder.is_silent = False
    snapshot = _pipeline_snapshot()

    with patch(
        "eloquent_notes.app.llm.transcribe_audio",
        side_effect=RuntimeError("Ollama failed"),
    ), patch(
        "eloquent_notes.app.llm.preload_model",
        side_effect=requests.RequestException("Unload failed"),
    ) as mock_preload:
        eloquent_app._process_audio(recorder, snapshot)

    eloquent_app.processing_completed.emit.assert_called_once_with(
        "error", "Ollama failed",
    )
    mock_preload.assert_called_once()


def test_user_prompts_preserve_literal_braces(qapp):
    eloquent_app = make_app(qapp)
    snapshot = _pipeline_snapshot()
    ai_cfg = snapshot["ai"]
    obs_cfg = snapshot["obsidian"]
    loaded = snapshot["_loaded_files"]
    loaded[config.REWRITING_USER_PROMPT_PATH] = "JSON example: {{\"a\": 1}} {unknown_key} {transcription} {language_instruction}"
    loaded[config.CLASSIFICATION_USER_PROMPT_PATH] = "Rule {custom_brace}: {transcription} {vault_context} {language_instruction}"

    lang_inst = EloquentApp._language_instruction("Spanish")
    assert "translating from the transcription language if necessary" in lang_inst

    with patch("eloquent_notes.app.llm.rewrite_transcription") as mock_rewrite:
        EloquentApp._rewrite(ai_cfg, loaded, "Hola", lang_inst)
        prompt = mock_rewrite.call_args.kwargs["user_prompt"]
        assert "{unknown_key}" in prompt
        assert "Hola" in prompt

    with patch("eloquent_notes.app.llm.classify_transcription") as mock_classify:
        eloquent_app._classify(ai_cfg, obs_cfg, loaded, "Rewritten text", lang_inst)
        prompt = mock_classify.call_args.kwargs["user_prompt"]
        assert "{custom_brace}" in prompt
        assert "Rewritten text" in prompt


def test_on_processing_completed_branches(qapp):
    eloquent_app = make_app(qapp)

    # Success branch
    eloquent_app.state = "PROCESSING"
    eloquent_app._on_processing_completed("success", "/path/to/Note.md")
    assert eloquent_app.state == "IDLE"
    assert eloquent_app._recorder is None
    eloquent_app._notify.assert_called_with(
        "Dictation Saved", "Saved dictation to Obsidian (Note.md)",
    )

    # Empty branch
    eloquent_app.state = "PROCESSING"
    eloquent_app._on_processing_completed("empty", "")
    assert eloquent_app.state == "IDLE"
    eloquent_app._notify.assert_called_with(
        "Dictation Empty", "No note was created because the audio was empty.",
    )

    # Error branch
    eloquent_app.state = "PROCESSING"
    eloquent_app._on_processing_completed("error", "API timeout")
    assert eloquent_app.state == "IDLE"
    eloquent_app._notify.assert_called_with(
        "Processing Error", "Error processing dictation: API timeout",
    )


def test_preload_model_uses_snapshot(qapp):
    eloquent_app = make_app(qapp)
    snapshot = _pipeline_snapshot()
    snapshot["ai"]["context_length"] = 2048

    with patch("eloquent_notes.app.llm.preload_model") as mock_preload:
        eloquent_app._preload_model(snapshot)
        mock_preload.assert_called_once_with(
            ollama_url="http://localhost:11434",
            model="gemma",
            context_length=2048,
            keep_alive="5m",
            timeout=10,
        )

    with patch(
        "eloquent_notes.app.llm.preload_model",
        side_effect=requests.RequestException("Connection refused"),
    ):
        eloquent_app._preload_model(snapshot)

    with patch(
        "eloquent_notes.app.llm.preload_model",
        side_effect=ValueError("Invalid URL"),
    ):
        eloquent_app._preload_model(snapshot)


def test_reload_config_success_and_failure(qapp):
    eloquent_app = make_app(qapp)
    valid_config = {"logging": {"level": "DEBUG", "max_mb": 10, "backup_count": 2}}

    with patch(
        "eloquent_notes.app.config.load_config",
        return_value=valid_config,
    ), patch("eloquent_notes.app.setup_logging") as mock_setup:
        eloquent_app.reload_config()
        mock_setup.assert_called_once_with(
            log_level_str="DEBUG", max_mb=10, backup_count=2,
        )
        assert eloquent_app.config == valid_config
        eloquent_app._notify.assert_called_with(
            "Eloquent Notes", "Configuration reloaded successfully.",
        )

    with patch(
        "eloquent_notes.app.config.load_config",
        return_value={"logging": {"level": "INVALID", "max_mb": 10, "backup_count": 2}},
    ), patch(
        "eloquent_notes.app.setup_logging",
        side_effect=ValueError("Invalid log level"),
    ):
        eloquent_app.reload_config()
        assert eloquent_app.config == valid_config
        eloquent_app._notify.assert_called_with(
            "Configuration Error", "Failed to reload configuration: Invalid log level",
        )

    with patch(
        "eloquent_notes.app.config.load_config",
        side_effect=ValueError("Corrupt YAML"),
    ):
        eloquent_app.reload_config()
        assert eloquent_app.config == valid_config
        eloquent_app._notify.assert_called_with(
            "Configuration Error", "Failed to reload configuration: Corrupt YAML",
        )


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


def test_tray_menu_creation_and_activation(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app.toggle_action = MagicMock()

    menu = eloquent_app._create_tray_menu()
    assert menu is not None
    assert len(menu.actions()) >= 4

    eloquent_app._on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
    eloquent_app.toggle_action.assert_called_once()


def test_exit_app_cleanup(qapp):
    eloquent_app = make_app(qapp)
    eloquent_app.state = "RECORDING"
    mock_recorder = MagicMock()
    mock_recorder.stop.side_effect = RuntimeError("PortAudio error on exit")
    eloquent_app._recorder = mock_recorder
    eloquent_app._config_dialog = MagicMock()
    eloquent_app.server = MagicMock()
    eloquent_app.tray = MagicMock()
    eloquent_app.app = MagicMock()

    with pytest.raises(SystemExit):
        eloquent_app.exit_app()

    mock_recorder.stop.assert_called_once()
    eloquent_app._config_dialog.close.assert_called_once()
    eloquent_app.server.close.assert_called_once()
    eloquent_app.tray.hide.assert_called_once()
    eloquent_app.app.quit.assert_called_once()


def test_run_schedules_initial_toggle_after_tray_init(qapp):
    with patch("eloquent_notes.app.QTimer.singleShot") as mock_single_shot:
        eloquent_app = EloquentApp(qapp, start_recording_immediately=True)
        mock_single_shot.assert_not_called()

        eloquent_app.app = MagicMock()
        eloquent_app.app.exec.return_value = 0
        with patch("eloquent_notes.app.QSystemTrayIcon"), patch.object(
            eloquent_app, "_init_ipc_server",
        ), patch.object(eloquent_app, "_init_tray_ui"), pytest.raises(SystemExit):
            eloquent_app.run()

        mock_single_shot.assert_called_once_with(100, eloquent_app.toggle_action)


def test_app_main_entry_point(monkeypatch):
    mock_qapp = MagicMock()
    mock_eloquent_app = MagicMock()

    monkeypatch.setattr("eloquent_notes.app.QApplication", lambda args: mock_qapp)
    monkeypatch.setattr(
        "eloquent_notes.app.EloquentApp",
        lambda app, start_recording_immediately, **kwargs: mock_eloquent_app,
    )
    monkeypatch.setattr("eloquent_notes.app.setup_logging", MagicMock())
    monkeypatch.setattr(sys, "argv", ["eloquent-notes", "toggle"])

    app_main()

    mock_qapp.setQuitOnLastWindowClosed.assert_called_once_with(False)
    mock_eloquent_app.run.assert_called_once()
