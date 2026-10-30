"""Actualizar Ollama desde la interfaz (Ajustes compartidos → Ollama).

Igual que el "Reiniciar para actualizar" de la bandeja de Ollama en Windows:
- La versión nueva la dice ollama.com/api/update (lo mismo que consulta la
  app de Ollama cada hora), que responde con la URL del instalador en
  GitHub (OllamaSetup.exe).
- Si la app de Ollama ya lo bajó (%LOCALAPPDATA%\\Ollama\\updates_v2), se usa
  ese; si no, se descarga a cache\\ollama (~1,5 GB) mostrando el progreso.
- Antes de ejecutarlo se comprueba la firma digital de Windows (válida y a
  nombre de Ollama).
- Se instala en silencio con los mismos parámetros que usa Ollama (cierra
  Ollama, instala, lo vuelve a abrir) y se espera a que la API responda con
  la versión nueva. Los modelos y su configuración (OLLAMA_MODELS, etc.) no
  se tocan.
"""
import glob
import json
import os
import re
import subprocess
import threading
import time

import requests

from app import paths
from app.webui import server_log

OLLAMA_URL = "http://127.0.0.1:11434"
UPDATE_API = "https://ollama.com/api/update"
# Solo instaladores publicados por Ollama en GitHub.
INSTALLER_URL_RE = re.compile(r"^https://github\.com/ollama/ollama/releases/download/v(\d+(?:\.\d+){1,3}(?:-rc\d+)?)/OllamaSetup\.exe$")
LOCAL = os.environ.get("LOCALAPPDATA", "")
APP_EXE = os.path.join(LOCAL, "Programs", "Ollama", "ollama app.exe")
DOWNLOAD_DIR = os.path.join(paths.ROOT, "cache", "ollama")
# Los de la bandeja de Ollama (app/updater de Ollama para Windows).
INSTALL_ARGS = ["/CLOSEAPPLICATIONS", "/FORCECLOSEAPPLICATIONS", "/SP", "/NOCANCEL", "/SILENT", "/SUPPRESSMSGBOXES"]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_lock = threading.Lock()
_state = {"state": "idle", "step": "", "current": None, "latest": None, "url": None, "downloaded": 0, "total": 0,
          "error": None, "checked_at": 0, "check_error": None}


def _log(msg: str, level: str = "info") -> None:
    server_log.log("ollama", msg, level)


def _set(**kw) -> None:
    with _lock:
        _state.update(kw)


def status() -> dict:
    with _lock:
        out = dict(_state)
    out["supported"] = os.name == "nt"
    out["available"] = bool(out["latest"] and out["current"] and _newer(out["latest"], out["current"]))
    return out


def _vtuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:4])


def _newer(a: str, b: str) -> bool:
    return _vtuple(a) > _vtuple(b)


def current_version():
    try:
        return requests.get(f"{OLLAMA_URL}/api/version", timeout=4).json().get("version")
    except (requests.exceptions.RequestException, ValueError):
        return None


def check(force: bool = False) -> dict:
    """Versión instalada y la última publicada (se consulta como mucho cada 10 min)."""
    with _lock:
        busy = _state["state"] in ("downloading", "verifying", "installing", "restarting")
        recent = time.time() - _state["checked_at"] < 600
    current = current_version()
    if current:
        _set(current=current)
    if busy or (recent and not force) or os.name != "nt":
        return status()
    try:
        r = requests.get(UPDATE_API, params={"os": "windows", "arch": "amd64", "version": current or "0.0.0"},
                         timeout=10, headers={"User-Agent": f"ollama/{current or '0.0.0'} (amd64 windows)"})
        data = r.json() if r.status_code == 200 and r.content.strip() else {}
        url = data.get("url") or ""
        m = INSTALLER_URL_RE.match(url)
        _set(latest=m.group(1) if m else current, url=url if m else None, checked_at=time.time(), check_error=None)
    except (requests.exceptions.RequestException, ValueError) as e:
        _set(check_error=str(e), checked_at=time.time())
    return status()


def _file_version(path: str) -> str:
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-Item -LiteralPath '{path}').VersionInfo.ProductVersion"],
                             capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW).stdout.strip()
        return out
    except (OSError, subprocess.SubprocessError):
        return ""


