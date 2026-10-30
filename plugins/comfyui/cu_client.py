"""Cliente HTTP mínimo de ComfyUI (sin websocket: todo por sondeo).

Rutas que usa: /system_stats (¿está?), /object_info (nodos y modelos
instalados), /userdata?dir=workflows (flujos guardados), /prompt (encolar),
/queue y /history/{id} (seguir), /interrupt (cancelar), /view (bajar el
resultado), /upload/image (imagen de origen) y /free (liberar la VRAM).
"""
import json
import time
import uuid
from urllib.parse import quote, urlencode

import requests

CLIENT_ID = "auravox-" + uuid.uuid4().hex[:12]
_info = {"url": None, "at": 0.0, "data": None}
_alive = {"url": None, "at": 0.0, "ok": False, "stats": None}
INFO_TTL = 600
ALIVE_TTL = 20


class ComfyError(Exception):
    pass


def _get(url, path, timeout=10, **params):
    r = requests.get(url + path + (("?" + urlencode(params)) if params else ""), timeout=timeout)
    r.raise_for_status()
    return r


def stats(url, timeout=3):
    """system_stats (versión, GPU, VRAM libre) o None si no responde."""
    try:
        data = _get(url, "/system_stats", timeout=timeout).json()
    except (requests.exceptions.RequestException, ValueError):
        data = None
    _alive.update(url=url, at=time.time(), ok=data is not None, stats=data)
    return data


def alive(url) -> bool:
    """¿Responde? (cacheado unos segundos: se pregunta en cada turno)."""
    if _alive["url"] == url and time.time() - _alive["at"] < ALIVE_TTL:
        return _alive["ok"]
    return stats(url, timeout=1.5) is not None


def object_info(url, force=False) -> dict:
    if not force and _info["url"] == url and _info["data"] and time.time() - _info["at"] < INFO_TTL:
        return _info["data"]
    try:
        data = _get(url, "/object_info", timeout=60).json()
    except (requests.exceptions.RequestException, ValueError) as e:
        raise ComfyError(f"/object_info: {e}") from e
    _info.update(url=url, at=time.time(), data=data)
    return data


def combo_options(spec) -> list:
    """Opciones de un input COMBO (formato viejo [lista, {...}] o nuevo
    ["COMBO", {"options": [...]}])."""
    if not isinstance(spec, (list, tuple)) or not spec:
        return []
    if isinstance(spec[0], list):
        return [str(x) for x in spec[0]]
    if spec[0] == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
        return [str(x) for x in spec[1].get("options") or []]
    return []


def input_spec(info, cls, name):
    node = (info or {}).get(cls) or {}
    for sect in ("required", "optional"):
        spec = (node.get("input") or {}).get(sect) or {}
        if name in spec:
            return spec[name]
    return None


# Modelos instalados, por tipo (de las listas de los nodos que los cargan).
MODEL_SOURCES = {
    "checkpoints": [("CheckpointLoaderSimple", "ckpt_name")],
    "diffusion_models": [("UNETLoader", "unet_name")],
    "gguf": [("UnetLoaderGGUF", "unet_name"), ("UnetLoaderGGUFAdvanced", "unet_name")],
    "loras": [("LoraLoader", "lora_name"), ("LoraLoaderModelOnly", "lora_name")],
    "vae": [("VAELoader", "vae_name")],
    "text_encoders": [("CLIPLoader", "clip_name")],
    "clip_gguf": [("CLIPLoaderGGUF", "clip_name")],
}


def models(info) -> dict:
    out = {}
    for kind, sources in MODEL_SOURCES.items():
        names = []
        for cls, inp in sources:
            for n in combo_options(input_spec(info, cls, inp)):
                if n not in names:
                    names.append(n)
        if names:
            out[kind] = names
    return out


def user_workflows(url) -> list:
    """Los flujos guardados en ComfyUI (user/default/workflows), por ruta."""
    for path in ("/api/userdata", "/userdata"):
        try:
            r = _get(url, path, timeout=10, dir="workflows", recurse="true", split="false")
            items = r.json()
            return sorted(str(x) for x in items if str(x).lower().endswith(".json"))
        except (requests.exceptions.RequestException, ValueError):
            continue
    return []


