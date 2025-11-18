"""Token storage and refresh management."""

import json
import os
import time
from functools import lru_cache
from pathlib import Path

import httpx
from jose import jwt

from .exceptions import TokenError, TokenExpiredError
from .logging import get_logger

# Import file locking utilities
try:
    import fcntl  # Unix/Linux file locking

    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

try:
    import msvcrt  # Windows file locking

    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

logger = get_logger("auth_store")

TOKEN_FILE = Path.home() / ".barndoor" / "token.json"


class _FileLock:
    """Simple file locking context manager for cross-platform compatibility."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lock_file = file_path.with_suffix(file_path.suffix + ".lock")
        self.lock_fd = None

    def __enter__(self):
        """Acquire file lock."""
        try:
            # Create lock file
            self.lock_fd = open(self.lock_file, "w")

            if HAS_FCNTL:
                # Unix/Linux: use fcntl for advisory locking
                fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX)
            elif HAS_MSVCRT:
                # Windows: use msvcrt for file locking
                msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_LOCK, 1)
            # If neither is available, proceed without locking (best effort)

            return self
        except Exception as e:
            logger.debug(f"Failed to acquire file lock: {e}")
            # Continue without locking rather than failing
            return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release file lock."""
        if self.lock_fd:
            try:
                if HAS_FCNTL:
                    fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
                elif HAS_MSVCRT:
                    msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_UNLCK, 1)

                self.lock_fd.close()

                # Clean up lock file
                if self.lock_file.exists():
                    self.lock_file.unlink()
            except Exception as e:
                logger.debug(f"Failed to release file lock: {e}")
                # Don't raise - cleanup is best effort


@lru_cache(maxsize=1)
def _get_jwks(auth_domain: str) -> list:
    """Fetch and cache JWKS from Auth0."""
    url = f"https://{auth_domain}/.well-known/jwks.json"
    try:
        # Use a shorter timeout and be more defensive
        with httpx.Client(timeout=3.0) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.json().get("keys", [])
    except Exception as e:
        logger.debug(f"Failed to fetch JWKS from {url}: {e}")
        return []  # Return empty list to fall back to remote validation


def verify_jwt_local(token: str, auth_domain: str, audience: str) -> bool | None:
    """Verify JWT locally using JWKS.

    Returns:
        True: Token is valid and not expired
        False: Token is expired (but otherwise valid)
        None: Token is invalid or couldn't be verified
    """
    try:
        keys = _get_jwks(auth_domain)
        if not keys:
            logger.debug("No JWKS keys available, falling back to remote validation")
            return None

        # Verify the token
        jwt.decode(
            token,
            keys,  # jose will pick the right key by 'kid'
            audience=audience,
            issuer=f"https://{auth_domain}/",
            options={"verify_aud": True},
        )
        logger.debug("Token verified locally using JWKS")
        return True
    except jwt.ExpiredSignatureError:
        logger.debug("Token expired (verified locally)")
        return False  # expired - let refresh path handle it
    except Exception as e:
        logger.debug(f"JWT verification failed: {e}")
        return None  # couldn't verify - try /userinfo fallback


