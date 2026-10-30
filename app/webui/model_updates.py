"""¿Hay una versión nueva de cada modelo de Ollama? Y actualizarlos.

Un modelo de Ollama es un "manifest" (lista de capas: pesos, plantilla,
parámetros) y su `digest` es el sha256 de ese manifest. Si en el registro
de donde vino (registry.ollama.ai para los de ollama.com, hf.co para los de
Hugging Face) el manifest de esa misma etiqueta tiene otro sha256, el autor
lo actualizó.

Actualizar = `ollama pull` del mismo nombre (config_ui.start_pull, con su
barra de progreso): Ollama baja solo las capas que cambiaron, reemplaza el
manifest y borra las capas viejas que ya no usa ningún modelo (a menos que
OLLAMA_NOPRUNE esté activo). Después se comprueba que quedó la versión
nueva y cuánto espacio se liberó.

Cada modelo tiene la opción "actualizar automáticamente" (por defecto sí):
se comprueba al rato de abrir la interfaz y cada CHECK_EVERY.
"""
import hashlib
import json
import os
import re
import threading
import time

import requests

from app import paths
from app.webui import server_log

OLLAMA_URL = "http://127.0.0.1:11434"
STATE_FILE = os.path.join(paths.CONFIG_DIR, "model_updates.json")
CHECK_EVERY = 6 * 3600
CACHE_SECONDS = 1800
FIRST_CHECK_DELAY = 180
MANIFEST_ACCEPT = "application/vnd.docker.distribution.manifest.v2+json"

_lock = threading.Lock()
_checking = threading.Lock()
_runtime = {"checking": False, "updating": None}


def _log(msg: str, level: str = "info") -> None:
    server_log.log("modelos", msg, level)


def _load() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)


def _split(name: str):
    """(host, repo, etiqueta) del registro de donde viene `name`, o None."""
    name = name.strip()
    if name.startswith(("hf.co/", "huggingface.co/")):
        host, rest = "hf.co", name.split("/", 1)[1]
    elif name.count("/") >= 2 or ("." in name.split("/")[0] and "/" in name):
        return None  # otro registro (o un modelo local con nombre raro): no se sabe consultar
    else:
        host, rest = "registry.ollama.ai", name if "/" in name.split(":")[0] else f"library/{name}"
    repo, _, tag = rest.partition(":")
    return host, repo, tag or "latest"


def remote_manifest(name: str):
    """(digest, manifest) de la etiqueta en su registro."""
    parts = _split(name)
    if not parts:
        raise ValueError("no viene de ollama.com ni de Hugging Face")
    host, repo, tag = parts
    # Sin User-Agent de Ollama: con él, registry.ollama.ai pide una firma (401).
    r = requests.get(f"https://{host}/v2/{repo}/manifests/{tag}", headers={"Accept": MANIFEST_ACCEPT}, timeout=20)
    if r.status_code == 404:
        raise ValueError("ya no está publicado en su registro")
    r.raise_for_status()
    return hashlib.sha256(r.content).hexdigest(), r.json()


