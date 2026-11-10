"""Historial de la conversación (escrita y por voz) de cada asistente.

La página lo guarda aquí al cambiar algo y lo recupera al volver a abrir el
asistente: así no se pierde al ir a la galería, al recargar ni al abrirlo
desde otro dispositivo de la red local. Cada perfil tiene las suyas (ver
profiles.py), un archivo por asistente en config/chats/<perfil>/<asistente>.json;
"Reiniciar" en el chat lo borra. Las del invitado no pasan por aquí: quedan
en su navegador.

Para que no crezca sin fin se guardan los últimos MAX_MESSAGES mensajes, y
las imágenes (que pesan) solo en los últimos KEEP_IMAGES mensajes que las
tengan: de los anteriores quedan el nombre y la descripción.
"""
import json
import os
import re
import threading
import time

from app import paths
from app.webui import profiles

CHATS_DIR = os.path.join(paths.CONFIG_DIR, "chats")
NAME_RE = re.compile(r"^[a-z0-9_]{1,40}$")
MAX_MESSAGES = 120
MAX_HISTORY = 80
KEEP_IMAGES = 6
SUMMARY_MAX = 8000
_lock = threading.Lock()


def _path(name: str, profile: str) -> str:
    if not NAME_RE.match(name or ""):
        raise ValueError("nombre de asistente inválido")
    return os.path.join(profiles.chats_dir(profile), f"{name}.json")


def rename_assistant(old: str, new: str) -> None:
    """La conversación de cada perfil pasa al nombre nuevo (si ya hay una con
    ese nombre, se deja la que estaba: no se pisa nada)."""
    if old == new or not NAME_RE.match(old or "") or not NAME_RE.match(new or ""):
        return
    with _lock:
        if not os.path.isdir(CHATS_DIR):
            return
        for profile in os.listdir(CHATS_DIR):
            src = os.path.join(CHATS_DIR, profile, f"{old}.json")
            dst = os.path.join(CHATS_DIR, profile, f"{new}.json")
            if os.path.isfile(src) and not os.path.exists(dst):
                os.replace(src, dst)


def load(name: str, profile: str) -> dict:
    try:
        with open(_path(name, profile), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _trim(data: dict) -> dict:
    messages = [m for m in data.get("messages") or [] if isinstance(m, dict)][-MAX_MESSAGES:]
    history = [m for m in data.get("history") or [] if isinstance(m, dict)][-MAX_HISTORY:]
    # Imágenes solo en los últimos KEEP_IMAGES mensajes que las tienen.
    with_thumbs = [i for i, m in enumerate(messages) if any(f.get("thumb") for f in m.get("files") or [] if isinstance(f, dict))]
    for i in with_thumbs[:-KEEP_IMAGES]:
        messages[i]["files"] = [{**f, "thumb": None} for f in messages[i]["files"]]
    with_images = [i for i, m in enumerate(history) if m.get("images")]
    for i in with_images[:-KEEP_IMAGES]:
        history[i] = {k: v for k, v in history[i].items() if k != "images"}
    return {
        "messages": messages,
        "history": history,
        "guests": [g for g in data.get("guests") or [] if isinstance(g, str) and NAME_RE.match(g)][:8],
        "lang": str(data.get("lang") or "auto")[:10],
        # Resumen de lo más viejo (ver chat_runtime.summarize).
        "summary": str(data.get("summary") or "")[:SUMMARY_MAX],
        "updated_at": time.time(),
    }


def save(name: str, data: dict, profile: str) -> dict:
    path = _path(name, profile)
    trimmed = _trim(data)
    with _lock:
        if not trimmed["messages"] and not trimmed["history"]:
            if os.path.exists(path):
                os.remove(path)  # conversación reiniciada
            return {"updated_at": trimmed["updated_at"]}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, ensure_ascii=False)
        os.replace(tmp, path)
    return {"updated_at": trimmed["updated_at"]}
