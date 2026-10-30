"""Clima (app/tools/weather.py) como plugin."""
from app.tools import weather


def tools(ctx):
    return weather.TOOLS


def call(name, args, ctx):
    return weather.call_tool(name, args)