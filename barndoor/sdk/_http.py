"""Internal HTTP client wrapper for the Barndoor SDK.

This module provides a thin wrapper around httpx to handle connection
pooling and error handling consistently across the SDK.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from .exceptions import ConnectionError, HTTPError, TimeoutError


@dataclass
class TimeoutConfig:
    """Configuration for HTTP request timeouts."""

    read: float = 30.0
    connect: float = 10.0
    write: float = 10.0
    pool: float = 10.0

    def to_httpx_timeout(self) -> httpx.Timeout:
        """Return an httpx.Timeout constructed from this config."""
        return httpx.Timeout(
            read=self.read,
            connect=self.connect,
            write=self.write,
            pool=self.pool,
        )


class HTTPClient:
    """Async HTTP client with connection pooling and error handling."""

    def __init__(self, timeout_config: TimeoutConfig | None = None, max_retries: int = 3):
        self._client: httpx.AsyncClient | None = None
        self.timeout_config = timeout_config or TimeoutConfig()
        self.max_retries = max_retries
        self._closed: bool = False

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazily create and return the underlying AsyncClient."""
        if self._closed:
            raise RuntimeError("HTTP client has been closed")
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_config.to_httpx_timeout())
        return self._client

    async def request(self, method: str, url: str, **kwargs) -> dict:
        """Make HTTP request and return JSON response with retries and mapping."""
        if self._closed:
            raise RuntimeError("HTTP client has been closed")

        client = await self._get_client()
        attempt = 0
        while True:
            try:
                resp = await client.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp.json()
            except httpx.TimeoutException as exc:
                # Map timeouts to our TimeoutError and do not retry
                raise TimeoutError(f"{method} {url} request timed out") from exc
            except httpx.ConnectError as exc:
                # Retry connect errors up to max_retries
                if attempt < self.max_retries:
                    attempt += 1
                    await asyncio.sleep(0.1 * attempt)
                    continue
                raise ConnectionError(url, exc) from exc
            except httpx.HTTPStatusError as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None) or 0
                body = None
                try:
                    body = exc.response.text  # type: ignore[union-attr]
                except Exception:
                    body = None
                # No retries for 4xx; wrap as our HTTPError
                raise HTTPError(status, body or str(exc), body) from exc
            except Exception as exc:
                raise RuntimeError(f"HTTP request failed: {exc}") from exc

    async def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._closed = True

    async def aclose(self) -> None:
        """Alias for close() to match expected interface."""
        await self.close()
