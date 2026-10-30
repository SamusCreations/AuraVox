"""Memoria a largo plazo de cada perfil.

El asistente guarda hechos que el usuario le cuenta de sí mismo ("mi hija
se llama Ana", "soy vegetariano") con la herramienta remember_fact y los
olvida con forget_fact ("olvida eso", "ya no soy vegetariano"). Lo decide
el modelo, sin palabras clave. Los hechos van al system prompt de todos
los asistentes de ese perfil, y el perfil los ve, edita y borra en Ajustes
→ "Lo que recuerdan de ti".

Se guarda en config/memory/<perfil>.json. El invitado la tiene en su
navegador (sessionStorage): la página la manda con cada pregunta y aplica
los cambios que le avisa el servidor (eventos "memory").

Con muchos hechos (más de PROMPT_FACTS) no entran todos en el prompt: si
está instalado nomic-embed-text se eligen los más parecidos a lo que se
habla (más los últimos guardados); si no, los más recientes.
"""
import json
import os
import re
import secrets
import threading
import time

from app import paths
from app.core import embeddings

NAME = "memory"
MIN_ROLE = "guest"

MEMORY_DIR = os.path.join(paths.CONFIG_DIR, "memory")
MAX_FACTS = 300
FACT_MAX = 300
PROMPT_FACTS = 40     # cuántos van al prompt como mucho
RECENT_ALWAYS = 8     # los últimos guardados van siempre
ID_RE = re.compile(r"^m[0-9a-f]{6}$")
PROFILE_RE = re.compile(r"^p[0-9a-f]{8}$")

REMEMBER = "remember_fact"
FORGET = "forget_fact"

_lock = threading.RLock()


# ── Archivo ────────────────────────────────────────────────────────────

def _path(profile: str) -> str:
    if not PROFILE_RE.match(profile or ""):
        raise ValueError("perfil inválido")
    return os.path.join(MEMORY_DIR, f"{profile}.json")


def clean_text(text) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", str(text or ""))).strip()[:FACT_MAX]


def load(profile: str) -> list:
    """Hechos del perfil: [{"id", "text", "created", "assistant"}], del más viejo al más nuevo."""
    with _lock:
        try:
            with open(_path(profile), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
    facts = data.get("facts") if isinstance(data, dict) else None
    return [f for f in facts or [] if isinstance(f, dict) and ID_RE.match(str(f.get("id"))) and f.get("text")]


def _save(profile: str, facts: list) -> None:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    path = _path(profile)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"facts": facts[-MAX_FACTS:]}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def public(facts: list) -> list:
    return [{"id": f["id"], "text": f["text"], "created": f.get("created"), "assistant": f.get("assistant", "")}
            for f in facts]


def add(profile: str, text: str, assistant: str = "") -> dict:
    text = clean_text(text)
    if not text:
        raise ValueError("vacío")
    with _lock:
        facts = load(profile)
        same = next((f for f in facts if f["text"].lower() == text.lower()), None)
        if same:
            return same
        fact = {"id": "m" + secrets.token_hex(3), "text": text, "created": time.time(), "assistant": assistant}
        facts.append(fact)
        _save(profile, facts)
        return fact


def edit(profile: str, fid: str, text: str) -> dict:
    text = clean_text(text)
    with _lock:
        facts = load(profile)
        fact = next((f for f in facts if f["id"] == fid), None)
        if not fact:
            raise KeyError(fid)
        if not text:
            facts.remove(fact)
        else:
            fact["text"] = text
            fact.pop("emb", None)
        _save(profile, facts)
        return fact


def remove(profile: str, fid: str) -> bool:
    with _lock:
        facts = load(profile)
        left = [f for f in facts if f["id"] != fid]
        if len(left) == len(facts):
            return False
        _save(profile, left)
        return True


def clear(profile: str) -> None:
    with _lock:
        try:
            os.remove(_path(profile))
        except OSError:
            pass


def delete_profile(profile: str) -> None:
    clear(profile)


# ── Qué hechos van al prompt ───────────────────────────────────────────

def _guest_facts(ctx) -> list:
    out = []
    for f in (ctx.guest_data.get("memory") or [])[:MAX_FACTS]:
        if isinstance(f, dict) and ID_RE.match(str(f.get("id"))) and clean_text(f.get("text")):
            out.append({"id": f["id"], "text": clean_text(f["text"])})
    return out


def facts_for(ctx) -> list:
    if ctx.guest:
        return _guest_facts(ctx)
    return load(ctx.profile) if ctx.profile else []


