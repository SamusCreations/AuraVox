"""
Ajustes de voz compartidos por todos los asistentes, en
config/voice_settings.yaml (se editan desde "Ajustes compartidos" de la
interfaz web):

- `stt_model`: qué Whisper usar para entender ("small", ligero, o
  "large-v3-turbo", pesado; ver STT_MODELS).
- `qwen_tts`: el motor de voces clonadas (Qwen3-TTS) — qué tamaño de modelo
  y con qué Python correrlo (necesita torch; por defecto el de ComfyUI si
  está al lado de esta carpeta, ver default_qwen_python()).
- `custom_voices`: las voces clonadas a partir de un audio de referencia.
  Cada asistente las elige igual que las de Supertonic (`voice:
  custom:<id>` en assistants.yaml).
"""
import hashlib
import os
import re
import threading

import yaml

from app import paths

# Whisper para entender lo que se dice (ver la comparación en el README).
STT_MODELS = {
    "small": "Ligero — Whisper small",
    "large-v3-turbo": "Pesado — Whisper large-v3-turbo",
}
DEFAULT_STT_MODEL = "large-v3-turbo"  # medido: ver la nota 12 del README

# Qwen3-TTS "Base" (el que clona voces), descargado en cache/qwen-tts.
QWEN_MODELS = {
    "0.6B": "Qwen3-TTS-12Hz-0.6B-Base",
    "1.7B": "Qwen3-TTS-12Hz-1.7B-Base",
}
DEFAULT_QWEN_MODEL = "0.6B"

CUSTOM_PREFIX = "custom:"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_LOCK = threading.RLock()

_HEADER = """\
# Ajustes de voz compartidos por todos los asistentes. Se editan desde
# "Ajustes compartidos" en la interfaz web (AuraVox.bat).
#
#   stt_model       Whisper para entender: small (ligero) | large-v3-turbo (pesado)
#   qwen_tts        Voces clonadas con Qwen3-TTS:
#     model         0.6B (menos VRAM) | 1.7B (mejor parecido)
#     compile       true = ~3 veces más rápido, pero tarda 1,5-4 min en prepararse al arrancar
#     python        Python con torch para correrlo ("" = el de ComfyUI si está)
#   custom_voices   Voces clonadas: audio de referencia (en custom_voices/), lo
#                   que se dice en él (ref_text), su idioma y la voz de
#                   Supertonic que se usa en los idiomas que Qwen3-TTS no habla.
"""


def default_qwen_python() -> str:
    """El Python de ComfyUI-Easy-Install si está junto a esta carpeta (ya
    trae torch con CUDA), o "" si no se encuentra."""
    parent = os.path.dirname(paths.ROOT)
    for candidate in (
        os.path.join(parent, "ComfyUI-Easy-Install", "python_embeded", "python.exe"),
        os.path.join(parent, "ComfyUI_windows_portable", "python_embeded", "python.exe"),
    ):
        if os.path.isfile(candidate):
            return candidate
    return ""


def _clean_voice(raw: dict) -> dict:
    vid = str(raw.get("id") or "").strip().lower()
    if not ID_RE.match(vid):
        return None
    audio = str(raw.get("audio") or f"custom_voices/{vid}.wav").replace("\\", "/")
    fallback = str(raw.get("fallback_voice") or "M5").strip().upper()
    return {
        "id": vid,
        "name": str(raw.get("name") or vid).strip()[:40],
        "audio": audio,
        "ref_text": " ".join(str(raw.get("ref_text") or "").split())[:1000],
        "language": str(raw.get("language") or "es").strip().lower()[:5],
        "fallback_voice": fallback if re.fullmatch(r"[FM][1-5]", fallback) else "M5",
    }


