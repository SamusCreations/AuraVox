"""Control de la PC donde corre AuraVox (solo administradores).

- pc_volume: subir, bajar, poner en un %, silenciar.
- pc_media: reproducir/pausar, siguiente, anterior, detener (lo que esté
  sonando: Spotify, YouTube en el navegador, VLC…; son las teclas
  multimedia de Windows).
- pc_open: abrir un programa (se busca entre los accesos directos del menú
  Inicio, así solo se abre lo instalado) o una página web.
- pc_lock: bloquear la pantalla.

Sin librerías extra: teclas virtuales y LockWorkStation con ctypes. Aunque
un administrador baje el rol mínimo en Ajustes → Plugins, aquí se exige ser
administrador (o los modos de consola, que ya corren en la propia PC).
"""
import ctypes
import difflib
import os
import re
import time
import unicodedata
import webbrowser

VK = {"vol_mute": 0xAD, "vol_down": 0xAE, "vol_up": 0xAF, "next": 0xB0, "previous": 0xB1, "stop": 0xB2, "play_pause": 0xB3}
KEYEVENTF_KEYUP = 0x0002
# Para probar sin tocar la PC: AURAVOX_PC_DRYRUN=1 solo anota lo que haría.
DRY = os.environ.get("AURAVOX_PC_DRYRUN") == "1"
DONE = []
_apps = {"at": 0.0, "items": {}}


def _admin(ctx) -> bool:
    return ctx is None or getattr(ctx, "role", "") == "admin"


def _do(what: str, fn) -> None:
    DONE.append(what)
    if DRY:
        print(f"[pc_control] (prueba, no se hace) {what}")
        return
    fn()


