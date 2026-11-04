"""
Lo que la interfaz web (config_ui.py) necesita para HABLAR y ESCUCHAR:
síntesis de voz (muestras de cada voz y respuestas del chat), transcripción
del micrófono del navegador y la conversación con el modelo — con la misma
lógica que usa voice_loop.py (ask_with_tools, herramientas, filtros de
Whisper, conversión de números...).

Todo se carga recién cuando hace falta (la primera muestra que no esté en
disco, el primer mensaje de chat, la primera vez que se habla por el
micrófono) y se puede liberar con unload(). Hay UN solo modelo Supertonic
(el compartido de supersonictts.shared_tts, en GPU si se puede) y solo
cambia el estilo de voz; y UN solo Whisper, que usan tanto el micrófono del
navegador como la escucha manos libres del servidor (voice_listener.py).

Cada paso deja una línea en la consola de la interfaz (server_log): cuánto
tardó Ollama, qué herramienta usó, en qué dispositivo y con qué RTF se
sintetizó cada trozo de voz, etc.
"""
import collections
import gc
import io
import json
import os
import threading
import time

import numpy as np
import soundfile as sf

from app import paths
from app.core import assistant_common
from app.core.assistant_common import (
    SERVER_KEEP_ALIVE,
    ask_with_tools,
    load_user_context,
    pipeline_languages,
    render_transcript,
    structured_request,
    unload_ollama_model,
)
from app.webui.server_log import log

PREVIEWS_DIR = paths.VOICE_PREVIEWS_DIR

# Lo que dice cada muestra de voz, por idioma de la interfaz.
PREVIEW_TEXT = {
    "es": "Esto es una muestra de esta voz. Puedes usarla para el modelo que desees.",
    "en": "This is a sample of this voice. You can use it for any model you want.",
}

# Cuánto se queda cargado el modelo de Ollama tras un mensaje del chat web:
# sin límite por defecto, configurable con AURAVOX_KEEP_ALIVE (ver
# assistant_common._keep_alive_setting). Con 15 min, tras una pausa la
# primera respuesta pagaba la recarga del modelo.
CHAT_KEEP_ALIVE = SERVER_KEEP_ALIVE

# Audios ya sintetizados (texto, voz, velocidad, idioma) → WAV: repetir una
# respuesta o el anuncio de búsqueda no vuelve a generarlos.
_TTS_CACHE_SIZE = 200
_tts_cache = collections.OrderedDict()

_tts_lock = threading.Lock()  # la caché y los estilos (la síntesis usa supersonictts.SYNTH_LOCK)
_tts = None
_tts_device = ""
_styles = {}
_stt_lock = threading.Lock()
_stt = None


def _short(text: str, n: int = 60) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


# ── Voz (Supertonic) ───────────────────────────────────────────────────

def _load_tts():
    global _tts, _tts_device
    if _tts is None:
        from app.voice.supersonictts import shared_tts

        t0 = time.time()
        _tts, device, reason = shared_tts()
        _tts_device = device
        log("voice", f"Supertonic ready in {time.time() - t0:.1f}s — {reason}", "info" if device == "GPU" else "warn")
    return _tts


def _synthesize_custom(text: str, voice: dict, lang: str, wait: bool = False) -> bytes:
    """WAV con una voz clonada (Qwen3-TTS, en su propio proceso)."""
    import tempfile

    from app.voice.qwen_tts import engine

    fd, tmp = tempfile.mkstemp(suffix=".wav", dir=paths.AUDIO_DIR)
    os.close(fd)
    try:
        reply = engine().synthesize(text, voice, lang, tmp, wait=wait)
        with open(tmp, "rb") as f:
            data = f.read()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    log("voice", f"{voice['code']} [{lang}] with Qwen3-TTS on {engine().device}: {reply['seconds']:.2f}s for "
                 f"{reply['audio_seconds']:.1f}s of audio (RTF {reply['seconds'] / max(reply['audio_seconds'], 0.01):.2f}) "
                 f"«{_short(text)}»")
    return data


