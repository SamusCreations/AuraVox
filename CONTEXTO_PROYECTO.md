# AuraVox — Contexto completo del proyecto (para humanos e IAs)

> **REGLA OBLIGATORIA PARA CUALQUIER IA QUE MODIFIQUE ESTE PROYECTO:**
> 1. **Lee este archivo antes de modificar código** para respetar la arquitectura, convenciones de diseño (Python puro + JS/CSS vanilla sin frameworks, bilingüe `es`/`en`, aislamiento por perfil) y privacidad de datos.
> 2. **Mantén este archivo siempre sincronizado**: cada vez que agregues o cambies rutas HTTP, vistas del frontend, módulos en `app/`, herramientas/plugins, esquemas de `config/` o reglas en `.gitignore`, **actualiza `CONTEXTO_PROYECTO.md` en el mismo cambio** para que la siguiente IA tenga el mapa exacto del sistema.

---

## Qué es

**AuraVox** es una plataforma de asistentes personales de voz y texto que corre **100 % en una PC con Windows** (sin nube, sin cuentas obligatorias, sin telemetría). Todo se abre y se usa desde una sola página web local (`http://127.0.0.1:8765`, que abre `AuraVox.bat`):

- **Pensar (LLM):** [Ollama](https://ollama.com) en la propia PC (`gemma4:E4B` por defecto; cualquier modelo de Ollama sirve, incluidos modelos con `tools` y `vision`).
- **Oír (STT):** `faster-whisper` (`small` o `large-v3-turbo`, con VAD Silero), en GPU (CUDA float16) o CPU (int8).
- **Hablar (TTS):** `Supertonic-3` (10 voces integradas `F1–F5`, `M1–M5`, 31 idiomas, en ONNX) + **voces clonadas** con `Qwen3-TTS` (`0.6B` o `1.7B`, a partir de 3–20 s de audio).
- **Crear imágenes, editarlas y hacer videos:** integración con **ComfyUI** local (`plugins/comfyui`), con gestión automática de VRAM entre Ollama y ComfyUI y biblioteca multimedia integrada.
- **Todo desde el navegador y desde el celular** (acceso en red local con HTTPS + QR + clave).

No usa frameworks de frontend (es HTML + CSS + JS vanilla en tres archivos principales: `app.js`, `features.js`, `i18n.js` más `icons.js`) ni de backend (`http.server.ThreadingHTTPServer` de la librería estándar de Python). Lleva su propio Python embebido en `python\`.

---

## Cómo arranca

- **`AuraVox.bat`** → lanza `python\python.exe -m app.webui.config_ui` y abre `http://127.0.0.1:8765`. Al cerrarse, apaga también el trabajador de Qwen3-TTS si estaba corriendo.
- En el arranque (`app/paths.py`), si no existen `config/assistants.yaml`, `config/voice_settings.yaml` o `config/spotify_config.yaml` (p. ej. tras clonar el repositorio limpio desde Git), se crean automáticamente copiando sus plantillas `*.example.yaml`.
- En `extras\` hay scripts `.bat` opcionales del modo consola clásico (`run_voice_loop.bat`, `run_assistant.bat`, `switch_model.bat`, `spotify_setup.bat`, `free_ollama_memory.bat`).

---

## Mapa de carpetas y archivos

```
AuraVox\
├── AuraVox.bat                  Arranque principal (abre la interfaz web en :8765)
├── README.md                    Guía para el usuario final
├── CONTEXTO_PROYECTO.md         Este archivo (fuente de verdad arquitectónica para múltiples IAs)
├── AGENTS.md / CLAUDE.md        Instrucciones de entrada para agentes de IA que apuntan a CONTEXTO_PROYECTO.md
├── .gitignore                   Exclusión estricta de datos personales, chats, medios generados y cachés
│
├── app\
│   ├── paths.py                 Todas las rutas del proyecto (soporta AURAVOX_CONFIG) + copia automática de *.example.yaml
│   ├── core\                    Lógica común de los asistentes (sin web)
│   │   ├── assistant_common.py  Prompts por idioma/modo, revisor de salida, bucle de herramientas con streaming (ask_with_tools), SpeechChunker
│   │   ├── assistant_engine.py  Motor de texto + definición de las herramientas base (TOOLS, call_tool) + chequeo de Ollama/modelos
│   │   ├── config_store.py      Lectura/escritura de assistants.yaml (conservando comentarios) y wake_words.txt
│   │   ├── voice_settings.py    Lectura/escritura de voice_settings.yaml y gestión de voces clonadas (custom:<id>)
│   │   ├── attachments.py       Extracción de texto de documentos (Word, Excel, PowerPoint, ODF, EPUB, RTF, HTML, TXT, código; sin librerías externas)
│   │   ├── converters.py        Conversión entre formatos para la herramienta convert_file (imagen, audio/video con ffmpeg, Office con Word/Excel/PowerPoint de Windows o LibreOffice, CSV↔XLSX/HTML/PDF en Python puro)
│   │   ├── plugins.py           Descubrimiento y carga de plugins (plugins/<id>/manifest.json + plugin.py)
│   │   ├── mcp_client.py        Cliente MCP (Model Context Protocol) por stdio y HTTP JSON-RPC 2.0
│   │   └── skills.py            Registro único de habilidades que van al LLM (memoria, recordatorios, listas, documentos, rutinas, plugins, MCP)
│   │
│   ├── voice\                   Oído, voz y activación en la PC
│   │   ├── supersonictts.py     TTS Supertonic-3 (ONNX, CUDA/CPU) + conversión de números a palabras en 31 idiomas + anuncios pre-generados
│   │   ├── qwen_tts.py          Cliente + proceso aparte (_qwen_tts_worker.py) para clonar voces con Qwen3-TTS
│   │   ├── _qwen_tts_worker.py  Proceso HTTP local que mantiene cargado el modelo Qwen3-TTS (usa el Python de ComfyUI si tiene CUDA)
│   │   ├── voice_listener.py    Hilo en segundo plano en la interfaz web: escucha por micrófono de la PC (wake word + push-to-talk)
│   │   ├── voice_loop.py        Bucle de voz clásico de consola (extras\run_voice_loop.bat)
│   │   ├── wake_word_utils.py   Detección del nombre del asistente en lo transcrito (alias fonéticos, fuzzy matching, exclusiones)
│   │   └── push_to_talk.py      Teclas y botones del mouse para hablar sin decir el nombre (GetAsyncKeyState en Windows)
│   │
│   ├── skills\                  Habilidades de los asistentes (cada una con herramientas para el LLM + API para la UI)
│   │   ├── memory.py            Memoria a largo plazo por perfil (config\memory\<owner>.json)
│   │   ├── reminders.py         Recordatorios, alarmas y temporizadores con hilo que avisa a la hora (config\reminders.json)
│   │   ├── lists.py             Listas y notas personales + de la casa (config\lists\<owner>.json)
│   │   ├── knowledge.py         Documentos por asistente (RAG local con embeddings de nomic-embed-text o BM25; config\knowledge\<asistente>\)
│   │   └── routines.py          Rutinas ("Buenos días" = fecha + clima + recordatorios + listas + noticias; también programadas por hora)
│   │
│   ├── tools\                   Implementación de las herramientas base
│   │   ├── web_search.py        Búsqueda web (DuckDuckGo + Wikipedia + lectura de páginas) y titulares de noticias (Google News RSS)
│   │   ├── weather_service.py   Clima actual y pronóstico (Open-Meteo, gratis, sin API key)
│   │   ├── nearby_places.py     Lugares cercanos y distancia en auto (OpenStreetMap: Nominatim + Overpass + OSRM) con caché en disco
│   │   └── spotify_player.py    Reproducción y control de Spotify (Web API + control local en Windows)
│   │
│   └── webui\                   Servidor e interfaz web
│       ├── config_ui.py         Servidor HTTP principal (todas las rutas /api/*, eventos SSE, archivos estáticos, seguridad Host/Origin/LAN)
│       ├── dashboard.py         Estadísticas de uso por perfil, catálogos de medios/archivos, vista previa de documentos y listado transversal de archivos del perfil (`list_profile_files`)
│       ├── chat_runtime.py      Puente entre la web y el motor: chat en streaming, TTS con caché, STT con Whisper, ruteo grupal, convert_file
│       ├── chat_store.py        Conversaciones guardadas en el servidor por asistente y perfil (config\chats\), con resumen automático
│       ├── file_store.py        Archivos adjuntos, convertidos y generados guardados en disco (config\chats\files\), protegidos mientras estén en chats o en jobs.json
│       ├── profiles.py          Perfiles (admin / user / invitado), sesiones por cookie, PIN con PBKDF2-SHA256, datos propios por perfil
│       ├── network.py           Servidor HTTPS en la red local (:8766) con certificado propio + clave de acceso + QR
│       ├── ollama_models.py     Listado de modelos instalados, capacidades (tools/vision/thinking), medición de VRAM y descargas (ollama pull)
│       ├── ollama_update.py     Comprobación e instalación de actualizaciones de Ollama desde GitHub Releases
│       ├── diagnostics.py       Diagnóstico en un clic (Ollama, modelos, variables de velocidad, GPU/VRAM, disco, Whisper, Supertonic, Qwen)
│       ├── backup.py            Exportar/importar un asistente (.auravox) y copia de seguridad completa (.auravox-backup.zip)
│       ├── notify.py            Cola de notificaciones en tiempo real del servidor al navegador (/api/notify, long-polling)
│       ├── server_log.py        Registro en memoria y en logs\webui_server.log (alimenta la consola integrada de la página)
│       ├── i18n.py               Textos del servidor en español e inglés (según cabecera X-UI-Lang)
│       └── static\
│           ├── index.html        Cascarón único de la SPA (barra superior, <main>, panel lateral, consola, diálogos)
│           ├── style.css        Todos los estilos (modo claro/oscuro, aro de voz, mapas, tarjetas, diseño móvil adaptativo)
│           ├── icons.js         Iconos SVG delineados (`svgIcon`, `ICON_CHAT`)
│           ├── i18n.js          Todos los textos de la interfaz en español (`STRINGS.es`) e inglés (`STRINGS.en`)
│           ├── app.js           Lógica principal: vistas, galería, ajustes por categorías, seguridad/PIN, chat escrito y modo voz, aro, mapas, perfiles, voces
│           └── features.js      Dashboard principal, bibliotecas `#/media` y `#/files`, selector transversal de biblioteca en chats, memoria, recordatorios, listas, documentos, rutinas, plugins, MCP, diagnóstico, respaldos, videollamada, ComfyUI
│
├── plugins\                     Plugins (cada carpeta tiene manifest.json + plugin.py)
│   ├── web_search\              Búsqueda en internet (integrado)
│   ├── weather\                 Clima y lugares cercanos (integrado)
│   ├── spotify\                 Música con Spotify (integrado)
│   ├── comfyui\                 Generar/editar imágenes y crear videos con ComfyUI local (con intercambio automático de VRAM con Ollama)
│   │   ├── plugin.py            Herramientas generate_image, edit_image, generate_video + rutas /api/plugin/comfyui/* + soporte de imágenes de todo el perfil
│   │   ├── client.py            Cliente HTTP/WebSocket de ComfyUI + liberación/recarga de modelos en VRAM
│   │   ├── workflows.py         Detección automática de qué hace cada flujo JSON y mapeo de sus entradas (prompt, semilla, tamaño, imagen…)
│   │   ├── jobs.py              Cola de trabajos en segundo plano, progreso en vivo, ETA e historial en config\comfyui\jobs.json
│   │   └── workflows\           Flujos incluidos listos para usar (Flux.2 Klein imagen/edición, LTX-Video, Wan 2.2)
│   ├── home_assistant\          Domótica con Home Assistant (luces, enchufes, clima, escenas)
│   ├── pc_control\              Controlar la PC (abrir programas/carpetas, volumen, portapapeles, bloquear, apagar con confirmación)
│   └── dice_example\            Plugin de ejemplo (~35 líneas) para aprender a crear uno
│
├── config\                      Configuración y datos del usuario
│   ├── assistants.example.yaml      Plantilla limpia de asistentes (publicada en Git)
│   ├── voice_settings.example.yaml  Plantilla limpia de ajustes de voz (publicada en Git)
│   ├── spotify_config.example.yaml  Plantilla limpia de Spotify (publicada en Git)
│   ├── languages.txt                Los 31 idiomas soportados por Whisper + Supertonic-3 (publicado en Git)
│   ├── wake_words.txt               Variantes fonéticas de los nombres y palabras excluidas (publicado en Git)
│   ├── assistants.yaml              (Ignorado por Git) Configuración local activa de asistentes y user_context
│   ├── voice_settings.yaml          (Ignorado por Git) Modelo de Whisper, ajustes de Qwen3-TTS y lista de voces clonadas
│   ├── spotify_config.yaml          (Ignorado por Git) Credenciales de Spotify
│   ├── profiles.json                (Ignorado por Git) Perfiles de usuario, hashes de PIN, sesiones y datos propios por perfil
│   ├── plugins.json                 (Ignorado por Git) Qué plugins están activados, rol mínimo y sus ajustes
│   ├── mcp.json                     (Ignorado por Git) Servidores MCP configurados
│   ├── network.json                 (Ignorado por Git) Estado y token del acceso desde otros dispositivos
│   ├── reminders.json               (Ignorado por Git) Recordatorios y alarmas
│   ├── model_memory.json            (Ignorado por Git) VRAM medida de cada modelo
│   ├── model_updates.json           (Ignorado por Git) Estado de actualizaciones de modelos en ollama.com
│   ├── certs\                       (Ignorado por Git) Certificado HTTPS local autogenerado para acceso LAN
│   ├── chats\                       (Ignorado por Git) Historial de conversaciones por perfil y asistente + carpeta files\ con adjuntos/medios
│   ├── custom_voices\               (Ignorado por Git) Audios WAV de referencia de las voces clonadas
│   ├── memory\                      (Ignorado por Git) Recuerdos por perfil (<owner>.json)
│   ├── lists\                       (Ignorado por Git) Listas por perfil (<owner>.json y home.json)
│   ├── routines\                    (Ignorado por Git) Rutinas por perfil (<owner>.json)
│   ├── knowledge\                   (Ignorado por Git) Documentos e índice de vectores por asistente
│   └── comfyui\                     (Ignorado por Git) settings.json, jobs.json y carpeta workflows\ para flujos propios
│
├── audio\                       Audios generados (ignorados por Git) y carpeta voice_previews\<idioma>\ con las muestras de cada voz
├── backups\                     Copias de seguridad .auravox-backup.zip (ignoradas por Git)
├── cache\                       Cachés locales (modelos de HuggingFace/Whisper/Supertonic, Qwen3-TTS, lugares cercanos; ignoradas por Git)
├── logs\                        webui_server.log (ignorado por Git)
└── python\                      Python embebido de Windows con las dependencias instaladas (ignorado por Git)
```

---

## Flujo de una conversación (texto y voz)

1. **Entrada del usuario:**
   - **Texto:** el navegador manda `POST /api/chat` con el asistente en edición (`S.draft`), el historial (`CHAT.history`), los participantes si es grupal y el modo (`"text"` o `"voice"`).
   - **Voz en la página:** el navegador graba con `MediaRecorder`, detecta el silencio con `AnalyserNode`, manda el audio a `POST /api/chat/transcribe` (que usa `faster-whisper` y corrige los nombres de los asistentes si sonaron parecido) y luego llama a `POST /api/chat`.
   - **Manos libres en la PC (`voice_listener.py`):** escucha el micrófono de la PC continuamente; cuando oye el nombre de un asistente (o se mantiene apretada su tecla de *push-to-talk*), manda la frase a la pestaña activa mediante `/api/voice/events`.
   - **Manos libres en otros dispositivos (`features.js`):** usa `SpeechRecognition` del navegador para detectar el nombre del asistente sin mandar audio hasta que lo llaman.

2. **Ruteo grupal (`POST /api/chat/route`):** si hay varios asistentes en la conversación (o se nombró a otro que comparte `base_model`), el modelo decide a quién(es) le habló el usuario, o si fue una pregunta para todos (ronda de opiniones).

3. **Armado del contexto y herramientas (`config_ui._chat_request` + `chat_runtime.chat`):**
   - Junta `personality` del asistente + `shared_context` + datos del usuario (`user_context` del perfil activo) + fecha/hora actual + estilo de respuesta (escrito con Markdown o hablado en prosa limpia).
   - Agrega el contexto dinámico de `app/core/skills.py`: recuerdos relevantes del perfil, recordatorios pendientes, rutinas que coincidan, trozos relevantes de los documentos del asistente (RAG) e instrucciones de los plugins activos (p. ej. ComfyUI con las imágenes disponibles en el chat y en la biblioteca del perfil).
   - Reúne las herramientas permitidas para el rol del perfil: `web_search`, `get_weather`, `find_nearby_places`, `find_place`, `play_music`, `convert_file` (con acceso a los archivos de la conversación actual **y de cualquier otro chat del mismo perfil** vía `dashboard.list_profile_files`), ` invite/remove_from_conversation`, memoria, recordatorios, listas, documentos, plugins (`generate_image`, `edit_image`, `generate_video`, Home Assistant, control de PC…) y servidores MCP.

4. **Respuesta en streaming (`assistant_common.ask_with_tools`):**
   - Llama a Ollama (`/api/chat` con `stream: True`). Si el modelo pide herramientas, las ejecuta (hasta `max_tool_rounds` rondas), emite avisos a la interfaz (`event`) y vuelve a consultar al modelo.
   - A medida que salen palabras (`delta`), `SpeechChunker` corta frases completas y en modo voz sintetiza el audio de cada frase en paralelo (`say` con el WAV en base64) para que el asistente empiece a hablar sin esperar al final de la respuesta.

---

## Vistas y navegación de la interfaz web (`index.html` + `app.js` + `features.js`)

La SPA usa rutas hash (`location.hash`):

- **`#/` (`kind: "gallery"`):** Pantalla principal tras iniciar sesión en un perfil:
  - **Dashboard de uso (`renderDashboardSection` en `features.js` + `GET /api/dashboard` en `dashboard.py`):** muestra bienvenida personalizada, botones de acceso rápido a **Imágenes y videos generados (`#/media`)** y **Archivos generados (`#/files`)**, 4 tarjetas KPI (conversaciones/mensajes/palabras, renders y tiempo de GPU en ComfyUI, archivos convertidos/adjuntos y memoria/productividad), gráfico de actividad por asistente y tiras de creaciones/archivos recientes.
  - **Galería de asistentes:** tarjetas de todos los asistentes visibles para el perfil (hablar por texto, hablar por voz, configurar, crear asistente nuevo o importar `.auravox`).
- **`#/media` (`kind: "media"`):** Biblioteca de todas las imágenes, ediciones y videos generados en el perfil, con búsqueda por texto/prompt/asistente, filtro por tipo (`all`, `image`, `edit`, `video`), filtro por fechas (hoy, 7 días, 30 días, desde/hasta), ordenamiento por fecha/nombre/tamaño, visor lightbox con zoom y navegación (`openMediaLightbox`) y botón **"Usar en chat"** (`useLibraryItemInChat`).
- **`#/files` (`kind: "files"`):** Biblioteca de todos los archivos generados, convertidos y adjuntados/transcritos en el perfil, con búsqueda, filtro por origen/tipo, filtro por fechas, ordenamiento, modal de previsualización (`openFilePreviewModal` + `GET /api/files/<id>/preview` para PDF, audio con transcripción, imagen, video, Word, Excel, PowerPoint, código y texto) y botón **"Usar en chat"**.
- **`#/a/<nombre>` (`kind: "assistant"`):** Escenario de conversación (modo texto y modo voz con orbe animado) + panel lateral plegable de configuración del asistente organizado por pestañas de categoría (`Identidad`, `Cerebro`, `Voz e idiomas`, `Activación`, `Documentos`, `Exportar`).
- **`#/new` (`kind: "new"`):** Creación de un nuevo asistente.
- **`#/shared` (`kind: "shared"`):** Ajustes compartidos y de cuenta organizados en un menú lateral de categorías (y cuadrícula adaptable en móvil) que muestra una sola categoría activa a la vez (`selectSettingsCat`):
  - `profile`: Perfil propio (`myProfileCard`: nombre, rol, acceso rápido a seguridad) y ubicación/coordenadas (`you-card` + mapa Leaflet).
  - `security`: **Contraseña y seguridad (`mySecurityCard`)**: permite establecer o cambiar la contraseña/PIN del perfil **sin pedir la contraseña anterior**, exigiendo confirmación en dos campos (`me.pin` y `me.pin_confirm`) y validando formato (`4–64` caracteres sin espacios). Los perfiles no administradores también pueden quitar su contraseña desde aquí.
  - `memory`: Memoria a largo plazo, recordatorios/alarmas y rutinas.
  - `models`: Estado/actualización de Ollama y gestión/descarga de modelos de IA.
  - `voice` *(admin)*: Reconocimiento Whisper, voces clonadas con Qwen3-TTS y palabras excluidas.
  - `rules` *(admin)*: Reglas compartidas (`shared_context`) y administración de perfiles de usuario.
  - `plugins` *(admin)*: Plugins integrados/externos, panel de ComfyUI y servidores MCP.
  - `system` *(admin)*: Acceso en red local (QR/HTTPS), diagnóstico del sistema y copias de seguridad.
- **`#/lists` (`kind: "lists"`):** Vista de listas y notas personales y del hogar.
- **`#/diag` (`kind: "diag"`):** Vista completa de diagnóstico del sistema.

---

## Referencia transversal de archivos y medios entre chats de un mismo perfil

Cualquier contenido generado (imágenes/videos de ComfyUI, archivos convertidos con `convert_file`) o subido (documentos, PDFs, hojas de cálculo, audios transcritos, imágenes) dentro de un perfil puede usarse en **cualquier otro chat de ese mismo perfil**:

1. **Desde la interfaz del chat (`openLibraryPickerModal` en `features.js` + `attachLibraryItemToChat` en `app.js`):**
   - El cuadro de texto del chat y el modo voz incluyen el botón **Biblioteca del perfil** (`data-chat-act="library"`, icono de carpeta, tanto en la barra como en el menú `+`).
   - Abre un selector modal con buscador y filtros por tipo que lista todas las imágenes, videos, audios y documentos del perfil. Al elegir uno, se adjunta a `CHAT.attachments` reutilizando su URL `/api/files/<id>` (sin duplicar el archivo en disco), preparando la imagen en base64 para modelos con visión o reutilizando el texto/transcripción ya extraído.
   - En `#/media`, `#/files` y en los modales de vista previa, cada elemento tiene el botón **"Usar en chat"** (`useLibraryItemInChat`), que permite elegir con qué asistente abrir la conversación llevando el archivo ya adjunto en la bandeja.
2. **Desde las herramientas del backend (`_conversation_files` en `config_ui.py` + `list_profile_files` en `dashboard.py`):**
   - En cada turno de `/api/chat`, `_conversation_files` combina los archivos de todos los chats y trabajos de ComfyUI del mismo perfil (`owner`) con los del chat actual (dejando los del chat actual al final como más recientes).
   - Así, herramientas como `edit_image`, `generate_video` y `convert_file` pueden operar sobre archivos e imágenes creados o subidos con otro asistente del mismo perfil cuando el usuario los menciona.

---

## Publicación en Git y privacidad de datos (`.gitignore`)

- `.gitignore` excluye **todos** los archivos con datos personales o generados por el usuario:
  - `config/assistants.yaml`, `config/voice_settings.yaml`, `config/spotify_config.yaml`, `config/profiles.json`, `config/reminders.json`, `config/mcp.json`, `config/plugins.json`, `config/network.json`, `config/voice_listener.json`, `config/model_memory.json`, `config/model_updates.json`, `config/*.bak`.
  - Carpetas completas: `config/chats/`, `config/comfyui/`, `config/custom_voices/`, `config/memory/`, `config/lists/`, `config/routines/`, `config/knowledge/`, `config/certs/`.
  - Audios generados (`audio/*.wav`, `audio/voice_previews/*/custom-*`), respaldos (`backups/`, `*.auravox`), registros (`logs/`), cachés (`cache/`) y el entorno local (`python/`).
- En el repositorio solo se versionan las plantillas limpias (`config/assistants.example.yaml`, `config/voice_settings.example.yaml`, `config/spotify_config.example.yaml`), `config/languages.txt` y `config/wake_words.txt`.

---

## Convenciones clave del código (para cualquier IA colaboradora)

- **Todo el código y los comentarios están en español claro**; los *prompts* internos que van al LLM están en inglés porque los modelos chicos los obedecen mejor, pero la respuesta sale siempre en el idioma del usuario.
- **La interfaz es bilingüe (español e inglés):** cualquier texto visible nuevo debe agregarse tanto en `STRINGS.es` como en `STRINGS.en` dentro de `app/webui/static/i18n.js` (y en `app/webui/i18n.py` si es un mensaje de error o estado del servidor).
- **Sin dependencias pesadas nuevas:** en el servidor se prioriza la librería estándar de Python; en el navegador, JS/CSS vanilla sin paso de compilación (*build step*).
- **Escritura atómica de archivos:** las configuraciones y JSON se escriben en un `.tmp` y se reemplazan con `os.replace` bajo un `threading.RLock` para no corromper nada si se corta la luz o concurren dos peticiones.
- **Separación por perfil (`owner`):** el administrador original tiene `owner = ""` (compatible con instalaciones de un solo usuario); cada perfil no administrador tiene su `id` (`"p" + 8 hex`) como `owner` para sus asistentes privados, chats, memoria, recordatorios, listas, rutinas y trabajos de ComfyUI; el invitado (`guest`) guarda sus cosas temporales en `sessionStorage` del navegador.
- **Diseño móvil (`style.css`):** todos los contenedores Grid/Flex dentro de `#/shared`, `#/media`, `#/files` y el chat deben mantener `min-width: 0` y colapsar `.grid-2` / `.grid-3` a una columna en pantallas `<= 720px` para evitar desbordamiento horizontal en celulares.
