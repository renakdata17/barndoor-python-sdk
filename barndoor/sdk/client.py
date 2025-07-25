"""Thin async client for Barndoor REST API."""

from __future__ import annotations

from typing import Any, List

import httpx

from ._http import HTTPClient
from .exceptions import ConnectionError, HTTPError
from .models import (
    ServerDetail,  # forward reference for type checking
    ServerSummary,
)


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
    ):
        from .auth_store import load_user_token

        self.base = api_base_url.rstrip("/")
        self.token = barndoor_token or load_user_token()
        if not self.token:
            raise ValueError(
                "Barndoor user token not provided and none found in store. Run `barndoor-login`. "
            )
        self._http = HTTPClient()
        self._token_validated = False

        # Optionally validate token on initialization
        if validate_token_on_init:
            # Note: This is async but we can't await in __init__
            # The validation will happen on first API call if needed
            pass

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
        """Ensure the token is valid, validating if necessary.

        This method is called before each API request to ensure
        the token hasn't been revoked or expired.
        """
        import os
        if os.getenv("BARNDOOR_ENV", "prod").lower() == "local":
            # will be handled by generic non-prod branch below
            pass

        # Skip validation for all non-production environments where the
        # /identity/token endpoint might be unreachable (dev, local, staging…)
        if os.getenv("BARNDOOR_ENV", "prod").lower() != "prod":
            self._token_validated = True
            return
            
        if not self._token_validated:
            is_valid = await self.validate_cached_token()
            if not is_valid:
                raise ValueError("Token validation failed")
            self._token_validated = True

    # ---------------- Registry -----------------

    async def list_servers(self) -> List[ServerSummary]:
        """List all MCP servers available to the caller's organization.

        Retrieves a list of servers that the authenticated user has
        access to, including their connection status.

        Returns
        -------
        List[ServerSummary]
            List of server summaries containing id, name, slug, provider,
            and connection_status for each server

        Raises
        ------
        HTTPError
            If the API request fails
        ConnectionError
            If unable to connect to the API
        """
        await self.ensure_valid_token()
        resp = await self._req("GET", f"{self.base}/servers")
        return [ServerSummary.model_validate(o) for o in resp.json()]

    # ----------- user onboarding helpers -------------

    async def initiate_connection(
        self, server_id: str, return_url: str | None = None
    ) -> dict[str, str]:
        """Initiate OAuth connection flow for a server.

        Starts the OAuth authorization process for connecting to a
        third-party server. Returns the authorization URL that the
        user should visit to complete the connection.

        Parameters
        ----------
        server_id : str
            UUID of the server to connect to
        return_url : str, optional
            URL to redirect to after OAuth completion. If not provided,
            uses the default configured for the application

        Returns
        -------
        dict[str, str]
            Dictionary containing:
            - connection_id: UUID of the connection request
            - auth_url: Authorization URL for the user to visit
            - state: OAuth state parameter for security

        Raises
        ------
        RuntimeError
            If the server is missing OAuth configuration
        HTTPError
            If the API request fails
        """
        await self.ensure_valid_token()
        params = {"return_url": return_url} if return_url else None
        try:
            resp = await self._req(
                "POST",
                f"{self.base}/servers/{server_id}/connect",
                params=params,
                json={},
            )
            return resp.json()
        except HTTPError as exc:
            # Provide a clearer error when the Registry does not have OAuth
            # configuration for this server yet.
            if (
                exc.status_code == 500
                and "OAuth server configuration not found" in exc.body
            ):
                raise RuntimeError(
                    "Server is missing OAuth configuration (client_id / client_secret). "
                    "Ask an admin to configure credentials before initiating a connection."
                ) from exc
            raise

    async def get_connection_status(self, server_id: str) -> str:
        """Get the user's connection status for a specific server.

        Parameters
        ----------
        server_id : str
            UUID of the server to check

        Returns
        -------
        str
            Connection status: "available", "pending", or "connected"

        Raises
        ------
        HTTPError
            If the API request fails or server not found
        """
        await self.ensure_valid_token()
        resp = await self._req("GET", f"{self.base}/servers/{server_id}/connection")
        return resp.json()["status"]

    async def get_server(self, server_id: str) -> "ServerDetail":
        """Get detailed information about a specific server.

        Parameters
        ----------
        server_id : str
            UUID of the server

        Returns
        -------
        ServerDetail
            Detailed server information including OAuth configuration

        Raises
        ------
        HTTPError
            If the API request fails or server not found
        """
        await self.ensure_valid_token()
        resp = await self._req("GET", f"{self.base}/servers/{server_id}")
        from .models import ServerDetail  # local import to avoid circular

        return ServerDetail.model_validate(resp.json())

    # ---------------- internal -----------------

    async def _req(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Make an authenticated HTTP request.

        Internal method that adds authentication headers and handles
        common error cases.

        Parameters
        ----------
        method : str
            HTTP method (GET, POST, etc.)
        url : str
            Full URL to request
        **kwargs
            Additional arguments passed to httpx.request()

        Returns
        -------
        httpx.Response
            The HTTP response

        Raises
        ------
        HTTPError
            For HTTP error status codes
        ConnectionError
            For connection failures
        RuntimeError
            For other request failures
        """
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token}"
        # No agent-specific header
        try:
            return await self._http.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPStatusError as exc:  # pragma: no cover
            raise HTTPError(exc.response.status_code, exc.response.text) from exc
        except ConnectionError as exc:
            # Re-raise ConnectionError with additional context
            raise ConnectionError(url=url, original_error=exc) from exc
        except RuntimeError as exc:
            # Re-raise RuntimeError from HTTPClient with additional context
            raise RuntimeError(f"API request failed ({method} {url}): {exc}") from exc

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
        api_base_url: str = "https://api.barndoor.ai",
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
            Base URL of the Barndoor API. Default is "https://api.barndoor.ai"
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