def synthesize(text: str, voice: str, speed: float = 1.0, lang: str = "es", wait: bool = False) -> bytes:
    """Devuelve un WAV (bytes) con `text` dicho por `voice`: una voz de
    Supertonic ("M5") o una clonada ("custom:<id>", con Qwen3-TTS; en los
    idiomas que no habla, o si no está disponible, su voz de respaldo)."""
    from supertonic.config import AVAILABLE_LANGUAGES
    from app.core import voice_settings
    from app.voice.qwen_tts import speaks
    from app.voice.supersonictts import CONFIG, SYNTH_LOCK, _VARIATION_SELECTORS_RE, _numbers_to_words

    custom = voice_settings.get_voice(voice) if voice_settings.is_custom(voice) else None
    key = (text, voice, custom["stamp"] if custom else "", round(float(speed), 2), lang)
    with _tts_lock:
        if key in _tts_cache:
            _tts_cache.move_to_end(key)
            log("voice", f"cached, no regeneration: «{_short(text)}»")
            return _tts_cache[key]

    if voice_settings.is_custom(voice):
        if custom and speaks(lang):
            try:
                data = _synthesize_custom(_VARIATION_SELECTORS_RE.sub("", text).strip(), custom, lang, wait)
                with _tts_lock:
                    _tts_cache[key] = data
                    while len(_tts_cache) > _TTS_CACHE_SIZE:
                        _tts_cache.popitem(last=False)
                return data
            except Exception as e:  # noqa: BLE001 — sin la voz clonada, que al menos hable
                from app.voice.qwen_tts import WarmingUp

                if isinstance(e, WarmingUp):
                    log("voice", f"cloned voice {voice} warming up; speaking with fallback voice in the meantime")
                else:
                    log("voice", f"cloned voice {voice} unavailable ({e}); using fallback voice", "warn")
        voice = custom["fallback_voice"] if custom else "M5"

    tts_lang = lang if lang in AVAILABLE_LANGUAGES else "na"
    clean = _numbers_to_words(_VARIATION_SELECTORS_RE.sub("", text).strip(), tts_lang)
    with _tts_lock:
        model = _load_tts()
        if voice not in _styles:
            _styles[voice] = model.get_voice_style(voice)
        with SYNTH_LOCK:
            t0 = time.time()
            wav, _ = model.synthesize(
                text=clean,
                voice_style=_styles[voice],
                total_steps=CONFIG["total_steps"],
                speed=speed,
                silence_duration=CONFIG["silence_duration"],
                lang=tts_lang,
            )
            seconds = time.time() - t0
        samplerate = model.sample_rate
        audio = np.asarray(wav, dtype=np.float32).reshape(-1)
        buf = io.BytesIO()
        sf.write(buf, audio, samplerate, format="WAV", subtype="PCM_16")
        data = buf.getvalue()
        _tts_cache[key] = data
        while len(_tts_cache) > _TTS_CACHE_SIZE:
            _tts_cache.popitem(last=False)
    audio_seconds = len(audio) / samplerate
    log("voice", f"{voice} [{lang}] on {_tts_device}: {seconds:.2f}s for {audio_seconds:.1f}s of audio "
                 f"(RTF {seconds / max(audio_seconds, 0.01):.2f}) «{_short(text)}»")
    return data


def ensure_preview(lang: str, voice: str) -> str:
    """Ruta de la muestra de `voice` en `lang` (audio/voice_previews/<lang>/
    <voz>.wav); la genera y la guarda la primera vez que se pide. Las de las
    voces clonadas llevan la marca de la voz en el nombre (si se cambia el
    audio o el texto de referencia, se genera otra)."""
    from app.core import voice_settings

    if voice_settings.is_custom(voice):
        custom = voice_settings.get_voice(voice)
        if not custom:
            raise FileNotFoundError(voice)
        path = os.path.join(PREVIEWS_DIR, lang, f"custom_{custom['id']}_{custom['stamp']}.wav")
    else:
        path = os.path.join(PREVIEWS_DIR, lang, f"{voice}.wav")
    if not os.path.isfile(path):
        # La muestra de una voz clonada espera a que el modelo esté listo.
        data = synthesize(PREVIEW_TEXT[lang], voice, 1.0, lang, wait=True)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        log("voice", f"preview saved: {os.path.relpath(path, paths.ROOT)}")
    return path


# ── Oído (Whisper) ─────────────────────────────────────────────────────

def _ensure_stt():
    """Whisper cargado (llamar con _stt_lock tomado), el que esté elegido en
    Ajustes compartidos (voice_settings.stt_model): si se cambió, se
    recarga."""
    global _stt
    from app.core import voice_settings
    from app.voice import stt_whisper

    wanted = voice_settings.stt_model()
    if _stt is not None and _stt.config["model_size"] != wanted:
        log("stt", f"switching Whisper model: {_stt.config['model_size']} → {wanted}")
        _stt = None
        gc.collect()
    if _stt is None:
        t0 = time.time()
        _stt = stt_whisper.WhisperSTT({**stt_whisper.CONFIG, "model_size": wanted})
        _stt._load()
        device = getattr(_stt._model.model, "device", "?")
        log("stt", f"Whisper ({wanted}) loaded on {device} in {time.time() - t0:.1f}s")
    return _stt


def load_stt() -> None:
    """Carga Whisper ya (la escucha manos libres lo hace al arrancar, para
    que la primera frase no espere la carga)."""
    with _stt_lock:
        _ensure_stt()


