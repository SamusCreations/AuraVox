"""Pantalla de diagnóstico: qué anda y qué no, con "arreglar" donde se puede.

Cada comprobación devuelve {"id", "group", "status" ("ok" | "warn" |
"error" | "info"), "title", "detail", "fix" (id de un arreglo o None),
"link" (una página para leer, opcional)}. Los textos salen en el idioma de
la interfaz (i18n.tr). Los arreglos los ejecuta config_ui (algunos
necesitan el servidor HTTP o la escucha manos libres) y solo desde la
propia PC los que tocan el sistema (firewall, red).

Comprueba: Ollama (corre, versión, modelos, alguno con herramientas, lo
cargado), GPU y VRAM, disco, voz (Whisper, Supertonic, voces clonadas),
micrófono de la PC, puertos (la interfaz y el acceso por red), firewall y
tipo de red de Windows, ffmpeg / Office (convertir archivos) y el modelo
de embeddings (documentos y memoria).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

import requests

from app import paths
from app.webui.i18n import tr

OLLAMA = "http://127.0.0.1:11434"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FIREWALL_RULE = "AuraVox (acceso por red)"
_fw_cache = {"at": 0.0, "data": None}


def _item(cid, group, status, title, detail="", fix=None, link=None) -> dict:
    return {"id": cid, "group": group, "status": status, "title": title, "detail": detail, "fix": fix, "link": link}


def _run(cmd: list, timeout: float = 15) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW,
                              encoding="utf-8", errors="replace").stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _gb(b) -> str:
    return f"{(b or 0) / 1024 ** 3:.1f} GB"


# ── Ollama ─────────────────────────────────────────────────────────────

def ollama_exe():
    """Ruta de Ollama (la app de la bandeja, o el ejecutable), o None."""
    local = os.environ.get("LOCALAPPDATA", "")
    for p in (os.path.join(local, "Programs", "Ollama", "ollama app.exe"),
              os.path.join(local, "Programs", "Ollama", "ollama.exe")):
        if os.path.isfile(p):
            return p
    return shutil.which("ollama")


def check_ollama(list_models, update_status) -> list:
    out = []
    try:
        version = requests.get(f"{OLLAMA}/api/version", timeout=4).json().get("version")
    except (requests.exceptions.RequestException, ValueError):
        version = None
    if not version:
        exe = ollama_exe()
        out.append(_item("ollama", "ollama", "error", tr("dg_ollama_down"),
                         tr("dg_ollama_down_d" if exe else "dg_ollama_missing_d"),
                         fix="ollama_start" if exe else None, link=None if exe else "https://ollama.com/download"))
        return out
    upd = update_status or {}
    latest = upd.get("latest")
    newer = latest and latest != version
    out.append(_item("ollama", "ollama", "warn" if newer else "ok", tr("dg_ollama_ok", v=version),
                     tr("dg_ollama_update", v=latest) if newer else ""))
    models = list_models()
    base = models.get("models") or []
    if not base:
        out.append(_item("models", "ollama", "error", tr("dg_models_none"), tr("dg_models_none_d"), fix="pull_recommended"))
    else:
        with_tools = [m["name"] for m in base if m.get("capabilities") is None or "tools" in (m.get("capabilities") or [])]
        out.append(_item("models", "ollama", "ok" if with_tools else "warn", tr("dg_models", n=len(base)),
                         tr("dg_models_tools", names=", ".join(with_tools[:4])) if with_tools else tr("dg_models_notools"),
                         fix=None if with_tools else "pull_recommended"))
    try:
        loaded = requests.get(f"{OLLAMA}/api/ps", timeout=4).json().get("models") or []
    except (requests.exceptions.RequestException, ValueError):
        loaded = []
    if loaded:
        parts = []
        for m in loaded:
            size, vram = m.get("size") or 0, m.get("size_vram") or 0
            where = "GPU" if vram >= size * 0.95 else f"{vram * 100 // max(size, 1)}% GPU"
            parts.append(f"{m.get('name')} ({_gb(size)}, {where})")
        partial = any((m.get("size_vram") or 0) < (m.get("size") or 0) * 0.95 for m in loaded)
        out.append(_item("loaded", "ollama", "warn" if partial else "info", tr("dg_loaded", n=len(loaded)),
                         "; ".join(parts) + (" — " + tr("dg_loaded_partial") if partial else ""), fix="free_vram"))
    out += check_ollama_tuning()
    return out


# Ajustes de Ollama para responder más rápido (variables de entorno del
# usuario; Ollama las lee al arrancar): flash attention y caché KV en 8 bits
# (menos VRAM y más velocidad con contextos largos), dos modelos cargados a
# la vez (el del asistente y nomic-embed-text, sin descargarse entre
# turnos) y dos peticiones en paralelo (la revisión previa corre a la vez
# que la respuesta, ver assistant_common._needs_tool).
OLLAMA_TUNING = {
    "OLLAMA_FLASH_ATTENTION": "1",
    "OLLAMA_KV_CACHE_TYPE": "q8_0",
    "OLLAMA_MAX_LOADED_MODELS": "2",
    "OLLAMA_NUM_PARALLEL": "2",
}


def ollama_server_env():
    """Las variables con que arrancó el Ollama que corre ahora, de la línea
    "server config" de su registro (Windows), o None si no se sabe."""
    log = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Ollama", "server.log")
    try:
        with open(log, encoding="utf-8", errors="replace") as f:
            lines = [ln for ln in f if 'msg="server config"' in ln]
    except OSError:
        return None
    if not lines:
        return None
    return dict(re.findall(r"(OLLAMA_[A-Z_]+):(\S*)", lines[-1]))


def _tuning_ok(name: str, value: str) -> bool:
    if name == "OLLAMA_FLASH_ATTENTION":
        return value.lower() in ("1", "true")
    if name in ("OLLAMA_MAX_LOADED_MODELS", "OLLAMA_NUM_PARALLEL"):
        return value.isdigit() and (int(value) >= int(OLLAMA_TUNING[name]) or (name == "OLLAMA_MAX_LOADED_MODELS" and value == "0"))
    return value == OLLAMA_TUNING[name]


def check_ollama_tuning() -> list:
    env = ollama_server_env()
    if env is None:
        return []
    missing = [f"{k}={OLLAMA_TUNING[k]}" for k in OLLAMA_TUNING if not _tuning_ok(k, env.get(k, ""))]
    active = ", ".join(f"{k.replace('OLLAMA_', '')}={env.get(k) or '—'}" for k in OLLAMA_TUNING)
    if not missing:
        return [_item("ollama_tuning", "ollama", "ok", tr("dg_tuning_ok"), active)]
    return [_item("ollama_tuning", "ollama", "warn", tr("dg_tuning_off"), tr("dg_tuning_off_d", vars=", ".join(missing)),
                  fix="ollama_tune")]


def fix_ollama_tuning() -> bool:
    """Guarda las variables para el usuario (setx) y reinicia Ollama con
    ellas (el proceso que lo arranca también las lleva, por si el
    Explorador todavía no se enteró del cambio)."""
    if os.name != "nt":
        return False
    for name, value in OLLAMA_TUNING.items():
        _run(["setx", name, value])
        os.environ[name] = value
    for image in ("ollama app.exe", "ollama.exe"):
        _run(["taskkill", "/F", "/IM", image])
    time.sleep(2)
    return start_ollama()


# ── GPU, disco ─────────────────────────────────────────────────────────

def check_gpu() -> list:
    raw = _run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,driver_version",
                "--format=csv,noheader,nounits"], 6).strip().splitlines()
    if not raw:
        return [_item("gpu", "system", "warn", tr("dg_gpu_none"), tr("dg_gpu_none_d"))]
    out = []
    for i, line in enumerate(raw):
        try:
            name, total, used, driver = [x.strip() for x in line.split(",")]
            total, used = float(total), float(used)
        except ValueError:
            continue
        pct = used / max(total, 1)
        status = "error" if pct > 0.95 else "warn" if pct > 0.85 else "ok"
        detail = tr("dg_gpu_d", used=f"{used / 1024:.1f}", total=f"{total / 1024:.1f}", pct=round(pct * 100), driver=driver)
        if status != "ok":
            detail += " " + tr("dg_gpu_full")
        out.append(_item(f"gpu{i}", "system", status, name, detail, fix="free_vram" if status != "ok" else None))
    return out


def check_disk() -> list:
    try:
        usage = shutil.disk_usage(paths.ROOT)
    except OSError:
        return []
    free = usage.free
    status = "error" if free < 2 * 1024 ** 3 else "warn" if free < 10 * 1024 ** 3 else "ok"
    drive = os.path.splitdrive(paths.ROOT)[0] or paths.ROOT
    return [_item("disk", "system", status, tr("dg_disk", drive=drive, free=_gb(free)),
                  tr("dg_disk_low") if status != "ok" else "")]


# ── Voz ────────────────────────────────────────────────────────────────

def check_voice(listener_state: dict, runtime_status: dict, voice_enabled: bool) -> list:
    from app.core import voice_settings

    out = []
    stt = voice_settings.stt_model()
    out.append(_item("whisper", "voice", "ok" if runtime_status.get("stt_loaded") else "info",
                     tr("dg_whisper", m=stt), tr("dg_loaded_yes") if runtime_status.get("stt_loaded") else tr("dg_loaded_lazy")))
    out.append(_item("tts", "voice", "ok" if runtime_status.get("tts_loaded") else "info",
                     tr("dg_tts"), (tr("dg_tts_dev", d=runtime_status.get("tts_device")) if runtime_status.get("tts_loaded")
                                    else tr("dg_loaded_lazy"))))
    try:
        from app.voice.qwen_tts import engine

        q = engine().status()
        custom = voice_settings.load()["custom_voices"]
        if custom:
            state = q.get("state") or q.get("status") or ""
            bad = bool(q.get("error"))
            out.append(_item("qwen", "voice", "warn" if bad else "ok" if state in ("ready", "listo") else "info",
                             tr("dg_qwen", n=len(custom)), str(q.get("error") or state or "")))
    except Exception:  # noqa: BLE001
        pass
    # Micrófono de la PC (escucha manos libres).
    if not voice_enabled:
        out.append(_item("mic", "voice", "info", tr("dg_mic_off"), tr("dg_mic_off_d")))
        return out
    try:
        import sounddevice as sd

        dev = sd.query_devices(kind="input")
        mic_name = dev.get("name", "?")
    except Exception as e:  # noqa: BLE001
        out.append(_item("mic", "voice", "error", tr("dg_mic_none"), str(e)))
        return out
    st = listener_state or {}
    if st.get("muted"):
        out.append(_item("mic", "voice", "warn", tr("dg_mic_muted", name=mic_name), "", fix="mic_unmute"))
    elif st.get("status") == "error":
        out.append(_item("mic", "voice", "error", tr("dg_mic_error", name=mic_name), st.get("error") or "", fix="mic_retry"))
    else:
        out.append(_item("mic", "voice", "ok", tr("dg_mic_ok", name=mic_name), tr(f"dg_mic_{st.get('status') or 'idle'}")
                         if f"dg_mic_{st.get('status')}" in _MIC_KEYS else (st.get("status") or "")))
    return out


_MIC_KEYS = {"dg_mic_listening", "dg_mic_idle", "dg_mic_paused", "dg_mic_loading", "dg_mic_hearing", "dg_mic_transcribing"}


# ── Puertos, firewall, red ─────────────────────────────────────────────

def port_owner(port: int) -> str:
    """Programa que escucha en `port` (para decir quién lo ocupa)."""
    out = _run(["netstat", "-ano", "-p", "TCP"], 8)
    pid = None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3].upper() in ("LISTENING", "ESCUCHANDO"):
            pid = parts[4]
            break
    if not pid:
        return ""
    name = _run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], 8).strip().split(",")[0].strip('"')
    return f"{name or '?'} (PID {pid})"


def check_ports(ui_port: int, lan: dict) -> list:
    out = [_item("port_ui", "network", "ok", tr("dg_port_ui", port=ui_port), "")]
    if not lan.get("enabled"):
        out.append(_item("port_lan", "network", "info", tr("dg_lan_off"), tr("dg_lan_off_d")))
        return out
    if lan.get("running"):
        out.append(_item("port_lan", "network", "ok", tr("dg_lan_on", port=lan.get("port")), ", ".join(lan.get("urls") or [])[:300]))
    else:
        err = str(lan.get("error") or "")
        owner = port_owner(int(lan.get("port") or 8443)) if "10048" in err else ""
        out.append(_item("port_lan", "network", "error", tr("dg_lan_fail", port=lan.get("port")),
                         (tr("dg_port_busy", who=owner) if owner else err), fix="lan_restart"))
    return out


_FW_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$py = '%PY%'; $port = '%PORT%'
# Por programa y por puerto directamente (recorrer todas las reglas tarda >40 s).
$prog = @(Get-NetFirewallApplicationFilter -Program $py | Get-NetFirewallRule | Where-Object { $_.Direction -eq 'Inbound' -and $_.Enabled -eq 'True' })
$ports = @(Get-NetFirewallPortFilter -Protocol TCP | Where-Object { $_.LocalPort -eq $port } | Get-NetFirewallRule | Where-Object { $_.Direction -eq 'Inbound' -and $_.Enabled -eq 'True' })
$cat = @(Get-NetConnectionProfile | ForEach-Object { "$($_.Name)=$($_.NetworkCategory)" })
$on = @(Get-NetFirewallProfile | Where-Object Enabled | ForEach-Object Name)
@{prog=@($prog | Where-Object Action -eq 'Allow').Count; port=@($ports | Where-Object Action -eq 'Allow').Count;
  block=@($prog + $ports | Where-Object Action -eq 'Block').Count; networks=$cat; enabled=$on;
  public=@($prog + $ports | Where-Object { $_.Action -eq 'Allow' -and "$($_.Profile)" -match 'Public|Any' }).Count} | ConvertTo-Json -Compress
"""


