---
hide:
  - toc
---

<div class="hero-section">
  <div class="hero-eyebrow">
    <i class="fa-solid fa-microphone-lines" aria-hidden="true"></i><span>Local Voice Dictation &amp; AI Note Pipeline</span>
  </div>
  <h1>Eloquent Notes</h1>
  <p class="hero-subtitle">A lightweight, system-tray-centric background utility for Linux that captures microphone dictation in-memory, structures it through a local three-phase Gemma 4 pipeline via Ollama, and writes enriched Markdown notes directly to your Obsidian vault.</p>
  <div class="hero-badges">
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.8%2B-blue.svg" alt="Python 3.8+"></a>
    <a href="#"><img src="https://img.shields.io/badge/platform-Linux%20POSIX-important.svg" alt="Platform"></a>
    <a href="https://riverbankcomputing.com/software/pyqt/"><img src="https://img.shields.io/badge/GUI-PyQt6-green.svg" alt="PyQt6"></a>
    <a href="https://ollama.ai/"><img src="https://img.shields.io/badge/LLM-Ollama-black.svg" alt="Ollama"></a>
    <a href="https://ollama.com/library/gemma4"><img src="https://img.shields.io/badge/Model-Gemma--4-purple.svg" alt="Gemma 4"></a>
    <a href="https://obsidian.md/"><img src="https://img.shields.io/badge/Vault-Obsidian-7a46ed.svg" alt="Obsidian"></a>
    <a href="https://github.com/arrase/eloquent-notes/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  </div>
  <div class="hero-badges">
    <a href="https://sonarcloud.io/summary/new_code?id=arrase_eloquent-notes"><img src="https://img.shields.io/sonar/quality_gate/arrase_eloquent-notes?server=https%3A%2F%2Fsonarcloud.io&amp;logo=sonarcloud" alt="Quality Gate Status"></a>
    <a href="https://sonarcloud.io/summary/new_code?id=arrase_eloquent-notes"><img src="https://img.shields.io/sonar/coverage/arrase_eloquent-notes?server=https%3A%2F%2Fsonarcloud.io&amp;logo=sonarcloud" alt="Coverage"></a>
    <a href="https://sonarcloud.io/summary/new_code?id=arrase_eloquent-notes"><img src="https://img.shields.io/sonar/bugs/arrase_eloquent-notes?server=https%3A%2F%2Fsonarcloud.io&amp;logo=sonarcloud" alt="Bugs"></a>
    <a href="https://sonarcloud.io/summary/new_code?id=arrase_eloquent-notes"><img src="https://img.shields.io/sonar/vulnerabilities/arrase_eloquent-notes?server=https%3A%2F%2Fsonarcloud.io&amp;logo=sonarcloud" alt="Vulnerabilities"></a>
    <a href="https://sonarcloud.io/summary/new_code?id=arrase_eloquent-notes"><img src="https://img.shields.io/sonar/code_smells/arrase_eloquent-notes?server=https%3A%2F%2Fsonarcloud.io&amp;logo=sonarcloud" alt="Code Smells"></a>
    <a href="https://sonarcloud.io/summary/new_code?id=arrase_eloquent-notes"><img src="https://img.shields.io/sonar/tech_debt/arrase_eloquent-notes?server=https%3A%2F%2Fsonarcloud.io&amp;logo=sonarcloud" alt="Tech Debt"></a>
    <a href="https://sonarcloud.io/summary/new_code?id=arrase_eloquent-notes"><img src="https://img.shields.io/sonar/duplicated_lines_density/arrase_eloquent-notes?server=https%3A%2F%2Fsonarcloud.io&amp;logo=sonarcloud" alt="Duplicated Lines"></a>
    <a href="https://sonarcloud.io/summary/new_code?id=arrase_eloquent-notes"><img src="https://img.shields.io/sonar/security_rating/arrase_eloquent-notes?server=https%3A%2F%2Fsonarcloud.io&amp;logo=sonarcloud" alt="Security Rating"></a>
    <a href="https://sonarcloud.io/summary/new_code?id=arrase_eloquent-notes"><img src="https://img.shields.io/sonar/reliability_rating/arrase_eloquent-notes?server=https%3A%2F%2Fsonarcloud.io&amp;logo=sonarcloud" alt="Reliability Rating"></a>
    <a href="https://sonarcloud.io/summary/new_code?id=arrase_eloquent-notes"><img src="https://img.shields.io/sonar/sqale_rating/arrase_eloquent-notes?server=https%3A%2F%2Fsonarcloud.io&amp;logo=sonarcloud" alt="Maintainability Rating"></a>
  </div>