def transcribe_array(audio, languages, hint: str = None, source: str = "stt") -> tuple:
    """Audio (numpy float32 mono a 16 kHz) → (texto, idioma, detección
    clara). Solo elige entre `languages` (vacío = todos los del pipeline),
    igual que voice_loop.py con los idiomas del asistente. `hint`: el idioma
    en que va la conversación (desempata si Whisper duda)."""
    from app.voice import stt_whisper

    with _stt_lock:
        stt = _ensure_stt()
        t0 = time.time()
        text, lang = stt.transcribe(audio, hint=hint, languages=set(languages or pipeline_languages()))
        detail, confident = stt.last_detail, stt.last_confident
    log(source, f"{len(audio) / stt_whisper.CONFIG['samplerate']:.1f}s of audio → [{lang}] «{_short(text) or '(empty)'}» "
                f"in {time.time() - t0:.2f}s — language: {detail}")
    return text.strip(), lang, confident


def transcribe(data: bytes, languages, hint: str = None) -> tuple:
    """Audio grabado en el navegador (webm/ogg/wav, lo decodifica PyAV) →
    (texto, idioma). Ver transcribe_array."""
    from faster_whisper import decode_audio
    from app.voice import stt_whisper

    audio = decode_audio(io.BytesIO(data), sampling_rate=stt_whisper.CONFIG["samplerate"])
    text, lang, confident = transcribe_array(audio, languages, hint)
    transcribe.last_confident = confident
    return text, lang


def transcribe_file(data: bytes, name: str = "") -> tuple:
    """Un audio adjunto (mp3, m4a, wav, ogg, flac, opus, webm, o el audio de
    un video; lo decodifica PyAV) → (texto, idioma, segundos). Puede durar
    lo que sea y estar en cualquier idioma (no solo los del asistente):
    Whisper lo detecta. Un salto de línea donde hay una pausa larga."""
    from faster_whisper import decode_audio
    from app.voice import stt_whisper

    rate = stt_whisper.CONFIG["samplerate"]
    audio = decode_audio(io.BytesIO(data), sampling_rate=rate)
    seconds = len(audio) / rate
    with _stt_lock:
        stt = _ensure_stt()
        stt._load()
        t0 = time.time()
        segments, info = stt._model.transcribe(audio, language=None, vad_filter=True, condition_on_previous_text=True)
        parts, last_end = [], None
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            if parts:
                parts.append("\n" if last_end is not None and seg.start - last_end > 1.5 else " ")
            parts.append(text)
            last_end = seg.end
    text = "".join(parts).strip()
    log("attachment", f"audio «{name}» ({seconds:.0f}s) → [{info.language} {info.language_probability:.2f}] "
                      f"{len(text)} chars in {time.time() - t0:.1f}s: «{_short(text)}»")
    return text, info.language, seconds


# ── Conversación (Ollama) ──────────────────────────────────────────────

def _refresh_user_context() -> None:
    """USER_CONTEXT se lee una vez al importar assistant_common; si cambió
    desde la interfaz (Ajustes compartidos), se actualiza en el lugar para
    que el chat use los datos nuevos sin reiniciar el servidor."""
    from app.tools import nearby_places

    fresh = load_user_context()
    if fresh != assistant_common.USER_CONTEXT:
        assistant_common.USER_CONTEXT.clear()
        assistant_common.USER_CONTEXT.update(fresh)
        assistant_common._resolved_location_cache = None
        nearby_places._home_coords_cache = None


def _log_event(label: str):
    def on_event(kind: str, d: dict) -> None:
        if kind == "round":
            load = f", {d['load_seconds']:.1f}s loading model" if d["load_seconds"] >= 0.5 else ""
            prompt = f", {d['prompt_seconds']:.1f}s prompt eval" if d.get("prompt_seconds", 0) >= 0.3 else ""
            who = "API" if d.get("remote") else "Ollama"
            log("chat", f"{label}: {who} round {d['n']} in {d['seconds']:.1f}s{load}{prompt} ({d['tokens'] or 0} tokens)")
            if not d.get("remote"):
                _warn_if_gpu_full(label, d["seconds"] - d["load_seconds"], d["tokens"])
        elif kind == "retry":
            extra = f": «{_short(d['text'])}»" if d["text"] else ""
            log("chat", f"{label}: retry — {d['reason']}{extra}", "warn")
        elif kind == "tool":
            log("tool", f"{d['name']}({json.dumps(d['arguments'], ensure_ascii=False)})")
        elif kind == "review":
            log("chat", f"{label}: review in {d['seconds']:.1f}s — tool: {d.get('needed_tool')}, "
                        f"problem: {d.get('draft_problem')}, language: {d.get('draft_language')} "
                        f"(«{_short(d.get('reasoning', ''), 100)}»)")
        elif kind == "precheck":
            log("chat", f"{label}: parallel precheck in {d['seconds']:.1f}s — tool: "
                        f"{d.get('needed_tool')} («{_short(d.get('reasoning', ''), 100)}»)")
        elif kind == "review_skipped":
            log("chat", f"{label}: draft review skipped (no tool needed and language is fixed)")
        elif kind == "fallback":
            log("chat", f"{label}: exhausted {d['rounds']} tool rounds; returning fallback message", "warn")
    return on_event


