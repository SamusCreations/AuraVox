"""
Clima actual y pronóstico de los próximos días donde vive el usuario, con
Open-Meteo (https://open-meteo.com): gratis, sin API key, datos de
servicios meteorológicos nacionales. Antes el clima se buscaba con
web_search y devolvía páginas genéricas ("cómo estará el clima el 30 de
septiembre") sin el dato; esto da números concretos.

Usa las mismas coordenadas que find_nearby_places (user_context de
assistants.yaml, o la ubicación geocodificada).
"""
import requests

from app.tools.nearby_places import _home_coords

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Códigos WMO de Open-Meteo → descripción.
_WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "heavy freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "heavy freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "violent showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "severe thunderstorm with hail",
}

WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "Current weather and forecast (today, tomorrow and the next days) where the user "
            "lives: temperature, chance of rain, wind. Use it for ANY question about the weather, "
            "temperature, rain or the forecast there, instead of web_search."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

TOOLS = [WEATHER_TOOL]


def _desc(code) -> str:
    return _WMO.get(int(code or 0), "unknown conditions")


def get_weather() -> str:
    lat, lon = _home_coords()
    if lat is None:
        return "The user's location couldn't be determined to check the weather."
    try:
        r = requests.get(FORECAST_URL, timeout=8, params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum",
            "timezone": "auto",
            "forecast_days": 4,
        })
        r.raise_for_status()
        data = r.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        return f"Couldn't get the weather right now ({e})."

    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    lines = [
        f"Now: {_desc(cur.get('weather_code'))}, {cur.get('temperature_2m')} °C "
        f"(feels like {cur.get('apparent_temperature')} °C), humidity {cur.get('relative_humidity_2m')} %, "
        f"wind {cur.get('wind_speed_10m')} km/h, rain in the last hour {cur.get('precipitation')} mm."
    ]
    names = ["Today", "Tomorrow"]
    for i, day in enumerate(daily.get("time") or []):
        label = f"{names[i]} ({day})" if i < len(names) else day
        lines.append(
            f"{label}: {_desc(daily['weather_code'][i])}, high {daily['temperature_2m_max'][i]} °C, "
            f"low {daily['temperature_2m_min'][i]} °C, chance of rain "
            f"{daily['precipitation_probability_max'][i]} %, total rain {daily['precipitation_sum'][i]} mm."
        )
    return "\n".join(lines)


def call_tool(name: str, arguments: dict):
    """Resultado si `name` es de este módulo; None si no la reconoce."""
    if name == "get_weather":
        return get_weather()
    return None
