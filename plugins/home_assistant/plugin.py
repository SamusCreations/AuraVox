"""Home Assistant: luces, enchufes, persianas, clima, escenas y sensores.

Usa la API REST de Home Assistant con un token de acceso de larga duración
(Ajustes → Plugins → Home Assistant). Herramientas:
- home_find: busca dispositivos/sensores por nombre o tipo y da su estado.
- home_control: enciende, apaga, alterna, abre/cierra, bloquea, cambia
  brillo/color/temperatura, activa una escena o un script.
El modelo ve en el prompt los nombres de lo que se puede manejar (así elige
el entity_id sin buscar), y si da un nombre en vez del id se busca el más
parecido. Las entidades de "exclude" nunca se tocan.
"""
import difflib
import re
import time
import unicodedata

import requests

from app.core import plugins
from app.webui.i18n import get_lang

PID = "home_assistant"
CONTROLLABLE = ("light", "switch", "fan", "cover", "climate", "media_player", "lock", "scene", "script", "input_boolean",
                "vacuum", "humidifier", "water_heater", "button", "siren", "valve")
SENSORS = ("sensor", "binary_sensor", "weather", "person", "device_tracker", "sun")
PROMPT_ENTITIES = 120
_cache = {"at": 0.0, "key": None, "states": []}

ACTIONS = ["turn_on", "turn_off", "toggle", "open", "close", "stop", "lock", "unlock", "set_brightness",
           "set_color", "set_temperature", "set_volume", "play", "pause", "next", "previous", "activate"]


def _cfg(s=None):
    s = s if s is not None else plugins.settings(PID)
    url = str(s.get("url") or "").strip().rstrip("/")
    return url, str(s.get("token") or "").strip(), {x.strip() for x in str(s.get("exclude") or "").split(",") if x.strip()}


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _states(force=False):
    url, token, _ex = _cfg()
    if not url or not token:
        raise RuntimeError("Home Assistant isn't set up yet (Settings → Plugins → Home Assistant: address and token).")
    key = (url, token)
    if not force and _cache["key"] == key and time.time() - _cache["at"] < 20:
        return _cache["states"]
    r = requests.get(f"{url}/api/states", headers=_headers(token), timeout=8)
    if r.status_code == 401:
        raise RuntimeError("Home Assistant rejected the token (401).")
    r.raise_for_status()
    states = [e for e in r.json() if isinstance(e, dict) and e.get("entity_id")]
    _cache.update(at=time.time(), key=key, states=states)
    return states


def _name(e):
    return str((e.get("attributes") or {}).get("friendly_name") or e["entity_id"])


