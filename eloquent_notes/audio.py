"""Audio recording and playback utilities.

Provides AudioRecorder for capturing microphone input as WAV bytes,
and play_beep for audible feedback tones.
"""

import io
import queue
import threading
import wave

import numpy as np
import sounddevice as sd


class AudioRecorder:
    """Records audio from the default input device and produces WAV bytes."""

    def __init__(self, sample_rate=16000, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.q = queue.Queue()
        self.stream = None
        self._wav_bytes = None
        self._lock = threading.Lock()

    def callback(self, indata, frames, time, status):
        """Sounddevice stream callback — enqueues audio chunks."""
        self.q.put(indata.copy())

    def start(self):
        """Open the audio input stream and begin recording."""
        with self._lock:
            self._stop_unlocked()
            self.q = queue.Queue()
            self._wav_bytes = None

            stream = None
            try:
                stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    callback=self.callback,
                    dtype="float32",
                )
                stream.start()
                self.stream = stream
            except Exception:
                if stream is not None:
                    stream.close()
                self.stream = None
                raise

    def stop(self):
        """Stop the recording stream. Non-blocking."""
        with self._lock:
            self._stop_unlocked()

    def _stop_unlocked(self):
        """Internal helper to stop and close stream without lock recursion."""
        if self.stream is not None:
            stream = self.stream
            self.stream = None
            try:
                stream.stop()
            finally:
                stream.close()

    @property
    def wav_bytes(self):
        """Compile captured audio to WAV bytes on demand (lazy loading)."""
        with self._lock:
            if self.stream is not None:
                self._stop_unlocked()

            if self._wav_bytes is None:
                chunks = []
                while True:
                    try:
                        chunks.append(self.q.get_nowait())
                    except queue.Empty:
                        break

                if chunks:
                    all_data = np.concatenate(chunks, axis=0)
                else:
                    all_data = np.zeros((0, self.channels), dtype=np.float32)

                pcm_data = (all_data * 32767.0).clip(-32768, 32767).astype(np.int16)

                wav_buffer = io.BytesIO()
                with wave.open(wav_buffer, "wb") as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(2)  # 16-bit PCM
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(pcm_data.tobytes())

                self._wav_bytes = wav_buffer.getvalue()
            return self._wav_bytes


def play_beep(frequency=440, duration=0.1, sample_rate=16000):
    """Play a short sine-wave beep for audible feedback."""
    num_samples = int(sample_rate * duration)
    if num_samples <= 0:
        return

    t = np.linspace(0, duration, num_samples, endpoint=False)
    sine_wave = np.sin(frequency * t * 2 * np.pi)

    # Smooth start and end to avoid clicks
    fade_len = min(int(sample_rate * 0.01), num_samples // 2)
    if fade_len > 0:
        fade_in = np.linspace(0.0, 1.0, fade_len)
        fade_out = np.linspace(1.0, 0.0, fade_len)
        sine_wave[:fade_len] *= fade_in
        sine_wave[-fade_len:] *= fade_out

    sd.play(sine_wave.astype(np.float32), sample_rate)
    sd.wait()
