"""Audio capture, voice activity detection and feedback tones.

AudioRecorder captures 16 kHz microphone audio via sounddevice, filters and
trims speech locally with Silero VAD, and encodes it as 16-bit PCM WAV bytes.
play_beep generates short sine-wave feedback tones with fade in/out to avoid
speaker clicks.
"""

import io
import wave

import numpy as np
import sounddevice as sd
from silero_vad_lite import SileroVAD

PCM16_MAX = 32767.0
PCM16_MIN_INT = -32768
PCM16_MAX_INT = 32767
BYTES_PER_SAMPLE_16BIT = 2

SAMPLE_RATE = 16000
# Silero VAD scores fixed 32 ms windows (512 samples at 16 kHz).
VAD_WINDOW_SAMPLES = 512
SPEECH_PROBABILITY = 0.5
MIN_SPEECH_S = 0.5
# Silero reacts a few windows late at word onsets/offsets; keep a margin when trimming.
SPEECH_PAD_S = 0.2


def speech_window_mask(data: np.ndarray) -> np.ndarray:
    """Return one boolean per 32 ms window: True where Silero VAD detects speech."""
    mono = data.mean(axis=1) if data.ndim > 1 else data
    num_windows = len(mono) // VAD_WINDOW_SAMPLES
    if num_windows == 0:
        return np.empty(0, dtype=bool)
    windows = np.ascontiguousarray(mono[: num_windows * VAD_WINDOW_SAMPLES], dtype=np.float32)
    vad = SileroVAD(SAMPLE_RATE)
    return np.array(
        [
            vad.process(memoryview(w.data)) > SPEECH_PROBABILITY
            for w in windows.reshape(num_windows, VAD_WINDOW_SAMPLES)
        ],
        dtype=bool,
    )


def _trim_speech(data: np.ndarray, active: np.ndarray) -> np.ndarray:
    if not np.any(active):
        return data

    pad = int(SAMPLE_RATE * SPEECH_PAD_S)
    first = int(np.argmax(active))
    last = len(active) - int(np.argmax(active[::-1]))
    start = max(0, first * VAD_WINDOW_SAMPLES - pad)
    end = min(len(data), last * VAD_WINDOW_SAMPLES + pad)
    return data[start:end]


def encode_wav_bytes(data: np.ndarray, sample_rate: int, channels: int) -> bytes:
    """Encode captured float32 audio samples into 16-bit PCM WAV bytes."""
    if data.size == 0:
        return b""

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

    def __init__(self, channels: int) -> None:
        self.channels = channels
        self._chunks: list[np.ndarray] = []
        self._cached_chunks = 0
        self._samples = np.empty(0, dtype=np.float32)
        self._active = np.empty(0, dtype=bool)
        self._stream: sd.InputStream | None = None

    def _on_audio(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: dict,
        status: sd.CallbackFlags,
    ) -> None:
        """sounddevice callback — enqueue an immutable copy of each chunk."""
        self._chunks.append(indata.copy())

    def start(self) -> None:
        """Open the input stream and begin recording."""
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
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

    def _analyze(self) -> tuple[np.ndarray, np.ndarray]:
        if not self._chunks:
            self._cached_chunks = 0
            return np.empty(0, dtype=np.float32), np.empty(0, dtype=bool)
        if self._cached_chunks != len(self._chunks):
            self._samples = np.concatenate(self._chunks)
            self._active = speech_window_mask(self._samples)
            self._cached_chunks = len(self._chunks)
        return self._samples, self._active

    @property
    def wav_bytes(self) -> bytes:
        """Trim surrounding non-speech windows and encode captured speech as 16-bit PCM WAV.

        Trimming drops leading and trailing silence or click transients while keeping
        a short padding margin and interior pauses intact for the transcription model.
        """
        samples, active = self._analyze()
        trimmed = _trim_speech(samples, active)
        return encode_wav_bytes(trimmed, SAMPLE_RATE, self.channels)

    @property
    def is_silent(self) -> bool:
        """Report whether the recording lacks sustained human speech.

        The transcription model cannot be trusted to flag empty recordings: given
        silence or noise it frequently answers empty=false and invents text or a
        refusal, which the pipeline would then save as a note. Silero VAD gates
        recordings locally before any audio is sent to the model.
        """
        _, active = self._analyze()
        return int(np.count_nonzero(active)) * VAD_WINDOW_SAMPLES / SAMPLE_RATE < MIN_SPEECH_S


def play_beep(
    frequency: float,
    duration: float,
    wait: bool,
) -> None:
    """Play a short sine-wave beep for audible feedback.

    When wait=True the call blocks until playback finishes; callers use this
    before opening the microphone so the tone cannot leak into the recording.
    """
    num_samples = int(SAMPLE_RATE * duration)
    if num_samples <= 0:
        return

    t = np.linspace(0.0, duration, num_samples, endpoint=False, dtype=np.float32)
    tone = np.sin(2.0 * np.pi * frequency * t, dtype=np.float32)

    fade_len = min(int(SAMPLE_RATE * 0.01), num_samples // 2)
    if fade_len > 0:
        tone[:fade_len] *= np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
        tone[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)

    sd.play(tone, SAMPLE_RATE)
    if wait:
        sd.wait()
