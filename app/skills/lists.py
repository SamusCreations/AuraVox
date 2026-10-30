"""Listas y notas: la de compras, tareas, notas rápidas…

Cada perfil tiene las suyas (config/lists/<perfil>.json) y hay otras de la
casa, compartidas por todos (config/lists/home.json): "agrega leche a la
lista de compras de la casa". Se manejan por voz o por escrito con el
asistente (herramientas add_to_list, update_list_items, delete_list; el
modelo decide cuál y en qué lista, sin palabras clave) o desde la vista
"Listas" de la página.

El invitado solo usa las de la casa.
"""
import json
import os
import re
import secrets
import threading
import time

from app import paths

NAME = "lists"
MIN_ROLE = "guest"

LISTS_DIR = os.path.join(paths.CONFIG_DIR, "lists")
HOME = "home"
PROFILE_RE = re.compile(r"^p[0-9a-f]{8}$")
LIST_ID_RE = re.compile(r"^l[0-9a-f]{6}$")
ITEM_ID_RE = re.compile(r"^i[0-9a-f]{6}$")
MAX_LISTS = 40
MAX_ITEMS = 300
NAME_MAX = 60
ITEM_MAX = 1000
PROMPT_ITEMS = 25   # por lista, en el prompt
PROMPT_CHARS = 5000

ADD = "add_to_list"
UPDATE = "update_list_items"
DELETE = "delete_list"

_lock = threading.RLock()
# Lo fija el servidor: avisa a las páginas abiertas que una lista cambió
# (on_change(alcance), alcance = "home" o el id del perfil).
on_change = None


def _changed(scope: str) -> None:
    if on_change:
        try:
            on_change(scope)
        except Exception:  # noqa: BLE001
            pass


def _clean(text, limit: int) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"[\x00-\x09\x0b-\x1f\x7f]", " ", str(text or ""))).strip()[:limit]


def _path(scope: str) -> str:
    if scope != HOME and not PROFILE_RE.match(scope or ""):
        raise ValueError("lista inválida")
    return os.path.join(LISTS_DIR, f"{scope}.json")


def load(scope: str) -> list:
    with _lock:
        try:
            with open(_path(scope), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
    out = []
    for lst in (data.get("lists") if isinstance(data, dict) else None) or []:
        if isinstance(lst, dict) and LIST_ID_RE.match(str(lst.get("id"))) and lst.get("name"):
            lst["items"] = [i for i in lst.get("items") or [] if isinstance(i, dict) and ITEM_ID_RE.match(str(i.get("id")))]
            out.append(lst)
    return out


def _save(scope: str, lists: list) -> None:
    os.makedirs(LISTS_DIR, exist_ok=True)
    path = _path(scope)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"lists": lists}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _find(lists: list, name_or_id: str):
    key = str(name_or_id or "").strip().lower()
    return next((x for x in lists if x["id"] == name_or_id or x["name"].lower() == key), None)


def _new_list(name: str, kind: str = "list") -> dict:
    return {"id": "l" + secrets.token_hex(3), "name": name, "kind": kind if kind in ("list", "notes") else "list",
            "items": [], "updated": time.time()}


def _new_item(text: str, by: str = "") -> dict:
    return {"id": "i" + secrets.token_hex(3), "text": text, "done": False, "added": time.time(), "by": by}


def delete_owner(profile: str) -> None:
    with _lock:
        try:
            os.remove(_path(profile))
        except OSError:
            pass


# ── Cambios desde la página (PUT /api/lists/<alcance>) ─────────────────

def apply(scope: str, op: dict, by: str = "") -> list:
    """Una operación de la página: {"op": "create"|"rename"|"delete"|"add"|
    "toggle"|"edit"|"remove"|"clear_done", "list": id, "item": id, "text"}."""
    kind = op.get("op")
    with _lock:
        lists = load(scope)
        lst = next((x for x in lists if x["id"] == op.get("list")), None)
        if kind == "create":
            name = _clean(op.get("text"), NAME_MAX)
            if not name:
                raise ValueError("name")
            if _find(lists, name):
                raise FileExistsError(name)
            if len(lists) >= MAX_LISTS:
                raise OverflowError(MAX_LISTS)
            lists.append(_new_list(name, op.get("kind") or "list"))
        elif lst is None:
            raise KeyError(op.get("list"))
        elif kind == "rename":
            name = _clean(op.get("text"), NAME_MAX)
            if not name:
                raise ValueError("name")
            other = _find(lists, name)
            if other and other is not lst:
                raise FileExistsError(name)
            lst["name"] = name
        elif kind == "delete":
            lists.remove(lst)
        elif kind == "add":
            text = _clean(op.get("text"), ITEM_MAX)
            if not text:
                raise ValueError("item")
            if len(lst["items"]) >= MAX_ITEMS:
                raise OverflowError(MAX_ITEMS)
            lst["items"].append(_new_item(text, by))
        elif kind == "clear_done":
            lst["items"] = [i for i in lst["items"] if not i.get("done")]
        else:
            item = next((i for i in lst["items"] if i["id"] == op.get("item")), None)
            if item is None:
                raise KeyError(op.get("item"))
            if kind == "toggle":
                item["done"] = not item.get("done")
            elif kind == "edit":
                text = _clean(op.get("text"), ITEM_MAX)
                if text:
                    item["text"] = text
                else:
                    lst["items"].remove(item)
            elif kind == "remove":
                lst["items"].remove(item)
            else:
                raise ValueError("op")
        if lst is not None and lst in lists:
            lst["updated"] = time.time()
        _save(scope, lists)
    _changed(scope)
    return lists


