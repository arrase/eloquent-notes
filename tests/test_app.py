"""Unit tests for eloquent_notes.app module."""

import copy
import sys
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
import requests
from PyQt6.QtWidgets import QSystemTrayIcon

from eloquent_notes import config, notes, ui
from eloquent_notes.app import EloquentApp
from eloquent_notes.app import main as app_main


@pytest.fixture
def mock_config(tmp_path):
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
        "notes": {
            "folder": str(tmp_path / "notes"),
            "columns": 2,
            "type_colors": dict(ui.DEFAULT_TYPE_COLORS),
        },
        "search": {
            "embedding_model": "embed",
            "keep_alive": "5m",
            "min_similarity": 0.3,
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
    eloquent_app._hud.close()
    eloquent_app._notify = MagicMock()
    eloquent_app._update_icon = MagicMock()
    eloquent_app._hud = MagicMock()
    eloquent_app._hud.isVisible.return_value = False
    return eloquent_app


def test_app_init_starts_idle(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app._hud.close()
    assert eloquent_app.state == "IDLE"
    assert eloquent_app._recorder is None
    assert eloquent_app._snapshot is None
    assert qapp.applicationName() == "eloquent-notes"
    assert qapp.desktopFileName() == "eloquent-notes"


def test_toggle_from_idle_starts_recording(qapp):
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

    # Prompts are snapshotted at recording start
    loaded = eloquent_app._snapshot["_loaded_files"]
    assert set(loaded) == set(config.PROMPT_PATHS)

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
    assert mock_thread_cls.call_args.kwargs["args"] == (recorder, snapshot, False)


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
    eloquent_app._hud.isVisible.return_value = True

    with patch("eloquent_notes.app.time.monotonic", return_value=100.0), patch(
        "eloquent_notes.app.threading.Thread",
    ):
        eloquent_app._recording_started_at = 60.0
        eloquent_app._on_recording_tick()

    eloquent_app._hud.update_progress.assert_called_once_with(40.0, 0.0, 30.0)
    assert eloquent_app.state == "PROCESSING"
    recorder.stop.assert_called_once()


def test_recording_tick_stops_timer_when_not_recording(qapp):
    eloquent_app = make_app(qapp)
    eloquent_app.state = "IDLE"
    eloquent_app._tick_timer.start(100)

    eloquent_app._on_recording_tick()

    assert not eloquent_app._tick_timer.isActive()


def test_start_recording_when_hud_disabled(qapp, mock_config):
    mock_config["audio"]["recording_hud_enabled"] = False
    eloquent_app = make_app(qapp)

    with patch(
        "eloquent_notes.app.audio.AudioRecorder", return_value=MagicMock(),
    ), patch("eloquent_notes.app.config.load_file", return_value="c"), patch(
        "eloquent_notes.app.threading.Thread",
    ):
        eloquent_app.toggle_action()

    eloquent_app._hud.show_recording.assert_not_called()
    eloquent_app._tick_timer.stop()


def test_ipc_connection_handling(qapp):
    eloquent_app = make_app(qapp)
    eloquent_app.toggle_action = MagicMock()
    eloquent_app.reload_config = MagicMock()
    eloquent_app.show_window = MagicMock()

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
        make_socket("open"),
    ]
    mock_server.hasPendingConnections.side_effect = [True, True, True, False]
    mock_server.nextPendingConnection.side_effect = sockets

    eloquent_app._handle_ipc_connection()

    eloquent_app.toggle_action.assert_called_once()
    eloquent_app.reload_config.assert_called_once()
    eloquent_app.show_window.assert_called_once()
    for socket in sockets:
        socket.disconnectFromServer.assert_called_once()


def test_update_icon_and_notify(qapp):
    eloquent_app = EloquentApp(qapp)
    eloquent_app._hud.close()
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


def test_process_audio_empty_wav(qapp):
    eloquent_app = make_app(qapp)
    eloquent_app.processing_completed = MagicMock()

    recorder = MagicMock()
    recorder.wav_bytes = b""
    recorder.is_silent = True
    snapshot = _pipeline_snapshot()

    with patch("eloquent_notes.app.llm.preload_model") as mock_preload:
        eloquent_app._process_audio(recorder, snapshot, False)

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
        "notes": {
            "folder": "/tmp/notes",
        },
        "_loaded_files": {
            config.RETRY_PROMPT_PATH: "retry prompt",
            config.REWRITING_SYSTEM_PROMPT_PATH: "sys rewrite",
            config.REWRITING_USER_PROMPT_PATH: (
                "{transcription}\n{language_instruction}"
            ),
            config.CLASSIFICATION_SYSTEM_PROMPT_PATH: "sys class",
            config.CLASSIFICATION_USER_PROMPT_PATH: (
                "{transcription}\n{language_instruction}"
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
        eloquent_app._process_audio(recorder, snapshot, False)

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
        eloquent_app._process_audio(recorder, snapshot, False)
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
        eloquent_app._process_audio(recorder, snapshot, False)

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
    snapshot["notes"]["folder"] = str(tmp_path / "notes")

    with patch(
        "eloquent_notes.app.llm.transcribe_audio",
        return_value={"empty": False, "transcription": "Hello note"},
    ) as mock_transcribe, patch(
        "eloquent_notes.app.llm.rewrite_transcription",
        return_value={"title": "Note Title", "content": "Clean note"},
    ), patch(
        "eloquent_notes.app.llm.classify_note",
        return_value={"type": "idea", "tags": ["#Tag1", "tag1", "two"]},
    ) as mock_classify, patch("eloquent_notes.app.llm.preload_model") as mock_preload:
        eloquent_app._process_audio(recorder, snapshot, False)

    eloquent_app.processing_completed.emit.assert_called_once_with("success", "Note Title")

    # Audio bytes are forwarded to phase 1
    assert mock_transcribe.call_args.kwargs["audio_bytes"] == recorder.wav_bytes

    # Phase 3 receives the rewritten content rather than raw transcription
    assert "Clean note" in mock_classify.call_args.kwargs["user_prompt"]
    assert "Hello note" not in mock_classify.call_args.kwargs["user_prompt"]

    # Since Phase 3 completed, preload_model is not called in finally
    mock_preload.assert_not_called()

    # The note is written to the notes folder with normalized tags
    [saved] = notes.load_notes(tmp_path / "notes")
    assert (saved.title, saved.type, saved.tags, saved.body) == ("Note Title", "idea", ["tag1", "two"], "Clean note")


def test_process_audio_append_stops_after_rewriting(qapp):
    eloquent_app = make_app(qapp)
    eloquent_app.processing_completed = MagicMock()

    recorder = MagicMock()
    recorder.is_silent = False
    snapshot = _pipeline_snapshot()

    with patch(
        "eloquent_notes.app.llm.transcribe_audio",
        return_value={"empty": False, "transcription": "more"},
    ), patch(
        "eloquent_notes.app.llm.rewrite_transcription",
        return_value={"title": "Ignored", "content": "More text"},
    ) as mock_rewrite, patch("eloquent_notes.app.llm.classify_note") as mock_classify, patch(
        "eloquent_notes.app.notes.create_note",
    ) as mock_create, patch("eloquent_notes.app.llm.preload_model") as mock_preload:
        eloquent_app._process_audio(recorder, snapshot, True)

    eloquent_app.processing_completed.emit.assert_called_once_with("appended", "More text")
    assert mock_rewrite.call_args.kwargs["keep_alive"] == "0"
    mock_classify.assert_not_called()
    mock_create.assert_not_called()
    mock_preload.assert_not_called()


def test_process_audio_rejects_empty_rewrite(qapp):
    eloquent_app = make_app(qapp)
    eloquent_app.processing_completed = MagicMock()

    recorder = MagicMock()
    recorder.is_silent = False
    snapshot = _pipeline_snapshot()

    with patch(
        "eloquent_notes.app.llm.transcribe_audio",
        return_value={"empty": False, "transcription": "hello"},
    ), patch(
        "eloquent_notes.app.llm.rewrite_transcription",
        return_value={"title": "Title", "content": "   "},
    ), patch("eloquent_notes.app.llm.preload_model"):
        eloquent_app._process_audio(recorder, snapshot, False)

    eloquent_app.processing_completed.emit.assert_called_once_with(
        "error", "Model returned empty note content",
    )


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
        eloquent_app._process_audio(recorder, snapshot, False)

    eloquent_app.processing_completed.emit.assert_called_once_with(
        "error", "Ollama failed",
    )
    mock_preload.assert_called_once()


def test_user_prompts_preserve_literal_braces(qapp):
    eloquent_app = make_app(qapp)
    snapshot = _pipeline_snapshot()
    ai_cfg = snapshot["ai"]
    loaded = snapshot["_loaded_files"]
    loaded[config.REWRITING_USER_PROMPT_PATH] = "JSON example: {{\"a\": 1}} {unknown_key} {transcription} {language_instruction}"
    loaded[config.CLASSIFICATION_USER_PROMPT_PATH] = "Rule {custom_brace}: {content} {transcription} {language_instruction}"

    lang_inst = EloquentApp._language_instruction("Spanish")
    assert "translating from the transcription language if necessary" in lang_inst

    with patch("eloquent_notes.app.llm.rewrite_transcription") as mock_rewrite:
        EloquentApp._rewrite(ai_cfg, loaded, "Hola", lang_inst, "5m")
        prompt = mock_rewrite.call_args.kwargs["user_prompt"]
        assert "{unknown_key}" in prompt
        assert "Hola" in prompt

    with patch("eloquent_notes.app.llm.classify_note") as mock_classify:
        eloquent_app._classify(ai_cfg, loaded, "Rewritten text", lang_inst)
        prompt = mock_classify.call_args.kwargs["user_prompt"]
        assert "{custom_brace}" in prompt
        assert prompt.count("Rewritten text") == 2


def test_on_processing_completed_branches(qapp):
    eloquent_app = make_app(qapp)

    # Success branch
    eloquent_app.state = "PROCESSING"
    eloquent_app._on_processing_completed("success", "Note Title")
    assert eloquent_app.state == "IDLE"
    assert eloquent_app._recorder is None
    eloquent_app._notify.assert_called_with("Note Saved", "Note Title")

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


def test_reload_config_success_and_failure(qapp, mock_config):
    eloquent_app = make_app(qapp)
    valid_config = copy.deepcopy(mock_config)
    valid_config["logging"] = {"level": "DEBUG", "max_mb": 10, "backup_count": 2}

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

    invalid_log_config = copy.deepcopy(valid_config)
    invalid_log_config["logging"]["level"] = "INVALID"
    with patch(
        "eloquent_notes.app.config.load_config",
        return_value=invalid_log_config,
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
    eloquent_app = make_app(qapp)
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
    eloquent_app = make_app(qapp)
    eloquent_app.toggle_action = MagicMock()

    menu = eloquent_app._create_tray_menu()
    assert menu is not None
    assert len(menu.actions()) >= 4

    eloquent_app._on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
    eloquent_app.toggle_action.assert_called_once()


def test_init_ipc_server_and_tray_ui(qapp):
    eloquent_app = make_app(qapp)

    mock_server = MagicMock()
    mock_server.listen.return_value = True
    with patch("eloquent_notes.app.QLocalServer", return_value=mock_server) as mock_server_cls:
        eloquent_app._init_ipc_server()
        mock_server_cls.removeServer.assert_called_once()
        mock_server.listen.assert_called_once()
        mock_server.newConnection.connect.assert_called_once_with(
            eloquent_app._handle_ipc_connection
        )

    failing_server = MagicMock()
    failing_server.listen.return_value = False
    failing_server.errorString.return_value = "Address in use"
    with patch("eloquent_notes.app.QLocalServer", return_value=failing_server), pytest.raises(
        RuntimeError, match="Address in use"
    ):
        eloquent_app._init_ipc_server()

    eloquent_app.tray = MagicMock()
    eloquent_app._init_tray_ui()
    eloquent_app.tray.setContextMenu.assert_called_once_with(eloquent_app.menu)
    eloquent_app.tray.show.assert_called_once()
    eloquent_app._update_icon.assert_called_with("gray", "Eloquent Notes (Idle)")


def test_exit_app_cleanup(qapp):
    eloquent_app = make_app(qapp)
    eloquent_app.state = "RECORDING"
    mock_recorder = MagicMock()
    mock_recorder.stop.side_effect = RuntimeError("PortAudio error on exit")
    eloquent_app._recorder = mock_recorder
    eloquent_app.window = MagicMock()
    eloquent_app._config_dialog = MagicMock()
    eloquent_app.server = MagicMock()
    eloquent_app.tray = MagicMock()
    eloquent_app.app = MagicMock()

    with pytest.raises(SystemExit):
        eloquent_app.exit_app()

    mock_recorder.stop.assert_called_once()
    eloquent_app.window.close.assert_called_once()
    eloquent_app._config_dialog.close.assert_called_once()
    eloquent_app.server.close.assert_called_once()
    eloquent_app.tray.hide.assert_called_once()
    eloquent_app.app.quit.assert_called_once()


def test_exit_app_waits_for_processing_thread(qapp):
    eloquent_app = make_app(qapp)
    eloquent_app.state = "PROCESSING"
    eloquent_app._processing_thread = MagicMock()
    eloquent_app.app = MagicMock()

    with pytest.raises(SystemExit):
        eloquent_app.exit_app()

    eloquent_app._processing_thread.join.assert_called_once_with(timeout=5.0)


def test_run_schedules_initial_toggle_after_tray_init(qapp):
    with patch("eloquent_notes.app.QTimer.singleShot") as mock_single_shot:
        eloquent_app = EloquentApp(qapp, start_recording_immediately=True)
        eloquent_app._hud.close()
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
    mock_install_desktop = MagicMock()

    monkeypatch.setattr("eloquent_notes.app.QApplication", lambda args: mock_qapp)
    monkeypatch.setattr(
        "eloquent_notes.app.EloquentApp",
        lambda app, start_recording_immediately, open_window_immediately, **kwargs: mock_eloquent_app,
    )
    monkeypatch.setattr("eloquent_notes.app.setup_logging", MagicMock())
    monkeypatch.setattr("eloquent_notes.app.autostart.install_desktop_entry", mock_install_desktop)
    monkeypatch.setattr(sys, "argv", ["eloquent-notes", "toggle"])

    app_main()

    mock_install_desktop.assert_called_once()
    mock_qapp.setQuitOnLastWindowClosed.assert_called_once_with(False)
    mock_eloquent_app.run.assert_called_once()


# --- Notes window integration -------------------------------------------------


def _write_note(folder, title="Groceries", body="Buy milk."):
    return notes.create_note(folder, title, "task", ["shopping"], body)


def test_show_window_creates_window_once_and_loads_notes(qapp, tmp_path):
    note = _write_note(tmp_path / "notes")
    eloquent_app = make_app(qapp)

    eloquent_app.show_window()
    window = eloquent_app.window
    window.show_note(note)
    window.reader.title_edit.setText("Edited in reader before show_window")
    assert window.stack.currentWidget() is window.reader

    eloquent_app.show_window()

    assert eloquent_app.window is window
    assert window.stack.currentWidget() is window.timeline
    assert [n.title for n in window.timeline._notes] == ["Edited in reader before show_window"]
    window.close()


def test_note_edited_is_saved_and_listed(qapp, tmp_path):
    note = _write_note(tmp_path / "notes")
    eloquent_app = make_app(qapp)
    eloquent_app.show_window()

    note.title = "Groceries for Sunday"
    eloquent_app.window.note_edited.emit(note)

    [saved] = notes.load_notes(tmp_path / "notes")
    assert saved.title == "Groceries for Sunday"
    assert eloquent_app.window.timeline._notes[0].title == "Groceries for Sunday"
    eloquent_app.window.close()


def test_delete_requested_moves_note_to_trash(qapp, tmp_path):
    note = _write_note(tmp_path / "notes")
    eloquent_app = make_app(qapp)
    eloquent_app.show_window()

    with patch("eloquent_notes.app.QFile.moveToTrash", return_value=True) as mock_trash:
        eloquent_app.window.delete_requested.emit(note)

    mock_trash.assert_called_once_with(str(note.path))
    eloquent_app._notify.assert_not_called()
    eloquent_app.window.close()


def test_delete_failure_notifies(qapp, tmp_path):
    note = _write_note(tmp_path / "notes")
    eloquent_app = make_app(qapp)

    with patch("eloquent_notes.app.QFile.moveToTrash", return_value=False):
        eloquent_app._on_delete_requested(note)

    assert eloquent_app._notify.call_args.args[0] == "Delete Failed"


def test_dictate_into_records_with_append_target(qapp, tmp_path):
    note = _write_note(tmp_path / "notes")
    eloquent_app = make_app(qapp)
    eloquent_app._start_recording = MagicMock()

    eloquent_app.dictate_into(note)

    assert eloquent_app._append_target is note
    eloquent_app._start_recording.assert_called_once()

    eloquent_app.state = "RECORDING"
    eloquent_app._stop_and_process = MagicMock()
    eloquent_app.dictate_into(note)
    eloquent_app._stop_and_process.assert_called_once()


def test_toggle_action_clears_append_target(qapp, tmp_path):
    eloquent_app = make_app(qapp)
    eloquent_app._append_target = _write_note(tmp_path / "notes")
    eloquent_app._start_recording = MagicMock()

    eloquent_app.toggle_action()

    assert eloquent_app._append_target is None


def test_appended_dictation_keeps_reader_edits(qapp, tmp_path):
    note = _write_note(tmp_path / "notes")
    eloquent_app = make_app(qapp)
    eloquent_app.show_window()
    window = eloquent_app.window
    window.show_note(note)
    window.reader.title_edit.setText("Edited while recording")
    eloquent_app._append_target = note
    eloquent_app.state = "PROCESSING"

    eloquent_app._on_processing_completed("appended", "Also eggs.")

    [saved] = notes.load_notes(tmp_path / "notes")
    assert saved.title == "Edited while recording"
    assert saved.body == "Buy milk.\n\nAlso eggs."
    assert window.reader.body_edit.toPlainText() == "Buy milk.\n\nAlso eggs."
    assert eloquent_app._append_target is None
    eloquent_app._notify.assert_called_with("Dictation Added", "Edited while recording")
    window.close()


def test_appended_dictation_without_window(qapp, tmp_path):
    note = _write_note(tmp_path / "notes")
    eloquent_app = make_app(qapp)
    eloquent_app._append_target = note

    eloquent_app._on_processing_completed("appended", "Also eggs.")

    assert notes.load_notes(tmp_path / "notes")[0].body == "Buy milk.\n\nAlso eggs."


def test_appended_dictation_does_not_resurrect_deleted_note(qapp, tmp_path):
    note = _write_note(tmp_path / "notes")
    eloquent_app = make_app(qapp)
    eloquent_app._append_target = note

    def move_to_trash(path_str):
        note.path.unlink()
        return True

    with patch("eloquent_notes.app.QFile.moveToTrash", side_effect=move_to_trash):
        eloquent_app._on_delete_requested(note)

    assert eloquent_app._append_target is None
    eloquent_app._on_processing_completed("appended", "Also eggs.")
    assert notes.load_notes(tmp_path / "notes") == []


def test_search_runs_in_background_and_reports_results(qapp, tmp_path):
    note = _write_note(tmp_path / "notes")
    eloquent_app = make_app(qapp)
    eloquent_app.show_window()
    eloquent_app._index = MagicMock()
    eloquent_app._index.search.return_value = [note]
    eloquent_app.window.show_search_results = MagicMock()

    with patch("eloquent_notes.app.threading.Thread") as mock_thread_cls:
        eloquent_app._start_search("milk")
    query, folder, cfg = mock_thread_cls.call_args.kwargs["args"]
    eloquent_app._run_search(query, folder, cfg)

    assert [n.title for n in eloquent_app._index.search.call_args.args[0]] == ["Groceries"]
    eloquent_app.window.show_search_results.assert_called_once_with("milk", [note])
    eloquent_app.window.close()


def test_search_failure_reaches_window(qapp, tmp_path):
    eloquent_app = make_app(qapp)
    eloquent_app.show_window()
    eloquent_app._index = MagicMock()
    eloquent_app._index.search.side_effect = requests.ConnectionError("Ollama down")
    eloquent_app.window.show_search_error = MagicMock()

    eloquent_app._run_search("milk", tmp_path / "notes", {})

    eloquent_app.window.show_search_error.assert_called_once_with("milk", "Ollama down")
    eloquent_app.window.close()


def test_tray_middle_click_toggles_window(qapp):
    eloquent_app = make_app(qapp)

    eloquent_app._on_tray_activated(QSystemTrayIcon.ActivationReason.MiddleClick)
    assert eloquent_app.window.isVisible()

    eloquent_app._on_tray_activated(QSystemTrayIcon.ActivationReason.MiddleClick)
    assert not eloquent_app.window.isVisible()


def test_update_icon_syncs_window_state(qapp):
    eloquent_app = make_app(qapp)
    eloquent_app._update_icon = EloquentApp._update_icon.__get__(eloquent_app, EloquentApp)
    eloquent_app.show_window()
    eloquent_app.state = "PROCESSING"

    eloquent_app._update_icon("orange", "Processing")

    assert not eloquent_app.window.reader.btn_dictate.isEnabled()
    eloquent_app.window.close()


def test_run_schedules_window_when_requested(qapp):
    with patch("eloquent_notes.app.QTimer.singleShot") as mock_single_shot:
        eloquent_app = EloquentApp(qapp, open_window_immediately=True)
        eloquent_app._hud.close()
        eloquent_app.app = MagicMock()
        eloquent_app.app.exec.return_value = 0
        with patch("eloquent_notes.app.QSystemTrayIcon"), patch.object(
            eloquent_app, "_init_ipc_server",
        ), patch.object(eloquent_app, "_init_tray_ui"), pytest.raises(SystemExit):
            eloquent_app.run()

        mock_single_shot.assert_called_once_with(100, eloquent_app.show_window)