def user_workflow(url, name: str) -> dict:
    for path in ("/api/userdata/", "/userdata/"):
        try:
            return _get(url, path + quote("workflows/" + name, safe=""), timeout=15).json()
        except (requests.exceptions.RequestException, ValueError):
            continue
    raise ComfyError(f"no pude leer el flujo {name}")


def queue_prompt(url, graph: dict) -> str:
    try:
        r = requests.post(url + "/prompt", json={"prompt": graph, "client_id": CLIENT_ID}, timeout=30)
    except requests.exceptions.RequestException as e:
        raise ComfyError(str(e)) from e
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400 or not data.get("prompt_id"):
        raise ComfyError(describe_error(data) or f"HTTP {r.status_code}: {r.text[:300]}")
    return data["prompt_id"]


def describe_error(data: dict) -> str:
    """El error de /prompt en una línea legible (qué nodo y qué falta)."""
    if not isinstance(data, dict):
        return ""
    err = data.get("error") or {}
    parts = [str(err.get("message") or "")] if isinstance(err, dict) else [str(err)]
    for nid, ne in (data.get("node_errors") or {}).items():
        for e in (ne.get("errors") or [])[:2]:
            detail = e.get("details") or e.get("message") or ""
            parts.append(f"{ne.get('class_type', '?')} #{nid}: {detail}")
    return " · ".join(p for p in parts if p)[:600]


def queue_state(url, prompt_id: str):
    """("running" | "pending" | None, posición en la cola)."""
    try:
        q = _get(url, "/queue", timeout=5).json()
    except (requests.exceptions.RequestException, ValueError):
        return None, 0
    for item in q.get("queue_running") or []:
        if len(item) > 1 and item[1] == prompt_id:
            return "running", 0
    pending = sorted(q.get("queue_pending") or [], key=lambda it: it[0] if it else 0)
    for k, item in enumerate(pending):
        if len(item) > 1 and item[1] == prompt_id:
            return "pending", k + 1 + len(q.get("queue_running") or [])
    return None, 0


def history(url, prompt_id: str):
    try:
        data = _get(url, f"/history/{prompt_id}", timeout=10).json()
    except (requests.exceptions.RequestException, ValueError):
        return None
    return data.get(prompt_id) if isinstance(data, dict) else None


def interrupt(url, prompt_id: str = None) -> None:
    try:
        requests.post(url + "/interrupt", json={"prompt_id": prompt_id} if prompt_id else {}, timeout=5)
        if prompt_id:
            requests.post(url + "/queue", json={"delete": [prompt_id]}, timeout=5)
    except requests.exceptions.RequestException:
        pass


def view(url, filename, subfolder="", type_="output") -> bytes:
    r = _get(url, "/view", timeout=120, filename=filename, subfolder=subfolder or "", type=type_ or "output")
    return r.content


def upload_image(url, name: str, data: bytes) -> str:
    """Sube la imagen de origen a input/auravox/ y da el nombre para LoadImage."""
    r = requests.post(url + "/upload/image", files={"image": (name, data)},
                      data={"overwrite": "true", "type": "input", "subfolder": "auravox"}, timeout=60)
    r.raise_for_status()
    d = r.json()
    return f"{d['subfolder']}/{d['name']}" if d.get("subfolder") else d["name"]


def free(url, unload_models=True, free_memory=True) -> bool:
    try:
        r = requests.post(url + "/free", json={"unload_models": unload_models, "free_memory": free_memory}, timeout=10)
        return r.ok
    except requests.exceptions.RequestException:
        return False


def outputs_of(entry: dict) -> list:
    """[(filename, subfolder, type, "image"|"video")] de lo que guardó el flujo."""
    found = []
    for _nid, out in ((entry or {}).get("outputs") or {}).items():
        for key in ("videos", "gifs", "images", "animated", "video"):
            for f in out.get(key) or []:
                if not isinstance(f, dict) or not f.get("filename"):
                    continue
                name = f["filename"]
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                kind = "video" if ext in ("mp4", "webm", "mov", "mkv", "gif", "webp") and key != "images" else (
                    "video" if ext in ("mp4", "webm", "mov", "mkv") else "image")
                found.append((name, f.get("subfolder") or "", f.get("type") or "output", kind))
    # Primero lo guardado (output) y lo que es video; las vistas previas (temp) al final.
    found.sort(key=lambda x: (x[2] != "output", x[3] != "video"))
    return found


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