def load() -> dict:
    with _LOCK:
        try:
            with open(paths.VOICE_SETTINGS_YAML, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except (FileNotFoundError, yaml.YAMLError):
            raw = {}
    qwen = raw.get("qwen_tts") or {}
    stt = str(raw.get("stt_model") or DEFAULT_STT_MODEL)
    model = str(qwen.get("model") or DEFAULT_QWEN_MODEL)
    voices = [v for v in (_clean_voice(x) for x in raw.get("custom_voices") or [] if isinstance(x, dict)) if v]
    return {
        "stt_model": stt if stt in STT_MODELS else DEFAULT_STT_MODEL,
        "qwen_tts": {
            "model": model if model in QWEN_MODELS else DEFAULT_QWEN_MODEL,
            "python": str(qwen.get("python") or "").strip(),
            "compile": qwen.get("compile", True) is not False,
        },
        "custom_voices": voices,
    }


def save(data: dict) -> None:
    out = {
        "stt_model": data["stt_model"],
        "qwen_tts": {"model": data["qwen_tts"]["model"], "python": data["qwen_tts"].get("python", ""),
                     "compile": bool(data["qwen_tts"].get("compile", True))},
        "custom_voices": [
            {k: v[k] for k in ("id", "name", "audio", "ref_text", "language", "fallback_voice")}
            for v in data["custom_voices"]
        ],
    }
    text = _HEADER + "\n" + yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=100)
    with _LOCK:
        os.makedirs(paths.CONFIG_DIR, exist_ok=True)
        tmp = paths.VOICE_SETTINGS_YAML + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, paths.VOICE_SETTINGS_YAML)


def update(**changes) -> dict:
    with _LOCK:
        data = load()
        if "stt_model" in changes and changes["stt_model"] in STT_MODELS:
            data["stt_model"] = changes["stt_model"]
        if "qwen_model" in changes and changes["qwen_model"] in QWEN_MODELS:
            data["qwen_tts"]["model"] = changes["qwen_model"]
        if "qwen_python" in changes:
            data["qwen_tts"]["python"] = str(changes["qwen_python"] or "").strip()
        if "qwen_compile" in changes:
            data["qwen_tts"]["compile"] = bool(changes["qwen_compile"])
        save(data)
        return data


def stt_model() -> str:
    return load()["stt_model"]


# ── Voces clonadas ─────────────────────────────────────────────────────

def is_custom(code) -> bool:
    return isinstance(code, str) and code.lower().startswith(CUSTOM_PREFIX)


def custom_id(code: str) -> str:
    return code[len(CUSTOM_PREFIX):].lower() if is_custom(code) else ""


def custom_voices() -> list:
    return load()["custom_voices"]


def get_voice(code_or_id: str):
    """La voz clonada (con la ruta absoluta de su audio y una marca que
    cambia si se edita: `stamp`), o None si no existe."""
    vid = custom_id(code_or_id) if is_custom(code_or_id) else str(code_or_id or "").lower()
    for v in custom_voices():
        if v["id"] == vid:
            path = os.path.join(paths.CONFIG_DIR, v["audio"])
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                return None
            stamp = hashlib.sha1(f"{mtime}|{v['ref_text']}".encode("utf-8")).hexdigest()[:10]
            return {**v, "code": CUSTOM_PREFIX + vid, "path": path, "stamp": stamp}
    return None


def voice_codes() -> set:
    """Códigos válidos de voces clonadas ("custom:<id>")."""
    return {CUSTOM_PREFIX + v["id"] for v in custom_voices()}


def add_voice(voice: dict) -> dict:
    with _LOCK:
        data = load()
        clean = _clean_voice(voice)
        if not clean:
            raise ValueError("id de voz inválido")
        data["custom_voices"] = [v for v in data["custom_voices"] if v["id"] != clean["id"]] + [clean]
        save(data)
        return clean


def edit_voice(vid: str, changes: dict) -> dict:
    with _LOCK:
        data = load()
        for i, v in enumerate(data["custom_voices"]):
            if v["id"] == vid:
                merged = _clean_voice({**v, **{k: changes[k] for k in ("name", "ref_text", "language", "fallback_voice")
                                               if k in changes}})
                data["custom_voices"][i] = merged
                save(data)
                return merged
        raise KeyError(vid)


def delete_voice(vid: str) -> None:
    with _LOCK:
        data = load()
        voice = next((v for v in data["custom_voices"] if v["id"] == vid), None)
        if not voice:
            raise KeyError(vid)
        data["custom_voices"] = [v for v in data["custom_voices"] if v["id"] != vid]
        save(data)
        try:
            os.remove(os.path.join(paths.CONFIG_DIR, voice["audio"]))
        except OSError:
            pass


def new_voice_id(name: str) -> str:
    """Un id libre a partir del nombre ("Mi voz" → "mi-voz", "mi-voz-2"...)."""
    import unicodedata

    base = "".join(c for c in unicodedata.normalize("NFD", name.lower()) if unicodedata.category(c) != "Mn")
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:30] or "voz"
    taken = {v["id"] for v in custom_voices()}
    vid, n = base, 2
    while vid in taken:
        vid, n = f"{base}-{n}", n + 1
    return vid
