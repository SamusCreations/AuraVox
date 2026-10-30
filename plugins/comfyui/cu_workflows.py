"""Flujos de ComfyUI: convertir, detectar sus entradas y rellenarlas.

Tres fuentes:
- Los guardados en ComfyUI (user/default/workflows), que están en formato
  de la interfaz (nodos, enlaces, subgrafos). Se convierten a formato API
  con /object_info: ui_to_api().
- Los que se dejan en plugins/comfyui/workflows/ (exportados con
  "Export (API)" o también en formato de la interfaz).
- Los de AuraVox (auto_templates): sencillos, armados con los modelos que
  se encuentren (checkpoint SD/SDXL, Flux.2 Klein, Wan).

detect() busca en el flujo dónde va cada cosa ("roles": prompt, negativo,
semilla, ancho/alto, duración, imagen de origen, modelo…) siguiendo los
enlaces desde el sampler; el administrador lo puede corregir en Ajustes.
apply() pone los valores de cada pedido en esos lugares.
"""
import copy
import random
import re

from cu_client import combo_options

CONTROL = {"fixed", "increment", "decrement", "randomize", "increment-wrap"}
WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}
SKIP_TYPES = {"Note", "MarkdownNote", "PrimitiveNode", "Reroute", "GetNode", "SetNode", "Fast Groups Bypasser (rgthree)",
              "Fast Groups Muter (rgthree)", "Fast Bypasser (rgthree)", "Fast Muter (rgthree)", "Label (rgthree)",
              "Bookmark (rgthree)", "Display Any (rgthree)"}
SAVE_RE = re.compile(r"^(Save|VHS_VideoCombine|Image Save|SaveImage)", re.I)
ROLES = ("prompt", "negative", "seed", "width", "height", "length", "fps", "image", "image2", "image3", "model",
         "model2", "steps", "cfg", "denoise")
MAX_REFS = 3


class WorkflowError(Exception):
    pass


# ── Formato de la interfaz → formato API ───────────────────────────────

def _spec_inputs(info: dict) -> list:
    """[(nombre, spec)] en el orden del nodo (required y optional)."""
    inp = (info or {}).get("input") or {}
    order = (info or {}).get("input_order") or {}
    out = []
    for sect in ("required", "optional"):
        d = inp.get(sect) or {}
        for name in order.get(sect) or list(d):
            if name in d:
                out.append((name, d[name]))
    return out


def _is_widget(spec) -> bool:
    if not isinstance(spec, (list, tuple)) or not spec:
        return False
    t = spec[0]
    return isinstance(t, list) or t in WIDGET_TYPES or (isinstance(t, str) and t.startswith("COMFY_DYNAMICCOMBO"))


def _widget_values(node: dict, info: dict) -> dict:
    named = node.get("widgets_values_named")
    if isinstance(named, dict) and named:
        return {k: v for k, v in named.items() if k != "control_after_generate"}
    vals = node.get("widgets_values")
    if isinstance(vals, dict):
        return dict(vals)
    vals = list(vals or [])
    names = [i["name"] for i in node.get("inputs") or [] if isinstance(i, dict) and i.get("widget")]
    spec_names = [n for n, s in _spec_inputs(info) if _is_widget(s)] if info else []
    if len(spec_names) > len(names):
        names = spec_names
    out, k = {}, 0
    for name in names:
        if k >= len(vals):
            break
        out[name] = vals[k]
        k += 1
        # Detrás de una semilla viene "randomize/fixed…" (control_after_generate).
        if k < len(vals) and isinstance(out[name], int) and not isinstance(out[name], bool) \
                and isinstance(vals[k], str) and vals[k] in CONTROL:
            k += 1
    return out


class _Scope:
    def __init__(self, graph: dict, prefix: str = "", instance=None, parent=None, sub=None):
        self.prefix = prefix
        self.instance = instance
        self.parent = parent
        self.sub = sub
        self.nodes = {n["id"]: n for n in graph.get("nodes") or [] if isinstance(n, dict) and "id" in n}
        self.links = {}
        for link in graph.get("links") or []:
            if isinstance(link, list) and len(link) >= 5:
                self.links[link[0]] = (link[1], link[2], link[3], link[4])
            elif isinstance(link, dict) and "id" in link:
                self.links[link["id"]] = (link.get("origin_id"), link.get("origin_slot"), link.get("target_id"),
                                          link.get("target_slot"))


