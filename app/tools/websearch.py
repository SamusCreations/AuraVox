"""
Búsqueda web para los asistentes de assistants.yaml.

Usa DuckDuckGo (paquete `ddgs`), que no requiere API key. Si no hay conexión
o la búsqueda falla, se devuelve un mensaje de error como texto en vez de
lanzar una excepción, para que el modelo pueda seguir respondiendo con lo
que ya sabe en lugar de romper la conversación.
"""
import time

from ddgs import DDGS

from app.tools.nearby_places import FIND_PLACE_TOOL, NEARBY_PLACES_TOOL, call_nearby_tool

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the internet for up-to-date information. Use it when answering needs recent or "
            "real-time facts you don't know for sure (news, prices, results, people, events, software "
            "versions, ages, etc.) or when the user asks you to look something up. For the weather use "
            "get_weather; for places use find_place / find_nearby_places. If the question is about "
            "today, now or something very recent, put the exact date (it's in your context) and "
            "concrete proper names in the query instead of generic words like 'today'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, a few keywords.",
                },
                "recent": {
                    "type": "boolean",
                    "description": "true if it's about something happening today or right now (results from the last day first).",
                },
            },
            "required": ["query"],
        },
    },
}

TOOLS = [WEB_SEARCH_TOOL, NEARBY_PLACES_TOOL, FIND_PLACE_TOOL]


def _run_search(query: str, max_results: int, timelimit: str = None) -> list:
    # region="wt-wt" (sin sesgo geográfico) en vez del default de ddgs
    # ("us-en"), que privilegia fuentes en inglés/EE.UU. incluso cuando la
    # consulta viene en español u otro idioma.
    return DDGS(timeout=6).text(query, max_results=max_results, region="wt-wt", timelimit=timelimit)


def web_search(query: str, recent: bool = False, max_results: int = 8) -> str:
    """Devuelve un resumen en texto plano de los resultados, o un aviso de error.

    `recent` (lo decide el modelo, en cualquier idioma): primero solo
    resultados del último día (mucho más precisos para algo que está
    pasando hoy) y, si eso no devuelve nada, sin esa restricción — así no se
    pierde una respuesta válida solo porque la página no se indexó hoy."""
    timelimit = "d" if recent else None
    try:
        try:
            results = _run_search(query, max_results, timelimit)
        except Exception:
            time.sleep(1)  # cortes de conexión puntuales (ConnectError): un reintento
            results = _run_search(query, max_results, timelimit)
        if recent and not results:
            results = _run_search(query, max_results)
    except Exception as e:
        return f"The web search failed right now ({e}). Answer with what you already know and say so."

    if not results:
        return "The search returned no results."

    lines = []
    for i, r in enumerate(results, start=1):
        title = (r.get("title") or "").strip()
        body = (r.get("body") or "").strip()
        url = (r.get("href") or "").strip()
        lines.append(f"{i}. {title} — {body} ({url})")
    return "\n".join(lines)


def call_tool(name: str, arguments: dict) -> str:
    if name == "web_search":
        return web_search(str(arguments.get("query") or ""), bool(arguments.get("recent")))
    nearby_result = call_nearby_tool(name, arguments)
    if nearby_result is not None:
        return nearby_result
    return f"Unknown tool: {name}"
