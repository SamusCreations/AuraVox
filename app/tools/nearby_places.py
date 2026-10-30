"""
Búsqueda de lugares reales cerca de la ubicación del usuario (restaurantes,
farmacias, gasolineras, etc.) para JARVIS y BELLA.

Usa dos servicios de OpenStreetMap, gratis y sin API key:
- Overpass API: busca por CATEGORÍA real (etiquetas de OSM, p. ej.
  amenity=gym) dentro de un radio del punto — da negocios de verdad. Es la
  vía principal para categorías conocidas (ver CATEGORY_TAGS).
- Nominatim: geocodificador de texto libre, se usa de respaldo para
  nombres propios ("Starbucks", "el Walmart de Alajuela") o categorías que
  no están en CATEGORY_TAGS, y para resolver USER_CONTEXT['ubicacion'] a
  coordenadas si no hay latitud/longitud configuradas.

Por qué dos servicios: Nominatim solo hace búsqueda de texto libre, así
que "gimnasio" podía devolver una CALLE llamada "Calle El Gimnasio" en vez
de un gimnasio real — no hay forma de pedirle "solo negocios de esta
categoría". Overpass sí permite filtrar por la etiqueta real del lugar
(amenity/shop/leisure), así que ya no confunde nombres de calles con
negocios.

La categoría la elige el MODELO de una lista cerrada en inglés (parámetro
`category` de la herramienta, ver CATEGORY_TAGS): entiende "¿dónde hay una
botica?", "аптека рядом" o "近くの薬局" y elige "pharmacy". Antes se
adivinaba buscando palabras ("farmacia", "pharmacy", "drugstore"…) en lo
que mandaba el modelo, y había que escribir sinónimos para cada idioma.

Si `USER_CONTEXT` (assistant_common.py, viene de assistants.yaml →
user_context) trae `latitud`/`longitud`, se usan directas — más precisas y
sin gastar una llamada de red. Si no, se geocodifica una sola vez
`ubicacion` (texto) y se cachea en memoria.
"""
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, wait

import requests

