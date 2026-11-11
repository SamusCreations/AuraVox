"""
Utilidades compartidas por los asistentes definidos en assistants.yaml.
"""
import contextlib
import datetime
import json
import math
import time
import os
import re
import subprocess
import threading

import requests
import yaml

from app.core import llm_remote

from app.paths import ASSISTANTS_YAML as _DEFAULT_CONFIG_PATH
from app.voice.push_to_talk import normalize_key

# Claves de nivel superior de assistants.yaml que NO son un asistente
# (son configuración compartida) — load_assistants_config() y
# switch_model.py las excluyen al recorrer las secciones del archivo.
NON_ASSISTANT_KEYS = {"shared_context", "user_context"}

VALID_VOICE_CODES = {"F1", "F2", "F3", "F4", "F5", "M1", "M2", "M3", "M4", "M5"}  # las de Supertonic


def normalize_voice(value) -> str:
    """Código de voz tal como se guarda: "M5" (Supertonic, en mayúsculas) o
    "custom:<id>" (clonada, ver voice_settings)."""
    from app.core import voice_settings

    value = str(value or "").strip()
    return value.lower() if voice_settings.is_custom(value) else value.upper()


def is_valid_voice(code: str) -> bool:
    from app.core import voice_settings

    return code in VALID_VOICE_CODES or code in voice_settings.voice_codes()
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"

# keep_alive que se manda en cada petición a Ollama (ver ask_with_tools):
# tiempo que el modelo se queda cargado en RAM/VRAM tras la última
# petición, sin volver a pagar la recarga entre turnos de una misma
# conversación. -1 = nunca expira solo, por decisión explícita: si
# voice_loop.py/el modo texto terminan de forma anormal (ventana cerrada a
# la fuerza, un crash, doble Ctrl+C encima de la limpieza) el modelo se
# queda cargado indefinidamente en vez de liberarse solo — a propósito,
# para no repetir nunca la recarga en frío (~15s) entre sesiones. Si eso
# pasa y hace falta la VRAM, liberar a mano con free_ollama_memory.bat en
# vez de esperar un timeout automático.
MODEL_KEEP_ALIVE = -1


def _keep_alive_setting(default=-1):
    """keep_alive de la interfaz web y de los embeddings: AURAVOX_KEEP_ALIVE
    ("30m", "2h", "-1"…) o, sin ella, -1 (gemma4 y nomic-embed-text se
    quedan cargados entre turnos; se descargan solo a pedido, con
    unload_ollama_model / "Liberar memoria"). Antes eran 15 y 10 minutos:
    tras una pausa, la primera respuesta pagaba ~10 s de recarga."""
    value = (os.environ.get("AURAVOX_KEEP_ALIVE") or "").strip()
    if not value:
        return default
    return int(value) if re.fullmatch(r"-?\d+", value) else value


SERVER_KEEP_ALIVE = _keep_alive_setting()

# (valor_por_defecto, mínimo, máximo) — usado por load_assistants_config()
# para completar/validar lo que falte o esté fuera de rango en assistants.yaml.
_NUMERIC_DEFAULTS = {
    "speed": (1.0, 0.5, 2.0),
    "temperature": (0.7, 0.0, 2.0),
    "top_p": (0.95, 0.01, 1.0),
    # Segundos de silencio antes de dar por terminada la frase en la
    # conversación por voz ("pausa para pensar"); antes era un selector de
    # la página, igual para todos los asistentes.
    "think_pause": (1.5, 0.5, 6.0),
}
_INT_DEFAULTS = {
    "top_k": (64, 1, 1000),
    "max_history": (20, 2, 200),
    "max_tool_rounds": (4, 1, 10),
}
_TEXT_DEFAULTS = {
    "search_announcement": "Buscando en internet.",
    "fallback_message": "Se me trabó la respuesta, ¿puedes repetir la pregunta?",
}

# Idiomas que reconoce Whisper (STT) Y habla Supertonic-3 (TTS) a la vez —
# los únicos que tiene sentido ofrecer. Se calcula de las propias librerías
# en pipeline_languages(); esta lista es solo el respaldo si no se pueden
# importar.
LANGUAGE_NAMES = {
    "ar": "Árabe", "bg": "Búlgaro", "cs": "Checo", "da": "Danés", "de": "Alemán",
    "el": "Griego", "en": "Inglés", "es": "Español", "et": "Estonio", "fi": "Finés",
    "fr": "Francés", "hi": "Hindi", "hr": "Croata", "hu": "Húngaro", "id": "Indonesio",
    "it": "Italiano", "ja": "Japonés", "ko": "Coreano", "lt": "Lituano", "lv": "Letón",
    "nl": "Neerlandés", "pl": "Polaco", "pt": "Portugués", "ro": "Rumano", "ru": "Ruso",
    "sk": "Eslovaco", "sl": "Esloveno", "sv": "Sueco", "tr": "Turco", "uk": "Ucraniano",
    "vi": "Vietnamita",
}


# Nombre en inglés y nombre propio de cada idioma, para pedirle al modelo
# que responda en él sin ambigüedad (solo el código ISO no alcanzaba).
LANGUAGE_PROMPT_NAMES = {
    "ar": ("Arabic", "العربية"), "bg": ("Bulgarian", "български"), "cs": ("Czech", "čeština"),
    "da": ("Danish", "dansk"), "de": ("German", "Deutsch"), "el": ("Greek", "Ελληνικά"),
    "en": ("English", "English"), "es": ("Spanish", "español"), "et": ("Estonian", "eesti"),
    "fi": ("Finnish", "suomi"), "fr": ("French", "français"), "hi": ("Hindi", "हिन्दी"),
    "hr": ("Croatian", "hrvatski"), "hu": ("Hungarian", "magyar"), "id": ("Indonesian", "Bahasa Indonesia"),
    "it": ("Italian", "italiano"), "ja": ("Japanese", "日本語"), "ko": ("Korean", "한국어"),
    "lt": ("Lithuanian", "lietuvių"), "lv": ("Latvian", "latviešu"), "nl": ("Dutch", "Nederlands"),
    "pl": ("Polish", "polski"), "pt": ("Portuguese", "português"), "ro": ("Romanian", "română"),
    "ru": ("Russian", "русский"), "sk": ("Slovak", "slovenčina"), "sl": ("Slovenian", "slovenščina"),
    "sv": ("Swedish", "svenska"), "tr": ("Turkish", "Türkçe"), "uk": ("Ukrainian", "українська"),
    "vi": ("Vietnamese", "Tiếng Việt"),
}


def language_label(code: str) -> str:
    """"English (English)", "Portuguese (português)"... para los prompts."""
    english, native = LANGUAGE_PROMPT_NAMES.get(code, (code, code))
    return english if english == native else f"{english} ({native})"


def pipeline_languages() -> list:
    """Códigos ISO 639-1 que soportan a la vez Whisper y Supertonic-3.

    Lo lee de las propias librerías (sin cargar ningún modelo) para que un
    cambio de versión se refleje solo; si no se pueden importar, usa
    LANGUAGE_NAMES."""
    try:
        from faster_whisper.tokenizer import _LANGUAGE_CODES
        from supertonic.config import AVAILABLE_LANGUAGES

        langs = (set(AVAILABLE_LANGUAGES) - {"na"}) & set(_LANGUAGE_CODES)
        if langs:
            return sorted(langs)
    except Exception:
        pass
    return sorted(LANGUAGE_NAMES)


def parse_bool(value, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "yes", "si", "sí", "1", "on")


def parse_language_list(value) -> list:
    """Normaliza el campo `languages` de assistants.yaml: acepta una lista
    YAML (`[es, en]`) o un texto separado por comas/espacios. Vacío = todos
    los idiomas del pipeline."""
    if not value:
        return []
    if isinstance(value, str):
        value = re.split(r"[,\s]+", value)
    return sorted({str(v).strip().lower() for v in value if str(v).strip()})

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"]


def load_user_context(path: str = _DEFAULT_CONFIG_PATH) -> dict:
    """Lee la sección `user_context` (nivel superior, no es un asistente) de
    assistants.yaml: nombre, país, ubicación en texto y, opcionalmente,
    coordenadas exactas (`latitud`/`longitud`) para que find_nearby_places
    (nearby_places.py) las use directas en vez de geocodificar `ubicacion`
    por nombre — más preciso y no depende de que Nominatim reconozca bien
    el lugar. Sin coordenadas, todo sigue funcionando igual (se geocodifica
    el texto como antes); con coordenadas, es más preciso y no gasta esa
    llamada de red.

    Es compartido por TODOS los asistentes de assistants.yaml (a diferencia
    de `personality`, que es por asistente) — se inyecta en cada llamada
    (ver `build_system_message`) para que el usuario no tenga que repetir
    quién es o dónde está en cada pregunta.
    """
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except FileNotFoundError:
        raw = {}
    ctx = raw.get("user_context") or {}

    lat, lon = ctx.get("latitud"), ctx.get("longitud")
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        print(f"(warning: assistants.yaml [user_context] invalid latitude/longitude ('{lat}', '{lon}'), ignoring)")
        lat = lon = None

    return {
        "nombre": str(ctx.get("nombre", "")).strip(),
        "pais": str(ctx.get("pais", "")).strip(),
        "ubicacion": str(ctx.get("ubicacion", "")).strip(),
        "latitud": lat,
        "longitud": lon,
    }


_user_ctx_local = threading.local()


