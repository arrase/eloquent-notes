"""Unit tests for eloquent_notes.audio module."""

import io
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from eloquent_notes.audio import (
    AudioRecorder,
    encode_wav_bytes,
    is_silent,
    play_beep,
    speech_frame_mask,
    trim_silence,
)

SAMPLE_RATE = 16000


def _speech_signal(duration_s: float) -> np.ndarray:
    """Synthesize a harmonic voice-band signal (F0=150 Hz + harmonics)."""
    num_samples = int(SAMPLE_RATE * duration_s)
    t = np.linspace(0.0, duration_s, num_samples, endpoint=False, dtype=np.float32)
    signal = sum(np.sin(2.0 * np.pi * 150.0 * k * t) / k for k in range(1, 8))
    normalized = (signal / np.max(np.abs(signal))).astype(np.float32)
    return (normalized * 0.2).reshape(-1, 1)


def test_recorder_init():
    recorder = AudioRecorder(sample_rate=44100, channels=2)
    assert recorder.sample_rate == 44100
    assert recorder.channels == 2
    assert recorder._stream is None


@patch("sounddevice.InputStream")
def test_start_and_stop(mock_input_stream):
    stream_instance = MagicMock()
    mock_input_stream.return_value = stream_instance

    recorder = AudioRecorder(sample_rate=16000, channels=1)
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

    recorder = AudioRecorder(sample_rate=16000, channels=1)
    with pytest.raises(RuntimeError, match="Device unavailable"):
        recorder.start()

    stream_instance.close.assert_called_once()
    assert recorder._stream is None


def test_stop_exception_safety():
    recorder = AudioRecorder(sample_rate=16000, channels=1)
    stream_instance = MagicMock()
    stream_instance.stop.side_effect = Exception("PortAudio error")
    recorder._stream = stream_instance

    with pytest.raises(Exception, match="PortAudio error"):
        recorder.stop()

    assert stream_instance.close.called
    assert recorder._stream is None


def test_callback_enqueues_copy():
    recorder = AudioRecorder(sample_rate=16000, channels=1)
    chunk = np.zeros((100, 1), dtype=np.float32)
    recorder._on_audio(chunk, 100, None, None)

    queued_chunk = recorder._chunks[0]
    assert np.array_equal(queued_chunk, chunk)
    assert queued_chunk is not chunk


def test_wav_bytes_without_data_is_empty():
    recorder = AudioRecorder(sample_rate=SAMPLE_RATE, channels=1)
    assert recorder.wav_bytes == b""
    assert encode_wav_bytes(np.empty(0, dtype=np.float32), SAMPLE_RATE, 1) == b""


def test_wav_bytes_encodes_captured_chunks():
    recorder = AudioRecorder(sample_rate=SAMPLE_RATE, channels=1)
    speech = _speech_signal(0.3)
    recorder._chunks.append(speech[:2400])
    recorder._chunks.append(speech[2400:])

    wav_bytes = recorder.wav_bytes
    assert recorder.wav_bytes == wav_bytes
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == SAMPLE_RATE
        assert wf.getnframes() == len(speech)


def test_speech_frame_mask_rejects_short_buffers():
    assert speech_frame_mask(np.empty(0, dtype=np.float32), SAMPLE_RATE).size == 0
    assert np.array_equal(
        speech_frame_mask(np.ones(320, dtype=np.float32), SAMPLE_RATE),
        np.array([False]),
    )


def test_is_silent_rejects_noise_clicks_and_out_of_band_signals():
    rng = np.random.default_rng(0)
    t = np.linspace(0.0, 1.0, SAMPLE_RATE, endpoint=False, dtype=np.float32)

    # Silence and loud broadband white noise
    assert is_silent(np.zeros(SAMPLE_RATE, dtype=np.float32), SAMPLE_RATE) is True
    assert is_silent(rng.standard_normal(SAMPLE_RATE).astype(np.float32) * 0.1, SAMPLE_RATE) is True

    # Low-frequency desk thump (40 Hz) and high-frequency tone (5000 Hz)
    low_thump = (np.sin(2.0 * np.pi * 40.0 * t) * 0.4).astype(np.float32)
    high_tone = (np.sin(2.0 * np.pi * 5000.0 * t) * 0.4).astype(np.float32)
    assert is_silent(low_thump, SAMPLE_RATE) is True
    assert is_silent(high_tone, SAMPLE_RATE) is True

    # Mouse click / short transient (< 200 ms of voiced audio)
    click = np.zeros((SAMPLE_RATE, 1), dtype=np.float32)
    click[1600:1920] = _speech_signal(0.02)
    assert is_silent(click, SAMPLE_RATE) is True

    # Sustained speech in the 85-3500 Hz band (clean and with background noise)
    speech = _speech_signal(0.4)
    noisy_speech = speech + rng.standard_normal(speech.shape).astype(np.float32) * 0.02
    assert is_silent(speech, SAMPLE_RATE) is False
    assert is_silent(noisy_speech, SAMPLE_RATE) is False


def test_trim_silence_removes_leading_and_trailing_quiet_and_clicks():
    speech = _speech_signal(0.3)
    quiet = np.zeros((1600, 1), dtype=np.float32)
    click = np.zeros((1600, 1), dtype=np.float32)
    click[:320] = _speech_signal(0.02)

    data = np.concatenate([click, quiet, speech, quiet, click])
    trimmed = trim_silence(data, SAMPLE_RATE)
    assert np.array_equal(trimmed, speech)


def test_trim_silence_keeps_interior_pauses():
    part = _speech_signal(0.2)
    pause = np.zeros((1600, 1), dtype=np.float32)
    data = np.concatenate([part, pause, part])

    trimmed = trim_silence(data, SAMPLE_RATE)
    assert np.array_equal(trimmed, data)


def test_trim_silence_returns_all_silent_audio_unchanged():
    quiet = np.zeros((1600, 1), dtype=np.float32)
    assert np.array_equal(trim_silence(quiet, SAMPLE_RATE), quiet)


def test_recorder_is_silent_for_quiet_and_loud_capture():
    recorder = AudioRecorder(sample_rate=SAMPLE_RATE, channels=1)
    assert recorder.is_silent is True

    recorder._chunks.append(np.zeros((1600, 1), dtype=np.float32))
    assert recorder.is_silent is True

    recorder._chunks.append(_speech_signal(0.3))
    assert recorder.is_silent is False


def test_wav_bytes_trims_surrounding_silence():
    recorder = AudioRecorder(sample_rate=SAMPLE_RATE, channels=1)
    speech = _speech_signal(0.3)
    recorder._chunks.append(np.zeros((1600, 1), dtype=np.float32))
    recorder._chunks.append(speech)
    recorder._chunks.append(np.zeros((1600, 1), dtype=np.float32))

    with wave.open(io.BytesIO(recorder.wav_bytes), "rb") as wf:
        assert wf.getnframes() == len(speech)


@patch("sounddevice.wait")
@patch("sounddevice.play")
def test_play_beep_blocks_when_wait_true(mock_play, mock_wait):
    play_beep(frequency=440, duration=0.1, sample_rate=16000, wait=True)

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
    play_beep(frequency=440, duration=0.0, sample_rate=16000, wait=True)

    assert not mock_play.called
    assert not mock_wait.called