from app.core.assistant_common import USER_CONTEXT

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Espejos públicos de la misma API: si el principal está saturado (pasa
# seguido: 504 o timeout), se prueba el siguiente en vez de caer directo a
# Nominatim, que solo busca la palabra en el NOMBRE del lugar y devolvía
# "Restaurante X" a 17 km teniendo restaurantes a 2 km.
# (overpass.kumi.systems se quitó: en las pruebas nunca respondió a tiempo.)
OVERPASS_URLS = [
    OVERPASS_URL,
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
# Ambos servicios exigen un User-Agent identificable (política de uso justo).
_HEADERS = {"User-Agent": "jarvis-bella-asistente-personal/1.0 (uso personal)"}

# ══════════════════════════════════════════════════════════════════════
# PLANTILLA DE PARÁMETROS — edita estos valores cuando quieras
# ══════════════════════════════════════════════════════════════════════
CONFIG = {
    "radius_degrees": 0.15,  # ~15 km de margen (usado por Nominatim/geocodificación)
    "radius_meters": 15000,  # mismo radio para Overpass, en metros
    "near_radius_meters": 5000,  # primero se busca aquí; si hay menos de 3, en radius_meters
    "max_results": 6,
    "timeout_seconds": 8,
}
# ══════════════════════════════════════════════════════════════════════

# Categoría (lo que el modelo elige en `category`) → etiquetas OSM (clave,
# valor) que la representan. Se buscan TODAS con Overpass (nodos Y ways)
# dentro del radio — así se filtra por lo que el lugar REALMENTE ES en
# OpenStreetMap, no por si su nombre/calle contiene la palabra buscada. Para
# agregar una categoría nueva, solo hace falta un renglón aquí (ver
# https://wiki.openstreetmap.org/wiki/Map_features): el modelo la ve sola
# en la lista de la herramienta.
CATEGORY_TAGS = {
    "restaurant": [("amenity", "restaurant")],
    "fast_food": [("amenity", "fast_food")],
    "cafe": [("amenity", "cafe")],
    "bar": [("amenity", "bar"), ("amenity", "pub")],
    "bakery": [("shop", "bakery")],
    "supermarket": [("shop", "supermarket")],
    "convenience_store": [("shop", "convenience")],
    "butcher": [("shop", "butcher")],
    "pharmacy": [("amenity", "pharmacy")],
    "hospital": [("amenity", "hospital")],
    "clinic": [("amenity", "clinic"), ("amenity", "doctors")],
    "dentist": [("amenity", "dentist")],
    "veterinary": [("amenity", "veterinary")],
    "gas_station": [("amenity", "fuel")],
    "car_repair": [("shop", "car_repair")],
    "bank": [("amenity", "bank")],
    "atm": [("amenity", "atm")],
    "hotel": [("tourism", "hotel"), ("tourism", "hostel"), ("tourism", "motel")],
    "gym": [("leisure", "fitness_centre"), ("amenity", "gym")],
    "park": [("leisure", "park")],
    "hairdresser": [("shop", "hairdresser"), ("shop", "beauty")],
    "laundry": [("shop", "laundry"), ("shop", "dry_cleaning")],
    "place_of_worship": [("amenity", "place_of_worship")],
    "school": [("amenity", "school")],
    "hardware_store": [("shop", "hardware"), ("shop", "doityourself")],
    "garden_centre": [("shop", "garden_centre"), ("shop", "florist")],
    "bookstore": [("shop", "books"), ("shop", "stationery")],
    "electronics": [("shop", "electronics")],
    "clothes": [("shop", "clothes")],
    "shoes": [("shop", "shoes")],
}
OTHER_CATEGORY = "other"
FOOD_CATEGORIES = {"restaurant", "fast_food"}

# Tipo de cocina (lo que el modelo elige en `cuisine`) → valores (regex) de
# la etiqueta OSM `cuisine`.
CUISINES = {
    "italian": "italian|pizza",
    "pizza": "pizza|italian",
    "chinese": "chinese",
    "mexican": "mexican",
    "japanese": "japanese|sushi",
    "sushi": "sushi|japanese",
    "burger": "burger",
    "chicken": "chicken",
    "seafood": "seafood|fish",
    "peruvian": "peruvian",
    "indian": "indian",
    "thai": "thai",
    "vegetarian": "vegetarian|vegan",
    "steak_house": "steak_house|grill|barbecue",
    "coffee_shop": "coffee_shop",
}

_home_coords_cache = None


def _home_coords():
    """Coordenadas exactas de USER_CONTEXT si están configuradas; si no,
    geocodifica USER_CONTEXT['ubicacion'] una sola vez y cachea el
    resultado (coordenadas exactas o geocodificadas) en memoria para el
    resto del proceso."""
    global _home_coords_cache
    lat, lon = USER_CONTEXT.get("latitud"), USER_CONTEXT.get("longitud")
    if lat is not None and lon is not None:
        return (lat, lon)

    # Por texto de la ubicación: cada perfil de la interfaz tiene la suya.
    query = f"{USER_CONTEXT['ubicacion']}, {USER_CONTEXT['pais']}"
    if _home_coords_cache is None:
        _home_coords_cache = {}
    if query in _home_coords_cache:
        return _home_coords_cache[query]
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers=_HEADERS,
            timeout=CONFIG["timeout_seconds"],
        )
        r.raise_for_status()
        results = r.json()
        _home_coords_cache[query] = (float(results[0]["lat"]), float(results[0]["lon"])) if results else (None, None)
    except Exception:
        return (None, None)  # sin red: se reintenta la próxima vez
    return _home_coords_cache[query]


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _search_overpass(tags: list, lat: float, lon: float, radius: int = None, cuisine: str = None) -> list:
    """Busca nodos/ways de OpenStreetMap con alguna de `tags` (lista de
    pares clave/valor) dentro de CONFIG["radius_meters"] de (lat, lon).
    Devuelve una lista de {"name", "lat", "lon"} — solo elementos CON
    nombre (uno sin nombre no sirve para dársela de respuesta al usuario).

    El servidor público de Overpass a veces da 504/timeout o una respuesta
    vacía bajo carga (medido: ~1 de cada 3 peticiones en las pruebas) —
    prueba los espejos de OVERPASS_URLS antes de rendirse (y dejar que
    find_nearby_places caiga a Nominatim de respaldo): se pide al principal
    y, si a los 2,5 s no respondió, también al espejo; gana el primero que
    responda bien. Medido: el principal tarda de 2 a 7 s; con un límite fijo
    de 6 s y los espejos uno detrás de otro se llegaba a ~17 s sin nada."""
    radius = radius or CONFIG["radius_meters"]
    extra = f'["cuisine"~"{cuisine}",i]' if cuisine else ""
    clauses = []
    for key, value in tags:
        clauses.append(f'node["{key}"="{value}"]{extra}(around:{radius},{lat},{lon});')
        clauses.append(f'way["{key}"="{value}"]{extra}(around:{radius},{lat},{lon});')
    query = f"[out:json][timeout:{CONFIG['timeout_seconds']}];({''.join(clauses)});out center;"

    cached = _overpass_cache.get(query)
    if cached and time.time() - cached[0] < 900:
        return [dict(p) for p in cached[1]]

    def fetch(url, timeout):
        r = requests.post(url, data={"data": query}, headers=_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json().get("elements", [])

    timeout = CONFIG["timeout_seconds"] + 3
    pool = ThreadPoolExecutor(max_workers=len(OVERPASS_URLS))
    try:
        futures = [pool.submit(fetch, OVERPASS_URLS[0], timeout)]
        done, _ = wait(futures, timeout=2.5)
        if not done or futures[0].exception():
            futures += [pool.submit(fetch, url, timeout) for url in OVERPASS_URLS[1:]]
        elements, last_error = None, None
        for future in as_completed(futures):
            try:
                elements = future.result()
                break
            except (requests.exceptions.RequestException, ValueError) as err:
                last_error = err
        if elements is None:
            raise last_error or RuntimeError("Overpass no respondió")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    places = []
    seen_names = set()
    for el in elements:
        name = (el.get("tags") or {}).get("name")
        if not name or name in seen_names:
            continue  # sin nombre no sirve, y no repetir el mismo lugar si salió por node y way
        center = el.get("center") or {}
        plat = el.get("lat", center.get("lat"))
        plon = el.get("lon", center.get("lon"))
        if plat is None or plon is None:
            continue
        seen_names.add(name)
        places.append({"name": name, "lat": plat, "lon": plon})
    # 15 min: el servidor público admite pocas consultas a la vez por IP y
    # repetir la misma búsqueda ("¿y la segunda?") no debería gastar otra.
    _overpass_cache[query] = (time.time(), [dict(p) for p in places])
    return places


_overpass_cache = {}


def _search_nominatim(query: str, lat: float, lon: float) -> list:
    delta = CONFIG["radius_degrees"]
    viewbox = f"{lon - delta},{lat + delta},{lon + delta},{lat - delta}"
    r = requests.get(
        NOMINATIM_URL,
        params={
            "q": query,
            "format": "json",
            "limit": CONFIG["max_results"],
            "viewbox": viewbox,
            "bounded": 1,
        },
        headers=_HEADERS,
        timeout=CONFIG["timeout_seconds"],
    )
    r.raise_for_status()
    # Sin calles, barrios ni ríos: "gimnasio" devolvía "Calle El Gimnasio".
    return [
        {"name": (p.get("display_name") or "").split(",")[0], "lat": float(p["lat"]), "lon": float(p["lon"])}
        for p in r.json()
        if p.get("class") not in _NOT_A_BUSINESS
    ]


_NOT_A_BUSINESS = {"highway", "boundary", "place", "landuse", "natural", "waterway", "railway", "route"}


NEARBY_PLACES_TOOL = {
    "type": "function",
    "function": {
        "name": "find_nearby_places",
        "description": (
            "Find real places (with name and distance) near where the user lives: restaurants, "
            "pharmacies, gas stations, supermarkets, banks, hospitals, etc. Use it whenever the user "
            "wants a kind of place near them, instead of web_search: it gives concrete results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [*CATEGORY_TAGS, OTHER_CATEGORY],
                    "description": (
                        "The kind of place, whatever language the user spoke in. "
                        f"'{OTHER_CATEGORY}' if none fits (then say what in `name`)."
                    ),
                },
                "cuisine": {
                    "type": "string",
                    "enum": [*CUISINES, "any"],
                    "description": "Only for food places: the kind of food asked for, or 'any'.",
                },
                "name": {
                    "type": "string",
                    "description": (
                        "Only if the user named a specific brand or business (e.g. 'Starbucks'), or "
                        f"category is '{OTHER_CATEGORY}': what to look for, in a few words. Otherwise empty."
                    ),
                },
                "label": {
                    "type": "string",
                    "description": "What the user asked for, in a few words of THEIR language (e.g. 'farmacia').",
                },
            },
            "required": ["category"],
        },
    },
}