def firewall_state(port: int, force: bool = False):
    now = time.time()
    if not force and _fw_cache["data"] is not None and now - _fw_cache["at"] < 60:
        return _fw_cache["data"]
    script = _FW_SCRIPT.replace("%PY%", sys.executable.replace("'", "''")).replace("%PORT%", str(port))
    raw = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], 40).strip()
    try:
        data = json.loads(raw.splitlines()[-1]) if raw else None
    except (ValueError, IndexError):
        data = None
    _fw_cache.update(at=now, data=data)
    return data


def check_firewall(lan: dict) -> list:
    if os.name != "nt" or not lan.get("enabled"):
        return []
    data = firewall_state(int(lan.get("port") or 8443))
    if data is None:
        return [_item("firewall", "network", "info", tr("dg_fw_unknown"), "")]
    out = []
    nets = [n for n in (data.get("networks") or []) if n]
    public = [n.split("=")[0] for n in nets if n.endswith("=Public") or n.endswith("=0")]
    if public and not data.get("public"):  # en red pública solo molesta si ninguna regla la cubre
        out.append(_item("netcat", "network", "warn", tr("dg_net_public", names=", ".join(public)), tr("dg_net_public_d"),
                         fix="net_private"))
    if not data.get("enabled"):
        out.append(_item("firewall", "network", "info", tr("dg_fw_disabled"), ""))
    elif data.get("block"):
        out.append(_item("firewall", "network", "error", tr("dg_fw_blocked"), tr("dg_fw_blocked_d"), fix="firewall_allow"))
    elif data.get("prog") or data.get("port"):
        out.append(_item("firewall", "network", "ok", tr("dg_fw_ok"), ""))
    else:
        out.append(_item("firewall", "network", "warn", tr("dg_fw_missing", port=lan.get("port")), tr("dg_fw_missing_d"),
                         fix="firewall_allow"))
    return out


