"""Simplified configuration management for the Barndoor SDK."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from jose import jwt
from pydantic import BaseModel, Field


class BarndoorConfig(BaseModel):
    """Unified configuration for the Barndoor SDK."""
    
    # Authentication
    auth_domain: str = Field(default="auth.barndoor.ai")
    client_id: str = Field(default="")
    client_secret: str = Field(default="")
    api_audience: str = Field(default="https://barndoor.ai/")
    
    # API endpoints (templates support {organization_id})
    api_base_url: str = Field(default="https://{organization_id}.mcp.barndoor.ai")
    mcp_base_url: str = Field(default="https://{organization_id}.mcp.barndoor.ai")
    
    # Runtime settings
    environment: str = Field(default="production")
    prompt_for_login: bool = Field(default=False)
    skip_login_local: bool = Field(default=False)
    
    # Organization-specific overrides (populated from JWT)
    organization_id: Optional[str] = Field(default=None)
    
    class Config:
        frozen = True

    @classmethod
    def from_environment(cls, token: Optional[str] = None) -> "BarndoorConfig":
        """Create configuration from environment variables and optional JWT token."""
        
        # Load environment variables
        env_mode = (os.getenv("MODE") or os.getenv("BARNDOOR_ENV", "production")).lower()
        
        # Base configuration from environment
        config_data = {
            "auth_domain": _get_env_var(["AUTH_DOMAIN", "AUTH0_DOMAIN"], "auth.barndoor.ai"),
            "client_id": _get_env_var(["AGENT_CLIENT_ID", "AUTH_CLIENT_ID"], ""),
            "client_secret": _get_env_var(["AGENT_CLIENT_SECRET", "AUTH_CLIENT_SECRET"], ""),
            "api_audience": os.getenv("API_AUDIENCE", "https://barndoor.ai/"),
            "environment": env_mode,
            "prompt_for_login": _get_bool("PROMPT_FOR_LOGIN", False),
            "skip_login_local": _get_bool("SKIP_LOGIN_LOCAL", False),
        }
        
        # Set environment-specific defaults
        if env_mode in ("localdev", "local"):
            config_data.update({
                "auth_domain": _get_env_var(["AUTH_DOMAIN"], "localhost:3001"),
                "api_base_url": os.getenv("BARNDOOR_API", "http://localhost:8000"),
                "mcp_base_url": os.getenv("BARNDOOR_URL", "http://localhost:8000"),
            })
        elif env_mode in ("development", "dev"):
            config_data.update({
                "api_base_url": os.getenv("BARNDOOR_API", "https://{organization_id}.mcp.barndoordev.com"),
                "mcp_base_url": os.getenv("BARNDOOR_URL", "https://{organization_id}.mcp.barndoordev.com"),
            })
        else:  # production
            config_data.update({
                "api_base_url": os.getenv("BARNDOOR_API", "https://{organization_id}.mcp.barndoor.ai"),
                "mcp_base_url": os.getenv("BARNDOOR_URL", "https://{organization_id}.mcp.barndoor.ai"),
            })
        
        # Apply JWT-based overrides if token provided
        if token:
            try:
                claims = jwt.get_unverified_claims(token)
                
                # Look for organization name in user claims first, then fallback to org_id
                org_name = None
                if user_claims := claims.get("user"):
                    org_name = user_claims.get("organization_name")
                
                if org_name:
                    config_data["organization_id"] = org_name
                    # Resolve URL templates
                    config_data["api_base_url"] = config_data["api_base_url"].format(organization_id=org_name)
                    config_data["mcp_base_url"] = config_data["mcp_base_url"].format(organization_id=org_name)
            except Exception as e:
                # Ignore JWT parsing errors - use defaults
                pass
        
        return cls(**config_data)

    def with_token(self, token: str) -> "BarndoorConfig":
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
_config: Optional[BarndoorConfig] = None


def get_config(token: Optional[str] = None, *, reload: bool = False) -> BarndoorConfig:
    """Get the global configuration instance."""
    global _config
    
    if _config is None or reload or token:
        _config = BarndoorConfig.from_environment(token)
    
    return _config


def load_dotenv_for_sdk(path: Optional[Path] = None, *, override: bool = False) -> None:
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
