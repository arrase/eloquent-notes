# Three-Phase AI Pipeline

Eloquent Notes utilizes a modular three-phase LLM processing pipeline powered by local models via the Ollama REST API (default model: `gemma4:12b-it-qat`).

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
│ - Output JSON: {"empty": bool, "transcription": string}                     │
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
    "empty": {
      "type": "boolean",
      "description": "True if audio contains only silence, background noise, or no spoken words."
    },
    "transcription": {
      "type": "string",
      "description": "Clean transcription of spoken words, or empty string if audio is empty."
    }
  },
  "required": ["empty", "transcription"]
}
```

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

## Structured JSON Validation & Retry Logic

Eloquent Notes requires deterministic structured JSON output from Ollama to ensure safe parsing and file generation.

Because LLMs can occasionally wrap output in Markdown code blocks (e.g., ` ```json ... ``` `) or omit required keys, `_execute_ollama_json_request()` implements robust validation and automatic retry attempts:

```python
def _execute_ollama_json_request(...):
    for attempt in range(max_retries + 1):
        response = requests.post(f"{ollama_url}/api/chat", json=payload, timeout=timeout)
        content = _strip_code_fences(response.json()["message"]["content"])

        try:
            result = json.loads(content)
            if not isinstance(result, dict) or not all(k in result for k in required_keys):
                raise ValueError(f"Missing required keys: {required_keys}")
            return result
        except (json.JSONDecodeError, TypeError, ValueError) as json_err:
            if attempt >= max_retries:
                raise json_err
            
            # Append failed response and custom retry prompt to history
            full_retry = f"{retry_prompt}\n\nExpected fields: {', '.join(required_keys)}."
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": full_retry})
```

### Retry Mechanism Details
1. **Code Fence Stripping:** `_strip_code_fences()` uses regular expressions to strip backticks (` ```json ` ... ` ``` `) before passing text to `json.loads()`.
2. **Schema Verification:** Ensures the output is a dictionary containing all mandatory keys for that phase.
3. **Chat Context Appending:** If validation fails, the erroneous assistant message is appended to the message history followed by the contents of `~/.config/eloquent-notes/prompts/retry_prompt.md`.
4. **Retry Loop:** Retries execution up to `max_retries` times (default: 3) before raising an exception.
