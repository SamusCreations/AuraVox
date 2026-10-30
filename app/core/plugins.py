"""Sistema de plugins: herramientas que se agregan con una carpeta.

Cada plugin vive en plugins/<id>/ (en la raíz de AuraVox) con:
- manifest.json: {"id", "name", "description", "version", "author",
  "min_role": "guest" | "user" | "admin", "tools": [herramientas en el
  formato de Ollama: {"name", "description", "parameters"}]}.
- plugin.py: `call(name, args, ctx) -> str` (lo que el modelo lee como
  resultado). Opcionales: `tools(ctx) -> list` (si las herramientas
  dependen de algo, p. ej. de si Spotify está configurado) y
  `context(ctx) -> str` (texto para el system prompt).
`ctx` es el de app/core/skills.py (quién pregunta) o None en los modos de
consola.

Un plugin puede pedir ajustes (una URL, un token…): "settings" en el
manifiesto, [{"key", "label": {"es", "en"}, "type": "text" | "secret" |
"number" | "select" | "bool", "placeholder", "options": [{"value",
"label"}] (para select)}]. Los llena un administrador en Ajustes → Plugins
y el plugin los lee con plugins.settings("<id>"). Los "secret" nunca se
vuelven a mostrar. Opcional en plugin.py: check(settings) -> (ok, texto),
para el botón "Probar".

Rutas propias (opcional): http(method, action, data, ctx) -> dict o
(estado, dict), en /api/plugin/<id>/<acción> (GET: los parámetros de la
URL; POST: el JSON). Las puede usar quien tenga el rol mínimo del plugin;
lo que sea solo de administradores lo comprueba el plugin (ctx.role).

Los que vienen con AuraVox (búsqueda web y lugares, clima, Spotify) traen
"builtin": true y arrancan activados; uno nuevo arranca DESACTIVADO hasta
que un administrador lo active en Ajustes → Plugins (es código que corre
en esta PC). Lo que se activa y el rol mínimo de cada uno se guardan en
config/plugins.json. Ver plugins/README.md.
"""
import importlib.util
import json
import os
import re
import sys
import threading
import traceback

from app import paths

NAME = "plugins"
MIN_ROLE = "guest"

PLUGINS_DIR = os.path.join(paths.ROOT, "plugins")
STATE_PATH = os.path.join(paths.CONFIG_DIR, "plugins.json")
ID_RE = re.compile(r"^[a-z0-9_]{2,40}$")
TOOL_RE = re.compile(r"^[a-zA-Z0-9_]{1,64}$")
ROLES = ("guest", "user", "admin")
RANKS = {"guest": 1, "user": 2, "admin": 3}

_lock = threading.RLock()
_cache = {"key": None, "plugins": []}


class Plugin:
    def __init__(self, pid: str, folder: str, manifest: dict):
        self.id = pid
        self.folder = folder
        self.manifest = manifest
        self.module = None
        self.error = ""

    @property
    def builtin(self) -> bool:
        return bool(self.manifest.get("builtin"))

    def static_tools(self) -> list:
        out = []
        for t in self.manifest.get("tools") or []:
            if isinstance(t, dict) and TOOL_RE.match(str(t.get("name"))):
                out.append({"type": "function", "function": {
                    "name": t["name"], "description": str(t.get("description") or "")[:1000],
                    "parameters": t.get("parameters") if isinstance(t.get("parameters"), dict)
                    else {"type": "object", "properties": {}, "required": []},
                }})
        return out


# ── Descubrir y cargar ─────────────────────────────────────────────────

def _scan_key():
    try:
        entries = sorted(os.listdir(PLUGINS_DIR))
    except OSError:
        return ()
    key = []
    for e in entries:
        for f in ("manifest.json", "plugin.py"):
            p = os.path.join(PLUGINS_DIR, e, f)
            try:
                key.append((e, f, os.path.getmtime(p)))
            except OSError:
                pass
    try:
        key.append(("state", os.path.getmtime(STATE_PATH)))
    except OSError:
        pass
    return tuple(key)


def _load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(data: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)


