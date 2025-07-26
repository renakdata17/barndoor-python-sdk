"""Test auth_store module functionality."""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
import pytest
import httpx

from barndoor.sdk.auth_store import (
    TokenManager,
    verify_jwt_local,
    _get_jwks,
    _FileLock,
    load_user_token,
    save_user_token,
    clear_cached_token,
)
from barndoor.sdk.exceptions import TokenError, TokenExpiredError


@pytest.fixture
def temp_token_dir():
    """Create a temporary directory for token storage."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        token_file = temp_path / "token.json"
        with patch("barndoor.sdk.auth_store.TOKEN_FILE", token_file):
            yield temp_path


@pytest.fixture
def isolated_token_file():
    """Create an isolated token file for testing legacy functions."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        token_file = Path(f.name)
    try:
        yield token_file
    finally:
        if token_file.exists():
            token_file.unlink()


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    config = MagicMock()
    config.auth_domain = "test.auth0.com"
    config.client_id = "test-client-id"
    config.client_secret = "test-client-secret"
    config.api_audience = "https://test.api/"
    return config


@pytest.fixture
def sample_token_data():
    """Sample token data for testing."""
    return {
        "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0LXVzZXIiLCJleHAiOjk5OTk5OTk5OTl9.test",
        "refresh_token": "refresh_token_123",
        "token_type": "Bearer",
        "expires_in": 3600,
    }


@pytest.fixture
def expired_token_data():
    """Expired token data for testing."""
    return {
        "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0LXVzZXIiLCJleHAiOjE2MDAwMDAwMDB9.test",
        "refresh_token": "refresh_token_123",
        "token_type": "Bearer",
        "expires_in": 3600,
    }


@pytest.fixture
def mock_jwks_keys():
    """Mock JWKS keys for testing."""
    return [
        {
            "kty": "RSA",
            "kid": "test-key-id",
            "use": "sig",
            "n": "test-modulus",
            "e": "AQAB",
        }
    ]


