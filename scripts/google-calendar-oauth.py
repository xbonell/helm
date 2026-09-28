#!/usr/bin/env python3
"""One-shot Google OAuth consent for Calendar read-only scope.

Prints the refresh token to stdout (human hints on stderr). Never writes secrets
into the repo. Requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the
environment or via --client-id / --client-secret.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Event

SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_PORT = 8765


class _OAuthHandler(BaseHTTPRequestHandler):
    code: str | None = None
    error: str | None = None
    done: Event
    expected_state: str = ""

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "error" in params:
            _OAuthHandler.error = params["error"][0]
        elif "code" in params:
            returned_state = params.get("state", [""])[0]
            if returned_state != _OAuthHandler.expected_state:
                _OAuthHandler.error = "state_mismatch"
            else:
                _OAuthHandler.code = params["code"][0]
        else:
            self.send_response(404)
            self.end_headers()
            return
        body = b"<html><body><p>Authorization complete. You can close this tab.</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.done.set()


def _exchange_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict:
    body = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Obtain a Google Calendar OAuth refresh token (read-only)."
    )
    parser.add_argument(
        "--client-id",
        default=os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
        help="OAuth client id (default: GOOGLE_CLIENT_ID env)",
    )
    parser.add_argument(
        "--client-secret",
        default=os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
        help="OAuth client secret (default: GOOGLE_CLIENT_SECRET env)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Loopback redirect port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the authorize URL instead of opening a browser",
    )
    args = parser.parse_args()

    if not args.client_id or not args.client_secret:
        print(
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET (or pass --client-id / --client-secret).",
            file=sys.stderr,
        )
        return 1

    redirect_uri = f"http://127.0.0.1:{args.port}/"
    oauth_state = secrets.token_urlsafe(32)
    params = {
        "client_id": args.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": oauth_state,
    }
    authorize_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    done = Event()
    _OAuthHandler.done = done
    _OAuthHandler.code = None
    _OAuthHandler.error = None
    _OAuthHandler.expected_state = oauth_state

    server = HTTPServer(("127.0.0.1", args.port), _OAuthHandler)
    server.socket.settimeout(1.0)
    print(
        f"Listening on {redirect_uri} — add this redirect URI to your OAuth client if needed.",
        file=sys.stderr,
    )
    if args.no_browser:
        print(authorize_url, file=sys.stderr)
    else:
        print("Opening browser for Google sign-in…", file=sys.stderr)
        webbrowser.open(authorize_url)

    while not done.is_set():
        try:
            server.handle_request()
        except TimeoutError:
            continue

    if _OAuthHandler.error:
        print(f"Authorization failed: {_OAuthHandler.error}", file=sys.stderr)
        return 1
    if not _OAuthHandler.code:
        print("No authorization code received.", file=sys.stderr)
        return 1

    try:
        token_payload = _exchange_code(
            client_id=args.client_id,
            client_secret=args.client_secret,
            code=_OAuthHandler.code,
            redirect_uri=redirect_uri,
        )
    except urllib.error.HTTPError as exc:
        msg = "request failed"
        try:
            err_json = json.loads(exc.read().decode())
            msg = err_json.get("error_description") or err_json.get("error") or msg
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        print(f"Token exchange failed ({exc.code}): {msg}", file=sys.stderr)
        return 1

    refresh = token_payload.get("refresh_token")
    if not refresh:
        print(
            "No refresh_token in response. Revoke prior access for this client in "
            "Google Account → Security → Third-party access, then run again with prompt=consent.",
            file=sys.stderr,
        )
        return 1

    print(
        "Paste the line below into your host .env as GOOGLE_REFRESH_TOKEN (never commit .env):",
        file=sys.stderr,
    )
    sys.stdout.write(refresh + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
