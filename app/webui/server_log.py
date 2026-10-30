"""
Consola de la interfaz web: guarda en memoria las últimas líneas que el
servidor escribe (print, tracebacks, avisos de librerías) para mostrarlas
en la página (panel "Consola"), además de seguir mostrándolas en la ventana
de AuraVox como siempre.

install() reemplaza sys.stdout/sys.stderr por un "tee": todo lo que pase
por ahí (incluidos los mensajes de Whisper/Supertonic) queda registrado sin
tener que tocar esos módulos. log("categoría", "texto") es la forma de
escribir líneas propias con una categoría (chat, voz, oído...).
"""
import collections
import os
import logging
import sys
import threading
import time

_MAX_LINES = 3000
_lock = threading.Lock()
_lines = collections.deque(maxlen=_MAX_LINES)
_next_id = 1


# Copia en disco de todo lo que pasa por la consola, en logs/webui_server.log
# (ver paths.WEBUI_LOG). Se sobreescribe en cada arranque: es el registro de
# la última ejecución, para revisar errores después.
_file = None


def _append(text: str, level: str) -> None:
    global _next_id
    now = time.time()
    with _lock:
        _lines.append({"id": _next_id, "t": now, "level": level, "text": text})
        _next_id += 1
        if _file is not None:
            try:
                _file.write(f"{time.strftime('%H:%M:%S', time.localtime(now))} {level:<5} {text}\n")
                _file.flush()
            except Exception:  # noqa: BLE001 — el archivo nunca debe tumbar el servidor
                pass


def _level_for(text: str, default: str) -> str:
    low = text.lower()
    if "traceback" in low or "error" in low or low.startswith("  file "):
        return "error"
    if any(w in low for w in ("aviso", "warning", "warn", "failed", "could not", "no se pudo")):
        return "warn"
    return default


class _Tee:
    """Escribe en el stream original y además guarda cada línea completa.
    Un "\\r" (barras de progreso) cuenta como fin de línea."""

    def __init__(self, stream, level: str):
        self._stream = stream
        self._level = level
        self._buf = ""
        self._buf_lock = threading.Lock()

    def write(self, s):
        try:
            self._stream.write(s)
        except Exception:  # noqa: BLE001 — la consola original nunca debe tumbar el servidor
            pass
        with self._buf_lock:
            self._buf += str(s).replace("\r", "\n")
            *complete, self._buf = self._buf.split("\n")
        for line in complete:
            if line.strip():
                _append(line.rstrip(), _level_for(line, self._level))
        return len(s)

    def flush(self):
        try:
            self._stream.flush()
        except Exception:  # noqa: BLE001
            pass

    # Otros módulos hacen sys.stdout.reconfigure(encoding="utf-8") si la
    # codificación no es utf-8: se declara utf-8 y reconfigure no hace nada.
    @property
    def encoding(self):
        return "utf-8"

    def reconfigure(self, **kwargs):
        pass

    def isatty(self):
        return False

    def fileno(self):
        return self._stream.fileno()


def install(log_path: str = None, append: bool = False) -> None:
    """Captura stdout/stderr para la consola de la página y, si se pasa
    `log_path`, también los guarda en ese archivo (sobreescribiéndolo, o
    a continuación con `append`: reinicio por recarga en caliente)."""
    global _file
    if log_path and _file is None:
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            _file = open(log_path, "a" if append else "w", encoding="utf-8")
            what = "hot-reload restart" if append else "run"
            _file.write(f"# AuraVox (web UI) — {what} at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        except OSError as e:
            sys.__stderr__.write(f"(warning: could not open log file {log_path}: {e})\n")
    if isinstance(sys.stdout, _Tee):
        return
    sys.stdout = _Tee(sys.stdout, "info")
    sys.stderr = _Tee(sys.stderr, "warn")
    # Los mensajes INFO de Supertonic (qué proveedor ONNX usa, etc.) también
    # a la consola.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    for name in ("supertonic", "faster_whisper"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.addHandler(handler)
        lg.propagate = False


def log(category: str, text: str, level: str = "info") -> None:
    """Línea propia con categoría: se imprime (ventana de AuraVox) y
    queda en la consola web con ese nivel."""
    line = f"[{category}] {text}"
    try:
        sys.__stdout__.write(line + "\n")
        sys.__stdout__.flush()
    except Exception:  # noqa: BLE001
        pass
    _append(line, level)


def since(after_id: int, limit: int = 500) -> dict:
    with _lock:
        lines = [ln for ln in _lines if ln["id"] > after_id]
        last = _next_id - 1
    return {"lines": lines[-limit:], "last": last}
