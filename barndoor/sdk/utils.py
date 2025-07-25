"""Utility functions for the Barndoor SDK.

This module contains helper functions used internally by the SDK and
potentially useful for SDK users building applications.
"""

import os

from typing import Optional
from urllib.parse import quote


__all__ = [
    "external_mcp_url",
]


def external_mcp_url(
    server_slug: str,
    jwt_token: str,
    env: str = "prod",
    region: Optional[str] = None,
) -> str:
    """Construct the external MCP URL for a given server.

    Builds the public-facing URL for accessing an MCP server through
    the Barndoor platform's edge infrastructure. The URL format varies
    based on the environment.

    Parameters
    ----------
    server_slug : str
        The unique identifier slug for the MCP server
    jwt_token : str
        User's JWT token for authentication
    env : str, optional
        Environment name: "prod", "dev", or "local". Default is "prod"
    region : str, optional
        AWS region for dev environment. If not provided, uses AWS_REGION
        environment variable or defaults to "us-east-1"

    Returns
    -------
    str
        The complete MCP URL including authentication token

    Examples
    --------
    >>> url = external_mcp_url("my-server", "jwt123", env="prod")
    >>> # Returns: https://api.barndoor.ai/mcp/my-server?token=jwt123

    >>> url = external_mcp_url("my-server", "jwt123", env="dev", region="us-west-2")
    >>> # Returns: https://api-dev-us-west-2.barndoor.ai/mcp/my-server?token=jwt123

    Notes
    -----
    The token is included as a query parameter for WebSocket compatibility.
    In production, these URLs are served through CloudFront for global
    distribution and caching.
    """
    if env == "prod":
        base = "https://api.barndoor.ai"
    elif env == "dev":
        # For dev, include region in subdomain
        if not region:
            region = os.getenv("AWS_REGION", "us-east-1")
        base = f"https://api-dev-{region}.barndoor.ai"
    else:
        # Treat local as dev default (use dev-style URL)
        if not region:
            region = os.getenv("AWS_REGION", "us-east-1")
        base = f"https://api-dev-{region}.barndoor.ai"

    # URL-encode the token to handle special characters
    encoded_token = quote(jwt_token, safe="")
    return f"{base}/mcp/{server_slug}?token={encoded_token}"


def is_valid_uuid(value: str) -> bool:
    """Check if a string is a valid UUID.

    Parameters
    ----------
    value : str
        String to validate

    Returns
    -------
    bool
        True if the string is a valid UUID format, False otherwise

    Examples
    --------
    >>> is_valid_uuid("550e8400-e29b-41d4-a716-446655440000")
    True
    >>> is_valid_uuid("not-a-uuid")
    False
    """
    import re

    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    return bool(uuid_pattern.match(value))