def find_nearby_places(arguments: dict) -> str:
    """Lo que ve el modelo: la lista de lugares en texto."""
    return search_nearby(arguments)["text"]


def search_nearby(arguments: dict) -> dict:
    """Busca y devuelve {"text": lo que ve el modelo, "categoria" (el
    título del mapa), "origin": [lat, lon] o None, "places": [{"name",
    "lat", "lon", "dist"}]}. La interfaz web usa `places`/`origin` para
    mostrar los lugares en un mapa. `arguments`: los de la herramienta
    (category, cuisine, name, label)."""
    category = str(arguments.get("category") or OTHER_CATEGORY).strip()
    cuisine_key = str(arguments.get("cuisine") or "").strip()
    name = str(arguments.get("name") or "").strip()
    label = str(arguments.get("label") or "").strip() or name or category.replace("_", " ")
    out = {"text": "", "categoria": label, "origin": None, "places": []}
    lat, lon = _home_coords()
    if lat is None:
        ctx = USER_CONTEXT
        out["text"] = (
            "The user's exact location couldn't be determined right now. Answer using that the user "
            f"lives near {ctx['ubicacion']}, {ctx['pais']}, without making up place names."
        )
        return out
    out["origin"] = [lat, lon]

    tags = CATEGORY_TAGS.get(category)
    cuisine = CUISINES.get(cuisine_key) if category in FOOD_CATEGORIES else None
    note = ""

    def overpass(cuisine_filter):
        # Primero cerca (rápido y es lo que importa); si hay pocos, más lejos.
        found = _search_overpass(tags, lat, lon, CONFIG["near_radius_meters"], cuisine_filter)
        if len(found) < 3:
            found = _search_overpass(tags, lat, lon, CONFIG["radius_meters"], cuisine_filter)
        return found

    results = []
    if tags:
        try:
            results = overpass(cuisine)
            if cuisine and not results:
                note = (f"No places with that kind of food ({cuisine_key}) nearby; "
                        "these are the closest places of that type:\n")
                results = overpass(None)
        except Exception:
            results = []  # Overpass falló/está caído: se sigue con Nominatim de respaldo

    if name and results:
        # Pidieron algo concreto dentro de la categoría ("Starbucks", "ラーメン屋"):
        # los de la categoría que se llaman así; si ninguno, se busca el nombre
        # y, si tampoco, quedan los de la categoría avisándolo.
        named = [p for p in results if name.lower() in p["name"].lower()]
        if named:
            results = named
        else:
            try:
                by_name = _search_nominatim(name, lat, lon)
            except Exception:
                by_name = []
            if by_name:
                results = by_name
            else:
                note = f"Nothing called '{name}' nearby; these are the closest {category.replace('_', ' ')} places:\n"

    if not results:
        # Respaldo: nombres propios, lo que no está en la lista, o Overpass
        # no tuvo suerte con esta categoría en la zona.
        query = name or label
        try:
            results = _search_nominatim(query, lat, lon) if query else []
        except Exception as e:
            out["text"] = f"Couldn't search for nearby places right now ({e})."
            return out

    if not results:
        out["text"] = f"No nearby results for '{label}'."
        return out

    for place in results:
        place["dist"] = _haversine_km(lat, lon, place["lat"], place["lon"])
    # Nominatim no respeta del todo el área pedida: fuera del radio no es "cerca".
    results = [p for p in results if p["dist"] <= CONFIG["radius_meters"] / 1000]
    if not results:
        out["text"] = f"No nearby results for '{label}'."
        return out
    results.sort(key=lambda p: p["dist"])
    results = results[: CONFIG["max_results"]]

    out["places"] = [{"name": p["name"], "lat": p["lat"], "lon": p["lon"], "dist": round(p["dist"], 2)} for p in results]
    out["text"] = note + "\n".join(f"{i}. {p['name']} — {p['dist']:.1f} km away" for i, p in enumerate(results, start=1))
    return out