def run_elevated(command: str) -> bool:
    """Corre un comando de PowerShell como administrador (Windows muestra
    el aviso de UAC en la PC). True si se aceptó y terminó bien. El comando
    va en un .ps1 temporal (así no hay comillas anidadas)."""
    import tempfile

    fd, script = tempfile.mkstemp(suffix=".ps1")
    with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
        f.write("$ErrorActionPreference = 'Stop'\n" + command + "\nexit 0\n")
    outer = (f"$p = Start-Process powershell -Verb RunAs -WindowStyle Hidden -Wait -PassThru "
             f"-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','{script}'; exit $p.ExitCode")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", outer], capture_output=True, text=True, timeout=180,
                           creationflags=NO_WINDOW)
        ok = r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    finally:
        try:
            os.remove(script)
        except OSError:
            pass
    _fw_cache["data"] = None
    return ok


def fix_firewall(port: int) -> bool:
    py = sys.executable.replace("'", "''")
    return run_elevated(
        f"Get-NetFirewallRule -DisplayName '{FIREWALL_RULE}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule; "
        f"Get-NetFirewallApplicationFilter -Program '{py}' | Get-NetFirewallRule | Where-Object {{ $_.Action -eq 'Block' -and $_.Direction -eq 'Inbound' }} | Remove-NetFirewallRule; "
        f"New-NetFirewallRule -DisplayName '{FIREWALL_RULE}' -Direction Inbound -Action Allow -Protocol TCP -LocalPort {int(port)} "
        f"-Profile Private,Domain | Out-Null")