def _relevant(ctx, facts: list) -> list:
    if len(facts) <= PROMPT_FACTS:
        return facts
    recent = facts[-RECENT_ALWAYS:]
    rest = facts[:-RECENT_ALWAYS]
    query = " ".join(str(m.get("content", ""))[:400] for m in ctx.history[-3:] if m.get("role") == "user")
    picked = None
    if query and embeddings.available():
        missing = [f for f in rest if not isinstance(f.get("emb"), list)]
        if missing:
            vecs = embeddings.embed([f["text"] for f in missing])
            if vecs:
                for f, v in zip(missing, vecs):
                    f["emb"] = v
                if not ctx.guest and ctx.profile:
                    with _lock:  # se guardan para no volver a calcularlos
                        stored = {f["id"]: f for f in load(ctx.profile)}
                        for f in missing:
                            if f["id"] in stored:
                                stored[f["id"]]["emb"] = f["emb"]
                        _save(ctx.profile, list(stored.values()))
        qv = embeddings.embed([query], "query")
        if qv and all(isinstance(f.get("emb"), list) for f in rest):
            ranked = sorted(rest, key=lambda f: embeddings.cosine(qv[0], f["emb"]), reverse=True)
            picked = ranked[:PROMPT_FACTS - RECENT_ALWAYS]
    if picked is None:
        picked = rest[-(PROMPT_FACTS - RECENT_ALWAYS):]
    keep = {f["id"] for f in picked + recent}
    return [f for f in facts if f["id"] in keep]


def context(ctx) -> str:
    facts = _relevant(ctx, facts_for(ctx))
    rules = (
        "LONG-TERM MEMORY: you can remember lasting facts about the user across conversations. When the user tells "
        f"you something lasting about themselves or their life (family, names of people or pets, diet, allergies, "
        "health, work, tastes, important dates, how they like to be treated) or asks you to remember something, "
        f"call {REMEMBER} with a short, self-contained fact in the third person (e.g. \"Their daughter is called "
        "Ana\"), in the user's language, and keep talking naturally. Don't save one-off requests, questions, "
        "small talk or things already saved. "
    )
    if not facts:
        return rules + "You don't remember anything about this user yet."
    lines = "\n".join(f"- [{f['id']}] {f['text']}" for f in facts)
    return (rules + f"If they ask you to forget something, or a saved fact is no longer true, call {FORGET} with its "
            "id (and save the new fact if there is one). Use these facts naturally when they're relevant, without "
            "reciting them or mentioning the ids; if they ask what you remember about them, tell them.\n"
            f"What you remember about the user:\n{lines}")


# ── Herramientas ───────────────────────────────────────────────────────

def tools(ctx) -> list:
    out = [{"type": "function", "function": {
        "name": REMEMBER,
        "description": ("Save a lasting fact about the user in long-term memory, so every assistant remembers it in "
                        "future conversations (family, diet, tastes, important dates, things they ask you to remember)."),
        "parameters": {"type": "object", "properties": {
            "fact": {"type": "string", "description": "The fact, short and self-contained, in the third person and in the user's language."},
        }, "required": ["fact"]},
    }}]
    ids = [f["id"] for f in facts_for(ctx)]
    if ids:
        out.append({"type": "function", "function": {
            "name": FORGET,
            "description": "Forget facts saved in long-term memory, when the user asks you to forget them or they're no longer true.",
            "parameters": {"type": "object", "properties": {
                "ids": {"type": "array", "items": {"type": "string", "enum": ids}, "description": "Ids of the facts to forget."},
            }, "required": ["ids"]},
        }})
    return out


def call(name: str, args: dict, ctx):
    if name == REMEMBER:
        text = clean_text(args.get("fact"))
        if not text:
            return "Nothing to save: the fact was empty."
        if ctx.guest:
            fact = {"id": "m" + secrets.token_hex(3), "text": text, "created": time.time()}
            ctx.guest_data.setdefault("memory", []).append(fact)
            ctx.emit({"type": "memory", "action": "add", "fact": fact})
        else:
            fact = add(ctx.profile, text, ctx.assistant)
            ctx.emit({"type": "memory", "action": "add", "fact": public([fact])[0]})
        return (f'Saved in long-term memory: "{text}". Just acknowledge it naturally in a few words (no need to '
                "mention the memory or how it works) and go on with the conversation.")
    if name == FORGET:
        ids = args.get("ids")
        ids = [ids] if isinstance(ids, str) else ids if isinstance(ids, list) else []
        facts = {f["id"]: f for f in facts_for(ctx)}
        gone = []
        for fid in ids:
            fid = str(fid)
            if fid not in facts:
                continue
            if ctx.guest:
                ctx.guest_data["memory"] = [f for f in ctx.guest_data.get("memory") or [] if f.get("id") != fid]
            else:
                remove(ctx.profile, fid)
            ctx.emit({"type": "memory", "action": "remove", "id": fid})
            gone.append(facts[fid]["text"])
        if not gone:
            return "None of those facts were in memory: nothing was forgotten."
        return (f"Forgotten: {'; '.join(gone)}. Confirm briefly that you forgot it, without repeating it word for "
                "word.")
    return None
