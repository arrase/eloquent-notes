# Eloquent Notes

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Linux%20POSIX-important.svg)](#)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://riverbankcomputing.com/software/pyqt/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-black.svg)](https://ollama.ai/)
[![Gemma 4](https://img.shields.io/badge/Model-Gemma--4-purple.svg)](https://ollama.com/library/gemma4)
[![Obsidian](https://img.shields.io/badge/Vault-Obsidian-7a46ed.svg)](https://obsidian.md/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/arrase/eloquent-notes/blob/main/LICENSE)

**Local Voice Dictation & AI Note Pipeline for Obsidian**

Eloquent Notes is a lightweight, system-tray-centric background utility for Linux inspired by Google Eloquent. It captures audio directly from your microphone in-memory, transcribes and structures your dictation using a local three-phase Gemma 4 model pipeline via Ollama, and automatically enriches and writes the formatted notes directly to your Obsidian vault.

---

## Key Features

<div class="projects-grid">
  <div class="feature-card">
    <i class="fa-solid fa-tray feature-icon"></i>
    <h3>System Tray Centric UX</h3>
    <p>Operates silently in the Linux system tray. Single-click or keybinding toggles recording instantly with visual and acoustic status cues.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-bars-staggered feature-icon"></i>
    <h3>Context Menu Actions</h3>
    <p>Right-click the tray icon to quickly access Start/Stop controls, open the graphical Configuration editor, or reload settings on-the-fly.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-terminal feature-icon"></i>
    <h3>Decoupled CLI</h3>
    <p>Lightweight <code>eloquent-notes toggle</code> command communicates with the running daemon over zero-latency IPC sockets without GUI overhead.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-shield-halved feature-icon"></i>
    <h3>Offline & Private</h3>
    <p>All transcription, rewriting, and metadata extraction happens 100% locally on your device using Ollama and Gemma 4 models.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-palette feature-icon"></i>
    <h3>Dynamic In-Memory Icons</h3>
    <p>State icons (Idle gray microphone, Recording red dot, Processing orange hourglass) are dynamically drawn using Pillow in RAM.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-gem feature-icon"></i>
    <h3>Advanced Obsidian Integration</h3>
    <p>Supports automatic Markdown callouts, vault topic scanning for <code>[[Wikilinks]]</code>, daily journal appending, and PyYAML frontmatter merging.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-sliders feature-icon"></i>
    <h3>Customizable Prompts</h3>
    <p>Tailor system and user Markdown prompts for every stage of the 3-phase LLM pipeline and structured JSON retry logic.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-file-code feature-icon"></i>
    <h3>Custom Note Templates</h3>
    <p>Define custom layouts for standalone notes and daily journals using dynamic placeholders like <code>{title}</code>, <code>{text}</code>, and <code>{tags}</code>.</p>
  </div>
</div>

---

## Graphical Configuration Interface

Eloquent Notes includes a full-featured PyQt6 GUI for editing your settings, AI endpoints, audio parameters, prompts, and templates visually.

![Configuration GUI](screenshots/configuration.png)

---

## Documentation Overview

<div class="projects-grid">
  <a href="architecture.md" class="feature-card">
    <i class="fa-solid fa-sitemap feature-icon"></i>
    <h3>Architecture & Design</h3>
    <p>Explore the PyQt6 event loop, QSystemTrayIcon, QLocalServer IPC, in-memory zero-disk audio capture, and state icon rendering.</p>
  </a>

  <a href="pipeline.md" class="feature-card">
    <i class="fa-solid fa-brain feature-icon"></i>
    <h3>Three-Phase AI Pipeline</h3>
    <p>Deep dive into Phase 1 (Transcription), Phase 2 (Rewriting), Phase 3 (Classification), model preloading, and JSON retry validation.</p>
  </a>

  <a href="obsidian.md" class="feature-card">
    <i class="fa-solid fa-book-bookmark feature-icon"></i>
    <h3>Obsidian Vault Integration</h3>
    <p>Learn how callout formatting, vault-wide wikilink matching, daily note appending, and YAML frontmatter merging operate.</p>
  </a>

  <a href="configuration.md" class="feature-card">
    <i class="fa-solid fa-gear feature-icon"></i>
    <h3>Configuration & Templates</h3>
    <p>Detailed reference for <code>config.yaml</code> settings, prompt customization, and template placeholder definitions.</p>
  </a>

  <a href="usage-shortcuts.md" class="feature-card">
    <i class="fa-solid fa-keyboard feature-icon"></i>
    <h3>System Tray & Shortcuts</h3>
    <p>Guide to desktop environment shortcuts (GNOME, KDE Plasma, i3/Sway) and tray interaction states.</p>
  </a>

  <a href="cli.md" class="feature-card">
    <i class="fa-solid fa-code feature-icon"></i>
    <h3>CLI & Logging</h3>
    <p>Command line reference for <code>eloquent-notes</code> subcommands, autostart configuration, and XDG log file rotation.</p>
  </a>

  <a href="installation.md" class="feature-card">
    <i class="fa-solid fa-download feature-icon"></i>
    <h3>Installation & Setup</h3>
    <p>Step-by-step instructions for installing via <code>uv</code>, <code>pipx</code>, or editable development builds along with prerequisites.</p>
  </a>
</div>