class _Converter:
    def __init__(self, ui: dict, info: dict):
        self.info = info
        self.subgraphs = {s["id"]: s for s in ((ui.get("definitions") or {}).get("subgraphs") or [])
                          if isinstance(s, dict) and s.get("id")}
        self.top = _Scope(ui)
        self.out = {}
        self.missing = set()
        self._busy = set()

    # Valor de un input de la instancia de un subgrafo (su widget promovido).
    def _instance_value(self, scope: _Scope, name: str):
        inst = scope.instance
        if inst is None:
            return None
        vals = inst.get("widgets_values")
        if isinstance(vals, list) and vals:
            wv = _widget_values({"inputs": inst.get("inputs"), "widgets_values": vals}, None)
            if name in wv:
                return ("value", wv[name])
        return None

    def resolve(self, scope: _Scope, link_id):
        """("link", id, slot) | ("value", v) | None de lo que llega por un enlace."""
        link = scope.links.get(link_id)
        if not link:
            return None
        origin, slot = link[0], link[1]
        if origin == -10:  # entrada del subgrafo: viene de afuera
            name = (scope.sub.get("inputs") or [{}])[slot].get("name") if scope.sub else None
            inst = scope.instance or {}
            for i in inst.get("inputs") or []:
                if i.get("name") == name:
                    if i.get("link") is not None:
                        return self.resolve(scope.parent, i["link"])
                    return self._instance_value(scope, name)
            return None
        node = scope.nodes.get(origin)
        return self.output_of(scope, node, slot) if node else None

    def output_of(self, scope: _Scope, node: dict, slot: int):
        t = node.get("type")
        mode = node.get("mode", 0)
        if mode == 2:  # silenciado: no da nada
            return None
        if mode == 4:  # puenteado: pasa la entrada del mismo tipo
            outs = node.get("outputs") or []
            want = outs[slot].get("type") if slot < len(outs) else None
            ins = [i for i in node.get("inputs") or [] if i.get("link") is not None and i.get("type") == want]
            return self.resolve(scope, ins[0]["link"]) if ins else None
        if t == "Reroute":
            ins = node.get("inputs") or []
            return self.resolve(scope, ins[0]["link"]) if ins and ins[0].get("link") is not None else None
        if t == "PrimitiveNode":
            vals = node.get("widgets_values") or []
            return ("value", vals[0]) if vals else None
        if t == "SetNode":
            ins = node.get("inputs") or []
            return self.resolve(scope, ins[0]["link"]) if ins and ins[0].get("link") is not None else None
        if t == "GetNode":
            key = (node.get("widgets_values") or [None])[0]
            for n in scope.nodes.values():
                if n.get("type") == "SetNode" and (n.get("widgets_values") or [None])[0] == key:
                    return self.output_of(scope, n, 0)
            return None
        if t in self.subgraphs:
            sub = self.subgraphs[t]
            inner = _Scope(sub, f"{scope.prefix}{node['id']}:", node, scope, sub)
            outs = sub.get("outputs") or []
            if slot >= len(outs):
                return None
            for lid in outs[slot].get("linkIds") or []:
                r = self.resolve(inner, lid)
                if r is not None:
                    return r
            return None
        nid = self.emit(scope, node)
        return ("link", nid, slot) if nid else None

    def emit(self, scope: _Scope, node: dict):
        nid = f"{scope.prefix}{node['id']}"
        if nid in self.out:
            return nid
        cls = node.get("type")
        info = self.info.get(cls)
        if info is None:
            self.missing.add(cls)
            return None
        if nid in self._busy:
            return None
        self._busy.add(nid)
        values = _widget_values(node, info)
        inputs = {}
        linked = {}
        for i in node.get("inputs") or []:
            if isinstance(i, dict) and i.get("link") is not None:
                linked[i["name"]] = i["link"]
        if cls == "Power Lora Loader (rgthree)":
            for k, v in values.items():
                if isinstance(v, dict) and ("lora" in v or v.get("type") == "PowerLoraLoaderHeaderWidget"):
                    inputs[k] = v
        spec_names = {n for n, _s in _spec_inputs(info)}
        for name, _spec in _spec_inputs(info):
            if name in linked:
                r = self.resolve(scope, linked[name])
                if r and r[0] == "link":
                    inputs[name] = [r[1], r[2]]
                    continue
                if r and r[0] == "value":
                    inputs[name] = r[1]
                    continue
            if name in values:
                inputs[name] = values[name]
        # Entradas anidadas de los combos dinámicos ("formato.códec").
        for k, v in values.items():
            if "." in k and k.split(".", 1)[0] in spec_names:
                inputs[k] = v
        # Entradas dinámicas que no están en la spec (p. ej. lora_1 o
        # entradas que crecen solas) pero que llegan enlazadas.
        for name, lid in linked.items():
            if name not in inputs and name not in spec_names:
                r = self.resolve(scope, lid)
                if r and r[0] == "link":
                    inputs[name] = [r[1], r[2]]
        self._busy.discard(nid)
        title = node.get("title") or ""
        self.out[nid] = {"class_type": cls, "inputs": inputs, "_meta": {"title": title or cls}}
        return nid

    def _outputs(self, scope: _Scope, active=True):
        for node in scope.nodes.values():
            if node.get("mode", 0) != 0 or not active:
                continue
            t = node.get("type")
            if t in self.subgraphs:
                sub = self.subgraphs[t]
                yield from self._outputs(_Scope(sub, f"{scope.prefix}{node['id']}:", node, scope, sub))
            elif (self.info.get(t) or {}).get("output_node"):
                yield scope, node

    def convert(self) -> dict:
        outs = list(self._outputs(self.top))
        saves = [(s, n) for s, n in outs if SAVE_RE.match(n.get("type") or "")]
        for scope, node in saves or outs:
            self.emit(scope, node)
        if not self.out:
            raise WorkflowError("el flujo no tiene un nodo que guarde la imagen o el video (SaveImage, SaveVideo…)")
        return self.out


