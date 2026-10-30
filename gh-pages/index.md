---
hide:
  - toc
---

<div class="hero-section">
  <div class="hero-eyebrow">
    <i class="fa-solid fa-microphone-lines" aria-hidden="true"></i><span>Voice Dictations to Structured Notes</span>
  </div>
  <h1>Eloquent Notes</h1>
  <p class="hero-subtitle">A Linux system tray app that turns voice dictations into well-structured, well-ordered Markdown notes with a local four-phase Gemma 4 pipeline via Ollama, and lets you browse, edit and search them by meaning.</p>
  <div class="hero-badges">
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"></a>
    <a href="#"><img src="https://img.shields.io/badge/platform-Linux%20POSIX-important.svg" alt="Platform"></a>
    <a href="https://riverbankcomputing.com/software/pyqt/"><img src="https://img.shields.io/badge/GUI-PyQt6-green.svg" alt="PyQt6"></a>
    <a href="https://ollama.ai/"><img src="https://img.shields.io/badge/LLM-Ollama-black.svg" alt="Ollama"></a>
    <a href="https://ollama.com/library/gemma4"><img src="https://img.shields.io/badge/Model-Gemma--4-purple.svg" alt="Gemma 4"></a>
    <a href="https://github.com/arrase/eloquent-notes/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  </div>
  <div class="hero-badges">
    <a href="https://sonarcloud.io/summary/overall?id=arrase_eloquent-notes"><img src="https://sonarcloud.io/api/project_badges/measure?project=arrase_eloquent-notes&amp;metric=alert_status" alt="Quality Gate Status"></a>
    <a href="https://sonarcloud.io/summary/overall?id=arrase_eloquent-notes"><img src="https://sonarcloud.io/api/project_badges/measure?project=arrase_eloquent-notes&amp;metric=coverage" alt="Coverage"></a>
    <a href="https://sonarcloud.io/summary/overall?id=arrase_eloquent-notes"><img src="https://sonarcloud.io/api/project_badges/measure?project=arrase_eloquent-notes&amp;metric=bugs" alt="Bugs"></a>
    <a href="https://sonarcloud.io/summary/overall?id=arrase_eloquent-notes"><img src="https://sonarcloud.io/api/project_badges/measure?project=arrase_eloquent-notes&amp;metric=vulnerabilities" alt="Vulnerabilities"></a>
    <a href="https://sonarcloud.io/summary/overall?id=arrase_eloquent-notes"><img src="https://sonarcloud.io/api/project_badges/measure?project=arrase_eloquent-notes&amp;metric=code_smells" alt="Code Smells"></a>
    <a href="https://sonarcloud.io/summary/overall?id=arrase_eloquent-notes"><img src="https://sonarcloud.io/api/project_badges/measure?project=arrase_eloquent-notes&amp;metric=sqale_index" alt="Technical Debt"></a>
    <a href="https://sonarcloud.io/summary/overall?id=arrase_eloquent-notes"><img src="https://sonarcloud.io/api/project_badges/measure?project=arrase_eloquent-notes&amp;metric=duplicated_lines_density" alt="Duplicated Lines (%)"></a>
    <a href="https://sonarcloud.io/summary/overall?id=arrase_eloquent-notes"><img src="https://sonarcloud.io/api/project_badges/measure?project=arrase_eloquent-notes&amp;metric=security_rating" alt="Security Rating"></a>
    <a href="https://sonarcloud.io/summary/overall?id=arrase_eloquent-notes"><img src="https://sonarcloud.io/api/project_badges/measure?project=arrase_eloquent-notes&amp;metric=reliability_rating" alt="Reliability Rating"></a>
    <a href="https://sonarcloud.io/summary/overall?id=arrase_eloquent-notes"><img src="https://sonarcloud.io/api/project_badges/measure?project=arrase_eloquent-notes&amp;metric=sqale_rating" alt="Maintainability Rating"></a>
    <a href="https://sonarcloud.io/summary/overall?id=arrase_eloquent-notes"><img src="https://sonarcloud.io/api/project_badges/measure?project=arrase_eloquent-notes&amp;metric=ncloc" alt="Lines of Code"></a>
  </div>
</div>

<div class="section-header">
  <h2>Key Features</h2>
  <span>Voice dictation to structured notes, locally</span>
</div>

