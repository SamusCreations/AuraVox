"""Respaldo y restauración: todo lo del usuario en un .zip.

Qué entra (todo dentro de config/): asistentes (assistants.yaml), alias
(wake_words.txt), ajustes de voz y voces clonadas (custom_voices/),
perfiles (sin las sesiones abiertas), conversaciones, memoria,
recordatorios, listas, documentos de los asistentes, rutinas, plugins y
servidores MCP. Opcional: los adjuntos originales de los chats (pueden
pesar) y las claves (la de acceso por red, Spotify y las variables de los
servidores MCP; sin ellas, mcp.json va sin sus valores secretos).
Nunca entran el certificado ni las mediciones de memoria.

Los respaldos se guardan en backups/ (en la raíz de AuraVox) y se pueden
descargar. Se hace uno automático por día al arrancar (se guardan los
últimos AUTO_KEEP) y otro siempre antes de restaurar.

Restaurar reemplaza esos archivos por los del zip: valida el manifiesto,
no acepta rutas fuera de config/ y conserva las sesiones abiertas (así
quien restaura no queda afuera si su perfil sigue existiendo).
"""
import datetime
import json
import os
import re
import shutil
import tempfile
import threading
import time
import zipfile

from app import paths

# Junto a config/ (con AURAVOX_CONFIG, junto a esa otra carpeta: una instancia
# de prueba no mezcla sus respaldos con los de verdad).
BACKUPS_DIR = os.path.join(os.path.dirname(os.path.abspath(paths.CONFIG_DIR)), "backups")
FORMAT = "auravox.backup"
VERSION = 1
NAME_RE = re.compile(r"^auravox-[a-z0-9-]{1,60}\.zip$")
AUTO_KEEP = 7
MAX_UPLOAD = 4 * 1024 ** 3

# Rutas relativas a config/ (archivos o carpetas).
ALWAYS = ["assistants.yaml", "wake_words.txt", "languages.txt", "voice_settings.yaml", "custom_voices",
          "profiles.json", "chats", "memory", "reminders.json", "lists", "knowledge", "routines", "plugins.json",
          "mcp.json", "voice_listener.json", "model_updates.json"]
SECRETS = ["network.json", "spotify_config.yaml"]
NEVER = {"certs", "model_memory.json", "assistants.yaml.bak"}
ATTACHMENTS = os.path.join("chats", "files")

_lock = threading.Lock()


def _cfg(*parts) -> str:
    return os.path.join(paths.CONFIG_DIR, *parts)


def _walk(rel: str):
    """(ruta relativa a config/, ruta real) de un archivo o de todo lo de una carpeta."""
    full = _cfg(rel)
    if os.path.isfile(full):
        yield rel.replace(os.sep, "/"), full
    elif os.path.isdir(full):
        for folder, _dirs, files in os.walk(full):
            for f in files:
                if f.endswith(".tmp"):
                    continue
                real = os.path.join(folder, f)
                yield os.path.relpath(real, paths.CONFIG_DIR).replace(os.sep, "/"), real


def _mcp_without_secrets(raw: bytes) -> bytes:
    try:
        data = json.loads(raw.decode("utf-8"))
        for s in data.get("servers") or []:
            if isinstance(s, dict):
                s["env"] = {k: "" for k in (s.get("env") or {})}
                s["headers"] = {k: "" for k in (s.get("headers") or {})}
        return json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
    except (ValueError, AttributeError):
        return raw


def _plugins_without_secrets(raw: bytes) -> bytes:
    """Los ajustes "secret" de los plugins (tokens) van vacíos."""
    try:
        from app.core import plugins

        data = json.loads(raw.decode("utf-8"))
        secret = {p.id: {f["key"] for f in plugins._schema(p) if f["type"] == "secret"}  # noqa: SLF001
                  for p in plugins.discover()}
        for pid, s in data.items():
            if isinstance(s, dict) and isinstance(s.get("settings"), dict):
                for k in secret.get(pid, set()):
                    if k in s["settings"]:
                        s["settings"][k] = ""
        return json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
    except (ValueError, AttributeError, TypeError):
        return raw


def _profiles_without_sessions(raw: bytes) -> bytes:
    try:
        data = json.loads(raw.decode("utf-8"))
        data["sessions"] = {}
        return json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
    except (ValueError, TypeError):
        return raw


