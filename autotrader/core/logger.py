"""Core logging setup module."""
from __future__ import annotations

import logging
import sys


def setup_logging(name: str, level: str = "INFO") -> logging.Logger:
    """Set up a logger with standard formatting.

    Creates or retrieves a logger with the given name and configures it
    with a stream handler that writes to stdout. If the logger already
    has handlers, no new handler is added.

    Args:
        name: Name for the logger (typically __name__ or module name).
        level: Log level as string (DEBUG, INFO, WARNING, ERROR).
               Defaults to "INFO".

    Returns:
        Configured Logger instance.

    Example:
        >>> log = setup_logging("myapp.module", level="DEBUG")
        >>> log.info("Application started")
    """
    logger = logging.getLogger(name)

    # Convert level string to logging level
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Only add handler if logger doesn't already have one
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
        )
        logger.addHandler(handler)

    return logger
