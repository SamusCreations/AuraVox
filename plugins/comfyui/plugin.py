"""ComfyUI: crear y editar imágenes y hacer videos cortos (opcional).

No agrega dependencias: habla con un ComfyUI que ya esté instalado y
abierto en esta PC (o en la red) por su API HTTP. Si no responde, las
herramientas no aparecen y AuraVox sigue igual.

- Herramientas: generate_image, edit_image (la última imagen del chat o un
  adjunto), generate_video. El modelo escribe el prompt en inglés.
- Flujos: los guardados en ComfyUI (se convierten a formato API), los que
  se dejen en plugins/comfyui/workflows/ y unos de AuraVox armados con los
  modelos instalados. Cada uno se asigna a una tarea (imagen, edición,
  video) y sus entradas se detectan solas (cu_workflows.detect); en
  Ajustes → Plugins → ComfyUI se corrige el mapeo y se elige el modelo.
- Ejecución y VRAM: cu_jobs.py (cola, sondeo, descargar/recargar Ollama).
- La página: tarjeta con progreso y cancelar, la imagen o el video queda
  como archivo del chat (file_store) y el video avisa al terminar.

Rutas propias (app/core/plugins.http): /api/plugin/comfyui/<acción>.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cu_client as C  # noqa: E402
import cu_jobs as J  # noqa: E402
import cu_workflows as W  # noqa: E402

from app import paths  # noqa: E402
from app.core import plugins  # noqa: E402

PID = "comfyui"
DATA_DIR = os.path.join(paths.CONFIG_DIR, "comfyui")
CONF_PATH = os.path.join(DATA_DIR, "config.json")
FOLDER = os.path.join(HERE, "workflows")
TASKS = ("image", "edit", "video")
DEFAULT_URL = "http://127.0.0.1:8188"
IMAGE_EXT = ("png", "jpg", "jpeg", "webp", "bmp", "gif")
_reg = {"at": 0.0, "url": None, "items": [], "error": ""}


# ── Ajustes ────────────────────────────────────────────────────────────

def cfg() -> dict:
    s = plugins.settings(PID)
    url = str(s.get("url") or "").strip().rstrip("/") or DEFAULT_URL
    if not re.match(r"^https?://", url):
        url = "http://" + url
    try:
        wait = max(0, min(3600, int(float(s.get("reload_wait") or 90))))
    except ValueError:
        wait = 90
    return {"url": url, "vram_mode": "coexist" if s.get("vram_mode") == "coexist" else "swap", "reload_wait": wait,
            "release_voice": str(s.get("release_voice") or "").lower() in ("1", "true", "yes", "on")}


def conf() -> dict:
    try:
        with open(CONF_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.setdefault("tasks", {})
    data.setdefault("workflows", {})
    for t in TASKS:
        data["tasks"].setdefault(t, {})
    return data


def save_conf(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONF_PATH + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(CONF_PATH + ".tmp", CONF_PATH)


def _log(text, level="info"):
    try:
        from app.webui import server_log
        server_log.log("comfyui", text, level)
    except Exception:  # noqa: BLE001
        print(f"[comfyui] {text}")


# ── Flujos disponibles ─────────────────────────────────────────────────

def registry(force=False) -> list:
    """Todos los flujos: {id, name, source, graph, detected, missing_nodes,
    missing_models, kind, error}. Se arma con /object_info (cacheado)."""
    c = cfg()
    if not force and _reg["url"] == c["url"] and time.time() - _reg["at"] < 120 and _reg["items"]:
        return _reg["items"]
    info = C.object_info(c["url"], force=force)
    items = []
    for t in W.auto_templates(info, C.models(info)):
        items.append({"id": t["id"], "name": t["name"], "source": "auravox", "graph": t["graph"], "suggested": t["task"]})
    for name in C.user_workflows(c["url"]):
        try:
            items.append({"id": "user:" + name, "name": name[:-5], "source": "comfyui", "ui": C.user_workflow(c["url"], name)})
        except C.ComfyError as e:
            items.append({"id": "user:" + name, "name": name[:-5], "source": "comfyui", "error": str(e)})
    os.makedirs(FOLDER, exist_ok=True)
    for f in sorted(os.listdir(FOLDER)):
        if f.lower().endswith(".json"):
            try:
                with open(os.path.join(FOLDER, f), encoding="utf-8") as fh:
                    items.append({"id": "file:" + f, "name": f[:-5], "source": "folder", "ui": json.load(fh)})
            except (OSError, ValueError) as e:
                items.append({"id": "file:" + f, "name": f[:-5], "source": "folder", "error": str(e)})
    for it in items:
        if it.get("error"):
            continue
        try:
            if "graph" not in it:
                it["graph"], it["missing_nodes"] = W.ui_to_api(it.pop("ui"), info)
            it.setdefault("missing_nodes", [])
            it["detected"] = W.detect(it["graph"])
            it["kind"] = W.kind_of(it["graph"], it["detected"])
            it["missing_models"] = W.missing_files(it["graph"], info, it["detected"])
        except Exception as e:  # noqa: BLE001 — un flujo raro no rompe la lista
            it.pop("ui", None)
            it["error"] = f"{type(e).__name__}: {e}"
    _reg.update(at=time.time(), url=c["url"], items=items, info=info)
    return items


def mapping_of(wf: dict, data: dict = None) -> list:
    data = data or conf()
    saved = (data["workflows"].get(wf["id"]) or {}).get("mapping")
    return saved if isinstance(saved, list) else wf.get("detected") or []


def suggested(wf: dict, data: dict = None):
    """La tarea que se deduce del flujo, si está completo (tiene prompt y no
    le faltan nodos ni modelos)."""
    if wf.get("error") or wf.get("missing_nodes") or wf.get("missing_models"):
        return None
    if "prompt" not in {m["role"] for m in mapping_of(wf, data)}:
        return None
    if wf.get("source") == "auravox":
        return wf.get("suggested")
    return wf.get("kind") if wf.get("kind") in TASKS else None


def task_of(wf: dict, data: dict = None):
    """La tarea del flujo: la que eligió el administrador; sin elegir, solo
    los de AuraVox (los de ComfyUI se sugieren, ver usable)."""
    data = data or conf()
    saved = (data["workflows"].get(wf["id"]) or {}).get("task")
    if saved in TASKS or saved == "none":
        return None if saved == "none" else saved
    return wf.get("suggested") if wf.get("source") == "auravox" and suggested(wf, data) else None


def usable(task: str, data: dict = None) -> list:
    """Flujos para la tarea, el elegido por defecto primero. Si no hay
    ninguno asignado, los de ComfyUI que parecen servir (sugeridos)."""
    data = data or conf()
    try:
        items = registry()
    except C.ComfyError:
        return []
    out = [w for w in items if task_of(w, data) == task]
    if not out:
        out = [w for w in items if suggested(w, data) == task
               and (data["workflows"].get(w["id"]) or {}).get("task") != "none"][:3]
    default = data["tasks"][task].get("workflow")
    # El elegido en "Tareas" vale aunque no se le haya asignado la tarea en la
    # lista de flujos (antes quedaba fuera y se usaba el de AuraVox).
    chosen = next((w for w in items if w["id"] == default and not w.get("error")), None)
    if chosen and chosen not in out:
        out.append(chosen)
    # Primero el elegido; después los que el administrador asignó a mano (sus
    # flujos de ComfyUI, con sus LoRAs) y al final los de AuraVox.
    assigned = lambda w: (data["workflows"].get(w["id"]) or {}).get("task") == task  # noqa: E731
    out.sort(key=lambda w: (w["id"] != default, not assigned(w), w.get("source") == "auravox", w["name"].lower()))
    return out


def connected() -> bool:
    return C.alive(cfg()["url"])


# ── Herramientas ───────────────────────────────────────────────────────

def _images(ctx) -> list:
    files = getattr(ctx, "files", None) or []
    out = [f for f in files if str(f.get("name", "")).rsplit(".", 1)[-1].lower() in IMAGE_EXT]
    return list(dict.fromkeys(f["name"] for f in out))


def tools(ctx):
    if not connected():
        return []
    data = conf()
    names = {t: [w["name"] for w in usable(t, data)] for t in TASKS}
    imgs = _images(ctx)
    out = []
    wf = lambda t: ({"workflow": {"type": "string", "enum": names[t],  # noqa: E731
                                  "description": "Only if the user names one of these ComfyUI workflows; otherwise omit."}}
                    if len(names[t]) > 1 and not data["tasks"][t].get("workflow") else {})
    if names["image"]:
        out.append({"type": "function", "function": {
            "name": "generate_image",
            "description": ("Create a NEW picture (photo, drawing, illustration, logo, wallpaper…) with ComfyUI on this PC "
                            "when the user asks you to draw, create, generate or imagine an image."),
            "parameters": {"type": "object", "properties": {
                "prompt": {"type": "string", "description": "Detailed description IN ENGLISH of the image: subject, style, "
                                                            "setting, lighting, colors, composition."},
                "negative": {"type": "string", "description": "Optional, in English: what must NOT appear."},
                "width": {"type": "integer", "description": "Optional, pixels (e.g. 1024; 768 x 1344 portrait, 1344 x 768 landscape)."},
                "height": {"type": "integer", "description": "Optional, pixels."},
                **wf("image"),
            }, "required": ["prompt"]},
        }})
    if names["edit"] and (imgs or ctx is None):
        out.append({"type": "function", "function": {
            "name": "edit_image",
            "description": ("Change an image of this conversation (one the user attached or one you created) with ComfyUI: "
                            "add or remove things, change colors, style, background, clothes, lighting…"),
            "parameters": {"type": "object", "properties": {
                "instruction": {"type": "string", "description": "What to change, as a short instruction IN ENGLISH "
                                                                 "(e.g. \"make the sky a sunset, keep everything else\")."},
                **({"image": {"type": "string", "enum": imgs, "description": "The image to change. Omit to use the latest one."},
                    "references": {"type": "array", "items": {"type": "string", "enum": imgs}, "maxItems": W.MAX_REFS,
                                   "description": ("Other images of the chat to take something from (a dress, a style, a "
                                                   "face, an object, a background…), when the user asks for it, e.g. "
                                                   "\"put on her the dress from the second photo\". Not the image to change.")}}
                   if imgs else {}),
                **wf("edit"),
            }, "required": ["instruction"]},
        }})
    if names["video"]:
        props = {
            "prompt": {"type": "string", "description": "Detailed description IN ENGLISH of the scene and the motion."},
            "duration": {"type": "number", "description": "Seconds, optional (default from settings, 2-5 is usual)."},
            **wf("video"),
        }
        if imgs:
            props["image"] = {"type": "string", "enum": imgs, "description": "Optional: an image of the chat to animate."}
        out.append({"type": "function", "function": {
            "name": "generate_video",
            "description": "Make a short video clip with ComfyUI on this PC (it takes minutes; it runs in the background).",
            "parameters": {"type": "object", "properties": props, "required": ["prompt"]},
        }})
    return out


def context(ctx):
    if not connected():
        return ""
    J.on_chat()
    jobs = J.active(getattr(ctx, "owner", None) or "*") if ctx is not None else []
    busy = (f" Right now {len(jobs)} of the user's requests are being created ({', '.join(j['kind'] for j in jobs)}): "
            "they appear in the chat by themselves when ready." if jobs else "")
    imgs = _images(ctx)
    lib_note = (f" Available images in this chat and the user's profile library: {', '.join(imgs[-10:])}." if imgs else "")
    return ("IMAGES AND VIDEOS (ComfyUI on this PC): when the user asks you to draw, create or imagine a picture, call "
            "generate_image right away; to change an image of the chat or from another chat in their profile, edit_image; "
            "for a short clip, generate_video. "
            "Write the prompt in English with concrete details even if the user speaks another language, and keep "
            "what they asked for. The result shows up in the chat by itself, with progress: never say it's ready "
            "before that and never write links or file paths." + lib_note + busy)


def _pick_workflow(task, wanted=None, need_image=False):
    items = usable(task)
    if wanted:
        hit = [w for w in items if w["name"].lower() == str(wanted).lower()]
        items = hit + [w for w in items if w not in hit]
    if need_image is not None and task == "video":
        with_img = [w for w in items if any(m["role"] == "image" for m in mapping_of(w))]
        without = [w for w in items if w not in with_img]
        items = (with_img + without) if need_image else (without + with_img)
    return items[0] if items else None


def _file_of(ctx, name, exact=False):
    files = getattr(ctx, "files", None) or []
    imgs = [f for f in files if str(f.get("name", "")).rsplit(".", 1)[-1].lower() in IMAGE_EXT]
    if name:
        q = str(name).strip().lower()
        hit = (
            [f for f in imgs if f["name"] == name]
            or [f for f in imgs if f["name"].lower() == q]
            or [f for f in imgs if q in f["name"].lower() or q in str(f.get("info") or "").lower()]
        )
        if hit:
            return hit[-1]
        if exact:
            return None
    return imgs[-1] if imgs else None


def call(name, args, ctx):
    if name not in ("generate_image", "edit_image", "generate_video"):
        return None
    if not connected():
        return "ComfyUI isn't running on this PC right now: tell the user to open it and try again."
    task = {"generate_image": "image", "edit_image": "edit", "generate_video": "video"}[name]
    data = conf()
    tcfg = data["tasks"][task]
    src = None
    if task == "edit" or (task == "video" and args.get("image")):
        src = _file_of(ctx, args.get("image"))
        if task == "edit" and not src:
            return "There's no image in this conversation to edit: ask the user to attach it."
    # Con un flujo elegido en Ajustes para la tarea, manda ese: el modelo
    # elegía otro de la lista por su cuenta (pasó con "Klein I2I").
    wanted = None if tcfg.get("workflow") else args.get("workflow")
    wf = _pick_workflow(task, wanted, need_image=bool(src) if task == "video" else None)
    if not wf:
        return f"There's no ComfyUI workflow set up for this ({task}). Tell the user an administrator can choose one in Settings → Plugins → ComfyUI."
    prompt = str(args.get("instruction") if task == "edit" else args.get("prompt") or "").strip()
    if not prompt:
        return "Say what to create (the prompt is empty)."
    params = {"prompt": prompt[:4000], "task": task}
    if args.get("negative"):
        params["negative"] = str(args["negative"])[:2000]
    for k in ("width", "height"):
        v = args.get(k) or tcfg.get(k)
        if v:
            try:
                params[k] = max(256, min(2048, int(v)))
            except (TypeError, ValueError):
                pass
    for k in ("steps", "cfg"):
        if tcfg.get(k):
            params[k] = tcfg[k]
    if tcfg.get("model"):
        params["model"] = tcfg["model"]
    if task == "video":
        try:
            params["duration"] = max(1.0, min(15.0, float(args.get("duration") or tcfg.get("duration") or 3)))
        except (TypeError, ValueError):
            params["duration"] = 3.0
        if tcfg.get("fps"):
            params["fps"] = tcfg["fps"]
    if src:
        params["src"] = {"id": src["id"], "name": src["name"]}
    note = ""
    if task == "edit":
        refs = []
        wanted_refs = args.get("references") if isinstance(args.get("references"), list) else []
        for r in wanted_refs[:W.MAX_REFS]:
            f = _file_of(ctx, r, exact=True)
            if f and f["id"] != (src or {}).get("id") and f["id"] not in [x["id"] for x in refs]:
                refs.append({"id": f["id"], "name": f["name"]})
        if refs:
            cap = W.ref_capacity(wf["graph"], mapping_of(wf))
            if cap < len(refs):
                note = "refs_ignored" if cap == 0 else "refs_some"
            refs = refs[:cap]
            if refs:
                params["refs"] = refs
    owner = getattr(ctx, "owner", None) or "*"
    c = cfg()
    job = J.create(owner, task, wf["id"], prompt, params, auto_go=J.GO_WAIT if ctx is not None else 3)
    job["wf_name"] = wf["name"]
    job["size"] = _target_size(wf, params, src)
    job["note"] = note
    if ctx is not None:
        ctx.emit({"type": "job", "plugin": PID, "job": J.public(job), "src": params.get("src"),
                  "hold": c["vram_mode"] == "swap"})
    secs = job["eta"] + (12 if c["vram_mode"] == "swap" and not J.VRAM["hot"] else 0)
    when = f"about {round(secs / 60)} minutes" if secs >= 120 else f"about {int(round(secs / 5) * 5) or 5} seconds"
    imgs = (f" on «{src['name']}»" if src else "") + (
        f" with reference(s) {', '.join('«' + r['name'] + '»' for r in params['refs'])}" if params.get("refs") else "")
    _log(f"{task} requested with «{wf['name']}»{imgs} (~{secs:.0f}s): «{prompt[:90]}»"
         + (f" — chat files: {[f['name'] for f in getattr(ctx, 'files', None) or []]}" if task == "edit" else ""))
    what = {"image": "the image", "edit": "the edited image", "video": "the video"}[task]
    extra = (" It runs in the background: they can keep chatting and will get a notification." if task == "video" else "")
    if note:
        extra += (f" This workflow ({wf['name']}) can't use reference images"
                  + (" (only some were used)" if note == "refs_some" else "")
                  + ": tell the user briefly, the result may not take the reference into account.")
    elif params.get("refs"):
        extra += f" Using {len(params['refs'])} reference image(s)."
    return (f"Started: {what} is being created with ComfyUI ({when}). The user already sees a card with the progress "
            f"and a cancel button, and {what} will appear there by itself.{extra} Now tell them in ONE short sentence "
            f"that you're on it and it takes {when}. Don't describe the prompt, don't say it's ready, no links.")


def _image_size(path):
    """(ancho, alto) de un PNG, JPEG, GIF o WEBP leyendo su cabecera."""
    import struct

    try:
        with open(path, "rb") as f:
            head = f.read(64)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return struct.unpack(">II", head[16:24])
            if head[:6] in (b"GIF87a", b"GIF89a"):
                return struct.unpack("<HH", head[6:10])
            if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
                kind = head[12:16]
                if kind == b"VP8X":
                    return (int.from_bytes(head[24:27], "little") + 1, int.from_bytes(head[27:30], "little") + 1)
                if kind == b"VP8 ":
                    w, h = struct.unpack("<HH", head[26:30])
                    return w & 0x3FFF, h & 0x3FFF
                if kind == b"VP8L":
                    b = int.from_bytes(head[21:25], "little")
                    return (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
            if head[:2] == b"\xff\xd8":
                f.seek(2)
                while True:
                    m = f.read(2)
                    if len(m) < 2 or m[0] != 0xFF:
                        return None
                    if m[1] in (0xD8, 0x01) or 0xD0 <= m[1] <= 0xD7:
                        continue
                    n = struct.unpack(">H", f.read(2))[0]
                    if 0xC0 <= m[1] <= 0xCF and m[1] not in (0xC4, 0xC8, 0xCC):
                        h, w = struct.unpack(">xHH", f.read(5))
                        return w, h
                    f.seek(n - 2, 1)
    except (OSError, struct.error):
        return None
    return None


def _target_size(wf, params, src):
    """El tamaño aproximado de lo que se va a crear, para el lienzo animado
    de la tarjeta: el pedido, el de la imagen de origen o el del flujo."""
    if params.get("width") and params.get("height"):
        return [int(params["width"]), int(params["height"])]
    if src:
        from app.webui import file_store

        found = file_store.open_file(src["id"])
        size = _image_size(found[0]) if found else None
        if size and size[0] and size[1]:
            return [int(size[0]), int(size[1])]
    vals = {}
    for m in mapping_of(wf):
        if m["role"] in ("width", "height") and m["role"] not in vals:
            v = wf["graph"].get(m["node"], {}).get("inputs", {}).get(m["input"])
            if isinstance(v, int) and v > 0:
                vals[m["role"]] = v
    if "width" in vals and "height" in vals:
        return [vals["width"], vals["height"]]
    return [832, 480] if params.get("task") == "video" else [1024, 1024]


# ── Lo que hace ComfyUI con cada trabajo (ver cu_jobs) ─────────────────

def _prepare(job) -> dict:
    wf = next((w for w in registry() if w["id"] == job["workflow"]), None)
    if not wf or wf.get("error"):
        raise C.ComfyError(f"el flujo {job['workflow']} ya no está")
    c = cfg()
    params = dict(job["params"])
    src = params.pop("src", None)
    if src:
        from app.webui import file_store

        found = file_store.open_file(src["id"])
        if not found:
            raise C.ComfyError("la imagen de origen ya no está")
        with open(found[0], "rb") as f:
            params["image"] = C.upload_image(c["url"], f"{job['id']}_{os.path.basename(found[0])}", f.read())
    refs = []
    for k, ref in enumerate(params.pop("refs", None) or []):
        from app.webui import file_store

        found = file_store.open_file(ref["id"])
        if not found:
            raise C.ComfyError("una imagen de referencia ya no está")
        with open(found[0], "rb") as f:
            refs.append(C.upload_image(c["url"], f"{job['id']}_ref{k}_{os.path.basename(found[0])}", f.read()))
    mapping = mapping_of(wf)
    if refs:
        g = W.apply(wf["graph"], mapping, params, _reg.get("info"))
        W.add_references(g, mapping, refs)
        return g
    if params.get("task") == "video" and wf.get("kind") != "video":
        params["video"] = True
    elif params.get("task") == "video":
        params["video"] = any(n.get("class_type") == "SaveImage" for n in wf["graph"].values())
    return W.apply(wf["graph"], mapping, params, _reg.get("info"))


def _finish(job, name, data, kind) -> dict:
    from app.webui import file_store

    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ("mp4" if kind == "video" else "png")
    label = {"image": "imagen", "edit": "edicion", "video": "video"}.get(job["kind"], "comfyui")
    nice = f"{label}_{time.strftime('%Y%m%d_%H%M%S')}.{ext}"
    saved = file_store.save(nice, data)
    return {"url": saved["url"], "name": nice, "size": len(data), "kind": kind}


def _notify(job):
    try:
        from app.webui import notify
    except Exception:  # noqa: BLE001
        return
    notify.push(job["owner"] if job["owner"] != "*" else "*", "comfyui", job=J.public(job))


J.HOOKS.update(cfg=cfg, prepare=_prepare, finish=_finish, notify=_notify, log=_log, dir=DATA_DIR)


# ── Probar conexión ────────────────────────────────────────────────────

def check(settings):
    from app.webui.i18n import tr

    url = str(settings.get("url") or "").strip().rstrip("/") or DEFAULT_URL
    if not re.match(r"^https?://", url):
        url = "http://" + url
    st = C.stats(url, timeout=4)
    if not st:
        return False, tr("comfy_off", url=url)
    dev = (st.get("devices") or [{}])[0]
    vram = f"{dev.get('vram_free', 0) / 1024 ** 3:.1f}/{dev.get('vram_total', 0) / 1024 ** 3:.1f} GB" if dev.get("vram_total") else "?"
    _reg["at"] = 0
    try:
        items = registry(force=True)
        n = {t: len(usable(t)) for t in TASKS}
    except C.ComfyError as e:
        return False, str(e)
    gpu = re.sub(r"^cuda:\d+\s*|\s*:.*$", "", str(dev.get("name") or "GPU"))
    return True, tr("comfy_on", ver=(st.get("system") or {}).get("comfyui_version", "?"), gpu=gpu,
                    vram=vram, n=len(items), **n)


# ── Rutas propias: /api/plugin/comfyui/<acción> ────────────────────────

def _wf_public(w, data, info):
    mapping = mapping_of(w, data)
    return {
        "id": w["id"], "name": w["name"], "source": w.get("source"), "kind": w.get("kind"), "error": w.get("error", ""),
        "missing_nodes": w.get("missing_nodes", []), "missing_models": w.get("missing_models", []),
        "task": task_of(w, data), "suggested": suggested(w, data), "task_saved": (data["workflows"].get(w["id"]) or {}).get("task") or "",
        "mapping": mapping, "detected": w.get("detected", []), "custom_mapping": isinstance(
            (data["workflows"].get(w["id"]) or {}).get("mapping"), list),
        "fields": W.fields(w["graph"], info) if w.get("graph") else [],
        "models": W.model_options(w["graph"], info, mapping) if w.get("graph") else [],
        "eta": J.eta(w["id"], w.get("kind") or "image"),
    }


def _admin_state(force=False):
    c = cfg()
    st = C.stats(c["url"], timeout=3)
    out = {"connected": bool(st), "url": c["url"], "settings": c, "vram": J.vram_state(), "tasks": conf()["tasks"],
           "folder": FOLDER, "stats": st and {"version": (st.get("system") or {}).get("comfyui_version"),
                                             "devices": st.get("devices") or []}}
    if not st:
        return out
    try:
        items = registry(force=force)
    except C.ComfyError as e:
        out["error"] = str(e)
        return out
    data = conf()
    info = _reg.get("info") or {}
    out["workflows"] = [_wf_public(w, data, info) for w in items]
    out["models"] = C.models(info)
    out["usable"] = {t: [w["id"] for w in usable(t, data)] for t in TASKS}
    return out


def http(method, action, data, ctx):
    owner = getattr(ctx, "owner", None) or "*"
    admin = getattr(ctx, "role", "") == "admin"
    if action == "jobs":
        ids = [str(x) for x in (data.get("ids") or [])][:50]
        return {"jobs": J.get(ids, owner, admin), "hold": cfg()["vram_mode"] == "swap"}
    if action == "active":
        return {"jobs": J.active(owner), "hold": cfg()["vram_mode"] == "swap"}
    if action == "regen" and method == "POST":
        # Otra versión del mismo pedido (otra semilla), con el mismo flujo.
        with J._cond:
            old = J.JOBS.get(str(data.get("id") or ""))
        if not old or (old["owner"] != owner and not admin):
            return 404, {"error": "not_found"}
        if not connected():
            return 409, {"error": "ComfyUI"}
        params = {k: v for k, v in old["params"].items() if k != "seed"}
        job = J.create(owner, old["kind"], old["workflow"], old["label"], params, auto_go=0)
        job["wf_name"] = old.get("wf_name")
        job["size"] = old.get("size")
        _log(f"{old['kind']}: new variation of «{old['label'][:80]}»")
        return {"job": J.public(job), "hold": cfg()["vram_mode"] == "swap"}
    if action == "go" and method == "POST":
        return {"started": J.go([str(x) for x in (data.get("ids") or [])][:50], owner)}
    if action == "cancel" and method == "POST":
        return {"ok": J.cancel(str(data.get("id") or ""), owner, admin)}
    if not admin:
        return 403, {"error": "admin"}
    if action == "admin":
        return _admin_state(force=bool(data.get("refresh")))
    if action == "tasks" and method == "POST":
        conf_ = conf()
        for t in TASKS:
            v = (data.get("tasks") or {}).get(t)
            if not isinstance(v, dict):
                continue
            clean = {}
            if isinstance(v.get("workflow"), str):
                clean["workflow"] = v["workflow"][:300]
            if isinstance(v.get("model"), str):
                clean["model"] = v["model"][:300]
            for k, lo, hi in (("width", 0, 4096), ("height", 0, 4096), ("steps", 0, 200), ("duration", 0, 30), ("fps", 0, 60)):
                try:
                    n = float(v.get(k) or 0)
                    if lo <= n <= hi and n:
                        clean[k] = int(n) if k != "duration" else n
                except (TypeError, ValueError):
                    pass
            conf_["tasks"][t] = clean
        save_conf(conf_)
        return _admin_state()
    if action == "workflow" and method == "POST":
        wid = str(data.get("id") or "")
        conf_ = conf()
        w = dict(conf_["workflows"].get(wid) or {})
        if "task" in data:
            task = data.get("task")
            if task in TASKS or task == "none":
                w["task"] = task
            else:
                w.pop("task", None)
        if "mapping" in data:
            m = data.get("mapping")
            if isinstance(m, list):
                w["mapping"] = [{"role": str(x["role"]), "node": str(x["node"]), "input": str(x["input"])}
                                for x in m if isinstance(x, dict) and x.get("role") in W.ROLES and x.get("node") and x.get("input")][:60]
            else:
                w.pop("mapping", None)
        conf_["workflows"][wid] = w
        save_conf(conf_)
        return _admin_state()
    if action == "import" and method == "POST":
        name = re.sub(r"[^\w .()+-]", "_", str(data.get("name") or "flujo"))[:80].strip() or "flujo"
        if not name.lower().endswith(".json"):
            name += ".json"
        wf = data.get("workflow")
        if not isinstance(wf, dict) or not (W.is_api_format(wf) or isinstance(wf.get("nodes"), list)):
            return 400, {"error": "workflow"}
        os.makedirs(FOLDER, exist_ok=True)
        with open(os.path.join(FOLDER, name), "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=1)
        _reg["at"] = 0
        return _admin_state()
    if action == "delete" and method == "POST":
        wid = str(data.get("id") or "")
        if wid.startswith("file:"):
            p = os.path.join(FOLDER, os.path.basename(wid[5:]))
            if os.path.isfile(p):
                os.remove(p)
            _reg["at"] = 0
        return _admin_state()
    return 404, {"error": "not_found"}
