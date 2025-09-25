"""Tests for HTTP client with timeout and retry logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from barndoor.sdk._http import HTTPClient, TimeoutConfig
from barndoor.sdk.exceptions import ConnectionError, HTTPError, TimeoutError


class TestTimeoutConfig:
    """Test timeout configuration."""

    def test_default_config(self):
        """Test default timeout configuration."""
        config = TimeoutConfig()
        assert config.connect == 10.0
        assert config.read == 30.0
        assert config.write == 10.0
        assert config.pool == 10.0

    def test_custom_config(self):
        """Test custom timeout configuration."""
        config = TimeoutConfig(connect=5.0, read=60.0, write=15.0, pool=20.0)
        assert config.connect == 5.0
        assert config.read == 60.0
        assert config.write == 15.0
        assert config.pool == 20.0

    def test_to_httpx_timeout(self):
        """Test conversion to httpx.Timeout."""
        config = TimeoutConfig(connect=5.0, read=30.0)
        httpx_timeout = config.to_httpx_timeout()

        assert isinstance(httpx_timeout, httpx.Timeout)
        assert httpx_timeout.connect == 5.0
        assert httpx_timeout.read == 30.0


class TestHTTPClient:
    """Test HTTP client."""

    @pytest.mark.asyncio
    async def test_successful_request(self):
        """Test successful HTTP request."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success"}
        mock_response.raise_for_status.return_value = None

        with patch("barndoor.sdk._http.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = HTTPClient()
            result = await client.request("GET", "https://api.test.com/endpoint")

            assert result == {"status": "success"}
            mock_client.request.assert_called_once_with("GET", "https://api.test.com/endpoint")

    @pytest.mark.asyncio
    async def test_http_error_handling(self):
        """Test HTTP error handling."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        http_error = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response)

        with patch("barndoor.sdk._http.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request.side_effect = http_error
            mock_client_class.return_value = mock_client

            client = HTTPClient()

            with pytest.raises(HTTPError) as exc_info:
                await client.request("GET", "https://api.test.com/endpoint")

            assert exc_info.value.status_code == 404
            assert "Resource not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_error_handling(self):
        """Test timeout error handling."""
        with patch("barndoor.sdk._http.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.TimeoutException("Request timeout")
            mock_client_class.return_value = mock_client

            client = HTTPClient()

            with pytest.raises(TimeoutError) as exc_info:
                await client.request("GET", "https://api.test.com/endpoint")

            assert "GET https://api.test.com/endpoint" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """Test connection error handling."""
        with patch("barndoor.sdk._http.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.ConnectError("Connection failed")
            mock_client_class.return_value = mock_client

            client = HTTPClient()

            with pytest.raises(ConnectionError) as exc_info:
                await client.request("GET", "https://api.test.com/endpoint")

            assert "https://api.test.com/endpoint" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_retry_logic_success_after_failure(self):
        """Test retry logic succeeds after initial failure."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success"}
        mock_response.raise_for_status.return_value = None

        with patch("barndoor.sdk._http.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            # First call fails, second succeeds
            mock_client.request.side_effect = [
                httpx.ConnectError("Connection failed"),
                mock_response,
            ]
            mock_client_class.return_value = mock_client

            client = HTTPClient(max_retries=2)

            with patch("asyncio.sleep") as mock_sleep:  # Speed up test
                result = await client.request("GET", "https://api.test.com/endpoint")

            assert result == {"status": "success"}
            assert mock_client.request.call_count == 2
            mock_sleep.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self):
        """Test retry logic exhaustion."""
        with patch("barndoor.sdk._http.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.ConnectError("Connection failed")
            mock_client_class.return_value = mock_client

            client = HTTPClient(max_retries=2)

            with patch("asyncio.sleep"):  # Speed up test
                with pytest.raises(ConnectionError):
                    await client.request("GET", "https://api.test.com/endpoint")

            # Should try initial + 2 retries = 3 total
            assert mock_client.request.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_for_client_errors(self):
        """Test that client errors (4xx) are not retried."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        http_error = httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=mock_response
        )

        with patch("barndoor.sdk._http.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request.side_effect = http_error
            mock_client_class.return_value = mock_client

            client = HTTPClient(max_retries=2)

            with pytest.raises(HTTPError):
                await client.request("GET", "https://api.test.com/endpoint")

            # Should only try once (no retries for 4xx)
            assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_client_cleanup(self):
        """Test HTTP client cleanup."""
        with patch("barndoor.sdk._http.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            client = HTTPClient()

            # Force client creation
            await client._get_client()

            # Close client
            await client.close()

            mock_client.aclose.assert_called_once()
            assert client._closed

    @pytest.mark.asyncio
    async def test_use_after_close(self):
        """Test using client after close raises error."""
        client = HTTPClient()
        await client.close()

        with pytest.raises(RuntimeError, match="HTTP client has been closed"):
            await client.request("GET", "https://api.test.com/endpoint")

    @pytest.mark.asyncio
    async def test_server_error_handling(self):
        """Test 5xx server error is wrapped into HTTPError with friendly message."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        http_error = httpx.HTTPStatusError(
            "Internal Server Error", request=MagicMock(), response=mock_response
        )

        with patch("barndoor.sdk._http.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request.side_effect = http_error
            mock_client_class.return_value = mock_client

            client = HTTPClient()

            with pytest.raises(HTTPError) as exc_info:
                await client.request("GET", "https://api.test.com/endpoint")

            assert exc_info.value.status_code == 500
            assert "Server error" in str(exc_info.value)
