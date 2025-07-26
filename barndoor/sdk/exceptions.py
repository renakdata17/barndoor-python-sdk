"""Exception classes for the Barndoor SDK."""

from __future__ import annotations


class BarndoorError(Exception):
    """Base exception for all Barndoor SDK errors."""
    pass


class AuthenticationError(BarndoorError):
    """Raised when authentication fails."""
    
    def __init__(self, message: str, error_code: str | None = None):
        self.error_code = error_code
        super().__init__(message)


class TokenError(AuthenticationError):
    """Raised when token operations fail."""
    
    def __init__(self, message: str, help_text: str | None = None):
        self.help_text = help_text
        
        full_message = message
        if help_text:
            full_message += f" {help_text}"
        else:
            full_message += " Run 'barndoor-login' to authenticate."
        
        super().__init__(full_message)


class TokenExpiredError(TokenError):
    """Raised when a token has expired."""
    pass


class TokenValidationError(TokenError):
    """Raised when token validation fails."""
    pass


class ConnectionError(BarndoorError):
    """Raised when unable to connect to the Barndoor API."""
    
    def __init__(self, url: str, original_error: Exception):
        self.url = url
        self.original_error = original_error
        
        # Create user-friendly message
        if "timeout" in str(original_error).lower():
            user_message = f"Connection to {url} timed out. Please check your internet connection and try again."
        elif "connection refused" in str(original_error).lower():
            user_message = f"Could not connect to {url}. The service may be unavailable."
        elif "name resolution" in str(original_error).lower():
            user_message = f"Could not resolve hostname for {url}. Please check the URL and your DNS settings."
        else:
            user_message = f"Failed to connect to {url}. Please check your internet connection."
        
        super().__init__(user_message)


class HTTPError(BarndoorError):
    """Raised for HTTP error responses."""
    
    def __init__(self, status_code: int, message: str, response_body: str | None = None):
        self.status_code = status_code
        self.response_body = response_body
        
        # Create user-friendly error messages
        user_message = self._create_user_friendly_message(status_code, message, response_body)
        super().__init__(user_message)
    
    def _create_user_friendly_message(self, status_code: int, message: str, response_body: str | None) -> str:
        """Create user-friendly error message based on status code."""
        base_message = f"Request failed (HTTP {status_code})"
        
        if status_code == 400:
            return f"{base_message}: Invalid request. Please check your input parameters."
        elif status_code == 401:
            return f"{base_message}: Authentication failed. Please check your token or re-authenticate."
        elif status_code == 403:
            return f"{base_message}: Access denied. You don't have permission for this operation."
        elif status_code == 404:
            return f"{base_message}: Resource not found. Please check the server ID or URL."
        elif status_code == 429:
            return f"{base_message}: Rate limit exceeded. Please wait before making more requests."
        elif 500 <= status_code < 600:
            return f"{base_message}: Server error. Please try again later or contact support."
        else:
            return f"{base_message}: {message}"


class ServerNotFoundError(BarndoorError):
    """Raised when a requested server is not found."""
    
    def __init__(self, server_identifier: str, available_servers: list[str] | None = None):
        self.server_identifier = server_identifier
        self.available_servers = available_servers
        
        message = f"Server '{server_identifier}' not found"
        if available_servers:
            message += f". Available servers: {', '.join(available_servers)}"
        else:
            message += ". Use list_servers() to see available servers."
        
        super().__init__(message)


class OAuthError(AuthenticationError):
    """Raised when OAuth flow fails."""
    pass


class ConfigurationError(BarndoorError):
    """Raised when there's an issue with SDK configuration.

    This typically indicates missing required configuration values,
    invalid configuration parameters, or configuration conflicts.

    Examples include missing client credentials, invalid timeout values,
    or malformed URLs.
    """

    pass


class TimeoutError(BarndoorError):
    """Raised when an operation times out.

    This can occur during HTTP requests, authentication flows,
    or other time-sensitive operations that exceed their
    configured timeout limits.
    """

    pass


class OAuthError(BarndoorError):
    """Raised when OAuth authentication fails.

    This covers various OAuth-related failures including
    invalid authorization codes, expired tokens, or
    misconfigured OAuth applications.
    """

    pass
