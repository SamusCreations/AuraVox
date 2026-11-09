"""
Interfaz web para configurar los asistentes de assistants.yaml: crear,
editar, ver y borrar asistentes; elegir su voz (con muestras en español o
inglés), su modelo base de Ollama (y descargar otros), sus idiomas, su forma
de activación (nombre y/o push to talk) y el resto de parámetros; más los
ajustes compartidos (user_context, shared_context) y las palabras de
activación (wake_words.txt). Incluye un chat para probar cada asistente por
texto o por voz con la configuración que se está editando.

Además trae la escucha manos libres (voice_listener.py): con la página
abierta, se llama a cualquier asistente por su nombre (o su tecla de push to
talk) y la página abre su conversación por voz; también se invita/saca a
otros asistentes por voz. El micrófono se silencia desde la barra superior.

Ejecutar:
    AuraVox.bat
    python config_ui.py [--port 8765] [--no-browser] [--no-voice]

Solo usa la librería estándar de Python para el servidor (http.server) y
solo escucha en 127.0.0.1. Los cambios de configuración se aplican la
próxima vez que arranquen voice_loop.py o el modo texto (la escucha manos
libres los toma sola). Supertonic se carga en este proceso recién al usar
el chat o generar una muestra de voz que falte, y Whisper al abrir la
página (ver chat_runtime.py).
"""
import argparse
import json
import mimetypes
import os
import re
import socket
import ssl
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlsplit

import time

import requests

# Ejecutado como script (los .bat): la raíz del proyecto va al path para
# poder importar el paquete `app` (el Python embebido no lo agrega solo).
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Todo lo que se imprima desde aquí (también Whisper/Supertonic) queda además
# en la consola de la página (panel "Consola", ver server_log.py).
from app.webui import server_log

server_log.install()

from app import paths
from app.core import assistant_common
from app.core import config_store as store
from app.core import llm_remote, hf_hub, secrets_store
from app.voice import wake_word_utils as ww
from app.webui import chat_runtime, chat_store, dev_reload, file_store, i18n, model_updates, network, ollama_update
from app.webui import profiles
from app.core import skills
from app.skills import knowledge, lists, memory, reminders, routines
from app.webui import notify
from app.webui import assistant_io
from app.webui import backup
from app.webui import dashboard
from app.webui.voice_listener import VoiceListener
from app.core import voice_settings
from app.voice import voice_reference
from app.core import attachments
from app.core.assistant_common import (
    VALID_VOICE_CODES,
    is_valid_voice,
    normalize_voice,
    _INT_DEFAULTS,
    _NUMERIC_DEFAULTS,
    _TEXT_DEFAULTS,
    pipeline_languages,
)
from app.webui.i18n import tr
from app.voice.push_to_talk import KEY_CODES

# Versión del contrato entre este servidor y webui/app.js. Si la página
# recibe otra (un servidor viejo que quedó abierto), avisa en vez de
# funcionar a medias. Súbela al cambiar el formato de /api/state o de las
# rutas.
API_VERSION = 10

# Escucha manos libres (ver voice_listener.py): se crea en main().
LISTENER = VoiceListener(enabled=False)
CLIENT_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
PLUGIN_HTTP_RE = re.compile(r"/api/plugin/([a-z0-9_]{2,40})/([a-z0-9_]{1,40})")

OLLAMA_URL = "http://127.0.0.1:11434"
WEBUI_DIR = paths.WEBUI_STATIC_DIR
DEFAULT_PORT = 8765
MAX_BODY = 1_000_000
MAX_AUDIO = 25_000_000
# Adjuntos del chat escrito (ver _group_history y app/core/attachments.py).
MAX_CHAT_BODY = 40_000_000     # /api/chat: el historial puede traer imágenes
MAX_AUDIO_FILE = 150_000_000   # un audio adjunto para pasar a texto
MAX_VOICE_AUDIO = 300_000_000  # audio largo para clonar una voz
MAX_IMAGES = 4                 # por mensaje
# Mensajes con imágenes que el modelo sigue viendo. Con 2, al describir una
# imagen nueva mezclaba detalles de la anterior (que seguía en el contexto).
IMAGE_TURNS = 1
FILE_TURNS = 2                 # mensajes con archivos que conservan todo su texto
OLD_FILE_CHARS = 1500          # de los más viejos queda el principio
MAX_MESSAGE_CHARS = 32_000     # texto total de los adjuntos de un mensaje
B64_RE = re.compile(r"^[A-Za-z0-9+/=\s]+$")
MODEL_NAME_RE = re.compile(r"^[\w.\-/:]{1,200}$")
PREVIEW_RE = re.compile(r"^/previews/([a-z]{2})/([FM][1-5]|custom-[a-z0-9][a-z0-9_-]{0,39})\.wav$")
VOICE_AUDIO_RE = re.compile(r"^/voices/([a-z0-9][a-z0-9_-]{0,39})\.wav$")

_LANGUAGES = []  # se calcula una vez al arrancar (importar faster_whisper tarda un poco)


def _meta() -> dict:
    voices = [
        {"code": code, "gender": "female" if code.startswith("F") else "male"}
        for code in sorted(VALID_VOICE_CODES, key=lambda c: (c[0] != "F", c))
    ]
    limits = {k: {"default": d, "min": lo, "max": hi, "int": False} for k, (d, lo, hi) in _NUMERIC_DEFAULTS.items()}
    limits.update({k: {"default": d, "min": lo, "max": hi, "int": True} for k, (d, lo, hi) in _INT_DEFAULTS.items()})
    return {
        "api_version": API_VERSION,
        "languages": _LANGUAGES,
        "voices": voices,
        "limits": limits,
        "text_defaults": _TEXT_DEFAULTS,
        "wake_ratio": ww.DEFAULT_RATIO,
        "ptt_keys": list(KEY_CODES),
        "preview_languages": list(chat_runtime.PREVIEW_TEXT),
        "voice_listener": LISTENER.enabled,
        "voice_settings": _voice_settings_state(),
    }


def _voice_settings_state() -> dict:
    """Ajustes de voz compartidos (Whisper, Qwen3-TTS) y voces clonadas."""
    from app.voice.qwen_tts import QWEN_LANGUAGES, engine

    data = voice_settings.load()
    voices = []
    for v in data["custom_voices"]:
        full = voice_settings.get_voice(v["id"])
        voices.append({**v, "code": voice_settings.CUSTOM_PREFIX + v["id"], "stamp": (full or {}).get("stamp", ""),
                       "missing_audio": full is None})
    return {
        "stt_model": data["stt_model"],
        "stt_models": voice_settings.STT_MODELS,
        "qwen_model": data["qwen_tts"]["model"],
        "qwen_models": list(voice_settings.QWEN_MODELS),
        "qwen_python": data["qwen_tts"]["python"],
        "qwen_compile": data["qwen_tts"]["compile"],
        "qwen_python_default": voice_settings.default_qwen_python(),
        "qwen": engine().status(),
        "qwen_languages": sorted(QWEN_LANGUAGES),
        "custom_voices": voices,
    }


# ── Perfiles y permisos (ver profiles.py) ──────────────────────────────

def can_see(a: dict, sess) -> bool:
    """Un asistente compartido lo ven todos; uno privado, solo quien lo creó."""
    return a["shared"] or (bool(sess) and not sess["guest"] and a["owner"] == sess["id"])


def can_edit(a: dict, sess) -> bool:
    """Quien lo creó, o un administrador si es compartido (o de antes de los
    perfiles, sin dueño). El invitado no cambia ninguno."""
    if not sess or sess["guest"]:
        return False
    if a["owner"] == sess["id"]:
        return True
    return sess["role"] == "admin" and (a["shared"] or not a["owner"])


def visible_assistants(sess) -> list:
    return [a for a in store.load_state()["assistants"] if can_see(a, sess)]


def build_state(sess) -> dict:
    state = store.load_state()
    names = {p["id"]: p["name"] for p in profiles.list_public()}
    assistants = []
    for a in state["assistants"]:
        if can_see(a, sess):
            assistants.append({**a, "editable": can_edit(a, sess), "mine": bool(sess) and a["owner"] == sess["id"],
                               "owner_name": names.get(a["owner"], "")})
    admin = bool(sess) and sess["role"] == "admin"
    me = {k: sess[k] for k in ("id", "name", "role", "color", "has_pin", "guest") if k in sess} if sess else None
    out = {**state, **_meta(), "assistants": assistants, "me": me,
           # Lo de assistants.yaml es de los modos de consola: en la página,
           # cada perfil ve los suyos (el invitado, los de su navegador).
           "user_context": _profile_user_context(sess)}
    if admin:
        out["profiles"] = profiles.list_public()
    return out


def _profile_user_context(sess) -> dict:
    uc = (sess or {}).get("user_context") or {}
    out = {k: str(uc.get(k) or "") for k in store.USER_TEXT_FIELDS}
    for k in ("latitud", "longitud"):
        out[k] = uc.get(k) if isinstance(uc.get(k), (int, float)) else None
    return out


# Qué rol hace falta para cada ruta. "public": sin perfil (elegir perfil,
# la página misma); "guest": cualquier sesión, también el invitado; "user":
# un perfil guardado (normal o admin); "admin": solo administradores.
def required_role(method: str, path: str) -> str:
    if method == "GET" and (path in ("/", "/index.html", "/sw.js", "/api/profiles", "/api/dev/version")
                            or path.startswith("/static/")):
        return "public"
    if path in ("/api/session", "/api/session/guest", "/api/profiles/setup"):
        return "public"
    if method == "GET":
        if path in ("/api/logs", "/api/network", "/api/plugins", "/api/mcp", "/api/diagnostics") or path.startswith(
                ("/api/backups", "/api/llm/", "/api/hf/")):
            return "admin"  # la consola muestra las conversaciones de todos; el estado de la red, la clave
        if re.fullmatch(r"/api/chats/[a-z0-9_]{1,40}", path) or path == "/api/memory":
            return "user"
        return "guest"
    admin_writes = (
        "/api/models/pull", "/api/models/update", "/api/models/updates/auto", "/api/models",
        "/api/network", "/api/network/token", "/api/ollama/update", "/api/voice-settings", "/api/voices",
        "/api/shared", "/api/profiles",
    )
    if path in admin_writes or path.startswith(("/api/voices/", "/api/profiles/", "/api/plugins", "/api/mcp", "/api/diagnostics",
                                                 "/api/backups", "/api/llm/", "/api/hf/")):
        return "admin"
    if path.startswith(("/api/assistants", "/api/chats/", "/api/memory", "/api/knowledge/", "/api/routines")) or path in (
            "/api/profile/me", "/api/models/measure", "/api/files/delete"):
        return "user"
    return "guest"


_RANK = {"public": 0, "guest": 1, "user": 2, "admin": 3}


def role_rank(sess) -> int:
    if not sess:
        return 0
    return 1 if sess["guest"] else 3 if sess["role"] == "admin" else 2


# ── Ollama ─────────────────────────────────────────────────────────────

_show_cache = {}


def _show(name: str, digest: str) -> dict:
    """Capacidades del modelo y si trae un prompt de sistema propio (señal
    de modelo personalizado creado con un Modelfile)."""
    key = (name, digest)
    if key not in _show_cache:
        try:
            r = requests.post(f"{OLLAMA_URL}/api/show", json={"model": name}, timeout=8)
            r.raise_for_status()
            data = r.json()
            # capabilities None = esta versión de Ollama no las informa (≠ lista vacía)
            _show_cache[key] = {"capabilities": data.get("capabilities"), "system": bool(data.get("system"))}
        except (requests.exceptions.RequestException, ValueError):
            return {"capabilities": None, "system": False}
    return _show_cache[key]


def list_models() -> dict:
    """Modelos BASE instalados en Ollama. Se ocultan los personalizados
    (`ollama create` a partir de otro modelo con su propio prompt, como los
    viejos jarvis:latest/bella:latest de antes de assistants.yaml): no
    sirven como base_model porque su prompt de sistema se sumaría al del
    asistente. Se reconocen por nombre (el modelo se llama igual que un
    asistente de assistants.yaml, sin contar el tag) y, además, porque su
    `parent_model` es otro modelo instalado o porque traen un prompt de
    sistema propio (el parent_model solo no alcanza: algunos modelos
    oficiales traen ahí una ruta)."""
    assistant_names = {a["name"] for a in store.load_state()["assistants"]}
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=4)
        r.raise_for_status()
        raw_models = r.json().get("models", [])
    except (requests.exceptions.RequestException, ValueError) as e:
        return {"online": False, "error": str(e), "models": [], "hidden": [], "remote": llm_remote.remote_models()}

    installed = {m.get("name") or m.get("model") for m in raw_models}
    models, hidden = [], []
    for m in raw_models:
        name = m.get("name") or m.get("model")
        if not name:
            continue
        details = m.get("details") or {}
        show = _show(name, m.get("digest", ""))
        parent = details.get("parent_model") or ""
        if name.split(":")[0].lower() in assistant_names or parent in installed or show["system"]:
            hidden.append({"name": name, "parent": parent})
            continue
        models.append({
            "name": name,
            "size": m.get("size") or 0,
            "family": details.get("family", ""),
            "parameter_size": details.get("parameter_size", ""),
            "quantization": details.get("quantization_level", ""),
            "capabilities": show["capabilities"],
        })
    models.sort(key=lambda x: x["name"].lower())
    hidden.sort(key=lambda x: x["name"].lower())
    return {"online": True, "models": models, "hidden": hidden, "remote": llm_remote.remote_models()}


# ── Memoria de cada modelo ────────────────────────────────────────────
# Cuánta VRAM ocupa un modelo al usarlo. Dos niveles:
# - MEDIDO: lo que reporta Ollama (/api/ps, size_vram) cuando el modelo está
#   cargado, más lo que suma el proceso de Ollama (CUDA y buffers). Se
#   guarda en config/model_memory.json cada vez que se ve un modelo cargado
#   o se pide "Medir" (lo carga un momento).
# - ESTIMADO, mientras no hay medición: pesos + caché del contexto (KV) +
#   el mismo margen. La caché sale de la forma del modelo según sus
#   metadatos (capas, cabezas, largo de claves/valores, capas con ventana
#   deslizante como Gemma, capas sin caché como las SSM de Qwen 3.5).
# Medido en la RTX 4080 SUPER (octubre 2026), subida real de nvidia-smi vs
# lo que dice Ollama: gemma4:E4B 4,7 vs 3,2 GiB, gemma4:e2b 3,1 vs 1,7,
# qwen3.5:9b 6,9 vs 5,6, granite4.1:3b 3,6 vs 3,4. Ojo: Gemma 4 E4B pesa
# 8,9 GiB en disco pero deja parte fuera de la GPU, así que su estimado
# teórico se pasa mucho: por eso manda la medición.