def _models_dir() -> str:
    """Carpeta de modelos de Ollama: OLLAMA_MODELS (del proceso o, si se
    definió después de abrirlo, la guardada en Windows) o la de siempre."""
    path = os.environ.get("OLLAMA_MODELS")
    if not path and os.name == "nt":
        import winreg

        for root, key in ((winreg.HKEY_CURRENT_USER, "Environment"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
            try:
                with winreg.OpenKey(root, key) as k:
                    path = os.path.expandvars(winreg.QueryValueEx(k, "OLLAMA_MODELS")[0])
                    break
            except OSError:
                continue
    if not path:
        # La app de Ollama la puede tener en sus propios ajustes: la dice el
        # log del servidor al arrancar ("server config ... OLLAMA_MODELS:F:\\AI\\Models").
        try:
            with open(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Ollama", "server.log"), encoding="utf-8",
                      errors="replace") as f:
                found = re.findall(r"OLLAMA_MODELS:(.*?) OLLAMA_", f.read())
            if found and found[-1].strip():
                path = found[-1].strip().replace("\\\\", "\\")
        except OSError:
            pass
    return path or os.path.join(os.path.expanduser("~"), ".ollama", "models")


def _local_manifest(name: str):
    parts = _split(name)
    if not parts:
        return None
    host, repo, tag = parts
    path = os.path.join(_models_dir(), "manifests", host, *repo.split("/"), tag)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _blob_paths(manifest: dict) -> list:
    layers = list((manifest or {}).get("layers") or []) + ([manifest["config"]] if (manifest or {}).get("config") else [])
    return [os.path.join(_models_dir(), "blobs", str(l.get("digest", "")).replace(":", "-")) for l in layers if l.get("digest")]


def _installed() -> dict:
    tags = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).json().get("models", [])
    return {m.get("name") or m.get("model"): m for m in tags}


def status() -> dict:
    data = _load()
    return {"models": data.get("checks", {}), "auto": data.get("auto", {}), "checked_at": data.get("checked_at", 0),
            "checking": _runtime["checking"], "updating": _runtime["updating"]}


def is_auto(name: str) -> bool:
    return _load().get("auto", {}).get(name, True)


def set_auto(name: str, on: bool) -> dict:
    with _lock:
        data = _load()
        data.setdefault("auto", {})[name] = bool(on)
        _save(data)
    _log(f"{name}: actualización automática {'activada' if on else 'desactivada'}")
    return status()


def check(force: bool = False, only: str = None) -> dict:
    """Compara cada modelo instalado (o solo `only`) con su registro."""
    data = _load()
    if not force and not only and time.time() - data.get("checked_at", 0) < CACHE_SECONDS:
        return status()
    if not _checking.acquire(blocking=False):
        return status()
    _runtime["checking"] = True
    try:
        try:
            installed = _installed()
        except requests.exceptions.ConnectionError:
            # Ollama cerrado: avisarlo una vez por caída, no en cada consulta.
            if not _runtime.get("ollama_down"):
                _runtime["ollama_down"] = True
                _log("Ollama no está abierto: no compruebo las actualizaciones hasta que vuelva", "warn")
            return status()
        if _runtime.pop("ollama_down", False):
            _log("Ollama vuelve a responder")
        names = [only] if only else list(installed)
        results = {}
        for name in names:
            local = installed.get(name)
            if not local:
                continue
            entry = {"local": local.get("digest", ""), "checked_at": time.time()}
            try:
                remote, manifest = remote_manifest(name)
                size = sum(int(l.get("size") or 0) for l in manifest.get("layers") or [])
                entry.update(remote=remote, size=size, state="current" if remote == entry["local"] else "available")
            except (requests.exceptions.RequestException, ValueError) as e:
                entry.update(state="unknown", error=str(e)[:200])
            results[name] = entry
        with _lock:
            data = _load()
            checks = data.setdefault("checks", {})
            if not only:  # se fueron modelos: sus entradas también
                for gone in [n for n in checks if n not in installed]:
                    checks.pop(gone)
            checks.update(results)
            if not only:
                data["checked_at"] = time.time()
            _save(data)
        new = [n for n, e in results.items() if e.get("state") == "available"]
        if new:
            _log(f"versión nueva disponible: {', '.join(new)}")
    except (requests.exceptions.RequestException, ValueError) as e:
        _log(f"no pude comprobar las actualizaciones ({e})", "warn")
    finally:
        _runtime["checking"] = False
        _checking.release()
    return status()


def before_update(name: str) -> dict:
    """Lo que hace falta para comprobar después que se borró la versión vieja."""
    _runtime["updating"] = name
    manifest = _local_manifest(name)
    return {"name": name, "digest": (_installed().get(name) or {}).get("digest", ""), "blobs": _blob_paths(manifest)}


def after_update(prev: dict, ok: bool) -> None:
    """Tras el pull: ¿quedó la versión nueva? ¿se borraron las capas viejas?"""
    name = prev["name"]
    _runtime["updating"] = None
    if not ok:
        return
    try:
        now = (_installed().get(name) or {}).get("digest", "")
    except (requests.exceptions.RequestException, ValueError):
        now = ""
    still = set(_blob_paths(_local_manifest(name)))
    freed = kept = 0
    for path in prev["blobs"]:
        if path in still:
            continue  # capa que la versión nueva sigue usando
        if os.path.exists(path):
            kept += 1
        else:
            freed += 1
    if now and now != prev["digest"]:
        _log(f"{name} actualizado ({prev['digest'][:12]} → {now[:12]}); capas viejas borradas: {freed}"
             + (f", {kept} siguen en disco (las usa otro modelo o OLLAMA_NOPRUNE está activo)" if kept else ""))
    elif now:
        _log(f"{name}: ya estaba en la última versión")
    check(only=name)


def auto_loop(start_pull, pull_status) -> None:
    """Comprueba cada CHECK_EVERY y actualiza los modelos que lo tengan activado."""
    def run():
        time.sleep(FIRST_CHECK_DELAY)
        while True:
            try:
                st = check(force=True)
                for name, entry in st["models"].items():
                    if entry.get("state") != "available" or not is_auto(name):
                        continue
                    while pull_status().get("state") == "running":
                        time.sleep(10)
                    _log(f"actualizando {name} automáticamente…")
                    prev = before_update(name)
                    try:
                        start_pull(name)
                    except Exception as e:  # noqa: BLE001 — otro pull empezó justo: el próximo ciclo
                        _log(f"no pude empezar la actualización de {name}: {e}", "warn")
                        after_update(prev, False)
                        continue
                    while pull_status().get("state") == "running":
                        time.sleep(5)
                    after_update(prev, pull_status().get("state") == "done")
            except Exception as e:  # noqa: BLE001 — que el ciclo no se muera
                _log(f"error en la actualización automática: {e}", "warn")
            time.sleep(CHECK_EVERY)

    threading.Thread(target=run, name="model-updates", daemon=True).start()