class TestTokenManager:
    """Test TokenManager class functionality."""

    def test_init(self):
        """Test TokenManager initialization."""
        manager = TokenManager("https://api.test.com/")
        assert manager.api_base_url == "https://api.test.com"

    @pytest.mark.asyncio
    async def test_get_valid_token_no_token(self, temp_token_dir):
        """Test get_valid_token when no token exists."""
        manager = TokenManager("https://api.test.com")
        
        with pytest.raises(TokenError, match="No token found"):
            await manager.get_valid_token()

    @pytest.mark.asyncio
    async def test_get_valid_token_valid_local(self, temp_token_dir, sample_token_data, mock_config):
        """Test get_valid_token with valid token (local verification)."""
        # Save token to file
        token_file = temp_token_dir / "token.json"
        with open(token_file, 'w') as f:
            json.dump(sample_token_data, f)

        manager = TokenManager("https://api.test.com")
        
        with patch("barndoor.sdk.config.get_static_config", return_value=mock_config), \
             patch("barndoor.sdk.auth_store.verify_jwt_local", return_value=True):
            
            token = await manager.get_valid_token()
            assert token == sample_token_data["access_token"]

    @pytest.mark.asyncio
    async def test_get_valid_token_valid_remote(self, temp_token_dir, sample_token_data, mock_config):
        """Test get_valid_token with valid token (remote verification)."""
        # Save token to file
        token_file = temp_token_dir / "token.json"
        with open(token_file, 'w') as f:
            json.dump(sample_token_data, f)

        manager = TokenManager("https://api.test.com")
        
        with patch("barndoor.sdk.config.get_static_config", return_value=mock_config), \
             patch("barndoor.sdk.auth_store.verify_jwt_local", return_value=None), \
             patch.object(manager, "_is_token_live_remote", return_value=True):
            
            token = await manager.get_valid_token()
            assert token == sample_token_data["access_token"]

    @pytest.mark.asyncio
    async def test_refresh_token_persistence(self, temp_token_dir, sample_token_data, mock_config):
        """Test that rotated refresh tokens are properly persisted."""
        # Save initial token to file
        token_file = temp_token_dir / "token.json"
        with open(token_file, 'w') as f:
            json.dump(sample_token_data, f)

        manager = TokenManager("https://api.test.com")
        
        # Mock refresh response with new refresh token
        new_token_data = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token_456",  # Rotated refresh token
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        
        with patch("barndoor.sdk.config.get_static_config", return_value=mock_config), \
             patch("barndoor.sdk.auth_store.verify_jwt_local", return_value=False), \
             patch.object(manager, "_is_token_live_remote", return_value=False), \
             patch.object(manager, "_refresh_token", return_value=new_token_data):
            
            token = await manager.get_valid_token()
            assert token == "new_access_token"
            
            # Verify the rotated refresh token was saved
            with open(token_file, 'r') as f:
                saved_data = json.load(f)
            
            assert saved_data["access_token"] == "new_access_token"
            assert saved_data["refresh_token"] == "new_refresh_token_456"  # Should be the new one
            assert saved_data["token_type"] == "Bearer"  # Original data preserved

    @pytest.mark.asyncio
    async def test_refresh_token_error_handling(self, temp_token_dir, sample_token_data, mock_config):
        """Test error handling in _refresh_token method."""
        # Save token to file
        token_file = temp_token_dir / "token.json"
        with open(token_file, 'w') as f:
            json.dump(sample_token_data, f)

        manager = TokenManager("https://api.test.com")
        
        # Test 400 error (invalid refresh token)
        mock_response_400 = MagicMock()
        mock_response_400.status_code = 400
        mock_response_400.json.return_value = {"error_description": "Invalid refresh token"}
        mock_response_400.headers = {"content-type": "application/json"}
        
        with patch("barndoor.sdk.config.get_static_config", return_value=mock_config), \
             patch("httpx.AsyncClient") as mock_client:
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response_400
            
            with pytest.raises(TokenExpiredError, match="Refresh token expired or invalid"):
                await manager._refresh_token(sample_token_data)

        # Test 429 error (rate limited)
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        
        with patch("barndoor.sdk.config.get_static_config", return_value=mock_config), \
             patch("httpx.AsyncClient") as mock_client:
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response_429
            
            with pytest.raises(TokenError, match="Rate limited"):
                await manager._refresh_token(sample_token_data)

        # Test 500 error (server error)
        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500
        
        with patch("barndoor.sdk.config.get_static_config", return_value=mock_config), \
             patch("httpx.AsyncClient") as mock_client:

            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response_500

            with pytest.raises(TokenError, match="Auth server temporarily unavailable"):
                await manager._refresh_token(sample_token_data)

        # Test timeout error
        with patch("barndoor.sdk.config.get_static_config", return_value=mock_config), \
             patch("httpx.AsyncClient") as mock_client:
            
            mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.TimeoutException("Timeout")
            
            with pytest.raises(TokenError, match="Token refresh timed out"):
                await manager._refresh_token(sample_token_data)

    def test_save_token_data_file_locking(self, temp_token_dir, sample_token_data):
        """Test that _save_token_data uses file locking."""
        manager = TokenManager("https://api.test.com")
        
        with patch("barndoor.sdk.auth_store._FileLock") as mock_lock:
            mock_lock.return_value.__enter__.return_value = mock_lock
            mock_lock.return_value.__exit__.return_value = None
            
            manager._save_token_data(sample_token_data)
            
            # Verify file lock was used
            mock_lock.assert_called_once()

    def test_load_token_data_missing_file(self, temp_token_dir):
        """Test _load_token_data when file doesn't exist."""
        manager = TokenManager("https://api.test.com")
        result = manager._load_token_data()
        assert result is None

    def test_load_token_data_invalid_json(self, temp_token_dir):
        """Test _load_token_data with invalid JSON."""
        token_file = temp_token_dir / "token.json"
        token_file.write_text("invalid json")
        
        manager = TokenManager("https://api.test.com")
        result = manager._load_token_data()
        assert result is None

    def test_should_refresh_token(self, sample_token_data, expired_token_data):
        """Test _should_refresh_token logic."""
        manager = TokenManager("https://api.test.com")
        
        # Valid token should not need refresh
        assert not manager._should_refresh_token(sample_token_data)
        
        # Expired token should need refresh
        assert manager._should_refresh_token(expired_token_data)
        
        # Invalid token data should need refresh
        assert manager._should_refresh_token({"access_token": "invalid"})


