"""Cliente MCP (Model Context Protocol): servidores MCP como herramientas.

Un servidor MCP expone herramientas (archivos, GitHub, calendarios, bases
de datos, domótica…) con un protocolo estándar: conectarlo da todas sus
herramientas a los asistentes sin escribirlas. Se configuran en Ajustes →
Servidores MCP (solo administradores) y se guardan en config/mcp.json:

  {"servers": [{"id", "name", "transport": "stdio" | "http",
                "command", "args": [...], "env": {...}, "cwd",   (stdio)
                "url", "headers": {...},                          (http)
                "enabled": true, "min_role": "admin"}]}

- stdio: AuraVox lanza el programa (p. ej. `npx -y @modelcontextprotocol/
  server-filesystem C:\\Users\\yo\\Documentos`) y habla con él por su entrada
  y salida estándar, JSON-RPC línea por línea.
- http: "Streamable HTTP": POST con JSON-RPC a la URL; la respuesta llega
  como JSON o como eventos (text/event-stream).

Solo biblioteca estándar (subprocess, threading, urllib). Cada servidor se
conecta en segundo plano al arrancar AuraVox (o al cambiar la
configuración); sus herramientas aparecen recién cuando está listo, con el
nombre <servidor>__<herramienta>. Por defecto solo los administradores las
pueden usar (pueden tocar archivos o cuentas): se puede bajar el rol.
"""
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.request

from app import paths

NAME = "mcp"
MIN_ROLE = "guest"

CONFIG_PATH = os.path.join(paths.CONFIG_DIR, "mcp.json")
PROTOCOL_VERSION = "2025-06-18"
ROLES = ("guest", "user", "admin")
RANKS = {"guest": 1, "user": 2, "admin": 3}
ID_RE = re.compile(r"^[a-z0-9_]{2,24}$")
MAX_SERVERS = 20
CALL_TIMEOUT = 120
START_TIMEOUT = 90   # npx puede tardar en descargar el paquete la primera vez
MAX_RESULT = 12000

_lock = threading.RLock()
_conns = {}   # id → Connection
_log = None   # lo fija el servidor: _log(mensaje, nivel)


def log(msg: str, level: str = "info") -> None:
    if _log:
        try:
            _log(msg, level)
            return
        except Exception:  # noqa: BLE001
            pass
    print(f"[mcp] {msg}")


# ── Configuración ──────────────────────────────────────────────────────

def load_config() -> list:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    servers = data.get("servers") if isinstance(data, dict) else None
    return [s for s in servers or [] if isinstance(s, dict) and ID_RE.match(str(s.get("id")))]


def _save_config(servers: list) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"servers": servers}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CONFIG_PATH)


def _clean(text, n: int) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", str(text or "")).strip()[:n]


def validate(data: dict, existing: list, sid: str = None) -> dict:
    """Servidor nuevo o editado, limpio. ValueError(clave) si falta algo."""
    name = _clean(data.get("name"), 40)
    if not name:
        raise ValueError("mcp_name")
    transport = data.get("transport") if data.get("transport") in ("stdio", "http") else "stdio"
    out = {"name": name, "transport": transport, "enabled": bool(data.get("enabled", True)),
           "min_role": data.get("min_role") if data.get("min_role") in ROLES else "admin"}
    if sid is None:
        base = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")[:20] or "mcp"
        base = base if len(base) >= 2 else base + "_s"
        sid, n = base, 2
        while any(s["id"] == sid for s in existing):
            sid = f"{base[:20]}{n}"
            n += 1
    out["id"] = sid
    if transport == "stdio":
        command = data.get("command")
        args = data.get("args")
        if isinstance(command, str) and not isinstance(args, list):
            # Una sola línea: "npx -y @modelcontextprotocol/server-filesystem C:\\docs"
            try:
                parts = shlex.split(command, posix=False)
            except ValueError:
                raise ValueError("mcp_command")
            parts = [p[1:-1] if len(p) > 1 and p[0] == p[-1] == '"' else p for p in parts]
            command, args = (parts[0], parts[1:]) if parts else ("", [])
        command = _clean(command, 500)
        if not command:
            raise ValueError("mcp_command")
        out["command"] = command
        out["args"] = [_clean(a, 1000) for a in (args or [])][:40]
        env = data.get("env") if isinstance(data.get("env"), dict) else {}
        out["env"] = {_clean(k, 100): _clean(v, 2000) for k, v in list(env.items())[:40] if _clean(k, 100)}
        out["cwd"] = _clean(data.get("cwd"), 500)
    else:
        url = _clean(data.get("url"), 1000)
        if not re.match(r"^https?://", url):
            raise ValueError("mcp_url")
        out["url"] = url
        headers = data.get("headers") if isinstance(data.get("headers"), dict) else {}
        out["headers"] = {_clean(k, 100): _clean(v, 2000) for k, v in list(headers.items())[:20] if _clean(k, 100)}
    return out


