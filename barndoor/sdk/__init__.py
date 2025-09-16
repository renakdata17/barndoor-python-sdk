"""Barndoor SDK - Python client for the Barndoor Platform API.

The Barndoor SDK provides a simple, async interface for interacting with
the Barndoor platform, including:

- User authentication and token management
- MCP server discovery and connection
- OAuth flow handling for third-party integrations
- Agent credential exchange

Quick Start
-----------
>>> from barndoor.sdk import BarndoorSDK
>>> sdk = BarndoorSDK("https://api.barndoor.host", barndoor_token="your_token")
>>> servers = await sdk.list_servers()

For interactive login:
>>> from barndoor.sdk.quickstart import login_interactive
>>> sdk = await login_interactive()

Main Components
---------------
- BarndoorSDK: Main client class for API interactions
- quickstart: Helper functions for rapid prototyping
- auth: OAuth and authentication utilities
- models: Pydantic models for API data structures
"""

from .client import BarndoorSDK
from .exceptions import BarndoorError, ConnectionError, HTTPError
from .models import AgentToken, ServerDetail, ServerSummary
from .quickstart import (
    ensure_server_connected,
    login_interactive,
    make_mcp_connection_params,
)

__all__ = [
    "BarndoorSDK",
    "BarndoorError",
    "ConnectionError",
    "HTTPError",
    "ServerSummary",
    "ServerDetail",
    "AgentToken",
    # quick-start helpers
    "login_interactive",
    "ensure_server_connected",
    "make_mcp_connection_params",
]

__version__ = "0.1.0"