</div>

<div class="section-header">
  <h2>Key Features</h2>
  <span>System-tray workflow &amp; local LLM enrichment</span>
</div>

<div class="projects-grid">
  <div class="feature-card">
    <i class="fa-solid fa-tray feature-icon" aria-hidden="true"></i>
    <h3>System Tray Centric UX</h3>
    <p>Operates silently in the Linux system tray. Single-click or keybinding toggles recording instantly with visual and acoustic status cues.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-bars-staggered feature-icon" aria-hidden="true"></i>
    <h3>Context Menu Actions</h3>
    <p>Right-click the tray icon to quickly access Start/Stop controls, open the graphical Configuration editor, or reload settings on-the-fly.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-terminal feature-icon" aria-hidden="true"></i>
    <h3>Decoupled CLI</h3>
    <p>Lightweight <code>eloquent-notes toggle</code> command communicates with the running daemon over zero-latency IPC sockets without GUI overhead.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-shield-halved feature-icon" aria-hidden="true"></i>
    <h3>Offline &amp; Private</h3>
    <p>All transcription, rewriting, and metadata extraction happens 100% locally on your device using Ollama and Gemma 4 models.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-palette feature-icon" aria-hidden="true"></i>
    <h3>Dynamic In-Memory Icons</h3>
    <p>State icons (Idle gray microphone, Recording red dot, Processing orange hourglass) are dynamically rendered with Qt <code>QPainter</code> in RAM.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-gem feature-icon" aria-hidden="true"></i>
    <h3>Advanced Obsidian Integration</h3>
    <p>Supports automatic Markdown callouts, vault topic scanning for <code>[[Wikilinks]]</code>, daily journal appending, and PyYAML frontmatter merging.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-sliders feature-icon" aria-hidden="true"></i>
    <h3>Customizable Prompts</h3>
    <p>Tailor system and user Markdown prompts for every stage of the 3-phase LLM pipeline and structured JSON retry logic.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-file-code feature-icon" aria-hidden="true"></i>
    <h3>Custom Note Templates</h3>
    <p>Define custom layouts for standalone notes and daily journals using dynamic placeholders like <code>{title}</code>, <code>{text}</code>, and <code>{tags}</code>.</p>
  </div>
</div>

<div class="section-header">
  <h2>Graphical Configuration Interface</h2>
  <span>Visual settings, prompt &amp; template editor</span>
</div>

Eloquent Notes includes a full-featured PyQt6 GUI for editing your settings, AI endpoints, audio parameters, prompts, and templates visually.

![Configuration GUI](screenshots/configuration.png)

<div class="section-header">
  <h2>Documentation</h2>
  <span>Architecture, pipeline &amp; configuration guides</span>
</div>

<div class="projects-grid">
  <a href="architecture/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-sitemap feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Architecture &amp; Design</h3>
    <p>Explore the PyQt6 event loop, QSystemTrayIcon, QLocalServer IPC, in-memory zero-disk audio capture, and state icon rendering.</p>
  </a>

  <a href="pipeline/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-brain feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Three-Phase AI Pipeline</h3>
    <p>Deep dive into Phase 1 (Transcription), Phase 2 (Rewriting), Phase 3 (Classification), model preloading, and JSON retry validation.</p>
  </a>

  <a href="obsidian/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-book-bookmark feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Obsidian Vault Integration</h3>
    <p>Learn how callout formatting, vault-wide wikilink matching, daily note appending, and YAML frontmatter merging operate.</p>
  </a>

  <a href="configuration/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-gear feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Configuration &amp; Templates</h3>
    <p>Detailed reference for <code>config.yaml</code> settings, prompt customization, and template placeholder definitions.</p>
  </a>

  <a href="usage-shortcuts/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-keyboard feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>System Tray &amp; Shortcuts</h3>
    <p>Guide to desktop environment shortcuts (GNOME, KDE Plasma, i3/Sway) and tray interaction states.</p>
  </a>

  <a href="cli/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-code feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>CLI &amp; Logging</h3>
    <p>Command line reference for <code>eloquent-notes</code> subcommands, autostart configuration, and XDG log file rotation.</p>
  </a>

  <a href="installation/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-download feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Installation &amp; Setup</h3>
    <p>Step-by-step instructions for installing via <code>uv</code>, <code>pipx</code>, or editable development builds along with prerequisites.</p>
  </a>

  <a href="releasing/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-tag feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Release Process</h3>
    <p>Semantic versioning workflow, tag verification tests, and procedure for publishing new releases from <code>pyproject.toml</code>.</p>
  </a>
</div>
