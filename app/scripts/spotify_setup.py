"""
Configuración inicial de Spotify: pide el Client ID/Secret de tu app de
developer.spotify.com, si tenés Premium o no, y (solo si sos Premium) te
hace iniciar sesión una vez en el navegador para poder controlar la
reproducción por voz. Todo queda guardado en spotify_config.yaml.

Ejecutar: spotify_setup.bat (o "python spotify_setup.py" directamente).
"""
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs

import requests
import yaml

# Ejecutado como script (los .bat): la raíz del proyecto va al path para
# poder importar el paquete `app` (el Python embebido no lo agrega solo).
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.paths import SPOTIFY_YAML as CONFIG_PATH

TOKEN_URL = "https://accounts.spotify.com/api/token"
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
REDIRECT_PORT = 8888
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"
SCOPES = "user-modify-playback-state user-read-playback-state"


class _CallbackHandler(BaseHTTPRequestHandler):
    """Recibe UNA sola petición: el redirect de Spotify con el código de
    autorización (o un error) en la URL."""

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        self.server.auth_code = query.get("code", [None])[0]
        self.server.auth_error = query.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if self.server.auth_code:
            body = "<html><body><h2>Listo, ya podés cerrar esta pestaña y volver a la consola.</h2></body></html>"
        else:
            body = f"<html><body><h2>Algo salió mal: {self.server.auth_error}</h2></body></html>"
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # sin esto, imprime una línea de log por cada petición HTTP


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(
            "# ══════════════════════════════════════════════════════════════════════\n"
            "# Credenciales y configuración de Spotify — generado/editado por\n"
            "# spotify_setup.bat. Ver ese script o el README para más detalle de\n"
            "# cada campo.\n"
            "# ══════════════════════════════════════════════════════════════════════\n"
        )
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def _check_credentials(client_id: str, client_secret: str) -> bool:
    """Pide un token por Client Credentials (no necesita login de usuario)
    solo para confirmar que el Client ID/Secret son válidos."""
    try:
        r = requests.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            timeout=15,
        )
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


def _run_oauth_flow(client_id: str, client_secret: str) -> str:
    """Hace el login de Spotify en el navegador y devuelve el
    refresh_token, o None si algo falla."""
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
    }
    auth_url = f"{AUTHORIZE_URL}?{urlencode(params)}"

    print(f"\nAbriendo el navegador para iniciar sesión en Spotify...")
    print(f"Si no se abre solo, entrá manualmente a esta dirección:\n{auth_url}\n")
    webbrowser.open(auth_url)

    try:
        server = HTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler)
    except OSError as e:
        print(
            f"No pude abrir el puerto {REDIRECT_PORT} para recibir el login "
            f"({e}). ¿Hay algo más usando ese puerto?"
        )
        return None

    server.auth_code = None
    server.auth_error = None
    print("Esperando a que completes el login en el navegador...")
    server.handle_request()  # bloquea hasta la primera petición (el redirect de Spotify)
    server.server_close()

    if not server.auth_code:
        print(f"No se pudo obtener el permiso ({server.auth_error}).")
        return None

    r = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": server.auth_code,
            "redirect_uri": REDIRECT_URI,
        },
        auth=(client_id, client_secret),
        timeout=15,
    )
    if r.status_code != 200:
        print(f"No se pudo intercambiar el código por un token ({r.status_code}: {r.text[:200]}).")
        return None

    return r.json().get("refresh_token")


def main():
    print("=== Configuración de Spotify ===\n")
    cfg = _load_config()

    print(
        "Antes de seguir, necesitás una app gratis en developer.spotify.com "
        "con este Redirect URI agregado en su configuración (Settings → "
        f"Redirect URIs):\n\n  {REDIRECT_URI}\n\n"
        "(Ver el README para el paso a paso completo si todavía no la creaste.)\n"
    )

    client_id = input(f"Client ID{' [' + cfg.get('client_id','')[:6] + '...]' if cfg.get('client_id') else ''}: ").strip() or cfg.get("client_id", "")
    client_secret = input("Client Secret: ").strip() or cfg.get("client_secret", "")

    if not client_id or not client_secret:
        print("Hace falta Client ID y Client Secret, cancelado.")
        sys.exit(1)

    print("\nProbando las credenciales...")
    if not _check_credentials(client_id, client_secret):
        print("El Client ID/Secret no parecen válidos. Revisalos en developer.spotify.com y probá de nuevo.")
        sys.exit(1)
    print("Credenciales válidas.")

    premium_input = input("\n¿Tenés Spotify Premium? [s/N]: ").strip().lower()
    premium = premium_input == "s"

    refresh_token = cfg.get("refresh_token", "")
    if premium:
        token = _run_oauth_flow(client_id, client_secret)
        if token:
            refresh_token = token
            print("\nInicio de sesión completado, ya podés controlar la reproducción por voz.")
        else:
            print("\nNo se completó el login — se guarda igual lo demás, podés volver a correr este script para intentarlo de nuevo.")
    else:
        refresh_token = ""
        print(
            "\nSin Premium: los asistentes van a poder buscar y arrancar música "
            "(canción/playlist/género), pero no pausar/saltar/subir volumen por voz."
        )

    _save_config({
        "client_id": client_id,
        "client_secret": client_secret,
        "premium": premium,
        "refresh_token": refresh_token,
    })
    print(f"\nListo, guardado en config\\spotify_config.yaml.")


if __name__ == "__main__":
    main()
