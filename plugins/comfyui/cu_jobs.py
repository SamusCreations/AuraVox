"""Trabajos de ComfyUI: cola, ejecución por sondeo y la VRAM con Ollama.

Un trabajo nace "waiting": la página avisa (go) cuando terminó la respuesta
y su voz ("Voy a crearla, tardo ~40 s"); si nadie avisa, arranca solo a
los GO_WAIT s. Un solo hilo los corre en orden. En modo "intercambio",
antes del primero descarga los modelos de Ollama (keep_alive 0, también
los embeddings) y, si se pidió, Whisper y la voz; al terminar la cola espera
`reload_wait` s por si llegan más (iterar ediciones) y recién entonces pide
a ComfyUI que libere todo (/free) y vuelve a cargar lo que había en Ollama.
Si mientras tanto alguien chatea, ComfyUI solo pasa sus modelos a la RAM
(on_chat) para que el LLM tenga la VRAM, y la próxima imagen sale rápido.

El estado vive en este módulo (no en plugin.py, que se recarga solo al
cambiar) y los trabajos recientes en config/comfyui/jobs.json.
"""
import json
import os
import secrets
import threading
import time
import traceback

import requests

import cu_client as C

GO_WAIT = 45                 # s sin "go" de la página → arranca igual
LOST_AFTER = 45              # s sin verlo en la cola ni en el historial → se perdió
KEEP_JOBS = 7 * 24 * 3600
ACTIVE = ("waiting", "queued", "starting", "running")
DEFAULT_ETA = {"image": 40, "edit": 45, "video": 420}

_cond = threading.Condition(threading.RLock())
JOBS = {}
VRAM = {"swapped": False, "remember": [], "voice": False, "hot": False, "timer": None}
HOOKS = {"cfg": None, "prepare": None, "finish": None, "notify": None, "log": None, "dir": None}
_thread = {"t": None}
# Descargar (antes de un trabajo) y recargar (después) no se pisan: si
# llega un pedido mientras vuelve el asistente, espera a que termine y lo
# vuelve a descargar (antes los dos peleaban por la VRAM y tardaba 10 veces más).
_vram_lock = threading.Lock()
_loaded = {"done": False}


def log(text, level="info"):
    fn = HOOKS["log"]
    if fn:
        fn(text, level)
    else:
        print(f"[comfyui] {text}")


