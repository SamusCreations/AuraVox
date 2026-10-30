"""Habilidades del asistente: herramientas que dependen de QUIÉN pregunta.

Las herramientas de siempre (búsqueda web, clima, Spotify…) son iguales
para todos. Estas otras —memoria, recordatorios, listas, documentos,
rutinas, plugins y servidores MCP— necesitan saber qué perfil pregunta,
con qué asistente y qué rol tiene. Cada una es un módulo con:

- NAME: nombre corto (para el registro).
- MIN_ROLE: "guest", "user" o "admin": quién puede usarla.
- tools(ctx) -> list: herramientas (formato de Ollama) para ESTE turno;
  [] si no aplica (p. ej. el asistente no tiene documentos).
- call(name, args, ctx) -> str | None: ejecuta una herramienta suya
  (None si `name` no es suya).
- context(ctx) -> str (opcional): texto que se suma al system prompt (lo
  que recuerda del usuario, los recordatorios pendientes…).

El servidor arma un `Ctx` por petición (ver config_ui._chat) y
chat_runtime.chat lo usa para sumar las herramientas y el contexto.
"""
import threading
import traceback

RANKS = {"guest": 1, "user": 2, "admin": 3}

_lock = threading.Lock()
_modules = []


class Ctx:
    """Quién pregunta y por dónde contestarle a la página.

    - profile: id del perfil (None para el invitado).
    - role: "admin" | "user" | "guest".
    - owner: clave de los datos propios: el perfil, o "g-<hash>" para la
      sesión del invitado (sus recordatorios viven mientras dure la sesión).
    - guest_data: lo que manda la página del invitado (su memoria y sus
      rutinas viven en su navegador).
    - assistant: nombre guardado del asistente (puede ser "" en un
      borrador) y cfg: su configuración.
    - emit(event): manda un evento a la página (línea del NDJSON).
    - history: la conversación de este turno.
    - files: los archivos de la conversación ({name, id}: adjuntos y lo
      que mandó el asistente), p. ej. para editar una imagen.
    """

    def __init__(self, profile=None, role="guest", owner="", guest_data=None, assistant="", cfg=None,
                 emit=None, history=None, style="text", lang=None, call_base_tool=None):
        self.profile = profile
        self.role = role
        self.owner = owner
        self.guest = role == "guest"
        self.guest_data = guest_data if isinstance(guest_data, dict) else {}
        self.assistant = assistant
        self.cfg = cfg or {}
        self.emit = emit or (lambda event: None)
        self.history = history or []
        self.style = style
        self.lang = lang
        # Para las rutinas: llamar a las herramientas de siempre (clima,
        # búsqueda) con el mismo registro que el resto.
        self.call_base_tool = call_base_tool
        self.files = []

    def allowed(self, min_role: str) -> bool:
        return RANKS.get(self.role, 0) >= RANKS.get(min_role, 3)


def register(module) -> None:
    with _lock:
        if module not in _modules:
            _modules.append(module)


def _active(ctx: Ctx) -> list:
    _ensure_builtin()
    with _lock:
        mods = list(_modules)
    return [m for m in mods if ctx.allowed(getattr(m, "MIN_ROLE", "guest"))]


def tools_for(ctx: Ctx) -> list:
    out = []
    for m in _active(ctx):
        try:
            out += m.tools(ctx) or []
        except Exception:  # noqa: BLE001 — una habilidad rota no deja sin chat al resto
            traceback.print_exc()
    return out


def context_for(ctx: Ctx) -> str:
    parts = []
    for m in _active(ctx):
        fn = getattr(m, "context", None)
        if not fn:
            continue
        try:
            text = fn(ctx)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            text = ""
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def call(name: str, args: dict, ctx: Ctx):
    """Resultado de la herramienta `name`, o None si no es de ninguna habilidad."""
    for m in _active(ctx):
        result = m.call(name, args if isinstance(args, dict) else {}, ctx)
        if result is not None:
            return result
    return None


_builtin_loaded = False


def _ensure_builtin() -> None:
    global _builtin_loaded
    if _builtin_loaded:
        return
    with _lock:
        if _builtin_loaded:
            return
        _builtin_loaded = True
    from app.skills import knowledge, lists, memory, reminders, routines

    register(memory)
    register(reminders)
    register(lists)
    register(knowledge)
    register(routines)
    from app.core import mcp_client, plugins

    register(plugins)
    register(mcp_client)