def _press(vk: int, times: int = 1) -> None:
    if DRY:
        DONE.append(f"tecla {vk:#x} x{times}")
        print(f"[pc_control] (prueba, no se hace) tecla {vk:#x} x{times}")
        return
    user32 = ctypes.windll.user32
    for _ in range(times):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.01)


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t).lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def _start_menu() -> dict:
    """{nombre normalizado: ruta del .lnk} de los accesos del menú Inicio."""
    if time.time() - _apps["at"] < 300 and _apps["items"]:
        return _apps["items"]
    roots = [os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
             os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")]
    items = {}
    for root in roots:
        for folder, _dirs, files in os.walk(root):
            for f in files:
                if f.lower().endswith((".lnk", ".url")):
                    name = _norm(os.path.splitext(f)[0])
                    if "uninstall" in name or "desinstalar" in name:
                        continue
                    items.setdefault(name, os.path.join(folder, f))
    _apps.update(at=time.time(), items=items)
    return items


# Programas de Windows que no siempre tienen acceso directo en el menú.
BUILTIN = {"notepad": "notepad.exe", "bloc de notas": "notepad.exe", "calculadora": "calc.exe", "calculator": "calc.exe",
           "explorador": "explorer.exe", "explorer": "explorer.exe", "file explorer": "explorer.exe",
           "explorador de archivos": "explorer.exe", "paint": "mspaint.exe", "administrador de tareas": "taskmgr.exe",
           "task manager": "taskmgr.exe", "configuracion": "ms-settings:", "settings": "ms-settings:",
           "ajustes": "ms-settings:"}


def tools(ctx):
    if not _admin(ctx) or os.name != "nt":
        return []
    return [
        {"type": "function", "function": {
            "name": "pc_volume",
            "description": "Change the volume of the PC where AuraVox runs: up, down, set a percentage, mute or unmute.",
            "parameters": {"type": "object", "properties": {
                "action": {"type": "string", "enum": ["up", "down", "set", "mute", "unmute"]},
                "percent": {"type": "number", "description": "For set: 0-100. For up/down: how much (default 10)."},
            }, "required": ["action"]},
        }},
        {"type": "function", "function": {
            "name": "pc_media",
            "description": "Control whatever is playing on the PC (Spotify, a video in the browser, VLC…): play/pause, next, previous, stop.",
            "parameters": {"type": "object", "properties": {
                "action": {"type": "string", "enum": ["play_pause", "next", "previous", "stop"]},
            }, "required": ["action"]},
        }},
        {"type": "function", "function": {
            "name": "pc_open",
            "description": "Open a program installed on the PC by its name, as in the Start menu (\"Google Chrome\", \"Spotify\", \"Word\", \"calculator\"), or a specific web page. Pass a web address ONLY when the user names a site or page to visit; to open a browser or any app, pass its name. It can NOT close, quit or stop programs.",
            "parameters": {"type": "object", "properties": {
                "target": {"type": "string", "description": "Program name, or a web address starting with https://"},
            }, "required": ["target"]},
        }},
        {"type": "function", "function": {
            "name": "pc_lock",
            "description": "Lock the PC screen (Windows lock screen).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }},
    ]


def call(name, args, ctx):
    if name not in ("pc_volume", "pc_media", "pc_open", "pc_lock"):
        return None
    if not _admin(ctx):
        return "Only an administrator profile can control the PC: tell the user."
    if name == "pc_volume":
        action = args.get("action")
        try:
            pct = float(args.get("percent")) if args.get("percent") not in (None, "") else None
        except (TypeError, ValueError):
            pct = None
        if action == "set" and pct is not None:
            _press(VK["vol_down"], 50)               # a 0 (cada paso es 2 %)
            _press(VK["vol_up"], round(max(0, min(100, pct)) / 2))
            return f"Volume set to about {round(max(0, min(100, pct)))}%. Confirm briefly."
        if action in ("up", "down"):
            steps = max(1, round((pct or 10) / 2))
            _press(VK["vol_up" if action == "up" else "vol_down"], steps)
            return f"Volume {action} about {steps * 2}%. Confirm briefly."
        if action in ("mute", "unmute"):
            # La tecla alterna: para "activar" se sube y baja un paso (eso quita el silencio).
            if action == "mute":
                _press(VK["vol_mute"])
            else:
                _press(VK["vol_up"])
                _press(VK["vol_down"])
            return f"Sound {'muted' if action == 'mute' else 'unmuted'}. Confirm briefly."
        return "Say how: up, down, set (with percent), mute or unmute."
    if name == "pc_media":
        action = args.get("action") if args.get("action") in ("play_pause", "next", "previous", "stop") else "play_pause"
        _press(VK[action])
        return f"Done ({action}). Confirm briefly."
    if name == "pc_lock":
        _do("bloquear pantalla", lambda: ctypes.windll.user32.LockWorkStation())
        return "The PC screen is locked. Confirm briefly."
    target = str(args.get("target") or "").strip()
    if re.match(r"^https?://", target, re.I):
        _do(f"abrir {target}", lambda: webbrowser.open(target))
        return f"Opened {target} in the browser. Confirm briefly."
    key = _norm(target)
    if not key:
        return "Say which program to open."
    if key in BUILTIN:
        _do(f"abrir {BUILTIN[key]}", lambda: os.startfile(BUILTIN[key]))  # noqa: S606 — programa de Windows de una lista fija
        return f"Opened {target}. Confirm briefly."
    apps = _start_menu()
    hit = apps.get(key)
    if not hit:
        close = difflib.get_close_matches(key, list(apps), n=1, cutoff=0.6)
        starts = [n for n in apps if n.startswith(key) or key in n.split()]
        name_ = close[0] if close else (min(starts, key=len) if starts else None)
        hit = apps.get(name_) if name_ else None
    if not hit:
        return f"There's no program called \"{target}\" in the Start menu. Ask the user for the exact name."
    _do(f"abrir {hit}", lambda: os.startfile(hit))  # noqa: S606 — acceso directo del menú Inicio (lo instalado)
    return f"Opened {os.path.splitext(os.path.basename(hit))[0]}. Confirm briefly."