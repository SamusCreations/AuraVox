"""Avisos del servidor a las páginas abiertas (recordatorios, alarmas,
rutinas programadas…).

Cada página pregunta con una consulta larga (GET /api/notify, como
/api/voice/events) y recibe los avisos de SU perfil (o de su sesión de
invitado). Así sirve igual en la PC y en el celular, sin Web Push (que
necesitaría un certificado de verdad y una librería de cifrado).

Para que en la PC el aviso se diga una sola vez: la primera página LOCAL
(abierta en la misma PC) que lo reclama (POST /api/notify/claim) lo dice
con la voz del asistente; si en la PC no hay ninguna página abierta, lo
dice el propio servidor por los altavoces (ver reminders.speak_on_pc).
"""
import collections
import threading
import time

MAX_EVENTS = 200
LOCAL_ALIVE = 45  # s: una página local que no pregunta hace más que esto, ya no está

_cond = threading.Condition()
_events = collections.deque(maxlen=MAX_EVENTS)
_last_id = 0
_claimed = set()
_local_seen = {}  # cliente → última vez que preguntó (solo páginas de la PC)


def push(owner: str, kind: str, **data) -> dict:
    """Aviso nuevo para las páginas de `owner` ("*" = todas)."""
    global _last_id
    with _cond:
        _last_id += 1
        event = {"id": _last_id, "owner": owner, "type": kind, "at": time.time(), **data}
        _events.append(event)
        _cond.notify_all()
        return event


def poll(owner: str, after: int, wait: float, client: str = "", local: bool = False) -> dict:
    deadline = time.monotonic() + max(0.0, min(wait, 25.0))
    with _cond:
        if local and client:
            _local_seen[client] = time.monotonic()
        while True:
            items = [{k: v for k, v in e.items() if k != "owner"} for e in _events
                     if e["id"] > after and e["owner"] in (owner, "*")]
            left = deadline - time.monotonic()
            if items or left <= 0:
                if local and client:
                    _local_seen[client] = time.monotonic()
                return {"events": items, "last": _last_id}
            _cond.wait(left)


def local_page_open() -> bool:
    now = time.monotonic()
    with _cond:
        return any(now - t < LOCAL_ALIVE for t in _local_seen.values())


def claim(event_id: int) -> bool:
    """True solo para la primera página que lo pide (la que lo dice en voz alta)."""
    with _cond:
        if event_id in _claimed:
            return False
        _claimed.add(event_id)
        if len(_claimed) > MAX_EVENTS * 2:
            for old in sorted(_claimed)[:MAX_EVENTS]:
                _claimed.discard(old)
        return True


def claimed(event_id: int) -> bool:
    with _cond:
        return event_id in _claimed