def is_api_format(data: dict) -> bool:
    return isinstance(data, dict) and bool(data) and all(
        isinstance(v, dict) and "class_type" in v for v in data.values())


def ui_to_api(ui: dict, info: dict):
    """(grafo API, nodos que faltan en ComfyUI)."""
    if is_api_format(ui):
        return ui, []
    if not isinstance(ui, dict) or not isinstance(ui.get("nodes"), list):
        raise WorkflowError("no es un flujo de ComfyUI")
    c = _Converter(ui, info)
    api = c.convert()
    return api, sorted(x for x in c.missing if x and x not in SKIP_TYPES)


# ── Detectar las entradas ──────────────────────────────────────────────

TEXT_KEYS = ("text", "prompt", "value", "string", "text_g", "t5xxl", "positive_prompt", "negative_prompt", "string_a")
SAMPLER_POS = ("positive", "conditioning")


def _is_link(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)


def _consumers(g: dict) -> dict:
    out = {}
    for nid, n in g.items():
        for name, v in (n.get("inputs") or {}).items():
            if _is_link(v):
                out.setdefault(v[0], []).append((nid, name))
    return out


def _trace_text(g: dict, ref, seen=None):
    """(nodo, input) del texto literal que termina en `ref` (condicionamiento
    o texto), siguiendo enlaces hacia atrás. Respeta los interruptores."""
    seen = seen or set()
    if not _is_link(ref) or ref[0] in seen or ref[0] not in g:
        return None
    nid = ref[0]
    seen.add(nid)
    n = g[nid]
    ins = n.get("inputs") or {}
    if n.get("class_type") == "ConditioningZeroOut":
        return None
    for key in TEXT_KEYS:
        if isinstance(ins.get(key), str):
            return nid, key
    if "switch" in ins and isinstance(ins["switch"], bool):
        pick = ins.get("on_true" if ins["switch"] else "on_false")
        return _trace_text(g, pick, seen)
    order = [k for k in TEXT_KEYS if _is_link(ins.get(k))] + [k for k, v in ins.items() if _is_link(v) and k not in TEXT_KEYS]
    for key in order:
        if key in ("clip", "model", "vae", "latent", "image", "pixels"):
            continue
        hit = _trace_text(g, ins[key], seen)
        if hit:
            return hit
    return None


def _samplers(g: dict) -> list:
    return [nid for nid, n in g.items() if "positive" in (n.get("inputs") or {}) or
            (n.get("class_type") == "BasicGuider" and "conditioning" in (n.get("inputs") or {}))]


def _literal_source(g, ref) -> bool:
    """¿El enlace viene de un nodo sin entradas enlazadas (un selector de
    resolución, un primitivo)? Esos sí se pueden pisar con un número."""
    n = g.get(ref[0]) if _is_link(ref) else None
    return bool(n) and not any(_is_link(v) for v in (n.get("inputs") or {}).values())


LOADER_KEYS = ("unet_name", "ckpt_name", "model_name", "gguf_name")


