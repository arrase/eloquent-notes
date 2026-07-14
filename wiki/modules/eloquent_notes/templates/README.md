# Module: `eloquent_notes/templates`

## Overview

The `eloquent_notes/templates` module provides static Markdown template definitions that encode output schemas for downstream note-generation systems. Each file is a non-executable, placeholder-driven artifact consumed by an external renderer at parse time. No runtime logic, error handling, or mutable state exists within any of the templates; all side-effect-bearing execution occurs outside this package's scope.

## Data Flow

1. **Template Selection** — The rendering engine selects a template file based on note type (append-only daily entry, new session with frontmatter tags, standalone document).
2. **Placeholder Resolution** — At render time, the engine substitutes `{time}`, `{date}`, `{title}`, `{text}`, and `{tags}` placeholders with concrete values supplied by the application layer.
3. **Output Emission** — The rendered Markdown is emitted to disk or forwarded via an I/O channel (not implemented within this module).

## Template Definitions

### `daily_append.md`

Encodes a minimal daily append entry schema. Output structure:

```markdown
## {time} — {title}
{text}
```

- `{time}`: ISO-formatted date/time string injected at runtime.
- `{title}`: Descriptive title for the day's focus.
- `{text}`: Free-form body content (thoughts, tasks, reflections).

**Invariant:** Every entry must contain exactly three fields — time reference, title, and text body. Entries are ordered chronologically per the `{time}` convention. The structure enforces separation between metadata (`{time}`) and content (`{title}` + `{text}`).

### `daily_new.md`

Encodes a daily dictation session schema with YAML frontmatter. Placeholder set: `{date}`, `{tags}`, `{time}`, `{title}`, `{text}`.

- **Frontmatter Block:** Declares tag support and timestamp placeholders (`{date}`, `{time}`).
- **Body Structure:** Timestamp, descriptive title, body text organized under the same markdown heading convention as `daily_append.md`.
- **Tag Attachment:** Classification tags are attached to each entry for grouping/filtering operations.

### `standalone.md`

Encodes a self-contained note document schema. Placeholder set: `{tags}`, `{date}`, `{time}`, `{title}`, `{text}`.

- **Frontmatter Block:** YAML header declares tag and timestamp placeholders (`{date}`, `{time}`).
- **Title Slot:** `{title}` placeholder resolves during rendering into the document heading.
- **Content Area:** `{text}` placeholder reserves the main body field for free-form text input.
- **Render Output:** Metadata and content are combined into a final Markdown layout.

## Structural Comparison

| Template | Placeholder Set | Frontmatter | Body Format | Tags |
|----------|-----------------|-------------|-------------|------|
| `daily_append.md` | `{time}`, `{title}`, `{text}` | None | Markdown heading + body | N/A |
| `daily_new.md` | `{date}`, `{tags}`, `{time}`, `{title}`, `{text}` | YAML block | Markdown heading + body | Yes |
| `standalone.md` | `{tags}`, `{date}`, `{time}`, `{title}`, `{text}` | YAML block | Markdown heading + body | Yes |

## State and Concurrency Characteristics

- **No mutable state** across any template file. All placeholders are resolved externally.
- **No concurrency primitives.** Templates do not participate in locking, signaling, or coordination.

## Error Handling and Side Effects

- **Zero external I/O paths.** No network calls, disk operations, database queries, or API interactions are present.
- **No error propagation logic.** No exception handlers, return codes, panic paths, or conditional fallbacks exist within any template.
- Undefined placeholder values would be surfaced by the downstream renderer; this module does not validate or handle such conditions.