# ── Habilidad ──────────────────────────────────────────────────────────

def _scopes(ctx) -> dict:
    """{"personal": perfil, "home": "home"} según quién pregunta."""
    out = {}
    if ctx.profile and not ctx.guest:
        out["personal"] = ctx.profile
    out["home"] = HOME
    return out


def context(ctx) -> str:
    scopes = _scopes(ctx)
    lines = []
    for scope_name, scope in scopes.items():
        for lst in load(scope):
            pending = [i for i in lst["items"] if not i.get("done")]
            done = len(lst["items"]) - len(pending)
            head = f"- {scope_name} list \"{lst['name']}\" ({lst.get('kind', 'list')}, {len(pending)} pending" + (f", {done} checked" if done else "") + ")"
            items = "; ".join(f"[{i['id']}] {i['text'][:200]}" for i in pending[:PROMPT_ITEMS])
            more = f" … and {len(pending) - PROMPT_ITEMS} more" if len(pending) > PROMPT_ITEMS else ""
            lines.append(head + (f": {items}{more}" if items else ""))
    who = ("personal lists (only this user) and home lists (shared by everyone in the house)" if "personal" in scopes
           else "home lists (shared by everyone in the house; this guest has no personal lists)")
    text = (f"LISTS AND NOTES: the user has {who}: shopping list, to-dos, quick notes… Manage them with {ADD} (it "
            f"creates the list if it doesn't exist), {UPDATE} (check off, uncheck, edit or remove items) and {DELETE}. "
            "If the user doesn't say whether it's theirs or the house's, use the existing list with that name; for "
            "a new one, personal unless it's clearly for the household (like the house shopping list). When they "
            "ask what's on a list, read it from here.")
    if not lines:
        return text + " There are no lists yet."
    body = "\n".join(lines)
    if len(body) > PROMPT_CHARS:
        body = body[:PROMPT_CHARS] + "\n…"
    return text + "\nCurrent lists:\n" + body


def tools(ctx) -> list:
    scopes = list(_scopes(ctx))
    names = sorted({lst["name"] for s in _scopes(ctx).values() for lst in load(s)})
    known = f" Existing lists: {', '.join(names)}." if names else ""
    scope_prop = {"type": "string", "enum": scopes, "description": "personal (only this user) or home (shared by the household)."}
    out = [{"type": "function", "function": {
        "name": ADD,
        "description": ("Add items to one of the user's lists (shopping, to-dos…) or save a quick note; the list is "
                        "created if it doesn't exist." + known),
        "parameters": {"type": "object", "properties": {
            "list": {"type": "string", "description": "List name, e.g. \"Compras\", \"Tareas\", \"Notas\" (in the user's language)."},
            "items": {"type": "array", "items": {"type": "string"}, "description": "One entry per item or note, short."},
            "scope": scope_prop,
            "notes": {"type": "boolean", "description": "true if it's a list of notes (free text) rather than items to check off."},
        }, "required": ["list", "items", "scope"]},
    }}]
    ids = [i["id"] for s in _scopes(ctx).values() for lst in load(s) for i in lst["items"]]
    if ids:
        out.append({"type": "function", "function": {
            "name": UPDATE,
            "description": "Check off, uncheck, edit or remove items of the user's lists (by id).",
            "parameters": {"type": "object", "properties": {
                "action": {"type": "string", "enum": ["check", "uncheck", "remove", "edit"]},
                "ids": {"type": "array", "items": {"type": "string", "enum": ids[:400]}},
                "new_text": {"type": "string", "description": "Only for edit: the new text."},
            }, "required": ["action", "ids"]},
        }})
    if names:
        out.append({"type": "function", "function": {
            "name": DELETE,
            "description": "Delete a whole list, or only its checked items, when the user asks for it.",
            "parameters": {"type": "object", "properties": {
                "list": {"type": "string", "enum": names},
                "scope": scope_prop,
                "only_checked": {"type": "boolean", "description": "true to remove only the checked items and keep the list."},
            }, "required": ["list", "scope"]},
        }})
    return out