def detect(g: dict) -> list:
    """[{role, node, input}] de un grafo API."""
    found = []
    have = set()

    def add(role, nid, inp):
        if (role, nid, inp) not in have:
            have.add((role, nid, inp))
            found.append({"role": role, "node": nid, "input": inp})

    for sid in _samplers(g):
        ins = g[sid]["inputs"]
        pos = ins.get("positive", ins.get("conditioning"))
        hit = _trace_text(g, pos)
        if hit and not any(f["role"] == "prompt" for f in found):
            add("prompt", *hit)
        hit = _trace_text(g, ins.get("negative"))
        if hit and not any(f["role"] == "negative" for f in found) and hit != next(
                ((f["node"], f["input"]) for f in found if f["role"] == "prompt"), None):
            add("negative", *hit)
    if not any(f["role"] == "prompt" for f in found):
        # Sin sampler reconocible: el primer codificador de texto.
        for nid, n in sorted(g.items(), key=lambda kv: _num(kv[0])):
            for key in ("text", "prompt"):
                if isinstance((n.get("inputs") or {}).get(key), str) and "Encode" in n["class_type"]:
                    add("prompt", nid, key)
                    break
            if found:
                break
    loads, loaders = [], []
    for nid, n in sorted(g.items(), key=lambda kv: _num(kv[0])):
        cls = n.get("class_type") or ""
        ins = n.get("inputs") or {}
        for key in ("seed", "noise_seed"):
            if isinstance(ins.get(key), int) and not isinstance(ins.get(key), bool):
                add("seed", nid, key)
        if re.search(r"Empty.*Latent|LatentVideo|ImageToVideo|Wan22ImageToVideoLatent|Flux2Scheduler", cls):
            for key in ("width", "height"):
                if isinstance(ins.get(key), int) or (_is_link(ins.get(key)) and _literal_source(g, ins[key])):
                    if cls != "Flux2Scheduler" or not _is_link(ins.get(key)) or _literal_source(g, ins[key]):
                        add(key, nid, key)
            for key in ("length", "num_frames", "frames"):
                if isinstance(ins.get(key), int):
                    add("length", nid, key)
        for key in ("fps", "frame_rate"):
            if isinstance(ins.get(key), (int, float)) and not isinstance(ins.get(key), bool):
                add("fps", nid, key)
        if cls in ("LoadImage", "LoadImageMask") or (cls.startswith("LoadImage") and isinstance(ins.get("image"), str)):
            loads.append(nid)
        for key in LOADER_KEYS:
            if isinstance(ins.get(key), str) and "Loader" in cls:
                loaders.append((nid, key))
                break
        if cls in ("KSampler", "KSamplerAdvanced", "Flux2Scheduler", "BasicScheduler") or cls.startswith("KSampler"):
            if isinstance(ins.get("steps"), int) and not any(f["role"] == "steps" for f in found):
                add("steps", nid, "steps")
            if isinstance(ins.get("denoise"), float) and not any(f["role"] == "denoise" for f in found):
                add("denoise", nid, "denoise")
        if isinstance(ins.get("cfg"), (int, float)) and not isinstance(ins.get("cfg"), bool) \
                and not any(f["role"] == "cfg" for f in found):
            add("cfg", nid, "cfg")
    for k, nid in enumerate(loads[:3]):
        add(("image", "image2", "image3")[k], nid, "image")
    for k, (nid, key) in enumerate(loaders[:2]):
        add("model" if k == 0 else "model2", nid, key)
    return found


def _num(nid: str):
    parts = re.findall(r"\d+", str(nid))
    return tuple(int(p) for p in parts) or (0,)


def kind_of(g: dict, mapping: list) -> str:
    """"video", "edit" o "image" según lo que tenga el flujo."""
    roles = {m["role"] for m in mapping}
    classes = {n.get("class_type") for n in g.values()}
    length = next((g[m["node"]]["inputs"].get(m["input"]) for m in mapping if m["role"] == "length"), None)
    if (isinstance(length, int) and length > 1) or classes & {"SaveVideo", "VHS_VideoCombine", "SaveWEBM",
                                                               "SaveAnimatedWEBP", "CreateVideo"}:
        return "video"
    if "image" in roles:
        return "edit"
    return "image"


def output_nodes(g: dict) -> list:
    return [nid for nid, n in g.items() if SAVE_RE.match(n.get("class_type") or "")]


def fields(g: dict, info: dict) -> list:
    """Todas las entradas con un valor literal (para corregir el mapeo)."""
    out = []
    for nid, n in sorted(g.items(), key=lambda kv: _num(kv[0])):
        for name, v in (n.get("inputs") or {}).items():
            if _is_link(v) or isinstance(v, dict):
                continue
            t = "text" if isinstance(v, str) else "bool" if isinstance(v, bool) else "int" if isinstance(v, int) else (
                "float" if isinstance(v, float) else "other")
            out.append({"node": nid, "input": name, "class": n.get("class_type"), "title": (n.get("_meta") or {}).get("title") or "",
                        "type": t, "value": v if not isinstance(v, str) else v[:160]})
    return out


