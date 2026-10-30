# Four-Phase AI Pipeline

Eloquent Notes utilizes a modular four-phase LLM processing pipeline powered by local models via the Ollama REST API (default model: `gemma4:e4b-it-qat`).

Rather than forcing a single small LLM call to transcribe audio, clean up prose, write a title, classify the note and generate tags at once, Eloquent Notes splits processing into four specialized sequential phases. The output is one structured Markdown note (see [Notes & Search](notes.md)).

---

## Pipeline Overview

```
                      ┌─────────────────────────────────┐
                      │  In-Memory Audio (WAV chunks)   │
                      │    (<= 30 s each via VAD)       │
                      └────────────────┬────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 1: Audio Transcription (Multimodal Input, per <= 30 s chunk)          │
│ - Inputs: Base64 WAV chunk + System & User Prompts                          │
│ - Tasks: Removes stutters, repetitions, and filler words; joins chunks.     │
│ - Output JSON: {"transcription": string, "empty": bool}                      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ (Early exit if all chunks empty)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 2: Note Rewriting & Formatting                                        │
│ - Inputs: Phase 1 Transcription + System & User Prompts                     │
│ - Tasks: Converts raw speech into clean first-person prose & short title.   │
│ - Output JSON: {"title": string, "content": string}                         │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 3: Note Classification                                                │
│ - Inputs: Phase 2 Rewritten Content + System & User Prompts                 │
│ - Tasks: Classifies the note type into one of six fixed English keys.       │
│ - Output JSON: {"type": string}                                             │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 4: Note Tagging                                                       │
│ - Inputs: Phase 2 Rewritten Content + System & User Prompts                 │
│ - Tasks: Generates 2 to 5 topic tags in the configured output_language.     │
│ - Output JSON: {"tags": list}                                               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
                   notes.create_note → "YYYY-MM-DD HHMMSS Title.md"
```

