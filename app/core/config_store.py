"""
Lectura/escritura de assistants.yaml (y de los alias/exclusiones de
wake_words.txt) para la interfaz web (config_ui.py).

assistants.yaml se escribe con un formato fijo propio en vez de
yaml.safe_dump, para que siga siendo cómodo de editar a mano y para
conservar los comentarios de ayuda: el bloque de comentarios que precede a
cada clave de nivel superior (el encabezado del archivo, el de
user_context...) se copia tal cual. Antes de escribir, el resultado se
vuelve a leer con yaml.safe_load y se compara contra lo que se quería
guardar; si no coincide, no se toca el archivo. Siempre queda una copia
del archivo anterior en assistants.yaml.bak.
"""
import hashlib
import json
import math
import os
import re
import threading

import yaml

from app.core.assistant_common import (
    NON_ASSISTANT_KEYS,
    VALID_VOICE_CODES,
    _INT_DEFAULTS,
    _NUMERIC_DEFAULTS,
    _TEXT_DEFAULTS,
    is_valid_voice,
    normalize_voice,
    parse_bool,
    parse_language_list,
    pipeline_languages,
)
from app.paths import ASSISTANTS_YAML as CONFIG_PATH
from app.voice import wake_word_utils as ww
from app.voice.push_to_talk import normalize_key
from app.webui.i18n import tr

NAME_RE = re.compile(r"^[a-z][a-z0-9]{1,29}$")
COLOR_RE = re.compile(r"^#[0-9a-f]{6}$")
RESERVED_NAMES = set(NON_ASSISTANT_KEYS) | {ww.EXCLUDE_SECTION}
KNOWN_FIELDS = {
    "label", "base_model", "voice", "speed", "language", "languages", "temperature",
    "top_k", "top_p", "max_history", "max_tool_rounds", "search_announcement",
    "fallback_message", "personality", "wake_word", "push_to_talk_key", "color", "think_pause",
    "owner", "shared", "expressiveness", "phrases",
}
EXPRESSIVENESS_LEVELS = ("none", "some", "lots")
DEFAULT_EXPRESSIVENESS = "lots"


def _phrases(value, legacy_search=None, legacy_fallback=None) -> dict:
    """{kind: {"mode": "auto"|"fixed", "fixed": [...]}} (ver app/core/phrases.py).
    Sin `phrases` (asistentes de antes), las frases propias de
    search_announcement / fallback_message pasan a su lista fija."""
    from app.core import phrases as ph

    raw = value if isinstance(value, dict) else {}
    out = {}
    for kind in ph.KINDS:
        s = raw.get(kind) if isinstance(raw.get(kind), dict) else {}
        mode = s.get("mode") if s.get("mode") in ph.MODES else "auto"
        fixed = ph.clean_list(s.get("fixed"))
        if not isinstance(value, dict):
            legacy = {"search": legacy_search, "fallback": legacy_fallback}.get(kind)
            legacy = _clean_line(legacy)
            if legacy and legacy != _TEXT_DEFAULTS.get(f"{kind}_announcement" if kind == "search" else "fallback_message"):
                fixed = [legacy]
        out[kind] = {"mode": mode, "fixed": fixed}
    return out


def _expressiveness(value) -> str:
    value = str(value or "").strip().lower()
    return value if value in EXPRESSIVENESS_LEVELS else DEFAULT_EXPRESSIVENESS
# De quién es cada asistente (perfil que lo creó, ver webui/profiles.py) y si
# lo ven los demás perfiles. Sin `owner` (los de antes de los perfiles o
# escritos a mano) es de los administradores; sin `shared`, compartido.
OWNER_RE = re.compile(r"^p[0-9a-f]{8}$")
USER_TEXT_FIELDS = {"nombre": 80, "pais": 80, "ubicacion": 200}
MAX_LEN = {"label": 40, "base_model": 200, "search_announcement": 300, "fallback_message": 300}
MAX_LONG_TEXT = 20000