def missing_files(g: dict, info: dict, mapping: list) -> list:
    """Modelos (o archivos) que el flujo pide y ComfyUI no tiene: un valor
    que no está entre las opciones de su lista. La imagen de origen no
    cuenta (se reemplaza en cada pedido)."""
    replaced = {(m["node"], m["input"]) for m in mapping if m["role"] in ("image", "image2")}
    out = []
    for nid, n in g.items():
        spec_all = ((info.get(n.get("class_type")) or {}).get("input") or {})
        for name, v in (n.get("inputs") or {}).items():
            if not isinstance(v, str) or (nid, name) in replaced:
                continue
            spec = (spec_all.get("required") or {}).get(name) or (spec_all.get("optional") or {}).get(name)
            is_combo = isinstance(spec, (list, tuple)) and spec and (isinstance(spec[0], list) or spec[0] == "COMBO")
            if is_combo and v not in combo_options(spec) and re.search(r"\.(safetensors|gguf|ckpt|pt|pth|bin|sft|onnx)$", v, re.I):
                out.append(v)
    return sorted(set(out))


def model_options(g: dict, info: dict, mapping: list, role="model") -> list:
    m = next((x for x in mapping if x["role"] == role), None)
    if not m or m["node"] not in g:
        return []
    cls = g[m["node"]]["class_type"]
    spec = ((info.get(cls) or {}).get("input") or {})
    for sect in ("required", "optional"):
        if m["input"] in (spec.get(sect) or {}):
            return combo_options(spec[sect][m["input"]])
    return []


# ── Rellenar un pedido ─────────────────────────────────────────────────

def _round_frames(length: int, default: int) -> int:
    for step in (8, 4):
        if default and (default - 1) % step == 0:
            return max(1, round((length - 1) / step) * step + 1)
    return max(1, length)