# ── Un lugar concreto: dónde queda y a qué distancia ───────────────────
# "¿A cuánta distancia está el Estadio Nacional?" no tenía herramienta y
# el modelo inventaba ("unos 15 km"). Esta lo ubica (Nominatim, prefiriendo
# el país y la zona del usuario) y da la distancia en línea recta y por
# carretera con el tiempo en auto (OSRM, servidor público gratis).
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
_country_code_cache = None

FIND_PLACE_TOOL = {
    "type": "function",
    "function": {
        "name": "find_place",
        "description": (
            "Locate one specific place by name (a stadium, a city, a building, a business, an address) "
            "and get how far it is from where the user lives, in a straight line and by road, and how "
            "long it takes by car. Use it whenever the user asks where something is or how far it is; "
            "never estimate distances yourself."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "place_type": {
                    "type": "string",
                    "enum": ["city_or_town", "specific_place"],
                    "description": (
                        "'city_or_town' for a city, town or region, also when the user says its downtown or "
                        "center; 'specific_place' for a building, stadium, business, address, etc."
                    ),
                },
                "place": {
                    "type": "string",
                    "description": (
                        "The name to look up on a map, as it's written there. For a city_or_town, ONLY the "
                        "city's own name: 'downtown San José' / 'el centro de San José' → 'San José'."
                    ),
                },
            },
            "required": ["place_type", "place"],
        },
    },
}