def _import(p: Plugin) -> None:
    path = os.path.join(p.folder, "plugin.py")
    name = f"auravox_plugin_{p.id}"
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        if not callable(getattr(module, "call", None)):
            raise AttributeError("plugin.py no define call(name, args, ctx)")
        p.module = module
        p.error = ""
    except Exception as e:  # noqa: BLE001 — un plugin roto no tumba a los demás
        traceback.print_exc()
        p.module = None
        p.error = f"{type(e).__name__}: {e}"


def discover(force: bool = False) -> list:
    """Todos los plugins de la carpeta (los activos, ya importados)."""
    with _lock:
        key = _scan_key()
        if not force and key == _cache["key"]:
            return _cache["plugins"]
        state = _load_state()
        old = {p.id: p for p in _cache["plugins"]}
        found = []
        try:
            entries = sorted(os.listdir(PLUGINS_DIR))
        except OSError:
            entries = []
        for e in entries:
            folder = os.path.join(PLUGINS_DIR, e)
            mpath = os.path.join(folder, "manifest.json")
            if not (ID_RE.match(e) and os.path.isfile(mpath)):
                continue
            try:
                with open(mpath, encoding="utf-8") as f:
                    manifest = json.load(f)
                if not isinstance(manifest, dict):
                    raise ValueError("manifest.json no es un objeto")
            except (OSError, ValueError) as ex:
                p = Plugin(e, folder, {"name": e})
                p.error = f"manifest.json: {ex}"
                found.append(p)
                continue
            p = Plugin(e, folder, manifest)
            if enabled(p, state):
                prev = old.get(e)
                mtime = os.path.getmtime(os.path.join(folder, "plugin.py")) if os.path.isfile(os.path.join(folder, "plugin.py")) else 0
                if prev and prev.module and getattr(prev, "_mtime", None) == mtime and not force:
                    p.module, p._mtime = prev.module, mtime
                else:
                    _import(p)
                    p._mtime = mtime
            found.append(p)
        # Los de AuraVox primero, en su orden; después los demás por id.
        found.sort(key=lambda p: (not p.builtin, int(p.manifest.get('order') or 50) if str(p.manifest.get('order') or '50').isdigit() else 50, p.id))
        _cache.update(key=key, plugins=found)
        return found


def enabled(p: Plugin, state: dict = None) -> bool:
    state = _load_state() if state is None else state
    s = state.get(p.id) if isinstance(state.get(p.id), dict) else {}
    return bool(s.get("enabled", p.builtin and p.manifest.get("default_enabled", True)))


def min_role(p: Plugin, state: dict = None) -> str:
    state = _load_state() if state is None else state
    s = state.get(p.id) if isinstance(state.get(p.id), dict) else {}
    role = s.get("min_role") or p.manifest.get("min_role") or "guest"
    return role if role in ROLES else "admin"


def configure(pid: str, enabled_=None, min_role_=None) -> None:
    with _lock:
        state = _load_state()
        s = state.get(pid) if isinstance(state.get(pid), dict) else {}
        if enabled_ is not None:
            s["enabled"] = bool(enabled_)
        if min_role_ in ROLES:
            s["min_role"] = min_role_
        state[pid] = s
        _save_state(state)
        _cache["key"] = None


def _schema(p: Plugin) -> list:
    out = []
    for f in p.manifest.get("settings") or []:
        if isinstance(f, dict) and re.match(r"^[a-z0-9_]{1,40}$", str(f.get("key"))):
            item = {"key": f["key"], "label": f.get("label") or f["key"], "type": f.get("type") or "text",
                    "placeholder": str(f.get("placeholder") or "")[:200], "help": f.get("help") or ""}
            if item["type"] == "select":
                item["options"] = [{"value": str(o.get("value")), "label": o.get("label") or str(o.get("value"))}
                                   for o in f.get("options") or [] if isinstance(o, dict) and "value" in o]
            out.append(item)
    return out


def settings(pid: str) -> dict:
    """Los ajustes que guardó el administrador para el plugin `pid`."""
    s = _load_state().get(pid)
    return dict((s or {}).get("settings") or {}) if isinstance(s, dict) else {}