class TestJWTVerification:
    """Test JWT verification functionality."""

    def test_get_jwks_success(self, mock_jwks_keys):
        """Test successful JWKS fetching."""
        with patch("httpx.Client") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"keys": mock_jwks_keys}
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            
            # Clear cache first
            _get_jwks.cache_clear()
            
            keys = _get_jwks("test.auth0.com")
            assert keys == mock_jwks_keys

    def test_get_jwks_failure(self):
        """Test JWKS fetching failure."""
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = Exception("Network error")
            
            # Clear cache first
            _get_jwks.cache_clear()
            
            keys = _get_jwks("test.auth0.com")
            assert keys == []

    def test_verify_jwt_local_no_keys(self):
        """Test local JWT verification when no JWKS keys available."""
        with patch("barndoor.sdk.auth_store._get_jwks", return_value=[]):
            result = verify_jwt_local("token", "test.auth0.com", "audience")
            assert result is None

    def test_verify_jwt_local_success(self, mock_jwks_keys):
        """Test successful local JWT verification."""
        with patch("barndoor.sdk.auth_store._get_jwks", return_value=mock_jwks_keys), \
             patch("barndoor.sdk.auth_store.jwt.decode") as mock_decode:
            
            mock_decode.return_value = {"sub": "test-user"}
            
            result = verify_jwt_local("token", "test.auth0.com", "audience")
            assert result is True

    def test_verify_jwt_local_expired(self, mock_jwks_keys):
        """Test local JWT verification with expired token."""
        from jose import jwt as jose_jwt
        
        with patch("barndoor.sdk.auth_store._get_jwks", return_value=mock_jwks_keys), \
             patch("barndoor.sdk.auth_store.jwt.decode") as mock_decode:
            
            mock_decode.side_effect = jose_jwt.ExpiredSignatureError("Token expired")
            
            result = verify_jwt_local("token", "test.auth0.com", "audience")
            assert result is False

    def test_verify_jwt_local_invalid(self, mock_jwks_keys):
        """Test local JWT verification with invalid token."""
        with patch("barndoor.sdk.auth_store._get_jwks", return_value=mock_jwks_keys), \
             patch("barndoor.sdk.auth_store.jwt.decode") as mock_decode:
            
            mock_decode.side_effect = Exception("Invalid token")
            
            result = verify_jwt_local("token", "test.auth0.com", "audience")
            assert result is None


class TestFileLocking:
    """Test file locking functionality."""

    def test_file_lock_context_manager(self, temp_token_dir):
        """Test _FileLock context manager."""
        test_file = temp_token_dir / "test.json"
        lock = _FileLock(test_file)
        
        # Test successful lock acquisition and release
        with lock:
            assert lock.lock_fd is not None

    def test_file_lock_exception_handling(self, temp_token_dir):
        """Test _FileLock handles exceptions gracefully."""
        test_file = temp_token_dir / "test.json"
        lock = _FileLock(test_file)
        
        # Mock file operations to raise exceptions
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            # Should not raise exception, just continue without locking
            with lock:
                pass


