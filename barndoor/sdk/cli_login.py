"""Command-line login utility for the Barndoor SDK.

This module provides a CLI tool for authenticating with the Barndoor
platform and saving credentials for use by SDK applications.
"""

import argparse
import asyncio
import os
import sys
import webbrowser
import logging

# Centralized static configuration
from barndoor.sdk.config import get_static_config

from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

from .auth import (
    build_authorization_url,
    exchange_code_for_token_backend,
    start_local_callback_server,
)
from .auth_store import clear_cached_token, is_token_active, save_user_token


# ---------------------------------------------------------------------------
# Helpers built on top of the *new* SDK primitives
# ---------------------------------------------------------------------------


async def interactive_login(
    auth_domain: str,
    client_id: str,
    client_secret: str,
    audience: str,
    api_base_url: str = "http://localhost:8003",
    port: int = 52765,
) -> str:
    """Perform interactive OAuth login flow.

    Opens the system browser for authentication and waits for the user
    to complete the login process.

    Parameters
    ----------
    auth_domain : str
        Auth0 domain (e.g., "barndoor.us.auth0.com")
    client_id : str
        OAuth client ID
    client_secret : str
        OAuth client secret
    audience : str
        API audience identifier
    api_base_url : str, optional
        Base URL of the Barndoor API. Default is "http://localhost:8003"
    port : int, optional
        Local port for OAuth callback. Default is 8765

    Returns
    -------
    str
        The authenticated user's JWT token

    Raises
    ------
    RuntimeError
        If the authentication flow fails
    """
    import webbrowser

    redirect_uri, waiter = start_local_callback_server(port=port)

    auth_url = build_authorization_url(
        domain=auth_domain,
        client_id=client_id,
        redirect_uri=redirect_uri,
        audience=audience,
    )

    print(f"\nOpening browser for authentication...")
    print(f"If the browser doesn't open automatically, visit:")
    print(f"{auth_url}\n")

    webbrowser.open(auth_url)

    try:
        code, _state = await waiter
    except Exception as e:
        raise RuntimeError(f"Failed to receive callback: {e}")

    # Exchange code for token
    token = exchange_code_for_token_backend(
        domain=auth_domain,
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=redirect_uri,
    )

    return token


async def main():
    """Main entry point for the barndoor-login CLI command.

    Handles the complete login flow:
    1. Checks for existing valid token
    2. Reads configuration from environment
    3. Performs interactive login if needed
    4. Saves token for future use

    Environment Variables
    ---------------------
    AUTH_DOMAIN : str
        Auth domain (production default "auth.barndoor.ai"; override for dev/local if needed)
    AGENT_CLIENT_ID : str
        OAuth client ID (required)
    AGENT_CLIENT_SECRET : str
        OAuth client secret (required)
    BARNDOOR_API : str
        API base URL (defaults to "http://localhost:8003")

    Exit Codes
    ----------
    0 : Success
    1 : Configuration error or login failure
    """
    # Load .env from current working directory if present.  This is kept for
    # backwards-compatibility – the real heavy lifting now happens inside
    # barndoor.sdk.config which already ran at import-time.
    load_dotenv(Path.cwd() / ".env")

    # Check for existing valid token
    cfg = get_static_config()

    api_base_url = cfg.BARNDOOR_API

    if await is_token_active(api_base_url):
        logging.getLogger(__name__).info("✓ Valid token already exists in ~/.barndoor/token.json")
        return

    # Get configuration from environment
    auth_domain = cfg.AUTH_DOMAIN
    client_id = cfg.AGENT_CLIENT_ID
    client_secret = cfg.AGENT_CLIENT_SECRET
    audience = "https://barndoor.api/"

    if not client_id or not client_secret:
        logging.error(
            "AGENT_CLIENT_ID and AGENT_CLIENT_SECRET must be set – create a .env file with those keys.")
        sys.exit(1)

    # Clear any existing invalid token
    clear_cached_token()

    try:
        # Perform interactive login
        token = await interactive_login(
            auth_domain=auth_domain,
            client_id=client_id,
            client_secret=client_secret,
            audience=audience,
            api_base_url=api_base_url,
        )

        # Save the token
        save_user_token(token)
        logging.getLogger(__name__).info("Login successful – token saved to ~/.barndoor/token.json")

    except Exception as e:
        logging.error("Login failed: %s", e)
        sys.exit(1)


def cli_main():
    """Entry point for the barndoor-login command."""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
