"""Búsqueda web y lugares (app/tools/websearch.py y nearby_places.py) como plugin.

Las herramientas son las de siempre; los lugares los muestra la página en un
mapa (eso lo intercepta chat_runtime por nombre, antes de llegar aquí)."""
from app.tools import websearch


def tools(ctx):
    return websearch.TOOLS


def call(name, args, ctx):
    return websearch.call_tool(name, args)