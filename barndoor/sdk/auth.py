"""Minimal Auth0 helper functions required by examples/sample_agent.py.

These helpers implement:
    • OAuth 2.0 client-credentials flow (`get_client_credentials_token`)
    • Interactive PKCE login helpers (`build_authorization_url`,
      `start_local_callback_server`, `exchange_code_for_token`)

No JWT verification or Auth0 Management API calls are included – the sample
script only needs to obtain a user token, not inspect its contents.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import threading
from collections.abc import Awaitable
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

__all__ = [
    "get_client_credentials_token",
    "build_authorization_url",
    "start_local_callback_server",
    "exchange_code_for_token",
    "exchange_code_for_token_backend",
    "refresh_access_token",
]

_code_verifier: str | None = None
_current_state: str | None = None


def _b64url(data: bytes) -> str:
    """Base64-url encode *data* without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def get_client_credentials_token(
    domain: str,
    client_id: str,
    client_secret: str,
    audience: str,
) -> str:
    """Perform OAuth 2.0 client-credentials grant and return the access token.

    This implements the standard OAuth 2.0 client credentials flow, typically
    used for machine-to-machine authentication where no user interaction is
    required.

    Parameters
    ----------
    domain : str
        Auth0 domain (e.g., "barndoor.us.auth0.com")
    client_id : str
        OAuth client ID for the application
    client_secret : str
        OAuth client secret for the application
    audience : str
        API audience identifier (e.g., "https://barndoor.ai/")

    Returns
    -------
    str
        The access token that can be used for API authentication

    Raises
    ------
    httpx.HTTPStatusError
        If the token request fails (e.g., invalid credentials)
    httpx.TimeoutException
        If the request times out

    Notes
    -----
    The token is returned directly without any caching. For user tokens
    that should be cached, use the interactive login flow instead.
    """
    resp = httpx.post(
        f"https://{domain}/oauth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "audience": audience,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def build_authorization_url(
    domain: str,
    client_id: str,
    redirect_uri: str,
    audience: str,
    scope: str = "openid profile email offline_access",
) -> str:
    """Build a PKCE-enabled Auth0 authorization URL.

    Constructs the URL for initiating an OAuth 2.0 authorization code flow
    with PKCE (Proof Key for Code Exchange) for enhanced security. This is
    used for interactive user authentication.

    Parameters
    ----------
    domain : str
        Auth0 domain (e.g., "barndoor.us.auth0.com")
    client_id : str
        OAuth client ID for the application
    redirect_uri : str
        URL where Auth0 will redirect after authentication
    audience : str
        API audience identifier (e.g., "https://barndoor.ai/")
    scope : str, optional
        OAuth scopes to request. Default is "openid profile email offline_access"

    Returns
    -------
    str
        The complete authorization URL to open in a browser

    Side Effects
    ------------
    Sets global variables _code_verifier and _current_state that will be
    needed later for the token exchange.

    Notes
    -----
    This function generates cryptographically secure PKCE parameters:
    - code_verifier: A random string used to prove possession of the code
    - code_challenge: SHA256 hash of the verifier
    - state: Random value to prevent CSRF attacks
    """
    global _code_verifier, _current_state

    _code_verifier = _b64url(secrets.token_bytes(32))
    code_challenge = _b64url(hashlib.sha256(_code_verifier.encode()).digest())
    _current_state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "audience": audience,
        "scope": scope,
        "state": _current_state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "consent",  # Forces consent screen for refresh tokens
    }
    return f"https://{domain}/authorize?{urlencode(params)}"


def start_local_callback_server(
    port: int = 0,
    path: str = "/cb",
) -> tuple[str, Awaitable[tuple[str, str]]]:
    """Start a local HTTP server to capture the OAuth redirect.

    Creates a minimal HTTP server on localhost that listens for the OAuth
    callback containing the authorization code. This is used for CLI/desktop
    applications that can't receive callbacks on a public URL.

    Parameters
    ----------
    port : int, optional
        Port to listen on. If 0 (default), a random available port is chosen
    path : str, optional
        URL path to listen on. Default is "/cb"

    Returns
    -------
    tuple[str, Awaitable[tuple[str, str]]]
        A tuple containing:
        - redirect_uri: The complete URL for the OAuth redirect
        - waiter: An awaitable that resolves to (code, state) when callback received

    Notes
    -----
    The server runs in a background thread and automatically shuts down after
    receiving the callback. The returned awaitable should be awaited to get
    the authorization code and state values.

    Example
    -------
    >>> redirect_uri, waiter = start_local_callback_server()
    >>> # ... initiate OAuth flow with redirect_uri ...
    >>> code, state = await waiter
    """
    loop = asyncio.get_event_loop()
    future: asyncio.Future[tuple[str, str]] = loop.create_future()

    class _Handler(BaseHTTPRequestHandler):  # noqa: D401, N801
        def do_GET(self):  # noqa: N802 (HTTP handler)
            parsed = urlparse(self.path)
            if parsed.path != path:
                self.send_error(404)
                return

            qs = parse_qs(parsed.query)
            loop.call_soon_threadsafe(
                future.set_result,
                (qs.get("code", [""])[0], qs.get("state", [""])[0]),
            )

            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"You may close this window.")

        def log_message(self, *_args, **_kwargs):  # silence default logging
            return

    server = HTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}{path}"

    async def _waiter() -> tuple[str, str]:
        code, state = await future
        server.shutdown()
        return code, state

    return redirect_uri, _waiter()


def exchange_code_for_token(
    domain: str,
    client_id: str,
    code: str,
    redirect_uri: str,
    client_secret: str | None = None,
) -> dict:  # Return full token response
    """Exchange an authorization code for tokens."""
    payload: dict[str, Any] = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": redirect_uri,
    }

    if _code_verifier:
        payload["code_verifier"] = _code_verifier
    elif client_secret is None:
        raise RuntimeError("PKCE verifier missing – call build_authorization_url() first")

    if client_secret:
        payload["client_secret"] = client_secret

    resp = httpx.post(f"https://{domain}/oauth/token", json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()  # Return full response with refresh_token


def exchange_code_for_token_backend(
    domain: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict:  # Return full token response
    """Exchange authorization code for tokens using client credentials."""
    return exchange_code_for_token(
        domain=domain,
        client_id=client_id,
        code=code,
        redirect_uri=redirect_uri,
        client_secret=client_secret,
    )


def refresh_access_token(
    refresh_token: str, client_id: str, client_secret: str, domain: str
) -> dict:
    """Refresh access token using refresh token."""
    payload = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    resp = httpx.post(f"https://{domain}/oauth/token", json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()  # Contains fresh access_token and possibly new refresh_token
