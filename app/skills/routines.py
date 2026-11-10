"""Rutinas: un pedido que junta varias cosas, configurable por perfil.

"Buenos días" = el clima + los recordatorios de hoy + lo pendiente de las
listas + los titulares. Cada perfil arma las suyas en Ajustes → Rutinas:
nombre, cuándo usarla (en sus palabras: "cuando te digo buenos días"), qué
bloques junta y una indicación extra ("termina con una frase motivadora").
El modelo decide cuándo llamar run_routine por lo que dice el usuario, en
cualquier idioma.

Una rutina puede además tener hora (y días): a esa hora el servidor la
corre con el asistente elegido y la avisa como un recordatorio (dicha en
la PC, notificación en el celular). Ver config_ui._routine_due.

Se guardan en config/routines/<perfil>.json. El invitado tiene solo la de
ejemplo ("Buenos días"), sin hora.
"""
import datetime
import json
import os
import re
import secrets
import threading
import time
import traceback

from app import paths

NAME = "routines"
MIN_ROLE = "guest"

ROUTINES_DIR = os.path.join(paths.CONFIG_DIR, "routines")
PROFILE_RE = re.compile(r"^p[0-9a-f]{8}$")
ID_RE = re.compile(r"^u[0-9a-f]{6}$")
BLOCKS = ("weather", "reminders", "lists", "news", "date")
MAX_ROUTINES = 12

RUN = "run_routine"

_lock = threading.RLock()


def default_routines(lang: str = "es") -> list:
    es = lang == "es"
    return [{
        "id": "u000001",
        "name": "Buenos días" if es else "Good morning",
        "when": ("Cuando te saludo por la mañana (buenos días, ¿qué hay para hoy?)" if es
                 else "When I greet you in the morning (good morning, what's on today?)"),
        "blocks": ["date", "weather", "reminders", "lists", "news"],
        "news_topic": "",
        "extra": "",
        "time": "", "days": [], "assistant": "",
    }]


def _path(profile: str) -> str:
    if not PROFILE_RE.match(profile or ""):
        raise ValueError("perfil inválido")
    return os.path.join(ROUTINES_DIR, f"{profile}.json")


def _clean(text, n: int) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", str(text or ""))).strip()[:n]


def validate(items) -> list:
    out = []
    seen = set()
    for r in (items if isinstance(items, list) else [])[:MAX_ROUTINES]:
        if not isinstance(r, dict):
            continue
        name = _clean(r.get("name"), 60)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        hhmm = str(r.get("time") or "").strip()
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", hhmm):
            hhmm = ""
        days = sorted({int(d) for d in r.get("days") or [] if str(d).isdigit() and 0 <= int(d) <= 6})
        assistant = str(r.get("assistant") or "")
        out.append({
            "id": r["id"] if ID_RE.match(str(r.get("id"))) else "u" + secrets.token_hex(3),
            "name": name,
            "when": _clean(r.get("when"), 300),
            "blocks": [b for b in BLOCKS if b in (r.get("blocks") or [])],
            "news_topic": _clean(r.get("news_topic"), 120),
            "extra": _clean(r.get("extra"), 600),
            "time": hhmm,
            "days": days or ([0, 1, 2, 3, 4, 5, 6] if hhmm else []),
            "assistant": assistant if re.fullmatch(r"[a-z0-9_]{1,40}", assistant) else "",
        })
    return out


def load(profile: str, lang: str = "es") -> list:
    with _lock:
        try:
            with open(_path(profile), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return default_routines(lang)
    return validate(data.get("routines") if isinstance(data, dict) else None)


def save(profile: str, items) -> list:
    clean = validate(items)
    with _lock:
        os.makedirs(ROUTINES_DIR, exist_ok=True)
        path = _path(profile)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"routines": clean}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    return clean


def rename_assistant(old: str, new: str) -> None:
    """Las rutinas de todos los perfiles que usaban al asistente renombrado."""
    with _lock:
        if not os.path.isdir(ROUTINES_DIR):
            return
        for name in os.listdir(ROUTINES_DIR):
            path = os.path.join(ROUTINES_DIR, name)
            if not name.endswith(".json"):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            items = data.get("routines") if isinstance(data, dict) else None
            if not isinstance(items, list) or not any(isinstance(r, dict) and r.get("assistant") == old for r in items):
                continue
            for r in items:
                if isinstance(r, dict) and r.get("assistant") == old:
                    r["assistant"] = new
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)


def delete_owner(profile: str) -> None:
    with _lock:
        try:
            os.remove(_path(profile))
        except OSError:
            pass


def all_scheduled() -> list:
    """(perfil, rutina) de todas las que tienen hora."""
    out = []
    try:
        names = os.listdir(ROUTINES_DIR)
    except OSError:
        return out
    for n in names:
        pid = n[:-5] if n.endswith(".json") else ""
        if PROFILE_RE.match(pid):
            out += [(pid, r) for r in load(pid) if r.get("time")]
    return out


# ── Habilidad ──────────────────────────────────────────────────────────

