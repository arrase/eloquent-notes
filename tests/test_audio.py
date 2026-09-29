"""Unit tests for eloquent_notes.audio module."""

import io
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from eloquent_notes.audio import (
    AudioRecorder,
    is_silent,
    play_beep,
    rms_level,
    trim_silence,
)


def test_recorder_init():
    recorder = AudioRecorder(sample_rate=44100, channels=2)
    assert recorder.sample_rate == 44100
    assert recorder.channels == 2
    assert recorder._stream is None


@patch("sounddevice.InputStream")
def test_start_and_stop(mock_input_stream):
    stream_instance = MagicMock()
    mock_input_stream.return_value = stream_instance

    recorder = AudioRecorder()
    recorder.start()

    mock_input_stream.assert_called_once()
    stream_instance.start.assert_called_once()
    assert recorder._stream is stream_instance

    recorder.stop()
    stream_instance.stop.assert_called_once()
    stream_instance.close.assert_called_once()
    assert recorder._stream is None

    # Stopping twice is a no-op
    recorder.stop()
    assert stream_instance.stop.call_count == 1


@patch("sounddevice.InputStream")
def test_start_failure_closes_stream_and_raises(mock_input_stream):
    stream_instance = MagicMock()
    stream_instance.start.side_effect = RuntimeError("Device unavailable")
    mock_input_stream.return_value = stream_instance

    recorder = AudioRecorder()
    with pytest.raises(RuntimeError, match="Device unavailable"):
        recorder.start()

    stream_instance.close.assert_called_once()
    assert recorder._stream is None


def test_stop_exception_safety():
    recorder = AudioRecorder()
    stream_instance = MagicMock()
    stream_instance.stop.side_effect = Exception("PortAudio error")
    recorder._stream = stream_instance

    with pytest.raises(Exception, match="PortAudio error"):
        recorder.stop()

    assert stream_instance.close.called
    assert recorder._stream is None


def test_callback_enqueues_copy():
    recorder = AudioRecorder()
    chunk = np.zeros((100, 1), dtype=np.float32)
    recorder._on_audio(chunk, 100, None, None)

    queued_chunk = recorder._chunks.get_nowait()
    assert np.array_equal(queued_chunk, chunk)
    assert queued_chunk is not chunk


def test_wav_bytes_without_data_is_empty():
    recorder = AudioRecorder(sample_rate=16000, channels=1)
    assert recorder.wav_bytes == b""


def test_wav_bytes_encodes_captured_chunks():
    recorder = AudioRecorder(sample_rate=16000, channels=1)
    recorder._chunks.put(np.ones((800, 1), dtype=np.float32) * 0.5)
    recorder._chunks.put(np.ones((800, 1), dtype=np.float32) * -0.5)

    wav_bytes = recorder.wav_bytes
    assert recorder.wav_bytes == wav_bytes
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 1600


def test_rms_level_of_silence_and_tone():
    assert rms_level(np.zeros((100, 1), dtype=np.float32)) == 0.0
    assert rms_level(np.empty((0, 1), dtype=np.float32)) == 0.0
    assert rms_level(np.full((100, 1), 0.5, dtype=np.float32)) == pytest.approx(0.5)


def test_is_silent_rejects_noise_but_accepts_speech():
    rng = np.random.default_rng(0)
    speech = rng.standard_normal(1600).astype(np.float32) * 0.2

    assert is_silent(np.zeros(1600, dtype=np.float32)) is True
    assert is_silent(rng.standard_normal(1600).astype(np.float32) * 0.001) is True
    assert is_silent(speech) is False


def test_trim_silence_removes_leading_and_trailing_quiet_blocks():
    loud = np.full((1600, 1), 0.2, dtype=np.float32)
    quiet = np.zeros((1600, 1), dtype=np.float32)

    trimmed = trim_silence([quiet, quiet, loud, quiet])
    assert len(trimmed) == 1
    assert np.array_equal(trimmed[0], loud)


def test_trim_silence_keeps_interior_pauses():
    loud = np.full((160, 1), 0.2, dtype=np.float32)
    quiet = np.zeros((160, 1), dtype=np.float32)

    trimmed = trim_silence([loud, quiet, loud])
    assert len(trimmed) == 3


def test_trim_silence_returns_all_silent_audio_unchanged():
    quiet = [np.zeros((16, 1), dtype=np.float32) for _ in range(3)]
    assert len(trim_silence(quiet)) == 3
    assert trim_silence([]) == []


def test_recorder_is_silent_for_quiet_and_loud_capture():
    recorder = AudioRecorder(sample_rate=16000, channels=1)
    assert recorder.is_silent is True

    recorder._chunks.put(np.zeros((1600, 1), dtype=np.float32))
    assert recorder.is_silent is True

    recorder._chunks.put(np.full((1600, 1), 0.2, dtype=np.float32))
    assert recorder.is_silent is False


def test_wav_bytes_trims_surrounding_silence():
    recorder = AudioRecorder(sample_rate=16000, channels=1)
    recorder._chunks.put(np.zeros((1600, 1), dtype=np.float32))
    recorder._chunks.put(np.full((1600, 1), 0.2, dtype=np.float32))
    recorder._chunks.put(np.zeros((1600, 1), dtype=np.float32))

    with wave.open(io.BytesIO(recorder.wav_bytes), "rb") as wf:
        assert wf.getnframes() == 1600


@patch("sounddevice.wait")
@patch("sounddevice.play")
def test_play_beep_blocks_by_default(mock_play, mock_wait):
    play_beep(frequency=440, duration=0.1, sample_rate=16000)

    assert mock_play.called
    assert mock_wait.called

    signal, sample_rate = mock_play.call_args[0]
    assert sample_rate == 16000
    assert len(signal) == 1600
    assert signal.dtype == np.float32


@patch("sounddevice.wait")
@patch("sounddevice.play")
def test_play_beep_non_blocking(mock_play, mock_wait):
    play_beep(frequency=440, duration=0.1, sample_rate=16000, wait=False)

    assert mock_play.called
    assert not mock_wait.called


@patch("sounddevice.wait")
@patch("sounddevice.play")
def test_play_beep_zero_duration(mock_play, mock_wait):
    play_beep(frequency=440, duration=0.0, sample_rate=16000)

    assert not mock_play.called
    assert not mock_wait.called
