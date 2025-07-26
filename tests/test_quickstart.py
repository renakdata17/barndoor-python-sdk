"""Tests for quickstart helper functions."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from barndoor.sdk.quickstart import (
    login_interactive,
    ensure_server_connected,
    make_mcp_connection_params,
)
from barndoor.sdk.exceptions import ServerNotFoundError


class TestLoginInteractive:
    """Test login_interactive helper."""

    @pytest.mark.asyncio
    async def test_login_with_cached_token(self, mock_token, temp_token_dir):
        """Test login with valid cached token."""
        # Save token to cache
        token_file = temp_token_dir / "token.json"
        token_file.write_text('{"access_token": "' + mock_token + '"}')
        
        with patch("barndoor.sdk.quickstart.is_token_active", return_value=True):
            sdk = await login_interactive()
            assert sdk.token == mock_token
            await sdk.aclose()

    @pytest.mark.asyncio
    async def test_login_interactive_flow(self, temp_token_dir):
        """Test interactive login flow."""
        mock_token = "new-token"
        
        with patch("barndoor.sdk.quickstart.is_token_active", return_value=False), \
             patch("barndoor.sdk.quickstart.start_local_callback_server") as mock_server, \
             patch("barndoor.sdk.quickstart.exchange_code_for_token_backend", return_value=mock_token), \
             patch("webbrowser.open") as mock_browser:
            
            # Mock callback server
            mock_waiter = AsyncMock(return_value=("auth_code", "state"))
            mock_server.return_value = ("http://localhost:52765/cb", mock_waiter)
            
            sdk = await login_interactive(
                auth_domain="test.auth0.com",
                client_id="test-client",
                client_secret="test-secret"
            )
            
            # Verify browser was opened
            mock_browser.assert_called_once()
            
            # Verify token was saved
            assert sdk.token == mock_token
            await sdk.aclose()

    @pytest.mark.asyncio
    async def test_login_missing_credentials(self):
        """Test login with missing credentials."""
        with pytest.raises(ValueError, match="client_id is required"):
            await login_interactive(client_id="", client_secret="secret")


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
        
        with pytest.raises(ServerNotFoundError, match="Server 'nonexistent' not found"):
            await ensure_server_connected(sdk_with_mocked_http, "nonexistent")

    @pytest.mark.asyncio
    async def test_server_needs_connection(self, sdk_with_mocked_http, mock_server_list):
        """Test with server that needs connection."""
        # Mock server list and connection flow
        sdk_with_mocked_http._http.request = AsyncMock(side_effect=[
            mock_server_list,  # list_servers call
            {"auth_url": "https://oauth.test.com"},  # initiate_connection call
            {"status": "connected"}  # get_connection_status call
        ])
        
        with patch("webbrowser.open") as mock_browser:
            await ensure_server_connected(sdk_with_mocked_http, "notion")
            mock_browser.assert_called_once()


class TestMakeMCPConnectionParams:
    """Test make_mcp_connection_params helper."""

    @pytest.mark.asyncio
    async def test_make_connection_params_dev(self, sdk_with_mocked_http, mock_server_list):
        """Test connection params in development mode."""
        sdk_with_mocked_http._http.request = AsyncMock(return_value=mock_server_list)
        
        with patch.dict("os.environ", {"MODE": "development"}):
            params, public_url = await make_mcp_connection_params(
                sdk_with_mocked_http, 
                "salesforce"
            )
        
        assert "url" in params
        assert "headers" in params
        assert "Authorization" in params["headers"]
        assert params["transport"] == "streamable-http"

    @pytest.mark.asyncio
    async def test_make_connection_params_prod(self, sdk_with_mocked_http, mock_server_list):
        """Test connection params in production mode."""
        sdk_with_mocked_http._http.request = AsyncMock(return_value=mock_server_list)
        
        with patch.dict("os.environ", {"MODE": "production"}):
            params, public_url = await make_mcp_connection_params(
                sdk_with_mocked_http,
                "salesforce"
            )
        
        assert "url" in params
        assert public_url is not None
        assert "mcp.barndoor.ai" in params["url"]

    @pytest.mark.asyncio
    async def test_make_connection_params_server_not_found(self, sdk_with_mocked_http):
        """Test connection params with non-existent server."""
        sdk_with_mocked_http._http.request = AsyncMock(return_value=[])
        
        with pytest.raises(ValueError, match="Server 'nonexistent' not found"):
            await make_mcp_connection_params(sdk_with_mocked_http, "nonexistent")