def _routines_for(ctx) -> list:
    lang = (ctx.cfg or {}).get("language") or "es"
    if ctx.guest or not ctx.profile:
        return default_routines(lang)
    return load(ctx.profile, lang)


def context(ctx) -> str:
    items = _routines_for(ctx)
    if not items:
        return ""
    lines = "\n".join(f"- \"{r['name']}\": {r['when'] or '(when the user asks for it by name)'}" for r in items)
    return (f"ROUTINES: the user set up these routines. When what they say matches one (in any language or words), "
            f"call {RUN} with its name and then present everything it returns as that routine, in your own style "
            f"and the user's language:\n{lines}")


def tools(ctx) -> list:
    items = _routines_for(ctx)
    if not items:
        return []
    return [{"type": "function", "function": {
        "name": RUN,
        "description": "Run one of the user's routines (e.g. their good-morning routine): it gathers the weather, today's reminders, pending lists and headlines as the routine says.",
        "parameters": {"type": "object", "properties": {
            "routine": {"type": "string", "enum": [r["name"] for r in items]},
        }, "required": ["routine"]},
    }}]


def gather(r: dict, ctx) -> str:
    """Lo que junta la rutina, como texto para el modelo."""
    from app.skills import lists, reminders

    parts = []
    now = datetime.datetime.now()
    if "date" in r["blocks"]:
        parts.append(f"DATE AND TIME: {now:%A %Y-%m-%d, %H:%M}.")
    call = ctx.call_base_tool
    if "weather" in r["blocks"] and call:
        try:
            parts.append("WEATHER:\n" + call("get_weather", {}))
        except Exception as e:  # noqa: BLE001
            parts.append(f"WEATHER: unavailable ({e}).")
    if "reminders" in r["blocks"] and ctx.owner:
        end = now.replace(hour=23, minute=59, second=59).timestamp()
        today = [x for x in reminders.list_for(ctx.owner) if x["due"] <= end]
        parts.append("TODAY'S REMINDERS AND ALARMS: " + ("; ".join(
            f"{datetime.datetime.fromtimestamp(x['due']):%H:%M} {x['text']}" for x in today) or "none."))
    if "lists" in r["blocks"]:
        rows = []
        for scope_name, scope in lists._scopes(ctx).items():
            for lst in lists.load(scope):
                pending = [i["text"] for i in lst["items"] if not i.get("done")]
                if pending:
                    rows.append(f"{lst['name']} ({scope_name}, {len(pending)}): {', '.join(pending[:10])}"
                                + ("…" if len(pending) > 10 else ""))
        parts.append("PENDING IN THE LISTS: " + ("; ".join(rows) or "nothing pending."))
    if "news" in r["blocks"] and call:
        from app.core.assistant_common import USER_CONTEXT

        topic = r.get("news_topic") or ""
        country = USER_CONTEXT.get("pais") or ""
        query = f"{topic or 'noticias principales'} hoy {country}".strip()
        try:
            parts.append("HEADLINES (web search):\n" + call("web_search", {"query": query})[:3500])
        except Exception as e:  # noqa: BLE001
            parts.append(f"HEADLINES: unavailable ({e}).")
    how = ("Present it as the routine: a short greeting fitting the time of day, then each block in that order, "
           "concrete (figures, times, names) and brief; for the headlines, the 3 most relevant in one line each.")
    if r.get("extra"):
        how += f" The user's extra instruction for this routine: {r['extra']}"
    return f"ROUTINE \"{r['name']}\" — gathered data:\n\n" + "\n\n".join(parts) + f"\n\n{how}"


def call(name: str, args: dict, ctx):
    if name != RUN:
        return None
    items = _routines_for(ctx)
    wanted = str(args.get("routine") or "").strip().lower()
    r = next((x for x in items if x["name"].lower() == wanted), None) or (items[0] if len(items) == 1 else None)
    if not r:
        return f"There's no routine called \"{args.get('routine')}\". Available: {', '.join(x['name'] for x in items)}."
    ctx.emit({"type": "routine", "name": r["name"]})
    return gather(r, ctx)


# ── Rutinas con hora ───────────────────────────────────────────────────

_thread = None


def start(on_due) -> None:
    """Hilo que mira cada 20 s si a alguna rutina le tocó su hora:
    on_due(perfil, rutina)."""
    global _thread
    if _thread and _thread.is_alive():
        return

    def run():
        done = set()
        while True:
            try:
                now = datetime.datetime.now()
                stamp = now.strftime("%Y-%m-%d %H:%M")
                for pid, r in all_scheduled():
                    key = (pid, r["id"], stamp)
                    if r["time"] == now.strftime("%H:%M") and now.weekday() in r["days"] and key not in done:
                        done.add(key)
                        threading.Thread(target=on_due, args=(pid, r), name="routine", daemon=True).start()
                done = {k for k in done if k[2] == stamp}
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            time.sleep(20)

    _thread = threading.Thread(target=run, name="routines", daemon=True)
    _thread.start()
