"""Unit tests for eloquent_notes.audio module."""

import io
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from eloquent_notes.audio import (
    PCM16_MAX,
    SAMPLE_RATE,
    SPEECH_PAD_S,
    VAD_WINDOW_SAMPLES,
    AudioRecorder,
    _trim_speech,
    encode_wav_bytes,
    play_beep,
    speech_window_mask,
)

SPEECH_WAV_PATH = Path(__file__).parent / "data" / "speech_16k.wav"


def _load_speech() -> np.ndarray:
    with wave.open(str(SPEECH_WAV_PATH), "rb") as wf:
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    return (pcm.astype(np.float32) / PCM16_MAX).reshape(-1, 1)


def test_recorder_init():
    recorder = AudioRecorder(channels=2)
    assert recorder.channels == 2
    assert recorder._stream is None


@patch("sounddevice.InputStream")
def test_start_and_stop(mock_input_stream):
    stream_instance = MagicMock()
    mock_input_stream.return_value = stream_instance

    recorder = AudioRecorder(channels=1)
    recorder.start()

    mock_input_stream.assert_called_once_with(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        callback=recorder._on_audio,
    )
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

    recorder = AudioRecorder(channels=1)
    with pytest.raises(RuntimeError, match="Device unavailable"):
        recorder.start()

    stream_instance.close.assert_called_once()
    assert recorder._stream is None


def test_stop_exception_safety():
    recorder = AudioRecorder(channels=1)
    stream_instance = MagicMock()
    stream_instance.stop.side_effect = Exception("PortAudio error")
    recorder._stream = stream_instance

    with pytest.raises(Exception, match="PortAudio error"):
        recorder.stop()

    assert stream_instance.close.called
    assert recorder._stream is None


def test_callback_enqueues_copy():
    recorder = AudioRecorder(channels=1)
    chunk = np.zeros((100, 1), dtype=np.float32)
    recorder._on_audio(chunk, 100, None, None)

    queued_chunk = recorder._chunks[0]
    assert np.array_equal(queued_chunk, chunk)
    assert queued_chunk is not chunk


def test_wav_bytes_without_data_is_empty():
    recorder = AudioRecorder(channels=1)
    assert recorder.wav_bytes == b""
    assert encode_wav_bytes(np.empty(0, dtype=np.float32), SAMPLE_RATE, 1) == b""


def test_wav_bytes_encodes_captured_chunks():
    recorder = AudioRecorder(channels=1)
    speech = _load_speech()
    recorder._chunks.append(speech[:24000])
    recorder._chunks.append(speech[24000:])

    wav_bytes = recorder.wav_bytes
    assert recorder.wav_bytes == wav_bytes
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == SAMPLE_RATE
        assert wf.getnframes() == len(speech)


def test_speech_window_mask_short_and_stereo():
    assert speech_window_mask(np.empty(0, dtype=np.float32)).size == 0
    assert speech_window_mask(np.ones(VAD_WINDOW_SAMPLES - 1, dtype=np.float32)).size == 0

    mono = _load_speech().ravel()
    stereo = np.column_stack([mono, mono])
    mono_mask = speech_window_mask(mono)
    stereo_mask = speech_window_mask(stereo)
    assert np.any(stereo_mask)
    assert np.array_equal(stereo_mask, mono_mask)


def test_is_silent_rejects_non_speech():
    assert AudioRecorder(channels=1).is_silent is True

    rng = np.random.default_rng(0)
    num_samples = SAMPLE_RATE * 2
    t = np.linspace(0.0, 2.0, num_samples, endpoint=False, dtype=np.float32)

    silence = np.zeros(num_samples, dtype=np.float32)
    white_noise = rng.standard_normal(num_samples).astype(np.float32) * 0.2
    hum_50hz = (sum(np.sin(2.0 * np.pi * 50.0 * k * t) / k for k in range(1, 12)) * 0.2).astype(np.float32)
    low_thump = (np.sin(2.0 * np.pi * 40.0 * t) * 0.4).astype(np.float32)
    high_tone = (np.sin(2.0 * np.pi * 5000.0 * t) * 0.4).astype(np.float32)

    chord_notes = (261.6, 329.6, 392.0, 523.3)
    chords = np.zeros(num_samples, dtype=np.float32)
    step = SAMPLE_RATE // 2
    for idx, start in enumerate(range(0, num_samples, step)):
        seg_t = np.arange(step, dtype=np.float32) / SAMPLE_RATE
        base = chord_notes[idx % len(chord_notes)]
        env = np.exp(-seg_t * 3.0)
        chords[start : start + step] = env * sum(np.sin(2.0 * np.pi * base * h * seg_t) / h for h in range(1, 6))
    chords *= 0.2

    for signal in (silence, white_noise, hum_50hz, chords, low_thump, high_tone):
        recorder = AudioRecorder(channels=1)
        recorder._chunks.append(signal.reshape(-1, 1))
        assert recorder.is_silent is True