def _home_country_code():
    global _country_code_cache
    if _country_code_cache is None:
        lat, lon = _home_coords()
        _country_code_cache = ""
        if lat is not None:
            try:
                r = requests.get(NOMINATIM_REVERSE_URL, params={"lat": lat, "lon": lon, "format": "json", "zoom": 3},
                                 headers=_HEADERS, timeout=CONFIG["timeout_seconds"])
                r.raise_for_status()
                _country_code_cache = (r.json().get("address") or {}).get("country_code", "")
            except Exception:
                pass
    return _country_code_cache


def _route(lat1, lon1, lat2, lon2):
    """(km por carretera, minutos en auto) o None si no se pudo."""
    try:
        r = requests.get(f"{OSRM_URL}/{lon1},{lat1};{lon2},{lat2}", params={"overview": "false"},
                         headers=_HEADERS, timeout=6)
        r.raise_for_status()
        route = (r.json().get("routes") or [None])[0]
        return (route["distance"] / 1000, route["duration"] / 60) if route else None
    except Exception:
        return None


def _minutes_text(minutes: float) -> str:
    minutes = round(minutes)
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest} min" if rest else f"{hours} h"


def locate_place(arguments: dict) -> dict:
    """Mismo formato que search_nearby (el mapa de la interfaz lo muestra).
    `arguments`: los de la herramienta (place_type, place)."""
    lugar = str(arguments.get("place") or "").strip()
    is_town = arguments.get("place_type") == "city_or_town" or arguments.get("is_town") is True
    out = {"text": "", "categoria": lugar, "origin": None, "places": [], "kind": "place"}
    lat, lon = _home_coords()
    if lat is None:
        out["text"] = "The user's location couldn't be determined to compute the distance."
        return out
    if not lugar:
        out["text"] = "No place name was given."
        return out
    out["origin"] = [lat, lon]
    delta = 1.5  # prefiere resultados de la zona, sin excluir los lejanos
    base = {"format": "json", "limit": 5,
            "viewbox": f"{lon - delta},{lat + delta},{lon + delta},{lat - delta}", "bounded": 0}

    def search(query: str, **extra):
        """(resultados, si son del país del usuario): primero en su país."""
        params = {**base, "q": query, **extra}
        code = _home_country_code()
        if code:
            r = requests.get(NOMINATIM_URL, params={**params, "countrycodes": code}, headers=_HEADERS,
                             timeout=CONFIG["timeout_seconds"])
            r.raise_for_status()
            if r.json():
                return r.json(), True
        r = requests.get(NOMINATIM_URL, params=params, headers=_HEADERS, timeout=CONFIG["timeout_seconds"])
        r.raise_for_status()
        return r.json(), False

    try:
        results = []
        if is_town:
            # Una ciudad: solo poblaciones (no el "Centro Costarricense de
            # Ciencia y Cultura" para "centro de San José"). Si el modelo
            # dejó palabras de más delante del nombre ("centro de", "downtown",
            # en cualquier idioma), se prueba también quitando palabras desde
            # el principio ("de San José", "San José"…) y gana la población
            # más importante — del país del usuario si hay alguna ("centro de
            # San José" sola encontraba un barrio llamado "… Centro", y "José"
            # sola, un pueblo de Bélgica).
            local, abroad = [], []
            words = lugar.split()
            for start in range(0, min(len(words), 4)):
                found, in_country = search(" ".join(words[start:]), featureType="settlement")
                (local if in_country else abroad).extend(found)
            if local:
                # …salvo que en el mundo haya una ciudad MUCHO más importante
                # con ese nombre: "París" es la de Francia, no "Colonia París".
                r = requests.get(NOMINATIM_URL, params={"format": "json", "limit": 5, "q": lugar,
                                                        "featureType": "settlement"},
                                 headers=_HEADERS, timeout=CONFIG["timeout_seconds"])
                r.raise_for_status()
                world = r.json()
                importance = lambda rs: max((float(x.get("importance") or 0) for x in rs), default=0)  # noqa: E731
                if importance(world) - importance(local) > 0.25:
                    local = world
            results = local or abroad
        if not results:
            results, _ = search(lugar)
    except Exception as e:
        out["text"] = f"Couldn't look up the place right now ({e})."
        return out
    if not results:
        out["text"] = f"Couldn't find the place '{lugar}'."
        return out

    # El más importante (la capital antes que un distrito con el mismo
    # nombre: "centro de San José" daba un "San José" a 12 km). Si es una
    # ciudad, la ciudad (place) antes que la provincia o el cantón (boundary).
    if is_town:
        results = ([x for x in results if x.get("class") == "place"]
                   or [x for x in results if x.get("class") == "boundary"] or results)
    p = max(results, key=lambda x: float(x.get("importance") or 0))
    plat, plon = float(p["lat"]), float(p["lon"])
    name = p.get("name") or (p.get("display_name") or lugar).split(",")[0]
    where = ", ".join(part.strip() for part in (p.get("display_name") or name).split(",")[:3])
    straight = _haversine_km(lat, lon, plat, plon)
    route = _route(lat, lon, plat, plon)
    text = f"{name} ({where}): {straight:.1f} km in a straight line from where the user lives"
    if route:
        text += f"; about {route[0]:.0f} km by road, roughly {_minutes_text(route[1])} by car"
    out["text"] = text + "."
    out["categoria"] = name
    out["places"] = [{"name": name, "lat": plat, "lon": plon, "dist": round(route[0] if route else straight, 1)}]
    return out


def call_nearby_tool(name: str, arguments: dict):
    """Devuelve el resultado si `name` es una de las herramientas de este
    módulo, o None si no la reconoce (para que el que llama pruebe otras)."""
    if name == "find_nearby_places":
        return find_nearby_places(arguments)
    if name == "find_place":
        return locate_place(arguments)["text"]
    return None
