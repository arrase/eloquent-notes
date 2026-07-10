# eloquent_notes/templates — Architecture Documentation

## Module Overview

The `eloquent_notes/templates` module is a collection of Markdown templates designed for structured note capture across multiple use cases: daily journaling, dictation sessions, and standalone entries. The module contains no executable code, no mutable state, and no error handling paths. It exists purely as a format contract consumed by external rendering engines (Go `text/template`, Jinja2, or equivalent placeholder substitution).

All templates follow a consistent pattern: YAML frontmatter for metadata (where applicable), followed by interpolated body content using named placeholders. The module's data flow is entirely downstream-dependent — behavior is defined exclusively by whichever runtime reads and substitutes into the templates.

---

## Template Inventory

### daily_append.md — Daily Journal Appender

**Responsibility:** Generate individual daily journal entries where each entry is stored as an independent Markdown document. New entries accumulate over time rather than being overwritten (append pattern).

**Data Model:**
| Placeholder | Description |
|---|---|
| `{time}` | Timestamp when the note was created |
| `{title}` | Human-readable label for the entry |
| `{text}` | Body content of the note |

**Template Shape:**

```markdown
## {time} — {title}
{text}
```

**Algorithmic Flow:**
1. User creates a new daily note → fresh Markdown file generated using this template
2. System captures three values: timestamp, title, body text
3. Formatted content written to disk as an independent document
4. Storage grows with each entry (append pattern)

---

### daily_new.md — Dictation Session Tracker

**Responsibility:** Capture dictation practice sessions organized by date and time periods for language learners. Supports multiple practice sessions per day through time-period segmentation.

**Data Model:**
| Placeholder | Description |
|---|---|
| `{tags}` | List of tags applied to the note (defaults to `dictation`) |
| `{date}` | Date of the dictation session |
| `{time}` | Time slot label for the entry |
| `{title}` | Title/headline of the entry |
| `{text}` | Body text / content of the dictation |

**Frontmatter:**

```yaml
tags: [dictation]
date: {date}
```

**Algorithmic Flow:**
1. Session initiation → user selects a date and assigns entries to specific time periods during that day
2. Entry capture → for each period: record `{time}` label, assign descriptive `{title}`, then capture raw `{text}` content
3. Daily compilation → all period-level entries aggregated under `# Dictations of {date}` heading and rendered sequentially

**Business Rule:** A dictation entry is scoped to a single day; cross-day organization relies on date navigation rather than temporal reordering within the file.

---

### standalone.md — Standalone Note Template

**Responsibility:** Generate structured, timestamped notes with metadata frontmatter and body content for general use cases outside daily or dictation workflows.

**Data Model:**
| Placeholder | Description |
|---|---|
| `{tags}` | Array of tag strings (YAML list) |
| `{date}` | Date string |
| `{time}` | Time string |
| `{title}` | Markdown heading level 1 |
| `{text}` | Main body content (paragraph) |

**Algorithmic Flow:**
1. Generate YAML frontmatter emitting `tags`, `date`, and `time` as key-value pairs
2. Render markdown body outputting a title heading followed by text content

---

## Cross-Template Patterns

All three templates share structural characteristics:

| Characteristic | Observation |
|---|---|
| **State** | None — no global variables, struct fields, or mutable state defined in any file |
| **Concurrency** | None — no locks, channels, synchronization primitives present |
| **I/O** | None — no disk writes, network calls, database queries, subprocess invocations |
| **Error Handling** | None — no try/except blocks, sentinel values, panic handling, logging, or fallback logic |
| **Return Values** | N/A across all files — templates are passive definitions consumed externally |

All three communicate only through placeholder substitution. The placeholders (`{time}`, `{title}`, `{text}`, `{tags}`, `{date}`) are bare strings awaiting resolution by an external rendering engine. If a template engine fails to resolve any placeholder, this file contains no mechanism to catch or report the failure.