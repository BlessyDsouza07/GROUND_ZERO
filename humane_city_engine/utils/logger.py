"""
Central Logging System for Humane City Engine

Features
--------
• Console logging
• File logging
• Automatic log directory creation
• Log rotation to prevent huge files
• Configurable log levels
• Reusable across all modules
"""

import logging
import os
from logging.handlers import RotatingFileHandler


# Default log directory
LOG_DIR = "logs"


def _ensure_log_directory():
    """
    Ensure the log directory exists.
    """
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)


def get_logger(name: str, level=logging.INFO) -> logging.Logger:
    """
    Create and return a configured logger instance.

    Parameters
    ----------
    name : str
        Name of the logger (usually module or engine name)

    level : logging level
        Logging level (default INFO)

    Returns
    -------
    logging.Logger
        Configured logger object
    """

    _ensure_log_directory()

    logger = logging.getLogger(name)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Log format
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # File Handler with rotation
    file_path = os.path.join(LOG_DIR, f"{name}.log")

    file_handler = RotatingFileHandler(
        file_path,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=5
    )

    file_handler.setFormatter(formatter)

    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# Optional: global system logger
system_logger = get_logger("city_engine")