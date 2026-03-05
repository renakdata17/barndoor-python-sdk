"""Simplified configuration management for the Barndoor SDK."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from jose import jwt
from pydantic import BaseModel, Field

# Baked-in auth configuration per environment
# Users should NOT need to configure these - just set BARNDOOR_ENV
#
# We have 6 environments: 3 for trial (Keycloak), 3 for enterprise (Auth0)
# Will consolidate in the future.
AUTH_CONFIG = {
    # === Trial environments (Keycloak) - DEFAULT ===
    "production": {
        "issuer": "https://auth.trial.barndoor.ai/realms/barndoor",
        "audience": "https://barndoor.ai/",
        "base_url": "https://{org_slug}.platform.barndoor.ai",
    },
    "uat": {
        "issuer": "https://auth.barndooruat.com/realms/barndoor",
        "audience": "https://barndoor.ai/",
        "base_url": "https://{org_slug}.trial.barndooruat.com",
    },
    "dev": {
        "issuer": "https://auth.barndoordev.com/realms/barndoor",
        "audience": "https://barndoor.ai/",
        "base_url": "https://{org_slug}.platform.barndoordev.com",
    },
    # === Enterprise environments (Auth0) ===
    "enterprise-production": {
        "issuer": "https://auth.barndoor.ai",
        "audience": "https://barndoor.ai/",
        "base_url": "https://{org_slug}.mcp.barndoor.ai",
    },
    "enterprise-uat": {
        "issuer": "https://auth.barndooruat.com",
        "audience": "https://barndoor.ai/",
        "base_url": "https://{org_slug}.mcp.barndooruat.com",
    },
    "enterprise-dev": {
        "issuer": "https://auth.barndoordev.com",
        "audience": "https://barndoor.ai/",
        "base_url": "https://{org_slug}.mcp.barndoordev.com",
    },
    # === Local development (Keycloak) ===
    "localdev": {
        "issuer": "http://localhost:8080/realms/barndoor",
        "audience": "https://barndoor.ai/",
        "base_url": "http://localhost:8000",
    },
}


class BarndoorConfig(BaseModel):
    """Unified configuration for the Barndoor SDK."""

    # Authentication - issuer is the full OIDC issuer URL
    # Defaults match AUTH_CONFIG["production"] (trial/Keycloak)
    auth_issuer: str = Field(default="https://auth.trial.barndoor.ai/realms/barndoor")
    client_id: str = Field(default="")
    client_secret: str = Field(default="")
    api_audience: str = Field(default="https://barndoor.ai/")

    # API endpoints (templates support {org_slug})
    base_url: str = Field(default="https://{org_slug}.platform.barndoor.ai")

    # Runtime settings
    environment: str = Field(default="production")
    prompt_for_login: bool = Field(default=False)
    skip_login_local: bool = Field(default=False)

    # Organization-specific overrides (populated from JWT)
    organization_id: str | None = Field(default=None)

    class Config:
        frozen = True

    # Backwards-compatible aliases (read-only)
    @property
    def auth_domain(self) -> str:
        """Extract domain from issuer URL for backwards compatibility."""
        # Remove protocol and path to get just the domain
        issuer = self.auth_issuer
        if issuer.startswith("https://"):
            issuer = issuer[8:]
        elif issuer.startswith("http://"):
            issuer = issuer[7:]
        # Return domain + path (needed for Keycloak realms)
        return issuer

    @property
    def AUTH_DOMAIN(self) -> str:
        return self.auth_domain

    @property
    def API_AUDIENCE(self) -> str:
        return self.api_audience

    @property
    def PROMPT_FOR_LOGIN(self) -> bool:
        return self.prompt_for_login

    @property
    def AGENT_CLIENT_ID(self) -> str:
        return self.client_id

    @property
    def AGENT_CLIENT_SECRET(self) -> str:
        return self.client_secret

    @classmethod
    def from_environment(cls, token: str | None = None) -> BarndoorConfig:
        """Create configuration from environment variables and optional JWT token."""

        # Load environment variables
        # Determine environment mode with pragmatic precedence:
        # - If BARNDOOR_ENV explicitly sets production/prod, prefer it over MODE
        # - Else prefer MODE when set
        # - Else fall back to BARNDOOR_ENV when set
        # - Else default to production
        be = os.getenv("BARNDOOR_ENV")
        md = os.getenv("MODE")
        if be and be.strip().lower() in ("production", "prod"):
            env_mode = be.strip().lower()
        elif md:
            env_mode = md.strip().lower()
        elif be:
            env_mode = be.strip().lower()
        else:
            env_mode = "production"

        # Normalize environment mode
        # Trial is the default - enterprise requires explicit prefix
        env_mode_map = {
            # Trial (default)
            "production": "production",
            "prod": "production",
            "uat": "uat",
            "dev": "dev",
            "development": "dev",
            # Enterprise (requires prefix)
            "enterprise-production": "enterprise-production",
            "enterprise-prod": "enterprise-production",
            "enterprise-uat": "enterprise-uat",
            "enterprise-dev": "enterprise-dev",
            "enterprise": "enterprise-production",  # Default enterprise to prod
            # Local
            "localdev": "localdev",
            "local": "localdev",
        }
        env_mode = env_mode_map.get(env_mode, "production")

        # Get baked-in auth config for this environment
        auth_cfg = AUTH_CONFIG.get(env_mode, AUTH_CONFIG["production"])

        # Base configuration - auth is baked in, with optional override via AUTH_URL
        config_data = {
            "auth_issuer": os.getenv("AUTH_URL", auth_cfg["issuer"]),
            "client_id": _get_env_var(["AGENT_CLIENT_ID", "AUTH_CLIENT_ID"], ""),
            "client_secret": _get_env_var(["AGENT_CLIENT_SECRET", "AUTH_CLIENT_SECRET"], ""),
            "api_audience": os.getenv("API_AUDIENCE", auth_cfg["audience"]),
            "environment": env_mode,
            "prompt_for_login": _get_bool("PROMPT_FOR_LOGIN", False),
            "skip_login_local": _get_bool("SKIP_LOGIN_LOCAL", False),
        }

        # Set base_url from config, with optional override
        config_data["base_url"] = os.getenv("BARNDOOR_URL", auth_cfg["base_url"])

        # Apply JWT-based overrides if token provided
        if token:
            try:
                claims = jwt.get_unverified_claims(token)

                # Look for organization name in user claims first,
                # then at top level, then fallback to org_id
                org_name = None
                if user_claims := claims.get("user"):
                    org_name = user_claims.get("organization_name")

                # If not found in user claims, check top level
                if not org_name:
                    org_name = claims.get("organization_name")

                if org_name:
                    config_data["organization_id"] = org_name
                    # Resolve URL templates
                    config_data["base_url"] = config_data["base_url"].format(org_slug=org_name)
            except Exception:
                # Ignore JWT parsing errors - use defaults
                pass

        return cls(**config_data)

    def with_token(self, token: str) -> BarndoorConfig:
        """Return a new config instance with JWT-based overrides applied."""
        return self.from_environment(token)


def _get_env_var(keys: list[str], default: str = "") -> str:
    """Get first available environment variable from a list of keys."""
    for key in keys:
        if value := os.getenv(key):
            return value
    return default


def _get_bool(key: str, default: bool = False) -> bool:
    """Get boolean environment variable."""
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Global configuration instance
_config: BarndoorConfig | None = None


def get_config(token: str | None = None, *, reload: bool = False) -> BarndoorConfig:
    """Get the global configuration instance."""
    global _config

    if _config is None or reload or token:
        _config = BarndoorConfig.from_environment(token)

    return _config


def load_dotenv_for_sdk(path: Path | None = None, *, override: bool = False) -> None:
    """Load environment variables from .env file."""
    if path is None:
        mode = os.getenv("MODE", os.getenv("BARNDOOR_ENV", "localdev")).lower()
        env_files = {
            "localdev": ".env.localdev",
            "local": ".env.localdev",
            "development": ".env.development",
            "dev": ".env.development",
            "production": ".env.production",
            "prod": ".env.production",
        }
        path = Path.cwd() / env_files.get(mode, ".env.localdev")

        # If the environment-specific file doesn't exist, try the default .env file
        if not path.exists():
            default_env = Path.cwd() / ".env"
            if default_env.exists():
                path = default_env

    if path.exists():
        load_dotenv(path, override=override)


def get_static_config() -> BarndoorConfig:
    """Get static configuration without JWT-based overrides."""
    return BarndoorConfig.from_environment(token=None)


def get_dynamic_config(token: str) -> BarndoorConfig:
    """Get configuration with JWT-based overrides applied."""
    return BarndoorConfig.from_environment(token=token)
