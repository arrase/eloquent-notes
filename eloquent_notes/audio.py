"""Audio capture, voice activity detection and feedback tones.

AudioRecorder captures 16 kHz microphone audio via sounddevice, trims and
splits speech locally with Silero VAD into <= 30 s chunks, and encodes them as
16-bit PCM WAV bytes. play_beep generates short sine-wave feedback tones with
fade in/out to avoid speaker clicks.
"""

import io
import math
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
MAX_CHUNK_S = 30.0
MIN_SPEECH_WINDOWS = math.ceil(MIN_SPEECH_S * SAMPLE_RATE / VAD_WINDOW_SAMPLES)
MIN_PAUSE_WINDOWS = 8
PAD_SAMPLES = int(SAMPLE_RATE * SPEECH_PAD_S)
MAX_CHUNK_SAMPLES = int(SAMPLE_RATE * MAX_CHUNK_S)
MAX_CHUNK_WINDOWS = (MAX_CHUNK_SAMPLES - 2 * PAD_SAMPLES) // VAD_WINDOW_SAMPLES


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


def _find_runs(active: np.ndarray, w_start: int, limit: int) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    idx = w_start
    while idx < limit:
        if active[idx]:
            idx += 1
            continue
        run_end = idx + 1
        while run_end < limit and not active[run_end]:
            run_end += 1
        runs.append((idx, run_end))
        idx = run_end
    return runs


def _skip_leading_transients(active: np.ndarray, w_start: int, last: int) -> int:
    """Advance past short noise bursts (< MIN_SPEECH_WINDOWS) separated by a real pause."""
    while w_start < last:
        w_start += int(np.argmax(active[w_start:last]))
        limit = min(last, w_start + MAX_CHUNK_WINDOWS)
        pauses = [r for r in _find_runs(active, w_start, limit) if r[1] - r[0] >= MIN_PAUSE_WINDOWS]
        if pauses and int(np.count_nonzero(active[w_start : pauses[0][0]])) < MIN_SPEECH_WINDOWS:
            w_start = pauses[0][1]
            continue
        break
    return w_start


def _skip_trailing_transients(active: np.ndarray, first: int, w_end: int) -> int:
    """Retreat before short noise bursts (< MIN_SPEECH_WINDOWS) preceded by a real pause."""
    while w_end > first:
        w_end -= int(np.argmax(active[first:w_end][::-1]))
        start = max(first, w_end - MAX_CHUNK_WINDOWS)
        pauses = [r for r in _find_runs(active, start, w_end) if r[1] - r[0] >= MIN_PAUSE_WINDOWS]
        if pauses and int(np.count_nonzero(active[pauses[-1][1] : w_end])) < MIN_SPEECH_WINDOWS:
            w_end = pauses[-1][0]
            continue
        break
    return w_end


def _find_split(active: np.ndarray, w_start: int, limit: int) -> tuple[int, int]:
    """Return (chunk_end, next_start) window indices within active[w_start:limit]."""
    runs = _find_runs(active, w_start, limit)
    if not runs:
        return limit, limit

    midpoint = w_start + (limit - w_start) // 2
    pauses = [r for r in runs if r[1] - r[0] >= MIN_PAUSE_WINDOWS]
    pool = pauses or runs
    second_half = [r for r in pool if r[1] > midpoint]
    candidates = second_half or pool
    return max(candidates, key=lambda r: (r[1] - r[0], r[1]))


def _split_speech(data: np.ndarray, active: np.ndarray) -> list[np.ndarray]:
    if int(np.count_nonzero(active)) < MIN_SPEECH_WINDOWS:
        return []

    first = int(np.argmax(active))
    last = len(active) - int(np.argmax(active[::-1]))
    last = _skip_trailing_transients(active, first, last)
    spans: list[tuple[int, int]] = []
    w_start = first

    while w_start < last:
        w_start = _skip_leading_transients(active, w_start, last)
        if last - w_start <= MAX_CHUNK_WINDOWS:
            chunk_end = last
            next_start = last
        else:
            chunk_end, next_start = _find_split(active, w_start, w_start + MAX_CHUNK_WINDOWS)

        trimmed_end = _skip_trailing_transients(active, w_start, chunk_end)
        if int(np.count_nonzero(active[w_start:trimmed_end])) >= MIN_SPEECH_WINDOWS:
            spans.append((w_start, trimmed_end))
        w_start = next_start

    chunks: list[np.ndarray] = []
    for idx, (s_win, e_win) in enumerate(spans):
        start = max(0, s_win * VAD_WINDOW_SAMPLES - PAD_SAMPLES)
        end = min(len(data), e_win * VAD_WINDOW_SAMPLES + PAD_SAMPLES)
        if idx > 0:
            prev_end = spans[idx - 1][1]
            start = max(start, (prev_end + s_win) * VAD_WINDOW_SAMPLES // 2)
        if idx + 1 < len(spans):
            next_s = spans[idx + 1][0]
            end = min(end, (e_win + next_s) * VAD_WINDOW_SAMPLES // 2)
        chunks.append(data[start:end])

    return chunks


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
    """Single-use microphone recorder producing WAV chunks once stopped."""

    def __init__(self, channels: int) -> None:
        self.channels = channels
        self._chunks: list[np.ndarray] = []
        self._cached_chunks = 0
        self._speech_chunks: list[np.ndarray] = []
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

    def _analyze(self) -> list[np.ndarray]:
        if not self._chunks:
            self._cached_chunks = 0
            return []
        if self._cached_chunks != len(self._chunks):
            samples = np.concatenate(self._chunks)
            self._speech_chunks = _split_speech(samples, speech_window_mask(samples))
            self._cached_chunks = len(self._chunks)
        return self._speech_chunks

    @property
    def wav_chunks(self) -> list[bytes]:
        """Trim surrounding silence, split speech at pauses into <= 30 s chunks, and encode as WAV."""
        return [encode_wav_bytes(chunk, SAMPLE_RATE, self.channels) for chunk in self._analyze()]

    @property
    def is_silent(self) -> bool:
        """Report whether the recording lacks sustained human speech.

        The transcription model cannot be trusted to flag empty recordings: given
        silence or noise it frequently answers empty=false and invents text or a
        refusal, which the pipeline would then save as a note. Silero VAD gates
        recordings locally before any audio is sent to the model.
        """
        return not self._analyze()


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
