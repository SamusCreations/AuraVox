r"""
Initial Spotify setup: prompts for the Client ID/Secret of your app from
developer.spotify.com, asks whether you have Spotify Premium, and (if Premium)
opens the browser once to sign in so you can control playback by voice.
Everything is saved to config/spotify_config.yaml.

Run: extras\spotify_setup.bat (or "python app/scripts/spotify_setup.py").
"""
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs

import requests
import yaml

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
    """Handles a SINGLE request: the Spotify OAuth redirect containing the
    authorization code (or an error) in the URL query string."""

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        self.server.auth_code = query.get("code", [None])[0]
        self.server.auth_error = query.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if self.server.auth_code:
            body = "<html><body><h2>Done! You can close this tab and return to the console.</h2></body></html>"
        else:
            body = f"<html><body><h2>Something went wrong: {self.server.auth_error}</h2></body></html>"
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        pass


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
            "# Spotify credentials and settings — generated/updated by\n"
            "# spotify_setup.bat. See that script or README.md for details.\n"
            "# ══════════════════════════════════════════════════════════════════════\n"
        )
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def _check_credentials(client_id: str, client_secret: str) -> bool:
    """Requests a Client Credentials token (no user login required) just to
    verify that the Client ID and Secret are valid."""
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
    """Runs the Spotify login flow in the browser and returns the
    refresh_token, or None if anything fails."""
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
    }
    auth_url = f"{AUTHORIZE_URL}?{urlencode(params)}"

    print("\nOpening browser to sign in to Spotify...")
    print(f"If it does not open automatically, visit this URL manually:\n{auth_url}\n")
    webbrowser.open(auth_url)

    try:
        server = HTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler)
    except OSError as e:
        print(
            f"Could not bind port {REDIRECT_PORT} to receive the login callback "
            f"({e}). Is another process using that port?"
        )
        return None

    server.auth_code = None
    server.auth_error = None
    print("Waiting for you to complete login in the browser...")
    server.handle_request()
    server.server_close()

    if not server.auth_code:
        print(f"Could not obtain authorization ({server.auth_error}).")
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
        print(f"Could not exchange authorization code for a token ({r.status_code}: {r.text[:200]}).")
        return None

    return r.json().get("refresh_token")


def main():
    print("=== Spotify Setup ===\n")
    cfg = _load_config()

    print(
        "Before continuing, you need a free app at developer.spotify.com "
        "with this Redirect URI added to its configuration (Settings → "
        f"Redirect URIs):\n\n  {REDIRECT_URI}\n\n"
        "(See README.md for step-by-step instructions if you haven't created one yet.)\n"
    )

    client_id = input(f"Client ID{' [' + cfg.get('client_id','')[:6] + '...]' if cfg.get('client_id') else ''}: ").strip() or cfg.get("client_id", "")
    client_secret = input("Client Secret: ").strip() or cfg.get("client_secret", "")

    if not client_id or not client_secret:
        print("Client ID and Client Secret are required. Cancelled.")
        sys.exit(1)

    print("\nTesting credentials...")
    if not _check_credentials(client_id, client_secret):
        print("Client ID/Secret appear invalid. Check them at developer.spotify.com and try again.")
        sys.exit(1)
    print("Credentials are valid.")

    premium_input = input("\nDo you have Spotify Premium? [y/N]: ").strip().lower()
    premium = premium_input in ("y", "yes", "s", "si")

    refresh_token = cfg.get("refresh_token", "")
    if premium:
        token = _run_oauth_flow(client_id, client_secret)
        if token:
            refresh_token = token
            print("\nSign-in complete! You can now control playback by voice.")
        else:
            print("\nSign-in was not completed — saving credentials anyway; re-run this script to try again.")
    else:
        refresh_token = ""
        print(
            "\nWithout Premium: assistants will be able to search and launch music "
            "(track/playlist/genre), but cannot pause/skip/adjust volume via the Web API."
        )

    _save_config({
        "client_id": client_id,
        "client_secret": client_secret,
        "premium": premium,
        "refresh_token": refresh_token,
    })
    print("\nDone! Saved to config\\spotify_config.yaml.")


if __name__ == "__main__":
    main()
