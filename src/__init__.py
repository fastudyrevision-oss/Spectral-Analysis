# -*- coding: utf-8 -*-
"""Spectral Analysis Software - Core package"""

from .config import (
    STEP1_PARAMS, STEP2_PARAMS, STEP3_PARAMS,
    OUTPUT_CONFIG, VALIDATION_CONFIG, LOGGING_CONFIG
)
from .logger import setup_logger
from .exceptions import (
    SpectralAnalysisError,
    DataValidationError,
    ConfigurationError,
    FileIOError,
    ProcessingError,
    ColumnDetectionError,
    NISTMatchingError
)
from .validators import (
    validate_wavelength_intensity,
    validate_parameters,
    validate_csv_columns
)

__version__ = "1.0.0"
__author__ = "Spectral Analysis Team"

__all__ = [
    'STEP1_PARAMS', 'STEP2_PARAMS', 'STEP3_PARAMS',
    'OUTPUT_CONFIG', 'VALIDATION_CONFIG', 'LOGGING_CONFIG',
    'setup_logger',
    'SpectralAnalysisError', 'DataValidationError', 'ConfigurationError',
    'FileIOError', 'ProcessingError', 'ColumnDetectionError', 'NISTMatchingError',
    'validate_wavelength_intensity', 'validate_parameters', 'validate_csv_columns'
]
