"""Quick-start helpers that remove the boiler-plate required in the
examples/sample_agent.py script.

The three public async helpers cover the parts that tend to repeat in every
prototype:

    1. ``login_interactive`` – obtain a user JWT (cached) **and** a ready
       ``BarndoorSDK`` instance in one go.
    2. ``ensure_server_connected`` – wrapper around
       :pymeth:`barndoor.sdk.client.BarndoorSDK.ensure_server_connected` with a
       sensible progress / timeout default.
    3. ``get_mcp_adapter`` – construct a ``crewai_tools.MCPServerAdapter`` (or
       any other framework-agnostic adapter) that already carries the correct
       proxy URL, streaming transport and *provider* access token in the
       ``Authorization`` header.

The helpers are intentionally dependency-free – they import optional packages
only when necessary.  They can therefore be used both inside the Barndoor SDK
repo and by downstream projects that vendor-copy the file.
"""

from __future__ import annotations

# Standard library
import asyncio
import os
import logging

from pathlib import Path
from typing import List, Tuple
from uuid import uuid4

# Import required auth helpers explicitly so type checkers can resolve them
from barndoor.sdk.auth import (
    build_authorization_url,
    exchange_code_for_token_backend,
    start_local_callback_server,
)

from .auth_store import (
    clear_cached_token,
    is_token_active,
    load_user_token,
    save_user_token,
)

# Automatically load .env if not done yet
from barndoor.sdk.config import get_static_config, load_dotenv_for_sdk

# Load default .env file exactly once – safe no-op if already loaded by caller
load_dotenv_for_sdk()

# Internal imports -----------------------------------------------------------
from .client import BarndoorSDK
from .utils import external_mcp_url
from .logging import get_logger

logger = get_logger("quickstart")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


a_sync = asyncio.run  # tiny alias for examples


async def login_interactive(
    *,
    auth_domain: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    audience: str | None = None,  
    api_base_url: str | None = None,
    port: int = 52765,
) -> BarndoorSDK:
    """Return an initialized BarndoorSDK after ensuring valid user JWT."""
    from .auth_store import is_token_active_with_refresh
    
    logger.info("Starting interactive login flow")
    
    cfg = get_static_config()

    auth_domain = auth_domain or cfg.auth_domain
    client_id = client_id or cfg.client_id
    client_secret = client_secret or cfg.client_secret
    audience = audience or cfg.api_audience  # Use config value

    if not client_id or not client_secret:
        raise RuntimeError(
            "AGENT_CLIENT_ID / AGENT_CLIENT_SECRET not set – create a .env file or export in the shell",
        )

    # 1. try cached token with refresh ----------------------------------
    token_data = None
    if await is_token_active_with_refresh(api_base_url or cfg.api_base_url):
        logger.info("Using cached/refreshed valid token")
        token_data = load_user_token()
    else:
        logger.info("No valid cached token, starting OAuth flow")
        # 2. if none – run interactive PKCE flow --------------------------
        redirect_uri, waiter = start_local_callback_server(port=port)
        auth_url = build_authorization_url(
            domain=auth_domain,
            client_id=client_id,
            redirect_uri=redirect_uri,
            audience=audience,
        )
        import webbrowser
        webbrowser.open(auth_url)
        logging.getLogger(__name__).info("Please complete login in your browser…")
        code, _state = await waiter
        token_data = exchange_code_for_token_backend(
            domain=auth_domain,
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            redirect_uri=redirect_uri,
        )
        save_user_token(token_data)

    # Extract access token for SDK
    access_token = token_data if isinstance(token_data, str) else token_data["access_token"]
    
    # 3. build dynamic configuration
    from barndoor.sdk.config import get_dynamic_config
    cfg_dyn = get_dynamic_config(access_token)
    api_base_url = api_base_url or cfg_dyn.api_base_url

    # 4. create SDK
    sdk = BarndoorSDK(api_base_url, barndoor_token=access_token, validate_token_on_init=False)
    logger.info("Login completed successfully")
    return sdk


async def ensure_server_connected(
    sdk: BarndoorSDK,
    server_identifier: str,
    *,
    timeout: int = 90,
) -> None:
    """Guarantee that *server_identifier* (slug or provider) is connected.

    If the server is already connected the coroutine is a no-op, otherwise it
    launches the browser OAuth flow and waits (up to *timeout* seconds) until
    the connection is live.
    """
    logger.info(f"Ensuring {server_identifier} server is connected")
    
    servers = await sdk.list_servers()
    server = next((s for s in servers if s.slug == server_identifier), None)
    
    if not server:
        logger.error(f"Server '{server_identifier}' not found")
        raise ValueError(f"Server '{server_identifier}' not found")
        
    if server.connection_status == "connected":
        logger.info(f"Server {server_identifier} already connected")
        return
        
    logger.info(f"Connecting to {server_identifier}...")
    await sdk.ensure_server_connected(server_identifier, poll_seconds=timeout)


async def make_mcp_connection_params(
    sdk: BarndoorSDK,
    server_slug: str,
    *,
    proxy_base_url: str = "http://proxy-ingress:8080",
    transport: str = "streamable-http",
):
    """Return ``(params_dict, public_url)`` where *params_dict* has the keys

    ``url``, ``headers`` and (optionally) ``transport`` so that it can be fed
    directly to whatever framework you’re using (CrewAI, LangChain, custom).

    The helper hides the rules:
      • If BARNDOOR_ENV is "prod" → build public MCP URL
        otherwise ("dev" or "local") → route through the local proxy.
      • Inject JWT + session-id headers
    """
    # 1. ensure server exists
    servers = await sdk.list_servers()
    if server_slug not in {s.slug for s in servers}:
        raise ValueError(f"Server '{server_slug}' not found for current user")

    # 2. decide proxy vs public based on env (default taken from MODE / BARNDOOR_ENV)
    env = (os.getenv("BARNDOOR_ENV") or os.getenv("MODE", "localdev")).lower()

    # Build dynamic configuration (slug already substituted)
    from barndoor.sdk.config import get_dynamic_config

    cfg_dyn = get_dynamic_config(str(sdk.token))

    if env in {"localdev", "local", "development", "dev"}:
        # Use org-aware MCP host from config
        url = f"{cfg_dyn.mcp_base_url}/mcp/{server_slug}"
    else:  # production (or any other value)
        url = external_mcp_url(
            server_slug=server_slug,
            jwt_token=str(sdk.token),
            env="prod",
        )

    params = {
        "url": url,
        "transport": transport,
        "headers": {
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {sdk.token}",
            "x-barndoor-session-id": str(uuid4()),
        },
    }

    return params, url
