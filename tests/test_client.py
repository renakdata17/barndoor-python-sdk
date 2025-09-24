"""Test the main SDK client."""

from unittest.mock import AsyncMock, patch

import pytest

from barndoor.sdk.exceptions import HTTPError
from barndoor.sdk.models import ServerSummary


class TestBarndoorSDK:
    """Test the main SDK client class."""

    @pytest.mark.asyncio
    async def test_list_servers_success(self, sdk_client):
        """Test successful server listing."""
        mock_response = [
            {
                "id": "server-1",
                "name": "Test Server",
                "slug": "test-server",
                "provider": "test",
                "connection_status": "connected",
            }
        ]

        with patch.object(sdk_client, '_req', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_response

            servers = await sdk_client.list_servers()

            assert len(servers) == 1
            assert isinstance(servers[0], ServerSummary)
            assert servers[0].slug == "test-server"
            mock_req.assert_called_once_with("GET", "/servers")

    @pytest.mark.asyncio
    async def test_list_servers_http_error(self, sdk_client):
        """Test server listing with HTTP error."""
        with patch.object(sdk_client, "_req", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = HTTPError(500, "Internal Server Error")

            with pytest.raises(HTTPError) as exc_info:
                await sdk_client.list_servers()

            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_token_validation_skip_non_prod(self, sdk_client):
        """Test token validation is skipped in non-prod environments."""
        with patch.dict("os.environ", {"BARNDOOR_ENV": "development"}):
            await sdk_client.ensure_valid_token()
            assert sdk_client._token_validated is True

    @pytest.mark.asyncio
    async def test_token_validation_prod_success(self, sdk_client):
        """Test successful token validation in production."""
        with patch.dict("os.environ", {"BARNDOOR_ENV": "prod"}):
            with patch.object(
                sdk_client, "validate_cached_token", new_callable=AsyncMock
            ) as mock_validate:
                mock_validate.return_value = True

                await sdk_client.ensure_valid_token()

                assert sdk_client._token_validated is True
                mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_token_validation_prod_failure(self, sdk_client):
        """Test failed token validation in production."""
        with patch.dict("os.environ", {"BARNDOOR_ENV": "prod"}):
            with patch.object(
                sdk_client, "validate_cached_token", new_callable=AsyncMock
            ) as mock_validate:
                mock_validate.return_value = False

                with pytest.raises(ValueError, match="Token validation failed"):
                    await sdk_client.ensure_valid_token()

    @pytest.mark.asyncio
    async def test_use_after_close_raises(self, sdk_client):
        """Using the SDK after aclose() should raise a clear error."""
        await sdk_client.aclose()
        with pytest.raises(RuntimeError, match="SDK has been closed"):
            await sdk_client.list_servers()
