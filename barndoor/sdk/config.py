from __future__ import annotations

"""Centralized configuration management for the Barndoor SDK.

This module consolidates all environment variable handling so the rest of the
code base never calls ``os.getenv`` directly.  Configuration is exposed in two
layers that mirror the extension example shared by the user:

1. Static configuration – loaded from .env* files **once at import-time** and
   represented by the immutable ``AppConfig`` model (tree-shakable, safe to
   cache).
2. Dynamic configuration – per-tenant overrides derived from the JWT after the
   user logs in (organization-specific URLs, custom API audiences, …).

Only this file (plus ``dynamic_config`` below) should ever look at the process
environment.  Everywhere else simply call :pyfunc:`get_static_config` or
:pyfunc:`get_dynamic_config`.
"""

from pathlib import Path
import os
from typing import Optional

from dotenv import load_dotenv
from jose import jwt  # python-jose is already declared in pyproject
from pydantic import BaseModel

# Public API ----------------------------------------------------------------

__all__ = [
    "AppConfig",
    "load_dotenv_for_sdk",
    "get_static_config",
    "reload_static_config",
    "get_dynamic_config",
]

# ---------------------------------------------------------------------------
# 1. Optional dotenv loading (no side-effects by default)
# ---------------------------------------------------------------------------

_dotenv_loaded = False


def _default_dotenv_path() -> Path:
    mode = os.getenv("MODE") or os.getenv("BARNDOOR_ENV", "localdev").lower()
    mapping = {
        "localdev": ".env.localdev",
        "local": ".env.localdev",
        "development": ".env.development",
        "dev": ".env.development",
        "production": ".env.production",
        "prod": ".env.production",
    }
    return Path.cwd() / mapping.get(mode, ".env.localdev")


def load_dotenv_for_sdk(path: Path | None = None, *, override: bool = False) -> None:
    """Load a dotenv file exactly once for this process."""

    global _dotenv_loaded
    if _dotenv_loaded:
        return

    p = Path(path) if path else _default_dotenv_path()
    if p.exists():
        load_dotenv(p, override=override)

    _dotenv_loaded = True

# ---------------------------------------------------------------------------
# 2. Static configuration (lazy)
# ---------------------------------------------------------------------------


def _bool(key: str, default: bool = False) -> bool:
    """Return ``key`` from env as boolean (truthy/falsey strings accepted)."""
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


class AppConfig(BaseModel):
    """All configuration values that never change during a Python session."""

    AUTH_DOMAIN: str = "auth.barndoor.ai"
    AGENT_CLIENT_ID: str = ""
    AGENT_CLIENT_SECRET: str = ""

    API_AUDIENCE: str = "https://barndoor.api/"
    BARNDOOR_API: str = "https://api.barndoor.ai"  # Registry / Identity API
    BARNDOOR_URL: str = "https://{organization_id}.mcp.barndoor.ai"  # MCP base URL template

    PROMPT_FOR_LOGIN: bool = False
    SKIP_LOGIN_LOCAL: bool = False

    class Config:
        frozen = True  # make the model immutable


def _build_static_config() -> AppConfig:
    """(Re)construct the static configuration from the current environment."""

    def _getenv_any(keys: list[str], default: str) -> str:
        for k in keys:
            val = os.getenv(k)
            if val is not None:
                return val
        return default

    defaults = AppConfig()  # instance with built-in default values

    # ------------------------------------------------------------------
    # Choose sensible *template* defaults when the variables are absent.
    # These match the ingress rules documented in the Registry README.
    # ------------------------------------------------------------------

    mode = (os.getenv("MODE") or os.getenv("BARNDOOR_ENV", "localdev")).lower()

    if mode in {"production", "prod"}:
        _api_default = "https://{organization_id}.mcp.barndoor.ai"
        _url_default = _api_default
    elif mode in {"development", "dev"}:
        _api_default = "https://{organization_id}.mcp.barndoordev.com"
        _url_default = _api_default
    else:  # local development
        _api_default = "https://{organization_id}.mcp.barndoor.ai"
        _url_default = _api_default

    return AppConfig(
        AUTH_DOMAIN=_getenv_any(["AUTH_DOMAIN", "AUTH0_DOMAIN", "LOGIN_AUTH_DOMAIN"], defaults.AUTH_DOMAIN),
        AGENT_CLIENT_ID=_getenv_any(["AGENT_CLIENT_ID", "AUTH_CLIENT_ID"], defaults.AGENT_CLIENT_ID),
        AGENT_CLIENT_SECRET=_getenv_any(["AGENT_CLIENT_SECRET", "AUTH_CLIENT_SECRET"], defaults.AGENT_CLIENT_SECRET),
        API_AUDIENCE=os.getenv("API_AUDIENCE", defaults.API_AUDIENCE),
        BARNDOOR_API=os.getenv("BARNDOOR_API", _api_default),
        BARNDOOR_URL=os.getenv("BARNDOOR_URL", _url_default),
        PROMPT_FOR_LOGIN=_bool("PROMPT_FOR_LOGIN", defaults.PROMPT_FOR_LOGIN),
        SKIP_LOGIN_LOCAL=_bool("SKIP_LOGIN_LOCAL", defaults.SKIP_LOGIN_LOCAL),
    )


