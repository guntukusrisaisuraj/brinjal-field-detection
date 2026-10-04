"""Centralised logging configuration using loguru."""
import os
import sys
from loguru import logger


def configure_logging(level: str = "INFO") -> None:
    # Ensure the logs directory exists (avoids FileNotFoundError on fresh clones)
    os.makedirs("logs", exist_ok=True)

    logger.remove()
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> – "
            "<level>{message}</level>"
        ),
        level=level,
        colorize=True,
    )
    logger.add(
        "logs/brinjal_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days",
        level="DEBUG",
        format="{time} | {level} | {name}:{function}:{line} – {message}",
    )


__all__ = ["logger", "configure_logging"]
