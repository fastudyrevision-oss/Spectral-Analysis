# -*- coding: utf-8 -*-
"""
Logging Configuration for Spectral Analysis Software

Sets up logging with both file and console output.
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from .config import LOGGING_CONFIG


def _writable_log_path() -> str:
    """
    Return a writable path for the log file.

    - Frozen (installed exe) → %APPDATA%\\LIBS_Analysis\\spectral_analysis.log
    - Development            → log file beside the launcher (current behaviour)
    """
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            log_dir = Path(appdata) / "LIBS_Analysis"
            log_dir.mkdir(parents=True, exist_ok=True)
            return str(log_dir / "spectral_analysis.log")
    return LOGGING_CONFIG["LOG_FILE"]  # relative — fine for dev


def setup_logger(name: str) -> logging.Logger:
    """
    Set up logger with console and file handlers.
    
    Parameters
    ----------
    name : str
        Logger name (typically __name__ of calling module)
    
    Returns
    -------
    logging.Logger
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Set level
    log_level = getattr(logging, LOGGING_CONFIG['LOG_LEVEL'])
    logger.setLevel(log_level)
    
    # Create formatters
    formatter = logging.Formatter(LOGGING_CONFIG['LOG_FORMAT'])
    
    # File handler
    try:
        file_handler = logging.FileHandler(_writable_log_path())
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not create file logger: {e}")
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger
