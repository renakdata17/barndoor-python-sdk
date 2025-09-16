from unittest.mock import AsyncMock

import pytest

from barndoor.sdk.client import BarndoorSDK


@pytest.mark.asyncio
async def test_list_servers_single_page(monkeypatch):
    sdk = BarndoorSDK(
        api_base_url="https://api.test.com",
        barndoor_token="aaa.bbb.ccc",
        validate_token_on_init=False,
    )

    # Mock response: new paginated shape with single page
    data = {
        "data": [
            {"id": "1", "name": "A", "slug": "a", "connection_status": "connected"},
            {"id": "2", "name": "B", "slug": "b", "connection_status": "available"},
        ],
        "page": 1,
        "limit": 100,
        "total": 2,
        "pages": 1,
        "previous_page": None,
        "next_page": None,
    }
    sdk._http.request = AsyncMock(return_value=data)

    servers = await sdk.list_servers()
    assert len(servers) == 2
    await sdk.aclose()


@pytest.mark.asyncio
async def test_list_servers_multi_page(monkeypatch):
    sdk = BarndoorSDK(
        api_base_url="https://api.test.com",
        barndoor_token="aaa.bbb.ccc",
        validate_token_on_init=False,
    )

    # Page 1
    p1 = {
        "data": [
            {"id": "1", "name": "A", "slug": "a", "connection_status": "connected"},
        ],
        "page": 1,
        "pages": 2,
        "next_page": 2,
    }
    # Page 2
    p2 = {
        "data": [
            {"id": "2", "name": "B", "slug": "b", "connection_status": "available"},
            {"id": "3", "name": "C", "slug": "c", "connection_status": "pending"},
        ],
        "page": 2,
        "pages": 2,
        "next_page": None,
    }

    sdk._http.request = AsyncMock(side_effect=[p1, p2])

    servers = await sdk.list_servers()
    slugs = [s.slug for s in servers]
    assert slugs == ["a", "b", "c"]
    await sdk.aclose()
