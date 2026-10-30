"""
Skill de música para JARVIS/BELLA: buscar y reproducir canciones, artistas,
playlists o música de un género/ambiente en Spotify.

Funciona en dos niveles, según `spotify_config.yaml` (llenado por
spotify_setup.bat):

- **Con Spotify Premium** (`premium: true` + sesión iniciada): controla la
  reproducción de verdad a través de la API oficial (Spotify Connect) —
  reproducir, pausar, reanudar, saltar canción, volumen — en cualquier
  dispositivo donde el usuario tenga Spotify abierto.
- **Sin Premium** (cuenta gratuita): la API de Spotify no permite controlar
  la reproducción sin Premium, así que en su lugar se abre la app de
  Spotify local (o el navegador) directo en la canción/playlist buscada,
  como si el usuario le hubiera dado clic — funciona igual de bien para
  "poné tal canción", solo que sin pausar/saltar/volumen por voz después.

La BÚSQUEDA (encontrar la canción/playlist/artista) funciona igual en
ambos casos: usa credenciales de la app (Client ID/Secret), sin necesitar
que el usuario haya iniciado sesión — por eso siempre está disponible en
cuanto spotify_config.yaml tiene client_id/client_secret, tenga o no
Premium.
"""
import os
import sys
import time
import webbrowser

import requests
import yaml

from app.paths import SPOTIFY_YAML as CONFIG_PATH

TOKEN_URL = "https://accounts.spotify.com/api/token"
SEARCH_URL = "https://api.spotify.com/v1/search"
PLAYER_URL = "https://api.spotify.com/v1/me/player"

_SEARCH_TYPE_BY_TIPO = {
    "cancion": "track",
    "artista": "artist",
    "playlist": "playlist",
    "genero_o_ambiente": "playlist",
}

_app_token_cache = {"token": None, "expires_at": 0.0}
_user_token_cache = {"token": None, "expires_at": 0.0}


class _NoActiveDeviceError(Exception):
    """No hay ningún Spotify abierto en ningún dispositivo ahora mismo."""


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def is_configured() -> bool:
    cfg = _load_config()
    return bool(cfg.get("client_id") and cfg.get("client_secret"))


def _get_app_token() -> str:
    """Token de solo-app (Client Credentials) — sirve para buscar, no para
    controlar reproducción. No requiere que el usuario haya iniciado sesión."""
    now = time.time()
    if _app_token_cache["token"] and now < _app_token_cache["expires_at"]:
        return _app_token_cache["token"]

    cfg = _load_config()
    r = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(cfg.get("client_id", ""), cfg.get("client_secret", "")),
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    _app_token_cache["token"] = data["access_token"]
    _app_token_cache["expires_at"] = now + data.get("expires_in", 3600) - 60
    return _app_token_cache["token"]


def _get_user_token() -> str:
    """Token de usuario (refresh_token de spotify_config.yaml) — hace
    falta para controlar la reproducción de verdad. Solo existe si el
    usuario completó el login en spotify_setup.bat (Premium)."""
    now = time.time()
    if _user_token_cache["token"] and now < _user_token_cache["expires_at"]:
        return _user_token_cache["token"]

    cfg = _load_config()
    if not cfg.get("refresh_token"):
        raise RuntimeError("no hay sesión de Spotify iniciada (correr spotify_setup.bat)")

    r = requests.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": cfg["refresh_token"]},
        auth=(cfg.get("client_id", ""), cfg.get("client_secret", "")),
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    _user_token_cache["token"] = data["access_token"]
    _user_token_cache["expires_at"] = now + data.get("expires_in", 3600) - 60
    return _user_token_cache["token"]


