"""Internal HTTP client wrapper for the Barndoor SDK.

This module provides a thin wrapper around httpx to handle connection
pooling and error handling consistently across the SDK.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from .exceptions import ConnectionError


@dataclass
class TimeoutConfig:
    """Configuration for HTTP request timeouts."""

    read: float = 30.0
    connect: float = 10.0
    write: float = 30.0
    pool: float = 30.0


class HTTPClient:
    """Async HTTP client with connection pooling and error handling."""

    def __init__(self, timeout_config: TimeoutConfig | None = None, max_retries: int = 3):
        self._client: httpx.AsyncClient | None = None
        self.timeout_config = timeout_config or TimeoutConfig()
        self.max_retries = max_retries

    async def request(self, method: str, url: str, **kwargs) -> dict:
        """Make HTTP request and return JSON response."""
        if self._client is None:
            timeout = httpx.Timeout(
                read=self.timeout_config.read,
                connect=self.timeout_config.connect,
                write=self.timeout_config.write,
                pool=self.timeout_config.pool,
            )
            self._client = httpx.AsyncClient(timeout=timeout)

        try:
            resp = await self._client.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ConnectionError(url, exc) from exc
        except httpx.HTTPStatusError as exc:
            raise exc  # Let caller handle HTTP errors
        except Exception as exc:
            raise RuntimeError(f"HTTP request failed: {exc}") from exc

    async def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def aclose(self) -> None:
        """Alias for close() to match expected interface."""
        await self.close()
