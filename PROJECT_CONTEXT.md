# AuraVox — Full Project Context (For Humans & AI Coding Agents)

> **MANDATORY RULE FOR ANY AI MODIFYING THIS PROJECT:**
> 1. **Read this file before modifying any code** to respect the architecture, design conventions (pure Python stdlib HTTP server + zero-framework vanilla JS/CSS SPA, bilingual `en`/`es` UI, English documentation & terminal logs, per-profile isolation), and strict data privacy.
> 2. **Keep this file continuously synchronized**: whenever you add, rename, or modify HTTP routes, frontend views, modules under `app/`, LLM tools/plugins, `config/` schemas, or `.gitignore` rules, **update `PROJECT_CONTEXT.md` in the same change** so the next AI agent has an accurate map of the system.

---

## What AuraVox Is

**AuraVox** is a self-hosted, multi-user personal voice and text assistant platform that runs **100% locally on a Windows PC** (no cloud dependencies, no mandatory accounts, no telemetry). Everything runs and is managed through a single local web interface (`http://127.0.0.1:8765`, launched via `AuraVox.bat`):

- **Thinking (LLM):** [Ollama](https://ollama.com) running locally (`gemma4:E4B` by default; compatible with any Ollama model, including `tools` and `vision` models).
- **Hearing (STT):** `faster-whisper` (`small` or `large-v3-turbo`, with Silero VAD), running on GPU (`CUDA float16`) or CPU (`int8`).
- **Speaking (TTS):** `Supertonic-3` (10 built-in voices `F1–F5`, `M1–M5`, 31 languages, ONNX runtime) + **zero-shot cloned voices** via `Qwen3-TTS` (`0.6B` or `1.7B`, from 3 s to 10 min of reference audio, accelerated with CUDA graphs).
- **Image Generation, Image Editing & Video Synthesis:** Local **ComfyUI** integration (`plugins/comfyui`), featuring automatic VRAM arbitration between Ollama and ComfyUI and a built-in multimedia library.
- **Accessible from Desktop Browser & Mobile Devices:** Includes a local LAN HTTPS server (`:8766`) with a self-signed certificate, access token, and scannable QR code.

It uses **no frontend frameworks** (vanilla HTML + CSS + ES2022 JS across `app.js`, `features.js`, `i18n.js`, and `icons.js`) and **no backend web frameworks** (Python standard library `http.server.ThreadingHTTPServer`). It supports either an embedded portable Python in `python\` or a standard system Python installation (`requirements.txt`).

---

## Startup & Plug-and-Play Bootstrap

- **`AuraVox.bat`** → detects `python\python.exe` (or falls back to system `python`), runs `app\scripts\start_services.py` (starts Ollama, and ComfyUI if its plugin is on), launches `-m app.webui.config_ui`, and opens `http://127.0.0.1:8765`. On exit, it also shuts down the `Qwen3-TTS` worker process if active.
- **Automatic Plug & Play Initialization (`app/paths.py` → `ensure_default_configs()`):** On import, if `config/assistants.yaml`, `config/voice_settings.yaml`, `config/spotify_config.yaml`, or `config/wake_words.txt` do not exist (e.g., on a fresh `git clone`), they are automatically created by copying their tracked `*.example.*` templates. All runtime subdirectories (`config/chats/files`, `config/memory`, `config/lists`, `config/routines`, `config/knowledge`, `config/custom_voices`, `config/comfyui/workflows`, `config/certs`, `audio`, `backups`, `cache`, `logs`) are also created automatically.
- **`extras\`** contains optional standalone CLI `.bat` scripts (`run_voice_loop.bat`, `run_assistant.bat`, `switch_model.bat`, `spotify_setup.bat`, `free_ollama_memory.bat`).

---

## Directory & File Map

```text
AuraVox\
├── AuraVox.bat                  Primary launcher (starts the Web UI server on :8765)
├── requirements.txt             Python package dependencies for non-portable setups
├── README.md                    Comprehensive technical & user documentation (in English)
├── PROJECT_CONTEXT.md           This file (architectural source of truth for multiple AI agents)
├── AGENTS.md / CLAUDE.md        Entrypoint instructions for coding agents pointing to PROJECT_CONTEXT.md
├── .gitignore                   Strict exclusion of personal data, chats, generated media, and caches
│
├── app\
│   ├── paths.py                 Centralized project paths (supports AURAVOX_CONFIG) + auto-copy of *.example.*
│   ├── core\                    Core assistant logic (UI-agnostic)
│   │   ├── assistant_common.py  System prompt builder, output reviewer, streaming tool loop (ask_with_tools), SpeechChunker
│   │   ├── assistant_engine.py  Text engine + core tool definitions (TOOLS, call_tool) + Ollama/model checks
│   │   ├── config_store.py      Read/write assistants.yaml (preserving comments) and wake_words.txt
│   │   ├── voice_settings.py    Read/write voice_settings.yaml and cloned voice registry (custom:<id>)
│   │   ├── attachments.py       Pure-Python document text extraction (Word, Excel, PowerPoint, ODF, EPUB, RTF, HTML, TXT, code)
│   │   ├── converters.py        Multi-format conversion for convert_file (images, audio/video via ffmpeg, Office via Word/Excel/PowerPoint COM or LibreOffice, CSV↔XLSX/HTML/PDF in pure Python)
│   │   ├── plugins.py           Plugin discovery and loader (plugins/<id>/manifest.json + plugin.py)
│   │   ├── mcp_client.py        MCP (Model Context Protocol) client over stdio and HTTP JSON-RPC 2.0
│   │   ├── llm_remote.py        Optional remote LLM providers (OpenAI-compatible, Anthropic, Gemini): drop-in llm_remote.post() translating Ollama /api/chat bodies
│   │   ├── hf_hub.py            Hugging Face Hub: search, GGUF quantizations, file download with progress (assistant LLM + ComfyUI models)
│   │   ├── secrets_store.py     Local secrets (API keys, HF token) in config/secrets.json, DPAPI-encrypted on Windows
│   │   └── skills.py            Unified skill registry exposed to the LLM (memory, reminders, lists, documents, routines, plugins, MCP)
│   │
│   ├── voice\                   Speech recognition, synthesis, and PC activation
│   │   ├── supersonictts.py     Supertonic-3 TTS (ONNX, CUDA/CPU) + number-to-words in 31 languages + pre-generated announcements
│   │   ├── qwen_tts.py          Client + subprocess manager (qwen_worker.py) for Qwen3-TTS voice cloning
│   │   ├── qwen_worker.py       Separate process (Python with torch) keeping Qwen3-TTS loaded; caches each voice prompt
│   │   ├── qwen_graph.py        CUDA-graph frame loop for Qwen3-TTS (replaces talker.generate in the worker)
│   │   ├── voice_reference.py   Long recording → best ~20 s reference + all usable speech for the speaker embedding
│   │   ├── stt_whisper.py       faster-whisper STT with Silero VAD and constrained multilingual detection
│   │   ├── mic_stream.py        16 kHz mono sounddevice capture and RMS silence detector
│   │   ├── wake_word_utils.py   Wake-word detection on transcripts (phonetic aliases, fuzzy matching, exclusions)
│   │   └── push_to_talk.py      Global keyboard/mouse push-to-talk listener (GetAsyncKeyState on Windows)
│   │
│   ├── skills\                  Assistant skills (LLM tools + Web UI REST handlers)
│   │   ├── memory.py            Per-profile long-term memory (config\memory\<owner>.json)
│   │   ├── reminders.py         Reminders, alarms, and timers with background scheduler thread (config\reminders.json)
│   │   ├── lists.py             Personal and shared household lists/notes (config\lists\<owner>.json)
│   │   ├── knowledge.py         Per-assistant RAG document index (nomic-embed-text embeddings or BM25; config\knowledge\<assistant>\)
│   │   └── routines.py          Scheduled and on-demand routines (date + weather + reminders + lists + news)
│   │
│   ├── scripts\                 Standalone scripts; start_services.py is run by AuraVox.bat (Ollama + ComfyUI)
│   ├── tools\                   Built-in tool implementations
│   │   ├── websearch.py         Web search (DuckDuckGo + Wikipedia + webpage reader) and news headlines (Google News RSS)
│   │   ├── weather.py           Current weather and forecast (Open-Meteo, no API key required)
│   │   ├── nearby_places.py     Nearby places and driving distance (OpenStreetMap: Nominatim + Overpass + OSRM) with disk cache
│   │   └── spotify_skill.py     Spotify playback and control (Web API + local Windows URI/media key control)
│   │
│   └── webui\                   Web server and Single-Page Application
│       ├── config_ui.py         Main HTTP server (/api/* routes, SSE streaming, static files, Host/Origin/LAN security)
│       ├── dashboard.py         Per-profile usage analytics, media/file libraries, document preview, and cross-chat file resolver (`list_profile_files`)
│       ├── chat_runtime.py      Bridge between Web UI and engine: streaming chat, cached TTS, Whisper STT, group routing, convert_file
│       ├── chat_store.py        Server-side conversation persistence per assistant and profile (config\chats\), with auto-summarization
│       ├── file_store.py        Attached, converted, and generated files stored on disk (config\chats\files\), garbage-collection protected while referenced
│       ├── profiles.py          User profiles (admin / user / guest), cookie sessions, PBKDF2-SHA256 PINs, per-profile data isolation
│       ├── network.py           LAN HTTPS server (:8766) with self-signed X.509 cert + access key + QR code
│       ├── ollama_models.py     Installed model listing, capabilities (tools/vision/thinking), VRAM measurement, and ollama pull streaming
│       ├── ollama_update.py     Ollama version checker and updater via GitHub Releases
│       ├── model_updates.py     Automatic and manual Ollama model digest update checker
│       ├── diagnostics.py       One-click system diagnostics and auto-remediation
│       ├── backup.py            Single-assistant export/import (.auravox) and full system backup (.auravox-backup.zip)
│       ├── notify.py            Real-time server-to-browser notification queue (/api/notify, long-polling)
│       ├── server_log.py        In-memory and disk logger (logs\webui_server.log) feeding the terminal and integrated Web UI Console
│       ├── i18n.py              Server localization dictionary (English and Spanish via X-UI-Lang header)
│       └── static\
│           ├── index.html       SPA shell: sidebar (#sidebar: nav, one conversation per assistant, mic, Ollama status, theme, language, profile), mobile topbar, <main>, console, modals
│           ├── style.css        COMPILED stylesheet (Tailwind CSS v4 output of src/, committed; never edit by hand)
│           ├── src/             Stylesheet sources: tailwind.css (entry), tokens.css (light/dark design tokens + base), components.css (component styles), aura.css ("Aura" redesign layer), shell.css (sidebar/topbar layout), mobile.css (loaded last: keeps every container within the real screen width on phones, and the image viewer layout)
│           ├── icons.js         Inline SVG icon catalog (`svgIcon`, `ICON_CHAT`)
│           ├── i18n.js          Bilingual frontend translations (`STRINGS.es` and `STRINGS.en`)
│           ├── app.js           Core SPA logic: router, gallery, categorized settings, security/PIN, text/voice chat, orb, maps, profiles
│           └── features.js      Main Dashboard, `#/media` and `#/files` libraries, cross-chat Library Picker, memory, reminders, lists, docs, routines, plugins, MCP, diagnostics, backups, ComfyUI
│
├── plugins\                     Modular plugins (manifest.json + plugin.py)
│   ├── README.md                Developer guide for creating custom plugins (in English)
│   ├── comfyui\                 Local ComfyUI image/edit/video integration with automatic Ollama VRAM swapping
│   │                            (cu_locate.py: auto-detects portable/Desktop installs, manual folder choice, disk-read workflows/models, start ComfyUI)
│   ├── home_assistant\          Home Assistant smart-home integration
│   ├── pc_control\              Windows PC automation (launch apps/folders, volume, clipboard, lock/shutdown)
│   └── dice_example\            Minimal ~35-line example plugin
│
└── config\                      Configuration and user data directory
    ├── assistants.example.yaml      Clean assistant template (tracked in Git)
    ├── voice_settings.example.yaml  Clean voice settings template (tracked in Git)
    ├── spotify_config.example.yaml  Clean Spotify config template (tracked in Git)
    ├── wake_words.example.txt       Clean wake-word alias template (tracked in Git)
    ├── languages.txt                31 supported ISO 639-1 languages (tracked in Git)
    └── [runtime user files]         (Git-ignored: assistants.yaml, voice_settings.yaml, profiles.json, llm_providers.json, secrets.json, chats/, comfyui/, etc.)
```

---

## Conversation Lifecycle (Text & Voice)

1. **User Input:**
   - **Text:** The browser sends `POST /api/chat` with the current assistant config (`S.draft`), conversation history (`CHAT.history`), group participants, and active mode (`"text"` or `"voice"`).
   - **Browser Voice Mode:** The browser records via `MediaRecorder`, detects silence with `AnalyserNode`, uploads audio to `POST /api/chat/transcribe` (`faster-whisper` + phonetic assistant name correction), and then invokes `POST /api/chat`.
   - **PC Hands-Free (`voice_listener.py`):** Continuously monitors the PC microphone; when an assistant's wake word is detected (or its push-to-talk key is held), it forwards the recognized phrase to the active browser tab via `/api/voice/events`.
   - **Mobile / LAN Hands-Free (`features.js`):** Uses browser `SpeechRecognition` to detect the assistant wake word locally before streaming audio.

2. **Group Routing (`POST /api/chat/route`):** When multiple assistants participate in a conversation, the router determines which assistant(s) the user addressed or triggers an all-participants opinion round.

3. **Context Assembly & Tool Injection (`config_ui._chat_request` + `chat_runtime.chat`):**
   - Combines assistant `personality` + `shared_context` + active profile's `user_context` + current date/time + output style rules (Markdown for text chat, clean spoken prose for voice).
   - Injects dynamic context from `app/core/skills.py`: profile memories, pending reminders, matching routines, top-scoring RAG document chunks, and active plugin context (e.g., ComfyUI available images across the chat and profile library).
   - Collects tools authorized for the profile's role: `web_search`, `get_weather`, `find_nearby_places`, `find_place`, `play_music`, `convert_file` (with access to both current-chat files **and any file from other chats in the same profile** via `dashboard.list_profile_files`), `invite/remove_from_conversation`, memory, reminders, lists, documents, plugins (`generate_image`, `edit_image`, `generate_video`, Home Assistant, PC control), and MCP servers.

4. **Streaming Response (`assistant_common.ask_with_tools`):**
   - Calls Ollama (`/api/chat` with `stream: True`). Executes requested tool calls (up to `max_tool_rounds`), emits `event` updates to the UI, and feeds tool outputs back to the model.
   - As tokens stream (`delta`), `SpeechChunker` segments complete sentences and synthesizes TTS audio in parallel (`say` event with base64 WAV) so speech begins immediately.

---

## Web UI Views & Navigation (`index.html` + `app.js` + `features.js`)

The SPA uses hash routing (`location.hash`):

- **`#/` (`kind: "gallery"`):** Main home screen after selecting a user profile:
  - **Usage Dashboard (`renderDashboardSection` in `features.js` + `GET /api/dashboard` in `dashboard.py`):** Personalized greeting, quick-access buttons to **Generated Images & Videos (`#/media`)** and **Generated Files (`#/files`)**, 4 KPI cards (conversations/messages/words, ComfyUI renders & GPU time, converted/attached files, and memory/productivity), per-assistant activity chart, and recent media/files strips.
  - **Assistants Gallery:** Cards for all assistants visible to the active profile (text chat, voice mode, configure, create new assistant, or import `.auravox`).
- **Library layout (`#/media`, `#/files`):** minimal, icon-first (`libHeadHtml`, `libToolbarHtml` in `features.js`): type filter pills, back/switch, selection bar and card/preview actions are icon buttons with `title` + `aria-label`; date presets include `range` (shows from/to). Thumbnails and previews use `object-fit: contain` (whole image, aspect ratio kept).
- **`#/media` (`kind: "media"`):** Full library of all generated images, edits, and videos in the active profile. Supports search by text/prompt/assistant, type filter (`all`, `image`, `edit`, `video`), date filter (today, 7d, 30d, custom from/to), sorting (date/name/size), zoomable lightbox viewer (`openMediaLightbox`), and **"Use in chat"** (`useLibraryItemInChat`).
- **`#/files` (`kind: "files"`):** Full library of all generated, converted, and uploaded/transcribed files in the active profile. Supports search, origin/type filter, date range filter, sorting, inline preview modal (`openFilePreviewModal` + `GET /api/files/<id>/preview` for PDF, audio with transcript, image, video, Word, Excel, PowerPoint, code, and text), and **"Use in chat"**.
- **Deleting library items (`#/media` + `#/files`):** per-card checkbox and trash button, bulk bar (`paintLibSelBar` / `libSelClick` / `deleteLibraryItems` in `features.js`, selection in `DASH.sel`), delete buttons in the lightbox and preview modal, confirmation via in-app `confirmDialog`. Calls `POST /api/files/delete` (role `user`, guests get 403) → `dashboard.delete_files`: only ids in the caller's library; strips references from every chat in `profiles.chats_dir(owner)` (`dashboard.strip_files`), ComfyUI jobs (`plugins.forget_files` hook → `cu_jobs.forget`, or `jobs.json` directly when the plugin is disabled), then `file_store.forget` deletes the file unless another profile references it (`kept`). The open chat is purged client-side with `window.purgeChatFiles` (`app.js`). Library files are not linked to the RAG index.
- **`#/a/<name>` (`kind: "assistant"`):** Conversation stage (text mode and animated-orb voice mode) + collapsible side drawer for assistant settings organized by category tabs (`Identity`, `Brain`, `Voice & Languages`, `Activation`, `Documents`, `Export`).
- **`#/new` (`kind: "new"`):** New assistant creation wizard.
- **`#/shared` (`kind: "shared"`):** Shared and account settings organized into a categorized sidebar menu showing one active category at a time (`selectSettingsCat`). At `<= 900px` the menu becomes an off-canvas drawer (`.settings-shell.cfg-open`, toggled by `setCfgDrawer` from the sticky `.cfg-menu-toggle` button that shows the current category; closes on backdrop, ✕, Escape or after picking a category). Keep `.main > .settings-shell` free of a lingering `transform` (its entrance animation uses `animation-fill-mode: backwards`), or the fixed drawer is positioned relative to it:
  - `profile`: Personal profile (`myProfileCard`: name, role, shortcut to security) and location/coordinates (`you-card` + Leaflet map).
  - `security`: **Password & Security (`mySecurityCard`)**: Allows setting or changing the profile password/PIN **without asking for the previous password**, requiring two-field confirmation (`me.pin` and `me.pin_confirm`) and validating format (`4–64` characters, no spaces). Non-admin profiles can also remove their password here.
  - `memory`: Long-term memory, reminders/alarms, and scheduled routines.
  - `models`: Ollama status/updates and AI model management/downloads (Ollama name, or **Download from Hugging Face** with GGUF quantization list), plus *(admin)* **AI providers via API** (`#providers-card`).
  - `voice` *(admin)*: Whisper STT settings, Qwen3-TTS cloned voices, and wake-word exclusions.
  - `rules` *(admin)*: Shared rules (`shared_context`) and user profile administration.
  - `plugins` *(admin)*: Built-in/external plugins, ComfyUI workflow manager, and MCP servers.
  - `system` *(admin)*: LAN/mobile access (QR/HTTPS), system diagnostics, and backups.
- **`#/lists` (`kind: "lists"`):** Personal and household lists & notes view.
- **`#/diag` (`kind: "diag"`):** Full system diagnostics view.

---

## Cross-Chat File & Media Referencing within a Profile

Any content generated (ComfyUI images/videos, files converted via `convert_file`) or uploaded (documents, PDFs, spreadsheets, transcribed audio, images) inside a profile can be referenced in **any other chat belonging to the same profile**:

1. **From the Chat UI (`openLibraryPickerModal` in `features.js` + `attachLibraryItemToChat` in `app.js`):**
   - Both the text composer and voice mode include a **Profile Library** option (`data-chat-act="library"`, folder icon). In voice mode, attach / library / camera are grouped in a single "+" dropdown (`details.menu.voice-attach` in `voiceSides`, `features.js`), so the row shows only that button, the mic and the video-call button; the text composer shows them as separate buttons on wide screens and as the "+" menu (`.attach-more`) on narrow ones.
   - Opens a searchable, filterable modal listing all images, videos, audio clips, and documents in the profile. Selecting an item attaches it to `CHAT.attachments` reusing its `/api/files/<id>` URL (zero disk duplication), preparing base64 image data for vision models or reusing extracted text/transcripts.
   - In `#/media`, `#/files`, and preview modals, every item has a **"Use in chat"** button (`useLibraryItemInChat`) to pick an assistant and open the chat with that item pre-attached.
2. **From Backend Tools (`_conversation_files` in `config_ui.py` + `list_profile_files` in `dashboard.py`):**
   - On every `/api/chat` turn, `_conversation_files` merges all files from all chats and ComfyUI jobs owned by the same profile (`owner`) with the current chat's files (placing current-chat files last as most recent).
   - Tools like `edit_image`, `generate_video`, and `convert_file` can therefore directly reference files and images created or uploaded with another assistant in the same profile.

---

## Key Coding Conventions (For Collaborating AI Agents)

- **English Documentation & Terminal Output:** All project documentation (`README.md`, `PROJECT_CONTEXT.md`, `AGENTS.md`, `CLAUDE.md`, `plugins/README.md`, config templates) and all terminal/console outputs (`print(...)`, `server_log.log(...)`, `.bat` scripts) must be in **English**.
- **Bilingual Web UI (Spanish & English):** Every user-facing string in the web interface must be added to both `STRINGS.es` and `STRINGS.en` in `app/webui/static/i18n.js` (and `MESSAGES["es"]` / `MESSAGES["en"]` in `app/webui/i18n.py` for server responses).
- **Zero Heavy Frameworks:** Keep the backend on Python's standard library HTTP server and the frontend in vanilla ES2022 JS. The only build step is CSS: Tailwind CSS v4 standalone CLI (`extras\build-css.bat`, downloads `cache\tailwind\tailwindcss.exe` once, no Node) compiles `app/webui/static/src/tailwind.css` into `style.css`, which is committed so the app runs without building. Preflight (Tailwind's reset) is NOT included because app.js/features.js markup relies on browser defaults.
- **Theme & layout shell (`index.html` + `app.js`):** `<html data-theme="light|dark">` is set before paint by an inline script in `<head>` from `localStorage["ui-theme"]` (`system`/`light`/`dark`, default system); `applyTheme`/`setTheme`/`initTheme` keep it in sync (`[data-ui-theme]` buttons). The left sidebar (`renderSidebar`, `initSidebar`, `setNavOpen`, `toggleNavCollapsed` in `app.js`) is docked from 1024 px (collapsible, `html.nav-collapsed`, `localStorage["nav-collapsed"]`) and an off-canvas drawer below it (`body.nav-open`); buttons with `data-nav="<kind>"` call `select({kind})`, `data-nav-act="open|close|toggle"` drive the drawer, `#sb-chats` lists the profile's assistants (`data-sb-open`, `data-sb-voice`). The stage header has a ☰ `.nav-open-btn` instead of the old back button. The login screen (`body.locked`) hides the sidebar and shows theme/language in the topbar (`.locked-only`).
- **Atomic File Writes:** Write JSON/YAML updates to a `.tmp` file and replace with `os.replace` under a `threading.RLock` to prevent corruption on power loss or concurrent requests.
- **Profile Isolation (`owner`):** The primary admin uses `owner = ""` (backward-compatible with single-user installs); each additional user profile uses its `id` (`"p" + 8 hex`) as `owner` for private assistants, chats, memories, reminders, lists, routines, and ComfyUI jobs; `guest` stores temporary state in browser `sessionStorage`.
- **Mobile Layout (`src/*.css` → `style.css`):** Every Grid/Flex container inside `#/shared`, `#/media`, `#/files`, and chat views must keep `min-width: 0` and collapse `.grid-2` / `.grid-3` to a single column at `<= 720px` to prevent horizontal overflow on phones. Button rows must `flex-wrap: wrap` (or use `.ic-row` for field + icon buttons), and long paths/URLs in notes break with `overflow-wrap: anywhere`. Check at 360/390/430 px that nothing sticks out of the viewport or gets clipped inside cards (`.cfg-section > .card` has `overflow-x: hidden`, so `document.scrollWidth` alone doesn't catch clipping). Phone-specific fixes live in `src/mobile.css` (loaded last). In chat, message bubbles are flex children: they need `min-width: 0`, or one long attachment name or URL widens the whole chat list (`.chat-log` scrolls sideways). Test chat with a file attachment, a Markdown table, a code block and a long URL. On phones (`<= 720px`) assistant replies use the full width with their buttons below, and the console opens full screen with its controls in a grid. Generated-image cards (`FEATURE_ROLES.job`) keep the prompt hidden in a `<details class="cj-prompt">` ("Show prompt") under the image.
- **Remote LLM providers (`app/core/llm_remote.py`)**: optional OpenAI-compatible / Anthropic / Gemini APIs. `base_model` = `@<provider_id>/<model>` for a remote model. **All LLM HTTP calls must use `llm_remote.post(url, json=body, …)` instead of `requests.post`** (Ollama `/api/chat` body in, Ollama-shaped response out; streaming via NDJSON `iter_lines`). Use `llm_remote.is_remote(model)` before anything Ollama-specific (pull, `/api/show`, VRAM measure, unload). Config: `config/llm_providers.json`; keys in `config/secrets.json` via `app/core/secrets_store.py` (DPAPI on Windows; `get/set/has`). `list_models()` returns them under `remote` (with `capabilities`, `provider`, `remote: true`). Routes: `GET/PUT /api/llm/providers`, `POST /api/llm/models`, `POST /api/llm/test` (admin). UI: `#providers-card` (`renderProvidersCard`, `PROV` in `features.js`) and the *Via API* group in the assistant model picker (`renderModelList` in `app.js`).
- **Hugging Face (`app/core/hf_hub.py`)**: `search`, `repo_files`, `gguf_info` (quantizations grouped from `.gguf` names, `mmproj` = vision), `download` (token from `secrets_store` key `hf_token`, `.part` + sha256), `Job` (background download with progress). Assistant LLM: `GET /api/hf/search`, `GET /api/hf/repo`, `POST /api/hf/pull` (public → `start_pull("hf.co/<repo>:<quant>")`; private/gated → `_hf_import_worker`: download to `cache/hf/`, `/api/blobs` + `/api/create`), `GET/PUT /api/hf/token` (admin). UI: `#hf-details` in the models card (`HFS`, `mountHfBox`). ComfyUI: plugin actions `hf_files`, `hf_download`, `hf_status`, `hf_cancel` (`_hf_action` in `plugins/comfyui/plugin.py`, `HF_FOLDERS`, `_hf_guess`); UI `cuHf` / `CUHF` in `features.js`.
- **Cloned voices (`app/voice/`)**: `voice_reference.build` turns an uploaded recording (up to 10 min, `/api/voices`) into a ~20 s reference + `ref_text` and, optionally, `full_audio` (`<id>.full.wav`, averaged speaker embedding); phrases come from `chat_runtime.transcribe_words`. `qwen_worker.py` runs in the Qwen Python and caches the prompt per voice/model in `cache/qwen-tts/prompts/` (bump `_PROMPT_VERSION` when its computation changes). `qwen_graph.install` replaces `talker.generate` with captured CUDA graphs; the worker falls back to `torch.compile`, then plain. Other sub-sampling values or batches use the original `generate`.
- **Startup (`AuraVox.bat` → `app/scripts/start_services.py`)**: starts Ollama if it doesn't answer (waits up to 30 s), and ComfyUI if its plugin is enabled, an installation is configured or detected (`cu_locate`) and its URL is local; ComfyUI is not waited for. Never blocks AuraVox from starting. `AURAVOX_NO_AUTOSTART=1` skips it; `--dry-run` only reports.
- **Voice mode behaviour (`app.js`)**: barge-in never stops the assistant on energy alone: `waitTurn` keeps a recording ring (`BargeRing`) while it speaks, and on a loud moment ducks the output (`duckOutput`) and asks `/api/chat/transcribe?probe=1` (`chat_runtime.probe_speech`: Whisper's VAD, no-speech and log-probability, no per-language phrase lists); only real speech that isn't its own echo (`isOwnEcho`) stops it, and that recording continues as the user's turn. The reply text follows the audio (`reveal` in `askAssistant` + `playUrl(url, onProgress)`); if it's cut, only what was said stays in the conversation. Assistants have `expressiveness` (`none`/`some`/`lots`, `EXPRESSIVENESS` in `assistant_common.py`). While text mode generates, the send button is a stop button (`stopGeneration`).
- **Own phrases (`app/core/phrases.py`)**: per assistant `phrases: {search|tool|create|wait|fallback: {mode: auto|fixed, fixed: [...]}}` in assistants.yaml (each kind on one line as a JSON mapping; `config_store._phrases`, legacy `search_announcement`/`fallback_message` become fixed lists). Auto ones are generated by the assistant's model in the background (`phrases.ensure_async`) and cached in `config/phrases/<name>.json` keyed by a hash of name/label/model/personality. Page: `phrasePool`/`pickPhrase`/`toolPhraseKind` in `app.js`; server fallback via `phrases.pick` in `chat_runtime.chat`. The chat history summary is folded AFTER the reply (`_fold_history` at the end of `_chat`; the page drains the rest of the stream with `drainAfterReply`).
- **Voice previews**: Supertonic samples live in `audio/voice_previews/<lang>/<voice>.wav` (tracked); cloned-voice samples in `config/custom_voices/previews/<lang>/<id>_<stamp>.wav` (`paths.CUSTOM_VOICE_PREVIEWS_DIR`, git-ignored with the voices, removed with the voice).
- **Assistant ownership & renames**: a private assistant (`shared: false`) is visible to its `owner`; one with no owner (legacy) belongs to admins (`can_see` in `config_ui.py`). When an ownerless assistant is saved as private, `save_assistant` gives it to the profile saving it. Renaming moves its RAG folder, each profile's chat (`chat_store.rename_assistant`), reminders and routines. Test: `python tests/test_rename_assistant.py` (temporary `AURAVOX_CONFIG`).
- **Plugin hook `forget_files(ids, owner)` (optional in `plugin.py`):** called by `plugins.forget_files` when library files are deleted, so a plugin can drop what it stored about them (ComfyUI uses it for `jobs.json`).
- **ComfyUI installation (`plugins/comfyui/cu_locate.py`):** `find_all()` (Desktop via `%APPDATA%\ComfyUI\config.json` `basePath` + `%LOCALAPPDATA%\Programs\…\ComfyUI.exe`, port 8000; portable folders with `main.py` + `models\`, port from the launcher `.bat`, default 8188), `info(path)` validates a hand-picked folder, `browse(path)` lists folders for the in-app picker, `disk_workflows`/`disk_models` read from disk, `start()` launches it. `plugin.py` caches detection (`detect`, `install`), uses the install URL when the `url` setting is empty (`auto_url`), stores a manual choice in `config/comfyui/config.json` → `install.path`, and exposes admin actions `locate`, `browse`, `install`, `start` under `/api/plugin/comfyui/`.