class _UserContext(dict):
    """USER_CONTEXT: el de assistants.yaml (los modos de consola), salvo
    que el hilo actual esté respondiendo a un perfil de la interfaz web
    (ver user_context_for): entonces se leen los datos de ESE perfil. Así
    dos personas pueden chatear a la vez, cada una con su nombre y su
    ubicación, sin pisarse."""

    def _view(self) -> dict:
        override = getattr(_user_ctx_local, "ctx", None)
        return self if override is None else override

    def __getitem__(self, key):
        return dict.__getitem__(self._view(), key)

    def get(self, key, default=None):
        return dict.get(self._view(), key, default)

    def __contains__(self, key):
        return dict.__contains__(self._view(), key)


@contextlib.contextmanager
def user_context_for(ctx):
    """Durante el bloque, USER_CONTEXT son los datos `ctx` (de un perfil o
    de un invitado; None = los de assistants.yaml)."""
    if ctx is None:
        yield
        return
    def num(v):
        try:
            v = float(v)
            return v if math.isfinite(v) else None
        except (TypeError, ValueError):
            return None
    lat, lon = num(ctx.get("latitud")), num(ctx.get("longitud"))
    if lat is None or lon is None:
        lat = lon = None
    view = {key: str(ctx.get(key) or "").strip() for key in ("nombre", "pais", "ubicacion")}
    view.update(latitud=lat, longitud=lon)
    previous = getattr(_user_ctx_local, "ctx", None)
    _user_ctx_local.ctx = view
    try:
        yield
    finally:
        _user_ctx_local.ctx = previous


# Cargado una vez al importar el módulo — igual que antes cuando era un
# dict hardcodeado, solo que ahora viene de assistants.yaml en vez de estar
# escrito aquí.
USER_CONTEXT = _UserContext(load_user_context())


def load_assistants_config(path: str) -> dict:
    """Lee assistants.yaml y devuelve {nombre: {...config validada...}}.

    `shared_context` (nivel superior, no es un asistente) son las reglas
    operativas comunes a todos — se agregan solas a la `personality` de
    CADA asistente (ver `cfg["shared_context"]` más abajo y
    `build_system_message()`), así no hay que repetirlas en cada uno ni
    copiarlas a mano al agregar un asistente nuevo.

    `base_model` y `personality` son obligatorios por asistente (sin ellos
    no hay asistente que valga: no se sabe qué modelo llamar ni qué
    personalidad darle). Todo lo demás (voice, speed, temperature, top_k,
    top_p, language, languages, max_history, max_tool_rounds,
    search_announcement, fallback_message, label) tiene un valor por defecto razonable y se
    avisa por consola (sin fallar) si el archivo trae algo inválido —
    igual que languages.txt/wake_words.txt: un typo en la configuración
    no debe tumbar el asistente.
    """
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    shared_context = str(raw.pop("shared_context", "") or "").strip()
    for key in NON_ASSISTANT_KEYS:
        raw.pop(key, None)

    assistants = {}
    for name, section in raw.items():
        section = section or {}
        cfg = {"shared_context": shared_context}

        base_model = str(section.get("base_model", "")).strip()
        if not base_model:
            raise ValueError(f"assistants.yaml: '{name}' is missing 'base_model' (required).")
        cfg["base_model"] = base_model

        personality = str(section.get("personality", "")).strip()
        if not personality:
            raise ValueError(f"assistants.yaml: '{name}' is missing 'personality' (required).")
        cfg["personality"] = personality

        voice = normalize_voice(section.get("voice", "M5"))
        if not is_valid_voice(voice):
            print(f"(warning: assistants.yaml [{name}] voice '{voice}' is invalid, using 'M5'. Options: {', '.join(sorted(VALID_VOICE_CODES))})")
            voice = "M5"
        cfg["voice"] = voice

        for key, (default, lo, hi) in _NUMERIC_DEFAULTS.items():
            value = section.get(key, default)
            try:
                value = float(value)
                if not (lo <= value <= hi):
                    raise ValueError
            except (TypeError, ValueError):
                print(f"(warning: assistants.yaml [{name}] {key}='{value}' is invalid ({lo}-{hi}), using {default})")
                value = default
            cfg[key] = value

        for key, (default, lo, hi) in _INT_DEFAULTS.items():
            value = section.get(key, default)
            try:
                value = int(value)
                if not (lo <= value <= hi):
                    raise ValueError
            except (TypeError, ValueError):
                print(f"(warning: assistants.yaml [{name}] {key}='{value}' is invalid ({lo}-{hi}), using {default})")
                value = default
            cfg[key] = value

        cfg["language"] = str(section.get("language", "es")).strip().lower() or "es"
        # Idiomas en los que este asistente responde (vacío = todos los que
        # soporta el pipeline) — voice_loop.py los cruza con lo que soportan
        # Whisper/Supertonic y con languages.txt.
        cfg["languages"] = parse_language_list(section.get("languages"))
        for key, default in _TEXT_DEFAULTS.items():
            cfg[key] = str(section.get(key) or default).strip()

        # Cómo se lo llama en voice_loop.py: diciendo su nombre (wake_word)
        # y/o manteniendo apretada una tecla (push_to_talk_key, "" = no).
        cfg["wake_word"] = parse_bool(section.get("wake_word"), True)
        raw_key = section.get("push_to_talk_key") or ""
        cfg["push_to_talk_key"] = normalize_key(raw_key)
        if raw_key and not cfg["push_to_talk_key"]:
            print(f"(warning: assistants.yaml [{name}] push_to_talk_key '{raw_key}' is not a supported key, push-to-talk disabled)")
        if not cfg["wake_word"] and not cfg["push_to_talk_key"]:
            print(f"(warning: assistants.yaml [{name}] has neither wake_word nor push_to_talk_key; enabling wake_word so it can be called)")
            cfg["wake_word"] = True
        cfg["label"] = str(section.get("label", "")).strip() or name.upper()

        assistants[name] = cfg

    return assistants


def ollama_installed_models(url: str = OLLAMA_TAGS_URL) -> list:
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return [m["name"] for m in r.json().get("models", [])]


def model_is_installed(name: str, installed: list) -> bool:
    if name in installed:
        return True
    # Ollama normaliza "modelo" (sin tag) a "modelo:latest" al listarlo.
    if ":" not in name and f"{name}:latest" in installed:
        return True
    return False


def ensure_models_installed(assistants: dict) -> None:
    """Revisa que el `base_model` de cada asistente (como lo devuelve
    load_assistants_config) esté instalado en Ollama; si falta alguno, lo
    pregunta y lo descarga ("ollama pull") antes de seguir.

    Así, agregar un asistente nuevo a assistants.yaml con un modelo que
    todavía no tienes lo deja listo para usarse igual que los demás — no
    hace falta acordarse de instalarlo a mano aparte. Se llama al arrancar
    voice_loop.py y el modo texto (assistant_engine.py); si Ollama no
    responde, solo avisa y sigue (la falla real se verá más adelante, al
    intentar usarlo)."""
    try:
        installed = ollama_installed_models()
    except requests.exceptions.RequestException:
        print("(warning: could not connect to Ollama to check installed models)")
        return

    needed = sorted({cfg["base_model"] for cfg in assistants.values() if not llm_remote.is_remote(cfg["base_model"])})
    missing = [m for m in needed if not model_is_installed(m, installed)]
    if not missing:
        return

    print(f"Models from assistants.yaml missing in Ollama: {', '.join(missing)}")
    for model in missing:
        confirm = input(f"Download '{model}' now? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes", "s", "si"):
            print(f"(skipped: assistants using '{model}' will fail until you install it manually with 'ollama pull {model}')")
            continue
        print(f"\nDownloading '{model}'...\n")
        result = subprocess.run(["ollama", "pull", model])
        if result.returncode != 0:
            print(f"Could not download '{model}'.")


def get_realtime_facts() -> dict:
    """Datos que cambian en tiempo real (se recalculan en cada llamada,
    nunca se cachean) y que el asistente necesita tener siempre presentes
    sin que el usuario se los tenga que decir en cada pregunta — hoy solo
    fecha/hora, pero este es el punto central donde agregar más datos "en
    vivo" en el futuro: todo lo que devuelva se inyecta solo en cada turno
    vía `turn_context()` → `_realtime_ctx()` (al final del último mensaje del usuario)."""
    now = datetime.datetime.now()
    hour12 = now.hour % 12 or 12
    return {
        "date": f"{_WEEKDAYS[now.weekday()]}, {_MONTHS[now.month - 1]} {now.day}, {now.year}",
        "iso_date": now.date().isoformat(),
        "time": f"{hour12}:{now.minute:02d} {'a.m.' if now.hour < 12 else 'p.m.'}",  # 12 horas: "7:19 p.m."
    }


def _realtime_ctx() -> str:
    facts = get_realtime_facts()
    # Antes se daba "sábado 26 de septiembre de 2026, 19:19" sin más: a
    # "¿qué hora es?" el modelo respondía con la fecha completa y en formato
    # de 24 horas.
    return (
        f"Today is {facts['date']} ({facts['iso_date']}). The local time is {facts['time']}. "
        "If you're asked the time, give ONLY the time, in 12-hour format with a.m./p.m. written the way it's "
        "usual in the reply language (e.g. «son las 7:19 p. m.»), without adding the date or the day unless "
        "they're asked too. If you're asked the date or the day, give the date. You don't need to search the "
        "internet for this. Don't mention the time or the date when nobody asked for them (a greeting is not "
        "asking for the time)."
    )


_NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
_NOMINATIM_HEADERS = {"User-Agent": "jarvis-bella-asistente-personal/1.0 (uso personal)"}
_resolved_location_cache = None