_LOCK = threading.RLock()
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f﻿]")
_TOP_KEY_RE = re.compile(r"^([^\s#][^:]*?)\s*:(\s|$)")


class ConfigError(Exception):
    def __init__(self, message: str, fields: dict = None, status: int = 400):
        super().__init__(message)
        self.message = message
        self.fields = fields or {}
        self.status = status


# ── Normalización ──────────────────────────────────────────────────────

def _clean_line(value) -> str:
    if value is None:
        return ""
    return _CONTROL_RE.sub("", str(value).replace("\t", " ")).replace("\n", " ").replace("\r", " ").strip()


def _clean_multiline(value) -> str:
    """Igual que lo que ve assistant_common (un .strip() del texto), más
    quitar espacios al final de cada línea y caracteres de control: así lo
    que se escribe como bloque `|` se relee exactamente igual."""
    if value is None:
        return ""
    text = _CONTROL_RE.sub("", str(value).replace("\r\n", "\n").replace("\r", "\n"))
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def _color(value) -> str:
    """Color del asistente en la interfaz (el aro del modo voz, su orbe):
    "#rrggbb" en minúsculas, o "" = automático (sale de su nombre)."""
    v = _clean_line(value).lower()
    return v if COLOR_RE.match(v) else ""


def _owner(value) -> str:
    v = _clean_line(value)
    return v if OWNER_RE.match(v) else ""


def _coerce(value, default, lo, hi, cast):
    try:
        v = cast(value)
        if isinstance(v, float):
            if not math.isfinite(v):
                raise ValueError
            v = round(v, 4)
        if lo <= v <= hi:
            return v
    except (TypeError, ValueError):
        pass
    return default


def assistant_view(name: str, section) -> dict:
    """Sección de un asistente tal como la usa el resto del proyecto
    (mismos valores por defecto que load_assistants_config), sin fallar
    ante datos inválidos. Los campos desconocidos se conservan en
    `_extra` para no perderlos al reescribir el archivo."""
    s = section if isinstance(section, dict) else {}
    label = _clean_line(s.get("label"))
    voice = normalize_voice(_clean_line(s.get("voice") or "M5"))
    out = {
        "name": name,
        "label": "" if label == name.upper() else label,
        "base_model": _clean_line(s.get("base_model")),
        "voice": voice if is_valid_voice(voice) else "M5",
        "language": (_clean_line(s.get("language")) or "es").lower(),
        "languages": parse_language_list(s.get("languages")),
        "personality": _clean_multiline(s.get("personality")),
        "wake_word": parse_bool(s.get("wake_word"), True),
        "push_to_talk_key": normalize_key(s.get("push_to_talk_key")),
        "color": _color(s.get("color")),
        "expressiveness": _expressiveness(s.get("expressiveness")),
        "phrases": _phrases(s.get("phrases"), s.get("search_announcement"), s.get("fallback_message")),
        "owner": _owner(s.get("owner")),
        "shared": parse_bool(s.get("shared"), True),
    }
    for key, (default, lo, hi) in _NUMERIC_DEFAULTS.items():
        out[key] = _coerce(s.get(key, default), default, lo, hi, float)
    for key, (default, lo, hi) in _INT_DEFAULTS.items():
        out[key] = _coerce(s.get(key, default), default, lo, hi, int)
    for key, default in _TEXT_DEFAULTS.items():
        out[key] = _clean_line(s.get(key)) or default
    extra = {k: v for k, v in s.items() if k not in KNOWN_FIELDS}
    if extra:
        out["_extra"] = extra
    return out


def user_view(section) -> dict:
    s = section if isinstance(section, dict) else {}
    out = {key: _clean_line(s.get(key)) for key in USER_TEXT_FIELDS}
    for key, limit in (("latitud", 90), ("longitud", 180)):
        try:
            v = float(s.get(key))
            out[key] = round(v, 7) if math.isfinite(v) and -limit <= v <= limit else None
        except (TypeError, ValueError):
            out[key] = None
    extra = {k: v for k, v in s.items() if k not in out}
    if extra:
        out["_extra"] = extra
    return out