def set_settings(pid: str, values: dict) -> None:
    """Guarda los ajustes; un "secret" vacío deja el que estaba."""
    p = next((x for x in discover() if x.id == pid), None)
    if not p:
        raise KeyError(pid)
    with _lock:
        state = _load_state()
        s = state.get(pid) if isinstance(state.get(pid), dict) else {}
        current = dict(s.get("settings") or {})
        for f in _schema(p):
            if f["key"] not in (values or {}):
                continue
            v = str(values[f["key"]] if values[f["key"]] is not None else "").strip()[:4000]
            if f["type"] == "secret" and not v:
                continue
            if f["type"] == "bool":
                v = "true" if v.lower() in ("1", "true", "yes", "on") else "false"
            if f["type"] == "select" and v not in {o["value"] for o in f.get("options") or []}:
                continue
            current[f["key"]] = v
        s["settings"] = current
        state[pid] = s
        _save_state(state)
        _cache["key"] = None


def check(pid: str):
    """(ok, texto) del botón "Probar" del plugin, o None si no tiene."""
    p = next((x for x in discover() if x.id == pid), None)
    if not p or not p.module or not callable(getattr(p.module, "check", None)):
        return None
    try:
        ok, text = p.module.check(settings(pid))
        return bool(ok), str(text)[:500]
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def public() -> list:
    state = _load_state()
    out = []
    for p in discover():
        on = enabled(p, state)
        tools = p.static_tools()
        if on and p.module and callable(getattr(p.module, "tools", None)):
            try:
                tools = p.module.tools(None) or tools
            except Exception:  # noqa: BLE001
                pass
        out.append({
            "id": p.id, "name": str(p.manifest.get("name") or p.id), "description": str(p.manifest.get("description") or ""),
            "version": str(p.manifest.get("version") or ""), "author": str(p.manifest.get("author") or ""),
            "builtin": p.builtin, "enabled": on, "min_role": min_role(p, state), "error": p.error,
            "tools": [t["function"]["name"] for t in tools],
            "settings_schema": _schema(p),
            "settings": {f["key"]: ("" if f["type"] == "secret" else settings(p.id).get(f["key"], ""))
                         for f in _schema(p)},
            "secrets_set": [f["key"] for f in _schema(p) if f["type"] == "secret" and settings(p.id).get(f["key"])],
            "can_check": bool(p.module and callable(getattr(p.module, "check", None))),
            "has_http": bool(on and p.module and callable(getattr(p.module, "http", None))),
        })
    return out


# ── Uso (como habilidad, ver app/core/skills.py) ───────────────────────

def _usable(ctx) -> list:
    state = _load_state()
    role = getattr(ctx, "role", "admin") if ctx is not None else "admin"
    return [p for p in discover() if p.module and enabled(p, state)
            and RANKS.get(role, 0) >= RANKS[min_role(p, state)]]


def _tools_of(p: Plugin, ctx) -> list:
    if callable(getattr(p.module, "tools", None)):
        return p.module.tools(ctx) or []
    return p.static_tools()


def tools(ctx) -> list:
    out, seen = [], set()
    for p in _usable(ctx):
        try:
            for t in _tools_of(p, ctx):
                name = t["function"]["name"]
                if name not in seen:
                    seen.add(name)
                    out.append(t)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    return out


def context(ctx) -> str:
    parts = []
    for p in _usable(ctx):
        fn = getattr(p.module, "context", None)
        if callable(fn):
            try:
                text = fn(ctx)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                text = ""
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def call(name: str, args: dict, ctx):
    for p in _usable(ctx):
        try:
            names = {t["function"]["name"] for t in _tools_of(p, ctx)}
        except Exception:  # noqa: BLE001
            continue
        if name in names:
            result = p.module.call(name, args if isinstance(args, dict) else {}, ctx)
            return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    return None


def http(pid: str, method: str, action: str, data: dict, ctx):
    """(estado, dict) de una ruta propia del plugin (/api/plugin/<id>/<acción>)."""
    p = next((x for x in _usable(ctx) if x.id == pid), None)
    if not p or not callable(getattr(p.module, "http", None)):
        return 404, {"error": "not_found"}
    out = p.module.http(method, action, data if isinstance(data, dict) else {}, ctx)
    if isinstance(out, tuple):
        return out[0], out[1]
    return 200, out