def _scope_of(ctx, args, list_name=None) -> str:
    scopes = _scopes(ctx)
    wanted = args.get("scope")
    if wanted in scopes:
        return scopes[wanted]
    # Sin alcance claro: donde ya exista una lista con ese nombre.
    for scope in scopes.values():
        if list_name and _find(load(scope), list_name):
            return scope
    return scopes.get("personal") or HOME


def call(name: str, args: dict, ctx):
    by = (ctx.cfg or {}).get("label") or ctx.assistant or ""
    if name == ADD:
        list_name = _clean(args.get("list"), NAME_MAX) or "Notas"
        items = args.get("items")
        items = [items] if isinstance(items, str) else items if isinstance(items, list) else []
        items = [t for t in (_clean(x, ITEM_MAX) for x in items) if t]
        if not items:
            return "Nothing to add: items was empty."
        scope = _scope_of(ctx, args, list_name)
        with _lock:
            lists = load(scope)
            lst = _find(lists, list_name)
            created = lst is None
            if created:
                if len(lists) >= MAX_LISTS:
                    return f"Too many lists (max {MAX_LISTS}): ask the user to delete one."
                lst = _new_list(list_name, "notes" if args.get("notes") else "list")
                lists.append(lst)
            existing = {i["text"].lower() for i in lst["items"] if not i.get("done")}
            # Visto: a "ya compré la leche, márcala" el modelo la marcaba y en
            # la misma ronda la volvía a agregar. Lo marcado en este turno no
            # se vuelve a agregar.
            existing |= getattr(ctx, "lists_checked", set())
            fresh = [t for t in items if t.lower() not in existing]
            for t in fresh:
                lst["items"].append(_new_item(t, by))
            lst["items"] = lst["items"][-MAX_ITEMS:]
            lst["updated"] = time.time()
            _save(scope, lists)
        _changed(scope)
        ctx.emit({"type": "lists", "scope": "home" if scope == HOME else "personal", "list": lst["name"],
                  "added": fresh})
        where = "the house's" if scope == HOME else "the user's personal"
        dup = f" ({len(items) - len(fresh)} were already there)" if len(fresh) < len(items) else ""
        return (f"Done: added {len(fresh)} to {where} list \"{lst['name']}\"{' (new list)' if created else ''}{dup}. "
                f"It now has {sum(1 for i in lst['items'] if not i.get('done'))} pending. Confirm it briefly.")
    if name == UPDATE:
        action = args.get("action")
        ids = args.get("ids")
        ids = {ids} if isinstance(ids, str) else set(map(str, ids)) if isinstance(ids, list) else set()
        touched = []
        for scope in _scopes(ctx).values():
            with _lock:
                lists = load(scope)
                changed = False
                for lst in lists:
                    for item in list(lst["items"]):
                        if item["id"] not in ids:
                            continue
                        touched.append(item["text"])
                        changed = True
                        if action in ("check", "remove"):
                            ctx.lists_checked = getattr(ctx, "lists_checked", set()) | {item["text"].lower()}
                        if action == "check":
                            item["done"] = True
                        elif action == "uncheck":
                            item["done"] = False
                        elif action == "remove":
                            lst["items"].remove(item)
                        elif action == "edit" and _clean(args.get("new_text"), ITEM_MAX):
                            item["text"] = _clean(args.get("new_text"), ITEM_MAX)
                        lst["updated"] = time.time()
                if changed:
                    _save(scope, lists)
            if changed:
                _changed(scope)
        if not touched:
            return "No items with those ids: nothing changed."
        ctx.emit({"type": "lists", "changed": action})
        return f"Done ({action}): {'; '.join(touched)}. Confirm it briefly."
    if name == DELETE:
        list_name = str(args.get("list") or "")
        scope = _scope_of(ctx, args, list_name)
        with _lock:
            lists = load(scope)
            lst = _find(lists, list_name)
            if not lst:
                return f"There's no list called \"{list_name}\" there."
            if args.get("only_checked"):
                lst["items"] = [i for i in lst["items"] if not i.get("done")]
                msg = f"Removed the checked items of \"{lst['name']}\"."
            else:
                lists.remove(lst)
                msg = f"Deleted the list \"{lst['name']}\"."
            _save(scope, lists)
        _changed(scope)
        ctx.emit({"type": "lists", "changed": "delete"})
        return msg + " Confirm it briefly."
    return None