class TestLegacyFunctions:
    """Test legacy token management functions."""

    def test_load_user_token_success(self, temp_token_dir, sample_token_data):
        """Test load_user_token with valid token file."""
        token_file = temp_token_dir / "token.json"
        with open(token_file, 'w') as f:
            json.dump(sample_token_data, f)
        
        with patch("barndoor.sdk.auth_store.TOKEN_FILE", token_file):
            token = load_user_token()
            assert token == sample_token_data["access_token"]

    def test_load_user_token_missing_file(self, temp_token_dir):
        """Test load_user_token when file doesn't exist."""
        token_file = temp_token_dir / "nonexistent.json"
        
        with patch("barndoor.sdk.auth_store.TOKEN_FILE", token_file):
            token = load_user_token()
            assert token is None

    def test_save_user_token_string(self, temp_token_dir):
        """Test save_user_token with string token."""
        token_file = temp_token_dir / "token.json"
        
        with patch("barndoor.sdk.auth_store.TOKEN_FILE", token_file):
            save_user_token("test_token")
            
            with open(token_file, 'r') as f:
                data = json.load(f)
            
            assert data["access_token"] == "test_token"

    def test_save_user_token_dict(self, temp_token_dir, sample_token_data):
        """Test save_user_token with dict token."""
        token_file = temp_token_dir / "token.json"
        
        with patch("barndoor.sdk.auth_store.TOKEN_FILE", token_file):
            save_user_token(sample_token_data)
            
            with open(token_file, 'r') as f:
                data = json.load(f)
            
            assert data == sample_token_data

    def test_clear_cached_token(self, temp_token_dir, sample_token_data):
        """Test clear_cached_token function."""
        token_file = temp_token_dir / "token.json"
        with open(token_file, 'w') as f:
            json.dump(sample_token_data, f)

        with patch("barndoor.sdk.auth_store.TOKEN_FILE", token_file):
            clear_cached_token()
            assert not token_file.exists()


