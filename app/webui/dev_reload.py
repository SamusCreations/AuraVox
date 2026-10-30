"""Recarga en caliente: los cambios se ven sin reiniciar nada a mano.

- **Página** (app/webui/static): la página pregunta cada pocos segundos por
  /api/dev/version. Si cambió solo el CSS, cambia la hoja de estilos al
  vuelo; si cambió el HTML o el JavaScript, se recarga sola en cuanto no se
  esté usando (sin conversación por voz abierta, sin respuesta en camino,
  sin cambios sin guardar ni texto a medio escribir). La conversación no se
  pierde: está guardada en el servidor (chat_store.py).
- **Servidor** (cualquier .py de app/): AuraVox.bat arranca un
  vigilante (supervise) que lanza el servidor como proceso hijo y, cuando
  cambia un .py, lo cierra ordenadamente (Ctrl+Break: libera Whisper, la
  voz clonada, el acceso por red…) y lo vuelve a lanzar. La página nota el
  reinicio (otro `boot`) y se recarga cuando puede. Si el código nuevo tiene
  un error, el vigilante espera al próximo cambio.

`--no-reload` lo desactiva (un solo proceso, como antes).
"""
import os
import signal
import subprocess
import sys
import time
import uuid

from app import paths

BOOT_ID = uuid.uuid4().hex[:12]   # cambia con cada arranque del servidor
CHILD_ENV = "AURAVOX_CHILD"
WATCH_DIRS = [os.path.join(paths.ROOT, "app")]
STATIC_DIR = paths.WEBUI_STATIC_DIR


def _scan(exts) -> dict:
    out = {}
    for base in WATCH_DIRS:
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "vendor", "static")]
            for name in files:
                if name.endswith(exts):
                    path = os.path.join(root, name)
                    try:
                        out[path] = os.path.getmtime(path)
                    except OSError:
                        pass
    return out


def static_version() -> dict:
    """Huella de los archivos de la página: por separado el CSS (se puede
    cambiar sin recargar) y el resto."""
    css = other = 0.0
    try:
        for name in os.listdir(STATIC_DIR):
            path = os.path.join(STATIC_DIR, name)
            if os.path.isfile(path):
                mtime = os.path.getmtime(path)
                if name.endswith(".css"):
                    css = max(css, mtime)
                else:
                    other = max(other, mtime)
    except OSError:
        pass
    return {"boot": BOOT_ID, "css": round(css, 3), "assets": round(other, 3)}


def is_child() -> bool:
    return os.environ.get(CHILD_ENV) == "1"


def install_child_signals() -> None:
    """En el hijo: Ctrl+Break (lo que manda el vigilante para reiniciar) se
    trata como Ctrl+C, así main() hace su limpieza normal."""
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)


def supervise(argv: list) -> int:
    """Lanza el servidor como hijo y lo reinicia cuando cambia un .py."""
    env = {**os.environ, CHILD_ENV: "1"}
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    first = True
    print("Recarga en caliente activada: los cambios en la página se ven solos y los del servidor lo reinician.")
    while True:
        args = [sys.executable, os.path.abspath(sys.argv[0]), *argv]
        if not first:
            args.append("--no-browser")
            env["AURAVOX_RESTART"] = "1"
        child = subprocess.Popen(args, env=env, creationflags=flags)
        first = False
        before = _scan((".py",))
        changed = None
        try:
            while child.poll() is None:
                time.sleep(1.0)
                now = _scan((".py",))
                diff = [p for p in set(now) | set(before) if now.get(p) != before.get(p)]
                if diff:
                    changed = diff
                    break
        except KeyboardInterrupt:
            _stop(child)
            return 0
        if changed is None:
            code = child.returncode
            if code in (0, None):
                return 0
            # Se cayó (p. ej. un error en el código recién guardado): se
            # espera a que se corrija.
            print(f"\n[recarga] el servidor terminó con el código {code}; espero un cambio en el código para reintentar…")
            before = _scan((".py",))
            try:
                while _scan((".py",)) == before:
                    time.sleep(1.0)
            except KeyboardInterrupt:
                return code
            continue
        names = ", ".join(os.path.relpath(p, paths.ROOT) for p in changed[:4])
        print(f"\n[recarga] cambió {names}: reiniciando el servidor…")
        time.sleep(0.4)  # que terminen de guardarse los demás archivos
        _stop(child)


def _stop(child) -> None:
    if child.poll() is not None:
        return
    try:
        child.send_signal(signal.CTRL_BREAK_EVENT if hasattr(signal, "CTRL_BREAK_EVENT") else signal.SIGINT)
        child.wait(timeout=20)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        child.kill()
        child.wait(timeout=5)
