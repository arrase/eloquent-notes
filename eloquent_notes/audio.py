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

# RMS level (0.0-1.0) below which audio is treated as silence. Microphone
# noise floors sit far lower than speech; -45 dBFS leaves ample headroom for
# quiet dictation while rejecting true silence and hiss.
SILENCE_RMS_THRESHOLD = 0.0056


def rms_level(data: np.ndarray) -> float:
    """Return the root-mean-square amplitude of a float32 audio block."""
    if data.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(data, dtype=np.float64))))


def is_silent(data: np.ndarray, threshold: float = SILENCE_RMS_THRESHOLD) -> bool:
    """Report whether an audio block carries no speech-level energy.

    The transcription model cannot be trusted to flag empty recordings: given
    silence it has been observed to answer empty=false and invent text, which
    the pipeline would then save as a note. This RMS gate decides locally and
    deterministically, before any audio is sent to the model.
    """
    return rms_level(data) < threshold


def trim_silence(chunks: list[np.ndarray], threshold: float = SILENCE_RMS_THRESHOLD) -> list[np.ndarray]:
    """Drop leading and trailing blocks quieter than the speech threshold.

    Trimming reduces the audio the model must encode, which makes it less prone
    to filling the gaps with invented speech, and saves tokens. Interior
    pauses are preserved so the model's prosody handling is unchanged.
    """
    if not chunks:
        return []

    loud = [not is_silent(chunk, threshold) for chunk in chunks]
    if not any(loud):
        return chunks

    first = loud.index(True)
    last = len(loud) - loud[::-1].index(True)
    return chunks[first:last]


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

        chunks = trim_silence(list(self._chunks.queue))
        self._wav_cache = encode_wav_bytes(chunks, self.sample_rate, self.channels)
        return self._wav_cache

    @property
    def is_silent(self) -> bool:
        """Report whether the recording holds no speech-level energy.

        Checked locally so an accidental trigger in a quiet room never reaches
        the model, which cannot reliably report empty audio on its own.
        """
        chunks = list(self._chunks.queue)
        if not chunks:
            return True
        return all(is_silent(chunk) for chunk in chunks)


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
