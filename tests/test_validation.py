"""Tests for input validation utilities."""

import pytest

from barndoor.sdk.exceptions import ConfigurationError
from barndoor.sdk.validation import (
    validate_client_credentials,
    validate_optional_string,
    validate_port,
    validate_server_id,
    validate_timeout,
    validate_token,
    validate_url,
)


class TestValidateUrl:
    """Test URL validation."""

    def test_valid_https_url(self):
        """Test valid HTTPS URL."""
        url = validate_url("https://api.barndoor.ai")
        assert url == "https://api.barndoor.ai"

    def test_valid_http_url(self):
        """Test valid HTTP URL."""
        url = validate_url("http://localhost:8080")
        assert url == "http://localhost:8080"

    def test_url_with_path(self):
        """Test URL with path."""
        url = validate_url("https://api.barndoor.ai/v1/servers")
        assert url == "https://api.barndoor.ai/v1/servers"

    def test_empty_url(self):
        """Test empty URL."""
        with pytest.raises(ConfigurationError, match="URL must be a non-empty string"):
            validate_url("")

    def test_none_url(self):
        """Test None URL."""
        with pytest.raises(ConfigurationError, match="URL must be a non-empty string"):
            validate_url(None)

    def test_invalid_scheme(self):
        """Test URL with invalid scheme."""
        with pytest.raises(ConfigurationError, match="URL must use http or https scheme"):
            validate_url("ftp://example.com")

    def test_no_scheme(self):
        """Test URL without scheme."""
        with pytest.raises(ConfigurationError, match="URL must be a valid URL with scheme"):
            validate_url("example.com")


class TestValidateToken:
    """Test token validation."""

    def test_valid_jwt_token(self):
        """Test valid JWT token."""
        token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.signature"
        result = validate_token(token)
        assert result == token

    def test_empty_token(self):
        """Test empty token."""
        with pytest.raises(ConfigurationError, match="Token must be a non-empty string"):
            validate_token("")

    def test_none_token(self):
        """Test None token."""
        with pytest.raises(ConfigurationError, match="Token must be a non-empty string"):
            validate_token(None)

    def test_invalid_jwt_format(self):
        """Test invalid JWT format."""
        with pytest.raises(ConfigurationError, match="Token must be a valid JWT"):
            validate_token("invalid.token")


class TestValidateServerId:
    """Test server ID validation."""

    def test_valid_uuid(self):
        """Test valid UUID."""
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        result = validate_server_id(uuid)
        assert result == uuid

    def test_valid_slug(self):
        """Test valid slug."""
        slug = "salesforce"
        result = validate_server_id(slug)
        assert result == slug

    def test_valid_slug_with_hyphens(self):
        """Test valid slug with hyphens."""
        slug = "my-server-name"
        result = validate_server_id(slug)
        assert result == slug

    def test_single_character_slug(self):
        """Test single character slug."""
        slug = "a"
        result = validate_server_id(slug)
        assert result == slug

    def test_empty_server_id(self):
        """Test empty server ID."""
        with pytest.raises(ConfigurationError, match="Server ID must be a non-empty string"):
            validate_server_id("")

    def test_invalid_characters(self):
        """Test server ID with invalid characters."""
        with pytest.raises(ConfigurationError, match="Server ID must be a valid UUID or slug"):
            validate_server_id("invalid server!")


class TestValidatePort:
    """Test port validation."""

    def test_valid_port(self):
        """Test valid port number."""
        port = validate_port(8080)
        assert port == 8080

    def test_port_boundary_values(self):
        """Test port boundary values."""
        assert validate_port(1) == 1
        assert validate_port(65535) == 65535

    def test_invalid_port_type(self):
        """Test invalid port type."""
        with pytest.raises(ConfigurationError, match="Port must be an integer"):
            validate_port("8080")

    def test_port_out_of_range_low(self):
        """Test port number too low."""
        with pytest.raises(ConfigurationError, match="Port must be between 1 and 65535"):
            validate_port(0)

    def test_port_out_of_range_high(self):
        """Test port number too high."""
        with pytest.raises(ConfigurationError, match="Port must be between 1 and 65535"):
            validate_port(65536)


class TestValidateTimeout:
    """Test timeout validation."""

    def test_valid_timeout_int(self):
        """Test valid timeout as integer."""
        timeout = validate_timeout(30)
        assert timeout == 30.0

    def test_valid_timeout_float(self):
        """Test valid timeout as float."""
        timeout = validate_timeout(30.5)
        assert timeout == 30.5

    def test_zero_timeout(self):
        """Test zero timeout."""
        with pytest.raises(ConfigurationError, match="Timeout must be positive"):
            validate_timeout(0)

    def test_negative_timeout(self):
        """Test negative timeout."""
        with pytest.raises(ConfigurationError, match="Timeout must be positive"):
            validate_timeout(-1)

    def test_excessive_timeout(self):
        """Test excessively large timeout."""
        with pytest.raises(ConfigurationError, match="Timeout cannot exceed 300 seconds"):
            validate_timeout(400)


class TestValidateClientCredentials:
    """Test client credentials validation."""

    def test_valid_credentials(self):
        """Test valid client credentials."""
        client_id, client_secret = validate_client_credentials("test-id", "test-secret")
        assert client_id == "test-id"
        assert client_secret == "test-secret"

    def test_empty_client_id(self):
        """Test empty client ID."""
        with pytest.raises(ConfigurationError, match="Client ID must be a non-empty string"):
            validate_client_credentials("", "secret")

    def test_empty_client_secret(self):
        """Test empty client secret."""
        with pytest.raises(ConfigurationError, match="Client secret must be a non-empty string"):
            validate_client_credentials("id", "")

    def test_whitespace_only_credentials(self):
        """Test whitespace-only credentials."""
        with pytest.raises(ConfigurationError, match="Client ID cannot be empty or whitespace"):
            validate_client_credentials("   ", "secret")


class TestValidateOptionalString:
    """Test optional string validation."""

    def test_valid_string(self):
        """Test valid string."""
        result = validate_optional_string("test", "Test field")
        assert result == "test"

    def test_none_value(self):
        """Test None value."""
        result = validate_optional_string(None, "Test field")
        assert result is None

    def test_empty_string(self):
        """Test empty string."""
        result = validate_optional_string("", "Test field")
        assert result is None

    def test_whitespace_string(self):
        """Test whitespace-only string."""
        result = validate_optional_string("   ", "Test field")
        assert result is None

    def test_string_too_long(self):
        """Test string exceeding max length."""
        with pytest.raises(ConfigurationError, match="Test field cannot exceed 5 characters"):
            validate_optional_string("toolong", "Test field", max_length=5)

    def test_invalid_type(self):
        """Test invalid type."""
        with pytest.raises(ConfigurationError, match="Test field must be a string or None"):
            validate_optional_string(123, "Test field")
