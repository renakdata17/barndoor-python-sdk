"""Tests for quickstart helper functions."""

from unittest.mock import AsyncMock, patch

import pytest

from barndoor.sdk.models import ServerSummary
from barndoor.sdk.quickstart import (
    ensure_server_connected,
    login_interactive,
    make_mcp_connection_params,
)


class TestLoginInteractive:
    """Test login_interactive helper."""

    @pytest.mark.asyncio
    async def test_login_with_cached_token(self, mock_token, temp_token_dir):
        """Test login with valid cached token."""
        # Save token to cache
        token_file = temp_token_dir / "token.json"
        token_file.write_text('{"access_token": "' + mock_token + '"}')

        with (
            patch(
                "barndoor.sdk.auth_store.is_token_active_with_refresh",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "barndoor.sdk.quickstart.load_user_token", return_value={"access_token": mock_token}
            ),
        ):
            sdk = await login_interactive()
            assert sdk.token == mock_token
            await sdk.aclose()

    @pytest.mark.asyncio
    async def test_login_interactive_flow(self, temp_token_dir):
        """Test interactive login flow."""
        with (
            patch(
                "barndoor.sdk.auth_store.is_token_active_with_refresh",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch("barndoor.sdk.quickstart.start_local_callback_server") as mock_server,
            patch(
                "barndoor.sdk.quickstart.exchange_code_for_token_backend",
                return_value="aaa.bbb.ccc",
            ),
            patch("webbrowser.open") as mock_browser,
        ):
            # Mock callback server
            async def waiter():
                return ("auth_code", "state")

            mock_server.return_value = ("http://localhost:52765/cb", waiter())

            with (
                patch("barndoor.sdk.quickstart.save_user_token") as mock_save,
                patch(
                    "barndoor.sdk.quickstart.build_authorization_url",
                    return_value="https://auth.example/authorize",
                ),
            ):
                sdk = await login_interactive(
                    auth_domain="test.auth0.com",
                    client_id="test-client",
                    client_secret="test-secret",
                )

                # Verify browser was opened
                mock_browser.assert_called_once()

                # Verify token was saved
                mock_save.assert_called_once()
                assert isinstance(sdk.token, str) and sdk.token.count(".") == 2
                await sdk.aclose()

    @pytest.mark.asyncio
    async def test_login_missing_credentials(self):
        """Test login with missing credentials."""
        with patch("barndoor.sdk.quickstart.get_static_config") as mock_cfg:
            # Make config empty so the function relies on provided args
            mock_cfg.return_value = type(
                "C",
                (),
                {"client_id": "", "client_secret": "", "auth_domain": "", "api_audience": ""},
            )()
            with pytest.raises(RuntimeError, match="AGENT_CLIENT_ID / AGENT_CLIENT_SECRET not set"):
                await login_interactive(client_id="", client_secret="")


class TestEnsureServerConnected:
    """Test ensure_server_connected helper."""

    @pytest.mark.asyncio
    async def test_server_already_connected(self, sdk_with_mocked_http, mock_server_list):
        """Test with server already connected."""
        sdk_with_mocked_http._http.request = AsyncMock(return_value=mock_server_list)

        # Should complete without error
        await ensure_server_connected(sdk_with_mocked_http, "salesforce")

    @pytest.mark.asyncio
    async def test_server_not_found(self, sdk_with_mocked_http, mock_server_list):
        """Test with non-existent server."""
        sdk_with_mocked_http._http.request = AsyncMock(return_value=mock_server_list)

        with pytest.raises(ValueError, match="Server 'nonexistent' not found"):
            await ensure_server_connected(sdk_with_mocked_http, "nonexistent")

    @pytest.mark.asyncio
    async def test_server_needs_connection(self, sdk_with_mocked_http, mock_server_list):
        """Test with server that needs connection."""
        # Build server objects directly to avoid ambiguity in HTTP mocking
        servers = [ServerSummary.model_validate(s) for s in mock_server_list]

        # Patch list_servers to return our objects; then mock only the subsequent HTTP calls
        sdk_with_mocked_http.list_servers = AsyncMock(return_value=servers)
        sdk_with_mocked_http._http.request = AsyncMock(
            side_effect=[
                {"auth_url": "https://oauth.test.com"},  # initiate_connection call
                {"status": "connected"},  # get_connection_status call
            ]
        )

        with patch("webbrowser.open") as mock_browser:
            await ensure_server_connected(sdk_with_mocked_http, "notion")
            mock_browser.assert_called_once()
            # Ensure the mocked request was fully consumed (2 calls: initiate + status)
            assert sdk_with_mocked_http._http.request.call_count == 2


class TestMakeMCPConnectionParams:
    """Test make_mcp_connection_params helper."""

    @pytest.mark.asyncio
    async def test_make_connection_params_uses_proxy_url(self, sdk_with_mocked_http):
        """make_mcp_connection_params should use proxy_url provided by registry."""
        mock_server_list = [
            {
                "id": "server-1",
                "name": "Salesforce",
                "slug": "salesforce",
                "provider": "salesforce",
                "connection_status": "connected",
                "proxy_url": "https://acme.mcp.barndoor.ai/mcp/salesforce",
            }
        ]

        sdk_with_mocked_http._http.request = AsyncMock(return_value=mock_server_list)

        params, public_url = await make_mcp_connection_params(sdk_with_mocked_http, "salesforce")

        assert params["url"] == "https://acme.mcp.barndoor.ai/mcp/salesforce"
        assert public_url == params["url"]
        assert "Authorization" in params["headers"]
        assert params["transport"] == "streamable-http"

    @pytest.mark.asyncio
    async def test_make_connection_params_server_not_found(self, sdk_with_mocked_http):
        """Test connection params with non-existent server."""
        sdk_with_mocked_http._http.request = AsyncMock(return_value=[])

        with pytest.raises(ValueError, match="Server 'nonexistent' not found"):
            await make_mcp_connection_params(sdk_with_mocked_http, "nonexistent")