def _public(view: dict) -> dict:
    return {k: v for k, v in view.items() if k != "_extra"}


# ── Validación estricta (lo que llega desde la interfaz) ───────────────

def validate_assistant(data: dict, taken_names: set, languages: list, taken_keys: dict = None):
    """Devuelve (asistente_limpio, alias, exclusiones_a_agregar, errores).
    A diferencia de assistant_view, aquí un valor inválido es un error que
    se le muestra al usuario, no se reemplaza en silencio.
    `taken_keys`: {tecla: nombre} de push to talk de los OTROS asistentes."""
    errors = {}
    name = str(data.get("name") or "").strip().lower()
    if not NAME_RE.match(name):
        errors["name"] = tr("name_format")
    elif name in RESERVED_NAMES:
        errors["name"] = tr("name_reserved", name=name)
    elif name in taken_names:
        errors["name"] = tr("name_taken", name=name)

    out = {"name": name}

    label = _clean_line(data.get("label"))
    if len(label) > MAX_LEN["label"]:
        errors["label"] = tr("max_chars", n=MAX_LEN["label"])
    out["label"] = "" if label == name.upper() else label

    base_model = _clean_line(data.get("base_model"))
    if not base_model:
        errors["base_model"] = tr("model_required")
    elif re.search(r"\s", base_model) or len(base_model) > MAX_LEN["base_model"]:
        errors["base_model"] = tr("model_invalid")
    out["base_model"] = base_model
    out["expressiveness"] = _expressiveness(data.get("expressiveness"))
    out["phrases"] = _phrases(data.get("phrases"), data.get("search_announcement"), data.get("fallback_message"))

    voice = normalize_voice(_clean_line(data.get("voice")))
    if not is_valid_voice(voice):
        errors["voice"] = tr("voice_invalid")
    out["voice"] = voice

    raw_color = _clean_line(data.get("color"))
    out["color"] = _color(raw_color)
    if raw_color and not out["color"]:
        errors["color"] = tr("color_invalid")

    for key, (_default, lo, hi) in _NUMERIC_DEFAULTS.items():
        try:
            v = float(data.get(key))
            if not (math.isfinite(v) and lo <= v <= hi):
                raise ValueError
            out[key] = round(v, 4)
        except (TypeError, ValueError):
            errors[key] = tr("number_range", lo=lo, hi=hi)
    for key, (_default, lo, hi) in _INT_DEFAULTS.items():
        try:
            v = float(data.get(key))
            if not (v.is_integer() and lo <= v <= hi):
                raise ValueError
            out[key] = int(v)
        except (TypeError, ValueError):
            errors[key] = tr("int_range", lo=lo, hi=hi)

    langs = parse_language_list(data.get("languages"))
    unknown = [code for code in langs if code not in languages]
    if unknown:
        errors["languages"] = tr("langs_unsupported", codes=", ".join(unknown))
    if not langs:
        langs = sorted(languages)  # todos: se escriben uno por uno, así en el archivo se ve cuáles son
    out["languages"] = langs

    language = _clean_line(data.get("language")).lower()
    if language not in languages:
        errors["language"] = tr("lang_invalid")
    elif langs and language not in langs:
        errors["language"] = tr("lang_not_enabled")
    out["language"] = language

    for key, default in _TEXT_DEFAULTS.items():
        value = _clean_line(data.get(key))
        if len(value) > MAX_LEN[key]:
            errors[key] = tr("max_chars", n=MAX_LEN[key])
        out[key] = value or default

    personality = _clean_multiline(data.get("personality"))
    if not personality:
        errors["personality"] = tr("personality_required")
    elif len(personality) > MAX_LONG_TEXT:
        errors["personality"] = tr("max_chars", n=MAX_LONG_TEXT)
    out["personality"] = personality

    out["wake_word"] = parse_bool(data.get("wake_word"), True)
    out["shared"] = parse_bool(data.get("shared"), True)
    out["owner"] = ""  # lo pone save_assistant (quién lo creó), nunca la página
    raw_key = str(data.get("push_to_talk_key") or "").strip()
    key = normalize_key(raw_key)
    if raw_key and not key:
        errors["push_to_talk_key"] = tr("ptt_key_invalid", key=raw_key)
    elif key and key in (taken_keys or {}):
        errors["push_to_talk_key"] = tr("ptt_key_taken", key=key, other=taken_keys[key].upper())
    out["push_to_talk_key"] = key
    if not out["wake_word"] and not raw_key:
        errors["wake_word"] = tr("activation_required")

    aliases, bad = [], []
    for raw in data.get("aliases") or []:
        word = ww.clean_word(raw)
        if not word:
            bad.append(str(raw))
        elif word != name and word not in aliases:
            aliases.append(word)
    if bad:
        errors["aliases"] = tr("one_word_alias", words=", ".join(bad))

    add_exclusions = [w for w in (ww.clean_word(x) for x in data.get("add_exclusions") or []) if w]
    return out, aliases, add_exclusions, errors


