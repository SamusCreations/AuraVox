"""
Push to talk para voice_loop.py: mientras se mantiene apretada la tecla
(o botón del mouse) configurada en un asistente (`push_to_talk_key` en
assistants.yaml), se graba el micrófono y lo dicho va directo a ese
asistente, sin decir su nombre.

La tecla se detecta de forma GLOBAL (funciona aunque la consola no tenga
el foco) con GetAsyncKeyState de la API de Windows vía ctypes — sin
dependencias nuevas. Ojo: la tecla también le llega a la ventana que tenga
el foco (una letra se escribiría ahí), por eso conviene F13-F24, Pausa,
Bloq Despl o los botones laterales del mouse.
"""
import sys
import threading
import time

# Nombre canónico (el que se guarda en assistants.yaml) → código de tecla
# virtual de Windows. La interfaz web traduce la tecla que apretás a estos
# mismos nombres.
KEY_CODES = {
    **{f"F{i}": 0x6F + i for i in range(1, 25)},
    **{chr(c): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
    **{f"NUMPAD{d}": 0x60 + d for d in range(10)},
    "SPACE": 0x20, "TAB": 0x09, "CAPSLOCK": 0x14, "PAUSE": 0x13, "SCROLLLOCK": 0x91,
    "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "LSHIFT": 0xA0, "RSHIFT": 0xA1, "LCTRL": 0xA2, "RCTRL": 0xA3, "LALT": 0xA4, "RALT": 0xA5,
    "BACKQUOTE": 0xC0,
    "MBUTTON": 0x04, "XBUTTON1": 0x05, "XBUTTON2": 0x06,
}

if sys.platform == "win32":
    import ctypes

    _user32 = ctypes.windll.user32

    def is_pressed(key: str) -> bool:
        vk = KEY_CODES.get(key)
        return bool(vk) and bool(_user32.GetAsyncKeyState(vk) & 0x8000)
else:  # sin API global de teclado: push to talk desactivado
    def is_pressed(key: str) -> bool:
        return False


def normalize_key(value) -> str:
    """"f8" → "F8"; "" si está vacío o no es una tecla soportada."""
    key = str(value or "").strip().upper()
    return key if key in KEY_CODES else ""


def record_while_pressed(key: str, mic, max_seconds: float = 30.0, tail_seconds: float = 0.25):
    """Graba del micrófono ya abierto `mic` (mic_stream.MicStream) mientras
    `key` siga apretada (más una colita de `tail_seconds` para no cortar la
    última sílaba). Devuelve un numpy float32 mono, o None si fue un toque
    demasiado corto para ser habla (min_speech_seconds)."""
    import winsound

    # El pitido suena en otro hilo para no perder el inicio de lo que se dice.
    threading.Thread(target=winsound.Beep, args=(1200, 70), daemon=True).start()
    return mic.record_while(lambda: is_pressed(key), max_seconds=max_seconds, tail_seconds=tail_seconds)


def wait_until_released(key: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while is_pressed(key) and time.monotonic() < deadline:
        time.sleep(0.02)
