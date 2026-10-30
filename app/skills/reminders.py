"""Recordatorios, alarmas y temporizadores.

"Recuérdame en 10 minutos sacar la pizza", "despiértame mañana a las 6",
"pon un temporizador de 5 minutos", "todos los días a las 8 recuérdame la
pastilla": el modelo llama set_reminder con la hora (relativa o exacta),
qué recordar y la frase que dirá cuando llegue la hora, en su estilo. El
modelo decide; nada de palabras clave.

Se guardan en config/reminders.json (sobreviven a los reinicios). Un hilo
del servidor (start) mira cada segundo cuáles vencieron y los avisa:
- a las páginas abiertas de ese perfil (notify.py): en el celular, una
  notificación; en la PC, la página lo dice con la voz del asistente;
- si en la PC no hay ninguna página abierta, lo dice el propio servidor
  por los altavoces (speak_on_pc).
Un aviso que venció con el servidor apagado se da al arrancar si pasó hace
menos de MISSED_GRACE; si no, se marca como perdido.
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

NAME = "reminders"
MIN_ROLE = "guest"

REMINDERS_PATH = os.path.join(paths.CONFIG_DIR, "reminders.json")
ID_RE = re.compile(r"^r[0-9a-f]{6}$")
KINDS = ("reminder", "alarm", "timer")
REPEATS = ("none", "daily", "weekdays", "weekly")
MAX_PER_OWNER = 100
MISSED_GRACE = 6 * 3600
KEEP_DONE = 30  # avisos ya dados que se conservan (para la lista "recientes")

SET = "set_reminder"
CANCEL = "cancel_reminder"

_lock = threading.RLock()
_thread = None
_on_fire = None


# ── Archivo ────────────────────────────────────────────────────────────

def _load() -> list:
    try:
        with open(REMINDERS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    items = data.get("items") if isinstance(data, dict) else None
    return [r for r in items or [] if isinstance(r, dict) and ID_RE.match(str(r.get("id")))]


def _save(items: list) -> None:
    os.makedirs(os.path.dirname(REMINDERS_PATH), exist_ok=True)
    tmp = REMINDERS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, REMINDERS_PATH)


def public(r: dict) -> dict:
    return {k: r.get(k) for k in ("id", "text", "say", "kind", "due", "repeat", "assistant", "label", "created",
                                  "fired_at", "state")}


def list_for(owner: str, include_done: bool = False) -> list:
    with _lock:
        items = [r for r in _load() if r.get("owner") == owner]
    pending = sorted([r for r in items if r.get("state") == "pending"], key=lambda r: r["due"])
    if not include_done:
        return pending
    done = sorted([r for r in items if r.get("state") != "pending"], key=lambda r: -(r.get("fired_at") or 0))
    return pending + done[:10]


def cancel(owner: str, rid: str) -> bool:
    with _lock:
        items = _load()
        left = [r for r in items if not (r["id"] == rid and r.get("owner") == owner)]
        if len(left) == len(items):
            return False
        _save(left)
        return True


def snooze(owner: str, rid: str, minutes: float) -> dict:
    """Vuelve a avisar en `minutes` (el mismo aviso, como uno de una vez)."""
    with _lock:
        items = _load()
        r = next((x for x in items if x["id"] == rid and x.get("owner") == owner), None)
        if not r:
            raise KeyError(rid)
        if r.get("repeat", "none") != "none":
            # Uno que se repite: se crea uno suelto para el aviso pospuesto.
            r = {**r, "id": "r" + secrets.token_hex(3), "repeat": "none"}
            items.append(r)
        r.update(due=time.time() + max(1.0, minutes) * 60, state="pending", fired_at=None)
        _save(items)
        return r


def delete_owner(owner: str) -> None:
    with _lock:
        items = _load()
        left = [r for r in items if r.get("owner") != owner]
        if len(left) != len(items):
            _save(left)


def add(owner: str, profile, text: str, say: str, kind: str, due: float, repeat: str, assistant: str,
        cfg: dict, lang: str) -> dict:
    with _lock:
        items = _load()
        if sum(1 for r in items if r.get("owner") == owner and r.get("state") == "pending") >= MAX_PER_OWNER:
            raise ValueError(f"too many reminders (max {MAX_PER_OWNER})")
        r = {
            "id": "r" + secrets.token_hex(3), "owner": owner, "profile": profile,
            "text": text, "say": say, "kind": kind, "due": due, "repeat": repeat, "state": "pending",
            "assistant": assistant, "label": (cfg.get("label") or assistant or "").upper(),
            "voice": cfg.get("voice") or "M5", "speed": cfg.get("speed") or 1.0, "lang": lang,
            "created": time.time(), "fired_at": None,
        }
        items.append(r)
        _save(items)
        return r


# ── Fechas ─────────────────────────────────────────────────────────────

def _next_due(due: float, repeat: str) -> float:
    d = datetime.datetime.fromtimestamp(due)
    now = datetime.datetime.now()
    while True:
        if repeat == "weekly":
            d += datetime.timedelta(days=7)
        else:
            d += datetime.timedelta(days=1)
            if repeat == "weekdays":
                while d.weekday() >= 5:
                    d += datetime.timedelta(days=1)
        if d > now:
            return d.timestamp()


def parse_when(args: dict):
    """(timestamp, error). `in_minutes` (relativo) o `at` ("YYYY-MM-DD HH:MM"
    o "HH:MM", hora local)."""
    rel = args.get("in_minutes")
    at = str(args.get("at") or "").strip()
    if rel not in (None, "", 0, "0"):
        try:
            minutes = float(rel)
        except (TypeError, ValueError):
            return None, "in_minutes must be a number."
        if not 0 < minutes <= 60 * 24 * 366:
            return None, "in_minutes must be between 0 and a year."
        return time.time() + minutes * 60, None
    if not at:
        return None, "Say when: give in_minutes or at."
    at = at.replace("T", " ")
    now = datetime.datetime.now()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%H:%M", "%H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.datetime.strptime(at, fmt)
        except ValueError:
            continue
        if fmt.startswith("%H"):
            d = now.replace(hour=d.hour, minute=d.minute, second=d.second, microsecond=0)
            if d <= now:
                d += datetime.timedelta(days=1)
        elif fmt == "%Y-%m-%d":
            d = d.replace(hour=9)
        if d <= now - datetime.timedelta(seconds=30):
            return None, f"That time ({d:%Y-%m-%d %H:%M}) has already passed: ask the user or pick the next one."
        return d.timestamp(), None
    return None, 'at must look like "2026-10-24 18:30" (local time).'


def _fmt(ts: float) -> str:
    d = datetime.datetime.fromtimestamp(ts)
    return f"{d:%Y-%m-%d %H:%M} ({['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][d.weekday()]})"


def _left(ts: float) -> str:
    s = int(ts - time.time())
    if s < 60:
        return f"in {max(s, 0)} s"
    if s < 3600:
        return f"in {s // 60} min {s % 60:02d} s"
    m = round(s / 60)
    if m < 120:
        return f"in {m} min"
    h, m = divmod(m, 60)
    if h < 48:
        return f"in {h} h {m} min"
    return f"in {round(h / 24)} days"


# ── Habilidad ──────────────────────────────────────────────────────────

def context(ctx) -> str:
    now = datetime.datetime.now()
    head = (f"REMINDERS, ALARMS AND TIMERS: you can set them with {SET} (the local date and time now is "
            f"{now:%Y-%m-%d %H:%M}, {now:%A}). When the time comes, the user hears your announcement on the PC and "
            "gets a notification on their phone. Never say you can't set reminders.")
    items = list_for(ctx.owner) if ctx.owner else []
    if not items:
        return head + " This user has no pending reminders."
    lines = "\n".join(f"- [{r['id']}] {_fmt(r['due'])}, {_left(r['due'])}: {r['text']} ({r['kind']}"
                      f"{', repeats ' + r['repeat'] if r.get('repeat', 'none') != 'none' else ''})" for r in items[:30])
    return (head + f" To cancel or change one, call {CANCEL} with its id (and {SET} again for the new time). If the "
            "user asks how much time is left or when one goes off, answer with the time left shown here (it's "
            "already computed for right now, " + now.strftime("%H:%M:%S") + "), not with the duration they asked for. "
            f"Pending reminders of this user:\n{lines}")


def _when_from_conversation(ctx) -> dict:
    """{"in_minutes"} o {"at"} sacados de la conversación, o {}. Visto con
    gemma4: a "pon un temporizador de 7 minutos" llamaba set_reminder sin
    in_minutes ni at más o menos la mitad de las veces (y decía "listo"
    sin que quedara nada). Se le pide solo el cuándo, con salida JSON."""
    if not ctx.history or not (ctx.cfg or {}).get("base_model"):
        return {}
    from app.core.assistant_common import SERVER_KEEP_ALIVE, render_transcript, structured_request
    from app.core.assistant_engine import OLLAMA_URL

    schema = {"type": "object", "properties": {
        "in_minutes": {"type": "number"},
        "at": {"type": "string"},
    }, "required": ["in_minutes", "at"]}
    system = ("The user asked (last lines starting with USER) for a reminder, alarm or timer. Say WHEN it must go off. "
              "in_minutes: minutes from now, if they gave a duration (\"in 10 minutes\", \"a 2-hour timer\" = 120); "
              "otherwise 0. at: the exact local time \"HH:MM\" (24 h) or \"YYYY-MM-DD HH:MM\", if they gave a clock "
              f"time or a date; otherwise empty. Now it is {datetime.datetime.now():%Y-%m-%d %H:%M (%A)}. If they "
              "didn't say when, both empty/0.")
    data = structured_request(OLLAMA_URL, ctx.cfg["base_model"], [
        {"role": "system", "content": system},
        {"role": "user", "content": render_transcript(ctx.history, last=4)},
    ], schema, keep_alive=SERVER_KEEP_ALIVE, max_tokens=60) or {}
    out = {}
    try:
        if float(data.get("in_minutes") or 0) > 0:
            out["in_minutes"] = float(data["in_minutes"])
    except (TypeError, ValueError):
        pass
    if not out and str(data.get("at") or "").strip():
        out["at"] = str(data["at"]).strip()
    return out


def tools(ctx) -> list:
    langs = list((ctx.cfg or {}).get("languages") or []) or None
    lang_prop = {"type": "string", "description": "ISO 639-1 code of the language of the announcement (the user's language)."}
    if langs:
        lang_prop["enum"] = langs
    out = [{"type": "function", "function": {
        "name": SET,
        "description": ("Set a reminder, an alarm or a timer for the user: \"remind me in 10 minutes to take out "
                        "the pizza\", \"wake me up at 6\", \"set a 5-minute timer\", \"every day at 8 remind me "
                        "my pill\". Give the time either relative (in_minutes) or exact (at, local time)."),
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "What to remind, short, in the user's language (e.g. \"Take the pizza out of the oven\")."},
            "announcement": {"type": "string", "description": ("What you'll say out loud when the time comes, in your own "
                                                               "style and the user's language, one or two short sentences "
                                                               "(e.g. \"Samuel, it's been 10 minutes: take the pizza out!\").")},
            "kind": {"type": "string", "enum": list(KINDS), "description": "reminder, alarm (rings, e.g. to wake up) or timer (a countdown)."},
            "in_minutes": {"type": "number", "description": "Minutes from now (decimals allowed, 0.5 = 30 s). Leave empty if you use 'at'."},
            "at": {"type": "string", "description": "Exact local date and time, \"YYYY-MM-DD HH:MM\" (24 h), or just \"HH:MM\" for the next time it's that hour. Leave empty if you use in_minutes."},
            "repeat": {"type": "string", "enum": list(REPEATS), "description": "none, daily, weekdays (Mon-Fri) or weekly."},
            "language": lang_prop,
        }, "required": ["text", "announcement", "kind"]},
    }}]
    ids = [r["id"] for r in list_for(ctx.owner)] if ctx.owner else []
    if ids:
        out.append({"type": "function", "function": {
            "name": CANCEL,
            "description": "Cancel pending reminders, alarms or timers of the user (by id).",
            "parameters": {"type": "object", "properties": {
                "ids": {"type": "array", "items": {"type": "string", "enum": ids}},
            }, "required": ["ids"]},
        }})
    return out


def call(name: str, args: dict, ctx):
    if name == SET:
        text = re.sub(r"\s+", " ", str(args.get("text") or "")).strip()[:200]
        if not text:
            return "Say what to remind (text)."
        if args.get("in_minutes") in (None, "", 0, "0") and not str(args.get("at") or "").strip():
            args = {**args, **_when_from_conversation(ctx)}
        due, error = parse_when(args)
        if error:
            # Visto: con "Say when: …" a secas el modelo decía "listo, puse el
            # temporizador" sin que hubiera quedado nada.
            return f"NOT SET (nothing was saved): {error} Ask the user when; never say it was set."
        kind = args.get("kind") if args.get("kind") in KINDS else "reminder"
        repeat = args.get("repeat") if args.get("repeat") in REPEATS else "none"
        if repeat == "weekdays":  # de lunes a viernes: si cae en fin de semana, el lunes
            d = datetime.datetime.fromtimestamp(due)
            while d.weekday() >= 5:
                d += datetime.timedelta(days=1)
            due = d.timestamp()
        say =re.sub(r"\s+", " ", str(args.get("announcement") or "")).strip()[:300] or text
        langs = (ctx.cfg or {}).get("languages") or []
        lang = args.get("language") if isinstance(args.get("language"), str) and len(args["language"]) == 2 else None
        lang = lang or ctx.lang or (ctx.cfg or {}).get("language") or "es"
        if langs and lang not in langs:
            lang = (ctx.cfg or {}).get("language") or langs[0]
        try:
            r = add(ctx.owner, ctx.profile, text, say, kind, due, repeat, ctx.assistant, ctx.cfg or {}, lang)
        except ValueError as e:
            return f"Couldn't save it: {e}."
        ctx.emit({"type": "reminder", "action": "add", "reminder": public(r)})
        rep = "" if repeat == "none" else f", repeating {repeat}"
        return (f"Done: {kind} set for {_fmt(due)} ({_left(due)}{rep}): \"{text}\". Confirm it briefly, saying "
                "the time in a natural way.")
    if name == CANCEL:
        ids = args.get("ids")
        ids = [ids] if isinstance(ids, str) else ids if isinstance(ids, list) else []
        gone = []
        pending = {r["id"]: r for r in list_for(ctx.owner)}
        for rid in ids:
            if str(rid) in pending and cancel(ctx.owner, str(rid)):
                gone.append(pending[str(rid)]["text"])
                ctx.emit({"type": "reminder", "action": "remove", "id": str(rid)})
        if not gone:
            return "No pending reminder with those ids: nothing was cancelled."
        return f"Cancelled: {'; '.join(gone)}. Confirm it briefly."
    return None


# ── Planificador ───────────────────────────────────────────────────────

def start(on_fire) -> None:
    """Arranca el hilo que avisa los vencidos: on_fire(recordatorio)."""
    global _thread, _on_fire
    _on_fire = on_fire
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_run, name="reminders", daemon=True)
    _thread.start()


def _run() -> None:
    first = True
    while True:
        try:
            _tick(first)
        except Exception:  # noqa: BLE001 — el planificador no se cae por un aviso raro
            traceback.print_exc()
        first = False
        time.sleep(1.0)


def _tick(first: bool) -> None:
    now = time.time()
    fired = []
    with _lock:
        items = _load()
        changed = False
        for r in items:
            if r.get("state") != "pending" or r["due"] > now:
                continue
            missed = now - r["due"] > (MISSED_GRACE if first else 120)
            fired.append((dict(r), missed))
            if r.get("repeat", "none") != "none":
                r["due"] = _next_due(r["due"], r["repeat"])
                r["fired_at"] = now
            else:
                r["state"] = "missed" if missed else "done"
                r["fired_at"] = now
            changed = True
        if changed:
            done = [r for r in items if r.get("state") != "pending"]
            done.sort(key=lambda r: r.get("fired_at") or 0)
            old = {r["id"] for r in done[:-KEEP_DONE]} if len(done) > KEEP_DONE else set()
            _save([r for r in items if r["id"] not in old])
    for r, missed in fired:
        if _on_fire:
            try:
                _on_fire(r, missed)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
