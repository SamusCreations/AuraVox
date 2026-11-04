"""Local secrets (API keys of remote LLM providers, Hugging Face token).

Stored in config/secrets.json (git-ignored, never sent to the browser). On
Windows every value is encrypted with DPAPI (CryptProtectData, tied to the
current Windows user), so copying the file to another PC or user does not
reveal the keys; elsewhere it falls back to plain text in that local file.
"""
import base64
import json
import os
import sys
import threading

from app import paths

SECRETS_JSON = os.path.join(paths.CONFIG_DIR, "secrets.json")
_lock = threading.RLock()
_ENTROPY = b"AuraVox secrets v1"


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _blob(data: bytes):
        buf = ctypes.create_string_buffer(data, len(data))
        return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    def _dpapi(data: bytes, protect: bool) -> bytes:
        crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
        src, _keep = _blob(data)
        ent, _keep2 = _blob(_ENTROPY)
        out = _Blob()
        fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        ok = fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, 0x01, ctypes.byref(out))  # UI_FORBIDDEN
        if not ok:
            raise OSError("DPAPI failed")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            kernel32.LocalFree(out.pbData)

    def _encode(value: str) -> str:
        return "dpapi:" + base64.b64encode(_dpapi(value.encode("utf-8"), True)).decode("ascii")

    def _decode(stored: str) -> str:
        if stored.startswith("dpapi:"):
            try:
                return _dpapi(base64.b64decode(stored[6:]), False).decode("utf-8")
            except (OSError, ValueError):
                return ""  # another Windows user / PC: the key has to be entered again
        return stored[6:] if stored.startswith("plain:") else stored
else:
    def _encode(value: str) -> str:
        return "plain:" + value

    def _decode(stored: str) -> str:
        if stored.startswith("dpapi:"):
            return ""
        return stored[6:] if stored.startswith("plain:") else stored


def _load() -> dict:
    try:
        with open(SECRETS_JSON, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(SECRETS_JSON), exist_ok=True)
    tmp = SECRETS_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, SECRETS_JSON)


def get(key: str) -> str:
    with _lock:
        stored = _load().get(key)
    return _decode(stored) if isinstance(stored, str) else ""


def has(key: str) -> bool:
    return bool(get(key))


def set(key: str, value: str) -> None:  # noqa: A001 — module-level API: secrets_store.set(...)
    with _lock:
        data = _load()
        if value:
            data[key] = _encode(str(value))
        else:
            data.pop(key, None)
        _save(data)


def delete_prefix(prefix: str, keep=()) -> None:
    """Removes every secret whose key starts with `prefix` except those in `keep`."""
    with _lock:
        data = _load()
        drop = [k for k in data if k.startswith(prefix) and k not in keep]
        if drop:
            for k in drop:
                data.pop(k, None)
            _save(data)