When the dictation was started with **Add dictation** on an existing note, the pipeline stops after Phase 2 (see [Add Dictation](#add-dictation-phases-1-2-only)).

---

## 1. Phase 1: Audio Transcription

Phase 1 iterates over the `<= 30 s` WAV audio chunks (`AudioRecorder.wav_chunks`) produced during dictation, base64 encodes each chunk, and sends it to the multimodal model endpoint, joining the non-empty transcriptions with `" "` before Phase 2.

### Goals
- Perform accurate speech-to-text conversion.
- Detect silent recordings, background noise, or accidental triggers (`empty: true`).
- Strip out false starts, stuttering, coughs, hesitations ("um", "ah", "like"), and duplicated phrases.

### JSON Format Schema
```json
{
  "type": "object",
  "properties": {
    "transcription": {
      "type": "string",
      "description": "Clean transcription of the spoken words in their original spoken language (never translate), or empty string if audio is empty."
    },
    "empty": {
      "type": "boolean",
      "description": "True if audio contains only silence, background noise, or no spoken words; False otherwise."
    }
  },
  "required": ["transcription", "empty"]
}
```

### Field Order Is Significant
Under constrained decoding Ollama emits properties in the order the schema declares them, so `transcription` is declared **before** `empty` on purpose. With `empty` first, the model must commit to that flag before it has transcribed anything, and it reports `empty: true` even when the transcript it then produces is correct — a note lost despite a perfect transcription. Declaring the transcript first makes the model transcribe and only then judge whether the audio was silent.

### Local Silence Detection

The model cannot be trusted to recognise silence or non-speech noise. Asked to label an empty recording it frequently answers `"empty": false` and invents text or a refusal — in testing, a clip of pure digital silence came back as `empty: false` with a fluent Spanish sentence about time, and 230 of 256 non-speech noise clips produced fabricated transcripts that the pipeline would otherwise have saved as notes. Frequency-domain DSP heuristics (voice-band energy ratio, spectral flatness, adaptive SNR) are not sufficient either, because music, sirens, motors, birds, laughter, snoring and colored ambient noise (fans, traffic) share harmonic structure and voice-band energy with human speech.

Eloquent Notes therefore decides emptiness locally via `AudioRecorder.is_silent`, which runs **Silero VAD** (`silero-vad-lite` on CPU) through `audio.speech_window_mask()`. The 16 kHz recording (`SAMPLE_RATE = 16000`) is sliced into fixed 32 ms windows (`VAD_WINDOW_SAMPLES = 512`), and each window is marked active when Silero's speech probability exceeds `0.5` (`SPEECH_PROBABILITY`). A recording must accumulate at least `0.5 s` of active speech windows (`MIN_SPEECH_S = 0.5`); otherwise `_process_audio()` emits the `empty` signal without contacting Ollama at all, so an accidental trigger, ambient noise, music or a cough cannot produce a fabricated note. Across a benchmark of 256 non-speech noise clips (ESC-50 and synthetic noise) and 200 LibriSpeech dictations (clean and noisy down to 0 dB SNR), this gate reduced noise clips saved as notes from 142/256 to **0/256** while losing **0/200** dictations. The model's own `empty` flag is retained in the schema and honoured, but treated as advisory.

### Silence Trimming & 30-Second VAD Segmentation

Because Gemma 4's audio encoder accepts clips of up to 30 seconds (`MAX_CHUNK_S = 30.0`), `AudioRecorder.wav_chunks` trims surrounding silence and segments longer dictations into `<= 30 s` WAV chunks via `audio._split_speech()`:

- **Single-chunk trimming (`<= 30 s`):** leading and trailing non-speech 32 ms windows (including isolated start/stop click transients with `< 0.5 s` of voice) are trimmed while keeping a `0.2 s` padding margin (`SPEECH_PAD_S = 0.2`) on each side so word onsets and offsets are not clipped, preserving interior pauses intact.
- **Natural-pause splitting (`> 30 s`):** when active speech exceeds `29.6 s` (`MAX_CHUNK_WINDOWS = 925`), `_find_split()` selects the longest real inter-word pause (`>= 256 ms`, `MIN_PAUSE_WINDOWS = 8` windows) in the second half of the window (or across the midpoint / first half if needed), avoiding intra-word consonant stop closures (`32–96 ms`). Padding between adjacent chunks is clamped to the pause midpoint so no samples are duplicated.
- **Per-chunk voice filter:** every resulting span must contain at least `0.5 s` of active speech (`MIN_SPEECH_WINDOWS = 16`); sub-`0.5 s` noise bursts or trailing clicks are discarded before encoding.
- **Sequential transcription & global synthesis:** `_process_audio()` transcribes each WAV chunk in Phase 1 and joins the non-empty segments with `" "` so Phases 2–4 operate on the complete dictation at once.

### Early Exit Safeguard
If every chunk in Phase 1 returns `"empty": true` or a blank transcription string, processing terminates immediately. The application fires an `"empty"` signal, displays a desktop notification ("Dictation Empty"), resets the tray icon to gray, and saves no file to disk.

---

## 2. Phase 2: Note Rewriting

Phase 2 converts the raw transcribed text from Phase 1 into clean, direct, first-person prose and a title.

### Goals
- Rephrase awkward oral phrasing into polished written prose (bullet and numbered lists allowed; no headers, bold or other decoration).
- Preserve the user's authentic first-person voice and core meaning without adding unsolicited commentary or external assumptions.
- Synthesize a concise title (maximum 8 words) summarizing the note's subject matter.

### JSON Format Schema
```json
{
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "description": "Concise title (max 8 words) in the requested output language."
    },
    "content": {
      "type": "string",
      "description": "Clean, direct note prose in the requested output language."
    }
  },
  "required": ["title", "content"]
}
```

---

## 3. Phase 3: Classification

Phase 3 (`llm.classify_note()`) reads the rewritten content from Phase 2 (`{content}`) and classifies the note's intent. Because `type` is always one of six fixed English enum keys, no `{language_instruction}` is sent.

### Goals
- **Type Classification:** one of six fixed English keys:
  - `task` → Action items, things to do.
  - `idea` → Proposals, creative thoughts, suggestions.
  - `note` → Information, observations, explanations.
  - `reminder` → Things to remember, deadlines.
  - `question` → Things to investigate or research.
  - `decision` → Choices made, conclusions reached.

### JSON Format Schema
```json
{
  "type": "object",
  "properties": {
    "type": {
      "type": "string",
      "enum": ["task", "idea", "note", "reminder", "question", "decision"],
      "description": "Classification of the note content."
    }
  },
  "required": ["type"]
}
```

---

## 4. Phase 4: Tagging

Phase 4 (`llm.tag_note()`) reads the rewritten content from Phase 2 (`{content}`) and generates topic tags in the configured `output_language`. It has no knowledge of other notes.

### Goals
- **Tag Generation:** 2 to 5 lowercase, single-word or hyphenated topic tags in the configured `output_language` (e.g., `["redis", "caching", "performance"]`), excluding generic note type names.

### JSON Format Schema
```json
{
  "type": "object",
  "properties": {
    "tags": {
      "type": "array",
      "items": { "type": "string" },
      "description": "2 to 5 relevant tags, lowercase, in the requested output language."
    }
  },
  "required": ["tags"]
}
```

---

## Saving the Note

After Phase 4, `notes.create_note()` writes the note into `notes.folder`:

- **Title** and **body** come from Phase 2, **type** from Phase 3, **tags** from Phase 4.
- **Tags** are normalized with `notes.normalize_tags()`: lowercased, leading `#` stripped, blanks and duplicates removed.
- `created` is the current local time with UTC offset; the file is named `YYYY-MM-DD HHMMSS Title.md` and written atomically.

The worker then emits `processing_completed("success", title)`; the main thread shows a **Note Saved** notification and refreshes the notes window.

---

## Add Dictation (Phases 1-2 Only)

**Add dictation** in the reader starts a recording targeted at the open note. Processing runs Phase 1 and Phase 2 only (passing `ai.keep_alive` directly to Phase 2 since Phases 3 and 4 are skipped), then emits `processing_completed("appended", content)`. On the main thread the controller saves any pending reader edits, appends the rewritten content to the note body as a new paragraph (`notes.append_to_note()`), and shows a **Dictation Added** notification. The Phase 2 title is discarded; the note keeps its title, type and tags.

---

## Language Control

Phase 2 (rewriting) and Phase 4 (tagging) each receive a field-specific `{language_instruction}` built from `ai.output_language`, asking the model to write `title and content` or `tags` in that language and to translate if necessary. Phase 1 always transcribes in the spoken language, and Phase 3 (classification) omits `{language_instruction}` because `type` values are fixed English keys regardless of language.

---

## Zero Cold-Start Model Preloading

Local LLMs loaded via Ollama can experience a cold-start latency of 2 to 5 seconds when weights need to be transferred into GPU VRAM from system storage.

To completely eliminate this delay when recording finishes, Eloquent Notes starts preloading model weights **in parallel while you are actively speaking**:

1. As soon as recording starts (transition to `RECORDING`), `EloquentApp._start_recording()` launches a background thread running `_preload_model()`.
2. This sends a lightweight request to Ollama's `/api/chat` with an empty message array and a `preload_keep_alive` parameter (default: `"5m"`):
   ```python
   requests.post(
       f"{ollama_url}/api/chat",
       json={
           "model": model,
           "messages": [],
           "keep_alive": keep_alive,
           "options": {"temperature": 0.0, "num_ctx": context_length},
       },
       timeout=timeout,
   )
   ```
3. By the time you click to stop recording, Ollama already has the Gemma 4 model fully loaded in VRAM, allowing Phase 1 execution to begin instantly without cold-start delay.

### Keep-Alive Handover

For a new note, Phases 1, 2 and 3 run with `preload_keep_alive` so the model stays loaded between phases, and Phase 4 (`tag_note()`) runs with `keep_alive` (default `"0"`), so the model is unloaded right after the note is written. On **Add Dictation** (`append=True`), Phase 2 passes `ai.keep_alive` directly since Phases 3 and 4 are skipped. When processing ends before the final phase completes (silence, empty transcription or an error) and the two values differ, a final preload request re-applies `keep_alive` so the model is not left resident for `preload_keep_alive`.

---

## Reasoning Mode Is Disabled

Gemma 4 enables reasoning by default (`thinking: true`, confirmed via `ollama show`). The reasoning tokens it emits are drawn from the same `num_predict` budget as the answer. When that budget is exhausted Ollama returns an **empty** `content` alongside `done_reason: length`, and the model reports that as `"empty": true` — so a correctly transcribed dictation is silently discarded and the user is told "Dictation Empty".

This is not a rare edge case: it is what happens whenever background noise at the microphone degrades the transcript enough to make the model reason at length. Measured against a reference clip ("Why is the sky blue?") with noise added to 5 dB SNR, the default reasoning mode discarded 4 of 5 dictations.

Eloquent Notes therefore sends `"think": false` on every pipeline request (`llm.THINK`). This restores correct transcription of noisy audio and is also substantially faster, since no tokens are spent on reasoning that a transcription task does not benefit from.

Disabling reasoning also improves the three text-only phases: it removes the thinking text that Ollama would otherwise append to the assistant turn on retries, and it leaves more of the token budget for the note itself.

## Structured JSON Validation & Retry Logic

Eloquent Notes requires deterministic structured JSON output from Ollama to ensure safe parsing and file generation.

Each phase requests constrained decoding via Ollama's `format` JSON schema, which makes the model emit valid JSON matching the expected shape. As a safety net (e.g. for Ollama versions that ignore `format`), `_execute_ollama_json_request()` validates every response via `_parse_json_response()` and automatically retries:

```python
def _execute_ollama_json_request(
    ollama_url: str,
    model: str,
    messages: list[dict[str, Any]],
    format_schema: dict[str, Any],
    retry_prompt: str,
    context_length: int | None,
    keep_alive: str,
    max_retries: int,
    timeout: int,
    task_name: str,
) -> dict[str, Any]:
    if max_retries < 0:
        raise ValueError(f"max_retries must be >= 0, got {max_retries}")

    keys = format_schema["required"]
    options: dict[str, Any] = {
        "temperature": 0.0,
        "num_predict": DEFAULT_NUM_PREDICT,
    }
    if context_length is not None:
        options["num_ctx"] = context_length

    conversation = list(messages)
    url = _chat_url(ollama_url)
    attempt = 0

    while True:
        payload: dict[str, Any] = {
            "model": model,
            "messages": conversation,
            "format": format_schema,
            "options": options,
            "keep_alive": keep_alive,
            "stream": False,
            "think": THINK,
        }
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()

        content = None
        try:
            content = response.json()["message"]["content"]
            return _parse_json_response(content, format_schema)
        except (KeyError, TypeError, ValueError):
            if attempt >= max_retries:
                raise
            conversation.append(
                {
                    "role": "assistant",
                    "content": content if content is not None else response.text,
                }
            )
            conversation.append(
                {
                    "role": "user",
                    "content": f"{retry_prompt}\n\nExpected fields: {', '.join(keys)}.",
                }
            )
            attempt += 1
```

### Retry Mechanism Details
1. **Schema-Constrained Output:** Requests include a `format` JSON schema so Ollama constrains sampling to the expected structure.
2. **Schema Verification:** `_parse_json_response()` verifies that the output is a JSON object containing all required keys with matching types and enum values.
3. **Chat Context Appending:** If validation fails, the erroneous assistant message is appended to the message history followed by the contents of `~/.config/eloquent-notes/prompts/retry_prompt.md`.
4. **Retry Loop:** Retries execution up to `max_retries` times (default: 3) before raising an exception.
