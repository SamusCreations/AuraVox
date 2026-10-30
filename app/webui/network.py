"""Acceso a la interfaz desde otros dispositivos de la red local.

La interfaz de siempre sigue en http://127.0.0.1:8765 (solo esta PC). Con
el acceso por red activado (Ajustes compartidos → Acceso desde otros
dispositivos) se abre ADEMÁS un servidor HTTPS en todas las interfaces
(puerto LAN_PORT) con el mismo contenido:

- HTTPS porque los navegadores solo dejan usar el micrófono y la cámara en
  páginas seguras (o en localhost): por http://192.168.x.x la conversación
  por voz no funcionaría en el celular. El certificado lo genera la propia
  app (autofirmado, para las IP de esta PC): la primera vez el navegador
  avisa que no lo conoce y hay que aceptarlo ("Avanzado → Continuar").
  Se genera en Python puro (RSA + X.509 a mano) porque el Python del
  proyecto no trae librerías de criptografía.
- Con clave: el enlace (o el código QR) lleva ?key=…; la primera visita la
  guarda en una cookie y ya no hace falta. Sin la clave no se entra (en la
  red puede haber otros). "Cambiar la clave" desconecta a todos.
- Desde otro dispositivo no se usa la escucha manos libres (sería el
  micrófono de la PC, no el del celular): ese dispositivo usa el suyo.
"""
import base64
import datetime
import hashlib
import ipaddress
import json
import os
import secrets
import socket
import ssl
import threading
from http.server import ThreadingHTTPServer

from app import paths
from app.webui import server_log

LAN_PORT = 8443
SETTINGS_FILE = os.path.join(paths.CONFIG_DIR, "network.json")
CERT_DIR = os.path.join(paths.CONFIG_DIR, "certs")
CERT_FILE = os.path.join(CERT_DIR, "lan_cert.pem")
KEY_FILE = os.path.join(CERT_DIR, "lan_key.pem")
COOKIE = "asistentes_lan"

_lock = threading.Lock()
_server = {"httpd": None, "thread": None, "error": None}


def _log(msg: str, level: str = "info") -> None:
    server_log.log("network", msg, level)


# ── Ajustes ────────────────────────────────────────────────────────────

def settings() -> dict:
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    changed = False
    if not isinstance(data.get("token"), str) or len(data["token"]) < 16:
        data["token"] = secrets.token_urlsafe(18)
        changed = True
    if "enabled" not in data:
        data["enabled"] = True
        changed = True
    data.setdefault("port", LAN_PORT)
    if changed:
        _save(data)
    return data


def _save(data: dict) -> None:
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SETTINGS_FILE)


def new_token() -> str:
    data = settings()
    data["token"] = secrets.token_urlsafe(18)
    _save(data)
    _log("access key changed: connected devices must reopen the link")
    return data["token"]


def token_ok(value: str) -> bool:
    return bool(value) and secrets.compare_digest(str(value), settings()["token"])


# ── Direcciones de esta PC ─────────────────────────────────────────────

def _usable(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.version != 4 or addr.is_loopback or addr.is_link_local:
        return False
    return addr.is_private or addr in ipaddress.ip_network("100.64.0.0/10")  # CGNAT (Tailscale…)


def local_ips() -> list:
    ips = set()
    try:  # la de la ruta por defecto (no manda ningún paquete)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    primary = next(iter(ips), None)
    ordered = sorted((ip for ip in ips if _usable(ip)), key=lambda ip: (not ip.startswith("192.168."), ip))
    return ordered


def host_names() -> set:
    name = socket.gethostname().lower()
    return {"localhost", "127.0.0.1", name, f"{name}.local", *local_ips()}


# ── Certificado autofirmado (RSA 2048 + X.509 en Python puro) ──────────

_SMALL_PRIMES = [p for p in range(3, 2000, 2) if all(p % d for d in range(3, int(p ** 0.5) + 1, 2))]


def _probable_prime(n: int) -> bool:
    if any(n % p == 0 for p in _SMALL_PRIMES):
        return n in _SMALL_PRIMES
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(40):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits: int) -> int:
    while True:
        n = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if _probable_prime(n):
            return n


