# Three-Phase AI Pipeline

Eloquent Notes utilizes a modular three-phase LLM processing pipeline powered by local models via the Ollama REST API (default model: `gemma4:e4b-it-qat`).

Rather than attempting to force a single small LLM call to simultaneously transcribe multimodal audio, clean up prose, generate titles, analyze Obsidian vault context, and classify metadata, Eloquent Notes breaks down note processing into three specialized sequential phases.

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
│ Phase 3: Note Classification & Context Analysis                             │
│ - Inputs: Transcription + Vault Topic Context + System & User Prompts       │
│ - Tasks: Classifies note type, extracts wikilinks, generates English tags. │
│ - Output JSON: {"type": string, "wikilinks": list, "tags": list}            │
└─────────────────────────────────────────────────────────────────────────────┘
```

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

Phase 2 converts the raw transcribed text from Phase 1 into structured, direct, first-person prose suitable for personal knowledge management.

### Goals
- Rephrase awkward oral phrasing into polished written Markdown prose.
- Preserve the user's authentic first-person voice and core meaning without adding unsolicited commentary or external assumptions.
- Synthesize a concise title (maximum 8 words) summarizing the note's subject matter.

### JSON Format Schema
```json
{
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "description": "Concise title (max 8 words) capturing the main topic."
    },
    "content": {
      "type": "string",
      "description": "Clean, direct note prose with basic markdown formatting."
    }
  },
  "required": ["title", "content"]
}
```

---

## 3. Phase 3: Classification & Wikilink Extraction

Phase 3 analyzes the dictation alongside existing vault topics to extract metadata and categorize the note.

### Goals
- **Vault Topic Matching:** Scans your Obsidian vault for existing note names to construct a context list. If a spoken phrase matches an existing note topic, it is flagged as a candidate `[[Wikilink]]`.
- **Type Classification:** Categorizes the entry into one of six core note types:
  - `task` → Action items, to-dos, or actionable chores.
  - `idea` → Insights, creative concepts, or brain dumps.
  - `reminder` → Time-sensitive alerts or items to keep in mind.
  - `question` → Unresolved inquiries or topics requiring research.
  - `decision` → Architectural decisions or agreed outcomes.
  - `note` → Standard informational observations or general prose.
- **Tag Generation:** Generates 2 to 5 relevant lowercase English tags for vault categorization (e.g., `["python", "architecture", "pyqt6"]`).

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
    "wikilinks": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Key concepts, tools, or proper nouns that deserve linked notes."
    },
    "tags": {
      "type": "array",
      "items": { "type": "string" },
      "description": "2 to 5 relevant tags, lowercase, in English."
    }
  },
  "required": ["type", "wikilinks", "tags"]
}
```

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

---

## Reasoning Mode Is Disabled

Gemma 4 enables reasoning by default (`thinking: true`, confirmed via `ollama show`). The reasoning tokens it emits are drawn from the same `num_predict` budget as the answer. When that budget is exhausted Ollama returns an **empty** `content` alongside `done_reason: length`, and the model reports that as `"empty": true` — so a correctly transcribed dictation is silently discarded and the user is told "Dictation Empty".

This is not a rare edge case: it is what happens whenever background noise at the microphone degrades the transcript enough to make the model reason at length. Measured against a reference clip ("Why is the sky blue?") with noise added to 5 dB SNR, the default reasoning mode discarded 4 of 5 dictations.

Eloquent Notes therefore sends `"think": false` on every pipeline request (`llm.THINK`). This restores correct transcription of noisy audio and is also substantially faster, since no tokens are spent on reasoning that a transcription task does not benefit from.

Disabling reasoning also improves the two text-only phases: it removes the thinking text that Ollama would otherwise append to the assistant turn on retries, and it leaves more of the token budget for the note itself.

## Structured JSON Validation & Retry Logic

Eloquent Notes requires deterministic structured JSON output from Ollama to ensure safe parsing and file generation.

Each phase requests constrained decoding via Ollama's `format` JSON schema, which makes the model emit valid JSON matching the expected shape. As a safety net (e.g. for Ollama versions that ignore `format`), `_execute_ollama_json_request()` validates every response and automatically retries:

```python
def _execute_ollama_json_request(...):
    conversation = list(messages)

    for attempt in range(max_retries + 1):
        response = requests.post(f"{ollama_url}/api/chat", json=payload, timeout=timeout)
        content = response.json()["message"]["content"]

        try:
            result = json.loads(content)
            if not isinstance(result, dict) or not all(k in result for k in required_keys):
                raise ValueError(f"missing required keys: {required_keys}")
            return result
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as err:
            if attempt >= max_retries:
                raise

            # Append failed response and custom retry prompt to history
            full_retry = f"{retry_prompt}\n\nExpected fields: {', '.join(required_keys)}."
            conversation.append({"role": "assistant", "content": content})
            conversation.append({"role": "user", "content": full_retry})
```

### Retry Mechanism Details
1. **Schema-Constrained Output:** Requests include a `format` JSON schema so Ollama constrains sampling to the expected structure.
2. **Schema Verification:** Ensures the output is a dictionary containing all mandatory keys for that phase.
3. **Chat Context Appending:** If validation fails, the erroneous assistant message is appended to the message history followed by the contents of `~/.config/eloquent-notes/prompts/retry_prompt.md`.
4. **Retry Loop:** Retries execution up to `max_retries` times (default: 3) before raising an exception.
