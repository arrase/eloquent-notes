# Three-Phase AI Pipeline

Eloquent Notes utilizes a modular three-phase LLM processing pipeline powered by local models via the Ollama REST API (default model: `gemma4:e4b-it-qat`).

Rather than forcing a single small LLM call to transcribe audio, clean up prose, write a title and classify the note at once, Eloquent Notes splits processing into three specialized sequential phases. The output is one structured Markdown note (see [Notes & Search](notes.md)).

---

## Pipeline Overview

```
                      ┌─────────────────────────────────┐
                      │    In-Memory Audio (WAV bytes)  │
                      └────────────────┬────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 1: Audio Transcription (Multimodal Input)                             │
│ - Inputs: Base64 WAV bytes + System & User Prompts                          │
│ - Tasks: Removes stutters, repetitions, and filler words.                   │
│ - Output JSON: {"transcription": string, "empty": bool}                      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ (Early exit if empty == true)
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
│ - Tasks: Classifies note type and generates tags in the configured          │
│          output_language.                                                   │
│ - Output JSON: {"type": string, "tags": list}                               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
                   notes.create_note → "YYYY-MM-DD HHMMSS Title.md"
```

When the dictation was started with **Add dictation** on an existing note, the pipeline stops after Phase 2 (see [Add Dictation](#add-dictation-phases-1-2-only)).

---

## 1. Phase 1: Audio Transcription

Phase 1 takes the raw WAV audio bytes captured during dictation, base64 encodes them, and sends them directly to the multimodal model endpoint.

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
      "description": "Clean transcription of spoken words, or empty string if audio is empty."
    },
    "empty": {
      "type": "boolean",
      "description": "True if audio contains only silence, background noise, or no spoken words."
    }
  },
  "required": ["transcription", "empty"]
}
```

### Field Order Is Significant
Under constrained decoding Ollama emits properties in the order the schema declares them, so `transcription` is declared **before** `empty` on purpose. With `empty` first, the model must commit to that flag before it has transcribed anything, and it reports `empty: true` even when the transcript it then produces is correct — a note lost despite a perfect transcription. Declaring the transcript first makes the model transcribe and only then judge whether the audio was silent.

### Local Silence Detection

The model cannot be trusted to recognise silence. Asked to label an empty recording it frequently answers `"empty": false` and invents text — in testing, a clip of pure digital silence came back as `empty: false` with a fluent Spanish sentence about time, which the pipeline would then have saved as a note.

Eloquent Notes therefore decides emptiness locally, in `audio.is_silent()`, by comparing the recording's RMS amplitude against a speech threshold of -45 dBFS. The threshold sits far above a microphone's noise floor while leaving ample headroom for quiet dictation. If the recording carries no speech-level energy, `_process_audio()` emits the `empty` signal without contacting the model at all, so an accidental trigger in a quiet room costs nothing and cannot produce a fabricated note. The model's own `empty` flag is retained in the schema and honoured, but treated as advisory.

### Silence Trimming

`AudioRecorder.wav_bytes` additionally trims leading and trailing blocks below the same threshold before encoding, keeping interior pauses intact. This shortens the audio the model must encode, which makes it less likely to fill the gaps with invented speech and reduces the token cost. A recording of 4 s of silence, 1.8 s of dictation and 4 s of silence is sent as 1.8 s.

### Early Exit Safeguard
If Phase 1 returns `"empty": true` or a blank transcription string, processing terminates immediately. The application fires an `"empty"` signal, displays a desktop notification ("Dictation Empty"), resets the tray icon to gray, and saves no file to disk.

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

Phase 3 reads only the rewritten content from Phase 2 and returns the note's type and tags. It has no knowledge of other notes.

### Goals
- **Type Classification:** one of six fixed English keys:
  - `task` → Action items, things to do.
  - `idea` → Proposals, creative thoughts, suggestions.
  - `note` → Information, observations, explanations.
  - `reminder` → Things to remember, deadlines.
  - `question` → Things to investigate or research.
  - `decision` → Choices made, conclusions reached.
- **Tag Generation:** 2 to 5 lowercase, single-word or hyphenated tags in the configured `output_language` (e.g., `["redis", "caching", "performance"]`).

### JSON Format Schema
```json
{
  "type": "object",
  "properties": {
    "type": {
      "type": "string",
      "enum": ["task", "idea", "note", "reminder", "question", "decision"],
      "description": "Classification of the note content."
    },
    "tags": {
      "type": "array",
      "items": { "type": "string" },
      "description": "2 to 5 relevant tags, lowercase, in the requested output language."
    }
  },
  "required": ["type", "tags"]
}
```

---

## Saving the Note

After Phase 3, `notes.create_note()` writes the note into `notes.folder`:

- **Title** and **body** come from Phase 2, **type** from Phase 3.
- **Tags** are normalized with `notes.normalize_tags()`: lowercased, leading `#` stripped, blanks and duplicates removed.
- `created` is the current local time with UTC offset; the file is named `YYYY-MM-DD HHMMSS Title.md` and written atomically.