class TokenManager:
    """Manages token storage, validation, and refresh."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def get_valid_token(self) -> str:
        """Get a valid token, refreshing if necessary."""
        token_data = self._load_token_data()

        if not token_data:
            raise TokenError("No token found. Please authenticate.")

        # Validate or refresh token using fast-path approach
        try:
            token_data = await self._validate_or_refresh(token_data)
            self._save_token_data(token_data)
            return token_data["access_token"]
        except Exception as e:
            logger.error(f"Token validation/refresh failed: {e}")
            raise TokenExpiredError("Token expired and refresh failed. Please re-authenticate.")

    def _load_token_data(self) -> dict | None:
        """Load token data from storage."""
        if not TOKEN_FILE.exists():
            return None

        try:
            with open(TOKEN_FILE) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load token file: {e}")
            return None

    def _save_token_data(self, token_data: dict) -> None:
        """Save token data to storage with file locking to prevent race conditions."""
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Use file locking to prevent concurrent writes
        with _FileLock(TOKEN_FILE):
            with open(TOKEN_FILE, "w") as f:
                json.dump(token_data, f, indent=2)

            # Set restrictive permissions
            os.chmod(TOKEN_FILE, 0o600)
            logger.debug("Token saved to storage")

    def _should_refresh_token(self, token_data: dict) -> bool:
        """Check if token should be refreshed."""
        try:
            claims = jwt.get_unverified_claims(token_data["access_token"])
            exp = claims.get("exp", 0)

            # Refresh if token expires within 5 minutes
            return (exp - time.time()) < 300
        except Exception:
            return True  # Refresh if we can't parse the token

    async def _refresh_token(self, token_data: dict) -> dict:
        """Refresh the access token using refresh token.

        Raises:
            TokenError: If no refresh token is available or refresh fails
            TokenExpiredError: If the refresh token itself is expired/invalid
        """
        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            raise TokenError("No refresh token available")

        from .config import get_static_config

        cfg = get_static_config()

        payload = {
            "grant_type": "refresh_token",
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "refresh_token": refresh_token,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://{cfg.auth_domain}/oauth/token", json=payload, timeout=15.0
                )

                if response.status_code == 400:
                    # Bad request - likely invalid refresh token
                    error_data = (
                        response.json()
                        if response.headers.get("content-type", "").startswith("application/json")
                        else {}
                    )
                    error_desc = error_data.get("error_description", "Invalid refresh token")
                    logger.warning(f"Refresh token invalid: {error_desc}")
                    raise TokenExpiredError(f"Refresh token expired or invalid: {error_desc}")

                elif response.status_code == 429:
                    # Rate limited - should implement backoff
                    logger.warning("Rate limited during token refresh")
                    raise TokenError("Rate limited during token refresh. Please try again later.")

                elif response.status_code >= 500:
                    # Server error - temporary issue
                    logger.warning(f"Auth server error during refresh: {response.status_code}")
                    raise TokenError(
                        f"Auth server temporarily unavailable (HTTP {response.status_code})"
                    )

                # Raise for any other HTTP errors
                response.raise_for_status()
                return response.json()  # may include rotated refresh_token

        except httpx.TimeoutException:
            logger.warning("Timeout during token refresh")
            raise TokenError("Token refresh timed out. Please check your connection.")
        except httpx.NetworkError as e:
            logger.warning(f"Network error during token refresh: {e}")
            raise TokenError("Network error during token refresh. Please check your connection.")
        except (TokenError, TokenExpiredError):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.error(f"Unexpected error during token refresh: {e}")
            raise TokenError(f"Token refresh failed: {e}")

    async def _is_token_live_remote(self, access_token: str, auth_domain: str) -> bool:
        """Check token validity via Auth0 /userinfo endpoint."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://{auth_domain}/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=5.0,
                )
                return response.status_code == 200
        except Exception as e:
            logger.debug(f"Remote token validation failed: {e}")
            return False

    async def _validate_or_refresh(self, token_data: dict) -> dict:
        """Validate token using fast-path local verification with /userinfo fallback."""
        access_token = token_data["access_token"]

        from .config import get_static_config

        cfg = get_static_config()

        # Fast path: local JWT verification
        jwt_valid = verify_jwt_local(access_token, cfg.auth_domain, cfg.api_audience)

        if jwt_valid is True:
            logger.debug("Token validated locally")
            return token_data  # verified locally

        if jwt_valid is None:
            # Couldn't verify locally, try remote validation
            logger.debug("Local validation failed, trying remote")
            if await self._is_token_live_remote(access_token, cfg.auth_domain):
                logger.debug("Token validated remotely")
                return token_data

        # Token is invalid or expired - attempt refresh
        logger.info("Token invalid or expired, attempting refresh")
        new_token_data = await self._refresh_token(token_data)

        # Merge the new token data (may include rotated refresh_token) with existing data
        token_data.update(new_token_data)
        return token_data