def _search_best(query: str, search_type: str):
    """Busca `query` en Spotify (tipo `search_type`: track/artist/playlist)
    y devuelve {"uri", "name"} del primer resultado, o None si no hay
    nada. Usa el token de app (no requiere login de usuario)."""
    token = _get_app_token()
    r = requests.get(
        SEARCH_URL,
        params={"q": query, "type": search_type, "limit": 1},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    items = ((data.get(search_type + "s") or {}).get("items")) or []
    items = [it for it in items if it]  # Spotify a veces mete null en la lista
    if not items:
        return None
    item = items[0]
    return {"uri": item["uri"], "name": item.get("name") or query}


def _play_on_device(uri: str, search_type: str):
    """Reproduce `uri` en el/los dispositivo(s) activo(s) de Spotify del
    usuario, vía la API real (requiere Premium + sesión iniciada)."""
    token = _get_user_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # Una canción suelta se manda como "uris"; una playlist/artista se manda
    # como "context_uri" para que siga con más canciones de lo mismo en vez
    # de reproducir un solo track y parar.
    body = {"uris": [uri]} if search_type == "track" else {"context_uri": uri}

    r = requests.put(PLAYER_URL + "/play", headers=headers, json=body, timeout=10)
    if r.status_code == 404:
        raise _NoActiveDeviceError()
    r.raise_for_status()


def _launch_locally(uri: str):
    """Abre `uri` con la app de Spotify instalada en esta PC (protocolo
    spotify:...) — funciona con cuenta gratuita, pero no se puede
    controlar después desde acá: es como si el usuario le diera clic él
    mismo."""
    if sys.platform == "win32":
        os.startfile(uri)
    else:
        webbrowser.open(uri)


PLAY_MUSIC_TOOL = {
    "type": "function",
    "function": {
        "name": "play_music",
        "description": (
            "Find and play music on Spotify: a specific song, an artist, a named playlist, or music "
            "for a genre/mood/activity (e.g. studying, reggaeton, relaxing to sleep, working out). "
            "Call it whenever the user wants music played. Needs Spotify open on one of the user's "
            "devices (phone, computer, etc.)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to play: song title, artist, playlist name, or a short description of the genre/mood.",
                },
                "tipo": {
                    "type": "string",
                    "enum": list(_SEARCH_TYPE_BY_TIPO),
                    "description": (
                        "What kind of search 'query' is: 'cancion' (a specific song title), "
                        "'artista' (an artist/band name), 'playlist' (a playlist with a specific "
                        "name) or 'genero_o_ambiente' (a genre, mood or activity — when nothing "
                        "specific was asked for)."
                    ),
                },
            },
            "required": ["query", "tipo"],
        },
    },
}

PAUSE_MUSIC_TOOL = {
    "type": "function",
    "function": {"name": "pause_music", "description": "Pause Spotify playback.", "parameters": {"type": "object", "properties": {}}},
}
RESUME_MUSIC_TOOL = {
    "type": "function",
    "function": {"name": "resume_music", "description": "Resume Spotify playback where it stopped.", "parameters": {"type": "object", "properties": {}}},
}
SKIP_MUSIC_TOOL = {
    "type": "function",
    "function": {"name": "skip_music", "description": "Skip to the next song on Spotify.", "parameters": {"type": "object", "properties": {}}},
}
PREVIOUS_MUSIC_TOOL = {
    "type": "function",
    "function": {"name": "previous_music", "description": "Go back to the previous song on Spotify.", "parameters": {"type": "object", "properties": {}}},
}
SET_VOLUME_TOOL = {
    "type": "function",
    "function": {
        "name": "set_music_volume",
        "description": "Set Spotify's volume to a specific percentage.",
        "parameters": {
            "type": "object",
            "properties": {"porcentaje": {"type": "integer", "description": "Desired volume, 0 to 100."}},
            "required": ["porcentaje"],
        },
    },
}

