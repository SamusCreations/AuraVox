"""Dónde está ComfyUI en esta PC (sin preguntarle a su API).

Busca las dos formas de instalarlo en Windows:
- Portable / standalone (ComfyUI_windows_portable, ComfyUI-Easy-Install,
  un clon con su venv…): una carpeta con main.py + models\\ (o comfy\\),
  en las ubicaciones típicas y en la raíz de cada unidad (dos niveles).
  El puerto sale del .bat con que se arranca (--port, si no 8188).
- ComfyUI Desktop: el programa en %LOCALAPPDATA%\\Programs\\… y su carpeta
  de datos (modelos, flujos) en "basePath" de %APPDATA%\\ComfyUI\\config.json.
  Puerto 8000 salvo que sus ajustes digan otro.

Con la ruta se leen los flujos guardados y los modelos aunque ComfyUI esté
cerrado, y se puede arrancar (start). La elegida a mano se valida con info().
"""
import json
import os
import re
import string
import subprocess
import time

PORTABLE_PORT = 8188
DESKTOP_PORT = 8000
SKIP = {"windows", "$recycle.bin", "system volume information", "programdata", "recovery", "$windows.~bt",
        "$windows.~ws", "msocache", "perflogs", "intel", "amd", "nvidia", "drivers", "config.msi", "onedrivetemp"}
MODEL_DIRS = ("checkpoints", "diffusion_models", "unet", "loras", "vae", "text_encoders", "clip", "upscale_models")
MODEL_EXT = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".sft")
LAUNCH_HINT = ("start", "run", "launch", "comfyui")


def _isdir(*parts) -> bool:
    try:
        return os.path.isdir(os.path.join(*parts))
    except (OSError, ValueError):
        return False


def _isfile(*parts) -> bool:
    try:
        return os.path.isfile(os.path.join(*parts))
    except (OSError, ValueError):
        return False


def _listdir(path) -> list:
    try:
        return sorted(os.listdir(path), key=str.lower)
    except (OSError, ValueError):
        return []


def is_code_root(path) -> bool:
    """¿Es la carpeta de ComfyUI (la que tiene main.py)?"""
    return _isfile(path, "main.py") and (_isdir(path, "models") or _isdir(path, "comfy")) and (
        _isfile(path, "nodes.py") or _isfile(path, "folder_paths.py") or _isdir(path, "comfy"))


def is_data_root(path) -> bool:
    """¿Es una carpeta de datos de ComfyUI Desktop (models\\ + user\\)?"""
    return _isdir(path, "models") and (_isdir(path, "user") or _isdir(path, "custom_nodes"))


def _version(code_root) -> str:
    try:
        with open(os.path.join(code_root, "comfyui_version.py"), encoding="utf-8") as f:
            m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", f.read())
            return m.group(1) if m else ""
    except OSError:
        return ""


# ── Portable / standalone ──────────────────────────────────────────────