<div class="projects-grid">
  <div class="feature-card">
    <i class="fa-solid fa-microphone feature-icon" aria-hidden="true"></i>
    <h3>One-Gesture Capture</h3>
    <p>Left-click the tray icon or press a global shortcut bound to <code>eloquent-notes toggle</code>. Visual and acoustic cues show the recording state.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-wand-magic-sparkles feature-icon" aria-hidden="true"></i>
    <h3>Clean, Structured Notes</h3>
    <p>A four-phase Gemma 4 pipeline transcribes, rewrites the dictation as clean prose with a title, classifies the note type, and generates 2&ndash;5 tags.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-file-lines feature-icon" aria-hidden="true"></i>
    <h3>Plain Markdown Files</h3>
    <p>One file per note with YAML frontmatter, in a folder you choose. No database; the folder can even live inside an Obsidian vault.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-list-ul feature-icon" aria-hidden="true"></i>
    <h3>Notes Timeline</h3>
    <p>A day-grouped timeline with type and tag filters, and a reader where title, type, tags and body are editable.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-comment-medical feature-icon" aria-hidden="true"></i>
    <h3>Add Dictation</h3>
    <p>Dictate more into an existing note: the new text is rewritten and appended as a paragraph, keeping the note's type and tags.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-magnifying-glass feature-icon" aria-hidden="true"></i>
    <h3>Semantic Search</h3>
    <p>Search notes by meaning with a local EmbeddingGemma model. Embeddings are computed on demand and cached.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-shield-halved feature-icon" aria-hidden="true"></i>
    <h3>Offline &amp; Private</h3>
    <p>Audio never touches the disk, and transcription, rewriting, classification, tagging and search all run locally through Ollama.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-sliders feature-icon" aria-hidden="true"></i>
    <h3>Customizable Prompts</h3>
    <p>Tailor the Markdown prompts of every pipeline phase and the output language of titles, prose and tags.</p>
  </div>

  <div class="feature-card">
    <i class="fa-solid fa-circle-half-stroke feature-icon" aria-hidden="true"></i>
    <h3>Light &amp; Dark Themes</h3>
    <p>Explicit dark and light palettes that follow your desktop color scheme and switch live when the system palette changes.</p>
  </div>
</div>

<div class="section-header">
  <h2>Notes Window &amp; Semantic Search</h2>
  <span>Day-grouped timeline, editable reader &amp; meaning-based search</span>
</div>

Browse notes grouped by day, filter by type or `#tag`, search by meaning with local embeddings, or click any card to edit its title, type, tags and body or append a new dictation. Toggle the site theme in the top bar to preview both **dark** and **light** modes.

![Notes Timeline (Dark)](screenshots/timeline-dark.png#only-dark)
![Notes Timeline (Light)](screenshots/timeline-light.png#only-light)

![Note Reader (Dark)](screenshots/reader-dark.png#only-dark)
![Note Reader (Light)](screenshots/reader-light.png#only-light)

![Semantic Search (Dark)](screenshots/search-dark.png#only-dark)
![Semantic Search (Light)](screenshots/search-light.png#only-light)

<div class="section-header">
  <h2>Dark &amp; Light Theme Support</h2>
  <span>Follows your system palette automatically</span>
</div>

| Dark Theme | Light Theme |
| :---: | :---: |
| ![Timeline Dark](screenshots/timeline-dark.png) | ![Timeline Light](screenshots/timeline-light.png) |
| ![Reader Dark](screenshots/reader-dark.png) | ![Reader Light](screenshots/reader-light.png) |

<div class="section-header">
  <h2>Graphical Configuration Interface</h2>
  <span>Visual settings &amp; prompt editor</span>
</div>

Eloquent Notes includes a PyQt6 dialog for editing the notes folder, timeline layout and note type colors, AI and search models, audio parameters and prompts.

![Configuration GUI (Dark)](screenshots/configuration-dark.png#only-dark)
![Configuration GUI (Light)](screenshots/configuration-light.png#only-light)

![Appearance Settings (Dark)](screenshots/configuration-appearance-dark.png#only-dark)
![Appearance Settings (Light)](screenshots/configuration-appearance-light.png#only-light)

![Prompts Editor (Dark)](screenshots/configuration-prompts-dark.png#only-dark)
![Prompts Editor (Light)](screenshots/configuration-prompts-light.png#only-light)

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
    <p>Explore the module layout, PyQt6 event loop, tray and notes window, QLocalServer IPC, in-memory audio capture, and threading model.</p>
  </a>

  <a href="pipeline/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-brain feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Four-Phase AI Pipeline</h3>
    <p>Deep dive into Phase 1 (Transcription), Phase 2 (Rewriting), Phase 3 (Classification), Phase 4 (Tagging), model preloading, and JSON retry validation.</p>
  </a>

  <a href="notes/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-book-bookmark feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Notes &amp; Search</h3>
    <p>Note file format and folder, the notes window, editing, adding dictations, and semantic search with its embedding cache.</p>
  </a>

  <a href="configuration/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-gear feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>Configuration</h3>
    <p>Reference for the configuration dialog, <code>config.yaml</code> settings and prompt customization.</p>
  </a>

  <a href="usage-shortcuts/" class="feature-card">
    <div class="card-top">
      <i class="fa-solid fa-keyboard feature-icon" aria-hidden="true"></i>
      <span class="card-badge">Read →</span>
    </div>
    <h3>System Tray &amp; Shortcuts</h3>
    <p>Tray interactions, notes window controls, and desktop environment shortcuts (GNOME, KDE Plasma, i3/Sway).</p>
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