# Reproducir/buscar siempre está disponible (no requiere login de usuario).
# Pausar/reanudar/saltar/volumen SOLO si hay Premium + sesión iniciada — la
# API de Spotify no los permite sin eso, así que ni se le ofrecen al modelo
# para que no intente usarlos y falle. Se decide una vez al importar (se
# actualiza si corrés spotify_setup.bat y reiniciás el script).
TOOLS = [PLAY_MUSIC_TOOL]
if _load_config().get("premium") and _load_config().get("refresh_token"):
    TOOLS += [PAUSE_MUSIC_TOOL, RESUME_MUSIC_TOOL, SKIP_MUSIC_TOOL, PREVIOUS_MUSIC_TOOL, SET_VOLUME_TOOL]


def play_music(query: str, tipo: str) -> str:
    if not is_configured():
        return "Spotify todavía no está configurado en esta instalación (hace falta correr spotify_setup.bat una vez)."

    search_type = _SEARCH_TYPE_BY_TIPO.get(tipo, "track")
    try:
        item = _search_best(query, search_type)
    except Exception as e:
        return f"No se pudo buscar en Spotify ahora mismo ({e})."

    if not item:
        return f"No encontré nada en Spotify para '{query}'."

    cfg = _load_config()
    if cfg.get("premium") and cfg.get("refresh_token"):
        try:
            _play_on_device(item["uri"], search_type)
            return f"Reproduciendo {item['name']} en Spotify."
        except _NoActiveDeviceError:
            return "No encontré ningún Spotify abierto ahora mismo. Abrí Spotify en el celular o la computadora y pedímelo de nuevo."
        except Exception as e:
            return f"No se pudo reproducir en Spotify ({e})."
    else:
        try:
            _launch_locally(item["uri"])
            return f"Abriendo {item['name']} en Spotify."
        except Exception as e:
            return f"No se pudo abrir Spotify ({e})."


def pause_music() -> str:
    try:
        token = _get_user_token()
        r = requests.put(PLAYER_URL + "/pause", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 404:
            return "No hay ningún Spotify activo para pausar."
        r.raise_for_status()
        return "Pausado."
    except Exception as e:
        return f"No se pudo pausar Spotify ({e})."


def resume_music() -> str:
    try:
        token = _get_user_token()
        r = requests.put(PLAYER_URL + "/play", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 404:
            return "No hay ningún Spotify activo para reanudar."
        r.raise_for_status()
        return "Reanudado."
    except Exception as e:
        return f"No se pudo reanudar Spotify ({e})."


def skip_music() -> str:
    try:
        token = _get_user_token()
        r = requests.post(PLAYER_URL + "/next", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 404:
            return "No hay ningún Spotify activo."
        r.raise_for_status()
        return "Saltado a la siguiente canción."
    except Exception as e:
        return f"No se pudo saltar la canción ({e})."


def previous_music() -> str:
    try:
        token = _get_user_token()
        r = requests.post(PLAYER_URL + "/previous", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 404:
            return "No hay ningún Spotify activo."
        r.raise_for_status()
        return "Volviendo a la canción anterior."
    except Exception as e:
        return f"No se pudo volver a la canción anterior ({e})."


def set_music_volume(porcentaje) -> str:
    try:
        porcentaje = max(0, min(100, int(porcentaje)))
        token = _get_user_token()
        r = requests.put(
            PLAYER_URL + "/volume",
            params={"volume_percent": porcentaje},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if r.status_code == 404:
            return "No hay ningún Spotify activo."
        r.raise_for_status()
        return f"Volumen puesto en {porcentaje} por ciento."
    except Exception as e:
        return f"No se pudo cambiar el volumen ({e})."


def call_tool(name: str, arguments: dict):
    """Devuelve el resultado si `name` es una de las herramientas de este
    módulo, o None si no la reconoce (para que el que llama pruebe otras)."""
    if name == "play_music":
        return play_music(arguments.get("query", ""), arguments.get("tipo", "cancion"))
    if name == "pause_music":
        return pause_music()
    if name == "resume_music":
        return resume_music()
    if name == "skip_music":
        return skip_music()
    if name == "previous_music":
        return previous_music()
    if name == "set_music_volume":
        return set_music_volume(arguments.get("porcentaje", 50))
    return None
