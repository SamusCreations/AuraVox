"""
Short phrases an assistant says on its own (voice mode): when it searches the
web, uses another tool, starts creating an image or video, takes long to
think, or when its reply gets stuck.

Per assistant and kind (`phrases` in assistants.yaml, see config_store):
- "auto" (default): written by the assistant's own model in its personality,
  once per assistant and language, cached in config/phrases/<name>.json and
  regenerated when the personality (or name/label/model) changes. Generated
  in the background: until then the fixed list (or the defaults below) is
  used, so it never adds latency to a turn.
- "fixed": the list the user wrote (one phrase per line in the page).

`pick` never repeats the previous phrase of the same kind.
"""
import hashlib
import json
import os
import random
import threading
import time

from app import paths

KINDS = ("search", "tool", "create", "wait", "fallback")
MODES = ("auto", "fixed")
PHRASES_DIR = os.path.join(paths.CONFIG_DIR, "phrases")
MAX_PHRASES = 20
MAX_CHARS = 200

# What each kind is for (for the model and the page).
PURPOSE = {
    "search": "right before searching the internet or the news for the user",
    "tool": ("right before doing something with a tool: checking the weather, finding places, playing music, "
             "reading or converting a file, setting a reminder or a list item"),
    "create": "right before starting to create an image, edit a photo or make a video, which takes a while",
    "wait": "when the answer is taking a few seconds, to let the user know it's still thinking",
    "fallback": "when its own reply got stuck or failed, asking the user to repeat or rephrase",
}

DEFAULTS = {
    "es": {
        "search": ["Buscando en internet.", "Déjame buscarlo.", "Un momento, lo busco.", "Voy a revisar en internet.",
                   "Dame un segundo, que lo busco.", "A ver qué encuentro.", "Lo consulto ya mismo.",
                   "Déjame echar un vistazo.", "Buscando la información.", "Voy a ver qué dicen."],
        "tool": ["Un momento.", "Ya lo reviso.", "Dame un segundo.", "En eso estoy.", "Lo hago ya mismo.",
                 "Déjame ver.", "Voy con eso.", "Ahora mismo.", "Enseguida.", "Lo preparo."],
        "create": ["Manos a la obra, esto tarda un poquito.", "Lo empiezo a crear, dame unos segundos.",
                   "Voy a crearlo, ya te aviso.", "Empiezo a dibujarlo.", "Lo pongo a hacer, tarda un rato.",
                   "Ya lo estoy preparando.", "Déjame trabajar en eso.", "Esto me toma un momento, ya empiezo."],
        "wait": ["Mmm, déjame pensarlo.", "Un segundito.", "Dame un momento.", "A ver…", "Pensando…",
                 "Déjame ver bien.", "Ya casi.", "Un momento, por favor."],
        "fallback": ["Se me trabó la respuesta, ¿puedes repetir la pregunta?", "Perdón, me perdí. ¿Me lo repites?",
                     "Ups, algo falló. ¿Lo puedes decir otra vez?", "No me salió bien, ¿me lo preguntas de nuevo?",
                     "Me enredé un poco, ¿lo repites?", "Disculpa, no pude responder. ¿Lo intentamos otra vez?"],
    },
    "en": {
        "search": ["Searching the web.", "Let me look that up.", "One moment, I'll search for it.",
                   "Let me check online.", "Give me a second to look it up.", "Let's see what I can find.",
                   "Checking that for you.", "Let me take a look.", "Looking for the information.",
                   "Let me see what's out there."],
        "tool": ["One moment.", "Let me check.", "Give me a second.", "On it.", "Doing it right now.",
                 "Let me see.", "Working on it.", "Right away.", "Just a moment.", "Getting that ready."],
        "create": ["On it, this takes a little while.", "I'll start creating it, give me a few seconds.",
                   "Let me make that, I'll let you know.", "Starting to draw it.", "I'm on it, it takes a bit.",
                   "Getting that started.", "Let me work on that.", "This takes a moment, starting now."],
        "wait": ["Hmm, let me think.", "Just a second.", "Give me a moment.", "Let's see…", "Thinking…",
                 "Let me think it through.", "Almost there.", "One moment, please."],
        "fallback": ["My answer got stuck, can you repeat the question?", "Sorry, I lost track. Could you say that again?",
                     "Oops, something went wrong. Can you repeat that?", "That didn't come out right, can you ask again?",
                     "I got tangled up, could you repeat it?", "Sorry, I couldn't answer. Shall we try again?"],
    },
}

_lock = threading.RLock()
_busy = set()
_last = {}  # (assistant, lang, kind) → last phrase said


def clean_list(values) -> list:
    if isinstance(values, str):
        values = values.split("\n")
    out = []
    for v in values or []:
        v = " ".join(str(v).split())[:MAX_CHARS]
        if v and v not in out:
            out.append(v)
    return out[:MAX_PHRASES]


def defaults(lang: str, kind: str) -> list:
    return list((DEFAULTS.get((lang or "")[:2]) or DEFAULTS["en"])[kind])


