"""Exportar / importar asistentes: un archivo .auravox para compartirlos.

Es un JSON con la personalidad, los parámetros, el color, los idiomas, el
modelo, la voz (si es una voz clonada, su audio de referencia va adentro),
los alias para llamarlo y, si se pide, el texto de sus documentos. Sin
datos de quien lo exporta (dueño, conversaciones, memoria).

Al importar se crea un asistente nuevo, privado, de quien lo importa (si
el nombre ya existe se le agrega un número). Una voz clonada solo la puede
crear un administrador; para los demás se usa su voz de respaldo.
"""
import base64
import os
import re
import time

from app import paths
from app.core import config_store as store
from app.core import voice_settings
from app.skills import knowledge

FORMAT = "auravox.assistant"
VERSION = 1
EXPORT_FIELDS = sorted(store.KNOWN_FIELDS - {"owner", "shared"})
MAX_VOICE_BYTES = 8_000_000


class ImportError_(Exception):
    def __init__(self, key: str, **params):
        super().__init__(key)
        self.key = key
        self.params = params


def export(name: str, with_docs: bool = False) -> dict:
    a = next((x for x in store.load_state()["assistants"] if x["name"] == name), None)
    if a is None:
        raise KeyError(name)
    out = {
        "format": FORMAT, "version": VERSION, "app": "AuraVox", "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "assistant": {"name": a["name"], **{k: a.get(k) for k in EXPORT_FIELDS}, "aliases": list(a.get("aliases") or [])},
    }
    out["assistant"]["push_to_talk_key"] = ""  # es de este teclado/PC
    if voice_settings.is_custom(a["voice"]):
        v = voice_settings.get_voice(a["voice"])
        if v and os.path.isfile(v["path"]) and os.path.getsize(v["path"]) <= MAX_VOICE_BYTES:
            with open(v["path"], "rb") as f:
                audio = base64.b64encode(f.read()).decode("ascii")
            out["custom_voice"] = {"name": v.get("name") or "", "ref_text": v.get("ref_text") or "",
                                   "language": v.get("language") or "", "fallback_voice": v.get("fallback_voice") or "M5",
                                   "wav_base64": audio}
    if with_docs:
        data = knowledge._read(name)  # noqa: SLF001
        texts = {}
        for c in sorted(data["chunks"], key=lambda c: (c["file"], c["i"])):
            texts.setdefault(c["file"], []).append(c["text"])
        out["documents"] = [{"name": f["name"], "format": f.get("format") or "", "text": _join(texts.get(f["id"], []))}
                            for f in data["files"]]
    return out


def _join(parts: list) -> str:
    """El texto original a partir de los trozos (que se solapan)."""
    if not parts:
        return ""
    text = parts[0]
    for p in parts[1:]:
        overlap = 0
        for n in range(min(len(p), knowledge.OVERLAP + 50), 10, -1):
            if text.endswith(p[:n]):
                overlap = n
                break
        text += ("" if overlap else "\n") + p[overlap:]
    return text


def _free_name(base: str, taken: set) -> str:
    base = re.sub(r"[^a-z0-9]", "", str(base or "").lower())
    if not re.match(r"^[a-z]", base):
        base = "asistente" + base
    base = base[:26] or "asistente"
    if len(base) < 2:
        base += "x"
    name, n = base, 2
    while name in taken or name in store.RESERVED_NAMES:
        name = f"{base}{n}"
        n += 1
    return name


def import_file(payload: dict, owner: str, is_admin: bool, languages: list) -> dict:
    """Crea el asistente. Devuelve {"name", "notes": [avisos]}."""
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise ImportError_("import_format")
    if int(payload.get("version") or 0) > VERSION:
        raise ImportError_("import_version")
    src = payload.get("assistant")
    if not isinstance(src, dict):
        raise ImportError_("import_format")
    state = store.load_state()
    taken = {a["name"] for a in state["assistants"]}
    notes = []
    data = {k: src.get(k) for k in EXPORT_FIELDS if k in src}
    data["name"] = _free_name(src.get("name") or src.get("label") or "asistente", taken)
    if data["name"] != str(src.get("name") or ""):
        notes.append(("import_renamed", {"name": data["name"]}))
    # Los alias son variantes de cómo suena SU nombre: si se renombró, ya no sirven.
    renamed = data["name"] != str(src.get("name") or "")
    data["aliases"] = [] if renamed else [str(x) for x in src.get("aliases") or [] if isinstance(x, str)][:20]
    data["push_to_talk_key"] = ""
    data["shared"] = False
    if isinstance(data.get("languages"), list):
        data["languages"] = [c for c in data["languages"] if c in languages]
    if data.get("language") not in languages:
        data["language"] = (data.get("languages") or ["es"])[0]

    voice = str(data.get("voice") or "")
    custom = payload.get("custom_voice") if isinstance(payload.get("custom_voice"), dict) else None
    if voice_settings.is_custom(voice):
        fallback = str((custom or {}).get("fallback_voice") or "M5").upper()
        fallback = fallback if re.fullmatch(r"[FM][1-5]", fallback) else "M5"
        if custom and is_admin and custom.get("wav_base64"):
            try:
                audio = base64.b64decode(custom["wav_base64"], validate=True)
            except (ValueError, TypeError):
                audio = b""
            if 1000 < len(audio) <= MAX_VOICE_BYTES and audio[:4] == b"RIFF":
                vname = str(custom.get("name") or data.get("label") or "Voz")[:40]
                vid = voice_settings.new_voice_id(vname)
                os.makedirs(paths.CUSTOM_VOICES_DIR, exist_ok=True)
                with open(os.path.join(paths.CUSTOM_VOICES_DIR, f"{vid}.wav"), "wb") as f:
                    f.write(audio)
                lang = custom.get("language") if custom.get("language") in languages else data["language"]
                voice_settings.add_voice({"id": vid, "name": vname, "audio": f"custom_voices/{vid}.wav",
                                          "ref_text": str(custom.get("ref_text") or "")[:1000], "language": lang,
                                          "fallback_voice": fallback})
                data["voice"] = voice_settings.CUSTOM_PREFIX + vid
                notes.append(("import_voice_added", {"name": vname}))
            else:
                data["voice"] = fallback
                notes.append(("import_voice_fallback", {"voice": fallback}))
        else:
            data["voice"] = fallback
            notes.append(("import_voice_fallback", {"voice": fallback}))

    name = store.save_assistant(None, data, state["version"], languages, owner=owner)
    docs = payload.get("documents") if isinstance(payload.get("documents"), list) else []
    added = 0
    for d in docs[:knowledge.MAX_FILES]:
        if isinstance(d, dict) and str(d.get("text") or "").strip():
            try:
                knowledge.add(name, str(d.get("name") or "documento"), str(d["text"]), fmt=str(d.get("format") or ""))
                added += 1
            except (ValueError, OverflowError):
                break
    if added:
        notes.append(("import_docs", {"n": added}))
    return {"name": name, "notes": notes, "model": data.get("base_model") or ""}