def _path(name):
    d = HOOKS["dir"]
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _read(name, default):
    try:
        with open(_path(name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(name, data):
    p = _path(name)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(p + ".tmp", p)


def _load():
    if _loaded["done"]:
        return
    _loaded["done"] = True
    now = time.time()
    for j in _read("jobs.json", []):
        if not isinstance(j, dict) or not j.get("id") or now - j.get("created", 0) > KEEP_JOBS:
            continue
        if j.get("status") in ACTIVE:
            j.update(status="error", error="interrupted")
        JOBS[j["id"]] = j


def _save():
    keep = sorted(JOBS.values(), key=lambda j: j.get("created", 0))[-300:]
    _write("jobs.json", [{k: v for k, v in j.items() if not k.startswith("_")} for j in keep])


# ── Estimaciones (cuánto tarda cada flujo en esta PC) ─────────────────

def eta(workflow: str, kind: str) -> float:
    s = _read("stats.json", {}).get(workflow)
    return float(s) if isinstance(s, (int, float)) and s > 0 else float(DEFAULT_ETA.get(kind, 60))


def _learn(workflow: str, seconds: float):
    stats = _read("stats.json", {})
    old = stats.get(workflow)
    stats[workflow] = round(seconds if not isinstance(old, (int, float)) else old * 0.6 + seconds * 0.4, 1)
    _write("stats.json", stats)


# ── API para plugin.py ─────────────────────────────────────────────────

def create(owner: str, kind: str, workflow: str, label: str, params: dict, auto_go: float = GO_WAIT) -> dict:
    with _cond:
        _load()
        jid = secrets.token_hex(8)
        job = {"id": jid, "owner": owner, "kind": kind, "workflow": workflow, "label": label[:300], "params": params,
               "status": "waiting", "created": time.time(), "go_at": time.time() + auto_go, "eta": eta(workflow, kind),
               "progress": 0.0, "position": 0, "error": "", "result": None}
        JOBS[jid] = job
        _save()
        _cancel_release()
        _ensure_thread()
        _cond.notify_all()
        return job


def go(ids, owner: str) -> int:
    n = 0
    with _cond:
        for jid in ids or []:
            j = JOBS.get(jid)
            if j and j["owner"] == owner and j["status"] == "waiting":
                j["go_at"] = 0
                n += 1
        _cond.notify_all()
    return n


def cancel(jid: str, owner: str, admin=False) -> bool:
    with _cond:
        j = JOBS.get(jid)
        if not j or (j["owner"] != owner and not admin) or j["status"] not in ACTIVE:
            return False
        j["_cancel"] = True
        if j["status"] in ("waiting", "queued"):
            j.update(status="cancelled", finished=time.time())
            _save()
        _cond.notify_all()
    if j.get("prompt_id"):
        C.interrupt(HOOKS["cfg"]()["url"], j["prompt_id"])
    return True


def public(j: dict) -> dict:
    out = {k: j.get(k) for k in ("id", "kind", "status", "label", "position", "error", "result", "created", "eta", "workflow",
                                 "wf_name", "size", "note")}
    if j["status"] == "running" and j.get("started"):
        elapsed = time.time() - j["started"]
        out["progress"] = round(min(0.95, elapsed / max(1.0, j["eta"])), 3)
        out["eta_left"] = max(0, round(j["eta"] - elapsed))
    else:
        out["progress"] = 1.0 if j["status"] == "done" else 0.0
        out["eta_left"] = round(j["eta"]) if j["status"] in ACTIVE else 0
    return out


def get(ids, owner: str, admin=False) -> list:
    with _cond:
        _load()
        return [public(JOBS[i]) for i in ids if i in JOBS and (JOBS[i]["owner"] == owner or admin)]


def active(owner: str = None) -> list:
    with _cond:
        return [public(j) for j in JOBS.values() if j["status"] in ACTIVE and (owner is None or j["owner"] == owner)]


def busy() -> bool:
    with _cond:
        return any(j["status"] in ("starting", "running") for j in JOBS.values())


def vram_state() -> dict:
    return {"swapped": VRAM["swapped"], "remember": list(VRAM["remember"]), "voice_released": VRAM["voice"],
            "release_pending": VRAM["timer"] is not None}


# ── VRAM: Ollama ↔ ComfyUI ─────────────────────────────────────────────

def _ollama():
    try:
        from app.core.assistant_engine import OLLAMA_URL
        return OLLAMA_URL.split("/api/")[0]
    except Exception:  # noqa: BLE001
        return "http://127.0.0.1:11434"


def _ollama_loaded() -> list:
    try:
        return [m["name"] for m in requests.get(_ollama() + "/api/ps", timeout=4).json().get("models", [])]
    except (requests.exceptions.RequestException, ValueError, KeyError):
        return []


def _ollama_unload(model: str):
    base = _ollama()
    try:
        r = requests.post(base + "/api/generate", json={"model": model, "keep_alive": 0}, timeout=15)
        if r.status_code >= 400:
            requests.post(base + "/api/embed", json={"model": model, "input": "", "keep_alive": 0}, timeout=15)
    except requests.exceptions.RequestException:
        pass


def _keep_alive():
    try:
        from app.core.assistant_common import SERVER_KEEP_ALIVE
        return SERVER_KEEP_ALIVE
    except Exception:  # noqa: BLE001
        return -1


def _ollama_load(model: str):
    base = _ollama()
    try:
        r = requests.post(base + "/api/generate", json={"model": model, "keep_alive": _keep_alive()}, timeout=120)
        if r.status_code >= 400:
            requests.post(base + "/api/embed", json={"model": model, "input": "warm up", "keep_alive": _keep_alive()},
                          timeout=120)
    except requests.exceptions.RequestException:
        pass


def _swap_out(cfg):
    """Antes de un trabajo: la GPU para ComfyUI."""
    with _vram_lock:
        _swap_out_locked(cfg)


def _swap_out_locked(cfg):
    loaded = _ollama_loaded()
    for m in loaded:
        if m not in VRAM["remember"]:
            VRAM["remember"].append(m)
    if loaded:
        t0 = time.time()
        for m in loaded:
            _ollama_unload(m)
        while _ollama_loaded() and time.time() - t0 < 15:
            time.sleep(0.3)
        log(f"VRAM for ComfyUI: unloaded {', '.join(loaded)} from Ollama in {time.time() - t0:.1f}s")
    if cfg.get("release_voice") and not VRAM["voice"]:
        # Aparte: cerrar Qwen3-TTS espera si se está preparando (minutos),
        # y la imagen no tiene por qué esperarlo.
        VRAM["voice"] = True
        threading.Thread(target=_release_voice, name="comfyui-voice", daemon=True).start()
        time.sleep(1.5)  # Whisper y Supertonic se van enseguida
    VRAM["swapped"] = True
    VRAM["hot"] = True


def _release_voice():
    try:
        from app.webui import chat_runtime
        chat_runtime.unload(())
    except Exception:  # noqa: BLE001 — en consola no hay voz que liberar
        pass


def _cancel_release():
    t = VRAM.get("timer")
    if t:
        t.cancel()
        VRAM["timer"] = None


def _schedule_release(cfg):
    _cancel_release()
    if not VRAM["swapped"]:
        return
    wait = max(0.0, float(cfg.get("reload_wait") or 0))
    t = threading.Timer(wait, _release)
    t.daemon = True
    VRAM["timer"] = t
    t.start()
    log(f"ComfyUI stays warm for {wait:.0f}s in case of another job; then assistant models reload")


def _release():
    with _cond:
        VRAM["timer"] = None
        if any(j["status"] in ACTIVE for j in JOBS.values()) or not VRAM["swapped"]:
            return
        remember, VRAM["remember"] = list(VRAM["remember"]), []
        voice, VRAM["voice"] = VRAM["voice"], False
        VRAM["swapped"] = False
        VRAM["hot"] = False
    cfg = HOOKS["cfg"]()
    t0 = time.time()
    with _vram_lock:
        C.free(cfg["url"], unload_models=True, free_memory=True)
        for m in remember:
            with _cond:
                if any(j["status"] in ACTIVE for j in JOBS.values()):
                    # Llegó otro pedido: lo que falta se recarga después de ese.
                    VRAM["remember"] = list(dict.fromkeys(VRAM["remember"] + remember))
                    VRAM["swapped"] = True
                    VRAM["voice"] = VRAM["voice"] or voice
                    log("another ComfyUI job arrived while reloading assistant: waiting for it to finish")
                    return
            _ollama_load(m)
    if voice:
        try:
            from app.webui import chat_runtime
            chat_runtime.prewarm_voices()
        except Exception:  # noqa: BLE001
            pass
    log(f"ComfyUI freed VRAM; reloaded {', '.join(remember) or 'nothing'} in {time.time() - t0:.1f}s")


def on_chat():
    """Alguien chatea mientras ComfyUI tiene la GPU (esperando otra
    edición): sus modelos pasan a la RAM para que el LLM entre rápido."""
    cfg = HOOKS["cfg"]()
    if cfg.get("vram_mode") != "swap" or not VRAM["swapped"] or not VRAM["hot"] or busy():
        return
    VRAM["hot"] = False
    C.free(cfg["url"], unload_models=True, free_memory=False)
    log("chat message while ComfyUI was warm: moving ComfyUI models to RAM so the assistant can reply")


# ── El hilo que corre los trabajos ─────────────────────────────────────

def _ensure_thread():
    t = _thread["t"]
    if t and t.is_alive():
        return
    t = threading.Thread(target=_loop, name="comfyui-jobs", daemon=True)
    _thread["t"] = t
    t.start()


def _next():
    with _cond:
        while True:
            now = time.time()
            ready = [j for j in JOBS.values() if j["status"] in ("waiting", "queued") and j.get("go_at", 0) <= now
                     and not j.get("_cancel")]
            if ready:
                j = min(ready, key=lambda x: x["created"])
                j["status"] = "starting"
                return j
            waits = [j["go_at"] - now for j in JOBS.values() if j["status"] == "waiting"]
            _cond.wait(timeout=max(0.2, min(waits)) if waits else 30)


def _loop():
    while True:
        job = _next()
        cfg = HOOKS["cfg"]()
        try:
            _run(job, cfg)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            _fail(job, str(e))
        with _cond:
            more = any(j["status"] in ACTIVE for j in JOBS.values())
        if not more and cfg.get("vram_mode") == "swap":
            _schedule_release(cfg)


def _fail(job, error):
    with _cond:
        if job["status"] in ("done", "cancelled"):
            return
        job.update(status="cancelled" if job.get("_cancel") else "error", error=str(error)[:600], finished=time.time())
        _save()
    log(f"job {job['id']} ({job['kind']}): {job['error'] or 'cancelled'}", "warn" if job["status"] == "error" else "info")
    _notify(job)


def _notify(job):
    fn = HOOKS["notify"]
    if fn:
        try:
            fn(job)
        except Exception:  # noqa: BLE001
            traceback.print_exc()


def _run(job, cfg):
    url = cfg["url"]
    if C.stats(url, timeout=4) is None:
        raise C.ComfyError("ComfyUI is not responding")
    if cfg.get("vram_mode") == "swap":
        _cancel_release()
        _swap_out(cfg)
    graph = HOOKS["prepare"](job)
    if job.get("_cancel"):
        raise C.ComfyError("cancelled")
    pid = C.queue_prompt(url, graph)
    with _cond:
        job.update(prompt_id=pid, status="running", started=time.time())
    log(f"job {job['id']} ({job['kind']}, {job['workflow']}) queued in ComfyUI: {pid}")
    last_seen = time.time()
    queued_at = time.time()
    while True:
        time.sleep(1.0)
        entry = C.history(url, pid)
        if entry:  # en el historial solo aparece al terminar
            st = entry.get("status") or {}
            if st.get("status_str") == "error":
                msg = ""
                for m in st.get("messages") or []:
                    if isinstance(m, list) and len(m) > 1 and m[0] in ("execution_error", "execution_interrupted"):
                        d = m[1] or {}
                        msg = d.get("exception_message") or m[0]
                        if d.get("node_type"):
                            msg = f"{d['node_type']}: {msg}"
                raise C.ComfyError(("cancelled" if job.get("_cancel") else msg.strip() or "ComfyUI execution error")[:500])
            break
        if job.get("_cancel"):
            C.interrupt(url, pid)
            raise C.ComfyError("cancelled")
        state, pos = C.queue_state(url, pid)
        if state:
            last_seen = time.time()
            with _cond:
                job["position"] = pos
                if state == "pending":
                    # Mientras espera su turno (otros trabajos en ComfyUI) no corre el reloj.
                    job["started"] = time.time()
        elif time.time() - last_seen > LOST_AFTER:
            raise C.ComfyError("ComfyUI lost the job (did it restart?)")
    files = C.outputs_of(entry)
    if not files:
        raise C.ComfyError("workflow finished without saving any image or video")
    name, sub, typ, kind = files[0]
    data = C.view(url, name, sub, typ)
    took = time.time() - job["started"]
    result = HOOKS["finish"](job, name, data, kind)
    with _cond:
        job.update(status="done", result=result, finished=time.time(), progress=1.0, took=round(took, 1))
        _save()
    _learn(job["workflow"], took)
    log(f"job {job['id']} completed in {took:.0f}s (+{max(0, job['started'] - queued_at):.0f}s queued): {result.get('name')}")
    _notify(job)