# ── Convertir archivos (ver app/core/converters.py) ───────────────────
# Solo se ofrece cuando la conversación tiene archivos (adjuntos o que ya
# mandó el asistente); el modelo elige cuál y a qué formato. El resultado se
# guarda como adjunto (file_store) y la página lo muestra para descargarlo.
CONVERT_TOOL = "convert_file"


def convert_tool(files: list) -> dict:
    names = list(dict.fromkeys(f["name"] for f in files))
    return {
        "type": "function",
        "function": {
            "name": CONVERT_TOOL,
            "description": (
                "Convert a file of this conversation or from another chat in the user's profile library (one the user "
                "attached, generated or that you already sent) to another format and send the result to the user to "
                "download: e.g. a Word .docx to PDF, a .csv to Excel (.xlsx), an Excel sheet to .csv or PDF, a "
                "PowerPoint to PDF, a .jpg to .png or .webp, a .wav to .mp3, a video to .mp4 or .gif. Use it only "
                "when the user asks to convert, export or save a file in another format."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "enum": names, "description": "Which file to convert."},
                    "to": {"type": "string", "description": "Target format, as a file extension: pdf, docx, xlsx, csv, png, jpg, webp, mp3…"},
                },
                "required": ["file", "to"],
            },
        },
    }


def _convert_result(arguments: dict, files: list, on_file) -> str:
    import shutil

    from app.core import converters
    from app.webui import file_store

    wanted = str(arguments.get("file") or "").strip()
    q = wanted.lower()
    match = (
        [f for f in files if f["name"] == wanted]
        or [f for f in files if f["name"].lower() == q]
        or ([f for f in files if q in f["name"].lower()] if q else [])
    )
    if not match:
        return f'There is no file called "{wanted}" in this conversation or profile library. Available: {", ".join(f["name"] for f in files)}.'
    src = match[-1]  # el más reciente con ese nombre
    found = file_store.open_file(src["id"])
    if not found:
        return f'The original of "{wanted}" is no longer available: ask the user to attach it again.'
    target = converters.norm_ext(arguments.get("to"))
    try:
        out = converters.convert(found[0], src["name"], target)
    except converters.ConversionError as e:
        log("tool", f"convert_file: «{src['name']}» → {target}: {e}", "warn")
        return f"Couldn't convert it: {e}. Tell the user plainly, in one sentence."
    try:
        with open(out, "rb") as f:
            data = f.read()
        saved = file_store.save(os.path.basename(out), data)
    finally:
        shutil.rmtree(os.path.dirname(out), ignore_errors=True)
    name = os.path.basename(out)
    if on_file:
        on_file({"name": name, "url": saved["url"], "size": len(data), "from": src["name"]})
    size = f"{len(data) / 1024:.0f} KB" if len(data) < 1024 ** 2 else f"{len(data) / 1024 ** 2:.1f} MB"
    return (f'Done: "{src["name"]}" was converted to "{name}" ({size}). The user already sees it in the chat '
            "with a button to download it: just tell them briefly that it's ready (don't write a link or a path).")


# ── Conversación grupal: invitar/sacar asistentes ─────────────────────
# Son herramientas del modelo (no palabras clave): "Jarvis, invita a Bella",
# "¿puede venir Bella?", "Bella, déjanos solos", "Джарвис, позови Беллу"…
# el modelo entiende el pedido en cualquier idioma, llama la herramienta y
# responde con naturalidad; la página aplica el cambio (ver app.js).
INVITE_TOOL = "invite_to_conversation"
REMOVE_TOOL = "remove_from_conversation"


def group_tools(cfg: dict, me: str, participants: list, assistants: list) -> list:
    """Herramientas para armar la conversación. La lista es la de TODOS los
    asistentes guardados (no solo los que se pueden invitar): con una lista
    recortada, a "Jarvis, invita a Jarvis" el modelo elegía al único que
    quedaba (se metía Ziggy sin que nadie lo pidiera). La propia herramienta
    contesta "ya está en la conversación" o "usa otro modelo"."""
    labels = {a["name"]: (a.get("label") or a["name"]).upper() for a in assistants}
    everyone = list(labels)
    if not everyone:
        return []
    inside = [n for n in participants if n in labels]
    other_model = [a["name"] for a in assistants if a.get("base_model") != cfg["base_model"]]
    you = f" You are {me}." if me else ""
    status = (f"In the conversation now: {', '.join(labels[n] for n in inside) or '(only you)'}."
              + (f" Can't join (another model): {', '.join(labels[n] for n in other_model)}." if other_model else ""))
    return [
        {"type": "function", "function": {
            "name": INVITE_TOOL,
            "description": (
                "Bring another assistant into this conversation when the user asks for it, in any words. "
                f"{status}{you} Once in, it hears everything and answers when the user talks to it."
            ),
            "parameters": {"type": "object", "properties": {
                "assistant": {"type": "string", "enum": everyone, "description": "Who the user wants to bring in."},
            }, "required": ["assistant"]},
        }},
        {"type": "function", "function": {
            "name": REMOVE_TOOL,
            "description": (
                "Take an assistant out of this conversation when the user asks for it, in any words: another one, "
                f"or yourself if the user asks you to leave. {status}{you}"
            ),
            "parameters": {"type": "object", "properties": {
                "assistant": {"type": "string", "enum": everyone, "description": "Who the user wants to leave."},
            }, "required": ["assistant"]},
        }},
    ]


