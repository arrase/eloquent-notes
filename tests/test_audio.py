import io
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from eloquent_notes.audio import AudioRecorder, play_beep


def test_audio_recorder_init():
    recorder = AudioRecorder(sample_rate=44100, channels=2)
    assert recorder.sample_rate == 44100
    assert recorder.channels == 2
    assert recorder.stream is None
    assert recorder._wav_bytes is None


@patch("sounddevice.InputStream")
def test_audio_recorder_start_and_stop(mock_input_stream):
    mock_stream_instance = MagicMock()
    mock_input_stream.return_value = mock_stream_instance

    recorder = AudioRecorder()
    recorder.start()

    assert mock_input_stream.called
    assert mock_stream_instance.start.called
    assert recorder.stream == mock_stream_instance

    # Test calling start again stops existing stream and resets queue/bytes
    recorder._wav_bytes = b"cached"
    recorder.start()
    assert mock_stream_instance.stop.called
    assert mock_stream_instance.close.called
    assert recorder._wav_bytes is None

    # Test stop
    recorder.stop()
    assert recorder.stream is None


@patch("sounddevice.InputStream")
def test_audio_recorder_start_error_handling(mock_input_stream):
    mock_stream_instance = MagicMock()
    mock_stream_instance.start.side_effect = RuntimeError("Device unavailable")
    mock_input_stream.return_value = mock_stream_instance

    recorder = AudioRecorder()
    with pytest.raises(RuntimeError, match="Device unavailable"):
        recorder.start()

    assert mock_stream_instance.close.called
    assert recorder.stream is None


def test_audio_recorder_stop_exception_safety():
    recorder = AudioRecorder()
    mock_stream = MagicMock()
    mock_stream.stop.side_effect = Exception("PortAudio error")
    recorder.stream = mock_stream

    with pytest.raises(Exception, match="PortAudio error"):
        recorder.stop()

    assert mock_stream.close.called
    assert recorder.stream is None


def test_audio_recorder_wav_bytes_auto_stops_stream():
    recorder = AudioRecorder()
    mock_stream = MagicMock()
    recorder.stream = mock_stream

    wav_bytes = recorder.wav_bytes
    assert isinstance(wav_bytes, bytes)
    assert mock_stream.stop.called
    assert mock_stream.close.called
    assert recorder.stream is None


def test_audio_recorder_callback():
    recorder = AudioRecorder()
    chunk = np.zeros((100, 1), dtype=np.float32)
    recorder.callback(chunk, 100, None, None)

    assert not recorder.q.empty()
    queued_chunk = recorder.q.get_nowait()
    assert np.array_equal(queued_chunk, chunk)


def test_audio_recorder_wav_bytes_lazy_and_empty():
    recorder = AudioRecorder(sample_rate=16000, channels=1)

    # Empty queue produces valid WAV header with 0 data frames
    wav_bytes = recorder.wav_bytes
    assert isinstance(wav_bytes, bytes)
    assert len(wav_bytes) > 0
    assert recorder.wav_bytes is wav_bytes  # Cached


def test_audio_recorder_wav_bytes_with_data():
    recorder = AudioRecorder(sample_rate=16000, channels=1)

    # Add 2 chunks of sine wave data
    chunk1 = np.ones((800, 1), dtype=np.float32) * 0.5
    chunk2 = np.ones((800, 1), dtype=np.float32) * -0.5
    recorder.q.put(chunk1)
    recorder.q.put(chunk2)

    wav_bytes = recorder.wav_bytes
    assert isinstance(wav_bytes, bytes)

    # Verify wave header parameters
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 1600


@patch("sounddevice.wait")
@patch("sounddevice.play")
def test_play_beep(mock_play, mock_wait):
    play_beep(frequency=440, duration=0.1, sample_rate=16000)

    assert mock_play.called
    assert mock_wait.called

    args, kwargs = mock_play.call_args
    signal, sample_rate = args[0], args[1]
    assert sample_rate == 16000
    assert len(signal) == 1600
    assert signal.dtype == np.float32


@patch("sounddevice.wait")
@patch("sounddevice.play")
def test_play_beep_zero_duration(mock_play, mock_wait):
    play_beep(frequency=440, duration=0.0, sample_rate=16000)

    assert not mock_play.called
    assert not mock_wait.called
