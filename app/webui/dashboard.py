"""Datos del panel principal (Dashboard) y bibliotecas de medios y archivos.

Reúne estadísticas reales de uso por perfil (conversaciones, mensajes,
palabras, actividad por asistente, tiempos de GPU en ComfyUI, memoria,
recordatorios, listas, rutinas y documentos) y construye los catálogos de:
  - Imágenes y videos generados (`media`)
  - Archivos generados, convertidos y procesados en chats (`files`)
"""
import json
import os
import re

from app import paths
from app.core import attachments, voice_settings
from app.skills import knowledge, lists, memory, reminders, routines
from app.webui import chat_store, file_store

_FILE_ID_RE = re.compile(r"/api/files/([0-9a-f]{24}(?:\.[a-z0-9]{1,8})?)")
_WORD_RE = re.compile(r"\S+")

IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "avif"}
VIDEO_EXTS = {"mp4", "webm", "mov", "mkv", "avi"}
AUDIO_EXTS = {"mp3", "wav", "ogg", "m4a", "flac", "aac", "opus", "wma"}
PDF_EXTS = {"pdf"}
DOC_EXTS = {"docx", "docm", "doc", "odt", "rtf", "epub"}
SHEET_EXTS = {"xlsx", "xlsm", "xls", "ods", "csv", "tsv"}
SLIDE_EXTS = {"pptx", "pptm", "ppt", "odp"}
CODE_EXTS = {
    "py", "js", "mjs", "ts", "tsx", "jsx", "html", "htm", "css", "scss",
    "json", "jsonl", "yaml", "yml", "toml", "ini", "xml", "sql", "sh",
    "bat", "ps1", "c", "cpp", "h", "cs", "go", "rs", "java", "kt", "php",
}


def _ext(name: str) -> str:
    if not name or "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower().strip()


def _classify_ext(ext: str) -> str:
    ext = (ext or "").lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in DOC_EXTS:
        return "doc"
    if ext in SHEET_EXTS:
        return "sheet"
    if ext in SLIDE_EXTS:
        return "slide"
    if ext in CODE_EXTS:
        return "code"
    if ext in attachments.TEXT_EXTENSIONS:
        return "text"
    return "other"


def _file_meta(file_id: str) -> dict | None:
    """Lee nombre, tamaño y fecha de config/chats/files/<file_id>(.json)."""
    if not file_store.ID_RE.match(file_id or ""):
        return None
    raw_path = os.path.join(file_store.FILES_DIR, file_id)
    if not os.path.isfile(raw_path):
        return None
    meta = {}
    meta_path = raw_path + ".json"
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f) or {}
        except (OSError, ValueError):
            meta = {}
    try:
        st = os.stat(raw_path)
        size = int(meta.get("size") or st.st_size)
        at = float(meta.get("at") or st.st_mtime)
    except OSError:
        return None
    name = str(meta.get("name") or file_id)[:200]
    ext = _ext(name) or _ext(file_id)
    return {
        "id": file_id,
        "url": f"/api/files/{file_id}",
        "name": name,
        "ext": ext,
        "size": size,
        "at": at,
    }


def _extract_file_id(url: str) -> str | None:
    m = _FILE_ID_RE.search(str(url or ""))
    return m.group(1) if m else None


def _count_words(text: str) -> int:
    if not text:
        return 0
    return len(_WORD_RE.findall(str(text)))


