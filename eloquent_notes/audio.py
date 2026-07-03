import io
import queue
import wave
import numpy as np
import sounddevice as sd

class AudioRecorder:
    def __init__(self, sample_rate=16000, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.q = queue.Queue()
        self.recording = False
        self.stream = None
        self.wav_bytes = None

    def callback(self, indata, frames, time, status):
        self.q.put(indata.copy())

    def start(self):
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            callback=self.callback,
            dtype='float32'
        )
        self.stream.start()
        self.recording = True

    def stop(self):
        if not self.recording:
            return
        self.recording = False
        self.stream.stop()
        self.stream.close()
        self.stream = None
        
        chunks = []
        while not self.q.empty():
            chunks.append(self.q.get())
            
        all_data = np.concatenate(chunks, axis=0) if chunks else np.zeros((0, self.channels), dtype=np.float32)
        pcm_data = (all_data * 32767.0).clip(-32768, 32767).astype(np.int16)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit PCM (2 bytes)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_data.tobytes())
            
        self.wav_bytes = wav_buffer.getvalue()

def play_beep(frequency=440, duration=0.1, sample_rate=16000):
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    sine_wave = np.sin(frequency * t * 2 * np.pi)
    
    # Smooth start and end to avoid clicks
    fade_len = min(int(sample_rate * 0.01), len(sine_wave) // 2)
    if fade_len > 0:
        fade_in = np.linspace(0.0, 1.0, fade_len)
        fade_out = np.linspace(1.0, 0.0, fade_len)
        sine_wave[:fade_len] *= fade_in
        sine_wave[-fade_len:] *= fade_out
        
    sd.play(sine_wave.astype(np.float32), sample_rate)
    sd.wait()
