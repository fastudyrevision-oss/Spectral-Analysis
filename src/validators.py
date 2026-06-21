# -*- coding: utf-8 -*-
"""
Input Validation for Spectral Analysis Software

Provides validation functions for all input data types.
"""

import numpy as np
import pandas as pd
from .config import VALIDATION_CONFIG
from .exceptions import DataValidationError


def validate_wavelength_intensity(wavelength: np.ndarray, 
                                   intensity: np.ndarray) -> bool:
    """
    Validate wavelength and intensity arrays.
    
    Parameters
    ----------
    wavelength : np.ndarray
        Wavelength array (nm)
    intensity : np.ndarray
        Intensity array
    
    Returns
    -------
    bool
        True if valid, raises exception otherwise
    
    Raises
    ------
    DataValidationError
        If data is invalid
    """
    # Type check
    if not isinstance(wavelength, np.ndarray):
        raise DataValidationError("wavelength must be numpy array")
    if not isinstance(intensity, np.ndarray):
        raise DataValidationError("intensity must be numpy array")
    
    # Length match
    if len(wavelength) != len(intensity):
        raise DataValidationError(
            f"wavelength and intensity must have same length: "
            f"{len(wavelength)} vs {len(intensity)}"
        )
    
    # Minimum points
    if len(wavelength) < VALIDATION_CONFIG['MIN_DATA_POINTS']:
        raise DataValidationError(
            f"Need at least {VALIDATION_CONFIG['MIN_DATA_POINTS']} data points, "
            f"got {len(wavelength)}"
        )
    
    # NaN/Inf check
    if np.any(np.isnan(wavelength)) or np.any(np.isinf(wavelength)):
        raise DataValidationError("wavelength contains NaN or Inf values")
    if np.any(np.isnan(intensity)) or np.any(np.isinf(intensity)):
        raise DataValidationError("intensity contains NaN or Inf values")
    
    # Monotonicity check
    if not np.all(np.diff(wavelength) > 0):
        raise DataValidationError("wavelength must be monotonically increasing")
    
    # Range check
    if np.min(wavelength) < VALIDATION_CONFIG['MIN_WAVELENGTH']:
        raise DataValidationError(
            f"wavelength below minimum: {np.min(wavelength)} < "
            f"{VALIDATION_CONFIG['MIN_WAVELENGTH']}"
        )
    if np.max(wavelength) > VALIDATION_CONFIG['MAX_WAVELENGTH']:
        raise DataValidationError(
            f"wavelength above maximum: {np.max(wavelength)} > "
            f"{VALIDATION_CONFIG['MAX_WAVELENGTH']}"
        )
    
    # Intensity range check
    if np.min(intensity) < VALIDATION_CONFIG['MIN_INTENSITY']:
        raise DataValidationError(
            f"intensity below minimum: {np.min(intensity)} < "
            f"{VALIDATION_CONFIG['MIN_INTENSITY']}"
        )
    if np.max(intensity) > VALIDATION_CONFIG['MAX_INTENSITY']:
        raise DataValidationError(
            f"intensity above maximum: {np.max(intensity)} > "
            f"{VALIDATION_CONFIG['MAX_INTENSITY']}"
        )
    
    return True


def validate_parameters(params: dict, param_names: list) -> bool:
    """
    Validate processing parameters.
    
    Parameters
    ----------
    params : dict
        Parameter dictionary
    param_names : list
        Required parameter names
    
    Returns
    -------
    bool
        True if valid
    
    Raises
    ------
    ConfigurationError
        If parameters invalid
    """
    for name in param_names:
        if name not in params:
            raise DataValidationError(f"Missing parameter: {name}")
    return True


def validate_csv_columns(df: pd.DataFrame, required_columns: list) -> bool:
    """
    Validate that CSV has required columns.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to validate
    required_columns : list
        List of required column names
    
    Returns
    -------
    bool
        True if valid
    
    Raises
    ------
    DataValidationError
        If columns missing
    """
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise DataValidationError(
            f"Missing columns: {missing}. Available: {list(df.columns)}"
        )
    return True
