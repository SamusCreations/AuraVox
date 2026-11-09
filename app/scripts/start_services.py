"""
Run by AuraVox.bat before the web UI: starts Ollama if it isn't answering, and
ComfyUI if its plugin is enabled and an installation is configured or detected.

Never stops AuraVox from starting: anything that fails is only reported.
AURAVOX_NO_AUTOSTART=1 skips this script. --dry-run reports what it would do.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from app import paths  # noqa: E402

OLLAMA_URL = "http://127.0.0.1:11434/api/version"
OLLAMA_WAIT = 30
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1", "0.0.0.0")
DRY_RUN = "--dry-run" in sys.argv


def say(text: str) -> None:
    print(f"[startup] {text}", flush=True)


def answers(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _ollama_exe():
    local = os.environ.get("LOCALAPPDATA", "")
    for p in (os.path.join(local, "Programs", "Ollama", "ollama app.exe"),
              os.path.join(local, "Programs", "Ollama", "ollama.exe")):
        if os.path.isfile(p):
            return p
    return shutil.which("ollama")


def ensure_ollama() -> None:
    if answers(OLLAMA_URL):
        say("Ollama is already running")
        return
    exe = _ollama_exe()
    if not exe:
        say("Ollama is not installed: https://ollama.com/download")
        return
    if DRY_RUN:
        say(f"would start Ollama: {exe}")
        return
    say("starting Ollama...")
    # The tray app starts the server by itself; the bare binary needs "serve".
    command = [exe] if exe.lower().endswith("ollama app.exe") else [exe, "serve"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        subprocess.Popen(command, close_fds=True, creationflags=flags, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        say(f"could not start Ollama: {e}")
        return
    deadline = time.time() + OLLAMA_WAIT
    while time.time() < deadline:
        if answers(OLLAMA_URL):
            say("Ollama is ready")
            return
        time.sleep(0.5)
    say(f"Ollama did not answer within {OLLAMA_WAIT} s; continuing without waiting for it")


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _comfy_enabled() -> tuple:
    """(enabled, saved settings), with the plugin's default when not set yet."""
    state = _read_json(os.path.join(paths.CONFIG_DIR, "plugins.json")).get("comfyui")
    manifest = _read_json(os.path.join(ROOT, "plugins", "comfyui", "manifest.json"))
    if isinstance(state, dict) and "enabled" in state:
        return bool(state["enabled"]), state.get("settings") or {}
    return bool(manifest.get("default_enabled", True)), {}


def _locate_module():
    path = os.path.join(ROOT, "plugins", "comfyui", "cu_locate.py")
    spec = importlib.util.spec_from_file_location("cu_locate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ensure_comfyui() -> None:
    enabled, settings = _comfy_enabled()
    if not enabled:
        return
    locate = _locate_module()
    chosen = str((_read_json(os.path.join(paths.CONFIG_DIR, "comfyui", "config.json")).get("install") or {}).get("path") or "")
    if chosen:
        inst = locate.info(chosen)
        if not inst:
            say(f"the ComfyUI folder set in AuraVox no longer exists: {chosen}")
            return
    else:
        found = locate.find_all(timeout=12.0)
        if not found:
            return  # plugin on but ComfyUI not on this PC: nothing to start
        inst = found[0]
    url = str(settings.get("url") or "").strip().rstrip("/") or f"http://127.0.0.1:{inst['port']}"
    if answers(url + "/system_stats"):
        say("ComfyUI is already running")
        return
    if (urlsplit(url).hostname or "") not in LOCAL_HOSTS:
        say(f"ComfyUI is configured on another machine ({url}): not starting it here")
        return
    if not locate.can_start(inst):
        say(f"found ComfyUI at {inst['path']} but no way to start it")
        return
    if DRY_RUN:
        say(f"would start ComfyUI: {inst.get('launcher') or inst['path']}")
        return
    # No waiting: ComfyUI opens in its own window and AuraVox connects when it's up.
    try:
        say(f"starting ComfyUI: {locate.start(inst)}")
    except OSError as e:
        say(f"could not start ComfyUI: {e}")


def main() -> int:
    if os.environ.get("AURAVOX_NO_AUTOSTART") == "1":
        return 0
    for step in (ensure_ollama, ensure_comfyui):
        try:
            step()
        except Exception as e:  # noqa: BLE001 — AuraVox has to start anyway
            say(f"{step.__name__} failed: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
