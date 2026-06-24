# -*- coding: utf-8 -*-
"""
Step 5: Validation with Reference Spectra

Compares processed spectra against pure reference spectra to validate
spectral processing and element identification through correlation analysis.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from scipy.interpolate import interp1d
from pathlib import Path

from src import (
    STEP5_PARAMS, setup_logger,
    ProcessingError
)


logger = setup_logger(__name__)


class ValidationAnalyzer:
    """
    Validates processed spectra against reference spectra.
    
    Features:
    - Spectral region extraction with windowing
    - Cross-spectrum interpolation and alignment
    - Correlation coefficient calculation
    - Line-by-line validation with confidence metrics
    - Batch processing for multiple elements
    """
    
    def __init__(self, config: dict = None):
        """
        Initialize validation analyzer.
        
        Parameters
        ----------
        config : dict, optional
            Configuration with keys:
            - WINDOW: search window around each line (nm)
            - MIN_POINTS: minimum data points required per region
            - INTERPOLATION_KIND: interpolation method ('linear', 'cubic')
            
            If None, uses defaults from STEP5_PARAMS
        """
        if config is None:
            config = STEP5_PARAMS
        
        self.window = float(config.get('WINDOW', 0.5))
        self.min_points = int(config.get('MIN_POINTS', 5))
        self.interp_kind = config.get('INTERPOLATION_KIND', 'linear')
        
        logger.info(f"ValidationAnalyzer initialized with:")
        logger.info(f"  WINDOW={self.window} nm, MIN_POINTS={self.min_points}")
        logger.info(f"  INTERPOLATION={self.interp_kind}")
    
    def validate_input(self, processed_df: pd.DataFrame,
                      reference_df: pd.DataFrame) -> bool:
        """
        Validate input spectra DataFrames.
        
        Parameters
        ----------
        processed_df : pd.DataFrame
            Processed spectrum data
        reference_df : pd.DataFrame
            Reference spectrum data
        
        Returns
        -------
        bool
            True if valid
        
        Raises
        ------
        ValidationError
            If validation fails
        """
        for name, df in [("Processed", processed_df), ("Reference", reference_df)]:
            if df is None or df.empty:
                raise ValidationError(f"{name} spectrum is empty")
            
            if df.shape[1] < 2:
                raise ValidationError(f"{name} spectrum has insufficient columns")
        
        logger.info(f"Input validation passed")
        return True
    
    @staticmethod
    def normalize_spectrum_columns(df: pd.DataFrame) -> pd.DataFrame:
        """
        Auto-detect and normalize spectrum column names.
        
        Parameters
        ----------
        df : pd.DataFrame
            Input spectrum data
        
        Returns
        -------
        pd.DataFrame
            DataFrame with normalized column names
        """
        df.columns = df.columns.str.strip()
        cols_lower = {col.lower(): col for col in df.columns}
        
        # Detect wavelength column
        wl_col = None
        for variant in ['wavelength', 'wl', 'wavelength (nm)', 'wave', 'lambda']:
            if variant in cols_lower:
                wl_col = cols_lower[variant]
                break
        
        # Detect intensity column
        int_col = None
        for variant in ['intensity', 'intensity (arb. u.)', 'counts', 'signal']:
            if variant in cols_lower:
                int_col = cols_lower[variant]
                break
        
        if wl_col is None or int_col is None:
            raise ValidationError("Cannot detect wavelength and/or intensity columns")
        
        # Create normalized DataFrame
        result = pd.DataFrame({
            'wavelength': df[wl_col],
            'intensity': df[int_col]
        })
        
        logger.info(f"Normalized columns: {wl_col} -> wavelength, {int_col} -> intensity")
        
        return result
    
    @staticmethod
    def validation_coefficient(processed: np.ndarray,
                               reference: np.ndarray) -> float:
        """
        Calculate correlation coefficient between two spectra.
        
        Uses Pearson correlation on normalized intensities.
        Handles edge cases (zero variance, mismatched lengths).
        
        Parameters
        ----------
        processed : np.ndarray
            Processed spectrum intensities
        reference : np.ndarray
            Reference spectrum intensities
        
        Returns
        -------
        float
            Correlation coefficient (-1 to 1), or NaN if undefined
        """
        p = np.asarray(processed, dtype=np.float64)
        r = np.asarray(reference, dtype=np.float64)
        
        # Handle length mismatch
        if len(p) != len(r):
            # Use minimum length for comparison
            min_len = min(len(p), len(r))
            p = p[:min_len]
            r = r[:min_len]
        
        # Handle empty or single-point data
        if len(p) < 2:
            return np.nan
        
        # Calculate means
        p_mean = np.mean(p)
        r_mean = np.mean(r)
        
        # Calculate covariance and standard deviations
        numerator = np.sum((p - p_mean) * (r - r_mean))
        denominator = np.sqrt(
            np.sum((p - p_mean)**2) * np.sum((r - r_mean)**2)
        )
        
        # Handle zero variance
        if denominator == 0:
            return np.nan
        
        correlation = numerator / denominator
        
        # Clamp to [-1, 1] to handle floating point errors
        return np.clip(correlation, -1.0, 1.0)
    
    def extract_region(self, spectrum: pd.DataFrame,
                      center_wavelength: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extract spectral region around target wavelength.
        
        Parameters
        ----------
        spectrum : pd.DataFrame
            Input spectrum with 'wavelength' and 'intensity' columns
        center_wavelength : float
            Center wavelength (nm)
        
        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            (wavelengths, intensities) in the region
        
        Raises
        ------
        ValidationError
            If insufficient data in region
        """
        wl_min = center_wavelength - self.window
        wl_max = center_wavelength + self.window
        
        region = spectrum[
            (spectrum['wavelength'] >= wl_min) &
            (spectrum['wavelength'] <= wl_max)
        ].copy()
        
        if len(region) < self.min_points:
            raise ValidationError(
                f"Insufficient data points ({len(region)}) for {center_wavelength} nm"
            )
        
        return region['wavelength'].values, region['intensity'].values
    
    def validate_line(self, processed: pd.DataFrame,
                     reference: pd.DataFrame,
                     line_wavelength: float) -> Dict:
        """
        Validate a single spectral line.
        
        Parameters
        ----------
        processed : pd.DataFrame
            Processed spectrum
        reference : pd.DataFrame
            Reference spectrum
        line_wavelength : float
            Target line wavelength (nm)
        
        Returns
        -------
        Dict with keys:
            - 'wavelength': line wavelength
            - 'validation_coefficient': correlation coefficient
            - 'processed_intensity': processed spectrum intensities
            - 'reference_intensity': reference spectrum intensities
            - 'processed_wl': processed spectrum wavelengths
            - 'reference_wl': reference spectrum wavelengths
        
        Raises
        ------
        ValidationError
            If validation fails
        """
        try:
            # Extract regions
            p_wl, p_int = self.extract_region(processed, line_wavelength)
            r_wl, r_int = self.extract_region(reference, line_wavelength)
            
            # Interpolate reference to processed wavelength grid
            interp_func = interp1d(
                r_wl, r_int,
                kind=self.interp_kind,
                fill_value="extrapolate"
            )
            r_int_interp = interp_func(p_wl)
            
            # Normalize intensities
            p_int_norm = p_int / np.max(np.abs(p_int)) if np.max(np.abs(p_int)) > 0 else p_int
            r_int_norm = r_int_interp / np.max(np.abs(r_int_interp)) if np.max(np.abs(r_int_interp)) > 0 else r_int_interp
            
            # Calculate correlation
            vc = self.validation_coefficient(p_int_norm, r_int_norm)
            
            logger.info(f"Validated line {line_wavelength} nm: VC = {vc:.4f}")
            
            return {
                'wavelength': line_wavelength,
                'validation_coefficient': vc,
                'processed_intensity': p_int_norm,
                'reference_intensity': r_int_norm,
                'processed_wl': p_wl,
                'reference_wl': r_wl,
                'normalized': True
            }
        
        except ValidationError as e:
            logger.warning(f"Line {line_wavelength} nm validation failed: {e}")
            return {
                'wavelength': line_wavelength,
                'validation_coefficient': np.nan,
                'error': str(e)
            }
    
    def validate_spectrum(self, processed: pd.DataFrame,
                         reference: pd.DataFrame,
                         target_lines: List[float]) -> pd.DataFrame:
        """
        Validate processed spectrum against reference for multiple lines.
        
        Parameters
        ----------
        processed : pd.DataFrame
            Processed spectrum
        reference : pd.DataFrame
            Reference spectrum
        target_lines : List[float]
            List of line wavelengths (nm) to validate
        
        Returns
        -------
        pd.DataFrame
            Validation results for all lines
        
        Raises
        ------
        ValidationError
            If input validation fails
        """
        # Normalize column names
        processed = self.normalize_spectrum_columns(processed)
        reference = self.normalize_spectrum_columns(reference)
        
        # Validate input
        self.validate_input(processed, reference)
        
        # Process each line
        results = []
        for line_wl in target_lines:
            result = self.validate_line(processed, reference, line_wl)
            results.append({
                'Wavelength_nm': result['wavelength'],
                'Validation_Coefficient': result.get('validation_coefficient', np.nan),
                'Status': 'Success' if 'error' not in result else f"Failed: {result['error']}"
            })
        
        # Create results DataFrame
        results_df = pd.DataFrame(results)
        
        # Calculate summary statistics
        valid_vc = results_df[results_df['Validation_Coefficient'].notna()]['Validation_Coefficient']
        
        if not valid_vc.empty:
            logger.info(f"Validation summary:")
            logger.info(f"  Mean VC: {valid_vc.mean():.4f}")
            logger.info(f"  Median VC: {valid_vc.median():.4f}")
            logger.info(f"  Min VC: {valid_vc.min():.4f}")
            logger.info(f"  Max VC: {valid_vc.max():.4f}")
        
        return results_df
    
    def validate_batch(self, processed: pd.DataFrame,
                      reference_dict: Dict[str, pd.DataFrame],
                      target_lines_dict: Dict[str, List[float]]) -> Dict[str, pd.DataFrame]:
        """
        Validate against multiple reference spectra (batch processing).
        
        Parameters
        ----------
        processed : pd.DataFrame
            Single processed spectrum
        reference_dict : Dict[str, pd.DataFrame]
            Dictionary of reference spectra {element_name: dataframe}
        target_lines_dict : Dict[str, List[float]]
            Dictionary of target lines {element_name: [wavelengths]}
        
        Returns
        -------
        Dict[str, pd.DataFrame]
            Validation results {element_name: results_df}
        """
        batch_results = {}
        
        for element, reference in reference_dict.items():
            target_lines = target_lines_dict.get(element, [])
            
            if not target_lines:
                logger.warning(f"No target lines for {element}")
                continue
            
            logger.info(f"Validating {element} with {len(target_lines)} lines")
            
            try:
                results_df = self.validate_spectrum(
                    processed, reference, target_lines
                )
                batch_results[element] = results_df
            except ValidationError as e:
                logger.error(f"Batch validation failed for {element}: {e}")
        
        logger.info(f"Batch validation completed for {len(batch_results)} elements")
        
        return batch_results


class ValidationError(ProcessingError):
    """Raised when validation analysis fails."""
    pass
