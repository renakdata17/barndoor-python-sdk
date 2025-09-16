"""Logging configuration for the Barndoor SDK."""

import logging
import sys


def setup_logging(
    level: str = "INFO",
    format_string: str | None = None,
    include_timestamp: bool = True,
) -> None:
    """Configure logging for the Barndoor SDK.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom format string
        include_timestamp: Whether to include timestamps
    """
    if format_string is None:
        if include_timestamp:
            format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        else:
            format_string = "%(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_string,
        stream=sys.stdout,
        force=True,
    )

    # Set SDK logger to be slightly more verbose
    sdk_logger = logging.getLogger("barndoor.sdk")
    sdk_logger.setLevel(logging.DEBUG if level.upper() == "DEBUG" else logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for the given module."""
    return logging.getLogger(f"barndoor.sdk.{name}")