def _norm(t):
    t = unicodedata.normalize("NFKD", str(t).lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _describe(e):
    a = e.get("attributes") or {}
    extra = []
    if a.get("unit_of_measurement"):
        extra.append(f"{e.get('state')} {a['unit_of_measurement']}")
    if "brightness" in a and a.get("brightness") is not None:
        extra.append(f"brightness {round(a['brightness'] * 100 / 255)}%")
    if a.get("current_temperature") is not None:
        extra.append(f"current {a['current_temperature']}°")
    if a.get("temperature") is not None and e["entity_id"].startswith("climate."):
        extra.append(f"target {a['temperature']}°")
    if a.get("current_position") is not None:
        extra.append(f"position {a['current_position']}%")
    state = e.get("state")
    return f"{e['entity_id']} \"{_name(e)}\": {state}" + (f" ({', '.join(extra)})" if extra else "")


def _domain(eid):
    return eid.split(".", 1)[0]


def _resolve(target, states, exclude):
    """El entity_id pedido, o el de nombre más parecido."""
    target = str(target or "").strip()
    ids = {e["entity_id"]: e for e in states}
    if target in ids:
        return ids[target]
    names = {_norm(_name(e)): e for e in states if e["entity_id"] not in exclude}
    hit = difflib.get_close_matches(_norm(target), list(names), n=1, cutoff=0.6)
    if hit:
        return names[hit[0]]
    parts = [p for p in re.findall(r"\w+", _norm(target)) if len(p) > 2]
    best = [e for k, e in names.items() if parts and all(p in k for p in parts)]
    return best[0] if len(best) == 1 else None


def context(ctx):
    url, token, exclude = _cfg()
    if not url or not token:
        return ""
    try:
        states = _states()
    except Exception:  # noqa: BLE001 — sin conexión, que lo diga la herramienta si la usan
        return ("HOME ASSISTANT: you can control the user's smart home with home_control and read sensors with "
                "home_find (it isn't reachable right now).")
    ctrl = [e for e in states if _domain(e["entity_id"]) in CONTROLLABLE and e["entity_id"] not in exclude]
    lines = "; ".join(f"{e['entity_id']} ({_name(e)}: {e.get('state')})" for e in ctrl[:PROMPT_ENTITIES])
    more = f" … and {len(ctrl) - PROMPT_ENTITIES} more (use home_find)" if len(ctrl) > PROMPT_ENTITIES else ""
    return ("HOME ASSISTANT: you control the user's smart home. To turn things on/off, open/close, change "
            "brightness, color or temperature, or activate scenes, call home_control with the entity_id; to read "
            "sensors (temperature, humidity, doors, presence, energy) or find a device, call home_find. For locks, "
            "alarms and garage doors, confirm with the user before acting. Devices you can control: "
            f"{lines}{more}")


def tools(ctx):
    url, token, _ex = _cfg()
    if not url or not token:
        return []
    return [
        {"type": "function", "function": {
            "name": "home_find",
            "description": "Find devices and sensors in the user's Home Assistant by name, room or type and get their current state (temperatures, doors, lights, presence…).",
            "parameters": {"type": "object", "properties": {
                "search": {"type": "string", "description": "Words of the name or room, e.g. \"kitchen\", \"temperatura salón\". Empty for all."},
                "domain": {"type": "string", "enum": ["", *CONTROLLABLE, *SENSORS], "description": "Type of entity, optional."},
            }, "required": []},
        }},
        {"type": "function", "function": {
            "name": "home_control",
            "description": "Control a device of the user's Home Assistant: lights, plugs, fans, blinds, thermostat, media players, locks, scenes and scripts.",
            "parameters": {"type": "object", "properties": {
                "entity_id": {"type": "string", "description": "The entity_id (e.g. light.living_room) or its name."},
                "action": {"type": "string", "enum": ACTIONS},
                "brightness_pct": {"type": "number", "description": "0-100, for set_brightness (or turn_on)."},
                "color": {"type": "string", "description": "Color name in English (red, warm white…), for set_color."},
                "temperature": {"type": "number", "description": "Target temperature, for set_temperature."},
                "volume_pct": {"type": "number", "description": "0-100, for set_volume."},
            }, "required": ["entity_id", "action"]},
        }},
    ]


def _service(eid, action, args):
    d = _domain(eid)
    data = {"entity_id": eid}
    if action in ("turn_on", "set_brightness", "set_color") and d == "light":
        if args.get("brightness_pct") is not None:
            data["brightness_pct"] = max(0, min(100, float(args["brightness_pct"])))
        if args.get("color"):
            name = str(args["color"]).lower().strip()
            if "warm" in name or "cálid" in name:
                data["color_temp_kelvin"] = 2700
            elif "cold" in name or "cool" in name or "fría" in name:
                data["color_temp_kelvin"] = 6000
            else:
                data["color_name"] = name.replace(" ", "")
        return d, "turn_on", data
    if action in ("turn_on", "turn_off", "toggle"):
        if d in ("scene", "script") and action == "turn_on":
            return d, "turn_on", data
        if d == "lock":
            return d, "unlock" if action == "turn_off" else "lock", data
        if d == "cover":
            return d, {"turn_on": "open_cover", "turn_off": "close_cover", "toggle": "toggle"}[action], data
        if d == "button":
            return d, "press", data
        return ("homeassistant" if d not in CONTROLLABLE else d), action, data
    if action in ("open", "close", "stop"):
        if d == "valve":
            return d, f"{action}_valve", data
        return "cover", f"{action}_cover", data
    if action in ("lock", "unlock"):
        return "lock", action, data
    if action == "activate":
        return (d if d in ("scene", "script") else "homeassistant"), "turn_on", data
    if action == "set_temperature":
        data["temperature"] = float(args.get("temperature"))
        return d if d in ("climate", "water_heater") else "climate", "set_temperature", data
    if action == "set_volume":
        data["volume_level"] = max(0, min(100, float(args.get("volume_pct") or 0))) / 100
        return "media_player", "volume_set", data
    if action in ("play", "pause", "next", "previous"):
        svc = {"play": "media_play", "pause": "media_pause", "next": "media_next_track", "previous": "media_previous_track"}[action]
        return "media_player", svc, data
    raise ValueError(action)


def call(name, args, ctx):
    if name not in ("home_find", "home_control"):
        return None
    url, token, exclude = _cfg()
    try:
        states = _states(force=name == "home_control")
    except Exception as e:  # noqa: BLE001
        return f"Couldn't reach Home Assistant: {e}"
    if name == "home_find":
        search = _norm(args.get("search") or "")
        domain = str(args.get("domain") or "")
        found = []
        for e in states:
            if domain and _domain(e["entity_id"]) != domain:
                continue
            if domain == "" and _domain(e["entity_id"]) not in CONTROLLABLE + SENSORS:
                continue
            text = _norm(f"{e['entity_id']} {_name(e)} {(e.get('attributes') or {}).get('device_class', '')}")
            if search and not all(w in text for w in re.findall(r"\w+", search)):
                continue
            found.append(e)
        if not found and search:
            hit = _resolve(args.get("search"), states, set())
            found = [hit] if hit else []
        if not found:
            return "Nothing in Home Assistant matches that."
        return "\n".join(_describe(e) for e in found[:60]) + (f"\n… and {len(found) - 60} more" if len(found) > 60 else "")
    e = _resolve(args.get("entity_id"), states, exclude)
    if not e:
        # ¿Es uno de los que no se tocan? (no están en la lista del prompt, así que el modelo inventa su id)
        blocked = [x for x in states if x["entity_id"] in exclude]
        hit = _resolve(args.get("entity_id"), blocked, set()) if blocked else None
        if not hit and blocked and _domain(str(args.get("entity_id") or "")) in {_domain(x["entity_id"]) for x in blocked}:
            hit = blocked[0] if len(blocked) == 1 else None
        if hit:
            return f"{_name(hit)} is on the list of devices AuraVox must not touch: tell the user they have to do it themselves."
        return f"There's no device called \"{args.get('entity_id')}\" in Home Assistant. Use home_find to look for it."
    if e["entity_id"] in exclude:
        return f"{_name(e)} is on the list of devices AuraVox must not touch: tell the user."
    try:
        domain, service, data = _service(e["entity_id"], str(args.get("action") or ""), args)
    except (ValueError, TypeError):
        return f"The action {args.get('action')} doesn't apply to {e['entity_id']} or a value is missing."
    r = requests.post(f"{url}/api/services/{domain}/{service}", headers=_headers(token), json=data, timeout=10)
    if r.status_code >= 400:
        return f"Home Assistant refused it ({r.status_code}): {r.text[:200]}"
    _cache["at"] = 0
    time.sleep(0.6)
    try:
        now = next((x for x in _states(force=True) if x["entity_id"] == e["entity_id"]), e)
    except Exception:  # noqa: BLE001
        now = e
    return f"Done: {domain}.{service} on {_name(e)}. Now: {_describe(now)}. Confirm it briefly."


_MSG = {
    "es": {"missing": "Falta la dirección o el token.", "unreachable": "No pude conectar con {url}: {e}",
           "token": "Home Assistant rechazó el token (401).", "status": "Home Assistant respondió {code}.",
           "ok": "Conectado: {n} entidades."},
    "en": {"missing": "The address or the token is missing.", "unreachable": "Couldn't connect to {url}: {e}",
           "token": "Home Assistant rejected the token (401).", "status": "Home Assistant answered {code}.",
           "ok": "Connected: {n} entities."},
}


def _m(key, **kw):
    return _MSG.get(get_lang(), _MSG["es"])[key].format(**kw)


def check(settings):
    url, token, _ex = _cfg(settings)
    if not url or not token:
        return False, _m("missing")
    try:
        r = requests.get(f"{url}/api/", headers=_headers(token), timeout=6)
    except requests.exceptions.RequestException as e:
        return False, _m("unreachable", url=url, e=e)
    if r.status_code == 401:
        return False, _m("token")
    if not r.ok:
        return False, _m("status", code=r.status_code)
    _cache["at"] = 0
    try:
        n = len(_states(force=True))
    except Exception:  # noqa: BLE001
        n = 0
    return True, _m("ok", n=n)