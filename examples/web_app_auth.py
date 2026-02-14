"""Example: Web app OAuth flow with PKCE using the Barndoor SDK.

This shows how to integrate Barndoor auth into a web application (e.g. Flask,
FastAPI, Django). The key difference from the CLI flow is that the code_verifier
must be stored in your session between the authorization redirect and the
callback — you can't rely on in-process globals.

The SDK provides create_authorization_request() for this purpose.

Setup:
    pip install barndoor

    # .env (no BARNDOOR_ENV needed — defaults to production)
    AGENT_CLIENT_ID=your-client-id
    AGENT_CLIENT_SECRET=your-client-secret

Usage:
    python examples/web_app_auth.py

    Then open http://127.0.0.1:8090/login in your browser.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from barndoor.sdk.auth import create_authorization_request, exchange_code_for_token
from barndoor.sdk.config import get_static_config

PORT = 8090
CALLBACK_URL = f"http://127.0.0.1:{PORT}/callback"

# In a real app this would be a server-side session (e.g. Flask session, Redis)
session: dict = {}


def handle_login(handler: BaseHTTPRequestHandler) -> None:
    """Step 1: Build auth URL, store PKCE verifier in session, redirect."""
    cfg = get_static_config()

    auth_req = create_authorization_request(
        client_id=cfg.AGENT_CLIENT_ID,
        redirect_uri=CALLBACK_URL,
        audience=cfg.api_audience,
        issuer=cfg.auth_issuer,
    )

    # Store these in your session — needed for the callback
    session["code_verifier"] = auth_req.code_verifier
    session["oauth_state"] = auth_req.state

    handler.send_response(302)
    handler.send_header("Location", auth_req.url)
    handler.end_headers()


def handle_callback(handler: BaseHTTPRequestHandler, query: dict) -> None:
    """Step 2: Handle the OAuth callback, exchange code for token."""
    cfg = get_static_config()

    # Check for errors from the auth server
    if error := query.get("error", [""])[0]:
        error_desc = query.get("error_description", [error])[0]
        handler.send_response(400)
        handler.send_header("Content-Type", "text/plain")
        handler.end_headers()
        handler.wfile.write(f"Auth error: {error_desc}".encode())
        return

    # Validate state to prevent CSRF
    state = query.get("state", [""])[0]
    if state != session.get("oauth_state"):
        handler.send_response(400)
        handler.send_header("Content-Type", "text/plain")
        handler.end_headers()
        handler.wfile.write(b"State mismatch - possible CSRF")
        return

    # Exchange the authorization code for tokens
    code = query.get("code", [""])[0]
    token_data = exchange_code_for_token(
        domain="",
        client_id=cfg.AGENT_CLIENT_ID,
        code=code,
        redirect_uri=CALLBACK_URL,
        client_secret=cfg.AGENT_CLIENT_SECRET,
        issuer=cfg.auth_issuer,
        code_verifier=session["code_verifier"],  # <-- stored from Step 1
    )

    handler.send_response(200)
    handler.send_header("Content-Type", "text/plain")
    handler.end_headers()
    handler.wfile.write(
        f"Auth successful!\n\n"
        f"Access token: {token_data['access_token'][:50]}...\n"
        f"Expires in: {token_data.get('expires_in')}s\n"
        f"Scopes: {token_data.get('scope')}\n".encode()
    )


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/login":
            handle_login(self)
        elif parsed.path == "/callback":
            handle_callback(self, parse_qs(parsed.query))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_a, **_k):
        return


if __name__ == "__main__":
    cfg = get_static_config()
    print(f"SDK config:")
    print(f"  issuer:   {cfg.auth_issuer}")
    print(f"  audience: {cfg.api_audience}")
    print(f"  client:   {cfg.AGENT_CLIENT_ID}")
    print(f"\nOpen http://127.0.0.1:{PORT}/login to start the auth flow\n")

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