def add_server(data: dict) -> dict:
    with _lock:
        servers = load_config()
        if len(servers) >= MAX_SERVERS:
            raise OverflowError(MAX_SERVERS)
        s = validate(data, servers)
        servers.append(s)
        _save_config(servers)
    restart(s["id"])
    return s


def update_server(sid: str, data: dict) -> dict:
    with _lock:
        servers = load_config()
        i = next((i for i, s in enumerate(servers) if s["id"] == sid), None)
        if i is None:
            raise KeyError(sid)
        merged = {**servers[i], **{k: v for k, v in data.items() if k in ("enabled", "min_role")}}
        if any(k in data for k in ("name", "command", "args", "env", "cwd", "url", "headers", "transport")):
            merged = validate({**servers[i], **data}, servers, sid)
        else:
            merged["min_role"] = merged.get("min_role") if merged.get("min_role") in ROLES else "admin"
            merged["enabled"] = bool(merged.get("enabled"))
        servers[i] = merged
        _save_config(servers)
    restart(sid)
    return merged


def remove_server(sid: str) -> None:
    with _lock:
        servers = [s for s in load_config() if s["id"] != sid]
        _save_config(servers)
        conn = _conns.pop(sid, None)
    if conn:
        conn.close()


# ── Conexiones ─────────────────────────────────────────────────────────

class McpError(Exception):
    pass