def _resolve_location_name() -> str:
    """Convierte latitud/longitud de USER_CONTEXT en un nombre de lugar
    legible ("Valencia, España") vía Nominatim (reverse geocoding), una
    sola vez por proceso y cacheado en memoria — igual que _home_coords()
    en nearby_places.py, pero para el system prompt en vez de las
    búsquedas.

    Bug real que motivó esto: con coordenadas configuradas pero
    `ubicacion`/`pais` en texto vacíos (el caso recomendado — ver el
    comentario de `user_context` en assistants.yaml), `_usuario_ctx()`
    antes no exponía la ubicación real al modelo de ninguna forma (los
    números de latitud/longitud crudos no le sirven, no puede interpretarlos
    él solo). Al preguntar por el clima o "dónde vivo", con la instrucción de
    "dalo por hecho, no lo preguntes" pero sin ningún dato real que usar, el
    modelo inventaba una ciudad cualquiera (se vio en la práctica: contestaba
    Madrid, con Gemma 4 E4B y con Qwen3.5, sin relación con las coordenadas
    reales). Con el nombre real resuelto acá, el modelo tiene algo concreto
    para razonar y para armar la consulta de web_search (p. ej. "clima hoy en
    Valencia España" en vez de una consulta sin ubicación)."""
    global _resolved_location_cache
    lat, lon = USER_CONTEXT.get("latitud"), USER_CONTEXT.get("longitud")
    if lat is None or lon is None:
        return ""
    # Por coordenadas: cada perfil tiene las suyas.
    if _resolved_location_cache is None:
        _resolved_location_cache = {}
    if (lat, lon) not in _resolved_location_cache:
        try:
            _resolved_location_cache[(lat, lon)] = reverse_geocode(lat, lon)["label"]
        except Exception:
            return ""  # sin red: se reintenta la próxima vez
    return _resolved_location_cache[(lat, lon)]


# ── Nominatim (OpenStreetMap), gratis y sin API key ────────────────────
# Su política de uso pide: User-Agent que identifique la app, máximo 1
# petición por segundo y NO autocompletar mientras se escribe (por eso el
# buscador del mapa en la interfaz busca solo al pulsar Enter).
_NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
_nominatim_lock = threading.Lock()
_nominatim_last = 0.0


def _nominatim_get(url: str, params: dict) -> object:
    global _nominatim_last
    with _nominatim_lock:
        wait = 1.0 - (time.time() - _nominatim_last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(url, params=params, headers=_NOMINATIM_HEADERS, timeout=8)
        finally:
            _nominatim_last = time.time()
    r.raise_for_status()
    return r.json()


def reverse_geocode(lat: float, lon: float, lang: str = "es") -> dict:
    """Coordenadas → nombre del lugar: {"barrio", "ciudad", "region",
    "pais", "label"} ("Ruzafa, Valencia, España")."""
    data = _nominatim_get(
        _NOMINATIM_REVERSE_URL,
        # zoom=10 (nivel "ciudad") resultó demasiado grueso en la
        # práctica: para una casa en el barrio San Rafael devolvía el
        # pueblo entero (el municipio) como si fuera el lugar exacto.
        # zoom=16 ("calle"/barrio) trae el barrio real además del
        # pueblo, y se arma la cadena de más preciso a menos preciso.
        {"lat": lat, "lon": lon, "format": "json", "zoom": 16, "accept-language": lang},
    )
    addr = (data or {}).get("address", {}) if isinstance(data, dict) else {}
    barrio = addr.get("neighbourhood") or addr.get("suburb") or addr.get("quarter") or ""
    ciudad = (
        addr.get("city") or addr.get("town") or addr.get("village")
        or addr.get("municipality") or addr.get("county") or ""
    )
    region = addr.get("state", "")
    pais = addr.get("country", "")
    return {
        "barrio": barrio,
        "ciudad": ciudad,
        "region": region,
        "pais": pais,
        "label": ", ".join(p for p in (barrio, ciudad, pais) if p),
    }


def search_places(query: str, lang: str = "es", limit: int = 6) -> list:
    """Texto libre ("Parque del Retiro", "Valencia") → [{"label", "lat", "lon"}]."""
    results = _nominatim_get(
        _NOMINATIM_SEARCH_URL,
        {"q": query, "format": "json", "limit": limit, "accept-language": lang},
    )
    return [
        {"label": p.get("display_name", ""), "lat": float(p["lat"]), "lon": float(p["lon"])}
        for p in results or []
        if p.get("lat") and p.get("lon")
    ]


def _usuario_ctx() -> str:
    ctx = USER_CONTEXT
    lugar = f"{ctx['ubicacion']} ({ctx['pais']})" if ctx.get("ubicacion") else ""
    if not lugar and ctx.get("latitud") is not None and ctx.get("longitud") is not None:
        lugar = _resolve_location_name()  # ubicacion/pais vacíos pero hay coordenadas: resolverlas

    if not ctx.get("nombre") and not lugar:
        return ""  # sin user_context configurado en assistants.yaml: no inyectar una frase vacía/rara

    facts = []
    if ctx.get("nombre"):
        facts.append(f"their name is {ctx['nombre']}")
    if lugar:
        facts.append(f"they live in {lugar} (take it also as their current location: if they ask where they "
                     "are or what their location is, it's that)")
    return (
        f"About the user you're talking to: {' and '.join(facts)}. Take these facts for granted, without asking "
        "for them or repeating them needlessly: use them directly for the weather, the local time, the time zone "
        "or nearby results and businesses, unless the user explicitly asks about another person or place. If "
        "they ask how you know this, the truth is that they saved it themselves in the assistant's settings "
        "(they didn't tell you in this conversation)."
    )


# Emojis y pictogramas: shared_context los prohíbe pero algunos modelos
# (gemma4:E4B con un "😊" al final) los ponen igual. En un asistente de voz
# nunca aportan, así que se quitan de la respuesta final.
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\U00002B00-\U00002BFF️‍]+"
)


def _ongoing_ctx(history: list) -> str:
    """Si la conversación ya empezó (hay respuestas previas del asistente),
    se le recuerda EN ESTE TURNO que no abra con un saludo. La regla
    general de shared_context sola no alcanzaba con modelos chicos:
    qwen3.5:4b seguía empezando cada respuesta con "¡Hola, <nombre>!" a mitad
    de la charla. (Antes se miraba con una lista de saludos si el usuario
    saludaba otra vez; ahora eso lo decide el modelo.)"""
    if not any(m.get("role") == "assistant" for m in history):
        return ""
    name = USER_CONTEXT.get("nombre")
    example = f' (like "Hi {name}!")' if name else ""
    return (
        f"The conversation is already under way and you've already greeted: don't open your reply with a "
        f"greeting{example} or introduce yourself again, unless the user is greeting you again (then a brief "
        "greeting back is fine). Go straight to what they just said."
    )


# Cómo de largas y de qué tipo son las respuestas según cómo se conversa.
# Se agrega al final del system prompt, así que pisa las indicaciones de
# brevedad de cada personalidad sin tener que tocarlas.
# - "voice": voice_loop.py y la conversación por voz de la interfaz web.
# - "text": el chat escrito de la interfaz web y el modo texto de consola.
RESPONSE_STYLES = {
    "voice": (
        "Reply mode: SPOKEN CONVERSATION. Answer the way people talk to each other, like today's best voice "
        "assistants: natural and compact, but SPECIFIC. Always say the concrete content that was asked for: "
        "the actual names, numbers, amounts, dates, conditions or steps (from your tools, the attached files or "
        "what you know), never a vague summary like \"there are some limits\", \"it depends\" or \"it has "
        "several conditions\" without saying which. Usually two to four sentences (about 20 to 70 words), "
        "essentials first; a greeting or a yes/no question gets one sentence. If the answer is a list, say the "
        "three most important items concretely and offer to go on with the rest. No generic intro like \"great "
        "question\". Don't end every reply with a question or an offer; only when it really helps. This length "
        "rule takes priority over any other length instruction, including your personality's."
    ),
    "text": (
        "Reply mode: WRITTEN CHAT. The user READS your reply on screen (if it's also read aloud, the formatting "
        "is cleaned up first), so the rules about plain spoken prose, no emojis and no symbols in your other "
        "instructions do NOT apply in this mode. Write like the best written assistants:\n"
        "- Substance and detail: give the real content (concrete facts, figures, names, examples, reasons, pros "
        "and cons), never one vague, generic sentence when the question deserves more. Length follows the "
        "question: a greeting or a single fact gets one or two lines; explanations, how-tos, comparisons, "
        "recommendations, plans, the weather, places found, search results or summaries of attached files get "
        "a complete answer (several paragraphs or a structured list), as long as needed but without filler.\n"
        "- Markdown when it helps to read: short paragraphs, **bold** for the key facts, numbered lists for steps "
        "or rankings, bullet lists for options or features, a table to compare several things, and a heading "
        "only in long answers.\n"
        "- Emojis as icons that add meaning, at the start of list items, headings or key lines (e.g. 🌡️ "
        "temperature, 🌧️ rain, 💨 wind, 📍 place, 🕒 time, 📅 date, 💰 price, 📏 distance, ✅/❌ pros and cons, "
        "⚠️ warnings, 💡 tips): a few per answer, not in every sentence.\n"
        "- Numbers in digits, with their units and symbols, in the number format of the reply's language: "
        "25 °C, 12,5 km, 30 km/h, 80 %, 2 h 15 min, $15, ₡7 500, 1,2 GB, 30/10/2026. When a tool or a file gives "
        "figures, include the exact ones.\n"
        "Keep your personality and tone in the words. This rule takes priority over your personality's "
        "brevity instructions."
    ),
}