def validate_user_context(data: dict, errors: dict) -> dict:
    out = {}
    for key, limit in USER_TEXT_FIELDS.items():
        value = _clean_line(data.get(key))
        if len(value) > limit:
            errors[f"user_context.{key}"] = tr("max_chars", n=limit)
        out[key] = value
    for key, limit in (("latitud", 90), ("longitud", 180)):
        raw = data.get(key)
        if raw in (None, ""):
            out[key] = None
            continue
        try:
            v = float(str(raw).replace(",", "."))
            if not (math.isfinite(v) and -limit <= v <= limit):
                raise ValueError
            out[key] = round(v, 7)
        except ValueError:
            out[key] = None
            errors[f"user_context.{key}"] = tr("coord_range", limit=limit)
    if not errors and (out["latitud"] is None) != (out["longitud"] is None):
        errors["user_context.longitud"] = tr("coords_together")
    return out


# ── Escritura de assistants.yaml ───────────────────────────────────────

def _q(value: str) -> str:
    # Un string JSON es un escalar YAML entre comillas dobles válido.
    return json.dumps(value, ensure_ascii=False)


_YAML11_BOOLS = {"y", "n", "yes", "no", "on", "off", "true", "false"}


def _code(value: str) -> str:
    """Códigos de idioma sin comillas ("es", como estaba escrito el
    archivo) salvo que YAML pueda leerlos como otra cosa ("no" = False)."""
    return value if re.fullmatch(r"[a-z]{2,3}", value) and value not in _YAML11_BOOLS else _q(value)


def _num(value) -> str:
    return str(value) if isinstance(value, int) else repr(float(value))


def _block(key: str, text: str, indent: int) -> list:
    pad = " " * indent
    if not text:
        return [f'{pad}{key}: ""']
    lines = [f"{pad}{key}: |"]
    lines += [f"{pad}  {line}" if line else "" for line in text.split("\n")]
    return lines


