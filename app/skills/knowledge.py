"""Documentos del asistente (RAG local).

Cada asistente puede tener una carpeta de conocimiento: manuales, apuntes,
recetas… (config/knowledge/<asistente>/). Al subir un documento se saca su
texto (con la misma extracción de los adjuntos, app/core/attachments.py;
los PDF los lee la página con pdf.js), se parte en trozos y, si está
nomic-embed-text, se calcula el embedding de cada trozo en segundo plano.

En la conversación el modelo tiene la herramienta search_documents: busca
los trozos más parecidos a la pregunta (por embeddings, o por palabras con
BM25 si no hay modelo de embeddings) y responde citando el documento.
"""
import json
import math
import os
import re
import secrets
import shutil
import threading
import time
import traceback
import unicodedata

from app import paths
from app.core import embeddings

NAME = "knowledge"
MIN_ROLE = "guest"

KNOWLEDGE_DIR = os.path.join(paths.CONFIG_DIR, "knowledge")
NAME_RE = re.compile(r"^[a-z0-9_]{1,40}$")
FILE_ID_RE = re.compile(r"^d[0-9a-f]{8}$")
MAX_FILES = 200
MAX_TEXT = 3_000_000       # por documento
MAX_TOTAL_CHUNKS = 20_000  # por asistente
CHUNK = 1000
OVERLAP = 150
TOP_K = 5

SEARCH = "search_documents"

_lock = threading.RLock()
_indexing = set()  # asistentes con embeddings calculándose


def _dir(assistant: str) -> str:
    if not NAME_RE.match(assistant or ""):
        raise ValueError("asistente inválido")
    return os.path.join(KNOWLEDGE_DIR, assistant)


def _read(assistant: str) -> dict:
    try:
        with open(os.path.join(_dir(assistant), "index.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data["files"] = [f for f in data.get("files") or [] if isinstance(f, dict) and FILE_ID_RE.match(str(f.get("id")))]
    data["chunks"] = [c for c in data.get("chunks") or [] if isinstance(c, dict) and c.get("text")]
    return data


def _write(assistant: str, data: dict) -> None:
    folder = _dir(assistant)
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, "index.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(folder, "index.json"))


def files(assistant: str) -> list:
    with _lock:
        data = _read(assistant)
    embedded = {}
    for c in data["chunks"]:
        e = embedded.setdefault(c["file"], [0, 0])
        e[1] += 1
        e[0] += 1 if isinstance(c.get("emb"), list) else 0
    out = []
    for f in data["files"]:
        done, total = embedded.get(f["id"], (0, 0))
        out.append({**{k: f.get(k) for k in ("id", "name", "chars", "added", "by", "format")},
                    "chunks": total, "embedded": done})
    return out


def has_documents(assistant: str) -> bool:
    if not NAME_RE.match(assistant or ""):
        return False
    return os.path.exists(os.path.join(_dir(assistant), "index.json")) and bool(files(assistant))


# ── Trozos ─────────────────────────────────────────────────────────────

def _chunks(text: str) -> list:
    """Trozos de ~CHUNK caracteres, cortando en párrafos u oraciones, con
    un poco de solapamiento para no partir una idea por la mitad."""
    text = re.sub(r"\n{3,}", "\n\n", text.replace("\r", "")).strip()
    parts = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + CHUNK)
        if end < n:
            window = text[start:end]
            cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(". "))
            if cut > CHUNK * 0.5:
                end = start + cut + 1
        piece = text[start:end].strip()
        if piece:
            parts.append(piece)
        if end >= n:
            break
        start = max(end - OVERLAP, start + 1)
    return parts


def add(assistant: str, name: str, text: str, by: str = "", fmt: str = "") -> dict:
    name = re.sub(r"[\x00-\x1f\x7f/\\]", "_", str(name or "documento")).strip()[:120] or "documento"
    text = str(text or "")[:MAX_TEXT].strip()
    if not text:
        raise ValueError("empty")
    pieces = _chunks(text)
    with _lock:
        data = _read(assistant)
        if len(data["files"]) >= MAX_FILES:
            raise OverflowError(MAX_FILES)
        # Mismo nombre: se reemplaza (una versión nueva del manual).
        old = {f["id"] for f in data["files"] if f["name"].lower() == name.lower()}
        data["files"] = [f for f in data["files"] if f["id"] not in old]
        data["chunks"] = [c for c in data["chunks"] if c["file"] not in old]
        if len(data["chunks"]) + len(pieces) > MAX_TOTAL_CHUNKS:
            raise OverflowError(MAX_TOTAL_CHUNKS)
        fid = "d" + secrets.token_hex(4)
        entry = {"id": fid, "name": name, "chars": len(text), "added": time.time(), "by": by, "format": fmt}
        data["files"].append(entry)
        data["chunks"] += [{"file": fid, "i": i, "text": p} for i, p in enumerate(pieces)]
        _write(assistant, data)
    index_async(assistant)
    return entry


def remove(assistant: str, fid: str) -> bool:
    with _lock:
        data = _read(assistant)
        if not any(f["id"] == fid for f in data["files"]):
            return False
        data["files"] = [f for f in data["files"] if f["id"] != fid]
        data["chunks"] = [c for c in data["chunks"] if c["file"] != fid]
        _write(assistant, data)
        return True