class TestConcurrentAccess:
    """Test concurrent access scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_token_refresh(self, temp_token_dir, sample_token_data, mock_config):
        """Test concurrent token refresh operations."""
        # Save initial token to file
        token_file = temp_token_dir / "token.json"
        with open(token_file, 'w') as f:
            json.dump(sample_token_data, f)

        manager1 = TokenManager("https://api.test.com")
        manager2 = TokenManager("https://api.test.com")

        # Mock refresh response
        new_token_data = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        refresh_call_count = 0

        async def mock_refresh(token_data):
            nonlocal refresh_call_count
            refresh_call_count += 1
            # Simulate some delay
            await asyncio.sleep(0.1)
            return new_token_data

        with patch("barndoor.sdk.config.get_static_config", return_value=mock_config), \
             patch("barndoor.sdk.auth_store.verify_jwt_local", return_value=False), \
             patch.object(manager1, "_is_token_live_remote", return_value=False), \
             patch.object(manager2, "_is_token_live_remote", return_value=False), \
             patch.object(manager1, "_refresh_token", side_effect=mock_refresh), \
             patch.object(manager2, "_refresh_token", side_effect=mock_refresh):

            # Run concurrent token refresh operations
            results = await asyncio.gather(
                manager1.get_valid_token(),
                manager2.get_valid_token(),
                return_exceptions=True
            )

            # Both should succeed
            assert all(result == "new_access_token" for result in results)

            # Both managers should have called refresh (file locking prevents corruption)
            assert refresh_call_count == 2

    def test_concurrent_file_writes(self, temp_token_dir, sample_token_data):
        """Test concurrent file write operations with locking."""
        import threading
        import time

        token_file = temp_token_dir / "token.json"
        manager = TokenManager("https://api.test.com")

        write_results = []

        def write_token(data, delay=0):
            """Write token data with optional delay."""
            time.sleep(delay)
            try:
                manager._save_token_data(data)
                write_results.append("success")
            except Exception as e:
                write_results.append(f"error: {e}")

        # Create different token data for each thread
        token_data_1 = {**sample_token_data, "access_token": "token_1"}
        token_data_2 = {**sample_token_data, "access_token": "token_2"}

        # Start concurrent writes
        thread1 = threading.Thread(target=write_token, args=(token_data_1, 0.1))
        thread2 = threading.Thread(target=write_token, args=(token_data_2, 0.05))

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # Both writes should succeed
        assert len(write_results) == 2
        assert all(result == "success" for result in write_results)

        # File should contain valid JSON (not corrupted)
        with open(token_file, 'r') as f:
            final_data = json.load(f)

        # Should be one of the two tokens (whichever wrote last)
        assert final_data["access_token"] in ["token_1", "token_2"]


class TestEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_refresh_token_missing(self, temp_token_dir, mock_config):
        """Test refresh when refresh_token is missing."""
        token_data = {
            "access_token": "access_token_only",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        manager = TokenManager("https://api.test.com")

        with patch("barndoor.sdk.config.get_static_config", return_value=mock_config):
            with pytest.raises(TokenError, match="No refresh token available"):
                await manager._refresh_token(token_data)

    @pytest.mark.asyncio
    async def test_network_error_during_refresh(self, temp_token_dir, sample_token_data, mock_config):
        """Test network error during token refresh."""
        manager = TokenManager("https://api.test.com")

        with patch("barndoor.sdk.config.get_static_config", return_value=mock_config), \
             patch("httpx.AsyncClient") as mock_client:

            mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.NetworkError("Connection failed")

            with pytest.raises(TokenError, match="Network error during token refresh"):
                await manager._refresh_token(sample_token_data)

    def test_file_permissions(self, temp_token_dir, sample_token_data):
        """Test that saved token files have correct permissions."""
        manager = TokenManager("https://api.test.com")
        token_file = temp_token_dir / "token.json"

        with patch("barndoor.sdk.auth_store.TOKEN_FILE", token_file):
            manager._save_token_data(sample_token_data)

            # Check file permissions (should be 0o600)
            file_mode = oct(token_file.stat().st_mode)[-3:]
            assert file_mode == "600"

    @pytest.mark.asyncio
    async def test_malformed_refresh_response(self, temp_token_dir, sample_token_data, mock_config):
        """Test handling of malformed refresh response."""
        manager = TokenManager("https://api.test.com")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)

        with patch("barndoor.sdk.config.get_static_config", return_value=mock_config), \
             patch("httpx.AsyncClient") as mock_client:

            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            with pytest.raises(TokenError, match="Token refresh failed"):
                await manager._refresh_token(sample_token_data)

    def test_jwks_caching(self, mock_jwks_keys):
        """Test that JWKS keys are properly cached."""
        with patch("httpx.Client") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"keys": mock_jwks_keys}
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            # Clear cache first
            _get_jwks.cache_clear()

            # First call should hit the network
            keys1 = _get_jwks("test.auth0.com")
            assert keys1 == mock_jwks_keys

            # Second call should use cache (no additional network call)
            keys2 = _get_jwks("test.auth0.com")
            assert keys2 == mock_jwks_keys

            # Should only have made one HTTP request
            assert mock_client.return_value.__enter__.return_value.get.call_count == 1

    @pytest.mark.asyncio
    async def test_token_validation_fallback_chain(self, temp_token_dir, sample_token_data, mock_config):
        """Test the complete validation fallback chain."""
        # Save token to file
        token_file = temp_token_dir / "token.json"
        with open(token_file, 'w') as f:
            json.dump(sample_token_data, f)

        manager = TokenManager("https://api.test.com")

        # Test scenario: local verification fails, remote verification succeeds
        with patch("barndoor.sdk.config.get_static_config", return_value=mock_config), \
             patch("barndoor.sdk.auth_store.verify_jwt_local", return_value=None), \
             patch.object(manager, "_is_token_live_remote", return_value=True):

            token = await manager.get_valid_token()
            assert token == sample_token_data["access_token"]

        # Test scenario: both local and remote fail, refresh succeeds
        new_token_data = {
            "access_token": "refreshed_token",
            "refresh_token": "new_refresh_token",
        }

        with patch("barndoor.sdk.config.get_static_config", return_value=mock_config), \
             patch("barndoor.sdk.auth_store.verify_jwt_local", return_value=None), \
             patch.object(manager, "_is_token_live_remote", return_value=False), \
             patch.object(manager, "_refresh_token", return_value=new_token_data):

            token = await manager.get_valid_token()
            assert token == "refreshed_token"