def _rsa_key(bits: int = 2048) -> dict:
    e = 65537
    while True:
        p, q = _prime(bits // 2), _prime(bits // 2)
        phi = (p - 1) * (q - 1)
        if p != q and phi % e and (p * q).bit_length() == bits:
            break
    d = pow(e, -1, phi)
    return {"n": p * q, "e": e, "d": d, "p": p, "q": q, "dp": d % (p - 1), "dq": d % (q - 1), "qi": pow(q, -1, p)}


def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _len(len(value)) + value


def _int(n: int) -> bytes:
    raw = n.to_bytes(max(1, (n.bit_length() + 8) // 8), "big")  # con un 0 delante si hace falta (positivo)
    return _tlv(0x02, raw)


def _seq(*items: bytes) -> bytes:
    return _tlv(0x30, b"".join(items))


def _oid(dotted: str) -> bytes:
    parts = [int(x) for x in dotted.split(".")]
    out = bytearray([parts[0] * 40 + parts[1]])
    for p in parts[2:]:
        chunk = [p & 0x7F]
        p >>= 7
        while p:
            chunk.append(0x80 | (p & 0x7F))
            p >>= 7
        out += bytes(reversed(chunk))
    return _tlv(0x06, bytes(out))


def _name(cn: str) -> bytes:
    return _seq(_tlv(0x31, _seq(_oid("2.5.4.3"), _tlv(0x0C, cn.encode()))),
                _tlv(0x31, _seq(_oid("2.5.4.10"), _tlv(0x0C, "AuraVox".encode()))))


def _time(t: datetime.datetime) -> bytes:
    return _tlv(0x17, t.strftime("%y%m%d%H%M%SZ").encode())


def _pem(label: str, der: bytes) -> str:
    b64 = base64.b64encode(der).decode()
    return f"-----BEGIN {label}-----\n" + "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64)) + f"\n-----END {label}-----\n"


def make_certificate(names: list, ips: list) -> tuple:
    """(cert PEM, clave PEM) autofirmado para esos nombres e IP."""
    key = _rsa_key()
    now = datetime.datetime.now(datetime.timezone.utc)
    sha256_rsa = _seq(_oid("1.2.840.113549.1.1.11"), _tlv(0x05, b""))
    public_key = _seq(_seq(_oid("1.2.840.113549.1.1.1"), _tlv(0x05, b"")),
                      _tlv(0x03, b"\x00" + _seq(_int(key["n"]), _int(key["e"]))))
    san = b"".join([_tlv(0x82, n.encode()) for n in names] + [_tlv(0x87, socket.inet_aton(ip)) for ip in ips])
    extensions = _seq(
        _seq(_oid("2.5.29.17"), _tlv(0x04, _seq(san))),                                     # subjectAltName
        _seq(_oid("2.5.29.19"), _tlv(0x01, b"\xff"), _tlv(0x04, _seq())),                  # basicConstraints CA:false
        _seq(_oid("2.5.29.15"), _tlv(0x01, b"\xff"), _tlv(0x04, _tlv(0x03, b"\x05\xa0"))),  # keyUsage
        _seq(_oid("2.5.29.37"), _tlv(0x04, _seq(_oid("1.3.6.1.5.5.7.3.1")))),              # serverAuth
    )
    subject = _name(f"AuraVox ({socket.gethostname()})")
    tbs = _seq(
        _tlv(0xA0, _int(2)),
        _int(secrets.randbits(63) | 1),
        sha256_rsa,
        subject,
        _seq(_time(now - datetime.timedelta(days=1)), _time(now + datetime.timedelta(days=395))),
        subject,
        public_key,
        _tlv(0xA3, extensions),
    )
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(tbs).digest()
    k = (key["n"].bit_length() + 7) // 8
    em = b"\x00\x01" + b"\xff" * (k - len(digest_info) - 3) + b"\x00" + digest_info
    signature = pow(int.from_bytes(em, "big"), key["d"], key["n"]).to_bytes(k, "big")
    cert = _seq(tbs, sha256_rsa, _tlv(0x03, b"\x00" + signature))
    private = _seq(*(_int(x) for x in (0, key["n"], key["e"], key["d"], key["p"], key["q"], key["dp"], key["dq"], key["qi"])))
    return _pem("CERTIFICATE", cert), _pem("RSA PRIVATE KEY", private)


def ensure_certificate() -> None:
    """Certificado vigente y que cubra las IP actuales (cambian con el DHCP)."""
    ips = local_ips()
    names = sorted({"localhost", socket.gethostname().lower(), f"{socket.gethostname().lower()}.local"})
    meta_file = CERT_FILE + ".json"
    try:
        with open(meta_file, encoding="utf-8") as f:
            meta = json.load(f)
        if (os.path.isfile(CERT_FILE) and os.path.isfile(KEY_FILE) and set(ips) <= set(meta.get("ips", []))
                and meta.get("expires", 0) > datetime.datetime.now().timestamp() + 30 * 86400):
            return
    except (OSError, ValueError):
        pass
    _log(f"generating HTTPS certificate for {', '.join(names + ['127.0.0.1'] + ips)}…")
    cert, key = make_certificate(names, ["127.0.0.1", *ips])
    os.makedirs(CERT_DIR, exist_ok=True)
    with open(CERT_FILE, "w", encoding="ascii") as f:
        f.write(cert)
    with open(KEY_FILE, "w", encoding="ascii") as f:
        f.write(key)
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({"ips": ["127.0.0.1", *ips], "names": names,
                   "expires": (datetime.datetime.now() + datetime.timedelta(days=395)).timestamp()}, f)


# ── Servidor HTTPS ─────────────────────────────────────────────────────

class LanServer(ThreadingHTTPServer):
    """El mismo Handler, por HTTPS y en todas las interfaces. El cifrado se
    negocia en el hilo de cada conexión (si se hiciera al aceptarla, un
    cliente lento trabaría a los demás)."""
    daemon_threads = True
    lan = True
    # Puerto exclusivo (como _Server en config_ui): con SO_REUSEADDR, en
    # Windows dos procesos podían escuchar el 8443 a la vez y las conexiones
    # del celular iban a cualquiera de los dos.
    allow_reuse_address = False

    def __init__(self, address, handler, context):
        self.context = context
        super().__init__(address, handler)

    def finish_request(self, request, client_address):
        request.settimeout(20)
        try:
            tls = self.context.wrap_socket(request, server_side=True)
        except (ssl.SSLError, OSError):
            return  # p. ej. el navegador rechazó el certificado (todavía no se aceptó)
        try:
            tls.settimeout(None)
            super().finish_request(tls, client_address)
        finally:
            try:
                tls.close()
            except OSError:
                pass


def start(handler_cls) -> None:
    with _lock:
        if _server["httpd"]:
            return
        cfg = settings()
        if not cfg["enabled"]:
            return
        try:
            ensure_certificate()
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(CERT_FILE, KEY_FILE)
            httpd = LanServer(("0.0.0.0", int(cfg["port"])), handler_cls, ctx)
        except (OSError, ssl.SSLError, ValueError) as e:
            _server["error"] = str(e)
            _log(f"could not start LAN access on port {cfg['port']}: {e}", "error")
            return
        thread = threading.Thread(target=httpd.serve_forever, name="lan-https", daemon=True)
        thread.start()
        _server.update(httpd=httpd, thread=thread, error=None)
    _log("LAN access enabled: " + ", ".join(urls(with_key=False)))


def stop() -> None:
    with _lock:
        httpd = _server["httpd"]
        _server.update(httpd=None, thread=None)
    if httpd:
        httpd.shutdown()
        httpd.server_close()
        _log("LAN access closed")


def set_enabled(on: bool, handler_cls) -> None:
    data = settings()
    data["enabled"] = bool(on)
    _save(data)
    if on:
        start(handler_cls)
    else:
        stop()


def urls(with_key: bool = True) -> list:
    cfg = settings()
    key = f"/?key={cfg['token']}" if with_key else "/"
    return [f"https://{ip}:{cfg['port']}{key}" for ip in local_ips()]


def status(local: bool) -> dict:
    cfg = settings()
    return {
        "enabled": cfg["enabled"],
        "running": _server["httpd"] is not None,
        "port": cfg["port"],
        "error": _server["error"],
        "hostname": socket.gethostname(),
        # La clave solo se le muestra a la propia PC.
        "urls": urls(with_key=local) if cfg["enabled"] else [],
        "local": local,
    }
