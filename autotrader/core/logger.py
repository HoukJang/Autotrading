"""Core logging setup module."""
from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


_LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"


def setup_logging(
    name: str,
    level: str = "INFO",
    log_dir: str | None = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    if not logger.handlers:
        # Console handler
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(console)

        # File handler with daily rolling
        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            file_handler = TimedRotatingFileHandler(
                filename=log_path / f"{name}.log",
                when="midnight",
                backupCount=30,
                encoding="utf-8",
            )
            file_handler.suffix = "%Y-%m-%d"
            file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
            logger.addHandler(file_handler)

    return logger
