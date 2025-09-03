"""Thin async client for Barndoor REST API."""

from __future__ import annotations

from typing import List

import logging
import os

from ._http import HTTPClient, TimeoutConfig
from .exceptions import HTTPError, ConfigurationError
from .models import (
    ServerDetail,  # forward reference for type checking
    ServerSummary,
)
from .logging import get_logger
from .validation import (
    validate_url,
    validate_token,
    validate_server_id,
    validate_timeout,
    validate_optional_string,
)

logger = get_logger("client")


class BarndoorSDK:
    """Async client for interacting with the Barndoor Platform API.

    This SDK provides methods to:
    - Manage server connections and OAuth flows
    - List available MCP servers
    - Validate user tokens

    The client handles authentication automatically by including the user's
    JWT token in all requests.

    Parameters
    ----------
    api_base_url : str
        Base URL of the Barndoor API (e.g., "https://api.barndoor.host")
    barndoor_token : str, optional
        User JWT token. If not provided, will attempt to load from local cache
    validate_token_on_init : bool, optional
        Whether to validate the token when creating the client. Default is True

    Raises
    ------
    ValueError
        If no token is provided and none found in local cache
    """

    def __init__(
        self,
        api_base_url: str,
        barndoor_token: str | None = None,
        validate_token_on_init: bool = True,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        from .auth_store import load_user_token
        from ._http import HTTPClient, TimeoutConfig

        # Validate inputs
        self.base = validate_url(api_base_url, "API base URL").rstrip("/")
        
        token = barndoor_token or load_user_token()
        if not token:
            raise ValueError(
                "Barndoor user token not provided and none found in store. Run `barndoor-login`."
            )
        self.token = validate_token(token)
        
        timeout = validate_timeout(timeout, "Timeout")
        if not isinstance(max_retries, int) or max_retries < 0:
            raise ConfigurationError("max_retries must be a non-negative integer")

        timeout_config = TimeoutConfig(read=timeout, connect=timeout/3)
        self._http = HTTPClient(timeout_config=timeout_config, max_retries=max_retries)
        self._token_validated = False
        self._closed = False

        logger.info(f"Initialized BarndoorSDK for {self.base}")

    async def __aenter__(self) -> "BarndoorSDK":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit with cleanup."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the SDK and clean up resources."""
        if not self._closed:
            await self._http.close()
            self._closed = True

    def _ensure_not_closed(self) -> None:
        """Ensure the SDK hasn't been closed."""
        if self._closed:
            raise RuntimeError("SDK has been closed. Create a new instance or use as context manager.")

    async def _req(self, method: str, path: str, **kwargs) -> dict:
        """Make authenticated request with automatic token validation."""
        self._ensure_not_closed()
        await self.ensure_valid_token()
        
        headers = kwargs.setdefault("headers", {})
        headers["Authorization"] = f"Bearer {self.token}"
        
        url = f"{self.base}{path}"
        return await self._http.request(method, url, **kwargs)

    # ---------------- Token validation -----------------

    async def validate_cached_token(self) -> bool:
        """Validate the cached token by making a test API call.

        Checks if the current token is still valid by calling the
        /identity/token endpoint.

        Returns
        -------
        bool
            True if the token is valid, False otherwise

        Notes
        -----
        This method caches the validation result internally to avoid
        repeated API calls.
        """
        from .auth_store import validate_token

        if not self.token:
            return False

        result = await validate_token(self.token, self.base)
        self._token_validated = True
        return result["valid"]

    async def ensure_valid_token(self) -> None:
        """Ensure token is valid, validating if necessary."""
        if self._token_validated:
            return
            
        # Skip validation in non-production environments
        env = os.getenv("BARNDOOR_ENV", "localdev").lower()
        if env in ("localdev", "local", "development", "dev"):
            self._token_validated = True
            return
            
        # Validate token in production
        is_valid = await self.validate_cached_token()
        if not is_valid:
            raise ValueError("Token validation failed. Please re-authenticate.")
        
        self._token_validated = True

    # ---------------- Registry -----------------

    async def list_servers(self) -> List[ServerSummary]:
        """List all MCP servers available to the caller's organization.

        Uses cursor-less page-based pagination as provided by the registry API.
        Expects a response shape:
          {
            "data": [...],
            "page": number,
            "limit": number,
            "total": number,
            "pages": number,
            "previous_page": number | null,
            "next_page": number | null
          }
        """
        await self.ensure_valid_token()
        logger.debug("Fetching server list")
        try:
            servers: List[ServerSummary] = []

            page = 1
            try:
                limit = int(os.getenv("BARNDOOR_PAGE_SIZE", "100"))
            except Exception:
                limit = 100
            max_pages = 100  # guard against infinite loops

            pages_visited = 0
            while True:
                params = {"page": page, "limit": limit}
                resp = await self._req("GET", "/servers", params=params)

                # Strictly require the new paginated shape
                server_data = resp["data"]
                servers.extend(ServerSummary.model_validate(o) for o in server_data)

                pages_visited += 1
                next_page = resp.get("next_page")

                if not next_page:
                    break
                if pages_visited >= max_pages:
                    logger.warning("Reached max pagination depth (%s), stopping.", max_pages)
                    break

                page = int(next_page)

            logger.info(f"Retrieved {len(servers)} servers")
            return servers
        except Exception as e:
            logger.error(f"Failed to list servers: {e}")
            raise

    # ----------- user onboarding helpers -------------

    async def initiate_connection(
        self, 
        server_id: str, 
        return_url: str | None = None
    ) -> dict[str, str]:
        """Initiate OAuth connection flow for a server."""
        server_id = validate_server_id(server_id)
        return_url = validate_optional_string(return_url, "Return URL", max_length=2048)
        
        if return_url:
            return_url = validate_url(return_url, "Return URL")

        logger.info(f"Initiating connection for server {server_id}")
        
        params = {"return_url": return_url} if return_url else None
        try:
            response = await self._req(
                "POST",
                f"/servers/{server_id}/connect",
                params=params,
                json={},
            )
            return response
        except HTTPError as exc:
            if (
                exc.status_code == 500
                and "OAuth server configuration not found" in str(exc)
            ):
                raise RuntimeError(
                    "Server is missing OAuth configuration. "
                    "Ask an admin to configure credentials before initiating a connection."
                ) from exc
            raise

    async def get_connection_status(self, server_id: str) -> str:
        """Get the user's connection status for a specific server."""
        server_id = validate_server_id(server_id)
        
        logger.debug(f"Checking connection status for server {server_id}")
        response = await self._req("GET", f"/servers/{server_id}/connection")
        return response["status"]

    async def get_server(self, server_id: str) -> "ServerDetail":
        """Get detailed information about a specific server."""
        server_id = validate_server_id(server_id)
        
        logger.debug(f"Fetching server details for {server_id}")
        response = await self._req("GET", f"/servers/{server_id}")
        
        from .models import ServerDetail
        return ServerDetail.model_validate(response)

    # ---------------- internal -----------------

    async def aclose(self) -> None:
        """Close the underlying HTTP client.

        Should be called when done with the SDK to properly clean up
        connections. Can also be used as an async context manager to
        handle this automatically.
        """
        await self._http.aclose()

    # ---------- Convenience helpers -----------------

    @classmethod
    async def login_interactive(
        cls,
        auth_domain: str,
        client_id: str,
        client_secret: str,
        audience: str,
        *,
        api_base_url: str = "https://{organization_id}.mcp.barndoor.ai",
        port: int = 52765,
    ) -> "BarndoorSDK":
        """Perform interactive login and return an initialized SDK instance.

        Opens the system browser for OAuth authentication, waits for the
        user to complete login, exchanges the authorization code for a JWT,
        and returns a configured BarndoorSDK instance ready for use.

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
            Base URL of the Barndoor API. Default is "https://{organization_id}.mcp.barndoor.ai"
        port : int, optional
            Local port for OAuth callback. Default is 8765

        Returns
        -------
        BarndoorSDK
            Initialized SDK instance with valid authentication

        Raises
        ------
        RuntimeError
            If authentication fails

        Notes
        -----
        This method handles the complete OAuth flow including:
        1. Starting a local callback server
        2. Opening the browser to the authorization URL
        3. Waiting for the callback with the authorization code
        4. Exchanging the code for a JWT token
        5. Creating the SDK instance
        """
        import webbrowser

        from . import auth as bda_auth

        redirect_uri, waiter = bda_auth.start_local_callback_server(port=port)

        auth_url = bda_auth.build_authorization_url(
            domain=auth_domain,
            client_id=client_id,
            redirect_uri=redirect_uri,
            audience=audience,
        )

        webbrowser.open(auth_url)
        print("Please complete login in your browser…")

        code, _state = await waiter

        # Hybrid flow – exchange code with client secret (no PKCE).
        token = bda_auth.exchange_code_for_token_backend(
            domain=auth_domain,
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            redirect_uri=redirect_uri,
        )

        return cls(api_base_url, barndoor_token=token)

    async def ensure_server_connected(
        self,
        server_identifier: str,
        *,
        poll_seconds: int = 60,
    ) -> None:
        """Ensure a server is connected, initiating OAuth if needed.

        Checks if the specified server is already connected. If not,
        initiates the OAuth flow, opens the browser, and polls until
        the connection is established.

        Parameters
        ----------
        server_identifier : str
            Server slug or provider name to connect
        poll_seconds : int, optional
            Maximum seconds to wait for connection. Default is 60

        Raises
        ------
        ValueError
            If the server is not found
        asyncio.TimeoutError
            If connection is not established within poll_seconds
        RuntimeError
            If the OAuth flow fails

        Notes
        -----
        This is a convenience method that combines multiple steps:
        1. Finding the server by slug or provider
        2. Checking current connection status
        3. Initiating OAuth if needed
        4. Opening the browser
        5. Polling until connected
        """

        import asyncio
        import webbrowser

        # 1. locate server
        servers = await self.list_servers()
        target = next(
            (
                s
                for s in servers
                if s.slug == server_identifier
                or (s.provider or "").lower() == server_identifier.lower()
            ),
            None,
        )

        if not target:
            raise ValueError(f"Server '{server_identifier}' not found")

        if target.connection_status == "connected":
            return  # already done

        # 2. start OAuth flow
        conn = await self.initiate_connection(target.id)
        auth_url = conn.get("auth_url")
        if not auth_url:
            raise RuntimeError("Registry did not return auth_url")

        webbrowser.open(auth_url)

        # 3. poll until connected or timeout
        for _ in range(poll_seconds):
            status = await self.get_connection_status(target.id)
            if status == "connected":
                return
            await asyncio.sleep(1)

        raise RuntimeError("OAuth connection was not completed in time")