def _key(cfg: dict) -> str:
    raw = "|".join(str(cfg.get(k) or "") for k in ("name", "label", "base_model", "personality"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _path(name: str) -> str:
    return os.path.join(PHRASES_DIR, f"{name}.json")


def _read(name: str) -> dict:
    try:
        with open(_path(name), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def generated(cfg: dict, lang: str):
    """The cached generated phrases ({kind: [...]}) for this personality, or None."""
    data = _read(cfg.get("name") or "")
    if data.get("key") != _key(cfg):
        return None
    got = (data.get("langs") or {}).get(lang)
    return got if isinstance(got, dict) else None


def _language_name(lang: str) -> str:
    try:
        from app.core.assistant_common import language_label

        return language_label(lang)
    except Exception:  # noqa: BLE001
        return lang


def generate(cfg: dict, lang: str) -> dict:
    """Asks the assistant's model for its phrases in `lang` (structured JSON)."""
    from app.core.assistant_common import structured_request
    from app.core.assistant_engine import OLLAMA_URL

    schema = {"type": "object", "properties": {
        k: {"type": "array", "items": {"type": "string"}, "minItems": 6, "maxItems": 10} for k in KINDS
    }, "required": list(KINDS)}
    kinds = "\n".join(f"- {k}: {PURPOSE[k]}" for k in KINDS)
    system = (
        "You write the short phrases a voice assistant says out loud in specific moments, fully in character. "
        f"Its personality:\n<<<\n{cfg.get('personality', '')[:6000]}\n>>>\n\n"
        f"Write 8 different phrases for each moment, in {_language_name(lang)} only, as this assistant would say "
        "them (its tone, slang and attitude). Each one short (3 to 14 words), natural when spoken, different from "
        "the others, plain words only: no emojis, no stage directions, no quotes, no placeholders. They must not "
        "promise a specific result, mention a specific topic, or address the user by a name.\n\nMoments:\n" + kinds
    )
    data = structured_request(OLLAMA_URL, cfg["base_model"], [
        {"role": "system", "content": system},
        {"role": "user", "content": "Write the phrases now."},
    ], schema, max_tokens=1500)
    if not data:
        raise RuntimeError("the model returned nothing usable")
    out = {k: clean_list(data.get(k)) for k in KINDS}
    if not all(out.values()):
        raise RuntimeError("some kinds came back empty")
    return out


def _store(cfg: dict, lang: str, found: dict) -> None:
    with _lock:
        os.makedirs(PHRASES_DIR, exist_ok=True)
        data = _read(cfg["name"])
        if data.get("key") != _key(cfg):
            data = {"key": _key(cfg), "langs": {}}
        data.setdefault("langs", {})[lang] = found
        data["updated"] = time.time()
        tmp = _path(cfg["name"]) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _path(cfg["name"]))


def ensure_async(cfg: dict, lang: str, force: bool = False, log=None) -> bool:
    """Starts generating in the background if needed. True if it started."""
    name = cfg.get("name") or ""
    if not name or not cfg.get("base_model") or not cfg.get("personality"):
        return False
    job = (name, lang)
    with _lock:
        if job in _busy or (not force and generated(cfg, lang)):
            return False
        _busy.add(job)

    def run():
        t0 = time.time()
        try:
            found = generate(cfg, lang)
            _store(cfg, lang, found)
            if log:
                log("phrases", f"{name.upper()} [{lang}]: generated its own phrases in {time.time() - t0:.1f}s "
                               f"(«{found['search'][0]}»)")
        except Exception as e:  # noqa: BLE001 — the fixed/default phrases are used meanwhile
            if log:
                log("phrases", f"{name.upper()} [{lang}]: could not generate phrases ({e})", "warn")
        finally:
            with _lock:
                _busy.discard(job)

    threading.Thread(target=run, name=f"phrases-{name}-{lang}", daemon=True).start()
    return True


def pool(cfg: dict, lang: str, log=None) -> dict:
    """{kind: [phrases]} to use now for `lang`, plus "pending": generating."""
    settings = cfg.get("phrases") or {}
    gen = None
    out = {}
    for kind in KINDS:
        s = settings.get(kind) or {}
        fixed = clean_list(s.get("fixed"))
        if s.get("mode", "auto") == "fixed" and fixed:
            out[kind] = fixed
            continue
        if gen is None:
            gen = generated(cfg, lang) or {}
            if not gen:
                ensure_async(cfg, lang, log=log)
        out[kind] = clean_list(gen.get(kind)) or fixed or defaults(lang, kind)
    out["pending"] = (cfg.get("name"), lang) in _busy
    return out


def pick(cfg: dict, lang: str, kind: str, log=None) -> str:
    """One phrase of `kind`, never the same as the previous one."""
    options = pool(cfg, lang, log).get(kind) or defaults(lang, kind)
    last = _last.get((cfg.get("name"), lang, kind))
    choices = [p for p in options if p != last] or options
    choice = random.choice(choices)
    _last[(cfg.get("name"), lang, kind)] = choice
    return choice
