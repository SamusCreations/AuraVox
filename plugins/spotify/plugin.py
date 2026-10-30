"""Spotify (app/tools/spotify_skill.py) como plugin. Sus herramientas
dependen de cómo esté configurado (ver spotify_skill.TOOLS)."""
from app.tools import spotify_skill


def tools(ctx):
    return spotify_skill.TOOLS


def call(name, args, ctx):
    return spotify_skill.call_tool(name, args)