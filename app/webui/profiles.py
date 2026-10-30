"""Perfiles de la interfaz web: quién está usando AuraVox y qué puede hacer.

Cada perfil tiene su nombre, su color, un PIN opcional (obligatorio para un
administrador), sus datos personales (lo que antes era `user_context` de
assistants.yaml: nombre, país, ubicación) y sus conversaciones
(config/chats/<perfil>/). Roles:

- "admin": todo, también lo delicado: eliminar/descargar/actualizar
  modelos, actualizar Ollama, el acceso por red, las voces clonadas, las
  reglas compartidas y crear/borrar perfiles.
- "user" (normal): chatear, crear sus asistentes (privados o compartidos) y
  editar los suyos, y sus propios datos. Ve los modelos pero no los toca.
- Invitado: no es un perfil guardado. Usa los asistentes compartidos y sus
  datos y conversaciones quedan en el navegador (sessionStorage): se
  pierden al salir o cerrar la pestaña.

La sesión va en una cookie (HttpOnly) con un token aleatorio; aquí se
guarda solo su hash (config/profiles.json), así sobrevive a los reinicios
de la recarga en caliente. Los PIN se guardan con PBKDF2.

Sin perfiles todavía (primera vez, o una instalación de antes de los
perfiles), la página pide crear el administrador; al crearlo se le pasan
los datos de `user_context` y las conversaciones que ya había.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import threading
import time

from app import paths

PROFILES_PATH = os.path.join(paths.CONFIG_DIR, "profiles.json")
COOKIE = "auravox_session"
ROLES = ("admin", "user")
GUEST = "guest"
ID_RE = re.compile(r"^p[0-9a-f]{8}$")
COLOR_RE = re.compile(r"^#[0-9a-f]{6}$")
MAX_PROFILES = 30
NAME_MAX = 40
PIN_RE = re.compile(r"^\S{4,64}$")
SESSION_DAYS = 60                # una sesión sin usar se vence después de esto
GUEST_HOURS = 12
MAX_FAILS, LOCK_SECONDS = 5, 60  # PIN mal puesto: se bloquea un rato
_ITERATIONS = 200_000

_lock = threading.RLock()
_fails = {}  # perfil → (intentos, hasta cuándo está bloqueado)


class ProfileError(Exception):
    def __init__(self, key: str, status: int = 400, **params):
        super().__init__(key)
        self.key = key
        self.status = status
        self.params = params


# ── Archivo ────────────────────────────────────────────────────────────

def _load() -> dict:
    try:
        with open(PROFILES_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data["profiles"] = [p for p in data.get("profiles") or [] if isinstance(p, dict) and ID_RE.match(str(p.get("id")))]
    data["sessions"] = data.get("sessions") if isinstance(data.get("sessions"), dict) else {}
    return data


def _save(data: dict) -> None:
    os.makedirs(paths.CONFIG_DIR, exist_ok=True)
    tmp = PROFILES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PROFILES_PATH)


def _hash_pin(pin: str, salt: str = None) -> dict:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS).hex()
    return {"salt": salt, "hash": digest}


def _pin_ok(profile: dict, pin: str) -> bool:
    stored = profile.get("pin") or {}
    if not stored.get("hash"):
        return True  # perfil sin PIN
    return hmac.compare_digest(_hash_pin(str(pin or ""), stored.get("salt"))["hash"], stored["hash"])


def _token_key(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _clean(value, limit: int) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", str(value or "")).strip()[:limit]


def public(p: dict) -> dict:
    return {"id": p["id"], "name": p["name"], "role": p["role"], "color": p.get("color") or "",
            "has_pin": bool((p.get("pin") or {}).get("hash"))}


def _find(data: dict, pid: str) -> dict:
    p = next((x for x in data["profiles"] if x["id"] == pid), None)
    if not p:
        raise ProfileError("profile_missing", 404)
    return p


# ── Consultas ──────────────────────────────────────────────────────────

def setup_needed() -> bool:
    with _lock:
        return not _load()["profiles"]


def list_public() -> list:
    with _lock:
        return [public(p) for p in _load()["profiles"]]


def session(token: str):
    """{"id", "name", "role", "guest", "user_context"} de la sesión, o None.
    Para un invitado `id` es None y `user_context` viene de la página."""
    if not token:
        return None
    with _lock:
        data = _load()
        key = _token_key(token)
        s = data["sessions"].get(key)
        if not isinstance(s, dict):
            return None
        now = time.time()
        ttl = GUEST_HOURS * 3600 if s.get("guest") else SESSION_DAYS * 86400
        if now - float(s.get("seen") or 0) > ttl:
            data["sessions"].pop(key, None)
            _save(data)
            return None
        if s.get("guest"):
            out = {"id": None, "name": "", "role": GUEST, "guest": True, "user_context": {}}
        else:
            p = next((x for x in data["profiles"] if x["id"] == s.get("profile")), None)
            if not p:
                data["sessions"].pop(key, None)
                _save(data)
                return None
            out = {**public(p), "guest": False, "user_context": dict(p.get("user_context") or {})}
        if now - float(s.get("seen") or 0) > 3600:  # se renueva, sin escribir el archivo en cada petición
            s["seen"] = now
            _save(data)
        return out


# ── Sesiones ───────────────────────────────────────────────────────────

def _new_session(data: dict, **fields) -> str:
    token = secrets.token_urlsafe(24)
    now = time.time()
    # Fuera las vencidas, para que el archivo no crezca.
    for key, s in list(data["sessions"].items()):
        ttl = GUEST_HOURS * 3600 if s.get("guest") else SESSION_DAYS * 86400
        if now - float(s.get("seen") or 0) > ttl:
            data["sessions"].pop(key)
    data["sessions"][_token_key(token)] = {**fields, "seen": now}
    return token


def login(pid: str, pin: str) -> str:
    with _lock:
        data = _load()
        p = _find(data, pid)
        count, until = _fails.get(pid, (0, 0))
        if until > time.time():
            raise ProfileError("pin_locked", 429, s=int(until - time.time()) + 1)
        if not _pin_ok(p, pin):
            count += 1
            _fails[pid] = (0, time.time() + LOCK_SECONDS) if count >= MAX_FAILS else (count, 0)
            raise ProfileError("pin_wrong", 403)
        _fails.pop(pid, None)
        token = _new_session(data, profile=pid)
        _save(data)
        return token


def guest_login() -> str:
    with _lock:
        data = _load()
        token = _new_session(data, guest=True)
        _save(data)
        return token


def logout(token: str) -> None:
    with _lock:
        data = _load()
        if data["sessions"].pop(_token_key(token), None) is not None:
            _save(data)


# ── Crear / cambiar / borrar ───────────────────────────────────────────

def _validate(data: dict, name, role, pin, color, pid=None) -> dict:
    out = {}
    name = _clean(name, NAME_MAX)
    if not name:
        raise ProfileError("profile_name_required")
    if any(p["name"].lower() == name.lower() and p["id"] != pid for p in data["profiles"]):
        raise ProfileError("profile_name_taken", name=name)
    out["name"] = name
    if role not in ROLES:
        raise ProfileError("profile_role_invalid")
    out["role"] = role
    color = _clean(color, 7).lower()
    out["color"] = color if COLOR_RE.match(color) else ""
    if pin is not None and pin != "" and not PIN_RE.match(str(pin)):
        raise ProfileError("pin_format")
    return out


def create(name: str, role: str, pin: str = "", color: str = "", user_context: dict = None) -> dict:
    """Perfil nuevo. El primero tiene que ser administrador (lo crea quien
    instala AuraVox) y se queda con lo que ya había (ver _adopt_legacy)."""
    with _lock:
        data = _load()
        first = not data["profiles"]
        if first and role != "admin":
            raise ProfileError("first_admin")
        if len(data["profiles"]) >= MAX_PROFILES:
            raise ProfileError("profiles_max", n=MAX_PROFILES)
        clean = _validate(data, name, role, pin, color)
        if role == "admin" and not pin:
            raise ProfileError("admin_pin_required")
        profile = {"id": "p" + secrets.token_hex(4), **clean, "pin": _hash_pin(pin) if pin else None,
                   "user_context": user_context or {}, "created_at": time.time()}
        data["profiles"].append(profile)
        _save(data)
        if first:
            _adopt_legacy(profile["id"])
        return public(profile)


def update(pid: str, name=None, role=None, pin=None, color=None, clear_pin: bool = False) -> dict:
    with _lock:
        data = _load()
        p = _find(data, pid)
        clean = _validate(data, p["name"] if name is None else name, p["role"] if role is None else role,
                          pin, p.get("color") if color is None else color, pid)
        if p["role"] == "admin" and clean["role"] != "admin" and _admins(data) == [pid]:
            raise ProfileError("last_admin")
        if pin:
            p["pin"] = _hash_pin(pin)
        elif clear_pin:
            p["pin"] = None
        if clean["role"] == "admin" and not (p.get("pin") or {}).get("hash"):
            raise ProfileError("admin_pin_required")
        p.update(clean)
        _save(data)
        return public(p)


def set_user_context(pid: str, user_context: dict) -> None:
    with _lock:
        data = _load()
        _find(data, pid)["user_context"] = dict(user_context or {})
        _save(data)


def check_pin(pid: str, pin: str) -> bool:
    with _lock:
        return _pin_ok(_find(_load(), pid), pin)


def _admins(data: dict) -> list:
    return [p["id"] for p in data["profiles"] if p["role"] == "admin"]


def delete(pid: str) -> None:
    """Borra el perfil, sus sesiones y sus conversaciones. Sus asistentes
    los pasa config_ui a quien lo borra (ver store.transfer_owner)."""
    with _lock:
        data = _load()
        p = _find(data, pid)
        if p["role"] == "admin" and _admins(data) == [pid]:
            raise ProfileError("last_admin")
        data["profiles"] = [x for x in data["profiles"] if x["id"] != pid]
        data["sessions"] = {k: s for k, s in data["sessions"].items() if s.get("profile") != pid}
        _save(data)
    shutil.rmtree(chats_dir(pid), ignore_errors=True)


# ── Conversaciones de cada perfil ──────────────────────────────────────

def chats_dir(pid: str) -> str:
    if not ID_RE.match(pid or ""):
        raise ValueError("perfil inválido")
    return os.path.join(paths.CONFIG_DIR, "chats", pid)


def _adopt_legacy(pid: str) -> None:
    """Primer administrador: las conversaciones guardadas antes de los
    perfiles (config/chats/<asistente>.json) pasan a ser suyas, y también
    los datos de user_context de assistants.yaml."""
    root = os.path.join(paths.CONFIG_DIR, "chats")
    target = chats_dir(pid)
    try:
        entries = os.listdir(root)
    except OSError:
        entries = []
    for entry in entries:
        src = os.path.join(root, entry)
        if entry.endswith(".json") and os.path.isfile(src):
            os.makedirs(target, exist_ok=True)
            os.replace(src, os.path.join(target, entry))
    from app.core import config_store

    try:
        uc = config_store.load_state()["user_context"]
    except Exception:  # noqa: BLE001 - sin assistants.yaml legible, el perfil empieza vacío
        uc = {}
    if any(v not in (None, "") for v in uc.values()):
        set_user_context(pid, uc)