def delete_assistant(assistant: str) -> None:
    with _lock:
        shutil.rmtree(_dir(assistant), ignore_errors=True)


def rename_assistant(old: str, new: str) -> None:
    with _lock:
        if old != new and os.path.isdir(_dir(old)) and not os.path.exists(_dir(new)):
            os.replace(_dir(old), _dir(new))


# ── Embeddings en segundo plano ────────────────────────────────────────

def index_async(assistant: str) -> bool:
    """Calcula los embeddings que falten (si está nomic-embed-text)."""
    if not embeddings.available():
        return False
    with _lock:
        if assistant in _indexing:
            return True
        _indexing.add(assistant)
    threading.Thread(target=_index, args=(assistant,), name=f"rag-{assistant}", daemon=True).start()
    return True


def _index(assistant: str) -> None:
    try:
        while True:
            with _lock:
                data = _read(assistant)
                todo = [(i, c["text"]) for i, c in enumerate(data["chunks"]) if not isinstance(c.get("emb"), list)][:64]
            if not todo:
                return
            vecs = embeddings.embed([text for _, text in todo])
            if not vecs:
                return
            with _lock:
                data = _read(assistant)
                for (i, text), v in zip(todo, vecs):
                    if i < len(data["chunks"]) and data["chunks"][i]["text"] == text:
                        data["chunks"][i]["emb"] = [round(x, 5) for x in v]
                _write(assistant, data)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    finally:
        with _lock:
            _indexing.discard(assistant)


def indexing(assistant: str) -> bool:
    with _lock:
        return assistant in _indexing


# ── Búsqueda ───────────────────────────────────────────────────────────

def _tokens(text: str) -> list:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return [w for w in re.findall(r"\w+", text) if len(w) > 1]


def _bm25(query: str, chunks: list) -> list:
    """Puntaje BM25 de cada trozo para `query`: palabras en común, pesadas
    por lo raras que son (sirve en cualquier idioma, sin listas de palabras)."""
    q = set(_tokens(query))
    if not q:
        return [0.0] * len(chunks)
    docs = [_tokens(c["text"]) for c in chunks]
    n = len(docs)
    avg = sum(len(d) for d in docs) / max(n, 1)
    df = {w: sum(1 for d in docs if w in set(d)) for w in q}
    scores = []
    for d in docs:
        tf = {}
        for w in d:
            if w in q:
                tf[w] = tf.get(w, 0) + 1
        s = 0.0
        for w, f in tf.items():
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(d) / max(avg, 1)))
        scores.append(s)
    return scores


def search(assistant: str, query: str, k: int = TOP_K) -> list:
    with _lock:
        data = _read(assistant)
    chunks = data["chunks"]
    if not chunks or not query.strip():
        return []
    names = {f["id"]: f["name"] for f in data["files"]}
    lexical = _bm25(query, chunks)
    scores = lexical
    if all(isinstance(c.get("emb"), list) for c in chunks) and embeddings.available():
        qv = embeddings.embed([query], "query")
        if qv:
            top = max(lexical) or 1.0
            # Embeddings + un poco de BM25 (nombres propios y códigos exactos).
            scores = [embeddings.cosine(qv[0], c["emb"]) + 0.15 * (lx / top) for c, lx in zip(chunks, lexical)]
    order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    out = []
    for i in order[:k]:
        if scores[i] <= 0:
            break
        c = chunks[i]
        out.append({"file": names.get(c["file"], "?"), "part": c["i"] + 1, "text": c["text"], "score": round(scores[i], 3)})
    return out


# ── Habilidad ──────────────────────────────────────────────────────────

def context(ctx) -> str:
    if not has_documents(ctx.assistant):
        return ""
    names = [f["name"] for f in files(ctx.assistant)]
    shown = ", ".join(names[:40]) + (f" and {len(names) - 40} more" if len(names) > 40 else "")
    return (f"YOUR DOCUMENTS: you have a knowledge folder with these documents: {shown}. When the user asks something "
            f"those documents may answer (their content, procedures, data, recipes, notes…), call {SEARCH} first and "
            "base your answer on what it returns, citing the document it came from (e.g. \"según el manual.pdf…\" or "
            "a short \"Source: manual.pdf\" at the end). If the search doesn't find it, say it's not in your "
            "documents before answering from your general knowledge.")


def tools(ctx) -> list:
    if not has_documents(ctx.assistant):
        return []
    return [{"type": "function", "function": {
        "name": SEARCH,
        "description": "Search your own knowledge documents (manuals, notes, recipes the user gave you) for the passages that answer a question.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "What to look for: the question or its key terms, in the language of the documents if you know it."},
        }, "required": ["query"]},
    }}]


def call(name: str, args: dict, ctx):
    if name != SEARCH:
        return None
    query = str(args.get("query") or "").strip()[:500]
    if not query:
        query = " ".join(str(m.get("content", ""))[:300] for m in ctx.history[-1:] if m.get("role") == "user")
    hits = search(ctx.assistant, query)
    if not hits:
        return "Nothing relevant was found in your documents for that. Say so, and then answer from general knowledge if you can."
    ctx.emit({"type": "sources", "sources": sorted({h["file"] for h in hits})})
    blocks = "\n\n".join(f"[{h['file']}, part {h['part']}]\n{h['text']}" for h in hits)
    return ("Passages found in your documents (cite the document name when you use them; don't make up anything "
            f"they don't say):\n\n{blocks}")