# Legacy functions for backward compatibility
def load_user_token() -> str | None:
    """Load user token from cache."""
    token_file = Path.home() / ".barndoor" / "token.json"
    if not token_file.exists():
        return None

    try:
        with open(token_file) as f:
            data = json.load(f)
            return data.get("access_token")
    except Exception:
        return None


def save_user_token(token: str | dict) -> None:
    """Save user token to cache."""
    token_file = Path.home() / ".barndoor" / "token.json"
    token_file.parent.mkdir(parents=True, exist_ok=True)

    # Handle both string tokens and full token responses
    if isinstance(token, str):
        token_data = {"access_token": token}
    else:
        token_data = token

    with open(token_file, "w") as f:
        json.dump(token_data, f, indent=2)

    os.chmod(token_file, 0o600)


def clear_cached_token() -> None:
    """Clear the cached token file."""
    token_file = Path.home() / ".barndoor" / "token.json"
    if token_file.exists():
        try:
            token_file.unlink()
            logger.debug("Cached token cleared")
        except OSError as e:
            logger.warning(f"Failed to clear cached token: {e}")


async def is_token_active(base_url: str) -> bool:
    """Check if cached token is active without attempting refresh."""
    from .config import get_static_config

    token_file = Path.home() / ".barndoor" / "token.json"
    if not token_file.exists():
        return False

    try:
        with open(token_file) as f:
            token_data = json.load(f)
    except Exception:
        return False

    access_token = token_data.get("access_token")
    if not access_token:
        return False

    # Test the access token against Auth0
    try:
        cfg = get_static_config()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{cfg.auth_domain}/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
            return response.status_code == 200
    except Exception:
        return False


async def is_token_active_with_refresh(base_url: str) -> bool:
    """Check if cached token is active, attempting refresh if needed."""
    from .auth import refresh_access_token
    from .config import get_static_config

    token_file = Path.home() / ".barndoor" / "token.json"
    if not token_file.exists():
        return False

    try:
        with open(token_file) as f:
            token_data = json.load(f)
    except Exception:
        return False

    access_token = token_data.get("access_token")
    if not access_token:
        return False

    # First try the access token
    try:
        cfg = get_static_config()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{base_url}/api/identity/token",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
            if response.status_code == 200:
                return True
    except Exception:
        pass

    # If access token failed, try refresh
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return False

    try:
        cfg = get_static_config()
        new_token_data = refresh_access_token(
            refresh_token=refresh_token,
            client_id=cfg.client_id,
            client_secret=cfg.client_secret,
            domain=cfg.auth_domain,
        )

        # Merge with existing data to preserve any additional fields
        token_data.update(new_token_data)
        save_user_token(token_data)
        logger.info("Token refreshed successfully")
        return True

    except Exception as e:
        logger.warning(f"Token refresh failed: {e}")
        return False


async def validate_token(token: str, base_url: str) -> dict:
    """Validate a token using fast-path local verification with remote fallback.

    Parameters
    ----------
    token : str
        The JWT token to validate
    base_url : str
        Base URL of the Barndoor API (unused, kept for compatibility)

    Returns
    -------
    dict
        Dictionary with 'valid' key indicating if token is valid

    Notes
    -----
    This function uses local JWT verification first, then falls back to
    Auth0's /userinfo endpoint for validation.
    """
    from .config import get_static_config

    cfg = get_static_config()

    # Fast path: local JWT verification
    jwt_valid = verify_jwt_local(token, cfg.auth_domain, cfg.api_audience)

    if jwt_valid is True:
        return {"valid": True}

    if jwt_valid is None:
        # Couldn't verify locally, try remote validation
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://{cfg.auth_domain}/userinfo",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5.0,
                )
                return {"valid": response.status_code == 200}
        except Exception as e:
            logger.warning(f"Remote token validation failed: {e}")
            return {"valid": False}

    # Token is expired or invalid
    return {"valid": False}