def _group_tool_result(name: str, who: str, cfg: dict, group: dict, on_group) -> str:
    """Aplica invitar/sacar (avisándole a la página) y le dice al modelo qué
    pasó. El que entra saluda y el que sale se despide él mismo después (ver
    app.js, applyGroupActions)."""
    saved = {a["name"]: a for a in group["assistants"]}
    a = saved.get(who)
    if not a:
        return f"There's no assistant called '{who}'."
    label = (a.get("label") or who).upper()
    inside = who in group["participants"] or who == group["me"]
    if name == INVITE_TOOL:
        if inside:
            return f"{label} is already in the conversation: nothing to do (tell the user so, briefly)."
        if a.get("base_model") != cfg["base_model"]:
            return f"{label} can't join: it runs on another model ({a.get('base_model')})."
        if on_group:
            on_group("invite", who)
        return f"{label} is joining the conversation and will greet everyone right after your reply: just confirm it in a few words."
    if not inside:
        return f"{label} isn't in the conversation: nothing to do (tell the user so, briefly)."
    if on_group:
        on_group("remove", who)
    if who == group["me"]:
        return "You're leaving the conversation right after this reply: say a short goodbye."
    return f"{label} will say goodbye and leave right after your reply: just confirm it in a few words."


# Turno de "llegué" / "me voy": lo pide la página justo después de invitar o
# sacar a un asistente, para que ESE asistente salude o se despida.
CUES = {
    "join": ("YOUR TURN NOW: you, {name}, have just joined this conversation because the user asked for you. Say hi "
             "to everyone, in your own style, in ONE short sentence. Don't talk about inviting anyone, don't do "
             "anything else and don't ask how you can help."),
    "leave": ("YOUR TURN NOW: you, {name}, are leaving this conversation right now because the user asked. Say a "
              "brief goodbye, in your own style, in ONE short sentence, and nothing else."),
}


