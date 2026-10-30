# AI Agent Guidelines

Eloquent Notes has one focus: **voice dictations → structured, well-ordered notes**, captured easily and efficiently. Resist feature creep: no knowledge-graph, RAG, copilot or database features.

This repository contains documentation under `gh-pages/` to help AI coding agents understand the system architecture, design patterns, and module structure:

- **System Blueprint**: Refer to gh-pages/architecture.md for modules, boundaries, IPC, the recording lifecycle and the threading model.
- **Processing Pipeline**: Refer to gh-pages/pipeline.md for the four-phase Ollama pipeline, add-dictation flow and retry logic.
- **Notes & Search**: Refer to gh-pages/notes.md for the note file format, the notes window and semantic search.
- **Configuration**: Refer to gh-pages/configuration.md for settings and prompts.
- **Usage & CLI**: Refer to gh-pages/usage-shortcuts.md and gh-pages/cli.md for tray, window and command-line behavior.
- **Releasing**: Refer to gh-pages/releasing.md before cutting a version or tag.

## Code Principles

- Keep it simple: no speculative fallbacks or dead defensive code.
- Use standard libraries and declared dependencies; do not re-implement what they provide.
- Fail fast on invalid configuration; surface actionable errors to the user via notifications.
- All application and UI state changes happen on the Qt main thread. Only model preloading, audio processing and semantic search run on background threads and report back via signals.

Before making changes, analyze these files to align with existing design choices and code structures.
