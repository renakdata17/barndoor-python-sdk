"""Input validation utilities for the Barndoor SDK."""

import re
from typing import Any, Optional
from urllib.parse import urlparse

from .exceptions import ConfigurationError


def validate_url(url: str, name: str = "URL") -> str:
    """Validate that a string is a valid URL."""
    if not url or not isinstance(url, str):
        raise ConfigurationError(f"{name} must be a non-empty string")
    
    url = url.strip()
    if not url:
        raise ConfigurationError(f"{name} cannot be empty or whitespace")
    
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ConfigurationError(f"{name} must be a valid URL with scheme and host")
        if parsed.scheme not in ("http", "https"):
            raise ConfigurationError(f"{name} must use http or https scheme")
    except Exception as e:
        raise ConfigurationError(f"Invalid {name}: {e}")
    
    return url


def validate_token(token: str) -> str:
    """Validate JWT token format."""
    if not token or not isinstance(token, str):
        raise ConfigurationError("Token must be a non-empty string")
    
    token = token.strip()
    if not token:
        raise ConfigurationError("Token cannot be empty or whitespace")
    
    # Basic JWT format check (3 parts separated by dots)
    parts = token.split(".")
    if len(parts) != 3:
        raise ConfigurationError("Token must be a valid JWT (3 parts separated by dots)")
    
    return token


def validate_server_id(server_id: str) -> str:
    """Validate server ID format."""
    if not server_id or not isinstance(server_id, str):
        raise ConfigurationError("Server ID must be a non-empty string")
    
    server_id = server_id.strip()
    if not server_id:
        raise ConfigurationError("Server ID cannot be empty or whitespace")
    
    # Check if it looks like a UUID or slug
    uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    slug_pattern = re.compile(r'^[a-z0-9][a-z0-9\-_]*[a-z0-9]$|^[a-z0-9]$', re.IGNORECASE)
    
    if not (uuid_pattern.match(server_id) or slug_pattern.match(server_id)):
        raise ConfigurationError("Server ID must be a valid UUID or slug")
    
    return server_id


def validate_port(port: int, name: str = "Port") -> int:
    """Validate port number."""
    if not isinstance(port, int):
        raise ConfigurationError(f"{name} must be an integer")
    
    if not (1 <= port <= 65535):
        raise ConfigurationError(f"{name} must be between 1 and 65535")
    
    return port


def validate_timeout(timeout: float, name: str = "Timeout") -> float:
    """Validate timeout value."""
    if not isinstance(timeout, (int, float)):
        raise ConfigurationError(f"{name} must be a number")
    
    if timeout <= 0:
        raise ConfigurationError(f"{name} must be positive")
    
    if timeout > 300:  # 5 minutes max
        raise ConfigurationError(f"{name} cannot exceed 300 seconds")
    
    return float(timeout)


def validate_client_credentials(client_id: str, client_secret: str) -> tuple[str, str]:
    """Validate OAuth client credentials."""
    if not client_id or not isinstance(client_id, str):
        raise ConfigurationError("Client ID must be a non-empty string")
    
    if not client_secret or not isinstance(client_secret, str):
        raise ConfigurationError("Client secret must be a non-empty string")
    
    client_id = client_id.strip()
    client_secret = client_secret.strip()
    
    if not client_id:
        raise ConfigurationError("Client ID cannot be empty or whitespace")
    
    if not client_secret:
        raise ConfigurationError("Client secret cannot be empty or whitespace")
    
    return client_id, client_secret


def validate_optional_string(value: Any, name: str, max_length: Optional[int] = None) -> Optional[str]:
    """Validate optional string parameter."""
    if value is None:
        return None
    
    if not isinstance(value, str):
        raise ConfigurationError(f"{name} must be a string or None")
    
    value = value.strip()
    if not value:
        return None
    
    if max_length and len(value) > max_length:
        raise ConfigurationError(f"{name} cannot exceed {max_length} characters")
    
    return value