class Connection:
    """Una conexión a un servidor MCP (stdio o http), con su estado."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.status = "starting"   # starting | ready | error | stopped
        self.error = ""
        self.tools = []            # herramientas MCP tal cual: {"name", "description", "inputSchema"}
        self.server_info = {}
        self._next_id = 0
        self._id_lock = threading.Lock()

    def new_id(self) -> int:
        with self._id_lock:
            self._next_id += 1
            return self._next_id

    # Lo que cambia según el transporte.
    def request(self, method: str, params: dict = None, timeout: float = CALL_TIMEOUT) -> dict:
        raise NotImplementedError

    def notify(self, method: str, params: dict = None) -> None:
        raise NotImplementedError

    def close(self) -> None:
        self.status = "stopped"

    # Común.
    def start(self) -> None:
        try:
            self.open()
            init = self.request("initialize", {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "AuraVox", "version": "1.0"},
            }, timeout=START_TIMEOUT)
            self.server_info = init.get("serverInfo") or {}
            self.notify("notifications/initialized")
            tools, cursor = [], None
            for _ in range(20):
                page = self.request("tools/list", {"cursor": cursor} if cursor else {}, timeout=60)
                tools += [t for t in page.get("tools") or [] if isinstance(t, dict) and t.get("name")]
                cursor = page.get("nextCursor")
                if not cursor:
                    break
            self.tools = tools
            self.status = "ready"
            log(f"{self.cfg['name']}: conectado ({self.server_info.get('name', '?')}), {len(tools)} herramienta(s)")
        except Exception as e:  # noqa: BLE001
            self.status = "error"
            self.error = str(e)[:500]
            log(f"{self.cfg['name']}: no pude conectar: {e}", "warn")
            self.close()
            self.status = "error"

    def open(self) -> None:
        pass

    def call_tool(self, name: str, arguments: dict) -> str:
        if self.status != "ready":
            raise McpError(f"the server {self.cfg['name']} isn't connected ({self.error or self.status})")
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        parts = []
        for c in result.get("content") or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "text":
                parts.append(str(c.get("text") or ""))
            elif c.get("type") == "resource":
                res = c.get("resource") or {}
                parts.append(str(res.get("text") or f"[resource {res.get('uri', '')}]"))
            elif c.get("type") in ("image", "audio"):
                parts.append(f"[{c['type']} ({c.get('mimeType', '')}) returned by the tool]")
            elif c.get("type") == "resource_link":
                parts.append(f"[link: {c.get('name') or ''} {c.get('uri') or ''}]")
        if not parts and result.get("structuredContent") is not None:
            parts.append(json.dumps(result["structuredContent"], ensure_ascii=False))
        text = "\n".join(p for p in parts if p).strip() or "(the tool returned nothing)"
        if len(text) > MAX_RESULT:
            text = text[:MAX_RESULT] + "\n[... cut]"
        if result.get("isError"):
            return f"The tool reported an error: {text}"
        return text


class StdioConnection(Connection):
    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.proc = None
        self._pending = {}
        self._cond = threading.Condition()
        self._write_lock = threading.Lock()

    def open(self) -> None:
        cmd = self.cfg["command"]
        exe = shutil.which(cmd) or cmd  # "npx" → npx.cmd en Windows
        env = {**os.environ, **(self.cfg.get("env") or {})}
        self.proc = subprocess.Popen(
            [exe, *self.cfg.get("args", [])], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=self.cfg.get("cwd") or None, env=env, bufsize=0,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Thread(target=self._read, name=f"mcp-{self.cfg['id']}", daemon=True).start()
        threading.Thread(target=self._read_err, name=f"mcp-{self.cfg['id']}-err", daemon=True).start()

    def _read(self) -> None:
        proc = self.proc
        try:
            for raw in iter(proc.stdout.readline, b""):
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if isinstance(msg, dict) and "id" in msg and ("result" in msg or "error" in msg):
                    with self._cond:
                        self._pending[msg["id"]] = msg
                        self._cond.notify_all()
                elif isinstance(msg, dict) and msg.get("method") and "id" in msg:
                    # Pedido del servidor (ping, sampling…): se responde que no se soporta, salvo ping.
                    reply = {"jsonrpc": "2.0", "id": msg["id"]}
                    if msg["method"] == "ping":
                        reply["result"] = {}
                    else:
                        reply["error"] = {"code": -32601, "message": "not supported by AuraVox"}
                    self._send(reply)
        except (OSError, ValueError):
            pass
        finally:
            if self.status not in ("stopped",):
                self.status = "error"
                self.error = self.error or f"the process ended (code {proc.poll()})"
            with self._cond:
                self._cond.notify_all()

    def _read_err(self) -> None:
        try:
            for raw in iter(self.proc.stderr.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip()
                if line:
                    log(f"{self.cfg['name']}: {line[:300]}")
        except (OSError, ValueError):
            pass

    def _send(self, msg: dict) -> None:
        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        with self._write_lock:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()

    def request(self, method: str, params: dict = None, timeout: float = CALL_TIMEOUT) -> dict:
        if not self.proc or self.proc.poll() is not None:
            raise McpError(f"the process isn't running ({self.error or 'ended'})")
        rid = self.new_id()
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, **({"params": params} if params is not None else {})})
        deadline = time.monotonic() + timeout
        with self._cond:
            while rid not in self._pending:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise McpError(f"{method}: no answer after {timeout:.0f} s")
                if self.proc.poll() is not None:
                    raise McpError(f"the process ended (code {self.proc.poll()})")
                self._cond.wait(min(left, 1.0))
            msg = self._pending.pop(rid)
        if "error" in msg:
            err = msg["error"] or {}
            raise McpError(f"{method}: {err.get('message', err)}")
        return msg.get("result") or {}

    def notify(self, method: str, params: dict = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})})

    def close(self) -> None:
        super().close()
        p = self.proc
        if p and p.poll() is None:
            try:
                p.stdin.close()
                p.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                pass
            if p.poll() is None:
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, timeout=10,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                except (OSError, subprocess.TimeoutExpired):
                    p.kill()


class HttpConnection(Connection):
    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.session_id = None
        self.negotiated = None

    def _post(self, msg: dict, timeout: float):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "User-Agent": "AuraVox-MCP/1.0", **(self.cfg.get("headers") or {})}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.negotiated:
            headers["MCP-Protocol-Version"] = self.negotiated
        req = urllib.request.Request(self.cfg["url"], data=json.dumps(msg).encode("utf-8"), headers=headers, method="POST")
        try:
            return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 — URL que eligió el administrador
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode("utf-8", "replace")
            raise McpError(f"HTTP {e.code}: {body}")
        except urllib.error.URLError as e:
            raise McpError(f"couldn't reach {self.cfg['url']}: {e.reason}")

    def request(self, method: str, params: dict = None, timeout: float = CALL_TIMEOUT) -> dict:
        rid = self.new_id()
        resp = self._post({"jsonrpc": "2.0", "id": rid, "method": method, **({"params": params} if params is not None else {})}, timeout)
        with resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self.session_id = sid
            ctype = resp.headers.get("Content-Type", "")
            msg = None
            if ctype.startswith("text/event-stream"):
                data_lines = []
                for raw in resp:
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                    elif not line and data_lines:
                        try:
                            m = json.loads("\n".join(data_lines))
                        except ValueError:
                            m = None
                        data_lines = []
                        if isinstance(m, dict) and m.get("id") == rid and ("result" in m or "error" in m):
                            msg = m
                            break
            else:
                try:
                    m = json.loads(resp.read().decode("utf-8"))
                except ValueError:
                    raise McpError(f"{method}: the answer isn't JSON")
                msg = next((x for x in (m if isinstance(m, list) else [m]) if isinstance(x, dict) and x.get("id") == rid), None)
        if msg is None:
            raise McpError(f"{method}: no answer")
        if "error" in msg:
            err = msg["error"] or {}
            raise McpError(f"{method}: {err.get('message', err)}")
        result = msg.get("result") or {}
        if method == "initialize":
            self.negotiated = result.get("protocolVersion") or PROTOCOL_VERSION
        return result

    def notify(self, method: str, params: dict = None) -> None:
        try:
            self._post({"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}, 30).close()
        except McpError:
            pass

    def close(self) -> None:
        super().close()
        if self.session_id:
            try:
                headers = {"Mcp-Session-Id": self.session_id, **(self.cfg.get("headers") or {})}
                urllib.request.urlopen(urllib.request.Request(self.cfg["url"], headers=headers, method="DELETE"), timeout=5)  # noqa: S310
            except Exception:  # noqa: BLE001
                pass


def _connect(cfg: dict) -> Connection:
    conn = HttpConnection(cfg) if cfg.get("transport") == "http" else StdioConnection(cfg)
    threading.Thread(target=conn.start, name=f"mcp-start-{cfg['id']}", daemon=True).start()
    return conn


def restart(sid: str = None) -> None:
    """(Re)conecta un servidor, o todos los activados si sid es None."""
    with _lock:
        cfgs = {s["id"]: s for s in load_config()}
        targets = [sid] if sid else list(set(cfgs) | set(_conns))
        for t in targets:
            old = _conns.pop(t, None)
            if old:
                threading.Thread(target=old.close, daemon=True).start()
            cfg = cfgs.get(t)
            if cfg and cfg.get("enabled", True):
                _conns[t] = _connect(cfg)


def start_all(logger=None) -> None:
    global _log
    _log = logger
    restart()


def stop_all() -> None:
    with _lock:
        conns = list(_conns.values())
        _conns.clear()
    for c in conns:
        c.close()


def status() -> list:
    out = []
    with _lock:
        conns = dict(_conns)
    for s in load_config():
        c = conns.get(s["id"])
        view = {k: s.get(k) for k in ("id", "name", "transport", "command", "args", "cwd", "url", "enabled", "min_role")}
        view["env_keys"] = sorted((s.get("env") or {}).keys())
        view["header_keys"] = sorted((s.get("headers") or {}).keys())
        view["status"] = c.status if c else ("stopped" if not s.get("enabled", True) else "starting")
        view["error"] = c.error if c else ""
        view["tools"] = [t["name"] for t in (c.tools if c else [])]
        view["server"] = (c.server_info.get("name") if c else "") or ""
        out.append(view)
    return out


# ── Habilidad (ver app/core/skills.py) ─────────────────────────────────
# Nombre para el modelo: <servidor>__<herramienta> (máx. 64, sin símbolos).

def _tool_name(sid: str, name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", f"{sid}__{name}")[:64]


def _usable(ctx) -> list:
    role = getattr(ctx, "role", "admin") if ctx is not None else "admin"
    with _lock:
        conns = dict(_conns)
    out = []
    for s in load_config():
        c = conns.get(s["id"])
        if c and c.status == "ready" and s.get("enabled", True) and RANKS.get(role, 0) >= RANKS.get(s.get("min_role"), 3):
            out.append((s, c))
    return out


def tools(ctx) -> list:
    out = []
    for s, c in _usable(ctx):
        for t in c.tools:
            schema = t.get("inputSchema") if isinstance(t.get("inputSchema"), dict) else {"type": "object", "properties": {}}
            schema = {k: v for k, v in schema.items() if k != "$schema"}
            desc = str(t.get("description") or t.get("title") or "")[:1000]
            out.append({"type": "function", "function": {
                "name": _tool_name(s["id"], t["name"]),
                "description": f"[{s['name']}] {desc}".strip(),
                "parameters": schema,
            }})
    return out


def call(name: str, args: dict, ctx):
    for s, c in _usable(ctx):
        for t in c.tools:
            if _tool_name(s["id"], t["name"]) == name:
                try:
                    return c.call_tool(t["name"], args)
                except McpError as e:
                    return f"The {s['name']} server failed: {e}. Tell the user plainly."
                except Exception as e:  # noqa: BLE001
                    traceback.print_exc()
                    return f"The {s['name']} server failed: {e}. Tell the user plainly."
    return None