def _bat_args(path) -> dict:
    """Puerto y --listen de la línea del .bat que lanza main.py."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read(64_000)
    except OSError:
        return {}
    for line in text.splitlines():
        low = line.lower()
        if "main.py" not in low or low.lstrip().startswith(("rem", "::")):
            continue
        port = re.search(r"--port[\s=]+(\d{2,5})\b", line)
        listen = re.search(r"--listen(?:[\s=]+([0-9a-fA-F.:]+))?", line)
        return {"port": int(port.group(1)) if port else None, "listen": bool(listen), "main": True}
    return {}


def _launchers(base) -> list:
    """Los .bat de `base` que arrancan ComfyUI, el más probable primero."""
    out = []
    for name in _listdir(base):
        if not name.lower().endswith((".bat", ".cmd")) or "update" in name.lower() or "install" in name.lower():
            continue
        args = _bat_args(os.path.join(base, name))
        if args.get("main"):
            low = name.lower()
            out.append((not low.startswith(("start", "run")), "cpu" in low, len(name), name, args))
    out.sort()
    return [(os.path.join(base, x[3]), x[4]) for x in out]


def _python_of(code_root, base):
    for p in (os.path.join(base, "python_embeded", "python.exe"), os.path.join(base, "python_embedded", "python.exe"),
              os.path.join(code_root, "venv", "Scripts", "python.exe"), os.path.join(code_root, ".venv", "Scripts", "python.exe"),
              os.path.join(base, "venv", "Scripts", "python.exe")):
        if os.path.isfile(p):
            return p
    return None


def _portable(code_root) -> dict:
    code_root = os.path.normpath(code_root)
    base = os.path.dirname(code_root)
    launchers = _launchers(base) or _launchers(code_root)
    launcher, args = launchers[0] if launchers else (None, {})
    py = _python_of(code_root, base)
    # La carpeta "de afuera" (la del .bat y python_embeded) si la hay.
    outer = bool(_launchers(base)) or bool(py and os.path.dirname(os.path.dirname(py)) == base)
    return {
        "kind": "portable",
        "path": code_root,
        "base": base if outer else code_root,
        "data": code_root,
        "launcher": launcher,
        "python": py,
        "port": args.get("port") or PORTABLE_PORT,
        "version": _version(code_root),
    }


# ── ComfyUI Desktop ────────────────────────────────────────────────────

def _desktop_exe():
    local = os.environ.get("LOCALAPPDATA") or ""
    for p in (os.path.join(local, "Programs", "@comfyorgcomfyui-electron", "ComfyUI.exe"),
              os.path.join(local, "Programs", "ComfyUI", "ComfyUI.exe"),
              os.path.join(local, "Programs", "comfyui-electron", "ComfyUI.exe")):
        if os.path.isfile(p):
            return p
    return None


def _find_port(obj, depth=0):
    """Un "port" en los ajustes de Desktop (la clave cambia entre versiones)."""
    if depth > 4:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in ("port", "--port") and str(v).strip().isdigit():
                return int(str(v).strip())
        for v in obj.values():
            hit = _find_port(v, depth + 1)
            if hit:
                return hit
    return None


def _desktop() -> dict:
    appdata = os.environ.get("APPDATA") or ""
    exe = _desktop_exe()
    base = ""
    try:
        with open(os.path.join(appdata, "ComfyUI", "config.json"), encoding="utf-8") as f:
            base = str((json.load(f) or {}).get("basePath") or "")
    except (OSError, ValueError, AttributeError):
        base = ""
    if not exe and not base:
        return {}
    port = None
    for p in (os.path.join(base, "user", "default", "comfy.settings.json"), os.path.join(appdata, "ComfyUI", "config.json")):
        try:
            with open(p, encoding="utf-8") as f:
                port = _find_port(json.load(f))
        except (OSError, ValueError):
            continue
        if port:
            break
    code = os.path.join(os.path.dirname(exe), "resources", "ComfyUI") if exe else ""
    return {
        "kind": "desktop",
        "path": os.path.normpath(base) if base else os.path.dirname(exe),
        "base": os.path.dirname(exe) if exe else base,
        "data": os.path.normpath(base) if base and _isdir(base) else "",
        "launcher": exe,
        "python": None,
        "port": port or DESKTOP_PORT,
        "version": _version(code) if code else "",
    }


# ── Búsqueda ───────────────────────────────────────────────────────────

def _drives() -> list:
    if os.name != "nt":
        return ["/"]
    out = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if letter in "AB":
            continue
        try:
            if os.path.isdir(root):
                out.append(root)
        except OSError:
            continue
    return out


def _places() -> list:
    home = os.path.expanduser("~")
    places = [home] + [os.path.join(home, x) for x in ("Desktop", "Documents", "Downloads", "AI", "Apps")]
    places += [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)")]
    places += [os.path.join(os.environ.get("LOCALAPPDATA") or "", "Programs")]
    return [p for p in dict.fromkeys(places) if p and _isdir(p)]


def _code_root_in(path):
    """La carpeta de ComfyUI dentro de `path` (él mismo o un nivel abajo)."""
    if is_code_root(path):
        return path
    for sub in ("ComfyUI", "comfyui", "ComfyUI-master"):
        if is_code_root(os.path.join(path, sub)):
            return os.path.join(path, sub)
    return None


def _scan(deadline) -> list:
    found = []
    seen = set()

    def look(path):
        root = _code_root_in(path)
        if root and os.path.normcase(root) not in seen:
            seen.add(os.path.normcase(root))
            found.append(_portable(root))

    starts = _drives() + _places()
    for start in starts:
        for name in _listdir(start):
            if time.time() > deadline:
                return found
            full = os.path.join(start, name)
            if name.lower() in SKIP or name.startswith(".") or not _isdir(full):
                continue
            if "comfy" in name.lower():
                look(full)
                continue
            # Un nivel más (p. ej. F:\AI\ComfyUI-Easy-Install, D:\StabilityMatrix\Packages\ComfyUI).
            for sub in _listdir(full)[:400]:
                low = sub.lower()
                if "comfy" in low:
                    look(os.path.join(full, sub))
                elif low in ("packages", "apps", "tools") and _isdir(full, sub):
                    for sub2 in _listdir(os.path.join(full, sub))[:200]:
                        if "comfy" in sub2.lower():
                            look(os.path.join(full, sub, sub2))
    return found


def find_all(timeout: float = 12.0) -> list:
    """Todas las instalaciones encontradas: Desktop primero si está, luego
    las portables (la carpeta de AuraVox/ComfyUI más cercana primero)."""
    out = []
    d = _desktop()
    if d:
        out.append(d)
    out += _scan(time.time() + timeout)
    return out


def info(path: str):
    """La instalación en `path` (elegida a mano) o None si no lo parece.
    Vale la carpeta de ComfyUI, la que la contiene (portable) o la carpeta
    de datos de Desktop."""
    path = os.path.normpath(os.path.expandvars(str(path or "").strip().strip('"')))
    if not path or not _isdir(path):
        return None
    root = _code_root_in(path)
    if root:
        return _portable(root)
    d = _desktop()
    if d and d.get("data") and os.path.normcase(d["data"]) == os.path.normcase(path):
        return d
    if is_data_root(path):
        exe = _desktop_exe()
        return {"kind": "desktop" if exe else "data", "path": path, "base": os.path.dirname(exe) if exe else path,
                "data": path, "launcher": exe, "python": None, "port": DESKTOP_PORT if exe else PORTABLE_PORT,
                "version": ""}
    return None


# ── Lo que hay en disco ────────────────────────────────────────────────

def workflows_dir(inst) -> str:
    data = (inst or {}).get("data") or ""
    return os.path.join(data, "user", "default", "workflows") if data else ""


def disk_workflows(inst) -> list:
    """Los flujos guardados (rutas relativas, como /userdata los da)."""
    folder = workflows_dir(inst)
    out = []
    if not folder or not os.path.isdir(folder):
        return out
    for dirpath, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.lower().endswith(".json"):
                out.append(os.path.relpath(os.path.join(dirpath, f), folder).replace("\\", "/"))
    return sorted(out, key=str.lower)


def read_workflow(inst, name: str):
    folder = workflows_dir(inst)
    path = os.path.normpath(os.path.join(folder, name))
    if not folder or not path.startswith(os.path.normpath(folder) + os.sep) or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def disk_models(inst, limit: int = 300) -> dict:
    """{tipo: [archivos]} de models\\ (sin seguir extra_model_paths.yaml)."""
    data = (inst or {}).get("data") or ""
    out = {}
    for kind in MODEL_DIRS:
        folder = os.path.join(data, "models", kind) if data else ""
        if not folder or not os.path.isdir(folder):
            continue
        names = []
        for dirpath, _dirs, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(MODEL_EXT):
                    names.append(os.path.relpath(os.path.join(dirpath, f), folder).replace("\\", "/"))
                    if len(names) >= limit:
                        break
        if names:
            out[kind] = sorted(names, key=str.lower)
    return out


# ── Arrancar ───────────────────────────────────────────────────────────

def can_start(inst) -> bool:
    inst = inst or {}
    return bool(inst.get("launcher") and os.path.isfile(inst["launcher"])) or bool(
        inst.get("kind") == "portable" and inst.get("python"))


def start(inst) -> str:
    """Abre ComfyUI en su propia ventana (como si se hiciera doble clic en
    su lanzador). Devuelve lo que se ejecutó."""
    inst = inst or {}
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    launcher = inst.get("launcher")
    if launcher and os.path.isfile(launcher):
        if launcher.lower().endswith((".bat", ".cmd")):
            subprocess.Popen(["cmd.exe", "/c", launcher], cwd=os.path.dirname(launcher), creationflags=flags,
                             close_fds=True)
        else:
            subprocess.Popen([launcher], cwd=os.path.dirname(launcher), close_fds=True,
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        return launcher
    if inst.get("kind") == "portable" and inst.get("python"):
        cmd = [inst["python"], "-s", os.path.join(inst["path"], "main.py"), "--windows-standalone-build"]
        if inst.get("port") and inst["port"] != PORTABLE_PORT:
            cmd += ["--port", str(inst["port"])]
        subprocess.Popen(cmd, cwd=inst.get("base") or inst["path"], creationflags=flags, close_fds=True)
        return " ".join(cmd)
    raise OSError("no launcher")


# ── Explorador de carpetas (para elegirla a mano) ──────────────────────

def browse(path: str) -> dict:
    """Subcarpetas de `path` (o las unidades) para el selector de la página,
    marcando las que parecen ComfyUI."""
    path = str(path or "").strip().strip('"')
    if not path:
        return {"path": "", "parent": None,
                "dirs": [{"name": d, "path": d, "comfy": False} for d in _drives()]
                + [{"name": p, "path": p, "comfy": bool(_code_root_in(p))} for p in _places()]}
    path = os.path.normpath(os.path.expandvars(path))
    if not _isdir(path):
        raise FileNotFoundError(path)
    parent = os.path.dirname(path)
    dirs = []
    for name in _listdir(path)[:500]:
        full = os.path.join(path, name)
        if name.startswith(("$", ".")) or not _isdir(full):
            continue
        dirs.append({"name": name, "path": full, "comfy": bool(_code_root_in(full) or is_data_root(full))})
    return {"path": path, "parent": parent if parent != path else "", "dirs": dirs, "here": bool(info(path))}
