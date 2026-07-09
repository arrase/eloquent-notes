```markdown
# `eloquent_notes/templates` — Template Registry

## Module Responsibility & Data Flow

The `templates` module maintains a static collection of Markdown/YAML frontmatter templates consumed by the note-generation engine at render time. Each template defines a document schema via YAML metadata followed by interpolation placeholders delimited by `{...}`. At runtime, the rendering pipeline substitutes each placeholder with the corresponding context value supplied by the originating service (e.g., dictation client, CLI flag, or REST payload). Templates are not compiled; they are loaded as-is and interpolated on demand.

**Data flow:**
1. Renderer resolves `template_name` from user input or default configuration.
2. Template file is read from this module's filesystem directory.
3. Context map `{title, text, date, time, tags}` is constructed by the upstream caller.
4. String interpolation substitutes all `{...}` placeholders in a single pass.
5. Resulting Markdown document is returned to the caller for persistence or streaming.

Templates are intentionally unexported and stateless—no runtime functions, classes, or interfaces exist within any of the three files. They serve as data-only artifacts consumed by the rendering layer.

---

## `daily_append.md` — Append-to-Daily Template

**File:** `eloquent_notes/templates/daily_append.md`

Used when a new daily note is being appended to an existing day's entry rather than creating a fresh record. The template omits frontmatter date/time metadata, relying on the caller to inject those values via context substitution only if needed by downstream consumers.

**Placeholder contract:**

| Placeholder | Type     | Interpolation Source                          |
|-------------|----------|-----------------------------------------------|
| `{time}`    | string   | Current wall-clock time at render invocation  |
| `{title}`   | string   | Note title supplied by the caller             |
| `{text}`    | string   | Main body content to be appended              |

**Usage pattern:** The rendering engine binds `daily_append.md` when the operation flag is set to *append*. The resulting document merges with any prior daily entry stored under the same date key, producing a single consolidated note per day.

---

## `daily_new.md` — New Daily Dictation Template

**File:** `eloquent_notes/templates/daily_new.md`

Full-featured template for initializing a new daily dictation note complete with YAML frontmatter metadata and structured body sections. This is the canonical entry point when starting a fresh day's recording session.

**Placeholder contract:**

| Placeholder | Type     | Interpolation Source                          |
|-------------|----------|-----------------------------------------------|
| `{tags}`    | string   | Comma-separated tag list for categorization   |
| `{date}`    | string   | ISO-8601 formatted date of the new entry      |
| `{time}`    | string   | Render-time wall-clock timestamp              |
| `{title}`   | string   | Note title from caller context                |
| `{text}`    | string   | Dictation body content to be recorded         |

**Usage pattern:** The renderer loads `daily_new.md` when the operation flag is set to *new*. All five placeholders are substituted in a single pass, producing a self-contained Markdown document with frontmatter headers and body sections ready for immediate persistence.

---

## `standalone.md` — Standalone Document Template

**File:** `eloquent_notes/templates/standalone.md`

Template for generating independent note documents that do not participate in the daily-entry lifecycle. Suitable for ad-hoc notes, reminders, or reference entries detached from any date-based aggregation scheme.

**Placeholder contract:**

| Placeholder | Type     | Interpolation Source                          |
|-------------|----------|-----------------------------------------------|
| `{title}`   | string   | Note title supplied by the caller             |
| `{text}`    | string   | Full document body content                   |
| `{date}`    | string   | Render-time date (optional, may remain empty) |
| `{time}`    | string   | Render-time timestamp (optional, may remain empty) |

**Usage pattern:** The rendering engine binds `standalone.md` when the operation flag is set to *standalone*. Only title and text are required; `date` and `time` may be left as empty strings if the caller does not supply them. The resulting document carries no frontmatter constraints beyond those defined by the template's YAML header.

---

## Rendering Engine Integration

All three templates share an identical interpolation pipeline:
1. Filesystem loader resolves the requested template path within this module's directory.
2. Template content is read as a raw string without compilation or caching.
3. Context map is built from caller-supplied values; missing keys default to empty strings unless overridden by configuration.
4. String replacement iterates over all `{...}` placeholders in document order, substituting each with its corresponding context value.
5. Rendered Markdown is returned to the caller for downstream persistence (local disk, remote API, or internal store).

No runtime state, functions, classes, interfaces, or data structures are exported from any of these files. The module operates entirely as a template data registry consumed by the upstream rendering layer.