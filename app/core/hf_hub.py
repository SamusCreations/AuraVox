"""Hugging Face Hub: search repos, list files / GGUF quantizations, download.

Public API only (https://huggingface.co/api/...). The optional access
token (for private or gated repos) is kept in config/secrets.json
(secrets_store key "hf_token") and only sent to huggingface.co.

Used by:
- Models → "Hugging Face" (assistant LLM): Ollama pulls GGUF repos itself
  with ``hf.co/<user>/<repo>:<quant>``; for private/gated repos (Ollama has
  no way to receive the token) the GGUF is downloaded here and imported
  into Ollama with /api/blobs + /api/create.
- The ComfyUI plugin: downloads a file into the right models\\ subfolder.
"""
import hashlib
import os
import re
import threading
from urllib.parse import quote

import requests

from app.core import secrets_store

HF = "https://huggingface.co"
TOKEN_KEY = "hf_token"
REPO_RE = re.compile(r"^[A-Za-z0-9][\w.\-]{0,95}/[\w.\-]{1,96}$")
_QUANT_RE = re.compile(
    r"(?<![A-Za-z0-9])(IQ[1-4]_(?:XXS|XS|S|M|NL)|Q[2-8](?:_[0-9])?(?:_K)?(?:_(?:XL|L|M|S))?|TQ[12]_0|"
    r"MXFP4(?:_MOE)?|BF16|F16|F32|FP16)(?![A-Za-z0-9])", re.I)
_SHARD_RE = re.compile(r"-(\d{5})-of-(\d{5})\.gguf$", re.I)


def token() -> str:
    return secrets_store.get(TOKEN_KEY)


def set_token(value: str) -> None:
    value = str(value or "").strip()
    if value and not re.fullmatch(r"hf_[A-Za-z0-9]{20,80}", value):
        raise ValueError("invalid token")
    secrets_store.set(TOKEN_KEY, value)


def _headers(tok=None) -> dict:
    tok = token() if tok is None else tok
    h = {"User-Agent": "AuraVox"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _check_repo(repo: str) -> str:
    repo = str(repo or "").strip().strip("/")
    repo = re.sub(r"^(https?://)?(huggingface\.co|hf\.co)/", "", repo)
    repo = repo.split("?")[0]
    parts = repo.split("/")
    if len(parts) > 2:
        repo = "/".join(parts[:2])
    if not REPO_RE.match(repo):
        raise ValueError("invalid repo")
    return repo


def _get(url: str, params=None, timeout=20):
    r = requests.get(url, params=params, headers=_headers(), timeout=timeout)
    if r.status_code == 401 or r.status_code == 403:
        raise PermissionError("auth")
    if r.status_code == 404:
        raise FileNotFoundError("not found")
    r.raise_for_status()
    return r.json()


def search(query: str, gguf: bool = True, limit: int = 30) -> list:
    query = str(query or "").strip()[:100]
    params = {"search": query, "limit": max(1, min(int(limit), 50)), "sort": "downloads", "direction": -1}
    if gguf:
        params["filter"] = "gguf"
    items = _get(f"{HF}/api/models", params)
    return [{"id": m.get("id") or m.get("modelId"), "downloads": m.get("downloads") or 0,
             "likes": m.get("likes") or 0, "private": bool(m.get("private")), "gated": bool(m.get("gated")),
             "pipeline": m.get("pipeline_tag") or "", "updated": m.get("lastModified") or ""}
            for m in items if m.get("id") or m.get("modelId")]


def repo_files(repo: str) -> dict:
    """Repo info + every file with its size."""
    repo = _check_repo(repo)
    info = _get(f"{HF}/api/models/{repo}")
    tree = _get(f"{HF}/api/models/{repo}/tree/main", {"recursive": "true"}, timeout=40)
    files = [{"path": f["path"], "size": (f.get("lfs") or {}).get("size") or f.get("size") or 0}
             for f in tree if f.get("type") == "file"]
    return {"id": info.get("id") or repo, "private": bool(info.get("private")), "gated": bool(info.get("gated")),
            "pipeline": info.get("pipeline_tag") or "", "files": files}


def quant_of(path: str) -> str:
    m = _QUANT_RE.findall(os.path.basename(path))
    return m[-1].upper() if m else ""


def gguf_quants(files: list) -> list:
    """GGUF quantizations of a repo: [{quant, size, files, sharded}]
    (mmproj vision projectors are not quantizations; `vision` says if the
    repo has one)."""
    groups = {}
    for f in files:
        p = f["path"]
        if not p.lower().endswith(".gguf") or "mmproj" in os.path.basename(p).lower():
            continue
        q = quant_of(p) or os.path.basename(p)[:-5]
        g = groups.setdefault(q.upper(), {"quant": q, "size": 0, "files": []})
        g["size"] += f["size"] or 0
        g["files"].append(p)
    out = []
    for g in groups.values():
        g["sharded"] = len(g["files"]) > 1 or any(_SHARD_RE.search(x) for x in g["files"])
        out.append(g)
    out.sort(key=lambda g: g["size"])
    return out


def gguf_info(repo: str) -> dict:
    data = repo_files(repo)
    has_mmproj = any("mmproj" in os.path.basename(f["path"]).lower() for f in data["files"])
    return {**{k: v for k, v in data.items() if k != "files"}, "quants": gguf_quants(data["files"]),
            "vision": has_mmproj}


def download(repo: str, path: str, dest: str, progress=None, cancel=None, chunk=1 << 20) -> str:
    """Downloads `path` of `repo` to `dest` (via dest + ".part"). Returns
    the sha256 hex of the file. `progress(done, total)`; `cancel()` → True
    stops (raises InterruptedError)."""
    repo = _check_repo(repo)
    if ".." in path.replace("\\", "/").split("/"):
        raise ValueError("invalid path")
    url = f"{HF}/{repo}/resolve/main/{quote(path)}"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    h = hashlib.sha256()
    with requests.get(url, headers=_headers(), stream=True, timeout=(15, 120), allow_redirects=True) as r:
        if r.status_code in (401, 403):
            raise PermissionError("auth")
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(part, "wb") as f:
            for block in r.iter_content(chunk):
                if cancel and cancel():
                    raise InterruptedError("cancelled")
                if not block:
                    continue
                f.write(block)
                h.update(block)
                done += len(block)
                if progress:
                    progress(done, total)
    os.replace(part, dest)
    return h.hexdigest()


# ── Background downloads with progress (one at a time per kind) ────────

class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {"state": "idle"}
        self._cancel = False

    def status(self) -> dict:
        with self.lock:
            return dict(self.state)

    def update(self, **kw):
        with self.lock:
            self.state.update(kw)

    def cancel(self):
        self._cancel = True

    def cancelled(self) -> bool:
        return self._cancel

    def start(self, target, **info) -> dict:
        with self.lock:
            if self.state.get("state") == "running":
                raise RuntimeError(self.state.get("label") or "busy")
            self.state = {"state": "running", "completed": 0, "total": 0, "error": None, **info}
            self._cancel = False
        threading.Thread(target=self._run, args=(target,), daemon=True).start()
        return self.status()

    def _run(self, target):
        try:
            target(self)
            self.update(state="done")
        except InterruptedError:
            self.update(state="cancelled")
        except Exception as e:  # noqa: BLE001 — shown as is in the UI
            self.update(state="error", error=str(e) or e.__class__.__name__)