The worker then emits `processing_completed("success", title)`; the main thread shows a **Note Saved** notification and refreshes the notes window.

---

## Add Dictation (Phases 1-2 Only)

**Add dictation** in the reader starts a recording targeted at the open note. Processing runs Phase 1 and Phase 2 only, then emits `processing_completed("appended", content)`. On the main thread the controller saves any pending reader edits, appends the rewritten content to the note body as a new paragraph (`notes.append_to_note()`), and shows a **Dictation Added** notification. The Phase 2 title is discarded; the note keeps its title, type and tags.

---

## Language Control

Every text phase receives a `{language_instruction}` built from `ai.output_language`, asking the model to write the title, content and tags in that language and to translate if necessary. Phase 1 always transcribes in the spoken language. The `type` values stay fixed English keys regardless of language.

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

Phases 1 and 2 run with `preload_keep_alive` so the model stays loaded between phases. Phase 3 runs with `keep_alive` (default `"0"`), so the model is unloaded right after a new note is written. When processing ends before Phase 3 (silence, empty transcription, add-dictation or an error) and the two values differ, a final preload request re-applies `keep_alive` so the model is not left resident for `preload_keep_alive`.

---

## Reasoning Mode Is Disabled

Gemma 4 enables reasoning by default (`thinking: true`, confirmed via `ollama show`). The reasoning tokens it emits are drawn from the same `num_predict` budget as the answer. When that budget is exhausted Ollama returns an **empty** `content` alongside `done_reason: length`, and the model reports that as `"empty": true` — so a correctly transcribed dictation is silently discarded and the user is told "Dictation Empty".

This is not a rare edge case: it is what happens whenever background noise at the microphone degrades the transcript enough to make the model reason at length. Measured against a reference clip ("Why is the sky blue?") with noise added to 5 dB SNR, the default reasoning mode discarded 4 of 5 dictations.

Eloquent Notes therefore sends `"think": false` on every pipeline request (`llm.THINK`). This restores correct transcription of noisy audio and is also substantially faster, since no tokens are spent on reasoning that a transcription task does not benefit from.

Disabling reasoning also improves the two text-only phases: it removes the thinking text that Ollama would otherwise append to the assistant turn on retries, and it leaves more of the token budget for the note itself.

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
            conversation.append({
                "role": "assistant",
                "content": content if content is not None else response.text,
            })
            conversation.append({
                "role": "user",
                "content": f"{retry_prompt}\n\nExpected fields: {', '.join(keys)}.",
            })
            attempt += 1
```

### Retry Mechanism Details
1. **Schema-Constrained Output:** Requests include a `format` JSON schema so Ollama constrains sampling to the expected structure.
2. **Schema Verification:** `_parse_json_response()` verifies that the output is a JSON object containing all required keys with matching types and enum values.
3. **Chat Context Appending:** If validation fails, the erroneous assistant message is appended to the message history followed by the contents of `~/.config/eloquent-notes/prompts/retry_prompt.md`.
4. **Retry Loop:** Retries execution up to `max_retries` times (default: 3) before raising an exception.