def _dump_extra(extra: dict, indent: int) -> list:
    if not extra:
        return []
    dumped = yaml.safe_dump(extra, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return [(" " * indent + line) if line else "" for line in dumped.rstrip("\n").split("\n")]


def _emit_assistant(a: dict) -> list:
    lines = [f"{a['name']}:", f"  base_model: {_q(a['base_model'])}"]
    if a["label"]:
        lines.append(f"  label: {_q(a['label'])}")
    if a["color"]:
        lines.append(f"  color: {_q(a['color'])}")
    if a.get("owner"):
        lines.append(f"  owner: {_q(a['owner'])}")
    lines.append(f"  shared: {'true' if a.get('shared', True) else 'false'}")
    lines.append(f"  expressiveness: {_expressiveness(a.get('expressiveness'))}")
    # Un objeto JSON es un mapeo YAML válido (en una línea por tipo).
    phrases = a.get("phrases") or _phrases(None)
    lines.append("  phrases:")
    lines += [f"    {kind}: {json.dumps(phrases[kind], ensure_ascii=False)}" for kind in phrases]
    lines += [
        f"  voice: {a['voice']}",
        f"  speed: {_num(a['speed'])}",
        f"  language: {_code(a['language'])}",
        f"  languages: [{', '.join(_code(c) for c in a['languages'])}]",
    ]
    for key in ("temperature", "top_k", "top_p", "max_history", "max_tool_rounds", "think_pause"):
        lines.append(f"  {key}: {_num(a[key])}")
    for key in _TEXT_DEFAULTS:
        lines.append(f"  {key}: {_q(a[key])}")
    lines += [
        f"  wake_word: {'true' if a['wake_word'] else 'false'}",
        f"  push_to_talk_key: {_q(a['push_to_talk_key'])}",
    ]
    lines += _dump_extra(a.get("_extra"), 2)
    lines += _block("personality", a["personality"], 2)
    return lines


def _emit_user_context(uc: dict) -> list:
    lines = ["user_context:"]
    for key in USER_TEXT_FIELDS:
        lines.append(f"  {key}: {_q(uc[key])}" if uc.get(key) else f'  # {key}: ""')
    for key in ("latitud", "longitud"):
        lines.append(f"  {key}: {_num(uc[key])}" if uc.get(key) is not None else f"  # {key}:")
    lines += _dump_extra(uc.get("_extra"), 2)
    return lines


def _comment_blocks(text: str):
    """{clave_de_nivel_superior: [líneas de comentario/blancas previas]} y
    los comentarios del final del archivo."""
    blocks, pending = {}, []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            pending.append(line.rstrip())
            continue
        m = _TOP_KEY_RE.match(line)
        if m:
            blocks[m.group(1).strip()] = pending
        pending = []
    return blocks, pending


def render_config(user_context: dict, shared_context: str, assistants: list, original_text: str, renames: dict = None) -> str:
    blocks, trailer = _comment_blocks(original_text)
    for old, new in (renames or {}).items():
        if old in blocks:
            blocks[new] = blocks.pop(old)

    sections = [
        ("user_context", _emit_user_context(user_context)),
        ("shared_context", _block("shared_context", shared_context, 0)),
    ] + [(a["name"], _emit_assistant(a)) for a in assistants]

    out = []
    for key, body in sections:
        comments = blocks.get(key)
        if comments is None:
            comments = [""] if out else []
        out += comments + body
    if any(line.strip() for line in trailer):
        out += [""] + trailer
    return "\n".join(out).rstrip("\n") + "\n"


def _check_roundtrip(text: str, user_context: dict, shared_context: str, assistants: list) -> None:
    try:
        parsed = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise ConfigError(tr("yaml_invalid", error=e), status=500)
    names = [k for k in parsed if k not in NON_ASSISTANT_KEYS]
    ok = (
        names == [a["name"] for a in assistants]
        and user_view(parsed.get("user_context")) == user_context
        and _clean_multiline(parsed.get("shared_context")) == shared_context
        and all(assistant_view(a["name"], parsed[a["name"]]) == a for a in assistants)
    )
    if not ok:
        raise ConfigError(tr("yaml_mismatch"), status=500)


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _write_config(new_text: str, original_text: str) -> None:
    raw_original = b""
    try:
        with open(CONFIG_PATH, "rb") as f:
            raw_original = f.read()
    except FileNotFoundError:
        pass
    newline = "\r\n" if b"\r\n" in raw_original else "\n"
    if raw_original:
        with open(CONFIG_PATH + ".bak", "wb") as f:
            f.write(raw_original)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline=newline) as f:
        f.write(new_text)
    os.replace(tmp, CONFIG_PATH)


# ── Estado y operaciones (lo que usa config_ui.py) ─────────────────────

def _version(config_text: str, wake_text: str) -> str:
    return hashlib.sha1((config_text + "\0" + wake_text).encode("utf-8")).hexdigest()[:16]