def _load_comfy_jobs() -> list[dict]:
    jobs_path = os.path.join(paths.CONFIG_DIR, "comfyui", "jobs.json")
    if not os.path.isfile(jobs_path):
        return []
    try:
        with open(jobs_path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def build_dashboard(owner: str, is_guest: bool, visible_assistants: list[dict]) -> dict:
    """Construye los datos completos del dashboard, galería multimedia y archivos."""
    asst_map = {}
    for a in visible_assistants:
        name = a.get("name") or ""
        if not name:
            continue
        asst_map[name] = {
            "name": name,
            "label": a.get("label") or name.upper(),
            "model": a.get("base_model") or "",
            "voice": a.get("voice") or "F1",
            "color": a.get("color") or "",
            "shared": bool(a.get("shared", True)),
            "messages": 0,
            "user_turns": 0,
            "assistant_turns": 0,
            "words": 0,
            "media_count": 0,
            "files_count": 0,
            "docs_count": 0,
            "updated_at": 0.0,
        }

    total_messages = 0
    user_messages = 0
    assistant_messages = 0
    user_words = 0
    assistant_words = 0
    active_chats = 0
    group_chats = 0
    tool_events = 0
    last_activity = 0.0

    # Catálogos indexados por file_id para evitar duplicados
    media_by_id: dict[str, dict] = {}
    files_by_id: dict[str, dict] = {}
    # Mapeo job_id -> nombre del asistente donde se originó
    job_assistant: dict[str, str] = {}

    if not is_guest:
        for name, info in asst_map.items():
            chat = chat_store.load(name, owner)
            msgs = chat.get("messages") or []
            updated = float(chat.get("updated_at") or 0.0)
            if updated > last_activity:
                last_activity = updated
            info["updated_at"] = updated
            if msgs:
                active_chats += 1
            if chat.get("guests"):
                group_chats += 1

            for m in msgs:
                if not isinstance(m, dict):
                    continue
                role = m.get("role")
                text = str(m.get("text") or "")
                words = _count_words(text)

                if role == "user":
                    total_messages += 1
                    user_messages += 1
                    user_words += words
                    info["messages"] += 1
                    info["user_turns"] += 1
                    info["words"] += words
                    for att in m.get("files") or []:
                        if not isinstance(att, dict):
                            continue
                        fid = _extract_file_id(att.get("url") or "")
                        if not fid:
                            continue
                        fmeta = _file_meta(fid)
                        if not fmeta:
                            continue
                        info["files_count"] += 1
                        fkind = _classify_ext(fmeta["ext"])
                        files_by_id[fid] = {
                            **fmeta,
                            "name": str(att.get("name") or fmeta["name"])[:200],
                            "kind": fkind,
                            "origin": "attachment",
                            "assistant": name,
                            "assistant_label": info["label"],
                            "info": str(att.get("info") or "")[:120],
                            "preview_text": str(att.get("text") or "")[:4000],
                        }

                elif role == "assistant":
                    total_messages += 1
                    assistant_messages += 1
                    assistant_words += words
                    speaker = m.get("speaker")
                    target = asst_map.get(speaker) if (speaker and speaker != "@host" and speaker in asst_map) else info
                    target["messages"] += 1
                    target["assistant_turns"] += 1
                    target["words"] += words

                elif role == "event":
                    tool_events += 1

                elif role == "file":
                    fdata = m.get("data") if isinstance(m.get("data"), dict) else {}
                    fid = _extract_file_id(fdata.get("url") or "")
                    if not fid:
                        continue
                    fmeta = _file_meta(fid)
                    if not fmeta:
                        continue
                    info["files_count"] += 1
                    fkind = _classify_ext(fmeta["ext"])
                    files_by_id[fid] = {
                        **fmeta,
                        "name": str(fdata.get("name") or fmeta["name"])[:200],
                        "kind": fkind,
                        "origin": "converted",
                        "from_name": str(fdata.get("from") or "")[:200],
                        "assistant": name,
                        "assistant_label": info["label"],
                        "info": "",
                        "preview_text": "",
                    }

                elif role == "job":
                    jdata = m.get("data") if isinstance(m.get("data"), dict) else {}
                    speaker = jdata.get("speaker")
                    asst_key = speaker if (speaker and speaker != "@host" and speaker in asst_map) else name
                    asst_label = asst_map[asst_key]["label"] if asst_key in asst_map else name.upper()
                    iters = jdata.get("iters") if isinstance(jdata.get("iters"), list) else [jdata]
                    for it in iters:
                        if not isinstance(it, dict):
                            continue
                        jid = str(it.get("id") or "")
                        if jid:
                            job_assistant[jid] = asst_key
                        res = it.get("result") if isinstance(it.get("result"), dict) else {}
                        fid = _extract_file_id(res.get("url") or "")
                        if not fid:
                            continue
                        fmeta = _file_meta(fid)
                        if not fmeta:
                            continue
                        if asst_key in asst_map:
                            asst_map[asst_key]["media_count"] += 1
                        jkind = str(it.get("kind") or jdata.get("kind") or res.get("kind") or "image")
                        is_vid = jkind == "video" or res.get("kind") == "video" or fmeta["ext"] in VIDEO_EXTS
                        media_item = {
                            **fmeta,
                            "name": str(res.get("name") or fmeta["name"])[:200],
                            "kind": "video" if is_vid else (jkind if jkind in ("image", "edit", "video") else "image"),
                            "media_type": "video" if is_vid else "image",
                            "prompt": str(it.get("label") or jdata.get("label") or "")[:500],
                            "workflow": str(it.get("wf_name") or it.get("workflow") or jdata.get("wf_name") or "")[:120],
                            "dimensions": it.get("size") if isinstance(it.get("size"), list) else None,
                            "took": round(float(it["took"]), 1) if isinstance(it.get("took"), (int, float)) else None,
                            "assistant": asst_key,
                            "assistant_label": asst_label,
                            "job_id": jid,
                        }
                        media_by_id[fid] = media_item
                        # También disponible en la biblioteca general de archivos generados
                        files_by_id.setdefault(fid, {
                            **fmeta,
                            "name": media_item["name"],
                            "kind": "video" if is_vid else "image",
                            "origin": "generated",
                            "from_name": media_item["workflow"],
                            "assistant": asst_key,
                            "assistant_label": asst_label,
                            "info": media_item["prompt"][:120],
                            "preview_text": "",
                        })

            # También revisar history por archivos convertidos que pudieran no tener mensaje role="file"
            for h in chat.get("history") or []:
                if not isinstance(h, dict) or h.get("role") != "assistant":
                    continue
                for hf in h.get("files") or []:
                    if not isinstance(hf, dict):
                        continue
                    fid = _extract_file_id(hf.get("url") or "")
                    if not fid or fid in files_by_id:
                        continue
                    fmeta = _file_meta(fid)
                    if not fmeta:
                        continue
                    info["files_count"] += 1
                    files_by_id[fid] = {
                        **fmeta,
                        "name": str(hf.get("name") or fmeta["name"])[:200],
                        "kind": _classify_ext(fmeta["ext"]),
                        "origin": "converted",
                        "from_name": str(hf.get("from") or "")[:200],
                        "assistant": name,
                        "assistant_label": info["label"],
                        "info": "",
                        "preview_text": "",
                    }

    # Procesar jobs.json de ComfyUI (incluye trabajos cuyos chats se reiniciaron o regeneraciones)
    all_jobs = _load_comfy_jobs()
    user_jobs = [
        j for j in all_jobs
        if isinstance(j, dict) and (j.get("owner") == owner or (not is_guest and not j.get("owner")))
    ]
    done_jobs = [j for j in user_jobs if j.get("status") == "done"]
    total_gpu_seconds = 0.0
    for j in done_jobs:
        took = j.get("took")
        if isinstance(took, (int, float)) and took > 0:
            total_gpu_seconds += float(took)
        res = j.get("result") if isinstance(j.get("result"), dict) else {}
        fid = _extract_file_id(res.get("url") or "")
        if not fid:
            continue
        fmeta = _file_meta(fid)
        if not fmeta:
            continue
        jid = str(j.get("id") or "")
        asst_key = job_assistant.get(jid, "")
        asst_label = asst_map[asst_key]["label"] if asst_key in asst_map else ""
        jkind = str(j.get("kind") or res.get("kind") or "image")
        is_vid = jkind == "video" or res.get("kind") == "video" or fmeta["ext"] in VIDEO_EXTS
        existing = media_by_id.get(fid)
        at_ts = float(j.get("finished") or j.get("created") or fmeta["at"])
        item = {
            **fmeta,
            "at": fmeta["at"] or at_ts,
            "name": str(res.get("name") or (existing and existing.get("name")) or fmeta["name"])[:200],
            "kind": "video" if is_vid else (jkind if jkind in ("image", "edit", "video") else "image"),
            "media_type": "video" if is_vid else "image",
            "prompt": str(j.get("label") or (existing and existing.get("prompt")) or "")[:500],
            "workflow": str(j.get("wf_name") or j.get("workflow") or (existing and existing.get("workflow")) or "")[:120],
            "dimensions": j.get("size") if isinstance(j.get("size"), list) else (existing and existing.get("dimensions")),
            "took": round(float(took), 1) if isinstance(took, (int, float)) else (existing and existing.get("took")),
            "assistant": asst_key or (existing and existing.get("assistant")) or "",
            "assistant_label": asst_label or (existing and existing.get("assistant_label")) or "",
            "job_id": jid,
        }
        media_by_id[fid] = item
        files_by_id.setdefault(fid, {
            **fmeta,
            "at": item["at"],
            "name": item["name"],
            "kind": "video" if is_vid else "image",
            "origin": "generated",
            "from_name": item["workflow"],
            "assistant": item["assistant"],
            "assistant_label": item["assistant_label"],
            "info": item["prompt"][:120],
            "preview_text": "",
        })

    # Ordenar medios y archivos del más reciente al más antiguo por defecto
    media_list = sorted(media_by_id.values(), key=lambda x: x.get("at") or 0.0, reverse=True)
    files_list = sorted(files_by_id.values(), key=lambda x: x.get("at") or 0.0, reverse=True)

    images_count = sum(1 for m in media_list if m["kind"] == "image")
    edits_count = sum(1 for m in media_list if m["kind"] == "edit")
    videos_count = sum(1 for m in media_list if m["kind"] == "video" or m["media_type"] == "video")
    media_bytes = sum(int(m.get("size") or 0) for m in media_list)

    converted_count = sum(1 for f in files_list if f.get("origin") == "converted")
    generated_files_count = sum(1 for f in files_list if f.get("origin") in ("converted", "generated"))
    attachment_files_count = sum(1 for f in files_list if f.get("origin") == "attachment")
    files_bytes = sum(int(f.get("size") or 0) for f in files_list)

    # Productividad y conocimiento
    docs_total = 0
    docs_chunks = 0
    for name, info in asst_map.items():
        try:
            dlist = knowledge.list_docs(name)
        except Exception:
            dlist = []
        info["docs_count"] = len(dlist)
        docs_total += len(dlist)
        docs_chunks += sum(int(d.get("chunks") or 0) for d in dlist)

    if is_guest:
        mem_count = 0
        rem_pending = 0
        rem_done = 0
        lists_count = 0
        items_pending = 0
        items_done = 0
        routines_count = 0
    else:
        try:
            mem_count = len(memory.list_facts(owner))
        except Exception:
            mem_count = 0
        try:
            rem_data = reminders.list_all(owner=owner)
            rem_pending = len(rem_data.get("pending") or [])
            rem_done = len(rem_data.get("done") or [])
        except Exception:
            rem_pending = rem_done = 0
        try:
            user_lists = lists.list_all(owner)
            lists_count = len(user_lists)
            items_pending = sum(
                sum(1 for it in (lst.get("items") or []) if not it.get("done"))
                for lst in user_lists
            )
            items_done = sum(
                sum(1 for it in (lst.get("items") or []) if it.get("done"))
                for lst in user_lists
            )
        except Exception:
            lists_count = items_pending = items_done = 0
        try:
            routines_count = len(routines.list_all(owner))
        except Exception:
            routines_count = 0

    try:
        cloned_voices = len(voice_settings.load().get("custom_voices") or [])
    except Exception:
        cloned_voices = 0

    by_assistant = sorted(
        asst_map.values(),
        key=lambda a: (a["messages"], a["media_count"], a["updated_at"]),
        reverse=True,
    )

    return {
        "chat_stats": {
            "total_messages": total_messages,
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
            "total_words": user_words + assistant_words,
            "user_words": user_words,
            "assistant_words": assistant_words,
            "active_chats": active_chats,
            "total_assistants": len(asst_map),
            "group_chats": group_chats,
            "tool_events": tool_events,
            "last_activity": last_activity,
        },
        "media_stats": {
            "total": len(media_list),
            "images": images_count,
            "edits": edits_count,
            "videos": videos_count,
            "total_jobs": len(done_jobs),
            "total_gpu_seconds": round(total_gpu_seconds, 1),
            "avg_gpu_seconds": round(total_gpu_seconds / len(done_jobs), 1) if done_jobs else 0.0,
            "total_bytes": media_bytes,
        },
        "file_stats": {
            "total": len(files_list),
            "generated_count": generated_files_count,
            "converted_count": converted_count,
            "attachment_count": attachment_files_count,
            "total_bytes": files_bytes,
        },
        "skills_stats": {
            "memory_count": mem_count,
            "reminders_pending": rem_pending,
            "reminders_done": rem_done,
            "lists_count": lists_count,
            "list_items_pending": items_pending,
            "list_items_done": items_done,
            "routines_count": routines_count,
            "docs_count": docs_total,
            "docs_chunks": docs_chunks,
            "cloned_voices_count": cloned_voices,
        },
        "by_assistant": by_assistant,
        "media": media_list,
        "files": files_list,
    }


def list_profile_files(owner: str, is_guest: bool, visible_assistants: list[dict] | None = None, limit: int = 60) -> list[dict]:
    """Devuelve los archivos y medios generados o subidos en cualquier chat del mismo perfil,
    ordenados del más antiguo al más reciente para que herramientas como edit_image,
    generate_video y convert_file puedan referenciarlos desde cualquier conversación."""
    if is_guest:
        return []
    try:
        dash = build_dashboard(owner, is_guest, visible_assistants or [])
        files_desc = dash.get("files") or []
    except Exception:
        return []
    recent = files_desc[:limit]
    recent.reverse()  # más reciente al final
    return [
        {
            "id": f["id"],
            "name": f["name"],
            "url": f["url"],
            "kind": f.get("kind") or "other",
            "origin": f.get("origin") or "",
            "assistant": f.get("assistant") or "",
            "assistant_label": f.get("assistant_label") or "",
            "info": f.get("info") or "",
        }
        for f in recent
        if f.get("id") and f.get("name")
    ]


def preview_file(file_id: str) -> dict | None:
    """Extrae una vista previa legible de un archivo guardado en file_store."""
    fmeta = _file_meta(file_id)
    if not fmeta:
        return None
    raw_path = os.path.join(file_store.FILES_DIR, file_id)
    ext = fmeta["ext"]
    kind = _classify_ext(ext)
    if kind in ("image", "video", "audio", "pdf"):
        return {**fmeta, "kind": kind, "text": "", "truncated": False}
    try:
        with open(raw_path, "rb") as f:
            raw = f.read(attachments.MAX_BYTES + 1)
        info = attachments.extract_text(fmeta["name"], raw)
        return {
            **fmeta,
            "kind": kind,
            "format": info.get("format") or ext.upper(),
            "text": info.get("text") or "",
            "chars": info.get("chars") or 0,
            "truncated": bool(info.get("truncated")),
        }
    except Exception as exc:
        return {
            **fmeta,
            "kind": kind,
            "format": ext.upper(),
            "text": "",
            "error": str(exc),
            "truncated": False,
        }