_static_config: AppConfig | None = None


def get_static_config(*, reload: bool = False) -> AppConfig:
    """Return session-wide immutable configuration.

    If *reload* is True the static config is rebuilt from the *current* env.
    """

    global _static_config
    if _static_config is None or reload:
        _static_config = _build_static_config()

    return _static_config


# Alias so callers can explicitly refresh without kwargs
reload_static_config = get_static_config  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 3. Runtime (dynamic) – per-tenant overrides from the JWT
# ---------------------------------------------------------------------------


def _apply_token_overrides(cfg: AppConfig, token: str) -> AppConfig:
    """Patch organization-specific settings (BarnDoor URLs, audiences, …)."""

    try:
        claims = jwt.get_unverified_claims(token)
    except Exception:  # pragma: no cover – any error → ignore overrides
        return cfg

    # 1) BarnDoor base URL – replace {organization_id} placeholder

    def _extract_slug(claims_dict: dict) -> str | None:
        # common variations seen in tokens
        possible_keys = [
            "organization_slug",
            "organization_name",  # e.g. barndoor-ai
            "org",
            "org_slug",
            "org_name",
        ]
        for k in possible_keys:
            if k in claims_dict and isinstance(claims_dict[k], str):
                return claims_dict[k]
        # nested user object as in access-token example
        user_part = claims_dict.get("user")
        if isinstance(user_part, dict):
            for k in possible_keys:
                v = user_part.get(k)
                if isinstance(v, str):
                    return v
            # organisation inside user
            if "organization_name" in user_part and isinstance(user_part["organization_name"], str):
                return user_part["organization_name"]
        return None

    org_slug: Optional[str] = _extract_slug(claims)
    # Handle nested { org: { slug: … } } object
    if org_slug is None and isinstance(claims.get("org"), dict):
        org_slug = claims["org"].get("slug")  # type: ignore[arg-type]

    barn_url = cfg.BARNDOOR_URL
    if org_slug and "{organization_id}" in barn_url:
        barn_url = barn_url.replace("{organization_id}", org_slug)

    api_base = cfg.BARNDOOR_API
    if org_slug and "{organization_id}" in api_base:
        api_base = api_base.replace("{organization_id}", org_slug)

    # 2) API audience – honour custom aud claim if present
    audience = claims.get("aud", cfg.API_AUDIENCE)

    return cfg.model_copy(update={"BARNDOOR_URL": barn_url, "BARNDOOR_API": api_base, "API_AUDIENCE": audience})


def get_dynamic_config(token: str | None = None) -> AppConfig:
    """Return configuration merged with per-tenant overrides.

    If *token* is omitted, the function tries to load the cached user token from
    :pyfunc:`barndoor.sdk.auth_store.load_user_token`.  When no token is
    available (user not logged-in yet) the static config is returned.
    """

    if token is None:
        try:
            from barndoor.sdk.auth_store import load_user_token

            token = load_user_token()
        except Exception:  # pragma: no cover – avoid circular import issues
            token = None

    cfg = get_static_config()

    if not token:
        return cfg

    return _apply_token_overrides(cfg, token) 