def create(kind: str = "manual", attachments: bool = False, secrets: bool = False) -> dict:
    """Crea backups/auravox-<fecha>-<tipo>.zip y devuelve su info."""
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"auravox-{stamp}-{kind}.zip"
    path = os.path.join(BACKUPS_DIR, name)
    items = ALWAYS + (SECRETS if secrets else [])
    count = 0
    with _lock, zipfile.ZipFile(path + ".tmp", "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel in items:
            for arc, real in _walk(rel):
                if not attachments and arc.startswith(ATTACHMENTS.replace(os.sep, "/") + "/"):
                    continue
                if arc.split("/")[0] in NEVER:
                    continue
                try:
                    with open(real, "rb") as f:
                        raw = f.read()
                except OSError:
                    continue
                if arc == "profiles.json":
                    raw = _profiles_without_sessions(raw)
                elif arc == "mcp.json" and not secrets:
                    raw = _mcp_without_secrets(raw)
                elif arc == "plugins.json" and not secrets:
                    raw = _plugins_without_secrets(raw)
                z.writestr("config/" + arc, raw)
                count += 1
        z.writestr("manifest.json", json.dumps({
            "format": FORMAT, "version": VERSION, "app": "AuraVox", "created": time.time(), "kind": kind,
            "attachments": attachments, "secrets": secrets, "files": count,
        }, ensure_ascii=False, indent=1))
    os.replace(path + ".tmp", path)
    return info(name)


def info(name: str) -> dict:
    path = os.path.join(BACKUPS_DIR, name)
    meta = {}
    try:
        with zipfile.ZipFile(path) as z:
            meta = json.loads(z.read("manifest.json").decode("utf-8"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        pass
    return {"name": name, "size": os.path.getsize(path), "created": meta.get("created") or os.path.getmtime(path),
            "kind": meta.get("kind", ""), "attachments": bool(meta.get("attachments")), "secrets": bool(meta.get("secrets")),
            "files": meta.get("files", 0)}


def list_backups() -> list:
    try:
        names = [n for n in os.listdir(BACKUPS_DIR) if NAME_RE.match(n)]
    except OSError:
        return []
    return sorted((info(n) for n in names), key=lambda b: -b["created"])


def path_of(name: str) -> str:
    if not NAME_RE.match(name or ""):
        raise KeyError(name)
    path = os.path.join(BACKUPS_DIR, name)
    if not os.path.isfile(path):
        raise KeyError(name)
    return path


def delete(name: str) -> None:
    os.remove(path_of(name))


def auto_daily() -> None:
    """Un respaldo automático por día (sin adjuntos ni claves)."""
    today = datetime.datetime.now().strftime("%Y%m%d")
    autos = [b for b in list_backups() if b["kind"] == "auto"]
    if not any(b["name"].startswith(f"auravox-{today}-") for b in autos):
        create("auto")
        autos = [b for b in list_backups() if b["kind"] == "auto"]
    for old in autos[AUTO_KEEP:]:
        try:
            delete(old["name"])
        except (KeyError, OSError):
            pass


class RestoreError(Exception):
    pass


def restore(zip_path: str) -> dict:
    """Reemplaza lo de config/ por lo del zip (antes hace un respaldo de lo
    actual). Devuelve {"files", "safety"}."""
    try:
        z = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile):
        raise RestoreError("backup_bad")
    with z:
        try:
            meta = json.loads(z.read("manifest.json").decode("utf-8"))
        except (KeyError, ValueError):
            raise RestoreError("backup_bad")
        if meta.get("format") != FORMAT:
            raise RestoreError("backup_bad")
        if int(meta.get("version") or 0) > VERSION:
            raise RestoreError("backup_newer")
        members = []
        allowed_top = set(ALWAYS) | set(SECRETS)
        for m in z.infolist():
            if m.is_dir() or m.filename == "manifest.json":
                continue
            name = m.filename.replace("\\", "/")
            if not name.startswith("config/") or ".." in name.split("/") or name.startswith("/") or ":" in name:
                raise RestoreError("backup_bad")
            rel = name[len("config/"):]
            if rel.split("/")[0] not in allowed_top:
                continue
            members.append((m, rel))
        safety = create("before-restore", attachments=False, secrets=True)
        tmp = tempfile.mkdtemp(prefix="auravox-restore-")
        try:
            for m, rel in members:
                target = os.path.join(tmp, *rel.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(m) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            with _lock:
                tops = {rel.split("/")[0] for _m, rel in members}
                # Sesiones abiertas: se conservan las de los perfiles que siguen existiendo.
                sessions = {}
                try:
                    with open(_cfg("profiles.json"), encoding="utf-8") as f:
                        sessions = json.load(f).get("sessions") or {}
                except (OSError, ValueError):
                    pass
                for top in tops:
                    src = os.path.join(tmp, top)
                    dst = _cfg(top)
                    if os.path.isdir(src):
                        if top == "chats" and not meta.get("attachments"):
                            # Sin adjuntos en el zip: se quedan los que ya había.
                            keep = _cfg(ATTACHMENTS)
                            if os.path.isdir(keep):
                                shutil.move(keep, os.path.join(tmp, "_files_keep"))
                        shutil.rmtree(dst, ignore_errors=True)
                        shutil.copytree(src, dst)
                        kept = os.path.join(tmp, "_files_keep")
                        if top == "chats" and os.path.isdir(kept):
                            shutil.rmtree(_cfg(ATTACHMENTS), ignore_errors=True)
                            shutil.move(kept, _cfg(ATTACHMENTS))
                    else:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copyfile(src, dst)
                if "profiles.json" in tops and sessions:
                    try:
                        with open(_cfg("profiles.json"), encoding="utf-8") as f:
                            data = json.load(f)
                        ids = {p.get("id") for p in data.get("profiles") or []}
                        data["sessions"] = {k: s for k, s in sessions.items()
                                            if isinstance(s, dict) and (s.get("guest") or s.get("profile") in ids)}
                        with open(_cfg("profiles.json"), "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=1)
                    except (OSError, ValueError):
                        pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return {"files": len(members), "safety": safety["name"]}


def save_upload(stream, length: int) -> str:
    """Guarda un zip subido en un archivo temporal (para restaurarlo)."""
    if length <= 0 or length > MAX_UPLOAD:
        raise RestoreError("backup_bad")
    fd, path = tempfile.mkstemp(suffix=".zip", prefix="auravox-upload-")
    left = length
    with os.fdopen(fd, "wb") as f:
        while left > 0:
            chunk = stream.read(min(left, 1 << 20))
            if not chunk:
                break
            f.write(chunk)
            left -= len(chunk)
    return path