# Recordatorio corto que se agrega al ÚLTIMO mensaje del usuario (solo en la
# copia que se manda a Ollama, no en el historial): la regla larga del
# system prompt sola no alcanzaba con modelos chicos — qwen3.5:4b seguía
# respondiendo 50-70 palabras en modo voz.
_STYLE_REMINDERS = {
    "voice": "(Spoken reply: short and natural, but with the concrete facts: names, numbers, amounts, conditions.)",
    "text": ("(Written chat: answer with substance and detail when the question calls for it, using Markdown, "
             "emoji icons and figures with their units where they help.)"),
}


# Cuánto se nota que es una conversación hablada (`expressiveness` de cada
# asistente). Se escribe como palabras porque así lo dice cualquier voz; las
# acotaciones se siguen rechazando (ver _STAGE_RE).
EXPRESSIVENESS = {
    "none": "",
    "some": (
        "Sound like a person talking, not reading: now and then use a spontaneous reaction or filler that is "
        "natural in the reply's language, and punctuation that shapes the intonation. Write them as the actual "
        "words you say, never as stage directions in parentheses, brackets or asterisks."
    ),
    "lots": (
        "Sound like a real person in a live conversation, not someone reading. Be very expressive, in the way "
        "that is natural in the reply's language and fits your personality: start with real reactions, and "
        "use interjections and fillers freely (the local equivalents of things like \"mmm\", \"uff\", \"ay\", "
        "\"wow\", \"oh\", \"well\", \"you know\", \"let's see\"), laughter written as sound (\"haha\", in the "
        "spelling of that language) when something is funny, thinking pauses with \"...\", small "
        "self-corrections, and colloquial phrasing with contractions. Let exclamation and question marks carry "
        "the intonation. Vary them: don't repeat the same expression in a reply and don't force them into "
        "serious or sad topics. Write them as the actual words you say, never as stage directions in "
        "parentheses, brackets or asterisks."
    ),
}


def _turn_reminder(style: str, reply_lang: str, auto_langs=None) -> str:
    parts = [_STYLE_REMINDERS.get(style, "")]
    if reply_lang:
        parts.append(f"(Reply only in {language_label(reply_lang)}.)")
    elif auto_langs:
        parts.append("(Reply in the same language as my message above.)")
    return " ".join(p for p in parts if p)


def turn_context(history: list, dynamic_context: str = None) -> str:
    """Lo que cambia en cada turno, para agregar al último mensaje del
    usuario (en la copia que va a Ollama): fecha y hora, lo de las
    habilidades y el aviso de que la charla ya empezó."""
    parts = [_realtime_ctx(), dynamic_context or "", _ongoing_ctx(history or [])]
    body = "\n\n".join(p for p in parts if p)
    return ("[CONTEXT FOR THIS TURN — from the system, not written by the user; use it only when it's relevant to "
            "what they said]\n" + body + "\n[END OF CONTEXT]")


def build_system_message(personality: str, shared_context: str = None, reply_lang: str = None, history: list = None,
                         style: str = None, auto_langs=None, dynamic_context: str = None,
                         expressiveness: str = "lots") -> str:
    """Arma el system prompt completo para una petición: la `personality`
    de assistants.yaml (lo específico de ESE asistente) más el
    `shared_context` (reglas operativas comunes a todos, ver
    load_assistants_config), la fecha/hora actuales, los datos del usuario
    (USER_CONTEXT) y, si se pasa, el idioma en el que debe responder este
    turno (código ISO 639-1, p. ej. "en" — detectado por Whisper en
    voice_loop.py a partir de lo que dijo el usuario).

    Todo va en inglés (una sola configuración para los 31 idiomas); el
    idioma de la RESPUESTA lo fija la instrucción de idioma.

    Ollama solo aplica el SYSTEM de un Modelfile como prompt por defecto
    cuando la petición NO trae un mensaje role="system" propio; como aquí
    siempre se llama al modelo base directo (sin Modelfile de por medio),
    este mensaje es la ÚNICA fuente de personalidad — por eso `personality`
    y `shared_context` deben venir completos desde assistants.yaml, no
    como fragmentos.

    Aquí va solo lo que no cambia entre turnos (personalidad, reglas, datos
    del usuario, estilo). Lo que cambia (hora, lo que agregan las
    habilidades —memoria relevante, recordatorios con los segundos que
    faltan—, si la charla ya empezó) va en el último mensaje del usuario
    (ver turn_context): Ollama reutiliza lo ya procesado del prompt, pero
    con herramientas cualquier cambio en el system prompt lo obligaba a
    procesar todo otra vez (~5000 tokens, ~0,6 s por ronda con gemma4 en una
    RTX 4080, y la revisión previa en paralelo esperaba lo mismo).
    `dynamic_context` se acepta por compatibilidad y también va al final.
    """
    parts = []
    if reply_lang:
        # También al principio: los modelos chicos pesan más el comienzo y
        # el final del prompt.
        parts.append(f"LANGUAGE: reply only in {language_label(reply_lang)}.")
    parts.append(personality)
    if shared_context:
        parts.append(shared_context)
    parts += [_usuario_ctx(), RESPONSE_STYLES.get(style, ""),
              EXPRESSIVENESS.get(expressiveness, "") if style == "voice" else "", dynamic_context or ""]
    if reply_lang:
        name = language_label(reply_lang)
        parts.append(
            f"LANGUAGE OF THIS REPLY: {name} (code '{reply_lang}'). Reply only in {name}, even if these "
            "instructions, your personality or earlier messages of the conversation are in another language. "
            "Keep your personality and every other rule as they are."
        )
    elif auto_langs:
        # Chat escrito en automático: que lo decida el modelo.
        names = ", ".join(language_label(c) for c in auto_langs)
        parts.append(
            "LANGUAGE OF THIS REPLY: the same language the user's last message is written in (it can be any of "
            f"these: {names}). If that message is too short to tell, keep the language the conversation is in."
        )
    return "\n\n".join(p for p in parts if p)


# ── Peticiones con salida estructurada (JSON) ──────────────────────────
# Para que el modelo JUZGUE (¿esto necesitaba una herramienta?, ¿a quién le
# hablaron?…) en vez de decidirlo con listas de palabras clave por idioma:
# Ollama restringe la salida a un esquema JSON (enum, boolean...), así que
# la respuesta siempre se puede leer, en cualquier idioma de la
# conversación. Usa el mismo modelo que ya está cargado (no gasta VRAM extra).