def fix_network_private() -> bool:
    return run_elevated("Get-NetConnectionProfile | Where-Object NetworkCategory -eq 'Public' | "
                        "Set-NetConnectionProfile -NetworkCategory Private")


# ── Herramientas de archivos y documentos ──────────────────────────────

def check_extras() -> list:
    out = []
    ff = shutil.which("ffmpeg")
    out.append(_item("ffmpeg", "extras", "ok" if ff else "info", tr("dg_ffmpeg_ok" if ff else "dg_ffmpeg_none"),
                     "" if ff else tr("dg_ffmpeg_none_d"), link=None if ff else "https://www.gyan.dev/ffmpeg/builds/"))
    office = any(os.path.isdir(os.path.join(os.environ.get(v, ""), "Microsoft Office"))
                 for v in ("ProgramFiles", "ProgramFiles(x86)"))
    out.append(_item("office", "extras", "ok" if office else "info", tr("dg_office_ok" if office else "dg_office_none"), ""))
    from app.core import embeddings

    emb = embeddings.available()
    out.append(_item("embed", "extras", "ok" if emb else "info", tr("dg_embed_ok" if emb else "dg_embed_none"),
                     "" if emb else tr("dg_embed_none_d"), fix=None if emb else "pull_embed"))
    return out


def start_ollama() -> bool:
    exe = ollama_exe()
    if not exe:
        return False
    args = [exe] if exe.lower().endswith("app.exe") else [exe, "serve"]
    try:
        subprocess.Popen(args, creationflags=NO_WINDOW | getattr(subprocess, "DETACHED_PROCESS", 0),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    for _ in range(30):
        time.sleep(1)
        try:
            if requests.get(f"{OLLAMA}/api/version", timeout=2).ok:
                return True
        except requests.exceptions.RequestException:
            pass
    return False


def recommended_model() -> str:
    """El modelo que conviene según la VRAM (ver CONTEXTO_PROYECTO.md)."""
    raw = _run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"], 6).strip().splitlines()
    try:
        total = float(raw[0]) / 1024
    except (ValueError, IndexError):
        total = 0
    return "gemma4:E4B" if total >= 10 else "gemma4:e2b"


def short_error(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or ""))[:300]
