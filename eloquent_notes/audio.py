"""Audio capture and feedback tones.

AudioRecorder captures default-input microphone audio via sounddevice and
encodes it as 16-bit PCM WAV bytes. play_beep generates short sine-wave
feedback tones with fade in/out to avoid speaker clicks.
"""

import io
import queue
import wave

import numpy as np
import sounddevice as sd


class AudioRecorder:
    """Single-use microphone recorder producing WAV bytes once stopped."""

    def __init__(self, sample_rate=16000, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._chunks = queue.Queue()
        self._stream = None

    def _on_audio(self, indata, frames, time_info, status):
        """sounddevice callback — enqueue an immutable copy of each chunk."""
        self._chunks.put(indata.copy())

    def start(self):
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

    def stop(self):
        """Stop and close the input stream."""
        if self._stream is None:
            return
        stream, self._stream = self._stream, None
        try:
            stream.stop()
        finally:
            stream.close()

    @property
    def wav_bytes(self):
        """Drain the captured chunks and encode them as 16-bit PCM WAV.

        Returns b"" when nothing was captured.
        """
        chunks = []
        while True:
            try:
                chunks.append(self._chunks.get_nowait())
            except queue.Empty:
                break
        if not chunks:
            return b""

        data = np.concatenate(chunks)
        pcm16 = (data * 32767.0).clip(-32768, 32767).astype(np.int16)

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(self.channels)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm16.tobytes())
        return buffer.getvalue()


def play_beep(frequency=440, duration=0.1, sample_rate=16000, wait=True):
    """Play a short sine-wave beep for audible feedback.

    When wait=True the call blocks until playback finishes; callers use this
    before opening the microphone so the tone cannot leak into the recording.
    """
    num_samples = int(sample_rate * duration)
    if num_samples <= 0:
        return

    t = np.linspace(0.0, duration, num_samples, endpoint=False)
    tone = np.sin(2.0 * np.pi * frequency * t)

    fade_len = min(int(sample_rate * 0.01), num_samples // 2)
    if fade_len > 0:
        tone[:fade_len] *= np.linspace(0.0, 1.0, fade_len)
        tone[-fade_len:] *= np.linspace(1.0, 0.0, fade_len)

    sd.play(tone.astype(np.float32), sample_rate)
    if wait:
        sd.wait()
