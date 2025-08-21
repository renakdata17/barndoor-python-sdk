"""Pydantic models for the Barndoor SDK.

This module defines the data models used for API requests and responses,
providing type safety and automatic validation.
"""

from typing import Optional

from pydantic import BaseModel


class ServerSummary(BaseModel):
    """Summary information about an MCP server.

    Represents basic server information as returned by the list servers
    endpoint. This is a lightweight representation suitable for listing
    many servers at once.

    Attributes
    ----------
    id : str
        Unique identifier (UUID) for the server
    name : str
        Human-readable name of the server
    slug : str
        URL-friendly identifier used in API paths
    provider : str, optional
        Third-party provider name (e.g., "github", "slack")
    connection_status : str
        Current connection status: "available", "pending", or "connected"
    """

    id: str
    name: str
    slug: str
    provider: Optional[str] = None
    connection_status: str
    proxy_url: Optional[str] = None


class ServerDetail(ServerSummary):
    """Detailed information about an MCP server.

    Extends ServerSummary with additional fields returned when fetching
    a single server's details.

    Attributes
    ----------
    url : str, optional
        MCP base URL from the server directory
    """

    url: str | None = None  # MCP base url from directory


class AgentToken(BaseModel):
    """Response from the agent token exchange endpoint.

    Contains the agent access token and expiration information returned
    when exchanging client credentials.

    Attributes
    ----------
    agent_token : str
        The agent access token to use for agent operations
    expires_in : int
        Token lifetime in seconds
    """

    agent_token: str
    expires_in: int