def _snapshot():
    config_text = _read_text(CONFIG_PATH)
    wake_text = _read_text(ww.WAKE_WORDS_PATH)
    try:
        raw = yaml.safe_load(config_text) or {}
    except yaml.YAMLError as e:
        raise ConfigError(tr("yaml_syntax", error=e), status=500)
    if not isinstance(raw, dict):
        raise ConfigError(tr("yaml_format"), status=500)
    names = [k for k in raw if k not in NON_ASSISTANT_KEYS]
    return config_text, _version(config_text, wake_text), raw, names


def _check_version(current: str, expected) -> None:
    if expected and expected != current:
        raise ConfigError(tr("conflict"), status=409)


def load_state() -> dict:
    with _LOCK:
        _text, version, raw, names = _snapshot()
        _header, sections = ww.read_wake_file()
        assistants = []
        for name in names:
            view = _public(assistant_view(name, raw[name]))
            view["aliases"] = list(sections.get(name, []))
            assistants.append(view)
        return {
            "version": version,
            "assistants": assistants,
            "user_context": _public(user_view(raw.get("user_context"))),
            "shared_context": _clean_multiline(raw.get("shared_context")),
            "exclusions": list(sections.get(ww.EXCLUDE_SECTION, [])),
        }


def _write_all(raw, original_text, assistants, user_context=None, shared_context=None, renames=None):
    # `languages` siempre explícito en el archivo: un asistente escrito a
    # mano con `languages: []` (todos) queda con la lista completa al
    # guardar cualquier cosa desde la interfaz.
    for a in assistants:
        if not a["languages"]:
            a["languages"] = pipeline_languages()
    uc = user_context if user_context is not None else user_view(raw.get("user_context"))
    sc = shared_context if shared_context is not None else _clean_multiline(raw.get("shared_context"))
    new_text = render_config(uc, sc, assistants, original_text, renames)
    _check_roundtrip(new_text, uc, sc, assistants)
    _write_config(new_text, original_text)


def _with_section(sections: dict, old, new: str, words: list) -> dict:
    """Pone/renombra la sección `new` (antes `old`) de wake_words.txt en su
    mismo lugar, o antes de [excluir] si es nueva."""
    out, placed = {}, False
    for key, value in sections.items():
        if key in (old, new):
            if not placed:
                out[new], placed = words, True
            continue
        if key == ww.EXCLUDE_SECTION and not placed:
            out[new], placed = words, True
        out[key] = value
    if not placed:
        out[new] = words
    return out


def save_assistant(original, data: dict, expected_version, languages: list, owner: str = "") -> str:
    """Crea (original=None) o actualiza/renombra un asistente. Devuelve su
    nombre final. `owner`: el perfil que lo crea o lo guarda. Al actualizar
    se queda con el dueño que tenía; si no tenía (de los administradores) y
    pasa a ser privado, queda de quien lo guardó, para que siga viéndolo."""
    with _LOCK:
        text, version, raw, names = _snapshot()
        _check_version(version, expected_version)
        if original is not None and original not in names:
            raise ConfigError(tr("assistant_missing", name=original), status=404)

        taken_keys = {}
        for n in names:
            key = assistant_view(n, raw[n])["push_to_talk_key"]
            if n != original and key:
                taken_keys[key] = n
        clean, aliases, add_exclusions, errors = validate_assistant(data, set(names) - {original}, languages, taken_keys)
        if errors:
            raise ConfigError(tr("check_fields"), errors)

        assistants = [assistant_view(n, raw[n]) for n in names]
        if original is None:
            clean["owner"] = _owner(owner)
            assistants.append(clean)
        else:
            before = assistant_view(original, raw[original])
            clean["owner"] = before["owner"] or ("" if clean.get("shared", True) else _owner(owner))
            if before.get("_extra"):
                clean["_extra"] = before["_extra"]
            assistants[names.index(original)] = clean

        renames = {original: clean["name"]} if original and original != clean["name"] else None
        _write_all(raw, text, assistants, renames=renames)

        header, sections = ww.read_wake_file()
        sections = _with_section(sections, original, clean["name"], aliases)
        if add_exclusions:
            current = sections.setdefault(ww.EXCLUDE_SECTION, [])
            current += [w for w in add_exclusions if w not in current]
        ww.write_wake_file(header, sections)
        return clean["name"]


