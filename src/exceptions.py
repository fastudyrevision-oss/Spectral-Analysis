# -*- coding: utf-8 -*-
"""
Custom Exception Classes for Spectral Analysis Software

Provides specific exception types for different error scenarios.
"""


class SpectralAnalysisError(Exception):
    """Base exception for all spectral analysis errors."""
    pass


class DataValidationError(SpectralAnalysisError):
    """Raised when input data fails validation."""
    pass


class ConfigurationError(SpectralAnalysisError):
    """Raised when configuration parameters are invalid."""
    pass


class FileIOError(SpectralAnalysisError):
    """Raised when file reading/writing fails."""
    pass


class ProcessingError(SpectralAnalysisError):
    """Raised when algorithm execution fails."""
    pass


class ColumnDetectionError(SpectralAnalysisError):
    """Raised when required columns cannot be detected in data."""
    pass


class NISTMatchingError(SpectralAnalysisError):
    """Raised when NIST matching fails."""
    pass
