"""Pytest configuration and fixtures."""

from unittest.mock import AsyncMock

import pytest

from barndoor.sdk.client import BarndoorSDK


@pytest.fixture
def mock_token():
    """Valid JWT token for testing."""
    return (
        "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0"
        "ZXN0LXVzZXIiLCJvcmciOiJ0ZXN0LW9yZyIsImV4cCI6OTk5OTk5OTk5OX0.test"
    )


@pytest.fixture
def mock_config():
    """Mock configuration."""
    return {
        "AUTH_DOMAIN": "auth.test.barndoor.ai",
        "AGENT_CLIENT_ID": "test-client-id",
        "AGENT_CLIENT_SECRET": "test-client-secret",
        "BARNDOOR_API": "https://test-org.mcp.barndoor.ai",
    }


@pytest.fixture
def sdk_client(mock_token):
    """SDK client with mocked dependencies."""
    return BarndoorSDK(
        api_base_url="https://test.barndoor.ai",
        barndoor_token=mock_token,
        validate_token_on_init=False,
    )


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client."""
    mock = AsyncMock()
    mock.request = AsyncMock()
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def sdk_with_mocked_http(mock_token):
    """SDK client ready for tests that patch the internal HTTP request."""
    return BarndoorSDK(
        api_base_url="https://api.test.com",
        barndoor_token=mock_token,
        validate_token_on_init=False,
    )


@pytest.fixture
def temp_token_dir(monkeypatch, tmp_path):
    """Temporary token storage path made available to auth_store."""
    token_file = tmp_path / "token.json"
    # Patch TOKEN_FILE used by auth_store to point into tmp path
    monkeypatch.setenv("BARNDOOR_TOKEN_FILE", str(token_file))
    # Some auth_store implementations read a module-level TOKEN_FILE;
    # if needed we could patch it here
    return tmp_path


@pytest.fixture
def mock_server_list():
    """Sample server list payload as returned by the API for list_servers."""
    return [
        {
            "id": "srv-salesforce",
            "name": "Salesforce",
            "slug": "salesforce",
            "provider": "salesforce",
            "connection_status": "connected",
            "proxy_url": "https://acme.mcp.barndoor.ai/mcp/salesforce",
        },
        {
            "id": "srv-notion",
            "name": "Notion",
            "slug": "notion",
            "provider": "notion",
            "connection_status": "available",
            "proxy_url": "https://acme.mcp.barndoor.ai/mcp/notion",
        },
    ]