GIB = 1024 ** 3
DEFAULT_CTX = 4096                # Ollama, si no se vio ningún modelo cargado
OLLAMA_PROCESS = int(1.0 * GIB)   # CUDA + buffers del proceso de Ollama (medido 0,2-1,5)
MEMORY_FILE = os.path.join(paths.CONFIG_DIR, "model_memory.json")
# Lo que suman los otros modelos de la app al hablar por voz (medido, nota 12
# del README; Supertonic: sus ~0,4 GB de ONNX más su contexto de CUDA).
VOICE_COSTS = {
    "whisper": {"small": int(0.9 * GIB), "large-v3-turbo": int(2.1 * GIB)},
    "supertonic": int(0.6 * GIB),
    "qwen": {"0.6B": int(2.8 * GIB), "1.7B": int(4.8 * GIB)},
}

_shape_cache = {}
_gpu_cache = {}
_memory_lock = threading.Lock()


def _load_memory() -> dict:
    try:
        with open(MEMORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_memory(data: dict) -> None:
    tmp = MEMORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, MEMORY_FILE)


def _record_loaded(loaded: list) -> dict:
    """Guarda lo que mide Ollama de los modelos cargados ahora."""
    with _memory_lock:
        data = _load_memory()
        models = data.setdefault("models", {})
        changed = False
        for m in loaded:
            name = m.get("name") or m.get("model")
            if not name or not m.get("size_vram"):
                continue
            entry = {"digest": m.get("digest", ""), "vram": int(m["size_vram"]), "size": int(m.get("size") or 0),
                     "ctx": m.get("context_length"), "at": int(time.time())}
            if models.get(name, {}).get("vram") != entry["vram"] or models.get(name, {}).get("ctx") != entry["ctx"]:
                models[name] = entry
                changed = True
            if m.get("context_length") and data.get("ctx") != m["context_length"]:
                data["ctx"] = int(m["context_length"])
                changed = True
        if changed:
            _save_memory(data)
        return data


def _model_shape(name: str, digest: str):
    """Metadatos de la arquitectura (verbose: trae las listas por capa)."""
    key = (name, digest)
    if key not in _shape_cache:
        try:
            r = requests.post(f"{OLLAMA_URL}/api/show", json={"model": name, "verbose": True}, timeout=30)
            r.raise_for_status()
            info = r.json().get("model_info") or {}
            arch = info.get("general.architecture") or ""
            _shape_cache[key] = {k[len(arch) + 1:]: v for k, v in info.items()
                                 if arch and k.startswith(arch + ".") and "tokenizer" not in k}
        except (requests.exceptions.RequestException, ValueError):
            return None
    return _shape_cache[key]


