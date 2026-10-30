"""Archivos adjuntos originales, para poder abrirlos desde el chat.

Al adjuntar algo, la página manda también el archivo tal cual (además de su
texto o transcripción, que es lo que ve el modelo) y lo enlaza en el
mensaje: la imagen en grande, el PDF en el visor del navegador, el audio con
su reproductor. Se guardan en config/chats/files/ y se borran solos cuando
ya ninguna conversación guardada los usa (ver cleanup).

Seguridad: se sirven desde el mismo sitio que la interfaz, así que lo que
podría ejecutar código en él (HTML, SVG, XML, JavaScript) se entrega como
texto plano.
"""
import json
import mimetypes
import os
import re
import secrets
import threading
import time

from app.webui import chat_store

FILES_DIR = os.path.join(chat_store.CHATS_DIR, "files")
MAX_BYTES = 150_000_000
ID_RE = re.compile(r"^[0-9a-f]{24}(?:\.[a-z0-9]{1,8})?$")
AS_TEXT = {"html", "htm", "xhtml", "svg", "xml", "js", "mjs", "cjs", "xsl", "xslt"}
KEEP_UNUSED = 24 * 3600          # un archivo sin conversación que lo use se borra después de esto
_last_cleanup = [0.0]
_lock = threading.Lock()


def _ext(name: str) -> str:
    m = re.search(r"\.([A-Za-z0-9]{1,8})$", name or "")
    return m.group(1).lower() if m else ""


def save(name: str, data: bytes) -> dict:
    ext = _ext(name)
    file_id = secrets.token_hex(12) + (f".{ext}" if ext else "")
    os.makedirs(FILES_DIR, exist_ok=True)
    with open(os.path.join(FILES_DIR, file_id), "wb") as f:
        f.write(data)
    with open(os.path.join(FILES_DIR, file_id + ".json"), "w", encoding="utf-8") as f:
        json.dump({"name": os.path.basename(name or file_id)[:200], "size": len(data), "at": time.time()}, f)
    cleanup()
    return {"id": file_id, "url": f"/api/files/{file_id}"}


def open_file(file_id: str):
    """(ruta, content-type, nombre original) o None."""
    if not ID_RE.match(file_id or ""):
        return None
    path = os.path.join(FILES_DIR, file_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path + ".json", encoding="utf-8") as f:
            name = json.load(f).get("name") or file_id
    except (OSError, ValueError):
        name = file_id
    ext = _ext(file_id)
    if ext in AS_TEXT:
        ctype = "text/plain; charset=utf-8"
    else:
        ctype = mimetypes.guess_type("x." + ext)[0] if ext else None
        ctype = ctype or "application/octet-stream"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
    return path, ctype, name


_FILE_URL_RE = re.compile(r"/api/files/([0-9a-f]{24}(?:\.[a-z0-9]{1,8})?)")


def ids_in(data) -> set:
    """Los archivos (adjuntos o convertidos) que menciona una conversación."""
    return set(_FILE_URL_RE.findall(json.dumps(data, ensure_ascii=False)))


def _used_ids() -> set:
    used = set()
    for folder, _dirs, entries in os.walk(chat_store.CHATS_DIR):
        if os.path.abspath(folder) == os.path.abspath(FILES_DIR):
            continue
        for entry in entries:
            if not entry.endswith(".json"):
                continue
            try:
                with open(os.path.join(folder, entry), encoding="utf-8") as f:
                    used.update(_FILE_URL_RE.findall(f.read()))
            except OSError:
                continue
    jobs_file = os.path.join(os.path.dirname(chat_store.CHATS_DIR), "comfyui", "jobs.json")
    if os.path.isfile(jobs_file):
        try:
            with open(jobs_file, encoding="utf-8") as f:
                used.update(_FILE_URL_RE.findall(f.read()))
        except OSError:
            pass
    return used


def forget(ids) -> int:
    """Borra ya los archivos de `ids` que ninguna conversación guardada usa
    (al reiniciar un chat: se van con él). Devuelve cuántos borró."""
    ids = {i for i in ids if ID_RE.match(i or "")}
    if not ids:
        return 0
    removed = 0
    with _lock:
        for file_id in ids - _used_ids():
            path = os.path.join(FILES_DIR, file_id)
            if not os.path.exists(path):
                continue
            for p in (path, path + ".json"):
                try:
                    os.remove(p)
                except OSError:
                    pass
            removed += 1
    return removed


def cleanup(force: bool = False) -> None:
    """Borra los archivos que ya no usa ninguna conversación guardada (como
    mucho una vez por hora)."""
    if not force and time.time() - _last_cleanup[0] < 3600:
        return
    _last_cleanup[0] = time.time()
    if not os.path.isdir(FILES_DIR):
        return
    with _lock:
        # Las conversaciones de todos los perfiles (config/chats/<perfil>/) y
        # las de antes de los perfiles (config/chats/*.json). Las de un
        # invitado están en su navegador: sus archivos duran KEEP_UNUSED.
        used = _used_ids()
        now = time.time()
        for entry in os.listdir(FILES_DIR):
            if entry.endswith(".json") or entry in used:
                continue
            path = os.path.join(FILES_DIR, entry)
            if now - os.path.getmtime(path) > KEEP_UNUSED:
                for p in (path, path + ".json"):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
