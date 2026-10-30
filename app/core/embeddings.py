"""Embeddings con Ollama (nomic-embed-text), para elegir lo relevante
cuando hay mucho: los hechos de la memoria de un perfil o los trozos de los
documentos de un asistente.

Es opcional: si el modelo no está instalado (o Ollama no responde), quien
llama sigue con su alternativa (lo más reciente, o la búsqueda por
palabras de los documentos). Se instala desde la interfaz como cualquier
modelo (`ollama pull nomic-embed-text`, ~270 MB).
"""
import math
import time

import requests

from app.core.assistant_common import SERVER_KEEP_ALIVE

OLLAMA = "http://127.0.0.1:11434"
MODEL = "nomic-embed-text"
_available = {"at": 0.0, "ok": False}


def available() -> bool:
    """¿Está instalado el modelo de embeddings? (se pregunta cada 60 s)"""
    now = time.time()
    if now - _available["at"] < 60:
        return _available["ok"]
    ok = False
    try:
        r = requests.get(f"{OLLAMA}/api/tags", timeout=3)
        names = {m.get("name", "") for m in r.json().get("models") or []}
        ok = any(n == MODEL or n.startswith(MODEL + ":") for n in names)
    except (requests.exceptions.RequestException, ValueError):
        ok = False
    _available.update(at=now, ok=ok)
    return ok


def embed(texts: list, kind: str = "document"):
    """Vectores de `texts` (lista de listas de float), o None si no se pudo.
    nomic-embed-text distingue lo que se guarda ("search_document: …") de lo
    que se busca ("search_query: …")."""
    if not texts or not available():
        return None
    prefix = "search_query: " if kind == "query" else "search_document: "
    out = []
    try:
        for i in range(0, len(texts), 32):
            r = requests.post(f"{OLLAMA}/api/embed", json={
                "model": MODEL, "input": [prefix + t[:2000] for t in texts[i:i + 32]], "keep_alive": SERVER_KEEP_ALIVE,
            }, timeout=120)
            r.raise_for_status()
            out += r.json()["embeddings"]
    except (requests.exceptions.RequestException, ValueError, KeyError):
        return None
    return out if len(out) == len(texts) else None


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
