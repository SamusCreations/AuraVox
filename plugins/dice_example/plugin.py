"""Plugin de ejemplo: tirar dados.

Un plugin es una carpeta en plugins/ con manifest.json (nombre, descripción,
rol mínimo y sus herramientas) y este plugin.py con `call(name, args, ctx)`.
Lo que devuelve `call` es lo que el modelo lee como resultado; el modelo
redacta la respuesta. `ctx` dice quién pregunta (ctx.role, ctx.profile,
ctx.assistant…) o es None en los modos de consola.
"""
import random


def call(name, args, ctx):
    if name != "roll_dice":
        return None
    try:
        count = min(20, max(1, int(args.get("count") or 1)))
        sides = min(1000, max(2, int(args.get("sides") or 6)))
    except (TypeError, ValueError):
        count, sides = 1, 6
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = f" (total {sum(rolls)})" if count > 1 else ""
    return f"Rolled {count}d{sides}: {', '.join(map(str, rolls))}{total}. Tell the user the result."