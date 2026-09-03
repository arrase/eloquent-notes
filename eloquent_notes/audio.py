"""Audio capture and feedback tones.

AudioRecorder captures default-input microphone audio via sounddevice and
encodes it as 16-bit PCM WAV bytes. play_beep generates short sine-wave
feedback tones with fade in/out to avoid speaker clicks.
"""

from __future__ import annotations

import io
import queue
import wave

import numpy as np
import sounddevice as sd

PCM16_MAX = 32767.0
PCM16_MIN_INT = -32768
PCM16_MAX_INT = 32767
BYTES_PER_SAMPLE_16BIT = 2


def encode_wav_bytes(chunks: list[np.ndarray], sample_rate: int, channels: int) -> bytes:
    """Encode captured float32 audio chunks into 16-bit PCM WAV bytes."""
    if not chunks:
        return b""

    data = np.concatenate(chunks)
    pcm16 = (data * PCM16_MAX).clip(PCM16_MIN_INT, PCM16_MAX_INT).astype(np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(BYTES_PER_SAMPLE_16BIT)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm16)
    return buffer.getvalue()


class AudioRecorder:
    """Single-use microphone recorder producing WAV bytes once stopped."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._chunks: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._wav_cache: bytes | None = None

    def _on_audio(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: dict,
        status: sd.CallbackFlags,
    ) -> None:
        """sounddevice callback — enqueue an immutable copy of each chunk."""
        self._chunks.put(indata.copy())

    def start(self) -> None:
        """Open the input stream and begin recording."""
        stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self._on_audio,
        )
        try:
            stream.start()
        except Exception:
            stream.close()
            raise
        self._stream = stream

    def stop(self) -> None:
        """Stop and close the input stream."""
        if self._stream is None:
            return
        stream, self._stream = self._stream, None
        try:
            stream.stop()
        finally:
            stream.close()

    @property
    def wav_bytes(self) -> bytes:
        """Encode captured chunks as 16-bit PCM WAV.

        Idempotent: caches result on first access so subsequent reads
        do not return empty bytes or destroy recorded audio.
        """
        if self._wav_cache is not None:
            return self._wav_cache

        chunks = list(self._chunks.queue)
        self._wav_cache = encode_wav_bytes(chunks, self.sample_rate, self.channels)
        return self._wav_cache


def play_beep(
    frequency: float = 440.0,
    duration: float = 0.1,
    sample_rate: int = 16000,
    wait: bool = True,
) -> None:
    """Play a short sine-wave beep for audible feedback.

    When wait=True the call blocks until playback finishes; callers use this
    before opening the microphone so the tone cannot leak into the recording.
    """
    num_samples = int(sample_rate * duration)
    if num_samples <= 0:
        return

    t = np.linspace(0.0, duration, num_samples, endpoint=False, dtype=np.float32)
    tone = np.sin(2.0 * np.pi * frequency * t, dtype=np.float32)

    fade_len = min(int(sample_rate * 0.01), num_samples // 2)
    if fade_len > 0:
        tone[:fade_len] *= np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
        tone[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)

    sd.play(tone, sample_rate)
    if wait:
        sd.wait()