def structured_request(ollama_url: str, model: str, messages: list, schema: dict, keep_alive=MODEL_KEEP_ALIVE,
                       max_tokens: int = 300, tools=None):
    """Respuesta del modelo como dict según `schema`, o None si falló.
    `tools`: solo para que el prompt sea idéntico al de una ronda con
    herramientas (y Ollama reutilice lo ya procesado); la salida igual es
    el JSON del esquema."""
    body = {
        "model": model,
        "think": False,
        "stream": False,
        "messages": messages,
        "format": schema,
        "options": {"temperature": 0, "num_predict": max_tokens},
        "keep_alive": keep_alive,
    }
    if tools:
        body["tools"] = tools
    try:
        r = llm_remote.post(ollama_url, json=body, timeout=60)
        r.raise_for_status()
        data = json.loads(r.json()["message"]["content"])
    except (requests.exceptions.RequestException, ValueError, KeyError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _clip(text, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


# En la conversación grupal lo que dijeron los otros asistentes llega como
# role "user" con el formato "[NOMBRE]: …" (ver config_ui._chat_request).
_SPEAKER_TAG_RE = re.compile(r"^\[([^\]]+)\]:\s*")


def render_transcript(history: list, tool_results=(), draft: str = None, last: int = 8) -> str:
    """La conversación como texto, para las peticiones de juicio."""
    lines = []
    for m in history[-last:]:
        content = str(m.get("content", ""))
        if m.get("role") == "assistant":
            lines.append(f"ASSISTANT: {_clip(content, 500)}")
            continue
        tag = _SPEAKER_TAG_RE.match(content)
        if tag:
            lines.append(f"{tag.group(1)} (another assistant): {_clip(content[tag.end():], 500)}")
        else:
            lines.append(f"USER: {_clip(content, 500)}")
    for name, result in tool_results:
        lines.append(f"TOOL RESULT ({name}): {_clip(result, 400)}")
    if draft is not None:
        lines.append(f"DRAFT REPLY: {draft}")
    return "\n".join(lines)


# ── Revisión de la respuesta antes de decirla ──────────────────────────
# Antes, para detectar que el modelo respondía sin llamar la herramienta que
# hacía falta, se buscaban palabras en el mensaje ("clima", "lluvia",
# "weather", "busca", "cerca de mí", "a cuánta distancia"… en español,
# inglés y portugués) y en la respuesta ("te recomiendo revisar", "voy a
# usar la función"…). Eso fallaba en los dos sentidos: "me encantan los días
# de lluvia" forzaba el clima, "¿necesito paraguas mañana?" dicho de otra
# forma (o en ruso) no; y había que escribir las palabras en cada idioma.
# Ahora el mismo modelo lee la conversación y su borrador y juzga, con una
# sola instrucción en inglés para todos los idiomas.
_REVIEW_SYSTEM = """You review the draft reply of a voice assistant{who} before the user hears it. You only judge; you never write the reply.

The assistant can use these tools:
{tools}

Read the user's LAST message (lines starting with USER), in whatever language it is in, and judge its meaning in the context of the conversation, not individual words. Files, images and audio transcriptions the user attached ("[Attached ...]") are already part of the conversation: questions about them need no tool (except converting a file to another format, which needs convert_file), and the language of the user's message is the one they wrote in, not the attachment's. Judge ONLY the technical points below: whether a request or a draft is appropriate, polite, edgy or allowed is not your concern (the assistant may be playing an uncensored roleplay character on purpose), so never flag a draft for its content or tone. Then answer:
1. needed_tool: does a correct answer need one of these tools RIGHT NOW? That is: real-time, local or external information the assistant can't know by itself (current weather, news, prices, scores, distances, nearby places, facts that change over time), or an action (like playing music, or bringing someone into the conversation). Today is {today}: anything about the latest, current or most recent something (last champion, current version, who holds a post now, ages), or about events from the last two years, needs a search, because the assistant's own knowledge may be out of date. Pick that tool, or "none". It's "none" when the message only mentions a topic without asking for new information or an action (chatting about rainy days, thanking for a forecast already given), when that information already came in a TOOL RESULT of this conversation, when general knowledge or the assistant's own opinion is enough, or when the action makes no sense for this assistant (e.g. being asked to invite itself), or when none of the tools does what's asked (never a tool that would do something different).
2. draft_problem: "promises_to_act" if the draft says it will look something up, check or do something instead of actually answering (not when a TOOL RESULT of this turn shows it was already done: then telling it, in any tense, is fine); "sends_user_elsewhere" if it tells the user to look it up, check or compare by themselves; "not_speakable" if {not_speakable}; "contradicts_tool_result" if it states something that a TOOL RESULT of this conversation contradicts (e.g. it says it did something the tool said wasn't possible or wasn't needed); otherwise "none".
3. draft_language: the language the draft is written in (ISO 639-1 code).
Write "reasoning" first: one short sentence."""

_REVIEW_NUDGES = {
    "promises_to_act": (
        "Don't say you'll do it, look it up or check it: if it needs information or an action, use the right "
        "tool now (tool calling), in this same turn; otherwise just answer."
    ),
    "sends_user_elsewhere": (
        "Don't send me to look it up, check or compare it myself: that's what you're for. If a fact is "
        "needed, get it now with the right tool (tool calling); if it's an opinion or a comparison, give me "
        "yours directly, in a few words."
    ),
    "contradicts_tool_result": (
        "Your reply contradicts what the tool result said. Answer again saying what actually happened, "
        "according to the tool result, in a few words."
    ),
    "not_speakable": (
        "Everything you write is read aloud exactly as it is. Say the same again without stage directions or "
        "descriptions of your voice, tone or actions (nothing in parentheses, brackets or asterisks), and "
        "without markdown, lists, links or emojis: show your style only through the words themselves."
    ),
}

# Visto con modelos de roleplay (Rocinante): ante el empujón contestaban a la
# instrucción ("Understood! I'll answer your questions directly…") en vez de
# volver a responderle al usuario. Por eso cada empujón termina pidiendo solo
# la respuesta nueva.
_ANSWER_AGAIN = (" Now answer my previous message again: write only your new reply to me, "
                 "without acknowledging or mentioning this note.")
_REVIEW_NUDGES = {k: v + _ANSWER_AGAIN for k, v in _REVIEW_NUDGES.items()}

# Cuántas veces se revisa un borrador por turno (cada empujón genera otro).
MAX_REVIEWS = 3

# Acotaciones: "(Voz de presentador, exageradamente entusiasta)", "[susurra]",
# "*se ríe*". Se reconocen por la puntuación (sirve en cualquier idioma) por
# si el revisor no las marca: visto, ZIGGY las escribía y la voz las leía.
_STAGE_RE = re.compile(r"\([^()]{3,}\)|\[[^\[\]]{3,}\]|\*[^*]{3,}\*")


# Qué cuenta como "not_speakable" según el modo: por voz todo se lee tal
# cual; en el chat escrito el markdown, las listas y los emojis son
# bienvenidos (ver RESPONSE_STYLES), solo sobran las acotaciones.
_NOT_SPEAKABLE = {
    "voice": ("it contains text that must not be read aloud: stage directions or descriptions of the voice, tone or "
              "actions (in parentheses, brackets or asterisks), markdown, lists, links or emojis"),
    "text": ("it contains stage directions or descriptions of the assistant's voice, tone or actions (like "
             "*laughs* or (sighs)); Markdown formatting, lists, tables, links, emojis and figures with units are "
             "fine in this written chat and are NOT a problem"),
}
_TEXT_NUDGES = {
    "not_speakable": ("Write the same again without stage directions or descriptions of your voice, tone or "
                      "actions: show your style only through the words themselves (Markdown and emojis are fine)."),
}


def _review_draft(ollama_url, model, keep_alive, tools, history, tool_results, draft, assistant_name=None,
                  style: str = "voice"):
    tool_lines = "\n".join(
        f"- {t['function']['name']}: {_clip(t['function'].get('description', ''), 300)}" for t in tools
    ) or "(none)"
    schema = {
        "type": "object",
        "properties": {
            "reasoning": {"type": "string"},
            "needed_tool": {"type": "string", "enum": ["none", *(t["function"]["name"] for t in tools)]},
            # Sin resultados de herramientas no hay nada que contradecir. Visto:
            # con una foto, "contradicts_tool_result" sin herramienta alguna
            # costaba una ronda y otra revisión de más.
            "draft_problem": {"type": "string", "enum": ["none", *(
                p for p in _REVIEW_NUDGES if tool_results or p != "contradicts_tool_result")]},
            "draft_language": {"type": "string", "enum": [*LANGUAGE_PROMPT_NAMES, "other"]},
        },
        "required": ["reasoning", "needed_tool", "draft_problem", "draft_language"],
    }
    messages = [
        {"role": "system", "content": _REVIEW_SYSTEM.format(
            tools=tool_lines, who=f" called {assistant_name} (its replies are the ASSISTANT lines)" if assistant_name else "",
            today=time.strftime("%Y-%m-%d"), not_speakable=_NOT_SPEAKABLE["text" if style == "text" else "voice"])},
        {"role": "user", "content": render_transcript(history, tool_results, draft)},
    ]
    return structured_request(ollama_url, model, messages, schema, keep_alive)


def _tool_arguments(ollama_url, model, keep_alive, tool, history, tool_results):
    """Argumentos para llamar `tool` directamente, generados por el modelo
    con el esquema de parámetros de la propia herramienta (sirve igual para
    cualquier herramienta nueva). {} si no tiene parámetros; None si falló."""
    fn = tool["function"]
    params = fn.get("parameters") or {}
    if not params.get("properties"):
        return {}
    messages = [
        {"role": "system", "content": (
            f"Fill in the arguments to call the tool `{fn['name']}` so it answers the user's last request "
            f"(lines starting with USER).\nTool: {fn.get('description', '')}\nUse the whole conversation for "
            "context: the user may refer to something said earlier. Keep free-text values short. Only fill an "
            "optional field with something the user actually said or that clearly follows from the conversation; "
            "otherwise leave it empty: never invent names, brands or places."
        )},
        {"role": "user", "content": render_transcript(history, tool_results)},
    ]
    return structured_request(ollama_url, model, messages, params, keep_alive)


# Algunos modelos (p. ej. Gemma vía Ollama) a veces escriben la llamada a la
# herramienta como texto ('web_search{query:"..."}<tool_call|>') en vez de
# usar el campo tool_calls, o dicen su nombre tal cual. No depende del
# idioma: son marcas de formato y nombres de herramientas.
_TOOL_CALL_LEAK_RE = re.compile(r"<\|?\s*tool_call|tool_response|<\|python_tag\|>", re.I)


# Caracteres que no se ven ni se pronuncian. Visto con Mistral Nemo
# abliterated: cuando no sabe qué decir (sobre todo tras un empujón o con
# herramientas a mano), su token más probable es un espacio de ancho cero
# (U+200B) o guiones suaves (U+00AD), y eso se daba por respuesta.
_INVISIBLE_RE = re.compile(r"[\u00ad\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")


def _text_tool_calls(content: str, tools_by_name) -> list:
    """Llamadas que el modelo escribió como texto en vez de usar tool_calls:
    '[TOOL_CALLS][{"name": "web_search", "arguments": {...}}]', o el JSON
    solo, con o sin ```. Pasa con fine-tunes de Mistral Nemo (Rocinante):
    saben QUÉ llamar pero no siempre emiten el token especial. Devuelve las
    llamadas en el formato de Ollama, o [] si el texto no es eso."""
    text = re.sub(r"^```(?:json)?|```$", "", content.strip()).strip()
    text = re.sub(r"^\[TOOL_CALLS\]", "", text).strip()
    start = min([i for i in (text.find("["), text.find("{")) if i >= 0], default=-1)
    if start < 0 or start > 3:
        return []
    try:
        data, end = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return []
    if text[start + end:].strip():
        return []  # JSON dentro de una frase: no es una llamada
    items = data if isinstance(data, list) else [data]
    calls = []
    for item in items:
        if not isinstance(item, dict) or item.get("name") not in tools_by_name:
            return []
        args = item.get("arguments", item.get("parameters", {})) or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                return []
        if not isinstance(args, dict):
            return []
        calls.append({"function": {"name": item["name"], "arguments": args}})
    return calls


def _leaked_tool_call(content: str, tool_names) -> bool:
    if _TOOL_CALL_LEAK_RE.search(content):
        return True
    return any(re.search(rf"\b{re.escape(name)}\b", content) for name in tool_names)


# ── Streaming: la respuesta se muestra y se dice mientras se genera ─────
# Antes cada ronda pedía la respuesta entera ("stream": false) y recién
# entonces se revisaba y se mandaba a la voz: la primera palabra sonaba
# tras la respuesta completa + la revisión + sintetizarla.

class Cancelled(Exception):
    """Quien recibe el texto en streaming cortó la respuesta (barge-in)."""


def _stream_chat(ollama_url: str, body: dict, on_piece, stop=None) -> dict:
    """POST a /api/chat con "stream": true. `on_piece(texto)` recibe cada
    trozo de contenido apenas llega; `stop()`, si devuelve True, corta la
    generación (se cierra la conexión y Ollama deja de generar). Devuelve lo
    mismo que la petición sin streaming (message con content/tool_calls,
    eval_count…) más "stopped" si se cortó."""
    content, tool_calls, last = [], [], {}
    stopped = False
    with llm_remote.post(ollama_url, json={**body, "stream": True}, stream=True, timeout=120) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            if chunk.get("error"):
                raise requests.exceptions.RequestException(chunk["error"])
            message = chunk.get("message") or {}
            tool_calls += message.get("tool_calls") or []
            piece = message.get("content") or ""
            if piece:
                content.append(piece)
                on_piece(piece)
            if chunk.get("done"):
                last = chunk
                break
            if stop and stop():
                stopped = True
                break
    message = {"role": "assistant", "content": "".join(content)}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {**last, "message": message, "stopped": stopped}


# Fin de frase para soltar el primer trozo y para trocear la voz: . ! ? … :
# o ; (con lo que cierre detrás: comillas, paréntesis) seguidos de espacio,
# o un salto de línea. Es puntuación: sirve en cualquier idioma.
_SPEECH_BREAK_RE = re.compile(r"[.!?…:;。！？]+[\"'»”’)\]]*(?:\s+|$)|\n+")


class _Release:
    """Lo que el usuario ya vio/oyó de la ronda en curso. El texto se suelta
    (on_text("delta", …)) apenas se puede: cuando `gate()` lo permite (la
    revisión previa ya dijo que no faltaba una herramienta) y el comienzo
    no parece una llamada a herramienta escrita como texto. Si después la
    ronda se descarta (llamó una herramienta, el revisor pidió otra
    respuesta…), on_text("reset", "") para que la página lo borre y corte
    la voz."""

    def __init__(self, on_text, tool_names, gate=None, hold_if=None):
        self.on_text = on_text
        self.tool_names = tool_names
        self.gate = gate
        self.hold_if = hold_if  # texto → True si desde ahí ya no conviene soltar nada (acotaciones)
        self.out = ""    # ya entregado en esta respuesta
        self.held = ""   # recibido y todavía retenido

    def feed(self, piece: str) -> None:
        self.held += piece
        self.release()

    def release(self) -> None:
        if not self.held or (self.gate and not self.gate()):
            return
        if self.hold_if and self.hold_if(self.out + self.held):
            return
        if not self.out:
            text = _INVISIBLE_RE.sub("", self.held).lstrip()
            # Una llamada escrita como texto ('[TOOL_CALLS]…', '{"name"…',
            # 'web_search{…}'): se retiene la ronda entera (ver _text_tool_calls).
            if text[:1] in ("[", "{", "`", "<") or _leaked_tool_call(text, self.tool_names):
                return
            if len(text) < 12 and not _SPEECH_BREAK_RE.search(text):
                return
            self.held = text
        self.on_text("delta", self.held)
        self.out += self.held
        self.held = ""

    def reset(self) -> None:
        if self.out:
            self.on_text("reset", "")
        self.out = self.held = ""

    def finish(self, final: str, clean=lambda t: t.strip()) -> None:
        """La respuesta quedó aceptada como `final`: se entrega lo retenido
        o, si cambió (reescrita en otro idioma, sin acotaciones), se
        reemplaza lo dicho."""
        streamed = self.out + self.held
        if clean(streamed) == clean(final):
            if self.held:
                self.on_text("delta", self.held)
        else:
            if self.out:
                self.on_text("reset", "")
            self.on_text("delta", final)
        self.out = self.held = ""


class SpeechChunker:
    """Junta el texto que llega en streaming y devuelve frases completas
    para la voz (cortadas por . ! ? : ; o salto de línea), de al menos
    `min_chars` para no pagar el costo fijo de cada síntesis en frases
    sueltas muy cortas. Si la primera frase es muy larga se corta en una
    coma: es la única que se espera antes de oír algo."""

    def __init__(self, min_chars: int = 20, first_max: int = 140):
        self.min_chars = min_chars
        self.first_max = first_max
        self.buf = ""
        self.started = False

    def feed(self, text: str) -> list:
        self.buf += text
        out = []
        while True:
            cut = next((m.end() for m in _SPEECH_BREAK_RE.finditer(self.buf)
                        if len(self.buf[:m.end()].strip()) >= self.min_chars and not self._initial(m.start())), None)
            if cut is None and not self.started and len(self.buf) > self.first_max:
                comma = re.search(r"^.{40,%d}?[,;]\s" % self.first_max, self.buf, re.S)
                cut = comma.end() if comma else None
            if cut is None:
                return out
            sentence, self.buf = self.buf[:cut].strip(), self.buf[cut:]
            if sentence:
                out.append(sentence)
                self.started = True

    def _initial(self, i: int) -> bool:
        """¿El punto en `i` cierra una inicial o abreviatura de una letra
        ("509 a. C.", "J. R. R.")? Ahí no se corta la frase."""
        return (self.buf[i] == "." and i >= 1 and self.buf[i - 1].isalpha()
                and (i == 1 or not self.buf[i - 2].isalnum()))

    def flush(self) -> list:
        rest, self.buf = self.buf.strip(), ""
        return [rest] if rest else []

    def reset(self) -> None:
        self.buf = ""
        self.started = False


# Antes de la primera ronda (solo con streaming), y en paralelo con ella:
# ¿el pedido necesita una herramienta? Es la parte "needed_tool" del
# revisor, juzgada sin borrador. Visto: a "¿qué tiempo hace hoy?" gemma4
# respondía de memoria (inventando el pronóstico) en vez de llamar
# get_weather, y lo atajaba el revisor. Con la respuesta ya sonando, eso se
# oiría y después se corregiría: por eso se pregunta ANTES de soltar el
# texto. Corre a la vez que la ronda (OLLAMA_NUM_PARALLEL=2), así que no
# suma espera: la primera frase suele tardar lo mismo.
# (Probado también como nota al final de la misma conversación, para
# compartir lo ya procesado por Ollama: tardaba el doble, 1,1 s, y juzgaba
# peor, influido por la personalidad.)
_PRECHECK_SYSTEM = """You help a voice assistant{who} decide, before it answers, whether it must use a tool. You only judge; you never write the reply.

The assistant can use these tools:
{tools}

Read the user's LAST message (lines starting with USER), in whatever language it is in, and judge its meaning in the context of the conversation, not individual words. Files, images and audio transcriptions the user attached ("[Attached ...]") are already part of the conversation: questions about them need no tool (except converting a file to another format, which needs convert_file).
needed_tool: does a correct answer need one of these tools RIGHT NOW? That is: real-time, local or external information the assistant can't know by itself (current weather, news, prices, scores, distances, nearby places, facts that change over time), or an action (like playing music, setting a reminder or timer, saving to a list, or bringing someone into the conversation). Today is {today}: anything about the latest, current or most recent something (last champion, current version, who holds a post now, ages), or about events from the last two years, needs a search, because the assistant's own knowledge may be out of date. Pick that tool, or "none". It's "none" for greetings and small talk, for stable knowledge that doesn't change (capitals, science, history, how things work, definitions), for suggestions, ideas or opinions the assistant can give by itself (what to cook, gift ideas, what it thinks), when the message only mentions a topic without asking for new information or an action (chatting about rainy days, thanking for a forecast already given), when that information already came in a TOOL RESULT of this conversation, when general knowledge or the assistant's own opinion is enough, or when the action makes no sense for this assistant (e.g. being asked to invite itself). It's also "none" when none of the tools does what's asked (e.g. closing a program when there's only a tool to open them): the assistant will just say so; never pick a tool that would do something different.
Write "reasoning" first: one short sentence."""

_POOL = None


def _pool():
    global _POOL
    if _POOL is None:
        from concurrent.futures import ThreadPoolExecutor

        _POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="precheck")
    return _POOL


def _needs_tool(ollama_url, model, keep_alive, tools, history, assistant_name=None):
    """{"reasoning", "needed_tool", "seconds"} o None si falló."""
    tool_lines = "\n".join(
        f"- {t['function']['name']}: {_clip(t['function'].get('description', ''), 300)}" for t in tools
    )
    schema = {
        "type": "object",
        "properties": {
            "reasoning": {"type": "string"},
            "needed_tool": {"type": "string", "enum": ["none", *(t["function"]["name"] for t in tools)]},
        },
        "required": ["reasoning", "needed_tool"],
    }
    messages = [
        {"role": "system", "content": _PRECHECK_SYSTEM.format(
            tools=tool_lines, who=f" called {assistant_name} (its replies are the ASSISTANT lines)" if assistant_name else "",
            today=time.strftime("%Y-%m-%d"))},
        {"role": "user", "content": render_transcript(history, last=6)},
    ]
    # Que la ronda llegue primero a Ollama: con dos peticiones a la vez,
    # cada una suele tomar la "ranura" con más prompt en común y conservar
    # lo ya procesado; si llegaban juntas a veces se cruzaban y la ronda
    # volvía a leer las ~5000 fichas del prompt (0,8 s en vez de 0,1 s).
    time.sleep(0.05)
    t0 = time.time()
    data = structured_request(ollama_url, model, messages, schema, keep_alive, max_tokens=120)
    return ({**data, "seconds": round(time.time() - t0, 2)}) if data else None


def ask_with_tools(
    ollama_url: str,
    model: str,
    personality: str,
    history: list,
    tools: list,
    call_tool_fn,
    max_tool_rounds: int,
    fallback_message: str,
    on_tool_call=None,
    reply_lang: str = None,
    shared_context: str = None,
    temperature: float = 0.7,
    top_k: int = 64,
    top_p: float = 0.95,
    keep_alive=MODEL_KEEP_ALIVE,
    on_event=None,
    style: str = None,
    auto_langs=None,
    info: dict = None,
    assistant_name: str = None,
    on_text=None,
    dynamic_context: str = None,
    expressiveness: str = "lots",
) -> str:
    """Lógica común de conversación con herramientas para cualquier
    asistente de assistants.yaml. Llama directo a `model` (el base_model de
    Ollama, sin Modelfile de por medio), con `personality` + `shared_context`
    como system prompt completo y `temperature`/`top_k`/`top_p` como
    parámetros de muestreo — todo configurable por asistente en
    assistants.yaml.

    Antes de dar por buena una respuesta, el mismo modelo la revisa
    (_review_draft): si el pedido necesitaba una herramienta que no llamó,
    se le pide que la llame (solo con esa herramienta disponible) y, si
    tampoco, se la llama directo con argumentos que genera el modelo con el
    esquema de la herramienta; si prometió hacer algo en vez de hacerlo o
    mandó al usuario a averiguar por su cuenta, se le pide una vez que lo
    resuelva; y si salió en otro idioma que el pedido, que la reescriba.

    `on_tool_call(tool_name)`, si se pasa, se llama justo antes de ejecutar
    una herramienta (p. ej. para anunciar "Buscando en internet..." por voz).

    `reply_lang`, si se pasa, le pide al modelo responder en ese idioma
    (ver `build_system_message`). `auto_langs`: sin `reply_lang`, responde
    en el idioma del último mensaje del usuario, que puede ser cualquiera
    de estos.

    `keep_alive`: cuánto se queda el modelo cargado tras la petición (ver
    MODEL_KEEP_ALIVE); el chat de la interfaz web usa uno finito.

    `on_event(tipo, detalle)`, si se pasa, recibe lo que pasa por dentro
    (para la consola de la interfaz web): "round" (n, segundos de Ollama),
    "review" (juicio del revisor), "retry" (motivo), "tool" (nombre,
    argumentos), "fallback".

    `style`: "voice" (respuestas cortas y naturales) o "text" (más
    detalladas si hace falta), ver RESPONSE_STYLES.

    `info`, si se pasa, se llena con {"language": idioma de la respuesta
    (según el revisor), "tools": herramientas usadas}.

    `assistant_name`: quién responde (para el revisor: "Jarvis, invita a
    Jarvis" no pide ninguna herramienta).

    `dynamic_context`: lo que cambia en cada turno (habilidades), al final
    del system prompt (ver build_system_message).

    `on_text(tipo, texto)`, si se pasa, activa el streaming: "delta" con
    cada trozo de la respuesta apenas se puede mostrar/decir y "reset" si
    lo ya entregado se descarta (ver _Release). Lo entregado tras el último
    "reset" es la respuesta que se devuelve (salvo limpiezas: emojis en
    voz). Si lanza una excepción (p. ej. la página se desconectó o
    Cancelled), corta la generación y la excepción sube.
    Con streaming, si hay herramientas, la pregunta "¿necesita una
    herramienta?" se hace antes y en paralelo con la primera ronda
    (_needs_tool) y, si no se usó ninguna herramienta y el idioma ya está
    fijado, no hace falta la revisión completa del borrador.
    """
    emit = on_event or (lambda kind, detail: None)
    written = style == "text"
    system_message = {
        "role": "system",
        "content": build_system_message(personality, shared_context, reply_lang, history, style, auto_langs,
                                        expressiveness=expressiveness),
    }
    working = [system_message] + list(history)
    # Lo que cambia en cada turno va al final (ver build_system_message), con
    # el recordatorio corto del estilo y el idioma.
    extra = "\n\n".join(p for p in (turn_context(history, dynamic_context),
                                     _turn_reminder(style, reply_lang, auto_langs)) if p)
    for i in range(len(working) - 1, 0, -1):
        if working[i].get("role") == "user":
            working[i] = {**working[i], "content": f"{working[i].get('content', '')}\n\n{extra}"}
            break
    else:
        working[0] = {**system_message, "content": system_message["content"] + "\n\n" + extra}
    tool_by_name = {t["function"]["name"]: t for t in tools}
    tools_called = []   # en orden, para el revisor y `info`
    tool_results = []   # (herramienta, resultado) de este turno, para el revisor
    done_calls = {}     # (herramienta, argumentos) → resultado: no se repite una acción en el mismo turno
    tool_rounds = 0     # rondas en que se usaron herramientas: lo que limita max_tool_rounds
    nudges = {}         # empujones por motivo (no gastan rondas de herramientas)
    reviews = 0
    only_tools = None   # tras pedirle una herramienta concreta, solo esa en la próxima petición
    empties = 0         # respuestas vacías (o invisibles) seguidas
    # Streaming (on_text): revisión previa en paralelo con la primera ronda.
    precheck = None
    if on_text and tools:
        precheck = _pool().submit(_needs_tool, ollama_url, model, keep_alive, tools, history, assistant_name)
    pre = {"done": precheck is None, "result": None}

    def pre_verdict():
        """Lo que dijo la revisión previa, si ya terminó (y solo una vez
        por turno se tiene en cuenta)."""
        if not pre["done"] and precheck.done():
            pre["done"] = True
            try:
                pre["result"] = precheck.result()
            except Exception:  # noqa: BLE001 — sin revisión previa, la completa decide
                pre["result"] = None
            if pre["result"]:
                emit("precheck", pre["result"])
        return pre["result"]

    def pre_needed():
        """La herramienta que según la revisión previa hacía falta y no se llamó.
        Si el modelo ya llamó alguna, decide él (la revisión completa ve los
        resultados; la previa no)."""
        needed = (pre_verdict() or {}).get("needed_tool")
        if tools_called:
            return None
        return needed if needed in tool_by_name and needed not in tools_called else None

    def gate():
        pre_verdict()
        # Por voz, la respuesta que sigue a una herramienta espera al revisor
        # (¿contradice el resultado?): si pide rehacerla, lo ya dicho no se
        # puede desdecir y se oía cortado. En el chat escrito se muestra
        # mientras tanto (si cambia, se reemplaza en pantalla).
        if not written and tool_results and reviews < MAX_REVIEWS:
            return False
        return pre["done"] and not pre_needed()

    # Por voz, una acotación ("(se ríe)", "*suspira*") hará pedir otra
    # respuesta: desde ahí no se suelta nada más (ver _STAGE_RE abajo).
    release = _Release(on_text, list(tool_by_name), gate=gate,
                       hold_if=None if written else _STAGE_RE.search) if on_text else None

    def ask_for_tool(needed: str, draft: str, why: str) -> bool:
        """Hacía falta `needed` y no la llamó: se le pide una vez (solo con
        esa herramienta) y, si no, se la llama directo. False si no se pudo."""
        nonlocal only_tools, tool_rounds
        takes_args = bool((tool_by_name[needed]["function"].get("parameters") or {}).get("properties"))
        if takes_args and not nudges.get(needed):
            nudges[needed] = 1
            only_tools = [tool_by_name[needed]]
            emit("retry", {"reason": f"hacía falta {needed} y no la llamó (se le pide{why})", "text": draft[:120]})
            working.append({"role": "user", "content": (
                f"That needs real data: call the tool {needed} now (tool calling), in this same turn, "
                "instead of answering from memory."
            )})
            return True
        if call_directly(needed, draft):
            tool_rounds += 1
            return True
        return False

    def run_tools(calls):
        """Ejecuta llamadas a herramientas (del modelo o forzadas) y deja
        el resultado en la conversación."""
        if on_tool_call:
            for name in dict.fromkeys(c.get("function", {}).get("name", "") for c in calls):
                on_tool_call(name)
        for call in calls:
            fn = call.get("function", {})
            name, args = fn.get("name", ""), fn.get("arguments", {}) or {}
            tools_called.append(name)
            key = (name, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str))
            if key in done_calls:
                # Visto: tras un empujón del revisor el modelo volvía a llamar
                # set_reminder con lo mismo y quedaban dos temporizadores.
                emit("retry", {"reason": f"repitió {name} con los mismos datos: no se ejecuta otra vez", "text": ""})
                result = ("You already called it with exactly these arguments in this turn, so it was not run "
                          "again. Its result was: " + done_calls[key] + " Answer the user now according to that "
                          "result, without calling it again with the same arguments.")
                tool_results.append((name, result))
                working.append({"role": "tool", "content": result})
                continue
            emit("tool", {"name": name, "arguments": args})
            result = call_tool_fn(name, args)
            done_calls[key] = result
            tool_results.append((name, result))
            working.append({"role": "tool", "content": result})

    def call_directly(name: str, draft: str) -> bool:
        args = _tool_arguments(ollama_url, model, keep_alive, tool_by_name[name], history, tool_results)
        if args is None:
            return False
        emit("retry", {"reason": f"no llamó {name}; se la llama directo", "text": draft[:120]})
        call = {"function": {"name": name, "arguments": args}}
        working.append({"role": "assistant", "content": "", "tool_calls": [call]})
        run_tools([call])
        return True

    # Tope duro de peticiones: rondas de herramientas + empujones/reintentos
    # + una última sin herramientas para que siempre pueda responder.
    for round_no in range(1, max_tool_rounds + 7):
        # Agotadas las rondas de herramientas, se le piden sin herramientas:
        # tiene que redactar la respuesta con lo que ya obtuvo.
        final_only = tool_rounds >= max_tool_rounds
        body = {
            "model": model,
            "think": False,  # no todos los modelos soportan "thinking"; Ollama lo ignora si no aplica
            "messages": working,
            "options": {
                "temperature": temperature,
                "top_k": top_k,
                "top_p": top_p,
            },
            # Se queda cargado MODEL_KEEP_ALIVE tras esta petición (en vez
            # del default de Ollama, 5 min) para no recargarlo entre turnos;
            # unload_ollama_model() lo descarga explícitamente al cerrar el
            # script. Solo afecta al modelo de esta petición.
            "keep_alive": keep_alive,
        }
        # Tras dos respuestas vacías seguidas, sin herramientas: con ellas a
        # mano Nemo se trababa entre llamar una y contestar.
        if not final_only and tools and empties < 2:
            body["tools"] = only_tools or tools
        only_tools = None
        t0 = time.time()
        if release:
            # El texto se suelta mientras llega (ver _Release); si la revisión
            # previa dice que faltaba una herramienta, se corta la ronda.
            data = _stream_chat(ollama_url, body, release.feed, stop=lambda: bool(pre_needed()))
        else:
            r = llm_remote.post(ollama_url, json={**body, "stream": False}, timeout=120)
            r.raise_for_status()
            data = r.json()
        message = data["message"]
        emit("round", {
            "n": round_no,
            "seconds": round(time.time() - t0, 2),
            "load_seconds": round((data.get("load_duration") or 0) / 1e9, 2),
            "tokens": data.get("eval_count"),
            "prompt_seconds": round((data.get("prompt_eval_duration") or 0) / 1e9, 2),
            "stream": bool(release),
            "remote": llm_remote.is_remote(model),
        })

        tool_calls = None if final_only else message.get("tool_calls")
        if tool_calls:
            if release:
                release.reset()
            # Se descarta el texto que haya venido junto con tool_calls (a
            # veces redacta "te pongo la música" en el mismo turno que la
            # llamada): dejarlo confunde al modelo en la ronda siguiente.
            working.append({**message, "content": ""})
            run_tools(tool_calls)
            tool_rounds += 1
            continue

        content = _INVISIBLE_RE.sub("", message.get("content") or "").strip()
        # Revisión previa (en paralelo con esta ronda): si faltaba una
        # herramienta, se pide antes de soltar el borrador.
        if precheck is not None and not final_only:
            if not pre["done"]:
                try:
                    precheck.result(timeout=60)
                except Exception:  # noqa: BLE001
                    pass
            needed = pre_needed()
            if needed:
                release.reset()
                if ask_for_tool(needed, content, ", según la revisión previa"):
                    continue
                pre["result"] = None  # no se pudo: sigue como si no hubiera dicho nada
        if release:
            release.release()  # lo retenido mientras se esperaba la revisión previa
        if not content:
            if release:
                release.reset()
            empties += 1
            invisible = bool(message.get("content"))
            emit("retry", {"reason": "respuesta vacía" + (" (solo caracteres invisibles)" if invisible else "")
                           + ("; la próxima, sin herramientas" if empties == 2 else ""), "text": ""})
            continue  # traspié puntual del modelo: reintenta
        empties = 0
        written_calls = [] if final_only else _text_tool_calls(content, tool_by_name)
        if written_calls:
            if release:
                release.reset()
            emit("retry", {"reason": "escribió la llamada como texto: se ejecuta igual", "text": content[:120]})
            working.append({"role": "assistant", "content": "", "tool_calls": written_calls})
            run_tools(written_calls)
            tool_rounds += 1
            continue
        if not final_only and nudges.get("leak", 0) < 2 and _leaked_tool_call(content, tool_by_name):
            if release:
                release.reset()
            nudges["leak"] = nudges.get("leak", 0) + 1
            emit("retry", {"reason": "escribió la herramienta en vez de llamarla", "text": content[:120]})
            working.append({"role": "user", "content": (
                "Don't write the tool's name or its call in your reply (it's read aloud): if you need it, "
                "call it right now with the tool calling mechanism; otherwise just answer."
            )})
            continue

        # Revisión completa del borrador. Con streaming el borrador ya se está
        # mostrando/diciendo mientras tanto; si pide otra respuesta, "reset".
        # Se omite cuando no aporta: la revisión previa ya dijo que no hacía
        # falta ninguna herramienta, no se usó ninguna (nada que contradecir)
        # y el idioma de la respuesta está fijado (no hay que averiguarlo).
        # Así una pregunta sin herramientas se resuelve con una ronda (más la
        # revisión previa, que corre a la vez).
        review = None
        skip_review = bool(pre["result"]) and not tool_results and bool(reply_lang) and not final_only
        if reviews < MAX_REVIEWS and not skip_review:
            reviews += 1
            t0 = time.time()
            review = _review_draft(ollama_url, model, keep_alive, tools, history, tool_results, content, assistant_name,
                                   style)
            if review:
                emit("review", {**review, "seconds": round(time.time() - t0, 2)})
        elif skip_review:
            emit("review_skipped", {})
        if review and not final_only:
            needed = review.get("needed_tool")
            if needed in tool_by_name and needed not in tools_called:
                if release:
                    release.reset()
                if ask_for_tool(needed, content, ""):
                    continue
        problem = (review or {}).get("draft_problem", "none") if not final_only else "none"
        # Por voz, los paréntesis o asteriscos largos son acotaciones; en
        # el chat escrito no (un "(25 °C)" o un **negrita**).
        if problem == "none" and not written and not final_only and _STAGE_RE.search(content):
            problem = "not_speakable"
        if problem in _REVIEW_NUDGES and not nudges.get(problem):
            if release:
                release.reset()
            nudges[problem] = 1
            emit("retry", {"reason": f"borrador con problema: {problem}", "text": content[:120]})
            working.append({"role": "assistant", "content": content})
            nudge = _TEXT_NUDGES[problem] + _ANSWER_AGAIN if written and problem in _TEXT_NUDGES else _REVIEW_NUDGES[problem]
            if written:
                nudge = nudge.replace(", in a few words", "").replace(" in a few words", "")
            working.append({"role": "user", "content": nudge})
            continue

        language = (review or {}).get("draft_language")
        if reply_lang and language in LANGUAGE_PROMPT_NAMES and language != reply_lang:
            content = _rewrite_in_language(content, reply_lang, language, working, model, ollama_url, keep_alive,
                                           {"temperature": temperature, "top_k": top_k, "top_p": top_p}, emit)
            language = reply_lang
        if info is not None:
            info["language"] = reply_lang or (language if language in (auto_langs or LANGUAGE_PROMPT_NAMES) else None)
            info["tools"] = list(tools_called)
        if written:
            # Chat escrito: markdown y emojis se quedan (la página los muestra
            # y los quita antes de leerlo en voz alta).
            content = content.strip()
            if release:
                release.finish(content)
            return content
        if nudges.get("not_speakable"):
            # Ya se le pidió una vez y volvió a escribir acotaciones: se quitan.
            content = _STAGE_RE.sub("", content)
        content = re.sub(r"[ \t]{2,}", " ", _EMOJI_RE.sub("", content)).strip() or content
        if release:
            release.finish(content, clean=lambda t: re.sub(r"\s+", " ", _EMOJI_RE.sub("", t)).strip())
        return content

    emit("fallback", {"rounds": round_no})
    if info is not None:
        info["language"] = reply_lang
        info["tools"] = list(tools_called)
    if release:
        release.finish(fallback_message)
    return fallback_message