def chat(cfg: dict, shared_context: str, history: list, reply_lang: str, on_tool_call=None, style: str = "text",
         auto_langs=None, on_places=None, group=None, on_group=None, cue: str = None, on_file=None,
         skill_ctx=None, on_text=None) -> tuple:
    """Una respuesta del asistente descrito por `cfg` (formato de
    config_store.assistant_view, puede ser un borrador sin guardar).
    Devuelve (texto, idioma de la respuesta).
    `style`: "text" (chat escrito, más detallado) o "voice" (conversación
    por voz, corto y natural). Sin `reply_lang`, responde en el idioma del
    mensaje del usuario entre `auto_langs` (el idioma en que salió lo dice
    el revisor de assistant_common).
    `on_places({"categoria", "origin", "places"})`: lugares encontrados por
    find_nearby_places, con coordenadas (para mostrarlos en un mapa).
    `group`: {"me", "participants", "assistants"} para poder invitar/sacar
    asistentes (ver group_tools); `on_group(acción, asistente)` avisa a la
    página.
    `cue`: "join"/"leave" (ver CUES): saludo o despedida, sin herramientas.
    `skill_ctx`: quién pregunta (app/core/skills.Ctx): suma las habilidades
    que dependen del perfil (memoria, recordatorios, listas, documentos…).
    `on_text(tipo, texto)`: la respuesta en streaming ("delta"/"reset", ver
    assistant_common.ask_with_tools)."""
    from app.core import skills
    from app.core.assistant_engine import OLLAMA_URL, TOOLS, call_tool
    from app.tools.nearby_places import locate_place, search_nearby

    label = (cfg.get("label") or cfg.get("name") or "?").upper()
    extra_tools = group_tools(cfg, group["me"], group["participants"], group["assistants"]) if group else []
    files = (group or {}).get("files") or []
    file_tools = [convert_tool(files)] if files and not cue else []
    if skill_ctx is not None:
        skill_ctx.history = history
        skill_ctx.call_base_tool = call_tool
        skill_ctx.files = files
    skill_tools = skills.tools_for(skill_ctx) if skill_ctx is not None and not cue else []
    # Con perfil, las herramientas de los plugins vienen con las habilidades
    # (según su rol mínimo); sin él (pruebas), todas las activadas.
    base_tools = [] if skill_ctx is not None else TOOLS
    tools = [] if cue else base_tools + extra_tools + file_tools + skill_tools
    group_names = {t["function"]["name"] for t in extra_tools}
    skill_names = {t["function"]["name"] for t in skill_tools}
    # Lo de las habilidades cambia en cada turno (memoria relevante a la
    # pregunta, recordatorios con lo que falta): va al final del system
    # prompt para no invalidar lo ya procesado por Ollama.
    dynamic_context = skills.context_for(skill_ctx) if skill_ctx is not None else ""
    if cue in CUES:
        shared_context = (shared_context + "\n\n" if shared_context else "") + CUES[cue].format(name=label)

    def logged_call_tool(name, arguments):
        t0 = time.time()
        if name in ("find_nearby_places", "find_place"):
            found = locate_place(arguments) if name == "find_place" else search_nearby(arguments)
            result = found["text"]
            if found["places"] and on_places:
                on_places({**{k: found[k] for k in ("categoria", "origin", "places")}, "kind": found.get("kind", "nearby")})
        elif name in group_names:
            result = _group_tool_result(name, str(arguments.get("assistant") or ""), cfg, group, on_group)
        elif name == CONVERT_TOOL:
            result = _convert_result(arguments, files, on_file)
        elif name in skill_names:
            try:
                result = skills.call(name, arguments, skill_ctx)
            except Exception as e:  # noqa: BLE001 — que el modelo lo cuente en vez de cortar la respuesta
                import traceback

                traceback.print_exc()
                result = f"The tool failed: {e}. Tell the user plainly, in one sentence."
            if result is None:
                result = f"Unknown tool {name}."
        else:
            result = call_tool(name, arguments)
        log("tool", f"{name} replied in {time.time() - t0:.1f}s: «{_short(result, 90)}»")
        return result

    _refresh_user_context()
    last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    mode = "voice" if style == "voice" else "text"
    lang_note = reply_lang or f"auto ({', '.join(auto_langs or [])})"
    what = f"[{cue}]" if cue else f"← «{_short(last_user)}»"
    log("chat", f"{label} ({cfg['base_model']}, lang {lang_note}, mode {mode}) {what}")
    t0 = time.time()
    info = {}
    first = {}

    def timed_text(kind, text):
        if kind == "delta" and "at" not in first:
            first["at"] = time.time() - t0
        elif kind == "reset":
            first.pop("at", None)
        on_text(kind, text)

    reply = ask_with_tools(
        OLLAMA_URL,
        cfg["base_model"],
        cfg["personality"],
        history[-cfg["max_history"]:],
        tools,
        logged_call_tool,
        max_tool_rounds=cfg["max_tool_rounds"],
        fallback_message=cfg["fallback_message"],
        on_tool_call=on_tool_call,
        reply_lang=reply_lang,
        shared_context=shared_context,
        temperature=cfg["temperature"],
        top_k=cfg["top_k"],
        top_p=cfg["top_p"],
        keep_alive=CHAT_KEEP_ALIVE,
        on_event=_log_event(label),
        style=style,
        auto_langs=auto_langs,
        info=info,
        assistant_name=label,
        on_text=timed_text if on_text else None,
        dynamic_context=dynamic_context,
    )
    shown = f", first token at {first['at']:.1f}s" if "at" in first else ""
    log("chat", f"{label} → reply in {time.time() - t0:.1f}s{shown} ({len(reply.split())} words): «{_short(reply, 90)}»")
    return reply, reply_lang or info.get("language") or cfg["language"]


# ── Resumen de chats largos ────────────────────────────────────────────
# Cuando la conversación pasa el historial del asistente (max_history), lo
# más viejo no se corta: el mismo modelo lo resume y el resumen va al
# system prompt. Así el asistente no pierde el hilo (nombres, datos, lo que
# se decidió) en charlas largas.
_SUMMARY_SYSTEM = """You condense the older part of a conversation between a user and an AI assistant called {name}, so the assistant can keep the thread after those messages are removed from its context.
Write a compact summary in the language the conversation is in. Keep what still matters: facts and data that were given (names, numbers, dates, places, files), what was asked and answered, decisions and plans, open questions or pending tasks, the user's preferences and mood, and any ongoing game, story or roleplay situation. Lines like "NAME (another assistant)" were said by other assistants in a group conversation: say who said what.
If there is a previous summary, merge it with the new messages into ONE summary (keep what still matters, drop what doesn't).
Plain text, no preamble, at most about 250 words."""