def _signature_ok(path: str) -> tuple:
    """(firma válida a nombre de Ollama, detalle)."""
    cmd = (f"$s = Get-AuthenticodeSignature -LiteralPath '{path}'; "
           "[pscustomobject]@{status=[string]$s.Status; subject=[string]$s.SignerCertificate.Subject} | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=120,
                             creationflags=NO_WINDOW).stdout.strip()
        data = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        return False, f"no se pudo comprobar la firma ({e})"
    ok = data.get("status") == "Valid" and "ollama" in (data.get("subject") or "").lower()
    return ok, f"{data.get('status')} — {data.get('subject')}"


def _ready_installer(version: str):
    """El instalador que ya bajó la app de Ollama o una descarga previa nuestra."""
    candidates = glob.glob(os.path.join(LOCAL, "Ollama", "updates*", "*", "OllamaSetup.exe"))
    candidates += [os.path.join(DOWNLOAD_DIR, f"OllamaSetup-{version}.exe")]
    for path in candidates:
        if os.path.isfile(path) and _vtuple(_file_version(path))[:3] == _vtuple(version)[:3]:
            return path
    return None


def _download(url: str, version: str) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    final = os.path.join(DOWNLOAD_DIR, f"OllamaSetup-{version}.exe")
    part = final + ".part"
    with requests.get(url, stream=True, timeout=(15, 120)) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        _set(total=total, downloaded=0)
        done = 0
        with open(part, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                done += len(chunk)
                _set(downloaded=done)
    os.replace(part, final)
    return final


def _wait_api(seconds: float):
    end = time.time() + seconds
    while time.time() < end:
        v = current_version()
        if v:
            return v
        time.sleep(2)
    return None


def _worker() -> None:
    try:
        st = check(force=True)
        if not st["available"] or not st["url"]:
            _set(state="done", step="up_to_date")
            return
        version, url, before = st["latest"], st["url"], st["current"]
        installer = _ready_installer(version)
        if installer:
            _log(f"update to {version}: using already downloaded installer ({installer})")
        else:
            _set(state="downloading", step="downloading")
            _log(f"update to {version}: downloading {url}")
            installer = _download(url, version)
        _set(state="verifying", step="verifying")
        ok, detail = _signature_ok(installer)
        _log(f"installer signature: {detail}", "info" if ok else "error")
        if not ok:
            raise RuntimeError(f"installer digital signature is invalid ({detail})")
        _set(state="installing", step="installing")
        _log(f"installing Ollama {version} (Ollama will close briefly)…")
        log_file = os.path.join(DOWNLOAD_DIR, "install.log")
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        proc = subprocess.run([installer, *INSTALL_ARGS, f"/LOG={log_file}"], timeout=1800, creationflags=NO_WINDOW)
        if proc.returncode != 0:
            raise RuntimeError(f"installer exited with code {proc.returncode} (see {log_file})")
        _set(state="restarting", step="restarting")
        now = _wait_api(45)
        if not now and os.path.isfile(APP_EXE):
            _log("Ollama did not restart automatically: launching it")
            subprocess.Popen([APP_EXE], creationflags=NO_WINDOW | getattr(subprocess, "DETACHED_PROCESS", 0),
                             close_fds=True)
            now = _wait_api(90)
        if not now:
            raise RuntimeError("installed, but Ollama did not respond: launch it from the Start menu")
        _set(state="done", step="updated", current=now, latest=version)
        _log(f"Ollama updated: {before} → {now}")
    except Exception as e:  # noqa: BLE001 — se muestra tal cual en la interfaz
        _set(state="error", error=str(e))
        _log(f"could not update Ollama: {e}", "error")


def start() -> dict:
    if os.name != "nt":
        raise RuntimeError("solo en Windows")
    with _lock:
        if _state["state"] in ("checking", "downloading", "verifying", "installing", "restarting"):
            return status()
        _state.update(state="checking", step="checking", error=None, downloaded=0, total=0)
    threading.Thread(target=_worker, name="ollama-update", daemon=True).start()
    return status()