def delete_assistant(name: str, expected_version) -> None:
    with _LOCK:
        text, version, raw, names = _snapshot()
        _check_version(version, expected_version)
        if name not in names:
            raise ConfigError(tr("assistant_missing", name=name), status=404)
        if len(names) == 1:
            raise ConfigError(tr("keep_one"))
        assistants = [assistant_view(n, raw[n]) for n in names if n != name]
        _write_all(raw, text, assistants)

        header, sections = ww.read_wake_file()
        if sections.pop(name, None) is not None:
            ww.write_wake_file(header, sections)


def save_shared(data: dict, expected_version) -> None:
    with _LOCK:
        text, version, raw, names = _snapshot()
        _check_version(version, expected_version)

        errors = {}
        # Los datos de cada persona ahora van en su perfil (profiles.py):
        # sin "user_context", el de assistants.yaml (el de los modos de
        # consola) queda como estaba.
        if "user_context" in data:
            uc = validate_user_context(data.get("user_context") or {}, errors)
            extra = user_view(raw.get("user_context")).get("_extra")
            if extra:
                uc["_extra"] = extra
        else:
            uc = user_view(raw.get("user_context"))

        shared_context = _clean_multiline(data.get("shared_context"))
        if len(shared_context) > MAX_LONG_TEXT:
            errors["shared_context"] = tr("max_chars", n=MAX_LONG_TEXT)

        exclusions, bad = [], []
        for raw_word in data.get("exclusions") or []:
            word = ww.clean_word(raw_word)
            if not word:
                bad.append(str(raw_word))
            elif word not in exclusions:
                exclusions.append(word)
        if bad:
            errors["exclusions"] = tr("one_word_exclusion", words=", ".join(bad))
        if errors:
            raise ConfigError(tr("check_fields"), errors)

        assistants = [assistant_view(n, raw[n]) for n in names]
        _write_all(raw, text, assistants, user_context=uc, shared_context=shared_context)

        header, sections = ww.read_wake_file()
        sections[ww.EXCLUDE_SECTION] = exclusions
        ww.write_wake_file(header, sections)


def transfer_owner(old: str, new: str) -> None:
    """Los asistentes de un perfil que se borra pasan a `new` (quien lo
    borra), con la misma visibilidad."""
    with _LOCK:
        text, _version_, raw, names = _snapshot()
        assistants = [assistant_view(n, raw[n]) for n in names]
        changed = False
        for a in assistants:
            if a["owner"] == old:
                a["owner"] = _owner(new)
                changed = True
        if changed:
            _write_all(raw, text, assistants)


def preview_assistant(data: dict) -> str:
    """Cómo quedaría la sección de este asistente en assistants.yaml."""
    name = str(data.get("name") or "").strip().lower() or "nuevo"
    fields = {k: v for k, v in data.items() if k in KNOWN_FIELDS}  # sin aliases/add_exclusions del borrador
    return "\n".join(_emit_assistant(assistant_view(name, fields))) + "\n"


def wake_check(name: str, aliases, original, extra_exclusions) -> dict:
    with _LOCK:
        _text, _version_, _raw, names = _snapshot()
        wake_aliases, exclusions = ww.load_wake_words()
    exclusions |= {w for w in (ww.clean_word(x) for x in extra_exclusions or []) if w}
    clean_name = ww.normalize(name or "")
    others = {
        n: wake_aliases.get(n, set())
        for n in names
        if n not in (original, clean_name)
    }
    return ww.wake_report(clean_name, [ww.clean_word(a) for a in aliases or []], exclusions, others)