def summarize(cfg: dict, previous: str, messages: list):
    """Resumen de `messages` (lo más viejo de la conversación) unido al
    resumen anterior, o None si falló."""
    import requests

    from app.core import llm_remote
    from app.core.assistant_engine import OLLAMA_URL

    label = (cfg.get("label") or cfg.get("name") or "?").upper()
    transcript = render_transcript(messages, last=len(messages))
    prompt = (f"PREVIOUS SUMMARY:\n{previous}\n\n" if previous else "") + f"MESSAGES TO ADD TO THE SUMMARY:\n{transcript}"
    t0 = time.time()
    try:
        r = llm_remote.post(OLLAMA_URL, json={
            "model": cfg["base_model"], "think": False, "stream": False, "keep_alive": CHAT_KEEP_ALIVE,
            "options": {"temperature": 0.2, "num_predict": 700},
            "messages": [{"role": "system", "content": _SUMMARY_SYSTEM.format(name=label)},
                         {"role": "user", "content": prompt}],
        }, timeout=180)
        r.raise_for_status()
        text = (r.json()["message"].get("content") or "").strip()
    except (requests.exceptions.RequestException, ValueError, KeyError) as e:
        log("chat", f"{label}: could not summarize older messages ({e}); truncating instead", "warn")
        return None
    if not text:
        return None
    log("chat", f"{label}: summarized {len(messages)} older messages in {time.time() - t0:.1f}s "
                f"({len(text.split())} words): «{_short(text, 100)}»")
    return text[:8000]


SUMMARY_NOTE = ("SUMMARY OF THE EARLIER PART OF THIS CONVERSATION (those messages were condensed to save space; "
                "treat this as things you already know from this same conversation):\n{summary}")


# ── ¿A quién le habló el usuario? (conversación grupal) ────────────────
_ROUTE_SYSTEM = """A user is talking by voice with a group of assistants: {names}.
Decide who the user's LAST message (lines starting with USER) is addressed to, whatever language it is in:
- addressed: the assistants the user is speaking TO, called by their name (usually at the start or the end, like "Bella, what do you think?" or "and you, Jarvis?"). Talking ABOUT an assistant is not addressing it: neither "what do you think of what Jarvis said?" nor being the object of a request ("Jarvis, invite Bella" is addressed only to Jarvis).
- everyone: true if the user asks all of them at once, in any words ("everyone", "you two", "what do you all think?"...). Then put in "first" who should answer first, only if the user says so.
If nobody in particular is addressed, leave "addressed" empty.
Write "reasoning" first: one short sentence."""

# Un asistente que NO está en la conversación y al que se nombra: se pregunta
# aparte qué relación tiene el mensaje con él. Con un solo campo para todos,
# a "Invita a Jarvis a la conversación" el modelo contestaba siempre que se
# le hablaba a Jarvis (entraba él en vez de que lo invitaran); así, medido,
# acierta 22 de 22 (español, inglés, ruso; con y sin historial).
_OUTSIDER_SYSTEM = """A user is talking by voice with assistants. In the conversation now: {inside}.
Another assistant exists but is NOT in the conversation yet: {out}.
Classify how the user's LAST message (the last USER line), in whatever language it is in, relates to {out}:
- "spoken_to": the user talks directly TO {out}, as if it were already in the room ("{out}, what do you think?", "hi {out}", "bye {out}", "{out}, what time is it?").
- "bring_in_request": the user asks the assistants in the conversation to bring, invite, call or add {out} ("invite {out}", "invite {out} to the conversation", "can {out} come?", "bring {out}").
- "mentioned": {out} is only talked about.
- "not_mentioned".
Write "reasoning" first: one short sentence."""


def _outsider_relation(cfg: dict, transcript: str, inside: list, out: str):
    schema = {"type": "object", "properties": {
        "reasoning": {"type": "string"},
        "relation": {"type": "string", "enum": ["spoken_to", "bring_in_request", "mentioned", "not_mentioned"]},
    }, "required": ["reasoning", "relation"]}
    from app.core.assistant_engine import OLLAMA_URL

    return structured_request(OLLAMA_URL, cfg["base_model"], [
        {"role": "system", "content": _OUTSIDER_SYSTEM.format(inside=", ".join(inside), out=out)},
        {"role": "user", "content": transcript},
    ], schema, keep_alive=CHAT_KEEP_ALIVE) or {}


