# AuraVox

**AuraVox** is a self-hosted, multi-user, multi-assistant conversational AI platform engineered for 100% local execution on consumer GPU hardware (optimized for Windows + NVIDIA CUDA). It combines large language models (**Ollama**), low-latency multilingual speech recognition (**faster-whisper** + **Silero VAD**), neural speech synthesis (**Supertonic-3 ONNX** + **Qwen3-TTS** zero-shot voice cloning), local image/video generation (**ComfyUI** with automatic VRAM swapping), local RAG document indexing, and **Model Context Protocol (MCP)** tool orchestration inside a zero-framework Python HTTP/SSE server and a vanilla ES2022 Single-Page Application.

---

## Table of Contents

1. [System Architecture & Data Flow](#1-system-architecture--data-flow)
2. [Core AI & Audio Stack](#2-core-ai--audio-stack)
   - [2.1 LLM Engine & Tool Orchestration (`Ollama`)](#21-llm-engine--tool-orchestration-ollama)
   - [2.1b Remote LLM Providers via API & Hugging Face Downloads](#21b-remote-llm-providers-via-api-optional--hugging-face-downloads)
   - [2.2 Speech-to-Text (`faster-whisper` + `Silero VAD`)](#22-speech-to-text-faster-whisper--silero-vad)
   - [2.3 Text-to-Speech (`Supertonic-3 ONNX` & `Qwen3-TTS` Voice Cloning)](#23-text-to-speech-supertonic-3-onnx--qwen3-tts-voice-cloning)
   - [2.4 Local Image & Video Generation (`ComfyUI` + Dynamic VRAM Swapping)](#24-local-image--video-generation-comfyui--dynamic-vram-swapping)
3. [Web Server, Security & Real-Time Streaming](#3-web-server-security--real-time-streaming)
4. [Application Features & Modules](#4-application-features--modules)
   - [4.1 Main Usage Dashboard & Multimedia/File Libraries](#41-main-usage-dashboard--multimediafile-libraries)
   - [4.2 Cross-Chat Content Referencing within a Profile](#42-cross-chat-content-referencing-within-a-profile)
   - [4.3 Categorized Settings & Dedicated Password/PIN Security](#43-categorized-settings--dedicated-passwordpin-security)
   - [4.4 Multi-Assistant Group Routing & Shared-VRAM Concurrency](#44-multi-assistant-group-routing--shared-vram-concurrency)
   - [4.5 Built-in Skills, Local RAG & File Conversion](#45-built-in-skills-local-rag--file-conversion)
   - [4.6 Plugin System & Model Context Protocol (MCP)](#46-plugin-system--model-context-protocol-mcp)
5. [Project Directory Structure](#5-project-directory-structure)
6. [Plug & Play Setup & Installation](#6-plug--play-setup--installation)
7. [Configuration Reference](#7-configuration-reference)
8. [HTTP API Overview](#8-http-api-overview)
9. [Command-Line Utilities (`extras/`)](#9-command-line-utilities-extras)

---

## 1. System Architecture & Data Flow

AuraVox runs as a single coordinator process (`app/webui/config_ui.py`) that manages local hardware resources (microphone, speakers, GPU VRAM, disk storage) and exposes both a local HTTP interface (`http://127.0.0.1:7860`) and an optional LAN HTTPS interface (`https://<LAN-IP>:7861`) for mobile devices and secondary computers.

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                            CLIENT LAYER (Browser SPA)                             │
│  app.js / features.js / i18n.js / icons.js / style.css                            │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐  ┌────────────────────┐  │
│  │  Dashboard  │  │ Media & File │  │ Text & Voice Chat│  │ Categorized Config │  │
│  │   (#/)      │  │  Libraries   │  │  (SSE + WebAudio)│  │   (#/shared)       │  │
│  └──────┬──────┘  └──────┬───────┘  └────────┬─────────┘  └─────────┬──────────┘  │
└─────────┼────────────────┼───────────────────┼──────────────────────┼─────────────┘
          │                │                   │                      │
          ▼                ▼                   ▼                      ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                    AURAVOX BACKEND (ThreadingHTTPServer)                          │
│  config_ui.py + chat_runtime.py + voice_listener.py + dashboard.py + network.py   │
│                                                                                   │
│  ┌──────────────────────┐  ┌─────────────────────────┐  ┌──────────────────────┐  │
│  │  Auth & Profiles     │  │  Assistant Engine       │  │  Background Daemons  │  │
│  │  PBKDF2-HMAC-SHA256  │  │  Tool Loop + Reviewer   │  │  Voice Listener      │  │
│  │  Session Isolation   │  │  Group Chat Router      │  │  Reminders / Routines│  │
│  └──────────────────────┘  └───────────┬─────────────┘  └──────────────────────┘  │
└────────────────────────────────────────┼──────────────────────────────────────────┘
                                         │
        ┌────────────────────────────────┼───────────────────────────────────┐
        ▼                                ▼                                   ▼
┌───────────────────┐    ┌───────────────────────────────┐    ┌─────────────────────┐
│   SPEECH STACK    │    │      LLM & RAG ENGINE         │    │  PLUGINS & TOOLS    │
│ • faster-whisper  │    │ • Ollama (/api/chat, /embed)  │    │ • ComfyUI (VRAM     │
│   + Silero VAD    │    │ • Per-Assistant Knowledge RAG │    │   Auto-Swapping)    │
│ • Supertonic-3    │    │   (nomic-embed-text / BM25)   │    │ • MCP Client        │
│   (ONNX CUDA/CPU) │    │ • Per-Profile Memory & Lists  │    │   (stdio & HTTP)    │
│ • Qwen3-TTS       │    │ • File Extractor & Converter  │    │ • Web Search, Map,  │
│   (Worker HTTP)   │    │   (Office COM/Libre/FFmpeg)   │    │   Weather, Spotify  │
└───────────────────┘    └───────────────────────────────┘    └─────────────────────┘
```

### End-to-End Request Lifecycles

1. **Streaming Text & Multimodal Chat (`POST /api/assistants/<name>/chat/stream`)**:
   - The browser sends the user message, conversation ID, optional attachments (images for vision models, audio recordings, or documents), and current UI mode via an HTTP POST request that upgrades into a **Server-Sent Events (`text/event-stream`)** stream.
   - `chat_runtime.py` resolves the user profile (`user_data/profiles/<profile_id>/`), injects relevant long-term profile memories, personal/home lists, RAG document chunks (`app/skills/knowledge.py`), and any files generated or attached in the conversation or referenced from the profile library.
   - `app/core/assistant_engine.py` executes `ask_with_tools()`, streaming tokens from Ollama (`http://127.0.0.1:11434/api/chat`). If the model emits native tool calls (or JSON tool calls parsed from text), AuraVox executes the corresponding Python skill, plugin tool, or MCP tool, streams a `tool` event to the UI, and feeds the result back into Ollama for up to `MAX_TOOL_ROUNDS = 5`.
   - When voice synthesis is enabled (`tts: true`), completed sentences are segmented on the fly (`SpeechChunker`) and synthesized in parallel via `Supertonic-3` or `Qwen3-TTS`, emitting `audio` SSE events so playback starts while the LLM is still generating subsequent sentences.

2. **PC Hands-Free Voice Loop (`app/webui/voice_listener.py` & `app/core/voice_loop.py`)**:
   - A background daemon thread captures 16 kHz mono PCM frames from the PC microphone via `sounddevice` (`app/voice/mic_stream.py`).
   - Once RMS energy crosses `silence_threshold` for `speech_trigger_chunks`, audio is buffered until `silence_duration` of silence is detected.
   - `faster-whisper` transcribes the segment with **Silero VAD** pre-filtering and language scoring constrained to the active assistants' configured languages.
   - `voice_loop.detect_wake_word()` normalizes text (accent stripping, Cyrillic/Greek/Arabic/CJK romanization via `anyascii`, and Levenshtein fuzzy token matching) to detect which assistant was called, strips the wake prefix, runs the assistant turn, and pushes notifications to `/api/notify` so any open browser tab displays and plays the response in real time.

3. **Browser & Mobile LAN Voice Mode (`POST /api/voice/turn`)**:
   - When the user opens the dedicated full-screen Voice Mode (`#/voice/<name>`) on PC or on a mobile phone over LAN HTTPS (`https://<LAN-IP>:7861`), `voice_listener.pause()` automatically releases the PC microphone so the browser can capture audio via `MediaRecorder` / WebAudio.
   - Recorded audio blobs are uploaded to `/api/voice/turn`, decoded to 16 kHz PCM via PyAV (`av`), transcribed by `faster-whisper`, processed by the target assistant, and returned with synthesized WAV chunk URLs.

---

## 2. Core AI & Audio Stack

### 2.1 LLM Engine & Tool Orchestration (`Ollama`)

Implemented in `app/core/assistant_common.py` and `app/core/assistant_engine.py`:

- **Direct Base-Model Execution (No `Modelfile` Duplication)**: Instead of creating duplicate Ollama models per assistant via `ollama create`, AuraVox calls the configured `base_model` directly on `/api/chat` and dynamically injects the system prompt, sampling parameters (`temperature`, `top_k`, `top_p`, `repeat_penalty`, `num_ctx`), and `keep_alive` (`30m` during active sessions; `0` on clean exit to free VRAM).
- **Dynamic System Prompt Construction (`build_system_prompt`)**:
  Combines:
  1. Assistant `personality` from `config/assistants.yaml`.
  2. Current local date, time, and day of the week (`build_datetime_note`).
  3. Shared household context (`user_context` — city, country, coordinates, shared notes) + per-profile context (`about` text and remembered facts).
  4. Active voice/text formatting constraints (e.g., forbidding markdown tables and symbols when speaking aloud so TTS reads naturally).
  5. Language enforcement rules (`build_language_rule`) restricting responses to the assistant's allowed `languages` list.
- **Hybrid Tool Calling & Reviewer Pipeline (`ask_with_tools`)**:
  - Supports native Ollama `tools` calls as well as fallback JSON extraction (`_parse_text_tool_call`) for models that emit tool invocations inside plain text.
  - **Self-Correction & Draft Reviewer (`_review_reply`)**: After the first draft is generated, a lightweight structured JSON verification pass (`format: _REVIEW_SCHEMA`) checks whether:
    - The model fabricated real-time data (weather, news, prices, reminders, lists, files) instead of calling an available tool.
    - The response violated the target language constraint.
    - The response leaked internal instructions or reasoning tags (`<think>...</think>`).
  - If a violation is detected, AuraVox automatically triggers a corrective retry round before delivering the final text to the user.
- **VRAM Contention Detection**: Before dispatching a turn, `_gpu_vram_mb()` queries `nvidia-smi`. If GPU VRAM utilization exceeds 92%, AuraVox logs a warning explaining when Windows spills shared GPU memory into system RAM.

### 2.1b Remote LLM Providers via API (optional) & Hugging Face Downloads

Ollama stays the default engine. Optionally, an assistant can run on a **remote model through an API** instead (`app/core/llm_remote.py`):

- **Provider kinds**: `openai` — any OpenAI-compatible `/v1/chat/completions` server (OpenAI, OpenRouter, Groq, LM Studio, llama-server, vLLM, Ollama's own `/v1`…); `anthropic` — Anthropic Messages API; `gemini` — Google Gemini API.
- **Setup**: *Settings → AI models → AI providers via API* (admin): name, API type (presets for OpenAI, OpenRouter, LM Studio, llama-server, Anthropic, Gemini), base URL, API key, model list (**Load the provider's model list** fills suggestions from `/models`), per-model `tools` / `vision` flags and a **Test** button (a short reply plus a tool-calling probe; if the model doesn't call the probe tool, `tools` is unchecked).
- **Using it**: remote models appear in the assistant's model picker under *Via API (remote)* and are stored in `base_model` as `@<provider_id>/<model>` (e.g. `@openrouter/meta-llama/llama-3.3-70b-instruct`). `@` is not valid in Ollama names, so local and remote models never collide. If the chosen model lacks `tools` or `vision`, the picker warns that it won't use tools / see images.
- **How it works**: every LLM call in AuraVox (tool loop, streaming, precheck, reviewer, language rewrite, structured JSON judgements, summaries) uses Ollama's `/api/chat` body and goes through `llm_remote.post()`, a drop-in for `requests.post`. Local models go to Ollama unchanged; remote ones are translated (base64 `images` → image parts, `tool_calls`/`tool` messages → each API's tool-use format with generated ids, `format` JSON schema → `response_format` / a forced `output` tool on Anthropic / `responseSchema` on Gemini, `options` → temperature/top_p/max tokens) and the reply comes back in Ollama's shape (`.json()` or NDJSON `.iter_lines()` for streaming), so tools, streaming and vision keep working. Requests with no messages (preload/unload with `keep_alive`) are no-ops for remote models.
- **VRAM / ComfyUI**: a remote model uses no VRAM; the ComfyUI plugin doesn't move its models to RAM when a remote-model assistant chats (`plugin.context`), and the Ollama ↔ ComfyUI swap only unloads what is really loaded in Ollama.
- **Secrets**: API keys (and the Hugging Face token) live in `config/secrets.json` (git-ignored), encrypted with Windows DPAPI for the current Windows user (`app/core/secrets_store.py`); they are never sent back to the browser (`has_key` only). Non-secret provider settings are in `config/llm_providers.json` (git-ignored). Full backups include `llm_providers.json`, and `secrets.json` only when secrets are included (DPAPI values only decrypt on the same PC/user).
- **Privacy note**: with a remote provider the conversation (and attached images) is sent to that service; embeddings for document search (`nomic-embed-text`) stay on Ollama.

**Hugging Face** (`app/core/hf_hub.py`, public API at `huggingface.co/api`):

- *Settings → AI models → Download from Hugging Face*: search GGUF repos (or paste `user/repo` / its link), list every quantization with its size (multi-part GGUFs are grouped), and **Download**. Public repos are pulled by Ollama itself as `hf.co/<user>/<repo>:<QUANT>` with the usual progress bar (`/api/models/pull`). Private or gated repos need a saved token (read access; accept the license on the website): Ollama can't receive the token, so AuraVox downloads the single-file GGUF to `cache/hf/`, uploads it as an Ollama blob (`/api/blobs`) and creates `<repo>:<quant>` with `/api/create`, then deletes the temporary file.
- *Settings → Plugins → ComfyUI → Download models from Hugging Face*: paste a repo, see its model files (`.safetensors`, `.gguf`, `.ckpt`, `.pt`, `.pth`, `.bin`, `.sft`) with sizes and a suggested `models\` subfolder (checkpoints, diffusion_models, unet, loras, vae, text_encoders, clip, clip_vision, controlnet, upscale_models, embeddings — editable), and download one file at a time with progress and cancel; it goes to `<ComfyUI>\models\<folder>\` via a `.part` file and the model lists refresh afterwards.

### 2.2 Speech-to-Text (`faster-whisper` + `Silero VAD`)

Implemented in `app/voice/stt_whisper.py`:

- **Model Tiers**: Configurable between `"fast"` (`small`, ~500 MB, ultra-low latency) and `"accurate"` (`large-v3-turbo`, ~1.6 GB, high accuracy across accents and noisy environments). Stored locally under `models/whisper/`.
- **Hardware Acceleration**: Automatically selects `device="cuda"` with `compute_type="float16"` when CUDA is available via `ctranslate2`, falling back cleanly to `device="cpu"` with `compute_type="int8"`.
- **Two-Stage Noise & Hallucination Filtering**:
  1. **Energy & Duration Gate**: Discards transient clicks shorter than `min_audio_seconds` (0.35 s) or below `min_rms`.
  2. **Silero VAD Integration**: Runs `vad_filter=True` (`min_silence_duration_ms=300`, `speech_pad_ms=200`). If Silero VAD detects zero speech frames, Whisper decoding is skipped entirely.
  3. **Whisper Confidence Gate**: Rejects segments where `no_speech_prob >= 0.6` or `avg_logprob < -1.0`, eliminating classic Whisper silence hallucinations (such as *"Thank you for watching"* or *"Subtítulos por..."*).
- **Constrained Multilingual Identification**:
  - When multiple languages are enabled across assistants, Whisper evaluates language probabilities restricted to `allowed_languages` (`es`, `en`, `pt`, `fr`, `de`, `it`, `ja`, `zh`, `ko`, `ru`, `ar`, `hi`, etc.) and combines acoustic log-probability with a script/stopword heuristic (`_text_language_score`).
- **Phonetic Wake-Word Detection & Name Correction**:
  - `voice_loop.py` builds phonetic aliases for every assistant (`config/wake_words.txt`) and uses `anyascii` transliteration + `difflib.SequenceMatcher` (`WAKE_FUZZY_RATIO = 0.72`) so phonetic transcriptions (e.g., `"Yarvis"`, `"Jarbis"`, `"Джарвис"`) reliably wake `JARVIS` while ignoring blacklisted words (`!jarabe`, `!llaves`).
  - `_fix_assistant_names()` automatically corrects phonetic misspellings of assistant names inside the transcribed command before sending it to the LLM.

### 2.3 Text-to-Speech (`Supertonic-3 ONNX` & `Qwen3-TTS` Voice Cloning)

AuraVox provides a dual-engine TTS architecture:

1. **Primary Fast Neural TTS — `Supertonic-3` (`app/voice/supersonictts.py`)**:
   - Runs the local ONNX model (`models/supertonic-3/`, ~250 MB) via `onnxruntime-gpu` (`CUDAExecutionProvider` with automatic fallback to `CPUExecutionProvider`).
   - Supports **31 languages** (`ar`, `bg`, `bn`, `ca`, `cs`, `da`, `de`, `el`, `en`, `es`, `et`, `eu`, `fi`, `fr`, `gl`, `gu`, `he`, `hi`, `hr`, `hu`, `id`, `it`, `ja`, `kn`, `ko`, `lt`, `lv`, `ml`, `mr`, `ms`, `nl`, `no`, `pa`, `pl`, `pt`, `ro`, `ru`, `sk`, `sl`, `sr`, `sv`, `sw`, `ta`, `te`, `th`, `tl`, `tr`, `uk`, `ur`, `vi`, `zh`) and **10 built-in voice styles** (`M1`–`M5` male, `F1`–`F5` female).
   - **Pre-Synthesis Text Normalization (`_normalize_numbers`)**: Converts digits, decimals, and percentages into spelled-out words in the target language via `num2words`, strips markdown/emojis (`clean_for_tts`), and pads short utterances so the ONNX prosody predictor never clips the final syllable.
   - **Parallel Pipelined Playback (`SpeechChunker`)**: Splits streaming LLM output at clause/sentence boundaries (`120`–`220` chars) and synthesizes chunk $N+1$ in a background thread while chunk $N$ is playing through the audio device.

2. **Zero-Shot Voice Cloning — `Qwen3-TTS` (`app/voice/qwen_tts.py` & `app/voice/_qwen_tts_worker.py`)**:
   - Clone any voice from a **3–15 second** reference audio clip (`WAV`/`MP3`/`OGG`/`FLAC` or recorded directly from the browser).
   - **Subprocess Isolation Architecture**: Because `Qwen3-TTS` (`Qwen3-TTS-12Hz-0.6B-Base` / `1.7B-Base`) requires PyTorch + `transformers` versions that conflict with the main process dependencies, AuraVox installs its Python dependencies into an isolated directory (`cache/qwen-tts/py-deps`) and runs `_qwen_tts_worker.py` as a persistent local HTTP microservice (`127.0.0.1`, random ephemeral port).
   - **Precomputed Voice Prompt Caching**: The reference audio and its Whisper transcript are encoded once into a `.prompt.pt` tensor file (`user_data/voices/<id>.prompt.pt`). Subsequent syntheses load the conditioning tensors directly, cutting synthesis latency by ~50%.
   - **Graceful Fallback & Idle VRAM Unloading**: While `Qwen3-TTS` is warming up on first use, assistants immediately speak using their configured `Supertonic-3` fallback voice (`M1`–`F5`) so the user never waits in silence. If no assistant is configured to use a cloned voice, the worker process is terminated automatically to free ~1.5–3.5 GB of VRAM.

### 2.4 Local Image & Video Generation (`ComfyUI` + Dynamic VRAM Swapping)

Implemented in `plugins/comfyui/` (`plugin.py`, `cu_workflows.py`, `cu_jobs.py`):

- **Installation Auto-Detection (`cu_locate.py`)**:
  - Finds **portable/standalone** installs (`ComfyUI_windows_portable`, `ComfyUI-Easy-Install`, cloned repos with a venv, StabilityMatrix packages…): any folder with `main.py` + `models\` (or `comfy\`), searched in the user's home/Desktop/Documents/Downloads, Program Files and two levels below every drive root. The port comes from the launcher `.bat` line that runs `main.py` (`--port`, default `8188`).
  - Finds **ComfyUI Desktop**: the app in `%LOCALAPPDATA%\Programs\@comfyorgcomfyui-electron\` (or `…\Programs\ComfyUI\`) and its data folder from `basePath` in `%APPDATA%\ComfyUI\config.json`; port `8000` unless its settings say otherwise.
  - If the **ComfyUI address** setting is empty, the detected installation's URL is used (the running one is preferred). Detection runs in the background on first use and can be repeated with **Detect again**.
  - If nothing is found (or to pick another one), the admin chooses the folder by hand in **Settings → Plugins → ComfyUI models and workflows → ComfyUI installation**: type the path or use **Browse…** (an in-app folder browser served by the plugin, since browsers don't expose full paths), then **Validate and use**. The choice is stored in `config/comfyui/config.json` (`install.path`).
  - With the folder known, saved workflows (`user/default/workflows`) and models (`models/*`) are listed even while ComfyUI is closed, saved workflows are read from disk when the API doesn't list them, and **Start ComfyUI** launches it in its own window (the portable launcher `.bat`, `python_embeded` + `main.py`, or the Desktop executable).
- **Workflow Auto-Discovery & Graph Conversion**:
  - Reads workflows directly from your ComfyUI installation (`user/default/workflows/*.json`) as well as custom JSON files placed in `plugins/comfyui/workflows/`.
  - Automatically converts ComfyUI visual graph JSON files (with `nodes` and `links`, including subgraph expansions) into executable ComfyUI `/prompt` API format on the fly (`cu_workflows.py`).
  - Auto-detects node roles: positive/negative text prompts (`CLIPTextEncode`, `TextEncodeQwenImageEditPlus`, etc.), `seed`, `steps`, `cfg`, `width`, `height`, `length`/`frames`, `fps`, and reference image inputs (`LoadImage`).
- **Four Specialized LLM Tools**:
  - `generate_image`: Text-to-image synthesis.
  - `edit_image`: Image-to-image / instruction-based editing (supports 1 to 4 reference images from the current chat, uploaded attachments, or the user's profile library).
  - `generate_video`: Text-to-video or image-to-video synthesis (`WAN 2.1/2.2`, `LTXV`, `HunyuanVideo`, `AnimateDiff`, `SVD`).
  - `Wait` / `Cancel` / `Regenerate` controls directly inside the chat bubble.
- **Automatic VRAM Arbitrator (`cu_jobs.py`)**:
  - Consumer GPUs (e.g., 12–16 GB VRAM) cannot hold a 14B–32B LLM in Ollama and a Flux.1 / WAN 2.2 diffusion pipeline in ComfyUI simultaneously without thrashing into system RAM.
  - Before submitting a job to ComfyUI:
    1. AuraVox queries Ollama `/api/ps` to record currently loaded LLM models (`_evict_ollama`).
    2. Sends `keep_alive: 0` to Ollama to immediately evict those models from VRAM.
    3. Submits the generation job to ComfyUI and streams live step-by-step progress (`max_steps`, `step`, `eta_seconds`) over WebSocket/HTTP to the chat UI.
    4. Keeps ComfyUI warm for a configurable grace window (`60s` after image generation, `20s` after video) in case the user asks for a quick variation.
    5. Calls ComfyUI `/free` (`unload_models: true, free_memory: true`) and reloads the assistant's LLM back into Ollama VRAM (`_restore_ollama`). If the user sends a chat message while ComfyUI is still in its post-job grace window, ComfyUI immediately yields VRAM back to Ollama.

---

## 3. Web Server, Security & Real-Time Streaming

Implemented in `app/webui/config_ui.py`, `app/webui/network.py`, and `app/webui/profiles.py`:

- **Zero-Framework Multi-Threaded HTTP/SSE Server**:
  - Built on Python's `http.server.ThreadingHTTPServer` (`_Server` with `daemon_threads = True`), avoiding external web framework overhead while supporting concurrent SSE streams, long-polling notification channels (`/api/notify`), and chunked media streaming with HTTP `Range` support (`206 Partial Content`) for video/audio seeking.
- **Role-Based Multi-Profile System (`app/webui/profiles.py`)**:
  - Supports three roles:
    - **`admin`**: Full access to shared settings, model downloads, plugins, MCP servers, backups, and profile management.
    - **`user`**: Isolated personal workspace (own chats, memories, reminders, routines, lists, custom assistants, and generated media/files).
    - **`guest`**: Temporary or restricted access without modifying global configuration.
  - **Cryptographic PIN/Password Hashing**: Profile PINs/passwords are hashed with **PBKDF2-HMAC-SHA256** (`120,000` iterations + 16-byte cryptographic salt) and verified using constant-time `hmac.compare_digest`.
  - **Session Tokens**: Validated via `HttpOnly`, `SameSite=Lax` cookies (`auravox_profile`) or `X-AuraVox-Profile` headers, stored in memory and persisted across restarts in `user_data/sessions.json`.
- **Host/Origin Validation & DNS-Rebinding Protection**:
  - Every request is checked against `_allowed_hosts()` (`127.0.0.1`, `localhost`, and authorized LAN IPs). Cross-origin requests from external websites are blocked (`403 Forbidden`) to prevent CSRF and DNS-rebinding attacks against your local AI server.
- **LAN HTTPS Server with Self-Signed X.509 Certificate & QR Pairing (`app/webui/network.py`)**:
  - Modern mobile browsers require a **Secure Context (`https://`)** to grant microphone access (`navigator.mediaDevices.getUserMedia`).
  - When LAN access is enabled in Settings, AuraVox generates a self-signed TLS certificate (`user_data/https_cert.pem`) with Subject Alternative Names (SAN) for `localhost`, `127.0.0.1`, and all local LAN IPv4 addresses, spins up a secondary TLS listener on port `7861`, and renders a scannable **QR code** containing a 192-bit access key (`?k=<token>`).

---

## 4. Application Features & Modules

### 4.1 Main Usage Dashboard & Multimedia/File Libraries

Implemented in `app/webui/dashboard.py` and `app/webui/static/features.js`:

- **Main View (`#/`)**:
  - Displays a live **Usage Dashboard** above the **Assistants Gallery** right after selecting a user profile.
  - Tracks and visualizes:
    - Total messages (user vs. assistant), approximate word count, and active conversations.
    - Per-assistant usage breakdown with horizontal activity bars.
    - 7-day rolling activity histogram.
    - Storage & item counters for generated images, generated videos, documents/files, remembered facts, active reminders, and scheduled routines.
  - Quick-navigation cards to jump directly to **Generated Images & Videos (`#/media`)** and **Generated Files (`#/files`)**.
- **Generated Images & Videos Library (`#/media`)**:
  - Aggregates all images (`.png`, `.jpg`, `.webp`, `.gif`) and videos (`.mp4`, `.webm`, `.mov`) generated via ComfyUI or uploaded across the active user profile's conversations.
  - Filterable by **name/prompt**, **media type** (`all`, `image`, `edit`, `video`), and **date** (presets or a *Date range…* with `from` / `to`), with sorting (`newest`, `oldest`, `name_asc`, `name_desc`, `size_desc`).
  - Minimal layout: type filters, back/switch, selection and card actions are **icon buttons** (`icons.js`, each with `title` + `aria-label`); thumbnails use `object-fit: contain`, so the whole image is visible (no cropping) with its aspect ratio.
  - Built-in **Lightbox Preview Modal** with full-resolution view, video player, download link, **"Use in chat..."** button, and delete action.
- **Generated Files Library (`#/files`)**:
  - Aggregates all documents, spreadsheets, presentations, code files, and archives generated (`create_file`, `convert_file`) or uploaded across the profile.
  - Filterable by **filename**, **date range**, and **sort order**.
  - Built-in **Document Preview Modal** (`/api/files/<id>/preview`) rendering inline previews for PDFs (`<iframe>`), images, audio/video players, and extracted text/Markdown previews for `.docx`, `.xlsx`, `.pptx`, `.txt`, `.md`, `.csv`, `.json`, `.yaml`, and source code files.
- **Deleting from the Libraries (single or bulk)**:
  - Every card in `#/media` and `#/files` has a selection checkbox and a trash button; the preview modal and the lightbox also have a **Delete** button. With items selected, the toolbar shows **Select everything shown**, **Cancel** and **Delete (N)**.
  - Confirmation uses the in-app dialog (`confirmDialog`), never the browser's `confirm()`. Guests cannot delete (`/api/files/delete` requires a saved profile).
  - `POST /api/files/delete` → `dashboard.delete_files(owner, …)` only accepts ids that are part of the **current profile's** library. For each id it removes every reference in that profile's saved chats (`strip_files`: the attachment and its vision image, the converted-file message, the ComfyUI card or just that variation), ComfyUI jobs (`plugins.forget_files` → `cu_jobs.forget`, or `jobs.json` directly when the plugin is off; deleted source/reference images are also dropped from other jobs' parameters), and then deletes the file and its `.json` metadata from `config/chats/files/` through `file_store.forget` — unless another profile still uses it (reported as `kept`). The open chat in the browser is purged too (`window.purgeChatFiles` in `app.js`) so it doesn't re-save stale references.
  - Library files are not linked to the RAG index (`config/knowledge/<assistant>/` stores extracted text separately and is managed from the assistant's **Documents** tab), so no index entries need to be removed.

### 4.2 Cross-Chat Content Referencing within a Profile

Users can reference any image, video, or document generated or uploaded in **any previous conversation** within the same profile:

1. **From the Chat Composer**: Click the **Library (`Biblioteca`)** button next to the paperclip attachment icon to open the **Profile Content Picker Modal**, switch between **Images & Videos** and **Files**, search by name, and click an item to attach it to the current chat.
2. **From the `#/media` or `#/files` Libraries**: Click **"Use in chat..."** on any card or inside the preview modal and choose which assistant conversation to send it to.
3. **Automatic Backend Resolution (`_conversation_files` in `app/webui/chat_runtime.py`)**:
   - Every tool that consumes files or images (`convert_file`, `edit_image`, `generate_video`) automatically searches the active conversation first and then falls back to `dashboard.list_profile_files()`, allowing you to ask an assistant in a brand-new chat: *"Convert the Word report I generated yesterday to PDF"* or *"Edit the cyberpunk city image from my other chat and make it rainy"* without even re-attaching it manually.

### 4.3 Categorized Settings & Dedicated Password/PIN Security

- **Sidebar-Categorized Settings (`#/shared` & Assistant Settings Drawer)**:
  - Instead of a single long scrolling page, both **Shared Settings (`#/shared`)** and the **Assistant Configuration Drawer** organize settings into a clean sidebar navigation menu (with horizontal scrollable pills on mobile screens) that displays one focused section at a time:
    - **Shared Settings Categories**: `General`, `Password & Security`, `Profiles & Accounts`, `Voice & Microphone`, `Cloned Voices (Qwen3-TTS)`, `AI Models (Ollama)`, `Plugins & ComfyUI`, `MCP Servers`, `Network / Mobile Access`, `Backups & Maintenance`.
    - **Assistant Settings Categories**: `Identity & Model`, `Voice & Languages`, `Activation (Wake Word / PTT)`, `Skills & Tools`, `Knowledge Documents (RAG)`, `Advanced Sampling Parameters`.
- **Dedicated Password & Security Section (`security`)**:
  - Allows any logged-in user to set, change, or remove their profile PIN/password directly without requiring the previous PIN, enforcing a double-entry confirmation (`New PIN/Password` + `Confirm PIN/Password`) before hashing and saving.

### 4.4 Multi-Assistant Group Routing & Shared-VRAM Concurrency

Implemented in `app/webui/chat_runtime.py` (`route_addressees`, `ask_group_opinion`):

- **Multi-Assistant Conversations**: You can invite multiple assistants (e.g., `JARVIS` and `BELLA`) into the same conversation or speak to them in group mode (`#/group`).
- **Intelligent Addressee Routing (`route_addressees`)**:
  - First checks deterministic mentions (e.g., `@Jarvis`, `"Jarvis and Bella"`, or *"respondan todos"*).
  - If ambiguous, uses a fast structured LLM classification call (`_GROUP_ROUTE_SCHEMA`) to determine which assistant(s) the user is addressing based on recent context and each assistant's persona.
- **VRAM-Aware Turn Serialization**:
  - When multiple assistants reply in the same turn (or during an **Opinion Round** where assistants debate or complement each other's answers), AuraVox groups execution order by `base_model` so assistants sharing the same Ollama model run back-to-back without swapping weights in and out of VRAM.

### 4.5 Built-in Skills, Local RAG & File Conversion

All built-in skills live in `app/skills/` and `app/tools/` and are exposed to assistants as structured tool definitions:

| Skill / Tool | Module | Technical Implementation |
|---|---|---|
| **Long-Term Memory** | `app/skills/memory.py` | Stores per-profile facts (`remember_fact`, `forget_fact`, `list_memories`) in `user_data/profiles/<id>/memories.json`. Injected into the system prompt on every turn. |
| **Reminders, Alarms & Timers** | `app/skills/reminders.py` | Persistent scheduler (`reminders.json`) checked every second by a daemon thread. Fires browser notifications, chat messages, and spoken TTS alerts over PC speakers. Supports one-shot and recurring (`daily`, `weekdays`, `weekly`) schedules. |
| **Personal & Home Lists** | `app/skills/lists.py` | Manages named checklists (shopping list, to-do, movies, etc.) with `scope="personal"` (per profile) or `scope="home"` (shared across all profiles in the household). |
| **Scheduled Routines** | `app/skills/routines.py` | Cron-like daily/weekly assistant prompts (`routines.json`) that run automatically at a specified `HH:MM`, execute tools (e.g., weather + reminders + news), and post/speak the result. |
| **Knowledge Base (Local RAG)** | `app/skills/knowledge.py` | Per-assistant document store (`user_data/knowledge/<assistant>/`). Splits uploaded docs into overlapping ~900-char chunks, embeds them via Ollama `nomic-embed-text` (`/api/embed`), and ranks chunks via **Cosine Similarity** with automatic fallback to **BM25 (`k1=1.5, b=0.75`)** if the embedding model is not installed. |
| **Document Attachment Extractor** | `app/core/attachments.py` | Pure-Python + PyAV extractor supporting `.pdf` (`pypdf`), `.docx`, `.xlsx`, `.pptx` (direct OOXML ZIP/XML parsing), `.odt`/`.ods`/`.odp`, `.epub`, `.rtf`, `.html`, `.csv`, `.json`, `.yaml`, code files, and audio/video files (transcribed automatically via `faster-whisper`). |
| **File Creation & Multi-Format Conversion** | `app/core/file_creator.py` & `app/core/file_converter.py` | Generates native `.docx`, `.xlsx`, `.pptx`, `.pdf`, `.md`, `.csv`, `.html`, `.json`, and `.txt` files. Converts between formats (`convert_file`) using a multi-tier pipeline: **Microsoft Office COM** (Word/Excel/PowerPoint on Windows) → **LibreOffice headless** → **Pure-Python renderer** for documents/data, plus **PyAV / FFmpeg** and **Pillow** for audio, video, and image format conversions. |
| **Web Search & Page Reader** | `app/tools/websearch.py` | Queries DuckDuckGo (`ddgs`) with region inference and fetches/cleans full article text (`fetch_webpage`) when deep reading is required. |
| **Weather & Nearby Places** | `app/tools/weather.py` & `app/tools/nearby_places.py` | Real-time weather + 7-day forecast via **Open-Meteo** (no API key required) and interactive **OpenStreetMap Overpass API** place search with distance sorting (`Haversine`). |
| **Spotify Control** | `app/tools/spotify_skill.py` | Search and launch tracks, artists, albums, playlists, or genres via local Spotify URI schemes or full playback control (`pause`, `next`, `previous`, `volume`) via Spotify Web API OAuth2. |

### 4.6 Plugin System & Model Context Protocol (MCP)

- **Drop-In Python Plugins (`app/core/plugins.py` & `plugins/`)**:
  - Any `.py` file or package subfolder inside `plugins/` is auto-discovered at startup and hot-reloaded whenever its file modification timestamp (`mtime`) changes.
  - Supports single-tool plugins (`TOOL` + `run()`) and multi-tool plugins (`TOOLS` + `HANDLERS`, plus optional `SETTINGS` and `STATUS()` hooks for the Settings UI).
  - Included plugins:
    - `plugins/comfyui/`: Full ComfyUI workflow manager, job queue, and VRAM arbitrator.
    - `plugins/pc_control/`: Local Windows automation (volume control, media keys, system mute, screenshots, opening applications/URLs).
    - `plugins/clipboard.py`: Read/write system clipboard content.
- **Model Context Protocol Client (`app/core/mcp_client.py`)**:
  - Native JSON-RPC 2.0 MCP client supporting both **`stdio`** (spawning local Node.js / Python / binary MCP servers) and **`http`** (Streamable HTTP / JSON-RPC endpoints).
  - Discovers tools via `tools/list`, namespaces them as `mcp__<server>__<tool>` to avoid collisions, and exposes them to any assistant that enables `mcp:<server>` in its skills list.

---

## 5. Project Directory Structure

```text
AuraVox/
├── AuraVox.bat                     # Main one-click launcher (starts the Web UI & voice server)
├── requirements.txt                # Pip dependencies for standard Python 3.11+ environments
├── README.md                       # Technical architecture & user documentation (this file)
├── PROJECT_CONTEXT.md              # AI developer context & architectural invariants
├── AGENTS.md / CLAUDE.md           # Pointers to PROJECT_CONTEXT.md for coding agents
├── app/
│   ├── paths.py                    # Centralized path resolver & Plug-and-Play config bootstrapper
│   ├── core/
│   │   ├── assistant_common.py     # Config loader, system prompt builder, Ollama helpers
│   │   ├── assistant_engine.py     # LLM tool-calling loop, draft reviewer, streaming client
│   │   ├── attachments.py          # Document, OOXML, PDF, and audio/video text extraction
│   │   ├── file_converter.py       # Multi-format document/data/image/audio/video converter
│   │   ├── file_creator.py         # Native PDF, DOCX, XLSX, PPTX, MD, CSV, HTML generator
│   │   ├── mcp_client.py           # Model Context Protocol (stdio & HTTP JSON-RPC 2.0) client
│   │   ├── plugins.py              # Hot-reloading plugin discovery and execution engine
│   │   └── voice_loop.py           # Terminal voice loop, wake-word matcher & TTS chunker
│   ├── voice/
│   │   ├── mic_stream.py           # 16 kHz mono sounddevice capture with RMS energy detector
│   │   ├── stt_whisper.py          # faster-whisper + Silero VAD multilingual transcription
│   │   ├── supersonictts.py        # Supertonic-3 ONNX (31 languages, 10 voices, CUDA/CPU)
│   │   ├── qwen_tts.py             # Qwen3-TTS zero-shot voice cloning manager
│   │   └── _qwen_tts_worker.py     # Isolated HTTP worker process for Qwen3-TTS inference
│   ├── skills/
│   │   ├── knowledge.py            # Per-assistant RAG (nomic-embed-text cosine + BM25)
│   │   ├── lists.py                # Personal & household shared lists
│   │   ├── memory.py               # Per-profile persistent long-term memory
│   │   ├── reminders.py            # Background daemon for alarms, timers, and reminders
│   │   └── routines.py             # Scheduled recurring assistant routines
│   ├── tools/
│   │   ├── nearby_places.py        # OpenStreetMap Overpass API nearby search
│   │   ├── spotify_skill.py        # Spotify URI launcher & Web API playback controller
│   │   ├── weather.py              # Open-Meteo current weather & forecast
│   │   └── websearch.py            # DuckDuckGo search & webpage article extractor
│   ├── scripts/
│   │   ├── free_ollama_memory.py   # CLI utility to immediately unload all models from Ollama VRAM
│   │   ├── spotify_setup.py        # Interactive OAuth2 setup wizard for Spotify
│   │   └── switch_model.py         # CLI utility to switch an assistant's Ollama base_model
│   └── webui/
│       ├── config_ui.py            # HTTP/SSE server, REST API router, startup orchestrator
│       ├── chat_runtime.py         # Chat turn execution, TTS caching, group routing, file resolver
│       ├── dashboard.py            # Usage metrics aggregator & profile media/file library indexer
│       ├── voice_listener.py       # Background PC microphone wake-word & PTT listener for Web UI
│       ├── profiles.py             # Multi-user profiles, PBKDF2-SHA256 PIN auth & sessions
│       ├── network.py              # LAN HTTPS server, self-signed X.509 generator & QR pairing
│       ├── backups.py              # Automatic & manual ZIP backup/restore manager
│       ├── diagnostics.py          # Self-healing hardware/service diagnostics
│       ├── i18n.py                 # Backend ES/EN localization dictionary
│       ├── server_log.py           # Stdout/stderr tee logger for terminal & Web UI Console
│       └── static/                 # Zero-build vanilla ES2022 Single-Page Application
│           ├── index.html          # Main application shell
│           ├── app.js              # Core SPA router, chat view, categorized settings, modals
│           ├── features.js         # Dashboard, Media/File libraries, Library Picker, Voice Mode
│           ├── i18n.js             # Frontend bilingual (ES/EN) string catalog
│           ├── icons.js            # Inline SVG icon registry
│           └── style.css           # Responsive CSS (desktop & mobile) with light/dark themes
├── config/
│   ├── assistants.example.yaml     # Default assistant definitions template (auto-copied on first run)
│   ├── voice_settings.example.yaml # Default STT/TTS settings template (auto-copied on first run)
│   ├── spotify_config.example.yaml # Default Spotify config template (auto-copied on first run)
│   ├── wake_words.example.txt      # Default phonetic wake-word aliases (auto-copied on first run)
│   └── languages.txt               # Supported ISO 639-1 language codes
├── plugins/
│   ├── README.md                   # Guide for authoring custom Python plugins
│   ├── clipboard.py                # System clipboard plugin
│   ├── pc_control/                 # Windows volume, media keys, screenshot & app launcher plugin
│   └── comfyui/                    # ComfyUI image/video generation plugin & workflow converter
└── extras/                         # Optional standalone CLI batch launchers
```

---

## 6. Plug & Play Setup & Installation

AuraVox is designed to work **out of the box (`Plug & Play`)** when cloned from Git. All personal configurations, user profiles, chats, cloned voices, and generated media are git-ignored, and **AuraVox automatically bootstraps its configuration files from `config/*.example.*` on first launch** (`ensure_default_configs()` in `app/paths.py`).

### Prerequisites

1. **Operating System**: Windows 10 or Windows 11 (64-bit).
2. **GPU (Recommended)**: NVIDIA GPU with CUDA support (8 GB+ VRAM recommended for 8B models; 16 GB VRAM such as RTX 4080 Super recommended for 14B–32B models + ComfyUI + Qwen3-TTS). Runs on CPU if no NVIDIA GPU is present.
3. **Ollama**: Install from [https://ollama.com](https://ollama.com) and pull at least one chat model:
   ```powershell
   ollama pull qwen3:14b
   # Optional: pull the embedding model for semantic RAG over uploaded documents
   ollama pull nomic-embed-text
   ```
4. **Python 3.11+**:
   - Either place an embedded Python 3.11 runtime inside `python/` (portable mode), or use your system Python / virtual environment:
   ```powershell
   pip install -r requirements.txt
   ```
5. **Local Speech Models (`models/`)**:
   - **Whisper (`models/whisper/`)**: Downloaded automatically by `faster-whisper` / Hugging Face on first run if not already present in `models/whisper/<size>/`.
   - **Supertonic-3 (`models/supertonic-3/`)**: Place the ONNX model files inside `models/supertonic-3/` (or download from Hugging Face `Supertone/supertonic-2` / `supertonic-3`).

### Launching AuraVox

Double-click **`AuraVox.bat`** or run from the terminal:

```powershell
.\AuraVox.bat
# Or with system Python:
python -m app.webui.config_ui
```

- On first startup, AuraVox automatically copies:
  - `config/assistants.example.yaml` → `config/assistants.yaml`
  - `config/voice_settings.example.yaml` → `config/voice_settings.yaml`
  - `config/spotify_config.example.yaml` → `config/spotify_config.yaml`
  - `config/wake_words.example.txt` → `config/wake_words.txt`
- Opens `http://127.0.0.1:7860` in your default browser and guides you through creating your administrator profile.

---

## 7. Configuration Reference

All configuration files live in `config/` and can be edited either through the **Web UI Settings (`#/shared`)** or directly in YAML/text:

### `config/assistants.yaml`

Defines shared household context (`user_context`) and each assistant's configuration:

```yaml
user_context:
  city: "San José"
  country: "Costa Rica"
  latitude: 9.9281
  longitude: -84.0907
  shared_context: |
    Household notes shared across all assistants.

jarvis:
  label: "JARVIS"
  avatar: ""
  base_model: "qwen3:14b"
  voice: "M5"                 # M1..M5 (male), F1..F5 (female), or custom Qwen3-TTS voice ID
  speed: 1.08                 # 0.7 to 1.5
  steps: 16                   # Supertonic ONNX diffusion steps (2 to 32)
  languages: ["es", "en"]     # Allowed ISO 639-1 languages
  wake_word: true             # Enable hands-free wake-word activation
  push_to_talk_key: ""        # Optional global PTT key (e.g., "f4", "right ctrl")
  temperature: 0.5
  top_k: 30
  top_p: 0.85
  repeat_penalty: 1.15
  num_ctx: 8192
  skills:
    - web_search
    - weather
    - nearby_places
    - reminders
    - memory
    - lists
    - files
    - knowledge
    - plugin:comfyui
    - plugin:pc_control
  personality: |
    You are JARVIS, a concise, dry-humored technical AI assistant...
```

### `config/voice_settings.yaml`

Controls Whisper STT model selection (`fast` = `small`, `accurate` = `large-v3-turbo`), microphone RMS thresholds, and default TTS parameters.

---

## 8. HTTP API Overview

| Method & Endpoint | Description |
|---|---|
| `GET /api/state` | Returns full application state: active profile, assistants, conversations, skills, and system status. |
| `GET /api/dashboard` | Returns aggregated usage metrics, per-assistant activity, 7-day timeline, and recent generated media/files (`#/`, `#/media`, `#/files`). |
| `GET /api/files/<id>/preview` | Returns inline preview metadata and extracted text/URLs for any generated or uploaded file in the profile. |
| `POST /api/files/delete` | Deletes one or more library files (`{"ids": [...]}`) of the current profile: removes their references in the profile's chats and ComfyUI jobs, then the file on disk unless another profile uses it. Returns `deleted`, `kept`, `refs`. |
| `POST /api/plugin/comfyui/{locate,browse,install,start}` | *(admin)* ComfyUI installation: re-detect, browse folders, choose/validate a folder (`path: ""` = back to automatic), start ComfyUI. |
| `POST /api/plugin/comfyui/{hf_files,hf_download,hf_cancel}`, `GET …/hf_status` | *(admin)* ComfyUI models from Hugging Face: list a repo's model files (with suggested `models\` folder), download one into `models\<folder>\`, cancel, progress. |
| `GET/PUT /api/llm/providers` | *(admin)* Remote LLM providers (no keys in the response, only `has_key`); PUT replaces the list (`api_key` only when it changes, `clear_key` to remove). |
| `POST /api/llm/models`, `POST /api/llm/test` | *(admin)* List a provider's models; test a model (short reply + tool-calling probe). |
| `GET /api/hf/search?q=`, `GET /api/hf/repo?repo=` | *(admin)* Search Hugging Face GGUF repos; list a repo's quantizations. |
| `POST /api/hf/pull`, `GET/PUT /api/hf/token` | *(admin)* Download a GGUF quantization into Ollama (`hf.co/…` pull, or download + import for private/gated repos); save/remove the HF token. |
| `POST /api/assistants/<name>/chat/stream` | Streams an assistant chat turn over SSE (`token`, `tool`, `audio`, `done`, `error` events). |
| `POST /api/group/stream` | Streams a multi-assistant group turn or opinion round over SSE. |
| `POST /api/voice/turn` | Processes a recorded audio blob from Browser/Mobile Voice Mode and returns transcript + reply + TTS audio URLs. |
| `GET /api/notify` | Long-polling notification stream for hands-free voice activations, ComfyUI job completions, and reminders. |
| `POST /api/profiles/<id>/pin` | Sets, updates, or clears a profile's PBKDF2-SHA256 PIN/password (`pin` + `pin_confirm`). |
| `GET /api/logs` | Returns incremental server console lines (`server_log.py`) for the integrated Web UI Console panel. |

---

## 9. Command-Line Utilities (`extras/`)

While **`AuraVox.bat`** is the primary launcher for the complete Web UI + Voice experience, standalone CLI scripts are available in `extras/`:

- `extras\run_voice_loop.bat`: Runs the terminal-only hands-free voice loop (`app/core/voice_loop.py`) without the Web UI.
- `extras\run_assistant.bat <name>`: Runs a terminal-only text chat session with a single assistant (`app/core/assistant_engine.py`).
- `extras\switch_model.bat`: Interactive CLI wizard to change an assistant's Ollama `base_model` (`app/scripts/switch_model.py`).
- `extras\free_ollama_memory.bat`: Emergency CLI utility that immediately unloads all currently loaded models from Ollama RAM/VRAM (`app/scripts/free_ollama_memory.py`).
- `extras\spotify_setup.bat`: Interactive OAuth2 setup wizard for Spotify integration (`app/scripts/spotify_setup.py`).
