"""Test exception hierarchy."""

from barndoor.sdk.exceptions import (
    AuthenticationError,
    BarndoorError,
    ConnectionError,
    HTTPError,
    TokenError,
)


def test_exception_hierarchy():
    """Test that exceptions inherit correctly."""
    assert issubclass(AuthenticationError, BarndoorError)
    assert issubclass(TokenError, AuthenticationError)
    assert issubclass(HTTPError, BarndoorError)
    assert issubclass(ConnectionError, BarndoorError)


def test_http_error_attributes():
    """Test HTTPError stores status code and response."""
    error = HTTPError(404, "Not Found", "Server not found")
    assert error.status_code == 404
    assert error.response_body == "Server not found"
    assert "HTTP 404" in str(error)


def test_connection_error_attributes():
    """Test ConnectionError stores URL and original error."""
    original = Exception("Network timeout")
    error = ConnectionError("https://api.test.com", original)
    assert error.url == "https://api.test.com"
    assert error.original_error is original