def _rewrite_in_language(content, reply_lang, got, working, model, ollama_url, keep_alive, options, emit) -> str:
    """La respuesta salió en otro idioma que el pedido (pasa con modelos
    chicos): se le pide al mismo modelo que la reescriba. El idioma en que
    salió lo dice el revisor, así que sirve para cualquiera de los 31."""
    name = language_label(reply_lang)
    emit("retry", {"reason": f"respondió en '{got}' en vez de '{reply_lang}'; se le pide reescribirla", "text": content[:120]})
    body = {
        "model": model,
        "think": False,
        "stream": False,
        "messages": working + [
            {"role": "assistant", "content": content},
            {"role": "user", "content": (
                f"Rewrite your previous answer in {name}. Keep the same meaning, tone and length. "
                f"Reply with only the rewritten answer, entirely in {name}."
            )},
        ],
        "options": options,
        "keep_alive": keep_alive,
    }
    try:
        r = llm_remote.post(ollama_url, json=body, timeout=120)
        r.raise_for_status()
        rewritten = (r.json().get("message", {}).get("content") or "").strip()
    except (requests.exceptions.RequestException, ValueError):
        return content
    return rewritten or content


def unload_ollama_model(model_name: str, ollama_url: str = "http://127.0.0.1:11434/api/chat") -> None:
    """Le pide a Ollama que descargue el modelo de memoria (RAM/VRAM) de inmediato.

    Por defecto Ollama mantiene un modelo cargado ~5 minutos tras la última
    petición (keep_alive), incluso si el script que lo usaba ya terminó. Con
    keep_alive=0 y sin mensajes, Ollama lo descarga sin generar nada.
    """
    try:
        llm_remote.post(
            ollama_url,
            json={"model": model_name, "messages": [], "keep_alive": 0},
            timeout=10,
        )
    except requests.exceptions.RequestException:
        pass  # si Ollama ya no responde, no hay nada que descargar
