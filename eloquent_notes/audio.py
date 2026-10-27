"""Audio capture and feedback tones.

AudioRecorder captures default-input microphone audio via sounddevice and
encodes it as 16-bit PCM WAV bytes. play_beep generates short sine-wave
feedback tones with fade in/out to avoid speaker clicks.
"""

import io
import wave

import numpy as np
import sounddevice as sd

PCM16_MAX = 32767.0
PCM16_MIN_INT = -32768
PCM16_MAX_INT = 32767
BYTES_PER_SAMPLE_16BIT = 2

# Voice activity detection constants (20 ms framing at the configured sample rate).
FRAME_DURATION_S = 0.02
SPEECH_LOW_HZ = 85.0
SPEECH_HIGH_HZ = 3500.0
SPEECH_RMS_THRESHOLD = 0.012
SPEECH_SNR_FACTOR = 2.0
MIN_VOICE_BAND_RATIO = 0.5
MAX_SPEECH_FLATNESS = 0.25
MIN_SPEECH_FRAMES = 10
EPSILON = 1e-12


def speech_frame_mask(data: np.ndarray, sample_rate: int) -> np.ndarray:
    """Return a boolean mask of 20 ms frames containing sustained human speech.

    Each frame is evaluated in the frequency domain and must simultaneously:
    1. Concentrate at least 50% of its AC energy in the 85-3500 Hz voice band
       (rejecting low-frequency mic bumps/pops and high-frequency clicks/hiss).
    2. Exhibit harmonic/formant structure via low spectral flatness <= 0.25
       (rejecting broadband white/pink noise, fan hum and breath noise).
    3. Exceed both the absolute RMS floor (-38 dBFS) and 2x the recording's
       adaptive broadband noise floor (+6 dB SNR).
    Isolated single-frame transients (< 40 ms) are discarded.
    """
    mono = data.mean(axis=1) if data.ndim > 1 else data
    frame_len = int(sample_rate * FRAME_DURATION_S)
    num_frames = len(mono) // frame_len
    if num_frames < 2:
        return np.zeros(num_frames, dtype=bool)

    frames = mono[: num_frames * frame_len].reshape(num_frames, frame_len)
    spectrum = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    freqs = np.fft.rfftfreq(frame_len, d=1.0 / sample_rate)
    band_mask = (freqs >= SPEECH_LOW_HZ) & (freqs <= SPEECH_HIGH_HZ)

    weights = np.full(len(freqs), 2.0 / (frame_len**2))
    weights[0] = 0.0

    total_power = spectrum @ weights
    band_power = spectrum[:, band_mask] @ weights[band_mask]
    band_rms = np.sqrt(band_power)
    band_ratio = band_power / np.maximum(total_power, EPSILON)

    band_spec = spectrum[:, band_mask] + EPSILON
    flatness = np.exp(np.mean(np.log(band_spec), axis=1)) / np.mean(band_spec, axis=1)

    noise_estimate = band_rms * np.clip(flatness / MAX_SPEECH_FLATNESS, 0.0, 1.0)
    noise_floor = float(np.percentile(noise_estimate, 20))
    threshold = max(SPEECH_RMS_THRESHOLD, noise_floor * SPEECH_SNR_FACTOR)

    active = (band_rms >= threshold) & (band_ratio >= MIN_VOICE_BAND_RATIO) & (flatness <= MAX_SPEECH_FLATNESS)
    pair = active[:-1] & active[1:]
    sustained = np.zeros_like(active)
    sustained[:-1] |= pair
    sustained[1:] |= pair
    return sustained


def is_silent(data: np.ndarray, sample_rate: int) -> bool:
    """Report whether an audio buffer lacks sustained human speech.

    The transcription model cannot be trusted to flag empty recordings: given
    silence or noise it frequently answers empty=false and invents text or a
    refusal, which the pipeline would then save as a note. This gate decides
    locally and deterministically before any audio is sent to the model.
    """
    return int(np.count_nonzero(speech_frame_mask(data, sample_rate))) < MIN_SPEECH_FRAMES


def _trim_frames(data: np.ndarray, sample_rate: int, active: np.ndarray) -> np.ndarray:
    if not np.any(active):
        return data

    frame_len = int(sample_rate * FRAME_DURATION_S)
    first = int(np.argmax(active))
    last = len(active) - int(np.argmax(active[::-1]))
    return data[first * frame_len : last * frame_len]


def trim_silence(data: np.ndarray, sample_rate: int) -> np.ndarray:
    """Drop leading and trailing non-speech frames around the spoken segment.

    Trimming removes surrounding silence and start/stop click transients so the
    model encodes only the spoken dictation while keeping interior pauses intact.
    """
    return _trim_frames(data, sample_rate, speech_frame_mask(data, sample_rate))


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

    def __init__(self, sample_rate: int, channels: int) -> None:
        self.sample_rate = sample_rate
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

    def _analyze(self) -> tuple[np.ndarray, np.ndarray]:
        if not self._chunks:
            self._cached_chunks = 0
            return np.empty(0, dtype=np.float32), np.empty(0, dtype=bool)
        if self._cached_chunks != len(self._chunks):
            self._samples = np.concatenate(self._chunks)
            self._active = speech_frame_mask(self._samples, self.sample_rate)
            self._cached_chunks = len(self._chunks)
        return self._samples, self._active

    @property
    def wav_bytes(self) -> bytes:
        """Encode captured speech as 16-bit PCM WAV."""
        samples, active = self._analyze()
        trimmed = _trim_frames(samples, self.sample_rate, active)
        return encode_wav_bytes(trimmed, self.sample_rate, self.channels)

    @property
    def is_silent(self) -> bool:
        """Report whether the recording lacks sustained human speech.

        Checked locally so an accidental trigger, ambient noise or click never
        reaches the model, which cannot reliably report empty audio on its own.
        """
        _, active = self._analyze()
        return int(np.count_nonzero(active)) < MIN_SPEECH_FRAMES


def play_beep(
    frequency: float,
    duration: float,
    sample_rate: int,
    wait: bool,
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