def test_is_silent_accepts_real_speech():
    rng = np.random.default_rng(0)
    speech = _load_speech()

    clean_recorder = AudioRecorder(channels=1)
    clean_recorder._chunks.append(speech)
    assert clean_recorder.is_silent is False

    speech_rms = float(np.sqrt(np.mean(speech**2)))
    noise_rms = speech_rms / (10.0 ** (5.0 / 20.0))
    noisy_speech = speech + rng.standard_normal(speech.shape).astype(np.float32) * noise_rms

    noisy_recorder = AudioRecorder(channels=1)
    noisy_recorder._chunks.append(noisy_speech)
    assert noisy_recorder.is_silent is False


def test_short_burst_is_silent():
    speech = _load_speech()
    silence = np.zeros((SAMPLE_RATE, 1), dtype=np.float32)
    short_burst = np.concatenate([silence, speech[: int(SAMPLE_RATE * 0.3)], silence])

    recorder = AudioRecorder(channels=1)
    recorder._chunks.append(short_burst)
    assert recorder.is_silent is True


def test_trim_keeps_speech_with_padding():
    speech = _load_speech()
    silence = np.zeros((SAMPLE_RATE, 1), dtype=np.float32)
    click = np.zeros((SAMPLE_RATE, 1), dtype=np.float32)
    click[1000:1080] = 0.8

    recorder = AudioRecorder(channels=1)
    recorder._chunks.extend([click, silence, speech, silence, click])
    samples, active = recorder._analyze()
    trimmed = _trim_speech(samples, active)

    pad = int(SAMPLE_RATE * SPEECH_PAD_S)
    first_speech_sample = int(np.argmax(active)) * VAD_WINDOW_SAMPLES
    last_speech_sample = (len(active) - int(np.argmax(active[::-1]))) * VAD_WINDOW_SAMPLES
    expected_start = first_speech_sample - pad
    expected_end = last_speech_sample + pad

    assert len(trimmed) == expected_end - expected_start
    speech_offset = 2 * SAMPLE_RATE - expected_start
    assert 0 <= speech_offset <= pad
    assert np.array_equal(trimmed[speech_offset : speech_offset + len(speech)], speech)
    # Distant leading and trailing clicks were trimmed out
    assert np.max(np.abs(trimmed[:speech_offset])) == 0.0
    assert np.max(np.abs(trimmed[speech_offset + len(speech) :])) == 0.0

    with wave.open(io.BytesIO(recorder.wav_bytes), "rb") as wf:
        assert wf.getnframes() == len(trimmed)


def test_trim_keeps_interior_pauses():
    speech = _load_speech()
    pause = np.zeros((SAMPLE_RATE, 1), dtype=np.float32)
    data = np.concatenate([speech[:24000], pause, speech[24000:]])

    active = speech_window_mask(data)
    assert not np.all(active)
    trimmed = _trim_speech(data, active)
    assert np.array_equal(trimmed, data)


def test_trim_speech_returns_all_silent_audio_unchanged():
    quiet = np.zeros((SAMPLE_RATE, 1), dtype=np.float32)
    active = speech_window_mask(quiet)
    assert not np.any(active)
    assert np.array_equal(_trim_speech(quiet, active), quiet)


def test_recorder_reuses_analysis_across_is_silent_and_wav_bytes():
    recorder = AudioRecorder(channels=1)
    speech = _load_speech()
    recorder._chunks.append(speech[:24000])
    recorder._chunks.append(speech[24000:])

    with (
        patch("eloquent_notes.audio.np.concatenate", wraps=np.concatenate) as mock_concat,
        patch("eloquent_notes.audio.speech_window_mask", wraps=speech_window_mask) as mock_mask,
    ):
        assert recorder.is_silent is False
        assert len(recorder.wav_bytes) > 0
        assert len(recorder.wav_bytes) > 0

    chunk_concats = [c for c in mock_concat.call_args_list if c.args[0] is recorder._chunks]
    assert len(chunk_concats) == 1
    assert mock_mask.call_count == 1

    recorder._chunks.clear()
    assert recorder.is_silent is True
    assert recorder.wav_bytes == b""


@patch("sounddevice.wait")
@patch("sounddevice.play")
def test_play_beep_blocks_when_wait_true(mock_play, mock_wait):
    play_beep(frequency=440, duration=0.1, wait=True)

    assert mock_play.called
    assert mock_wait.called

    signal, sample_rate = mock_play.call_args[0]
    assert sample_rate == SAMPLE_RATE
    assert len(signal) == 1600
    assert signal.dtype == np.float32


@patch("sounddevice.wait")
@patch("sounddevice.play")
def test_play_beep_non_blocking(mock_play, mock_wait):
    play_beep(frequency=440, duration=0.1, wait=False)

    assert mock_play.called
    assert not mock_wait.called


@patch("sounddevice.wait")
@patch("sounddevice.play")
def test_play_beep_zero_duration(mock_play, mock_wait):
    play_beep(frequency=440, duration=0.0, wait=True)

    assert not mock_play.called
    assert not mock_wait.called