def apply(g: dict, mapping: list, params: dict, info: dict = None) -> dict:
    """Copia del grafo con los valores del pedido. `params`: prompt,
    negative, seed, width, height, duration (s), fps, image, image2,
    model, steps, cfg…"""
    g = copy.deepcopy(g)
    by = {}
    for m in mapping or []:
        if m.get("node") in g and m.get("role") in ROLES:
            by.setdefault(m["role"], []).append(m)

    def put(role, value):
        for m in by.get(role, []):
            g[m["node"]]["inputs"][m["input"]] = value

    seed = params.get("seed")
    seed = int(seed) if isinstance(seed, (int, float)) and seed >= 0 else random.randint(1, 2 ** 48)
    put("seed", seed)
    for role in ("prompt", "negative", "image", "image2", "model", "model2"):
        if params.get(role) not in (None, ""):
            put(role, params[role])
    for role in ("width", "height", "steps"):
        if params.get(role):
            v = int(params[role])
            if role in ("width", "height"):
                v = max(64, min(4096, v // 16 * 16))
            put(role, v)
    for role in ("cfg", "denoise"):
        if params.get(role) not in (None, ""):
            put(role, float(params[role]))
    fps = None
    for m in by.get("fps", []):
        fps = g[m["node"]]["inputs"].get(m["input"])
        break
    if params.get("fps"):
        fps = float(params["fps"])
        put("fps", fps if any(isinstance(g[m["node"]]["inputs"].get(m["input"]), float) for m in by.get("fps", [])) else int(fps))
    if params.get("duration") and by.get("length"):
        m = by["length"][0]
        default = g[m["node"]]["inputs"].get(m["input"]) or 0
        frames = int(round(float(params["duration"]) * float(fps or 16))) + 1
        put("length", _round_frames(min(frames, 1000), int(default)))
    if params.get("video") and info is not None:
        as_video(g, float(fps or 16), info)
    return g


def as_video(g: dict, fps: float, info: dict) -> None:
    """Si el flujo es de video (latente con duración) pero guarda imágenes
    sueltas (p. ej. un flujo de Wan para imágenes), guarda un MP4."""
    if "CreateVideo" not in info or "SaveVideo" not in info:
        return
    for nid in list(g):
        n = g[nid]
        if n.get("class_type") != "SaveImage":
            continue
        images = n["inputs"].get("images")
        cv = f"{nid}_video"
        g[cv] = {"class_type": "CreateVideo", "inputs": {"images": images, "fps": float(fps)}, "_meta": {"title": "Create Video"}}
        g[nid] = {"class_type": "SaveVideo", "inputs": {"video": [cv, 0], "filename_prefix": "auravox/video",
                                                        "format": "auto", "format.codec": "auto"},
                  "_meta": {"title": "Save Video"}}


# ── Flujos de AuraVox, armados con los modelos instalados ──────────────

def _pick(names, *patterns, avoid=()):
    for pat in patterns:
        for n in names:
            low = n.lower()
            if re.search(pat, low) and not any(re.search(a, low) for a in avoid):
                return n
    return None


def _save(prefix):
    return {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": prefix}, "_meta": {"title": "Save Image"}}


def auto_templates(info: dict, models: dict) -> list:
    """[{id, name, task, graph}] de los flujos que se pueden armar."""
    out = []
    ckpts = models.get("checkpoints") or []
    ckpt = _pick(ckpts, r"xl|pony|illustrious|juggernaut|realvis", r".") if ckpts else None
    if ckpt:
        size = 512 if re.search(r"(sd)?[-_ ]?1\.?5|v1-5", ckpt.lower()) else 1024
        base = {
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["4", 1]}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry, low quality, deformed, watermark, text", "clip": ["4", 1]}},
            "3": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 25, "cfg": 6.0, "sampler_name": "dpmpp_2m",
                                                       "scheduler": "karras", "denoise": 1.0, "model": ["4", 0],
                                                       "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        }
        t2i = copy.deepcopy(base)
        t2i["5"] = {"class_type": "EmptyLatentImage", "inputs": {"width": size, "height": size, "batch_size": 1}}
        t2i["9"] = _save("auravox/image")
        out.append({"id": "auto:sd_t2i", "name": "AuraVox · Checkpoint → imagen", "task": "image", "graph": t2i})
        i2i = copy.deepcopy(base)
        i2i["10"] = {"class_type": "LoadImage", "inputs": {"image": "example.png"}}
        i2i["11"] = {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["10", 0], "upscale_method": "lanczos",
                                                                          "megapixels": 1.0 if size == 1024 else 0.3,
                                                                          "resolution_steps": 8}}
        i2i["5"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["4", 2]}}
        i2i["3"]["inputs"]["denoise"] = 0.6
        i2i["9"] = _save("auravox/edit")
        out.append({"id": "auto:sd_img2img", "name": "AuraVox · Checkpoint → retocar imagen (img2img)", "task": "edit",
                    "graph": i2i})

    unets = (models.get("diffusion_models") or []) + (models.get("gguf") or [])
    encoders = models.get("text_encoders") or []
    vaes = models.get("vae") or []
    klein = _pick(unets, r"klein.*9b", r"klein")
    if klein and "Flux2Scheduler" in info and "EmptyFlux2LatentImage" in info:
        gguf = klein.lower().endswith(".gguf")
        if gguf and "UnetLoaderGGUF" not in info:
            klein = None
    if klein and "Flux2Scheduler" in info:
        big = "9b" in klein.lower()
        enc = _pick(encoders, r"qwen.?3.?8b" if big else r"qwen.?3.?4b", r"qwen.?3")
        vae = _pick(vaes, r"flux2", r"flux.?2")
        if enc and vae:
            loader = ({"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": klein}} if klein.lower().endswith(".gguf")
                      else {"class_type": "UNETLoader", "inputs": {"unet_name": klein, "weight_dtype": "default"}})
            base = {
                "1": loader,
                "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": enc, "type": "flux2", "device": "default"}},
                "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
                "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["2", 0]}},
                "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["2", 0]}},
                "12": {"class_type": "RandomNoise", "inputs": {"noise_seed": 1}},
                "13": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
                "15": {"class_type": "CFGGuider", "inputs": {"cfg": 1.0, "model": ["1", 0], "positive": ["6", 0], "negative": ["7", 0]}},
                "16": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["12", 0], "guider": ["15", 0], "sampler": ["13", 0],
                                                                         "sigmas": ["14", 0], "latent_image": ["5", 0]}},
                "8": {"class_type": "VAEDecode", "inputs": {"samples": ["16", 0], "vae": ["3", 0]}},
            }
            t2i = copy.deepcopy(base)
            t2i["5"] = {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}}
            t2i["14"] = {"class_type": "Flux2Scheduler", "inputs": {"steps": 4, "width": 1024, "height": 1024}}
            t2i["9"] = _save("auravox/image")
            out.append({"id": "auto:flux2_klein_t2i", "name": "AuraVox · Flux.2 Klein → imagen", "task": "image", "graph": t2i})
            ed = copy.deepcopy(base)
            ed["20"] = {"class_type": "LoadImage", "inputs": {"image": "example.png"}}
            ed["21"] = {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["20", 0], "upscale_method": "lanczos",
                                                                             "megapixels": 1.0, "resolution_steps": 16}}
            ed["22"] = {"class_type": "GetImageSize", "inputs": {"image": ["21", 0]}}
            ed["23"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["21", 0], "vae": ["3", 0]}}
            ed["24"] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["6", 0], "latent": ["23", 0]}}
            ed["25"] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["7", 0], "latent": ["23", 0]}}
            ed["15"]["inputs"].update(positive=["24", 0], negative=["25", 0])
            ed["5"] = {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": ["22", 0], "height": ["22", 1], "batch_size": 1}}
            ed["14"] = {"class_type": "Flux2Scheduler", "inputs": {"steps": 4, "width": ["22", 0], "height": ["22", 1]}}
            ed["9"] = _save("auravox/edit")
            out.append({"id": "auto:flux2_klein_edit", "name": "AuraVox · Flux.2 Klein → editar imagen", "task": "edit", "graph": ed})

    # Wan 2.2 (dos modelos, ruido alto y bajo) o Wan 2.1 (uno), texto → video.
    umt5 = _pick(encoders, r"umt5")
    wvae = _pick(vaes, r"wan.?2\.?1.*vae|wan_2\.1_vae", r"wan.*vae", avoid=(r"2\.2",))
    high = _pick(unets, r"wan2\.?2.*t2v.*high", avoid=(r"i2v",))
    low = _pick(unets, r"wan2\.?2.*t2v.*low", avoid=(r"i2v",))
    single = _pick(unets, r"wan2\.?1.*t2v", avoid=(r"i2v",))
    lora = _pick(models.get("loras") or [], r"lightx2v.*t2v|t2v.*lightx2v|lightx2v")
    if umt5 and wvae and (high and low or single) and "EmptyHunyuanLatentVideo" in info and "SaveVideo" in info:
        def load(name, nid):
            if name.lower().endswith(".gguf"):
                return {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": name}}
            return {"class_type": "UNETLoader", "inputs": {"unet_name": name, "weight_dtype": "default"}}

        g = {
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": umt5, "type": "wan", "device": "default"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": wvae}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["2", 0]}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "static, blurry, low quality, worst quality, deformed, "
                                                                     "extra fingers, watermark, subtitles", "clip": ["2", 0]}},
            "5": {"class_type": "EmptyHunyuanLatentVideo", "inputs": {"width": 832, "height": 480, "length": 33, "batch_size": 1}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["31", 0], "vae": ["3", 0]}},
            "40": {"class_type": "CreateVideo", "inputs": {"images": ["8", 0], "fps": 16.0}},
            "9": {"class_type": "SaveVideo", "inputs": {"video": ["40", 0], "filename_prefix": "auravox/video",
                                                        "format": "auto", "format.codec": "auto"}},
        }
        steps, cfg = (6, 1.0) if lora else (20, 3.5)
        models_ = [("1", high or single), ("11", low)] if high and low else [("1", single)]
        prev = None
        for k, (nid, name) in enumerate(models_):
            g[nid] = load(name, nid)
            src = [nid, 0]
            if lora:
                g[f"{nid}0"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": src, "lora_name": lora, "strength_model": 1.0}}
                src = [f"{nid}0", 0]
            g[f"{nid}5"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": src, "shift": 8.0}}
            src = [f"{nid}5", 0]
            two = len(models_) == 2
            sid = "30" if k == 0 else "31"
            g[sid] = {"class_type": "KSamplerAdvanced", "inputs": {
                "model": src, "add_noise": "enable" if k == 0 else "disable", "noise_seed": 1, "steps": steps, "cfg": cfg,
                "sampler_name": "euler", "scheduler": "simple", "positive": ["6", 0], "negative": ["7", 0],
                "latent_image": ["5", 0] if k == 0 else [prev, 0],
                "start_at_step": 0 if k == 0 else steps // 2, "end_at_step": steps // 2 if (two and k == 0) else 10000,
                "return_with_leftover_noise": "enable" if (two and k == 0) else "disable"}}
            prev = sid
        if len(models_) == 1:
            g["8"]["inputs"]["samples"] = ["30", 0]
        out.append({"id": "auto:wan_t2v", "name": "AuraVox · Wan → video", "task": "video", "graph": g})
    return out


# ── Imágenes de referencia ("un vestido como el de esta otra foto") ─────
# Se suman al grafo en memoria (nunca se toca el flujo guardado), según lo
# que tenga el flujo:
# 1. Entradas mapeadas como "image2"/"image3" (otro LoadImage del flujo).
# 2. Codificadores con entradas de imagen libres (TextEncodeQwenImageEditPlus:
#    image2, image3).
# 3. Flujos con ReferenceLatent (Flux.2 Klein, Flux Kontext…): por cada
#    referencia, LoadImage → escalar como la de origen → VAEEncode → un
#    ReferenceLatent más en la cadena del positivo y del negativo.

def _ref_slots(g: dict, mapping: list) -> list:
    """Lugares fijos para referencias: [(nodo, input)] de image2/image3 y
    de entradas de imagen libres de los codificadores tipo Qwen."""
    slots = [(m["node"], m["input"]) for r in ("image2", "image3") for m in mapping if m["role"] == r and m["node"] in g]
    for nid, n in g.items():
        if "TextEncodeQwenImageEdit" in (n.get("class_type") or ""):
            for key in ("image2", "image3"):
                if key not in (n.get("inputs") or {}):
                    slots.append((nid, key))
    return slots


def ref_capacity(g: dict, mapping: list) -> int:
    """Cuántas referencias admite el flujo (además de la imagen a editar)."""
    if any(n.get("class_type") == "ReferenceLatent" for n in g.values()):
        return MAX_REFS
    return min(MAX_REFS, len(_ref_slots(g, mapping)))


def add_references(g: dict, mapping: list, refs: list) -> int:
    """Suma al grafo (ya copiado) las referencias subidas a ComfyUI
    (nombres para LoadImage). Devuelve cuántas usó."""
    refs = list(refs)[:MAX_REFS]
    if not refs:
        return 0
    loads = []
    for k, name in enumerate(refs):
        nid = f"avref{k}_load"
        g[nid] = {"class_type": "LoadImage", "inputs": {"image": name}, "_meta": {"title": f"Referencia {k + 1}"}}
        loads.append(nid)
    used = 0
    slots = _ref_slots(g, mapping)
    for (nid, key), load in zip(slots, loads):
        cls = g[nid].get("class_type")
        if cls in ("LoadImage", "LoadImageMask") or cls.startswith("LoadImage"):
            g[nid]["inputs"][key] = g[load]["inputs"]["image"]
            g.pop(load)
        else:
            g[nid]["inputs"][key] = [load, 0]
        used += 1
    loads = [x for x in loads[used:] if x in g]
    rls = [nid for nid, n in g.items() if n.get("class_type") == "ReferenceLatent"]
    if loads and rls:
        enc = None
        for nid in rls:
            lat = g[nid]["inputs"].get("latent")
            if _is_link(lat) and g.get(lat[0], {}).get("class_type") == "VAEEncode":
                enc = g[lat[0]]
                break
        if enc and _is_link(enc["inputs"].get("vae")):
            pix = enc["inputs"].get("pixels")
            scale = g.get(pix[0]) if _is_link(pix) else None
            scale_inputs = dict(scale["inputs"]) if scale and scale.get("class_type") == "ImageScaleToTotalPixels" else {
                "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 16}
            # Dónde termina cada cadena de ReferenceLatent (lo que la usa y no es otro ReferenceLatent).
            ends = [(nid, key) for nid, n in g.items() if n.get("class_type") != "ReferenceLatent"
                    for key, v in (n.get("inputs") or {}).items() if _is_link(v) and v[0] in rls]
            for k, load in enumerate(loads):
                sc, ve = f"avref{k}_scale", f"avref{k}_enc"
                g[sc] = {"class_type": "ImageScaleToTotalPixels", "inputs": {**scale_inputs, "image": [load, 0]}}
                g[ve] = {"class_type": "VAEEncode", "inputs": {"pixels": [sc, 0], "vae": enc["inputs"]["vae"]}}
                for j, (nid, key) in enumerate(ends):
                    rl = f"avref{k}_rl{j}"
                    g[rl] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": g[nid]["inputs"][key], "latent": [ve, 0]}}
                    g[nid]["inputs"][key] = [rl, 0]
                used += 1
    for nid in [x for x in g if x.startswith("avref") and x.endswith("_load")]:
        if not any(_is_link(v) and v[0] == nid for n in g.values() for v in (n.get("inputs") or {}).values()):
            g.pop(nid)  # una referencia que no entró en ningún lado
    return used