def route_addressees(cfg: dict, history: list, labels: dict, outsiders: dict = None) -> dict:
    """{"keys": [quiénes responden, en orden], "all": bool} según el
    modelo; {"keys": [], "all": False} si falló o no se le habló a nadie
    en particular (responde el de la página).
    `labels`: {clave: nombre en pantalla} de los participantes.
    `outsiders`: {clave: nombre} de asistentes que NO están en la
    conversación y se nombran en el mensaje: si el usuario le habla a uno
    ("Ziggy, ¿y tú qué opinas?", "Adiós, Ziggy"), vuelve solo ese en
    `keys` (la página lo suma); si pide que lo traigan ("invita a Ziggy"),
    no (lo resuelve la conversación con su herramienta de invitar)."""
    from app.core.assistant_engine import OLLAMA_URL

    outsiders = {k: v for k, v in (outsiders or {}).items() if k not in labels}
    transcript = render_transcript(history, last=6)
    inside = list(labels.values())
    for key, out in list(outsiders.items())[:2]:
        t0 = time.time()
        rel = _outsider_relation(cfg, transcript, inside, out)
        log("chat", f"group: {out} (not in room) → {rel.get('relation', '?')} in {time.time() - t0:.1f}s "
                    f"(«{_short(rel.get('reasoning', ''), 100)}»)")
        if rel.get("relation") == "spoken_to":
            return {"keys": [key], "all": False}
    if len(labels) < 2:
        return {"keys": [], "all": False}

    by_label = {label: key for key, label in labels.items()}
    names = list(by_label)
    schema = {
        "type": "object",
        "properties": {
            "reasoning": {"type": "string"},
            "addressed": {"type": "array", "items": {"type": "string", "enum": names}},
            "everyone": {"type": "boolean"},
            "first": {"type": "string", "enum": ["", *names]},
        },
        "required": ["reasoning", "addressed", "everyone", "first"],
    }
    t0 = time.time()
    data = structured_request(OLLAMA_URL, cfg["base_model"], [
        {"role": "system", "content": _ROUTE_SYSTEM.format(names=", ".join(names))},
        {"role": "user", "content": transcript},
    ], schema, keep_alive=CHAT_KEEP_ALIVE)
    if not data:
        log("chat", "group: could not determine addressee; defaulting to current page assistant", "warn")
        return {"keys": [], "all": False}
    keys = [by_label[n] for n in dict.fromkeys(data.get("addressed") or []) if n in by_label]
    first = by_label.get(data.get("first") or "")
    everyone = bool(data.get("everyone"))
    if everyone:
        keys = [first] if first else []
    log("chat", f"group: {'everyone' if everyone else ', '.join(labels[k] for k in keys) or '(nobody in particular)'}"
                f"{f', starting with {labels[first]}' if everyone and first else ''} in {time.time() - t0:.1f}s "
                f"(«{_short(data.get('reasoning', ''), 100)}»)")
    return {"keys": keys, "all": everyone}


def prewarm_voices() -> bool:
    """Si algún asistente usa una voz clonada, prepara Qwen3-TTS en segundo
    plano (con compilación tarda minutos: mejor que no le toque a la
    primera respuesta). True si empezó.
    Si ya ninguno la usa, cierra su proceso: ocupa ~2,8 GB de VRAM y, con
    un modelo de 12B cargado, la GPU se llenaba y todo iba 30 veces más
    lento (ver _warn_if_gpu_full)."""
    from app.core import config_store as store, voice_settings
    from app.voice.qwen_tts import engine

    if any(voice_settings.is_custom(a["voice"]) for a in store.load_state()["assistants"]):
        if engine().warm_up_async():
            log("voice", "warming up cloned voices in the background (using fallback voice in the meantime)")
            return True
    elif not engine().warming and engine().release():
        log("memory", "no assistant uses a cloned voice: closed Qwen3-TTS (freed its VRAM)")
    return False


def _gpu_memory():
    """(MiB en uso, MiB totales) de la GPU, o None."""
    import subprocess

    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.split(",")
        return int(float(out[0])), int(float(out[1]))
    except Exception:  # noqa: BLE001
        return None


def _warn_if_gpu_full(label: str, seconds: float, tokens: int) -> None:
    """Una ronda lenta para lo poco que generó suele ser la GPU llena: en
    Windows, cuando no entra todo, el driver pasa memoria a la RAM
    compartida y Ollama sigue diciendo "100% GPU" pero va decenas de veces
    más lento (visto con Nemo 12B: 55-68 s por ronda en vez de 1-2 s)."""
    if seconds < 12 or seconds / max(tokens or 1, 1) < 0.3:
        return
    mem = _gpu_memory()
    if mem and mem[0] > mem[1] * 0.92:
        log("chat", f"{label}: GPU VRAM is nearly full ({mem[0] / 1024:.1f} of {mem[1] / 1024:.1f} GB): Windows is spilling "
                    "into system RAM, slowing inference significantly. Close GPU-heavy apps or use a smaller model.",
            "warn")


def unload(ollama_models=()) -> None:
    """Libera Whisper, Supertonic y los modelos de Ollama indicados."""
    global _tts, _stt
    from app.voice.supersonictts import release_shared_tts

    for model in ollama_models:
        unload_ollama_model(model)
    with _tts_lock:
        had_tts = _tts is not None
        _tts = None
        _styles.clear()
        release_shared_tts()
    from app.voice.qwen_tts import engine as qwen_engine

    had_qwen = qwen_engine().release()
    with _stt_lock:
        had_stt = _stt is not None
        _stt = None
    gc.collect()
    freed = ([*ollama_models] + (["Supertonic"] if had_tts else []) + (["Whisper"] if had_stt else [])
             + (["Qwen3-TTS"] if had_qwen else []))
    if freed:
        log("memory", f"unloaded: {', '.join(freed)}")


def status() -> dict:
    return {"tts_loaded": _tts is not None, "tts_device": _tts_device, "stt_loaded": _stt is not None}