def _kv_bytes(shape: dict, ctx: int):
    """Bytes de la caché KV (f16) para `ctx` tokens, o None si no se sabe."""
    layers = int(shape.get("block_count") or 0)
    if not layers:
        return None
    heads = shape.get("attention.head_count") or 1
    heads = max(heads) if isinstance(heads, list) else heads
    emb = shape.get("embedding_length") or 0
    kv = shape.get("attention.head_count_kv", heads)
    kv = kv if isinstance(kv, list) else [kv] * layers
    k_len = shape.get("attention.key_length") or (emb // heads if emb else 128)
    v_len = shape.get("attention.value_length") or k_len
    k_swa = shape.get("attention.key_length_swa") or k_len
    v_swa = shape.get("attention.value_length_swa") or v_len
    window = shape.get("attention.sliding_window")
    pattern = shape.get("attention.sliding_window_pattern")
    total = 0
    for i in range(layers):
        n = kv[i] if i < len(kv) else kv[-1]
        if not n:
            continue  # capa sin atención (SSM): no guarda caché por token
        sliding = bool(window) and isinstance(pattern, list) and i < len(pattern) and pattern[i]
        tokens = min(ctx, window) if sliding else ctx
        total += n * ((k_swa + v_swa) if sliding else (k_len + v_len)) * tokens * 2
    return total


def _gpu() -> dict:
    """Nombre, VRAM total y en uso ahora (nvidia-smi)."""
    try:
        import subprocess
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip().splitlines()
        if out:
            name, total, used = [x.strip() for x in out[0].split(",")]
            return {"name": name, "total": int(float(total)) << 20, "used": int(float(used)) << 20}
    except Exception:
        pass
    return {}


def model_memory() -> dict:
    """VRAM de cada modelo instalado (medida o estimada), más lo que suma la voz."""
    try:
        tags = requests.get(f"{OLLAMA_URL}/api/tags", timeout=4).json().get("models", [])
        loaded = requests.get(f"{OLLAMA_URL}/api/ps", timeout=4).json().get("models", [])
    except (requests.exceptions.RequestException, ValueError):
        return {"online": False, "models": {}}
    saved = _record_loaded(loaded)
    ctx = saved.get("ctx") or DEFAULT_CTX
    loaded_names = {m.get("name") or m.get("model") for m in loaded}
    out = {}
    for m in tags:
        name = m.get("name") or m.get("model")
        weights = m.get("size") or 0
        shape = _model_shape(name, m.get("digest", ""))
        kv = _kv_bytes(shape, ctx) if shape else None
        meas = saved.get("models", {}).get(name)
        if meas and meas.get("digest") not in ("", m.get("digest")):
            meas = None  # se actualizó el modelo: la medición vieja no vale
        out[name] = {
            "weights": weights,
            "kv": kv,
            "kv_per_1k": _kv_bytes(shape, 1024) if shape else None,
            "estimate": int(weights + (kv or 0) + OLLAMA_PROCESS),
            "measured": int(meas["vram"] + OLLAMA_PROCESS) if meas else None,
            "measured_ctx": meas.get("ctx") if meas else None,
            "loaded": name in loaded_names,
        }
    vs = voice_settings.load()
    qwen_model = (vs.get("qwen_tts") or {}).get("model")
    return {
        "online": True,
        "ctx": ctx,
        "process": OLLAMA_PROCESS,
        "models": out,
        "gpu": _gpu(),
        "voice": {
            "whisper": VOICE_COSTS["whisper"].get(vs.get("stt_model"), VOICE_COSTS["whisper"]["small"]),
            "whisper_model": vs.get("stt_model"),
            "supertonic": VOICE_COSTS["supertonic"],
            "qwen": VOICE_COSTS["qwen"].get(qwen_model, VOICE_COSTS["qwen"]["0.6B"]),
            "qwen_model": qwen_model,
        },
    }


def measure_model(name: str) -> dict:
    """Carga el modelo un momento para medir su VRAM real; si no estaba
    cargado, lo descarga después para no dejar ocupada la memoria."""
    if not MODEL_NAME_RE.match(name or ""):
        raise store.ConfigError(tr("pull_name_invalid"))
    try:
        was_loaded = any((m.get("name") or m.get("model")) == name
                         for m in requests.get(f"{OLLAMA_URL}/api/ps", timeout=4).json().get("models", []))
        # Si ya estaba cargado (el de los asistentes) se le deja su
        # keep_alive: con "60s" se descargaba al minuto, entre turnos.
        keep = chat_runtime.CHAT_KEEP_ALIVE if was_loaded else "60s"
        requests.post(f"{OLLAMA_URL}/api/generate", json={"model": name, "prompt": "", "keep_alive": keep},
                      timeout=300).raise_for_status()
        _record_loaded(requests.get(f"{OLLAMA_URL}/api/ps", timeout=4).json().get("models", []))
        if not was_loaded:
            requests.post(f"{OLLAMA_URL}/api/generate", json={"model": name, "keep_alive": 0}, timeout=30)
    except requests.exceptions.RequestException as e:
        raise store.ConfigError(tr("ollama_failed", error=e), status=502)
    server_log.log("ollama", f"measured memory for {name}")
    return model_memory()


_pull_lock = threading.Lock()
_pull = {"model": None, "state": "idle", "status": "", "completed": 0, "total": 0, "error": None}


def pull_status() -> dict:
    with _pull_lock:
        return dict(_pull)


def _pull_worker(model: str) -> None:
    try:
        with requests.post(
            f"{OLLAMA_URL}/api/pull",
            json={"model": model, "stream": True},
            stream=True,
            timeout=(10, 600),
        ) as r:
            if r.status_code != 200:
                raise RuntimeError(r.text.strip() or f"HTTP {r.status_code}")
            for line in r.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if data.get("error"):
                    raise RuntimeError(data["error"])
                with _pull_lock:
                    if data.get("status") and data.get("status") != _pull["status"]:
                        server_log.log("ollama", f"pull {model}: {data['status']}")
                    _pull["status"] = data.get("status", "")
                    if data.get("total"):
                        _pull["total"] = data["total"]
                        _pull["completed"] = data.get("completed", 0)
        with _pull_lock:
            _pull.update(state="done", status="success")
        server_log.log("ollama", f"{model} downloaded")
    except Exception as e:  # noqa: BLE001 — se muestra tal cual en la interfaz
        with _pull_lock:
            _pull.update(state="error", error=str(e))
        server_log.log("ollama", f"could not download {model}: {e}", "error")


def start_pull(model: str) -> dict:
    model = str(model or "").strip()
    if not MODEL_NAME_RE.match(model):
        raise store.ConfigError(tr("pull_name_invalid"), {"pull": tr("pull_name_hint")})
    with _pull_lock:
        if _pull["state"] == "running":
            raise store.ConfigError(tr("pull_running", model=_pull["model"]), status=409)
        _pull.update(model=model, state="running", status="", completed=0, total=0, error=None)
    threading.Thread(target=_pull_worker, args=(model,), daemon=True).start()
    return pull_status()


def _hf_import_worker(repo: str, path: str, name: str, size: int) -> None:
    """Private/gated Hugging Face GGUF: Ollama can't receive the token, so the
    file is downloaded here (with the token), sent to Ollama as a blob and
    turned into a model with /api/create. Progress goes to the same _pull
    state as `ollama pull`."""
    dest = os.path.join(paths.ROOT, "cache", "hf", repo.replace("/", "__"), os.path.basename(path))
    try:
        def progress(done, total):
            with _pull_lock:
                _pull.update(status="downloading from Hugging Face", completed=done, total=total or size)
        server_log.log("models", f"downloading {repo}/{path} from Hugging Face (private/gated)")
        digest = hf_hub.download(repo, path, dest, progress=progress)
        with _pull_lock:
            _pull.update(status="importing into Ollama")
        blob = f"sha256:{digest}"
        if requests.head(f"{OLLAMA_URL}/api/blobs/{blob}", timeout=10).status_code != 200:
            with open(dest, "rb") as fh:
                requests.post(f"{OLLAMA_URL}/api/blobs/{blob}", data=fh, timeout=(10, 3600)).raise_for_status()
        with requests.post(f"{OLLAMA_URL}/api/create", json={"model": name, "files": {os.path.basename(path): blob},
                                                             "stream": True}, stream=True, timeout=(10, 1800)) as r:
            if r.status_code != 200:
                raise RuntimeError(r.text.strip() or f"HTTP {r.status_code}")
            for line in r.iter_lines():
                if line:
                    msg = json.loads(line)
                    if msg.get("error"):
                        raise RuntimeError(msg["error"])
                    with _pull_lock:
                        _pull["status"] = msg.get("status", "")
        with _pull_lock:
            _pull.update(state="done", status="success")
        server_log.log("ollama", f"{name} imported from Hugging Face ({repo}/{path})")
        _show_cache.clear()
    except Exception as e:  # noqa: BLE001 — shown as is in the UI
        with _pull_lock:
            _pull.update(state="error", error=tr("hf_auth") if isinstance(e, PermissionError) else str(e))
        server_log.log("ollama", f"could not import {repo}/{path}: {e}", "error")
    finally:
        for p in (dest, dest + ".part"):
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(os.path.dirname(dest))
        except OSError:
            pass


def start_hf_pull(repo: str, quant: str) -> dict:
    """Assistant model from a Hugging Face GGUF repo. Public repos: Ollama
    pulls `hf.co/<repo>:<quant>` itself. Private or gated ones (with a
    token saved): downloaded here and imported (single-file quants)."""
    try:
        info = hf_hub.gguf_info(repo)
    except PermissionError:
        raise store.ConfigError(tr("hf_auth"), status=403)
    except FileNotFoundError:
        raise store.ConfigError(tr("hf_not_found"), status=404)
    except (ValueError, requests.exceptions.RequestException) as e:
        raise store.ConfigError(tr("hf_failed", error=e), status=502)
    q = next((x for x in info["quants"] if x["quant"].upper() == str(quant or "").upper()), None)
    if not q:
        raise store.ConfigError(tr("hf_quant_missing"))
    repo = info["id"]
    if not (info["private"] or info["gated"]):
        return start_pull(f"hf.co/{repo}:{q['quant']}")
    if not hf_hub.token():
        raise store.ConfigError(tr("hf_needs_token"), status=403)
    if q["sharded"]:
        raise store.ConfigError(tr("hf_sharded_private"))
    name = re.sub(r"[^a-z0-9._-]", "-", repo.split("/")[1].lower())[:80] + ":" + q["quant"].lower()
    with _pull_lock:
        if _pull["state"] == "running":
            raise store.ConfigError(tr("pull_running", model=_pull["model"]), status=409)
        _pull.update(model=name, state="running", status="", completed=0, total=q["size"], error=None)
    threading.Thread(target=_hf_import_worker, args=(repo, q["files"][0], name, q["size"]), daemon=True).start()
    return pull_status()


def models_api(method: str, path: str, data: dict, query: dict):
    """/api/llm/* (remote LLM providers) and /api/hf/* (Hugging Face). None
    if the path is not one of them."""
    def q(k, d=""):
        return (query.get(k) or [d])[0]
    try:
        if path == "/api/llm/providers":
            if method == "GET":
                return {"providers": llm_remote.public(), "kinds": list(llm_remote.KINDS),
                        "defaults": llm_remote.DEFAULT_URLS}
            if method == "PUT":
                out = llm_remote.save(data.get("providers") or [])
                server_log.log("models", f"remote LLM providers saved: {', '.join(p['id'] for p in out) or 'none'}")
                return {"providers": out, "models": list_models()}
        if method == "POST" and path == "/api/llm/models":
            return {"models": llm_remote.list_provider_models(data)}
        if method == "POST" and path == "/api/llm/test":
            res = llm_remote.test_provider(data)
            server_log.log("models", f"tested remote LLM {data.get('kind')} {data.get('model')}: ok in {res['ms']} ms"
                                     f", tools {res['tools']}")
            return res
        if path == "/api/hf/token":
            if method == "PUT":
                hf_hub.set_token(data.get("token") or "")
                server_log.log("models", "Hugging Face token " + ("saved" if data.get("token") else "removed"))
            return {"has_token": bool(hf_hub.token())}
        if method == "GET" and path == "/api/hf/search":
            return {"models": hf_hub.search(q("q"), gguf=q("gguf", "1") != "0")}
        if method == "GET" and path == "/api/hf/repo":
            return hf_hub.gguf_info(q("repo"))
        if method == "POST" and path == "/api/hf/pull":
            return start_hf_pull(str(data.get("repo") or ""), str(data.get("quant") or ""))
    except store.ConfigError:
        raise
    except PermissionError:
        raise store.ConfigError(tr("hf_auth"), status=403)
    except FileNotFoundError:
        raise store.ConfigError(tr("hf_not_found"), status=404)
    except (ValueError, requests.exceptions.RequestException) as e:
        key = "hf_failed" if path.startswith("/api/hf/") else "llm_failed"
        raise store.ConfigError(tr(key, error=e), status=400 if isinstance(e, ValueError) else 502)
    return None


def delete_model(name: str) -> dict:
    """Borra un modelo de Ollama (Ajustes compartidos → Modelos de IA). La
    página avisa antes si lo usa algún asistente; esos asistentes quedan
    apuntando a un modelo que falta (la página ofrece descargarlo de nuevo)."""
    if not MODEL_NAME_RE.match(name or ""):
        raise store.ConfigError(tr("pull_name_invalid"))
    running = pull_status()
    if running["state"] == "running" and running["model"] == name:
        raise store.ConfigError(tr("pull_running", model=name), status=409)
    try:
        requests.post(f"{OLLAMA_URL}/api/generate", json={"model": name, "keep_alive": 0}, timeout=30)  # descargarlo de la memoria
        r = requests.delete(f"{OLLAMA_URL}/api/delete", json={"model": name}, timeout=60)
        if r.status_code == 404:
            raise store.ConfigError(tr("model_not_found", model=name), status=404)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise store.ConfigError(tr("ollama_failed", error=e), status=502)
    used = [a["label"] or a["name"].upper() for a in store.load_state()["assistants"] if a["base_model"] == name]
    server_log.log("models", f"deleted model: {name}" + (f" (used by {', '.join(used)})" if used else ""))
    _show_cache.clear()
    return list_models()


def start_model_update(model: str) -> dict:
    """Actualiza un modelo instalado a la versión nueva de su registro: el
    mismo pull (con su barra de progreso) y después se comprueba que quedó
    la versión nueva y se borraron las capas viejas (model_updates)."""
    model = str(model or "").strip()
    if not MODEL_NAME_RE.match(model):
        raise store.ConfigError(tr("pull_name_invalid"))
    running = pull_status()
    if running["state"] == "running":  # p. ej. la actualización automática
        raise store.ConfigError(tr("pull_running", model=running["model"]), status=409)
    prev = model_updates.before_update(model)
    try:
        start_pull(model)
    except store.ConfigError:
        model_updates.after_update(prev, False)
        raise
    server_log.log("models", f"updating {model}…")

    def wait():
        while pull_status()["state"] == "running":
            time.sleep(2)
        model_updates.after_update(prev, pull_status()["state"] == "done")

    threading.Thread(target=wait, name="model-update-wait", daemon=True).start()
    return pull_status()


# ── Chat ───────────────────────────────────────────────────────────────

def _images_of(m: dict) -> list:
    """Imágenes adjuntas de un mensaje (base64, sin el prefijo data:)."""
    out = []
    for img in m.get("images") or []:
        img = str(img or "")
        img = img.split(",", 1)[1] if img.startswith("data:") else img
        if img and B64_RE.match(img[:200]):
            out.append(img)
    return out[:MAX_IMAGES]


def _with_attachments(m: dict, full_text: bool, show_images: bool, vision: bool) -> tuple:
    """(contenido, imágenes) de un mensaje del usuario con sus adjuntos:
    el texto de cada archivo (o la transcripción de un audio) va a
    continuación de lo que escribió, entre <<< >>>, y las imágenes en
    `images` (Ollama se las pasa al modelo con visión). Lo que escribió va
    primero: el revisor y el registro miran el principio."""
    content = str(m.get("content", "")).strip()
    blocks = []
    seen_image = False
    images = _images_of(m) if vision and show_images else []
    for a in [a for a in m.get("attachments") or [] if isinstance(a, dict)][:12]:
        name = str(a.get("name") or "?")[:120]
        kind = a.get("kind")
        if kind == "image":
            if not vision:
                blocks.append(f'[The user attached an image "{name}", but you can\'t see images: say so if they ask about it.]')
            elif not show_images:
                blocks.append(f'[Earlier the user attached an image "{name}" (you no longer see it)]')
            else:
                blocks.append(f'[Attached image "{name}"]')
                seen_image = True
            continue
        text = str(a.get("text") or "").strip()
        info = str(a.get("info") or "")[:80]
        detail = f" ({info})" if info else ""
        # "ya transcrito": sin esto, con un audio sin mensaje BELLA contestaba
        # "no puedo procesar archivos de audio".
        head = (f'[Attached audio "{name}"{detail}: it was already transcribed for you by speech recognition, '
                'this is exactly what is said in it]'
                if kind == "audio" else f'[Attached file "{name}"{detail}]')
        if not full_text and len(text) > OLD_FILE_CHARS:
            text = text[:OLD_FILE_CHARS] + "\n[... the rest was in an earlier message]"
        blocks.append(f"{head}\n<<<\n{text}\n>>>" if text else f"{head} (empty)")
    if not blocks:
        return content, images
    attached = "\n\n".join(blocks)
    if len(attached) > MAX_MESSAGE_CHARS:
        attached = attached[:MAX_MESSAGE_CHARS] + "\n[... cut: the attachments were too long]\n>>>"
    if seen_image and images:
        # Visto: inventaba quién era la persona por el nombre del archivo
        # ("channels4_profile.jpg" → un político) y rellenaba con detalles
        # que no estaban.
        attached += ("\n\n(About the image: talk about it only if the user asks something about it. Then describe "
                     "only what you can actually see in it, with the concrete details (objects, people's appearance, "
                     "colors, setting, and any visible text copied exactly). Don't guess who a person is from their "
                     "face or from the file name; only name someone if their name is written in the image or the "
                     "user said it. If something isn't clear, say so instead of making it up.)")
    if content:
        # Visto: a "pásalo a PDF" con un documento adjunto, primero lo resumía.
        return (f"{content}\n\n{attached}\n\n(Use the attachments only for what the user asked; don't describe "
                "or summarize them unless that's what they asked.)"), images
    kinds = {a.get("kind") for a in m.get("attachments") or [] if isinstance(a, dict)}
    if kinds == {"audio"}:
        # Al final: los modelos chicos le hacen más caso a lo último.
        note = ("(The user sent only this audio, with no message, so they want it transcribed: start your reply "
                "with the full transcription above, word for word between quotation marks, and only then, in one "
                "or two sentences, comment on what it says. Don't promise actions you can't do, like setting "
                "reminders.)")
    else:
        note = ("(The user sent only these attachments, with no message: in one short sentence say you got them "
                "and ask what they'd like you to do with them (for example: summarize it, answer questions about "
                "it, translate it or convert it to another format). Don't describe or summarize them yet.)")
    return f"{attached}\n\n{note}", images


def _group_history(data: dict, vision: bool = True):
    """(historial, mensajes crudos, claves→nombres) del borrador que manda
    la página. En una conversación con varios asistentes (`group`: [{"key",
    "label"}], `speaker`: la clave del que responde ahora) cada mensaje de
    asistente trae su `speaker`: los propios quedan como "assistant" y los
    de los demás pasan como "[NOMBRE]: ..." para que este asistente tenga
    todo el contexto sin confundirlos con lo suyo ni con el usuario.

    Adjuntos (chat escrito): ver _with_attachments. Solo los últimos
    IMAGE_TURNS mensajes con imágenes las siguen mandando (cada imagen son
    cientos de tokens y se vuelve a procesar en cada turno) y solo los
    últimos FILE_TURNS con archivos conservan todo el texto. `vision`: si
    el modelo ve imágenes; si no, se le avisa que hay una que no ve."""
    raw = [
        m for m in data.get("history") or []
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        and (str(m.get("content", "")).strip() or (m["role"] == "user" and (m.get("attachments") or m.get("images"))))
    ]
    me = str(data.get("speaker") or "")
    group = [g for g in data.get("group") or [] if isinstance(g, dict) and g.get("key")]
    labels = {str(g["key"]): str(g.get("label") or g["key"]).upper()[:40] for g in group}
    with_images = [i for i, m in enumerate(raw) if m["role"] == "user" and _images_of(m)][-IMAGE_TURNS:]
    with_files = [i for i, m in enumerate(raw) if m["role"] == "user"
                  and any(isinstance(a, dict) and a.get("kind") != "image" for a in m.get("attachments") or [])][-FILE_TURNS:]
    history = []
    for i, m in enumerate(raw):
        content = str(m.get("content", ""))
        speaker = str(m.get("speaker") or "")
        if m["role"] == "assistant" and group and speaker and speaker != me:
            history.append({"role": "user", "content": f"[{labels.get(speaker, speaker.upper())}]: {content}"})
        elif m["role"] == "user" and (m.get("attachments") or m.get("images")):
            content, images = _with_attachments(m, i in with_files, i in with_images, vision)
            history.append({"role": "user", "content": content, **({"images": images} if images else {})})
        else:
            sent = [str(f.get("name") or "")[:120] for f in m.get("files") or [] if isinstance(f, dict)] if m["role"] == "assistant" else []
            if sent:
                content += "\n\n" + "\n".join(f'[You sent the user the file "{n}"]' for n in sent if n)
            history.append({"role": m["role"], "content": content})
    return history, raw, labels


def _conversation_files(raw: list, sess=None, assistants: list | None = None) -> list:
    """Archivos disponibles para convertir o editar: combina los archivos y medios
    generados o subidos en cualquier otro chat del mismo perfil con los de la
    conversación actual (dejando los del chat actual al final como más recientes)."""
    conv_files = []
    conv_ids = set()
    for m in raw:
        items = m.get("attachments") if m.get("role") == "user" else m.get("files")
        for a in items or []:
            if not isinstance(a, dict) or not a.get("name"):
                continue
            mm = re.fullmatch(r"/api/files/([0-9a-z.]{1,40})", str(a.get("url") or ""))
            if mm:
                fid = mm.group(1)
                conv_files.append({"name": str(a["name"])[:200], "id": fid})
                conv_ids.add(fid)

    profile_files = []
    if sess and not sess.get("guest"):
        owner = "" if sess.get("role") == "admin" else str(sess.get("id") or "")
        for pf in dashboard.list_profile_files(owner, False, assistants or []):
            if pf["id"] not in conv_ids:
                profile_files.append({
                    "name": pf["name"],
                    "id": pf["id"],
                    "assistant": pf.get("assistant") or "",
                    "info": pf.get("info") or "",
                })
    return profile_files + conv_files


def _model_sees_images(model: str) -> bool:
    if llm_remote.is_remote(model):
        return "vision" in (llm_remote.model_caps(model) or [])
    caps = _show(model, "")["capabilities"]
    return caps is None or "vision" in caps  # None: esta versión de Ollama no lo informa


def _speech_chunks(text: str) -> list:
    chunker = assistant_common.SpeechChunker()
    return chunker.feed(text) + chunker.flush()


def _chat_request(data: dict, sess=None):
    """(cfg, shared_context, history, lang, estilo, idiomas_auto, grupo) a
    partir del borrador que manda la interfaz — se usa la configuración en
    edición aunque no esté guardada.

    `lang`: un código (responde en ese idioma) o "auto" (chat escrito:
    responde en el idioma en que escribió el usuario, entre los del
    asistente; lo decide el modelo, sin adivinarlo con listas de palabras).

    `grupo`: para las herramientas de invitar/sacar asistentes ("me": quién
    responde, "participants": los asistentes guardados que están en la
    conversación, "assistants": todos los guardados)."""
    draft = {k: v for k, v in (data.get("assistant") or {}).items() if k in store.KNOWN_FIELDS}
    cfg = store.assistant_view(str((data.get("assistant") or {}).get("name") or "nuevo"), draft)
    state = store.load_state()
    shared_context = state["shared_context"]
    state["assistants"] = [a for a in state["assistants"] if can_see(a, sess)]
    history, _raw, labels = _group_history(data, _model_sees_images(cfg["base_model"]))
    me = str(data.get("speaker") or "")
    if len(labels) > 1:
        others = [label for key, label in labels.items() if key != me]
        shared_context = (shared_context + "\n\n" if shared_context else "") + (
            f"GROUP VOICE CONVERSATION: besides you and the user, {', '.join(others)} take part. Everyone hears "
            "the whole conversation. Messages starting with «[NAME]:» were said by that other assistant, not by "
            "the user. The user just spoke to you: answer only for yourself, without speaking for the others, "
            "without putting your name in front and without repeating what they already said (you can comment "
            "on it, agree or disagree)."
        )
        # Ronda: el usuario les preguntó a todos y responden por turnos.
        round_info = data.get("round") if isinstance(data.get("round"), dict) else {}
        if round_info.get("all"):
            done = [str(x).upper()[:40] for x in round_info.get("answered") or []]
            # Que cada personalidad opine de verdad: visto, BELLA se escudaba en
            # "como asistente no tengo gustos" y el segundo no reaccionaba al
            # primero. Va en el system prompt y, corto, al final del último
            # mensaje (los modelos chicos pesan más el final).
            stance = ("It's a game of opinions between personalities: take a concrete, personal stance (what you "
                      "prefer, yes or no, which one you'd pick) as your character would, even though you're an AI; "
                      "don't say you have no tastes or opinions.")
            if done:
                shared_context += (
                    f"\n\nROUND OF OPINIONS: the user asked EVERYONE this question and you answer in turns. "
                    f"{', '.join(done)} already answered: their answers are the «[NAME]: …» messages after the "
                    "question. Now it's your turn. Start by reacting to what they said (agree, disagree or add "
                    "something, naming who you react to) and then give YOUR opinion, different or with something "
                    "of your own, without repeating the same thing or answering for them. " + stance
                )
                nudge = (f"(Round: your turn now. First react to what {', '.join(done)} said — agree, disagree or "
                         "add something — and give your own opinion, from your personality.)")
            else:
                shared_context += (
                    "\n\nROUND OF OPINIONS: the user asked EVERYONE this question and you answer in turns; you "
                    "go first. Give your opinion; the others will give theirs after you. " + stance
                )
                nudge = "(Question for everyone: you answer first, with your own concrete opinion.)"
            if history:
                history[-1] = {**history[-1], "content": f"{history[-1]['content']}\n\n{nudge}"}
    if data.get("video_call"):
        # Videollamada (modo voz con la cámara): cada mensaje trae lo que ve la cámara.
        shared_context = (shared_context + "\n\n" if shared_context else "") + (
            "VIDEO CALL: you are on a live video call with the user. Each of their messages comes with a frame of what "
            "their camera shows at that moment (the attached image named like \"camera-…\" or \"camara-…\"): you CAN see "
            "it. When they ask what you see, what something is, to read text, count things, compare, or help with what "
            "they're showing, look at that frame and answer concretely: name the objects and their colors, brands, "
            "text or state. If it's blurry, dark or you can't tell, say so and ask them to bring it closer or turn "
            "on a light. When they talk about something else, don't describe the frame. Never say you can't see."
        )
    allowed = cfg["languages"] or _LANGUAGES
    style = "voice" if data.get("mode") == "voice" else "text"
    auto_langs = None
    if data.get("lang") == "auto":
        lang = None
        auto_langs = list(allowed)
    else:
        lang = data.get("lang") if data.get("lang") in allowed else cfg["language"]

    # Quién es quién para invitar/sacar: el de la página va como "@host"
    # (puede ser un borrador sin guardar); la página manda su nombre aparte.
    saved = [{"name": a["name"], "label": a["label"], "base_model": a["base_model"]} for a in state["assistants"]]
    host = str(data.get("host_name") or "")
    to_name = lambda key: host if key == "@host" else key  # noqa: E731
    participants = [n for n in (to_name(k) for k in (labels or {"@host": ""})) if n]
    group = {"me": to_name(me or "@host"), "participants": participants, "assistants": saved,
             "files": _conversation_files(_raw, sess, state["assistants"]), "raw": _raw}
    return cfg, shared_context, history, lang, style, auto_langs, group


# ── HTTP ───────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    server_version = "AuraVox/2.0"

    # Peticiones que se repiten solas (sondeos, vistas previas mientras se
    # escribe): no se registran para no tapar lo importante en la consola.
    _QUIET = ("/api/logs", "/api/geo/", "/api/models/pull", "/api/models/updates", "/api/ollama/update", "/api/chats/",
              "/api/dev/",
              "/api/files/", "/api/wake-check", "/api/preview", "/static/", "/previews/", "/api/state",
              "/api/voice/", "/api/notify", "/api/plugin/")

    def log_message(self, fmt, *args):
        pass  # el registro propio está en log_request

    def log_request(self, code="-", size="-"):
        path = urlsplit(self.path).path
        if path == "/" or any(path.startswith(q) for q in self._QUIET):
            if str(code).startswith(("2", "3")):
                return
        ms = (time.time() - getattr(self, "_t0", time.time())) * 1000
        level = "error" if str(code).startswith("5") else "warn" if str(code).startswith("4") else "info"
        server_log.log("http", f"{self.command} {path} → {code} ({ms:.0f} ms)", level)

    # Protección para un servidor local que escribe archivos: el Host tiene
    # que ser el nuestro (evita DNS rebinding) y las escrituras exigen JSON
    # (o audio, solo para transcribir) y un Origin propio: una web
    # cualquiera abierta en el navegador no puede mandar un POST "simple".
    def _allowed_hosts(self) -> set:
        port = self.server.server_address[1]
        if getattr(self.server, "lan", False):  # acceso por red (network.py): las IP y el nombre de esta PC
            return {f"{h}:{port}" for h in network.host_names()}
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _remote(self) -> bool:
        """Viene de otro dispositivo (por el acceso por red)."""
        return getattr(self.server, "lan", False) and self.client_address[0] not in ("127.0.0.1", "::1")

    def _lan_auth(self) -> bool:
        """Desde otro dispositivo hace falta la clave: en el enlace (?key=…,
        la primera vez; queda en una cookie) o en la cookie."""
        if not self._remote():
            return True
        query = parse_qs(urlsplit(self.path).query)
        if self.command == "GET" and network.token_ok(query.get("key", [""])[0]):
            # Se sirve la página directamente con la cookie (la página quita
            # ?key de la dirección). Antes se redirigía a "/" con una cookie
            # SameSite=Strict y, viniendo del escáner de QR (otra app), el
            # navegador no la mandaba en la redirección: "falta la clave".
            self._cookies.append(f"{network.COOKIE}={network.settings()['token']}; Path=/; Max-Age=31536000; "
                                 "Secure; HttpOnly; SameSite=Lax")
            server_log.log("network", f"authorized LAN device: {self.client_address[0]}")
            return True
        cookies = dict(c.strip().split("=", 1) for c in self.headers.get("Cookie", "").split(";") if "=" in c)
        if network.token_ok(cookies.get(network.COOKIE, "")):
            return True
        if urlsplit(self.path).path in ("/", "/index.html"):
            body = ("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                    "<title>AuraVox</title><body style='font-family:system-ui;padding:24px;max-width:520px;margin:auto'>"
                    f"<h2>{tr('lan_locked_title')}</h2><p>{tr('lan_locked')}</p>"
                    "<form method='get' action='/' style='display:flex;gap:8px;margin-top:16px'>"
                    f"<input name='key' placeholder='{tr('lan_key_ph')}' autocomplete='off' autocapitalize='off' "
                    "style='flex:1;padding:10px;font-size:16px;border:1px solid #888;border-radius:8px'>"
                    f"<button style='padding:10px 16px;font-size:16px'>{tr('lan_key_go')}</button></form></body>").encode("utf-8")
            self._send_bytes(body, "text/html; charset=utf-8", 401)
        else:
            self._send_json({"error": tr("lan_locked")}, 401)
        return False

    def _guard(self, write: bool, allow_audio: bool = False, allow_binary: bool = False) -> bool:
        self._t0 = time.time()
        self._cookies = []
        i18n.set_lang(self.headers.get("X-UI-Lang"))
        allowed = self._allowed_hosts()
        if self.headers.get("Host", "").lower() not in allowed:
            self._send_json({"error": tr("host_forbidden")}, 403)
            return False
        if not self._lan_auth():
            return False
        # La escucha manos libres es el micrófono de ESTA PC: desde otro
        # dispositivo no se maneja (ese usa el suyo).
        path = urlsplit(self.path).path
        if self._remote() and (path.startswith("/api/voice/") or (write and path.startswith("/api/network"))):
            self._send_json({"error": tr("lan_local_only")}, 403)
            return False
        # Perfil de esta sesión (cookie) y si su rol alcanza para la ruta.
        self._sess = profiles.session(self._cookie_value(profiles.COOKIE))
        need = required_role(self.command, path)
        if role_rank(self._sess) < _RANK[need]:
            if not self._sess:
                self._send_json({"error": tr("login_required"), "login": True}, 401)
            else:
                self._send_json({"error": tr("role_forbidden")}, 403)
            return False
        if write:
            origin = self.headers.get("Origin")
            scheme = "https" if getattr(self.server, "lan", False) else "http"
            if origin and origin.lower() not in {f"{scheme}://{h}" for h in allowed}:
                self._send_json({"error": tr("origin_forbidden")}, 403)
                return False
            ctype = self.headers.get("Content-Type", "")
            if not (ctype.startswith("application/json") or (allow_audio and ctype.startswith("audio/"))
                    or (allow_binary and ctype.startswith("application/octet-stream"))):
                self._send_json({"error": tr("json_expected")}, 415)
                return False
        return True

    def _cookie_value(self, name: str) -> str:
        for part in self.headers.get("Cookie", "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == name:
                return value
        return ""

    def _set_session(self, token, guest: bool = False) -> None:
        """Cookie de la sesión: la del invitado sin Max-Age (se borra al
        cerrar el navegador); vacía = cerrar sesión."""
        secure = "; Secure" if getattr(self.server, "lan", False) else ""
        if not token:
            self._cookies.append(f"{profiles.COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax{secure}")
            return
        age = "" if guest else f"; Max-Age={profiles.SESSION_DAYS * 86400}"
        self._cookies.append(f"{profiles.COOKIE}={token}; Path=/{age}; HttpOnly; SameSite=Lax{secure}")

    def _state(self) -> dict:
        return build_state(self._sess)

    def _send_bytes(self, body: bytes, ctype: str, status: int = 200, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        for cookie in getattr(self, "_cookies", None) or []:  # clave del acceso por red y sesión del perfil
            self.send_header("Set-Cookie", cookie)
        self._cookies = []
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj, status: int = 200) -> None:
        self._send_bytes(json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)

    def _send_file(self, path: str, root: str) -> None:
        real = os.path.realpath(path)
        if not real.startswith(os.path.realpath(root) + os.sep) or not os.path.isfile(real):
            self._send_json({"error": tr("not_found")}, 404)
            return
        ctype = mimetypes.guess_type(real)[0] or "application/octet-stream"
        if real.endswith(".js"):
            ctype = "text/javascript"
        elif real.endswith(".svg"):
            ctype = "image/svg+xml"
        elif real.endswith(".webmanifest"):
            ctype = "application/manifest+json"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        with open(real, "rb") as f:
            self._send_bytes(f.read(), ctype, cache="no-cache")

    def _raw_body(self, limit: int) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            raise store.ConfigError(tr("too_large"), status=413)
        return self.rfile.read(length) if length else b""

    def _body(self, limit: int = MAX_BODY) -> dict:
        raw = self._raw_body(limit) or b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise store.ConfigError(tr("json_invalid"))
        if not isinstance(data, dict):
            raise store.ConfigError(tr("json_invalid"))
        return data

    def _handle(self, fn) -> None:
        try:
            fn()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, ssl.SSLEOFError):
            # (SSLEOFError: lo mismo por HTTPS, desde el celular)
            # La página se cerró o recargó con una consulta en espera
            # (/api/voice/events espera hasta 20 s): no hay a quién responder.
            self.close_connection = True
        except store.ConfigError as e:
            self._send_json({"error": e.message, "fields": e.fields}, e.status)
        except profiles.ProfileError as e:
            self._send_json({"error": tr(e.key, **e.params), "fields": {}}, e.status)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            try:
                self._send_json({"error": tr("internal", error=e)}, 500)
            except (OSError, ssl.SSLError):
                self.close_connection = True  # ya no hay a quién responder

    def do_GET(self):
        if not self._guard(write=False):
            return
        path = urlsplit(self.path).path

        def route():
            if path in ("/", "/index.html"):
                return self._send_file(os.path.join(WEBUI_DIR, "index.html"), WEBUI_DIR)
            if path.startswith("/static/"):
                return self._send_file(os.path.join(WEBUI_DIR, unquote(path[len("/static/"):])), WEBUI_DIR)
            if path == "/sw.js":  # en la raíz, para que su alcance sea toda la página (notificaciones)
                return self._send_file(os.path.join(WEBUI_DIR, "sw.js"), WEBUI_DIR)
            m = VOICE_AUDIO_RE.match(path)
            if m:
                voice = voice_settings.get_voice(m.group(1))
                if not voice:
                    return self._send_json({"error": tr("voice_missing", id=m.group(1))}, 404)
                return self._send_file(voice["path"], paths.CUSTOM_VOICES_DIR)
            m = PREVIEW_RE.match(path)
            if m and m.group(1) in chat_runtime.PREVIEW_TEXT:
                code = m.group(2).replace("custom-", voice_settings.CUSTOM_PREFIX, 1)
                try:
                    preview = chat_runtime.ensure_preview(m.group(1), code)
                except Exception as e:  # noqa: BLE001
                    traceback.print_exc()
                    return self._send_json({"error": tr("tts_failed", error=e)}, 500)
                return self._send_file(preview, chat_runtime.PREVIEWS_DIR)
            if path == "/api/state":
                return self._send_json(self._state())
            if path == "/api/profiles":
                me = self._state()["me"] if self._sess else None
                return self._send_json({"setup": profiles.setup_needed(), "profiles": profiles.list_public(), "me": me,
                                        "api_version": API_VERSION})
            if path.startswith(("/api/llm/", "/api/hf/")):
                out = models_api("GET", path, {}, parse_qs(urlsplit(self.path).query))
                if out is not None:
                    return self._send_json(out)
            if path == "/api/models":
                return self._send_json(list_models())
            if path == "/api/models/memory":
                return self._send_json(model_memory())
            if path == "/api/models/pull":
                return self._send_json(pull_status())
            mc = re.fullmatch(r"/api/chats/([a-z0-9_]{1,40})", path)
            if mc:
                return self._send_json(chat_store.load(mc.group(1), self._sess["id"]))
            if path == "/api/memory":
                return self._send_json({"facts": memory.public(memory.load(self._sess["id"]))})
            if path == "/api/notify":
                query = parse_qs(urlsplit(self.path).query)
                after = query.get("after", ["0"])[0]
                try:
                    wait = float(query.get("wait", ["20"])[0])
                except ValueError:
                    wait = 20.0
                client = query.get("client", [""])[0]
                return self._send_json(notify.poll(self._owner(), int(after) if after.isdigit() else 0, wait,
                                                   client if CLIENT_RE.match(client) else "", not self._remote()))
            if path == "/api/lists":
                return self._send_json(self._lists_state())
            if path == "/api/plugins":
                from app.core import plugins

                return self._send_json({"plugins": plugins.public(), "folder": plugins.PLUGINS_DIR})
            if path == "/api/diagnostics":
                return self._send_json(self._diagnostics())
            if path == "/api/backups":
                return self._send_json({"backups": backup.list_backups(), "folder": backup.BACKUPS_DIR})
            mb = re.fullmatch(r"/api/backups/(auravox-[a-z0-9-]{1,60}\.zip)", path)
            if mb:
                try:
                    return self._send_download(backup.path_of(mb.group(1)), mb.group(1), "application/zip")
                except KeyError:
                    return self._send_json({"error": tr("not_found")}, 404)
            if path == "/api/mcp":
                from app.core import mcp_client

                return self._send_json({"servers": mcp_client.status()})
            if path == "/api/routines":
                guest = self._sess["guest"]
                lang = i18n.get_lang()
                items = routines.default_routines(lang) if guest else routines.load(self._sess["id"], lang)
                return self._send_json({"routines": items, "blocks": list(routines.BLOCKS), "editable": not guest})
            me = re.fullmatch(r"/api/assistants/([a-z0-9_]{1,40})/export", path)
            if me:
                return self._export_assistant(me.group(1), parse_qs(urlsplit(self.path).query).get("docs", [""])[0] == "1")
            mk = re.fullmatch(r"/api/knowledge/([a-z0-9_]{1,40})", path)
            if mk:
                return self._send_json(self._knowledge_state(mk.group(1), edit=False))
            if path == "/api/reminders":
                return self._send_json({"reminders": [reminders.public(r) for r in
                                                      reminders.list_for(self._owner(), include_done=True)]})
            if path == "/api/dashboard":
                st = self._state()
                return self._send_json(dashboard.build_dashboard(
                    self._owner(), bool(self._sess.get("guest")), st.get("assistants") or []
                ))
            mfp = re.fullmatch(r"/api/files/([0-9a-z.]{1,40})/preview", path)
            if mfp:
                prev = dashboard.preview_file(mfp.group(1))
                if not prev:
                    return self._send_json({"error": tr("not_found")}, 404)
                return self._send_json(prev)
            mf = re.fullmatch(r"/api/files/([0-9a-z.]{1,40})", path)
            if mf:
                return self._send_attachment(mf.group(1))
            if path == "/api/models/updates":
                query = parse_qs(urlsplit(self.path).query)
                only = query.get("model", [""])[0]
                force = query.get("check", [""])[0] == "1"
                return self._send_json(model_updates.check(force=force, only=only if MODEL_NAME_RE.match(only) else None)
                                       if force or not only else model_updates.status())
            if path == "/api/dev/version":
                return self._send_json(dev_reload.static_version())
            if path == "/api/network":
                return self._send_json(network.status(local=not self._remote()))
            if path == "/api/ollama/update":
                force = parse_qs(urlsplit(self.path).query).get("check", [""])[0] == "1"
                return self._send_json(ollama_update.check(force))
            if path in ("/api/geo/search", "/api/geo/reverse"):
                return self._geo(path, parse_qs(urlsplit(self.path).query))
            if path == "/api/voice/events":
                query = parse_qs(urlsplit(self.path).query)
                after = query.get("after", ["0"])[0]
                try:
                    wait = float(query.get("wait", ["20"])[0])
                except ValueError:
                    wait = 20.0
                return self._send_json(LISTENER.poll(self._client_id(query.get("client", [""])[0]),
                                                     int(after) if after.isdigit() else 0, wait))
            if path == "/api/logs":
                after = parse_qs(urlsplit(self.path).query).get("after", ["0"])[0]
                return self._send_json(server_log.since(int(after) if after.isdigit() else 0))
            mpx = PLUGIN_HTTP_RE.fullmatch(path)
            if mpx:
                query = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
                return self._plugin_http("GET", mpx.group(1), mpx.group(2), query)
            return self._send_json({"error": tr("not_found")}, 404)

        self._handle(route)

    def _write(self, method: str) -> None:
        path = urlsplit(self.path).path
        if not self._guard(write=True, allow_audio=(path in ("/api/chat/transcribe", "/api/voices", "/api/wake/listen")),
                           allow_binary=(path in ("/api/chat/extract", "/api/files", "/api/backups/restore")
                                         or path.startswith("/api/knowledge/"))):
            # Se lee (y descarta) lo que mandó: cerrar la conexión con datos
            # sin leer la corta con un RST y el navegador pierde la respuesta
            # (pasaba por HTTPS, desde otro dispositivo).
            try:
                left = min(int(self.headers.get("Content-Length") or 0), MAX_VOICE_AUDIO)
                while left > 0:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    left -= len(chunk)
            except (OSError, ValueError):
                pass
            self.close_connection = True
            return
        m = re.fullmatch(r"/api/assistants/([a-z0-9_]+)", path)

        def route():
            if method == "POST" and path == "/api/chat/transcribe":
                return self._transcribe()
            if method == "POST" and path == "/api/wake/listen":
                return self._wake_listen()
            if method == "POST" and path == "/api/chat/extract":
                return self._extract()
            if method == "POST" and path == "/api/files/forget":
                # El invitado reinicia su chat (está en su navegador): los
                # archivos que subió se borran ya si nadie más los usa.
                ids = [str(x) for x in (self._body(MAX_BODY).get("ids") or [])][:200]
                return self._send_json({"removed": file_store.forget(ids)})
            if method == "POST" and path == "/api/files/delete":
                # Biblioteca del perfil (#/media, #/files): borrar uno o varios.
                if self._sess.get("guest"):
                    return self._send_json({"error": tr("role_forbidden")}, 403)
                ids = [str(x) for x in (self._body(MAX_BODY).get("ids") or [])][:500]
                result = dashboard.delete_files(self._owner(), False, self._state().get("assistants") or [], ids)
                if result["deleted"] or result["kept"]:
                    server_log.log("files", f"library: deleted {len(result['deleted'])} file(s), "
                                            f"removed {result['refs']} reference(s), kept {len(result['kept'])} in use elsewhere")
                return self._send_json(result)
            if method == "POST" and path == "/api/files":
                data = self._raw_body(file_store.MAX_BYTES)
                if not data:
                    raise store.ConfigError(tr("file_empty"))
                name = unquote(parse_qs(urlsplit(self.path).query).get("name", [""])[0])[:200]
                return self._send_json(file_store.save(name, data))
            if method == "POST" and path == "/api/voices":
                return self._add_voice()
            if path.startswith("/api/knowledge/"):
                return self._knowledge(method, path)
            if path.startswith("/api/backups"):
                return self._backups(method, path)
            mv = re.fullmatch(r"/api/voices/([a-z0-9][a-z0-9_-]{0,39})", path)
            if mv and method in ("PUT", "DELETE"):
                return self._edit_voice(method, mv.group(1), self._body())
            if method == "PUT" and path == "/api/voice-settings":
                data = self._body()
                voice_settings.update(**{k: data[k] for k in ("stt_model", "qwen_model", "qwen_python", "qwen_compile")
                                         if k in data})
                server_log.log("voice", f"voice settings: Whisper {voice_settings.stt_model()}, "
                                        f"Qwen3-TTS {voice_settings.load()['qwen_tts']['model']}")
                from app.voice.qwen_tts import engine as qwen_engine

                qwen_engine().release()  # con el modelo o el Python nuevos la próxima vez
                chat_runtime.prewarm_voices()
                return self._send_json({"state": self._state()})
            mc = re.fullmatch(r"/api/chats/([a-z0-9_]{1,40})", path)
            data = self._body(MAX_CHAT_BODY if path in ("/api/chat", "/api/assistants/import") or mc else MAX_BODY)
            if mc and method == "PUT":
                # Reiniciar el chat (se guarda vacío): sus archivos se borran
                # con él, salvo que otra conversación guardada los use.
                cleared = not data.get("messages") and not data.get("history")
                before = file_store.ids_in(chat_store.load(mc.group(1), self._sess["id"])) if cleared else set()
                result = chat_store.save(mc.group(1), data, self._sess["id"])
                if before:
                    gone = file_store.forget(before)
                    if gone:
                        server_log.log("chat", f"chat reset: deleted {gone} file(s) shared in it")
                return self._send_json(result)
            if path.startswith(("/api/session", "/api/profile")):
                return self._profiles(method, path, data)
            if path.startswith("/api/memory"):
                return self._memory(method, path, data)
            if path.startswith("/api/lists/"):
                return self._lists(method, path, data)
            if path.startswith("/api/plugins"):
                return self._plugins(method, path, data)
            mpx = PLUGIN_HTTP_RE.fullmatch(path)
            if mpx and method == "POST":
                return self._plugin_http("POST", mpx.group(1), mpx.group(2), data)
            if path.startswith("/api/mcp"):
                return self._mcp(method, path, data)
            if method == "POST" and path == "/api/diagnostics/fix":
                return self._diagnostics_fix(str(data.get("id") or ""))
            if method == "PUT" and path == "/api/routines":
                items = routines.save(self._sess["id"], data.get("routines"))
                return self._send_json({"routines": items, "blocks": list(routines.BLOCKS), "editable": True})
            if path.startswith(("/api/reminders", "/api/notify")):
                return self._reminders(method, path, data)
            if method == "POST" and path == "/api/assistants/import":
                return self._import_assistant(data)
            if method == "POST" and path == "/api/assistants":
                name = store.save_assistant(None, data.get("assistant") or {}, data.get("version"), _LANGUAGES,
                                            owner=self._sess["id"])
                chat_runtime.prewarm_voices()  # voz clonada nueva, o ya nadie la usa
                return self._send_json({"name": name, "state": self._state()})
            if method == "PUT" and m:
                self._check_editable(m.group(1))
                name = store.save_assistant(m.group(1), data.get("assistant") or {}, data.get("version"), _LANGUAGES)
                knowledge.rename_assistant(m.group(1), name)  # sus documentos lo siguen
                chat_runtime.prewarm_voices()
                return self._send_json({"name": name, "state": self._state()})
            if method == "DELETE" and m:
                self._check_editable(m.group(1))
                store.delete_assistant(m.group(1), data.get("version"))
                knowledge.delete_assistant(m.group(1))
                chat_runtime.prewarm_voices()
                return self._send_json({"state": self._state()})
            if method == "PUT" and path == "/api/shared":
                # Reglas compartidas y exclusiones (admin). Los datos de la
                # persona van en su perfil: PUT /api/profile/me.
                store.save_shared({k: v for k, v in data.items() if k != "user_context"}, data.get("version"))
                return self._send_json({"state": self._state()})
            if method == "POST" and path == "/api/preview":
                return self._send_json({"yaml": store.preview_assistant(data.get("assistant") or {})})
            if method == "POST" and path == "/api/wake-check":
                return self._send_json(store.wake_check(
                    data.get("name", ""), data.get("aliases"), data.get("original"), data.get("exclusions"),
                ))
            if path.startswith(("/api/llm/", "/api/hf/")):
                out = models_api(method, path, data, {})
                if out is not None:
                    return self._send_json(out)
            if method == "POST" and path == "/api/models/measure":
                return self._send_json(measure_model(str(data.get("model") or "")))
            if method == "POST" and path == "/api/models/update":
                return self._send_json(start_model_update(data.get("model")))
            if method == "DELETE" and path == "/api/models":
                return self._send_json(delete_model(str(data.get("model") or "")))
            if method == "PUT" and path == "/api/models/updates/auto":
                name = str(data.get("model") or "")
                if not MODEL_NAME_RE.match(name):
                    raise store.ConfigError(tr("pull_name_invalid"))
                return self._send_json(model_updates.set_auto(name, bool(data.get("auto"))))
            if method == "PUT" and path == "/api/network":
                network.set_enabled(bool(data.get("enabled")), Handler)
                return self._send_json(network.status(local=True))
            if method == "POST" and path == "/api/network/token":
                network.new_token()
                return self._send_json(network.status(local=True))
            if method == "POST" and path == "/api/ollama/update":
                try:
                    return self._send_json(ollama_update.start())
                except RuntimeError as e:
                    raise store.ConfigError(str(e))
            if method == "POST" and path == "/api/models/pull":
                return self._send_json(start_pull(data.get("model")))
            if method == "POST" and path == "/api/tts":
                return self._tts(data)
            if method == "POST" and path == "/api/chat":
                return self._chat(data)
            if method == "POST" and path == "/api/chat/route":
                return self._route_group(data)
            if method == "POST" and path.startswith("/api/voice/"):
                return self._voice(path, data)
            if method == "POST" and path == "/api/chat/unload":
                models = [str(x) for x in data.get("models") or [] if MODEL_NAME_RE.match(str(x))]
                chat_runtime.unload(models)
                return self._send_json({"ok": True})
            return self._send_json({"error": tr("not_found")}, 404)

        self._handle(route)

    def _check_editable(self, name: str) -> None:
        a = next((x for x in store.load_state()["assistants"] if x["name"] == name), None)
        if a is None or not can_see(a, self._sess):
            raise store.ConfigError(tr("assistant_missing", name=name), status=404)
        if not can_edit(a, self._sess):
            raise store.ConfigError(tr("assistant_forbidden"), status=403)

    def _profiles(self, method: str, path: str, data: dict) -> None:
        """Entrar/salir, el primer administrador, los datos propios y (admin)
        crear, cambiar y borrar perfiles."""
        if method == "POST" and path == "/api/profiles/setup":
            if not profiles.setup_needed():
                raise store.ConfigError(tr("setup_done"), status=409)
            p = profiles.create(data.get("name"), "admin", str(data.get("pin") or ""), data.get("color") or "")
            server_log.log("profiles", f"first profile (admin): {p['name']}")
            self._set_session(profiles.login(p["id"], str(data.get("pin") or "")))
            return self._send_json({"ok": True})
        if method == "POST" and path == "/api/session":
            token = profiles.login(str(data.get("profile") or ""), str(data.get("pin") or ""))
            self._set_session(token)
            return self._send_json({"ok": True})
        if method == "POST" and path == "/api/session/guest":
            self._set_session(profiles.guest_login(), guest=True)
            return self._send_json({"ok": True})
        if method == "DELETE" and path == "/api/session":
            profiles.logout(self._cookie_value(profiles.COOKIE))
            self._set_session(None)
            return self._send_json({"ok": True})
        if method == "PUT" and path == "/api/profile/me":
            return self._save_me(data)
        if method == "POST" and path == "/api/profiles":
            p = profiles.create(data.get("name"), data.get("role"), str(data.get("pin") or ""), data.get("color") or "")
            server_log.log("profiles", f"new profile: {p['name']} ({p['role']})")
            return self._send_json({"state": self._state()})
        mp = re.fullmatch(r"/api/profiles/(p[0-9a-f]{8})", path)
        if mp and method == "PUT":
            profiles.update(mp.group(1), name=data.get("name"), role=data.get("role"), pin=str(data.get("pin") or ""),
                            color=data.get("color"), clear_pin=bool(data.get("clear_pin")))
            self._sess = profiles.session(self._cookie_value(profiles.COOKIE))  # pudo cambiarse a sí mismo
            return self._send_json({"state": self._state()})
        if mp and method == "DELETE":
            if mp.group(1) == self._sess["id"]:
                raise store.ConfigError(tr("self_delete"))
            profiles.delete(mp.group(1))
            memory.delete_profile(mp.group(1))
            reminders.delete_owner(mp.group(1))
            lists.delete_owner(mp.group(1))
            routines.delete_owner(mp.group(1))
            store.transfer_owner(mp.group(1), self._sess["id"])  # sus asistentes no se pierden
            server_log.log("profiles", f"deleted profile: {mp.group(1)}")
            return self._send_json({"state": self._state()})
        return self._send_json({"error": tr("not_found")}, 404)

    def _save_me(self, data: dict) -> None:
        """Datos de la persona (nombre, país, ubicación) y, opcionalmente, su
        nombre de perfil, color y PIN (el actual hace falta para cambiarlo)."""
        errors = {}
        uc = store.validate_user_context(data.get("user_context") or {}, errors)
        if errors:
            raise store.ConfigError(tr("check_fields"), errors)
        me = self._sess
        if any(k in data for k in ("name", "color", "pin", "pin_confirm", "clear_pin")):
            pin_arg = ""
            if data.get("clear_pin"):
                pin_arg = "__clear__"
            elif data.get("pin") or data.get("pin_confirm"):
                new_pin = str(data.get("pin") or "")
                confirm_pin = str(data.get("pin_confirm") or "")
                if not profiles.PIN_RE.match(new_pin):
                    raise store.ConfigError(tr("pin_format"), {"me.pin": tr("pin_format")}, status=400)
                if new_pin != confirm_pin:
                    raise store.ConfigError(tr("pin_mismatch"), {"me.pin_confirm": tr("pin_mismatch")}, status=400)
                pin_arg = new_pin
            profiles.update(me["id"], name=data.get("name"), pin=pin_arg, color=data.get("color"))
        profiles.set_user_context(me["id"], uc)
        self._sess = profiles.session(self._cookie_value(profiles.COOKIE))
        return self._send_json({"state": self._state()})

    def _memory(self, method: str, path: str, data: dict) -> None:
        """Lo que recuerdan de ti (ver app/skills/memory.py): agregar,
        corregir, olvidar uno u olvidar todo."""
        pid = self._sess["id"]
        mm = re.fullmatch(r"/api/memory/(m[0-9a-f]{6})", path)
        try:
            if method == "POST" and path == "/api/memory":
                memory.add(pid, data.get("text"), "")
            elif method == "PUT" and mm:
                memory.edit(pid, mm.group(1), data.get("text"))
            elif method == "DELETE" and mm:
                memory.remove(pid, mm.group(1))
            elif method == "DELETE" and path == "/api/memory":
                memory.clear(pid)
                server_log.log("memory", f"{self._sess['name']} cleared all remembered facts for their profile")
            else:
                return self._send_json({"error": tr("not_found")}, 404)
        except KeyError:
            raise store.ConfigError(tr("memory_missing"), status=404)
        except ValueError:
            raise store.ConfigError(tr("memory_empty"))
        return self._send_json({"facts": memory.public(memory.load(pid))})

    def _owner(self) -> str:
        """De quién son los datos propios (recordatorios, avisos): el perfil,
        o la sesión del invitado."""
        if not self._sess["guest"]:
            return self._sess["id"]
        import hashlib

        return "g-" + hashlib.sha256(self._cookie_value(profiles.COOKIE).encode()).hexdigest()[:16]

    def _reminders(self, method: str, path: str, data: dict) -> None:
        """Recordatorios (ver app/skills/reminders.py): borrar, posponer, y
        qué página los dice en voz alta en la PC."""
        if method == "POST" and path == "/api/notify/claim":
            if self._remote():
                return self._send_json({"speak": False})
            try:
                return self._send_json({"speak": notify.claim(int(data.get("id")))})
            except (TypeError, ValueError):
                raise store.ConfigError(tr("json_invalid"))
        owner = self._owner()
        mr = re.fullmatch(r"/api/reminders/(r[0-9a-f]{6})(/snooze)?", path)
        if mr and method == "DELETE" and not mr.group(2):
            reminders.cancel(owner, mr.group(1))
        elif mr and method == "POST" and mr.group(2):
            try:
                minutes = min(24 * 60, max(1.0, float(data.get("minutes") or 10)))
            except (TypeError, ValueError):
                minutes = 10.0
            try:
                reminders.snooze(owner, mr.group(1), minutes)
            except KeyError:
                raise store.ConfigError(tr("reminder_missing"), status=404)
        else:
            return self._send_json({"error": tr("not_found")}, 404)
        return self._send_json({"reminders": [reminders.public(r) for r in reminders.list_for(owner, include_done=True)]})

    def _export_assistant(self, name: str, with_docs: bool) -> None:
        """Descarga del asistente como .auravox (ver assistant_io.py)."""
        a = next((x for x in store.load_state()["assistants"] if x["name"] == name), None)
        if a is None or not can_see(a, self._sess):
            raise store.ConfigError(tr("assistant_missing", name=name), status=404)
        body = json.dumps(assistant_io.export(name, with_docs), ensure_ascii=False, indent=1).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote((a['label'] or name) + '.auravox')}")
        self.end_headers()
        self.wfile.write(body)
        server_log.log("assistants", f"exported: {name}{' (with documents)' if with_docs else ''}")

    def _import_assistant(self, data: dict) -> None:
        try:
            result = assistant_io.import_file(data.get("file"), self._sess["id"], self._sess["role"] == "admin", _LANGUAGES)
        except assistant_io.ImportError_ as e:
            raise store.ConfigError(tr(e.key, **e.params))
        chat_runtime.prewarm_voices()
        server_log.log("assistants", f"imported: {result['name']}")
        notes = [tr(k, **p) for k, p in result["notes"]]
        return self._send_json({"name": result["name"], "notes": notes, "model": result["model"], "state": self._state()})

    def _plugin_http(self, method: str, pid: str, action: str, data: dict) -> None:
        """Rutas propias de un plugin (p. ej. el progreso de una imagen de
        ComfyUI): las puede usar quien tenga su rol mínimo (ver
        app/core/plugins.http)."""
        from app.core import plugins

        ctx = self._skill_ctx({}, {}, None, "text", None)
        status, out = plugins.http(pid, method, action, data, ctx)
        if status == 403:
            return self._send_json({"error": tr("role_forbidden")}, 403)
        if status == 404:
            return self._send_json({"error": tr("not_found")}, 404)
        return self._send_json(out, status)

    def _plugins(self, method: str, path: str, data: dict) -> None:
        """Ajustes → Plugins (admin): activar/desactivar, rol mínimo y volver
        a leer la carpeta (ver app/core/plugins.py)."""
        from app.core import plugins

        mp = re.fullmatch(r"/api/plugins/([a-z0-9_]{2,40})", path)
        mc = re.fullmatch(r"/api/plugins/([a-z0-9_]{2,40})/check", path)
        if method == "POST" and mc:
            result = plugins.check(mc.group(1))
            if result is None:
                return self._send_json({"error": tr("not_found")}, 404)
            return self._send_json({"ok": result[0], "message": result[1]})
        if method == "POST" and path == "/api/plugins/reload":
            plugins.discover(force=True)
        elif method == "PUT" and mp:
            if not any(p.id == mp.group(1) for p in plugins.discover()):
                raise store.ConfigError(tr("plugin_missing"), status=404)
            plugins.configure(mp.group(1), data.get("enabled") if "enabled" in data else None,
                              data.get("min_role") if data.get("min_role") in plugins.ROLES else None)
            if isinstance(data.get("settings"), dict):
                plugins.set_settings(mp.group(1), data["settings"])
            server_log.log("plugins", f"{mp.group(1)}: {'enabled' if data.get('enabled') else 'disabled' if 'enabled' in data else ''}"
                                      f"{' min_role ' + data['min_role'] if data.get('min_role') else ''}")
        else:
            return self._send_json({"error": tr("not_found")}, 404)
        return self._send_json({"plugins": plugins.public(), "folder": plugins.PLUGINS_DIR})

    def _send_download(self, path: str, name: str, ctype: str) -> None:
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(name)}")
        self.end_headers()
        with open(path, "rb") as f:
            while chunk := f.read(1 << 20):
                self.wfile.write(chunk)

    def _backups(self, method: str, path: str) -> None:
        """Respaldo y restauración (admin, ver backup.py)."""
        mb = re.fullmatch(r"/api/backups/(auravox-[a-z0-9-]{1,60}\.zip)(/restore)?", path)
        if method == "POST" and path == "/api/backups/restore":
            # El zip subido tal cual (application/octet-stream).
            try:
                tmp = backup.save_upload(self.rfile, int(self.headers.get("Content-Length") or 0))
            except backup.RestoreError as e:
                raise store.ConfigError(tr(str(e)))
            try:
                return self._restore_from(tmp, "uploaded")
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        data = self._body()
        if method == "POST" and path == "/api/backups":
            b = backup.create("manual", attachments=bool(data.get("attachments")), secrets=bool(data.get("secrets")))
            server_log.log("backup", f"backup created: {b['name']} ({b['size'] / 1024 / 1024:.1f} MB, {b['files']} files)")
            return self._send_json({"created": b, "backups": backup.list_backups(), "folder": backup.BACKUPS_DIR})
        if mb and method == "DELETE" and not mb.group(2):
            try:
                backup.delete(mb.group(1))
            except (KeyError, OSError):
                raise store.ConfigError(tr("not_found"), status=404)
            return self._send_json({"backups": backup.list_backups(), "folder": backup.BACKUPS_DIR})
        if mb and method == "POST" and mb.group(2):
            try:
                return self._restore_from(backup.path_of(mb.group(1)), mb.group(1))
            except KeyError:
                raise store.ConfigError(tr("not_found"), status=404)
        return self._send_json({"error": tr("not_found")}, 404)

    def _restore_from(self, zip_path: str, label: str) -> None:
        try:
            result = backup.restore(zip_path)
        except backup.RestoreError as e:
            raise store.ConfigError(tr(str(e)))
        server_log.log("backup", f"restored {label}: {result['files']} files (safety backup saved to {result['safety']})")
        # Lo que se lee al arrancar o se guarda en memoria, de nuevo.
        from app.core import mcp_client, plugins

        plugins.discover(force=True)
        mcp_client.restart()
        chat_runtime.prewarm_voices()
        self._sess = profiles.session(self._cookie_value(profiles.COOKIE))
        if not self._sess:
            self._set_session(None)
            return self._send_json({"restored": result, "relogin": True})
        return self._send_json({"restored": result, "backups": backup.list_backups(), "folder": backup.BACKUPS_DIR})

    def _diagnostics(self) -> dict:
        """Pantalla de diagnóstico (ver diagnostics.py)."""
        from app.webui import diagnostics as dg

        lan = network.status(local=not self._remote())
        checks = (dg.check_ollama(list_models, ollama_update.status()) + dg.check_gpu() + dg.check_disk()
                  + dg.check_voice(LISTENER.state(), chat_runtime.status(), LISTENER.enabled)
                  + dg.check_ports(self.server.server_address[1] if not getattr(self.server, "lan", False) else DEFAULT_PORT, lan)
                  + dg.check_firewall(lan) + dg.check_extras())
        return {"checks": checks, "local": not self._remote(), "at": time.time()}

    _SYSTEM_FIXES = {"firewall_allow", "net_private", "ollama_start", "ollama_tune", "lan_restart", "mic_unmute", "mic_retry"}

    def _diagnostics_fix(self, fix: str) -> None:
        from app.webui import diagnostics as dg

        if fix in self._SYSTEM_FIXES and self._remote():
            raise store.ConfigError(tr("lan_local_only"), status=403)
        ok, note = True, ""
        if fix == "ollama_start":
            ok = dg.start_ollama()
        elif fix == "ollama_tune":
            ok = dg.fix_ollama_tuning()
        elif fix == "free_vram":
            try:
                loaded = [m.get("name") for m in requests.get(f"{OLLAMA_URL}/api/ps", timeout=4).json().get("models") or []]
            except (requests.exceptions.RequestException, ValueError):
                loaded = []
            chat_runtime.unload([m for m in loaded if m])
        elif fix == "pull_recommended":
            model = dg.recommended_model()
            start_pull(model)
            note = model
        elif fix == "pull_embed":
            start_pull("nomic-embed-text")
            note = "nomic-embed-text"
        elif fix == "mic_unmute":
            LISTENER.set_muted(False)
        elif fix == "mic_retry":
            LISTENER.stop()
            LISTENER._stop.clear()  # noqa: SLF001 — vuelve a arrancar el mismo hilo de escucha
            LISTENER.start()
        elif fix == "lan_restart":
            network.stop()
            network.start(Handler)
            ok = network.status(local=True)["running"]
        elif fix == "firewall_allow":
            ok = dg.fix_firewall(int(network.settings().get("port") or 8443))
        elif fix == "net_private":
            ok = dg.fix_network_private()
        else:
            return self._send_json({"error": tr("not_found")}, 404)
        server_log.log("diagnostics", f"fix {fix}: {'done' if ok else 'failed'}{' (' + note + ')' if note else ''}",
                       "info" if ok else "warn")
        return self._send_json({"ok": ok, "note": note, **self._diagnostics()})

    def _mcp(self, method: str, path: str, data: dict) -> None:
        """Ajustes → Servidores MCP (admin): agregar, cambiar, quitar y
        reconectar (ver app/core/mcp_client.py)."""
        from app.core import mcp_client

        mm = re.fullmatch(r"/api/mcp/([a-z0-9_]{2,24})(/restart)?", path)
        try:
            if method == "POST" and path == "/api/mcp":
                s = mcp_client.add_server(data)
                server_log.log("mcp", f"server added: {s['name']} ({s['transport']})")
            elif mm and method == "POST" and mm.group(2):
                mcp_client.restart(mm.group(1))
            elif mm and method == "PUT" and not mm.group(2):
                mcp_client.update_server(mm.group(1), data)
            elif mm and method == "DELETE" and not mm.group(2):
                mcp_client.remove_server(mm.group(1))
                server_log.log("mcp", f"server removed: {mm.group(1)}")
            else:
                return self._send_json({"error": tr("not_found")}, 404)
        except ValueError as e:
            raise store.ConfigError(tr(str(e)))
        except KeyError:
            raise store.ConfigError(tr("mcp_missing"), status=404)
        except OverflowError as e:
            raise store.ConfigError(tr("list_full", n=str(e)))
        return self._send_json({"servers": mcp_client.status()})

    def _knowledge_state(self, name: str, edit: bool) -> dict:
        """Documentos de un asistente (ver app/skills/knowledge.py)."""
        a = next((x for x in store.load_state()["assistants"] if x["name"] == name), None)
        if a is None or not can_see(a, self._sess):
            raise store.ConfigError(tr("assistant_missing", name=name), status=404)
        if edit and not can_edit(a, self._sess):
            raise store.ConfigError(tr("assistant_forbidden"), status=403)
        from app.core import embeddings

        return {"files": knowledge.files(name), "embeddings": embeddings.available(),
                "indexing": knowledge.indexing(name), "editable": can_edit(a, self._sess)}

    def _knowledge(self, method: str, path: str) -> None:
        """Subir (el archivo tal cual, o el texto que sacó la página de un
        PDF), borrar un documento o calcular los embeddings que falten."""
        mk = re.fullmatch(r"/api/knowledge/([a-z0-9_]{1,40})(?:/(d[0-9a-f]{8}|index))?", path)
        if not mk:
            return self._send_json({"error": tr("not_found")}, 404)
        name, sub = mk.group(1), mk.group(2)
        self._knowledge_state(name, edit=True)
        who = self._sess.get("name") or ""
        if method == "POST" and not sub:
            query = parse_qs(urlsplit(self.path).query)
            if self.headers.get("Content-Type", "").startswith("application/octet-stream"):
                fname = unquote(query.get("name", [""])[0])[:200]
                raw = self._raw_body(attachments.MAX_BYTES)
                if not raw:
                    raise store.ConfigError(tr("file_empty"))
                try:
                    result = attachments.extract_text(fname, raw, limit=knowledge.MAX_TEXT)
                except attachments.UnsupportedFile as e:
                    raise store.ConfigError(tr("file_unsupported", name=fname, error=e), status=415)
                text, fmt = result["text"], result["format"]
            else:
                data = self._body(MAX_CHAT_BODY)
                fname = str(data.get("name") or "")[:200]
                text, fmt = str(data.get("text") or ""), str(data.get("format") or "")[:20]
            try:
                entry = knowledge.add(name, fname, text, by=who, fmt=fmt)
            except ValueError:
                raise store.ConfigError(tr("knowledge_empty", name=fname))
            except OverflowError as e:
                raise store.ConfigError(tr("knowledge_full", n=str(e)))
            server_log.log("documents", f"{name}: «{entry['name']}» ({entry['chars']} chars) added by {who}")
        elif method == "DELETE" and sub and sub != "index":
            self._raw_body(MAX_BODY)
            knowledge.remove(name, sub)
        elif method == "POST" and sub == "index":
            self._raw_body(MAX_BODY)
            knowledge.index_async(name)
        else:
            return self._send_json({"error": tr("not_found")}, 404)
        return self._send_json(self._knowledge_state(name, edit=False))

    def _lists_state(self) -> dict:
        """Listas y notas (ver app/skills/lists.py): las propias (no el
        invitado) y las de la casa."""
        personal = None if self._sess["guest"] else lists.load(self._sess["id"])
        return {"personal": personal, "home": lists.load(lists.HOME)}

    def _lists(self, method: str, path: str, data: dict) -> None:
        ml = re.fullmatch(r"/api/lists/(personal|home)", path)
        if not ml or method != "POST":
            return self._send_json({"error": tr("not_found")}, 404)
        guest = self._sess["guest"]
        if ml.group(1) == "personal" and guest:
            raise store.ConfigError(tr("role_forbidden"), status=403)
        if guest and data.get("op") in ("delete", "rename"):
            raise store.ConfigError(tr("role_forbidden"), status=403)
        scope = lists.HOME if ml.group(1) == "home" else self._sess["id"]
        try:
            lists.apply(scope, data, by=self._sess.get("name") or "")
        except FileExistsError as e:
            raise store.ConfigError(tr("list_exists", name=str(e)), status=409)
        except OverflowError as e:
            raise store.ConfigError(tr("list_full", n=str(e)))
        except KeyError:
            raise store.ConfigError(tr("list_missing"), status=404)
        except ValueError:
            raise store.ConfigError(tr("list_empty"))
        return self._send_json(self._lists_state())

    def _skill_ctx(self, data: dict, cfg: dict, emit, style: str, lang) -> "skills.Ctx":
        """Quién pregunta, para las habilidades (memoria, recordatorios…)."""
        sess = self._sess
        owner = self._owner()
        if sess["guest"]:
            guest_data = data.get("guest_data") if isinstance(data.get("guest_data"), dict) else {}
        else:
            guest_data = {}
        name = str((data.get("assistant") or {}).get("name") or "")
        return skills.Ctx(profile=None if sess["guest"] else sess["id"], role=sess["role"] if not sess["guest"] else "guest",
                          owner=owner, guest_data=guest_data, assistant=name if store.NAME_RE.match(name) else "",
                          cfg=cfg, emit=emit, style=style, lang=lang)

    @staticmethod
    def _client_id(value) -> str:
        value = str(value or "")
        if not CLIENT_RE.match(value):
            raise store.ConfigError(tr("json_invalid"))
        return value

    def _voice(self, path: str, data: dict) -> None:
        """Escucha manos libres (ver voice_listener.py): qué pestaña
        responde, silenciar el micrófono, qué está haciendo la página y
        abrir/cerrar la conversación desde el botón."""
        client = self._client_id(data.get("client"))
        if path == "/api/voice/claim":
            return self._send_json(LISTENER.claim(client))
        if path == "/api/voice/mute":
            return self._send_json(LISTENER.set_muted(bool(data.get("muted"))))
        if path == "/api/voice/client":
            LISTENER.report(client, data)
            return self._send_json({"ok": True})
        if path == "/api/voice/pause":
            return self._send_json(LISTENER.set_paused(client, bool(data.get("paused"))))
        if path == "/api/voice/session":
            if data.get("open"):
                name = str(data.get("assistant") or "")
                return self._send_json(LISTENER.open_session(client, name if store.NAME_RE.match(name) else None))
            return self._send_json(LISTENER.close_session(client))
        return self._send_json({"error": tr("not_found")}, 404)

    _geo_cache = {}

    def _geo(self, path: str, query: dict) -> None:
        """Mapa de "Ajustes compartidos": buscar un lugar por nombre y
        convertir el punto elegido en un nombre legible, vía Nominatim
        (OpenStreetMap) desde el servidor, con el User-Agent y el límite de
        1 petición/s que pide su política de uso."""
        lang = i18n.get_lang()
        try:
            if path == "/api/geo/search":
                q = (query.get("q", [""])[0] or "").strip()[:200]
                if not q:
                    return self._send_json({"results": []})
                key = ("s", q.lower(), lang)
                if key not in self._geo_cache:
                    self._geo_cache[key] = assistant_common.search_places(q, lang)
                    server_log.log("map", f"search «{q}»: {len(self._geo_cache[key])} result(s)")
                return self._send_json({"results": self._geo_cache[key]})
            lat, lon = float(query["lat"][0]), float(query["lon"][0])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
            key = ("r", round(lat, 5), round(lon, 5), lang)
            if key not in self._geo_cache:
                self._geo_cache[key] = assistant_common.reverse_geocode(lat, lon, lang)
                server_log.log("map", f"{lat:.6f}, {lon:.6f} → {self._geo_cache[key]['label'] or '(unnamed)'}")
            return self._send_json(self._geo_cache[key])
        except (KeyError, ValueError):
            raise store.ConfigError(tr("coord_range", limit=180))
        except requests.exceptions.RequestException as e:
            raise store.ConfigError(tr("geo_failed", error=e), status=502)

    def _tts(self, data: dict) -> None:
        text = str(data.get("text") or "").strip()[:2000]
        voice = normalize_voice(data.get("voice"))
        if not text or not is_valid_voice(voice):
            raise store.ConfigError(tr("voice_invalid"))
        try:
            speed = min(2.0, max(0.5, float(data.get("speed") or 1.0)))
        except (TypeError, ValueError):
            speed = 1.0
        try:
            wav = chat_runtime.synthesize(text, voice, speed, str(data.get("lang") or "es"))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            raise store.ConfigError(tr("tts_failed", error=e), status=500)
        self._send_bytes(wav, "audio/wav")

    def _add_voice(self) -> None:
        """Voz clonada nueva a partir de un audio (lo que el navegador sube:
        un archivo o una grabación) de hasta 10 minutos: se elige lo mejor
        de él como referencia y su texto, ver voice_reference.py."""
        import io

        import soundfile as sf
        from faster_whisper import decode_audio

        data = self._raw_body(MAX_VOICE_AUDIO)
        if not data:
            raise store.ConfigError(tr("audio_empty"))
        query = parse_qs(urlsplit(self.path).query)
        name = (query.get("name", [""])[0] or "").strip()[:40] or "Voz"
        lang = query.get("lang", ["es"])[0]
        lang = lang if lang in _LANGUAGES else "es"
        fallback = (query.get("fallback", ["M5"])[0] or "M5").upper()
        try:
            audio = decode_audio(io.BytesIO(data), sampling_rate=24000)
        except Exception as e:  # noqa: BLE001
            raise store.ConfigError(tr("voice_audio_bad", error=e))
        if len(audio) / 24000 < voice_reference.MIN_SECONDS:
            raise store.ConfigError(tr("voice_audio_short"))
        audio = audio[: int(voice_reference.MAX_SOURCE_SECONDS * 24000)]
        pcm16k = decode_audio(io.BytesIO(data), sampling_rate=16000)[: int(voice_reference.MAX_SOURCE_SECONDS * 16000)]
        t0 = time.time()
        try:
            segments = chat_runtime.transcribe_words(pcm16k, lang)
        except Exception as e:  # noqa: BLE001 — sin texto la voz igual sirve (solo el timbre)
            server_log.log("voice", f"could not transcribe reference audio ({e})", "warn")
            segments = []
        result = voice_reference.build(audio, pcm16k, segments)
        vid = voice_settings.new_voice_id(name)
        os.makedirs(paths.CUSTOM_VOICES_DIR, exist_ok=True)
        sf.write(os.path.join(paths.CUSTOM_VOICES_DIR, f"{vid}.wav"), result["ref"], 24000, subtype="PCM_16")
        full_audio = ""
        if result["full"] is not None:
            full_audio = f"custom_voices/{vid}.full.wav"
            sf.write(os.path.join(paths.CONFIG_DIR, full_audio), result["full"], 24000, subtype="PCM_16")
        voice_settings.add_voice({"id": vid, "name": name, "audio": f"custom_voices/{vid}.wav", "full_audio": full_audio,
                                  "ref_text": result["ref_text"], "language": lang, "fallback_voice": fallback})
        server_log.log("voice", f"new cloned voice «{name}» ({vid}): {result['seconds']:.0f}s analysed in "
                                f"{time.time() - t0:.1f}s, {result['phrases']} phrases, {result['used']:.1f}s reference, "
                                f"{0 if result['full'] is None else len(result['full']) / 24000:.0f}s for timbre: "
                                f"«{result['ref_text'][:80]}»")
        self._send_json({"id": vid, "state": self._state(),
                         "reference": {k: round(result[k], 1) for k in ("seconds", "used")} | {"phrases": result["phrases"]}})

    def _edit_voice(self, method: str, vid: str, data: dict) -> None:
        if not voice_settings.get_voice(vid):
            raise store.ConfigError(tr("voice_missing", id=vid), status=404)
        code = voice_settings.CUSTOM_PREFIX + vid
        if method == "DELETE":
            users = [a["label"] or a["name"].upper() for a in store.load_state()["assistants"] if a["voice"] == code]
            if users:
                raise store.ConfigError(tr("voice_in_use", names=", ".join(users)), status=409)
            voice_settings.delete_voice(vid)
            server_log.log("voice", f"deleted cloned voice: {vid}")
        else:
            changes = {k: data[k] for k in ("name", "ref_text", "language", "fallback_voice") if k in data}
            if "language" in changes and changes["language"] not in _LANGUAGES:
                changes.pop("language")
            voice_settings.edit_voice(vid, changes)
        self._send_json({"state": self._state()})

    def _transcribe(self) -> None:
        query = parse_qs(urlsplit(self.path).query)
        if query.get("file", [""])[0] == "1":
            return self._transcribe_file(query)
        audio = self._raw_body(MAX_AUDIO)
        if not audio:
            raise store.ConfigError(tr("audio_empty"))
        langs = [c for c in (query.get("langs", [""])[0]).split(",") if c in _LANGUAGES]
        hint = query.get("hint", [""])[0]
        try:
            skip = min(30.0, max(0.0, float(query.get("skip", ["0"])[0])))
        except ValueError:
            skip = 0.0
        if query.get("probe", [""])[0] == "1":
            return self._send_json(chat_runtime.probe_speech(audio, langs, hint if hint in _LANGUAGES else None, skip))
        try:
            text, lang = chat_runtime.transcribe(audio, langs, hint if hint in _LANGUAGES else None, skip)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            raise store.ConfigError(tr("stt_failed", error=e), status=500)
        # Los nombres de los asistentes como se llaman de verdad ("Harvis" →
        # "Jarvis", "CG" → "Ziggy", "Джарвис" → "Jarvis"), igual que en manos libres.
        # `confident`: si Whisper dudó del idioma (frases cortas: "Buenos días"
        # salió como inglés), la página deja que el modelo decida el idioma de
        # la respuesta por el texto.
        self._send_json({"text": LISTENER.canonicalize(text), "lang": lang,
                         "confident": bool(getattr(chat_runtime.transcribe, "last_confident", True))})

    def _wake_listen(self) -> None:
        """Escucha por nombre desde el navegador (el celular u otro
        dispositivo): la página detecta la voz (VAD por energía), manda cada
        frase y aquí Whisper la pasa a texto y se busca el nombre de un
        asistente que ESE perfil puede usar, igual que voice_listener.py con
        el micrófono de la PC. {"text", "lang", "wake", "remainder"}."""
        audio = self._raw_body(MAX_AUDIO)
        if not audio:
            raise store.ConfigError(tr("audio_empty"))
        visible = visible_assistants(self._sess)
        callable_ = [a for a in visible if a.get("wake_word")]
        if not callable_:
            return self._send_json({"text": "", "lang": None, "wake": None, "remainder": ""})
        langs = sorted({c for a in callable_ for c in (a.get("languages") or _LANGUAGES)} & set(_LANGUAGES)) or _LANGUAGES
        try:
            text, lang = chat_runtime.transcribe(audio, langs, None)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            raise store.ConfigError(tr("stt_failed", error=e), status=500)
        aliases, exclusions = ww.load_wake_words()
        names_all = {a["name"]: {ww.normalize(a["name"])} | set(aliases.get(a["name"], set())) for a in visible}
        names_wake = {n: v for n, v in names_all.items() if n in {a["name"] for a in callable_}}
        display = {a["name"]: (a.get("label") or a["name"]).title() for a in visible}
        text = ww.canonicalize(text, names_all, exclusions, display, ww.DEFAULT_RATIO) if text else ""
        wake, rest = ww.find_wake_word(text, names_wake, exclusions, ww.DEFAULT_RATIO) if text else (None, "")
        if text:
            server_log.log("stt (browser)", f"«{text[:80]}» [{lang}] → {('called ' + wake) if wake else 'no wake word'}")
        return self._send_json({"text": text, "lang": lang, "wake": wake, "remainder": rest or ""})

    def _transcribe_file(self, query) -> None:
        """Un audio (o video) adjunto en el chat escrito → texto. A
        diferencia de lo que se dice por el micrófono, puede ser largo y en
        cualquier idioma: Whisper lo detecta solo."""
        audio = self._raw_body(MAX_AUDIO_FILE)
        if not audio:
            raise store.ConfigError(tr("audio_empty"))
        name = unquote(query.get("name", [""])[0])[:120]
        try:
            text, lang, seconds = chat_runtime.transcribe_file(audio, name)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            raise store.ConfigError(tr("stt_failed", error=e), status=500)
        self._send_json({"text": text, "lang": lang, "seconds": round(seconds, 1)})

    def _send_attachment(self, file_id: str) -> None:
        """Un adjunto original (ver file_store): en el navegador, con su nombre."""
        found = file_store.open_file(file_id)
        if not found:
            return self._send_json({"error": tr("not_found")}, 404)
        path, ctype, name = found
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "private, max-age=86400")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(name)}")
        self.end_headers()
        with open(path, "rb") as f:
            while chunk := f.read(1 << 20):
                self.wfile.write(chunk)

    def _extract(self) -> None:
        """Texto de un documento adjunto (ver app/core/attachments.py)."""
        data = self._raw_body(attachments.MAX_BYTES)
        name = unquote(parse_qs(urlsplit(self.path).query).get("name", [""])[0])[:200]
        if not data:
            raise store.ConfigError(tr("file_empty"))
        try:
            result = attachments.extract_text(name, data)
        except attachments.UnsupportedFile as e:
            raise store.ConfigError(tr("file_unsupported", name=name, error=e), status=415)
        cut = " (truncated)" if result["truncated"] else ""
        server_log.log("attachment", f"«{name}» ({result['format']}, {len(data) / 1024:.0f} KB): "
                                     f"{result['chars']} chars{cut}")
        self._send_json(result)

    def _chat(self, data: dict) -> None:
        """Respuesta en streaming (una línea JSON por evento): {"type":
        "tool", "name": ...} cuando el modelo usa una herramienta (la
        interfaz muestra "Buscando en internet..." y lo anuncia por voz, como
        voice_loop.py), {"type": "delta", "text"} con la respuesta mientras
        se genera, {"type": "say", "text", "lang"} en modo voz con cada frase
        lista para sintetizar (en cola, sin esperar el resto), {"type":
        "reset"} si lo mostrado/dicho se descarta (la página lo borra y corta
        la voz) y al final {"type": "reply", ...} o {"type": "error"}."""
        cfg, shared_context, history, lang, style, auto_langs, group = _chat_request(data, self._sess)
        # Datos de quién pregunta: los de su perfil, o los que manda la
        # página del invitado (los tiene en su navegador).
        if self._sess["guest"]:
            user_ctx = store.validate_user_context(data.get("user_context") or {}, {})
        else:
            user_ctx = self._sess["user_context"]
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        def emit(event: dict) -> None:
            self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

        skill_ctx = self._skill_ctx(data, cfg, emit, style, lang)
        if data.get("barge") and history and self._only_stop(cfg, history):
            # Lo interrumpió hablando solo para que se callara ("para", "ya,
            # gracias", "silencio"…): no se responde nada.
            emit({"type": "silent"})
            return
        # Modo voz: frases para la voz a medida que llegan. Sin idioma fijado
        # (Whisper dudó) se dicen al final, cuando el revisor ya dijo en qué
        # idioma salió la respuesta (la voz lo necesita).
        chunker = assistant_common.SpeechChunker() if style == "voice" else None

        def on_text(kind: str, text: str) -> None:
            if kind == "reset":
                if chunker:
                    chunker.reset()
                emit({"type": "reset"})
                return
            emit({"type": "delta", "text": text})
            if chunker and lang:
                for sentence in chunker.feed(text):
                    emit({"type": "say", "text": sentence, "lang": lang})

        try:
            shared_context, history = self._fold_history(data, cfg, shared_context, history, group, emit)
            with assistant_common.user_context_for(user_ctx):
                reply, reply_lang = chat_runtime.chat(
                    cfg, shared_context, history, lang,
                    on_tool_call=lambda name: emit({"type": "tool", "name": name}),
                    style=style,
                    auto_langs=auto_langs,
                    # Lugares encontrados: la página los muestra en un mapa.
                    on_places=lambda found: emit({"type": "places", **found}),
                    # Invitó o sacó a un asistente: la página arma la conversación.
                    group=group,
                    on_group=lambda action, who: emit({"type": "group", "action": action, "assistant": who}),
                    # Saludo al entrar / despedida al salir de la conversación.
                    cue=data.get("cue") if data.get("cue") in chat_runtime.CUES else None,
                    # Archivo convertido (convert_file): la página muestra para descargarlo.
                    on_file=lambda f: emit({"type": "file", **f}),
                    # Memoria, recordatorios, listas, documentos… (app/core/skills.py)
                    skill_ctx=skill_ctx,
                    on_text=on_text,
                )
            if chunker:
                rest = chunker.flush() if lang else _speech_chunks(reply)
                for sentence in rest:
                    emit({"type": "say", "text": sentence, "lang": reply_lang})
            emit({"type": "reply", "text": reply, "lang": reply_lang})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # La página cortó la respuesta (barge-in, salió del chat): al
            # cerrarse la conexión con Ollama, deja de generar.
            server_log.log("chat", f"{(cfg.get('label') or cfg.get('name') or '?').upper()}: browser aborted the response")
        except requests.exceptions.ConnectionError:
            emit({"type": "error", "message": tr("ollama_down")})
        except requests.exceptions.RequestException as e:
            emit({"type": "error", "message": tr("ollama_failed", error=e)})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            emit({"type": "error", "message": tr("internal", error=e)})

    @staticmethod
    def _only_stop(cfg: dict, history: list) -> bool:
        """¿El último mensaje (dicho interrumpiendo al asistente) solo le pide
        que se calle o que pare? Lo juzga el modelo, en cualquier idioma."""
        schema = {"type": "object", "properties": {
            "reasoning": {"type": "string"},
            "intent": {"type": "string", "enum": ["only_stop_talking", "something_else"]},
        }, "required": ["reasoning", "intent"]}
        system = ("The user interrupted a voice assistant while it was talking and said the LAST USER line. Decide if that "
                  "line ONLY asks it to stop or be quiet (\"stop\", \"enough\", \"ok, thanks, that's it\", \"shh\", in any "
                  "language) and asks nothing else: \"only_stop_talking\". If it asks, says or corrects anything else (a "
                  "new question, \"stop, I meant Paris\", \"wait, and tomorrow?\"), \"something_else\". Write "
                  "\"reasoning\" first: one short sentence.")
        from app.core.assistant_engine import OLLAMA_URL

        t0 = time.time()
        data = assistant_common.structured_request(OLLAMA_URL, cfg["base_model"], [
            {"role": "system", "content": system},
            {"role": "user", "content": assistant_common.render_transcript(history, last=3)},
        ], schema, keep_alive=chat_runtime.CHAT_KEEP_ALIVE) or {}
        stop = data.get("intent") == "only_stop_talking"
        server_log.log("chat", f"interrupted: {'only asked to stop talking' if stop else 'said something else'} in {time.time() - t0:.1f}s "
                               f"(«{str(data.get('reasoning', ''))[:100]}»)")
        return stop

    @staticmethod
    def _fold_history(data: dict, cfg: dict, shared_context: str, history: list, group: dict, emit) -> tuple:
        """Resumen de chats largos: si la conversación pasa max_history, lo
        más viejo se resume (chat_runtime.summarize) junto con el resumen que
        ya traía la página, y se le avisa a la página cuántos mensajes de su
        historial ya están en el resumen (evento "summary": los quita y manda
        el resumen en las próximas preguntas)."""
        summary = str(data.get("summary") or "")[:chat_store.SUMMARY_MAX]
        limit = cfg["max_history"]
        raw = group.pop("raw", [])
        if len(history) > limit and not data.get("cue"):
            keep = max(4, limit // 2)
            # Que lo que queda empiece con un mensaje del usuario.
            while keep < len(history) - 1 and history[-keep]["role"] != "user":
                keep += 1
            folded = chat_runtime.summarize(cfg, summary, history[:-keep])
            if folded:
                first = raw[-keep] if len(raw) == len(history) else None
                drop = next((i for i, m in enumerate(data.get("history") or []) if m is first), None)
                if drop is not None:
                    summary = folded
                    history = history[-keep:]
                    emit({"type": "summary", "text": summary, "drop": drop})
        if summary:
            shared_context = ((shared_context + "\n\n") if shared_context else "") + chat_runtime.SUMMARY_NOTE.format(summary=summary)
        return shared_context, history

    def _route_group(self, data: dict) -> None:
        """Conversación grupal: a quién le habló el usuario (lo decide el
        modelo, ver chat_runtime.route_addressees)."""
        draft = {k: v for k, v in (data.get("assistant") or {}).items() if k in store.KNOWN_FIELDS}
        cfg = store.assistant_view(str((data.get("assistant") or {}).get("name") or "nuevo"), draft)
        history, _raw, labels = _group_history({**data, "speaker": ""})
        outsiders = {str(o["key"]): str(o.get("label") or o["key"]).upper()[:40]
                     for o in data.get("outsiders") or [] if isinstance(o, dict) and o.get("key")}
        if (len(labels) < 2 and not outsiders) or not history:
            return self._send_json({"keys": [], "all": False})
        try:
            return self._send_json(chat_runtime.route_addressees(cfg, history, labels, outsiders))
        except requests.exceptions.RequestException:
            return self._send_json({"keys": [], "all": False})

    def do_POST(self):
        self._write("POST")

    def do_PUT(self):
        self._write("PUT")

    def do_DELETE(self):
        self._write("DELETE")


class _Server(ThreadingHTTPServer):
    # http.server activa SO_REUSEADDR, y en Windows eso deja que DOS procesos
    # escuchen el MISMO puerto: al reabrir AuraVox.bat con una ventana
    # vieja todavía abierta, las peticiones seguían yendo al servidor viejo
    # (con la página nueva) y todo fallaba a medias. Con uso exclusivo del
    # puerto, el segundo proceso falla al abrirlo y pasa al siguiente.
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


# ── Recordatorios: avisarlos al vencer (ver app/skills/reminders.py) ──
_speak_lock = threading.Lock()


def _reminder_fired(r: dict, missed: bool) -> None:
    """Aviso a las páginas del perfil; si en unos segundos ninguna página
    de la PC lo dijo (no hay ninguna abierta, o es de otro perfil), lo dice
    el servidor por los altavoces."""
    event = notify.push(r["owner"], "reminder", missed=missed, reminder=reminders.public(r),
                        voice=r.get("voice"), speed=r.get("speed"), lang=r.get("lang"))
    when = "missed (server was off)" if missed else "now"
    server_log.log("reminder", f"{r['label'] or 'assistant'} → {r['kind']} {when}: «{r['text']}»")
    if missed:
        return

    def speak_later():
        time.sleep(6)
        if notify.claimed(event["id"]):
            return
        notify.claim(event["id"])
        _speak_on_pc(r)

    threading.Thread(target=speak_later, name="reminder-speak", daemon=True).start()


def _speak_on_pc(r: dict) -> None:
    import winsound

    with _speak_lock:
        try:
            if r.get("kind") == "alarm":
                for _ in range(3):
                    for freq in (880, 1175, 1568):
                        winsound.Beep(freq, 140)
                    time.sleep(0.25)
            else:
                winsound.Beep(1175, 120)
                winsound.Beep(1568, 160)
            wav = chat_runtime.synthesize(r.get("say") or r["text"], normalize_voice(r.get("voice")) or "M5",
                                          float(r.get("speed") or 1.0), r.get("lang") or "es")
            winsound.PlaySound(wav, winsound.SND_MEMORY)
            server_log.log("reminder", f"spoken over PC speakers: «{r.get('say') or r['text']}»")
        except Exception as e:  # noqa: BLE001 — sin audio o sin voz: queda la notificación
            server_log.log("reminder", f"could not speak over PC speakers: {e}", "warn")


def _safe(fn) -> None:
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        server_log.log("backup", f"could not create automatic backup: {e}", "warn")


def _routine_due(pid: str, r: dict) -> None:
    """Una rutina con hora: la corre el asistente elegido (o el primero que
    ese perfil puede usar) y se avisa como un recordatorio."""
    p = next((x for x in profiles.list_public() if x["id"] == pid), None)
    if not p:
        return
    sess = {"id": pid, "guest": False, "role": p["role"]}
    visible = [a for a in store.load_state()["assistants"] if can_see(a, sess)]
    a = next((x for x in visible if x["name"] == r.get("assistant")), None) or (visible[0] if visible else None)
    if not a:
        return
    cfg = store.assistant_view(a["name"], {k: v for k, v in a.items() if k in store.KNOWN_FIELDS})
    data = profiles._load()  # noqa: SLF001 — sus datos (nombre, ubicación) para el clima y el saludo
    uc = next((x.get("user_context") or {} for x in data["profiles"] if x["id"] == pid), {})
    ctx = skills.Ctx(profile=pid, role=p["role"], owner=pid, assistant=a["name"], cfg=cfg, style="voice",
                     lang=cfg["language"])
    history = [{"role": "user", "content": f"(It's {r['time']}: scheduled routine.) Run my routine \"{r['name']}\"."}]
    server_log.log("routine", f"{p['name']}: «{r['name']}» with {a['label'] or a['name']} ({r['time']})")
    try:
        with assistant_common.user_context_for(uc):
            reply, lang = chat_runtime.chat(cfg, store.load_state()["shared_context"], history, cfg["language"],
                                            style="voice", skill_ctx=ctx)
    except Exception as e:  # noqa: BLE001
        server_log.log("routine", f"could not run «{r['name']}»: {e}", "warn")
        return
    _reminder_fired({"id": "r000000", "owner": pid, "text": r["name"], "say": reply, "kind": "routine",
                     "due": time.time(), "repeat": "none", "assistant": a["name"],
                     "label": (a["label"] or a["name"]).upper(), "voice": cfg["voice"], "speed": cfg["speed"],
                     "lang": lang, "state": "done"}, False)


def _running_instance(port: int):
    """api_version de una interfaz que ya esté escuchando en `port` (None si
    no hay ninguna; 0 si es una versión vieja que no la informa)."""
    try:
        r = requests.get(f"http://127.0.0.1:{port}/api/state", timeout=2)
        return r.json().get("api_version", 0) if r.ok else None
    except (requests.exceptions.RequestException, ValueError):
        return None


def _bind(port: int) -> ThreadingHTTPServer:
    last_error = None
    for candidate in range(port, port + 10):
        try:
            return _Server(("127.0.0.1", candidate), Handler)
        except OSError as e:
            last_error = e
    raise SystemExit(f"Could not bind any port between {port} and {port + 9} ({last_error}).")


def main():
    parser = argparse.ArgumentParser(description="AuraVox Web UI and local assistant server.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    parser.add_argument("--no-voice", action="store_true",
                        help="disable hands-free listening (do not open the server microphone)")
    parser.add_argument("--log", default=paths.WEBUI_LOG, help="log file path (default: logs/webui_server.log)")
    parser.add_argument("--no-reload", action="store_true",
                        help="disable hot reload (do not restart automatically on code changes)")
    args = parser.parse_args()
    global LISTENER
    existing = _running_instance(args.port)
    # Recarga en caliente (dev_reload.py): este proceso solo vigila el código
    # y lanza el servidor de verdad como hijo.
    if not args.no_reload and not dev_reload.is_child() and existing != API_VERSION:
        sys.exit(dev_reload.supervise(sys.argv[1:]))
    dev_reload.install_child_signals()
    # Registro de esta ejecución en logs/webui_server.log (se sobreescribe;
    # en un reinicio por recarga en caliente, se sigue en el mismo).
    server_log.install(args.log, append=os.environ.get("AURAVOX_RESTART") == "1")

    if existing == API_VERSION:
        url = f"http://127.0.0.1:{args.port}/"
        print(f"The AuraVox Web UI is already running at {url} (in another window); opening it in your browser.")
        if not args.no_browser:
            webbrowser.open(url)
        return
    if existing is not None:
        print("=" * 72)
        print(f"WARNING: an OLDER version of the Web UI is running on port {args.port}.")
        print("Close that AuraVox window (and the old browser tab);")
        print("meanwhile, this instance will open on another port.")
        print("=" * 72)

    print("AuraVox: starting web interface...")
    _LANGUAGES[:] = pipeline_languages()
    store.load_state()  # falla temprano (con un mensaje claro) si assistants.yaml tiene un error

    server = _bind(args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    # Escucha manos libres: abre el micrófono recién cuando hay una página
    # abierta (y no está silenciado desde la interfaz).
    LISTENER = VoiceListener(enabled=not args.no_voice)
    LISTENER.start()
    chat_runtime.prewarm_voices()  # voces clonadas: en segundo plano
    model_updates.auto_loop(start_pull, pull_status)  # versiones nuevas de los modelos
    network.start(Handler)  # acceso desde otros dispositivos de la red (HTTPS)
    file_store.cleanup(force=True)  # adjuntos que ya no usa ninguna conversación
    reminders.start(_reminder_fired)  # recordatorios, alarmas y temporizadores
    routines.start(_routine_due)  # rutinas con hora ("Buenos días" a las 7:00)
    # Un respaldo automático por día (sin adjuntos ni claves; ver backup.py).
    threading.Thread(target=lambda: _safe(backup.auto_daily), name="backup-auto", daemon=True).start()
    from app.core import mcp_client
    import atexit

    mcp_client.start_all(lambda msg, level="info": server_log.log("mcp", msg, level))  # servidores MCP, en segundo plano
    atexit.register(mcp_client.stop_all)
    # Una lista cambió (por chat o desde otra página): las páginas abiertas la recargan.
    lists.on_change = lambda scope: notify.push("*" if scope == lists.HOME else scope, "lists", scope="home" if scope == lists.HOME else "personal")
    print(f"\nAuraVox ready at {url}")
    if network.status(local=True)["running"]:
        print("From other devices on your local network (the access link with key and QR code are in Shared Settings):")
        for lan_url in network.urls(with_key=False):
            print(f"  {lan_url}")
    if LISTENER.enabled:
        print("Hands-free: while the web page is open, call any assistant by name "
              "(you can mute the microphone from the top bar).")
    print("Keep this window open while using AuraVox (press Ctrl+C to quit).\n")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        LISTENER.stop()
        network.stop()
        server.server_close()
        chat_runtime.unload()
    print("Web interface closed.")


if __name__ == "__main__":
    main()
