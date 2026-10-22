# Notes & Search

Every dictation becomes one Markdown file. The notes window is a thin view over that folder: it lists, filters, searches and edits the files, and nothing else is stored besides an embedding cache that can be deleted at any time.

---

## Note Files

### Folder

Notes are written to `notes.folder` (default `~/Documents/Eloquent Notes`, configurable in the **Notes** tab). The folder is created on the first save. Only `*.md` files directly inside it are read.

### File Name

```
YYYY-MM-DD HHMMSS Title.md
```

For example `2026-10-19 094217 Redis cache for Postgres.md`. The timestamp is the creation time, so names are unique and sort chronologically. Characters that are unsafe in file names or Markdown links (`\ / : * ? " < > | # ^ [ ]`) are removed and the title part is capped at 80 characters.

Editing a title in the app **never renames the file**; the frontmatter `title` is the source of truth.

### Format

```markdown
---
title: Redis cache for Postgres
created: '2026-10-19T09:42:17+02:00'
type: idea
tags:
- redis
- caching
- performance
---
Consider using Redis as a caching layer to avoid hitting Postgres directly on slow queries.
```

| Field | Description |
| :--- | :--- |
| `title` | Title written in Phase 2 (rewriting). Editable. |
| `created` | ISO-8601 timestamp with UTC offset, second precision. |
| `type` | One of `note`, `task`, `idea`, `reminder`, `question`, `decision`. Editable. |
| `tags` | Lowercase tags without `#`, de-duplicated. Editable. |
| body | The rewritten prose. Additional dictations are appended as new paragraphs. |

Files are written atomically (temporary file + rename).

### Foreign Files Are Ignored

A file is loaded only if it starts with a YAML frontmatter block containing `title`, `created` and a known `type`. Anything else is skipped with a warning in the log. This makes it safe to point the folder inside an Obsidian vault or any other Markdown collection: Eloquent Notes only sees its own notes, and other tools see plain Markdown with standard frontmatter.

Notes edited by other programs are picked up the next time the window refreshes (opening it, saving, deleting, or after a new note).

---

## Notes Window

Open the window with a middle click on the tray icon, **Open Notes** in the tray menu, clicking a notification, `eloquent-notes open`, or running `eloquent-notes` while the daemon is already running. Closing the window keeps the daemon running in the tray.

The window follows the desktop's light/dark palette; dates are shown in English.

### Timeline

- Notes are listed newest first, grouped under day headings (**Today**, **Yesterday**, then e.g. **Monday, 19 October**; the year is added for previous years) and arranged in a multi-column grid (`notes.columns`, default `2`).
- Each card shows the time, the type, the title, a preview of the body and the tags.
- **Type chips** (All, Notes, Tasks, Ideas, Reminders, Questions, Decisions) and the **tag selector** filter the list. Clicking a `#tag` on a card selects that tag.
- The round **record button** at the bottom starts and stops a new dictation; the text below it shows the current state.
- **Settings** opens the configuration dialog.

### Reader & Editing

Click a card to open it in the reader:

- **Title**, **type**, **tags** (comma separated) and **body** are editable.
- Changes are saved when you leave the reader (**← Back** or <kbd>Esc</kbd>), open another note, start a dictation, copy, or close the window. Unchanged notes are not rewritten.
- **Copy** puts the note on the clipboard as Markdown: `# Title`, a blank line, then the body.
- **Delete** asks for confirmation and moves the file to the system trash.

### Add Dictation

**Add dictation** records a new dictation for the open note. It runs only Phase 1 (transcription) and Phase 2 (rewriting); the rewritten content is appended to the body as a new paragraph. The note keeps its title, type and tags. Pending edits in the reader are saved first, and the reader refreshes when the text arrives.

---

## Semantic Search

Type a query in the search box and press <kbd>Enter</kbd>. Results are ordered by similarity and can still be narrowed with the type and tag filters. Clearing the box returns to the timeline.

### How It Works

Search runs on a background thread and uses Ollama's `/api/embed` endpoint with `search.embedding_model` (default `embeddinggemma-2:latest`):

1. **Lazy indexing:** there is no indexing step. At query time every note is checked against the cache and only new or changed notes are embedded.
2. **Task prompts:** EmbeddingGemma expects task-specific prefixes. Notes are embedded as `title: {title} | text: {body}` and queries as `task: search result | query: {query}`.
3. **Ranking:** vectors are normalized and scored by cosine similarity. A note is shown if its score is at least

    ```
    cutoff = max(min_similarity, best_score - 0.05)
    ```

    EmbeddingGemma similarities cluster in a narrow band (roughly 0.5–0.75), so a fixed threshold alone either floods the results or drops good matches; results must also be close to the best match. `min_similarity` defaults to `0.6`.

### Embedding Cache

Vectors are cached in:

```
$XDG_CACHE_HOME/eloquent-notes/embeddings.npz   # default ~/.cache/eloquent-notes/embeddings.npz
```

Entries are keyed by file name and `sha256(embedding model + document text)`. Editing a note (in the app or elsewhere) or switching the embedding model therefore triggers re-embedding on the next search, and entries of deleted notes are dropped. Deleting the file is always safe; it is rebuilt on the next search.

`search.keep_alive` (default `5m`) keeps the embedding model loaded between consecutive searches.
