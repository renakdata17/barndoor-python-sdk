"""Tests for proxy_url-first behavior in make_mcp_connection_params."""

from unittest.mock import AsyncMock

import pytest

from barndoor.sdk.quickstart import make_mcp_connection_params


@pytest.mark.asyncio
async def test_make_connection_params_uses_proxy_url_from_list(sdk_with_mocked_http):
    """When proxy_url is provided in list_servers, it should be used directly."""
    mock_server_list = [
        {
            "id": "srv-1",
            "name": "Salesforce",
            "slug": "salesforce",
            "provider": "salesforce",
            "connection_status": "connected",
            "proxy_url": "https://acme.mcp.barndoor.ai/mcp/salesforce",
        }
    ]

    # list_servers
    sdk_with_mocked_http._http.request = AsyncMock(return_value=mock_server_list)

    params, public_url = await make_mcp_connection_params(sdk_with_mocked_http, "salesforce")

    assert params["url"] == "https://acme.mcp.barndoor.ai/mcp/salesforce"
    assert public_url == params["url"]
    assert "Authorization" in params["headers"]


@pytest.mark.asyncio
async def test_make_connection_params_uses_proxy_url_from_details(sdk_with_mocked_http):
    """If list response lacks proxy_url, fetch details and use proxy_url there."""
    mock_server_list = [
        {
            "id": "srv-2",
            "name": "Notion",
            "slug": "notion",
            "provider": "notion",
            "connection_status": "connected",
        }
    ]

    mock_server_detail = {
        "id": "srv-2",
        "name": "Notion",
        "slug": "notion",
        "provider": "notion",
        "connection_status": "connected",
        "proxy_url": "https://acme.mcp.barndoor.ai/mcp/notion",
        "url": "https://directory.example/notion",
    }

    # list_servers then get_server
    sdk_with_mocked_http._http.request = AsyncMock(
        side_effect=[mock_server_list, mock_server_detail]
    )

    params, public_url = await make_mcp_connection_params(sdk_with_mocked_http, "notion")

    assert params["url"] == "https://acme.mcp.barndoor.ai/mcp/notion"
    assert public_url == params["url"]
    assert "Authorization" in params["headers"]


@pytest.mark.asyncio
async def test_make_connection_params_no_proxy_url_raises(sdk_with_mocked_http):
    """If neither list nor details contain proxy_url, error clearly."""
    mock_server_list = [
        {
            "id": "srv-3",
            "name": "Custom",
            "slug": "custom",
            "provider": "custom",
            "connection_status": "connected",
        }
    ]

    mock_server_detail = {
        "id": "srv-3",
        "name": "Custom",
        "slug": "custom",
        "provider": "custom",
        "connection_status": "connected",
        # proxy_url intentionally missing
    }

    sdk_with_mocked_http._http.request = AsyncMock(
        side_effect=[mock_server_list, mock_server_detail]
    )

    with pytest.raises(RuntimeError, match="Registry did not provide a proxy_url"):
        await make_mcp_connection_params(sdk_with_mocked_http, "custom")
