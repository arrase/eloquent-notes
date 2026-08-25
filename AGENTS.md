# AI Agent Guidelines

This repository contains documentation under `docs/` to help AI coding agents understand the system architecture, design patterns, and module structure:

- **System Blueprint**: Refer to docs/architecture.md for a high-level system overview, module relationships, and boundary definitions.
- **Processing Pipeline**: Refer to docs/pipeline.md for details on the three-phase Ollama pipeline and retry logic.
- **Configuration & Usage**: Refer to docs/configuration.md and README.md for settings, prompts, and templates.

## Code Principles

- Keep it simple: no speculative fallbacks or dead defensive code.
- Use standard libraries and declared dependencies; do not re-implement what they provide.
- Fail fast on invalid configuration; surface actionable errors to the user via notifications.
- All application state changes happen on the Qt main thread. Only model preloading and audio processing run on background threads and report back via signals.

Before making changes, analyze these files to align with existing design choices and code structures.
