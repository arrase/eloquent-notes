"""Unit tests for eloquent_notes.audio module."""

import io
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from eloquent_notes.audio import (
    MAX_CHUNK_SAMPLES,
    MAX_CHUNK_WINDOWS,
    MIN_PAUSE_WINDOWS,
    MIN_SPEECH_WINDOWS,
    PAD_SAMPLES,
    PCM16_MAX,
    SAMPLE_RATE,
    SPEECH_PAD_S,
    VAD_WINDOW_SAMPLES,
    AudioRecorder,
    _split_speech,
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


def test_wav_chunks_without_data_is_empty():
    recorder = AudioRecorder(channels=1)
    assert recorder.wav_chunks == []
    assert encode_wav_bytes(np.empty(0, dtype=np.float32), SAMPLE_RATE, 1) == b""


def test_wav_chunks_encodes_captured_chunks():
    recorder = AudioRecorder(channels=1)
    speech = _load_speech()
    recorder._chunks.append(speech[:24000])
    recorder._chunks.append(speech[24000:])

    wav_chunks = recorder.wav_chunks
    assert len(wav_chunks) == 1
    assert recorder.wav_chunks == wav_chunks
    with wave.open(io.BytesIO(wav_chunks[0]), "rb") as wf:
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
    burst = speech[: int(SAMPLE_RATE * 0.3)]
    short_burst = np.concatenate([silence, burst, silence])

    recorder = AudioRecorder(channels=1)
    recorder._chunks.append(short_burst)
    assert recorder.is_silent is True

    # Multiple short bursts whose combined active windows exceed MIN_SPEECH_WINDOWS remain silent
    multi_burst = np.concatenate([silence, burst, silence, burst, silence, burst, silence])
    assert int(np.count_nonzero(speech_window_mask(multi_burst))) >= MIN_SPEECH_WINDOWS
    multi_recorder = AudioRecorder(channels=1)
    multi_recorder._chunks.append(multi_burst)
    assert multi_recorder.is_silent is True


def test_trim_keeps_speech_with_padding():
    speech = _load_speech()
    silence = np.zeros((SAMPLE_RATE, 1), dtype=np.float32)
    click = np.zeros((SAMPLE_RATE, 1), dtype=np.float32)
    click[1000:1080] = 0.8

    recorder = AudioRecorder(channels=1)
    recorder._chunks.extend([click, silence, speech, silence, click])
    samples = np.concatenate(recorder._chunks)
    active = speech_window_mask(samples)
    [trimmed] = _split_speech(samples, active)

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

    wav_chunks = recorder.wav_chunks
    assert len(wav_chunks) == 1
    with wave.open(io.BytesIO(wav_chunks[0]), "rb") as wf:
        assert wf.getnframes() == len(trimmed)


def test_trim_keeps_interior_pauses():
    speech = _load_speech()
    pause = np.zeros((SAMPLE_RATE, 1), dtype=np.float32)
    data = np.concatenate([speech[:24000], pause, speech[24000:]])

    active = speech_window_mask(data)
    assert not np.all(active)
    [trimmed] = _split_speech(data, active)
    assert np.array_equal(trimmed, data)


def test_split_speech_returns_empty_for_silent_audio():
    quiet = np.zeros((SAMPLE_RATE, 1), dtype=np.float32)
    active = speech_window_mask(quiet)
    assert not np.any(active)
    assert _split_speech(quiet, active) == []


def test_split_speech_splits_long_audio_at_real_pauses():
    total_windows = 1300
    active = np.ones(total_windows, dtype=bool)
    # Place a 20-window (640 ms > 2 * SPEECH_PAD_S) pause in the second half of the first 30 s window
    pause_start, pause_end = 700, 720
    active[pause_start:pause_end] = False
    data = np.arange(total_windows * VAD_WINDOW_SAMPLES, dtype=np.float32).reshape(-1, 1)

    chunks = _split_speech(data, active)
    assert len(chunks) == 2
    for chunk in chunks:
        assert len(chunk) <= MAX_CHUNK_SAMPLES

    # First chunk ends at pause_start + PAD_SAMPLES, second chunk starts at pause_end - PAD_SAMPLES
    assert int(chunks[0][0, 0]) == 0
    assert int(chunks[0][-1, 0]) == pause_start * VAD_WINDOW_SAMPLES + PAD_SAMPLES - 1
    assert int(chunks[1][0, 0]) == pause_end * VAD_WINDOW_SAMPLES - PAD_SAMPLES
    assert int(chunks[1][-1, 0]) == total_windows * VAD_WINDOW_SAMPLES - 1

    # A long pause crossing midpoint (312..906) beats a shorter pause in the second half (916..925)
    crossing_active = np.ones(1100, dtype=bool)
    crossing_active[312:906] = False
    crossing_active[916:925] = False
    crossing_chunks = _split_speech(data[: 1100 * VAD_WINDOW_SAMPLES], crossing_active)
    assert len(crossing_chunks) == 2
    assert int(crossing_chunks[0][0, 0]) == 0
    assert int(crossing_chunks[0][-1, 0]) == 312 * VAD_WINDOW_SAMPLES + PAD_SAMPLES - 1


def test_split_speech_prioritizes_first_half_real_pause_over_second_half_micro_pause():
    total_windows = 1200
    active = np.ones(total_windows, dtype=bool)
    # Real inter-word pause (>= MIN_PAUSE_WINDOWS) in the first half
    real_pause_start, real_pause_end = 300, 300 + MIN_PAUSE_WINDOWS
    active[real_pause_start:real_pause_end] = False
    # Short stop-consonant closure (< MIN_PAUSE_WINDOWS) in the second half
    micro_pause_start, micro_pause_end = 750, 753
    active[micro_pause_start:micro_pause_end] = False
    data = np.arange(total_windows * VAD_WINDOW_SAMPLES, dtype=np.float32).reshape(-1, 1)

    chunks = _split_speech(data, active)
    assert len(chunks) == 2
    for chunk in chunks:
        assert len(chunk) <= MAX_CHUNK_SAMPLES

    # Must split at the real pause (300..308), never at the 3-window consonant closure (750..753)
    midpoint_sample = (real_pause_start + real_pause_end) * VAD_WINDOW_SAMPLES // 2
    assert int(chunks[0][-1, 0]) == midpoint_sample - 1
    assert int(chunks[1][0, 0]) == midpoint_sample


def test_split_speech_continuous_speech_no_pauses_and_short_pause_clamping():
    # Continuous speech > 30 s with zero silent windows splits cleanly at MAX_CHUNK_WINDOWS
    total_windows = 1100
    active = np.ones(total_windows, dtype=bool)
    data = np.arange(total_windows * VAD_WINDOW_SAMPLES, dtype=np.float32).reshape(-1, 1)

    chunks = _split_speech(data, active)
    assert len(chunks) == 2
    for chunk in chunks:
        assert len(chunk) <= MAX_CHUNK_SAMPLES

    split_sample = MAX_CHUNK_WINDOWS * VAD_WINDOW_SAMPLES
    assert int(chunks[0][-1, 0]) == split_sample - 1
    assert int(chunks[1][0, 0]) == split_sample
    assert np.array_equal(np.concatenate(chunks), data)

    # Fallback when only short pauses (< MIN_PAUSE_WINDOWS) exist: clamp PAD_SAMPLES at midpoint
    active_short_pause = np.ones(total_windows, dtype=bool)
    active_short_pause[600:604] = False
    chunks_short = _split_speech(data, active_short_pause)
    assert len(chunks_short) == 2
    midpoint_sample = (600 + 604) * VAD_WINDOW_SAMPLES // 2
    assert int(chunks_short[0][-1, 0]) == midpoint_sample - 1
    assert int(chunks_short[1][0, 0]) == midpoint_sample


def test_split_speech_discards_short_transients():
    # Leading transient (5..10) + pause (10..25) + first speech (25..625) + pause (625..650)
    # + intermediate transient (650..655) + pause (655..675) + second speech (675..1580)
    # + pause (1580..1600) + trailing transient (1600..1605)
    total_windows = 1610
    active = np.zeros(total_windows, dtype=bool)
    active[5:10] = True
    active[25:625] = True
    active[650:655] = True
    active[675:1580] = True
    active[1600:1605] = True
    assert 5 < MIN_SPEECH_WINDOWS <= 600
    data = np.arange(total_windows * VAD_WINDOW_SAMPLES, dtype=np.float32).reshape(-1, 1)

    chunks = _split_speech(data, active)
    # Leading (5..10), intermediate (650..655), and trailing (1600..1605) transients are discarded;
    # only the two sustained speech segments (25..625 and 675..1580) are emitted.
    assert len(chunks) == 2
    assert int(chunks[0][0, 0]) == 25 * VAD_WINDOW_SAMPLES - PAD_SAMPLES
    assert int(chunks[0][-1, 0]) == 625 * VAD_WINDOW_SAMPLES + PAD_SAMPLES - 1
    assert int(chunks[1][0, 0]) == 675 * VAD_WINDOW_SAMPLES - PAD_SAMPLES
    assert int(chunks[1][-1, 0]) == 1580 * VAD_WINDOW_SAMPLES + PAD_SAMPLES - 1

    # Single-chunk recording (<= MAX_CHUNK_WINDOWS) trims both leading (5..10) and trailing (650..655) transients
    single_active = np.zeros(660, dtype=bool)
    single_active[5:10] = True
    single_active[25:625] = True
    single_active[650:655] = True
    [single_chunk] = _split_speech(data[: 660 * VAD_WINDOW_SAMPLES], single_active)
    assert int(single_chunk[0, 0]) == 25 * VAD_WINDOW_SAMPLES - PAD_SAMPLES
    assert int(single_chunk[-1, 0]) == 625 * VAD_WINDOW_SAMPLES + PAD_SAMPLES - 1

    # Speech 0..900 (with internal pause 500..510) + pause 900..940 + trailing transient 940..945
    # stays a single chunk once the trailing transient is trimmed before the split loop
    near_limit_active = np.zeros(950, dtype=bool)
    near_limit_active[0:900] = True
    near_limit_active[500:510] = False
    near_limit_active[940:945] = True
    [near_limit_chunk] = _split_speech(data[: 950 * VAD_WINDOW_SAMPLES], near_limit_active)
    assert int(near_limit_chunk[0, 0]) == 0
    assert int(near_limit_chunk[-1, 0]) == 900 * VAD_WINDOW_SAMPLES + PAD_SAMPLES - 1

    # Intermediate transient (650..655) followed by a longer pause (655..680, 25 windows) than its
    # preceding pause (635..650, 15 windows): split occurs at 655..680 and the transient is trimmed
    # off the end of Chunk 1
    trailing_mid_active = np.zeros(total_windows, dtype=bool)
    trailing_mid_active[25:635] = True
    trailing_mid_active[650:655] = True
    trailing_mid_active[680:1580] = True
    trailing_mid_chunks = _split_speech(data, trailing_mid_active)
    assert len(trailing_mid_chunks) == 2
    assert int(trailing_mid_chunks[0][0, 0]) == 25 * VAD_WINDOW_SAMPLES - PAD_SAMPLES
    assert int(trailing_mid_chunks[0][-1, 0]) == 635 * VAD_WINDOW_SAMPLES + PAD_SAMPLES - 1
    assert int(trailing_mid_chunks[1][0, 0]) == 680 * VAD_WINDOW_SAMPLES - PAD_SAMPLES
    assert int(trailing_mid_chunks[1][-1, 0]) == 1580 * VAD_WINDOW_SAMPLES + PAD_SAMPLES - 1

    # Multiple short transients summing to >= MIN_SPEECH_WINDOWS across the recording yield no chunks
    bursts_active = np.zeros(100, dtype=bool)
    for start in (5, 25, 45, 65):
        bursts_active[start : start + 5] = True
    assert int(np.count_nonzero(bursts_active)) >= MIN_SPEECH_WINDOWS
    assert _split_speech(data[: 100 * VAD_WINDOW_SAMPLES], bursts_active) == []


def test_recorder_reuses_analysis_across_is_silent_and_wav_chunks():
    recorder = AudioRecorder(channels=1)
    speech = _load_speech()
    recorder._chunks.append(speech[:24000])
    recorder._chunks.append(speech[24000:])

    with (
        patch("eloquent_notes.audio.np.concatenate", wraps=np.concatenate) as mock_concat,
        patch("eloquent_notes.audio.speech_window_mask", wraps=speech_window_mask) as mock_mask,
    ):
        assert recorder.is_silent is False
        assert len(recorder.wav_chunks) == 1
        assert len(recorder.wav_chunks) == 1

    chunk_concats = [c for c in mock_concat.call_args_list if c.args[0] is recorder._chunks]
    assert len(chunk_concats) == 1
    assert mock_mask.call_count == 1

    recorder._chunks.clear()
    assert recorder.is_silent is True
    assert recorder.wav_chunks == []


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
