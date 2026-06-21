# -*- coding: utf-8 -*-
"""
Logging Configuration for Spectral Analysis Software

Sets up logging with both file and console output.
"""

import logging
import logging.handlers
from .config import LOGGING_CONFIG


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
        file_handler = logging.FileHandler(LOGGING_CONFIG['LOG_FILE'])
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
