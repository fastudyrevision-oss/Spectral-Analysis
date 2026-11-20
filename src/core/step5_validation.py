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
import re

from src import (
    STEP5_PARAMS, setup_logger,
    ProcessingError
)


logger = setup_logger(__name__)


def extract_element_symbol(name_or_filename: str) -> str:
    """
    Extract standard elemental symbol from a filename or element string.
    
    Examples:
        'Al.csv' -> 'Al'
        'Fe-Cl2.csv' -> 'Fe'
        'SG_ALS_LIBS_processed (Fe).csv' -> 'Fe'
        'Mn_I.csv' -> 'Mn'
        'Ca II' -> 'Ca'
    """
    base = Path(str(name_or_filename)).stem.strip()
    bracket_match = re.search(r'\(([A-Z][a-z]?)\)', base)
    if bracket_match:
        return bracket_match.group(1)
    prefix_match = re.match(r'^([A-Z][a-z]?)', base)
    if prefix_match:
        return prefix_match.group(1)
    return base


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
            DataFrame with normalized column names ('wavelength' and 'intensity')
        """
        if df is None or df.empty:
            raise ValidationError("Spectrum data is empty")

        df = df.copy()
        df.columns = df.columns.astype(str).str.strip()
        cols_lower = {col.lower(): col for col in df.columns}
        
        # 1. Detect wavelength column
        wl_col = None
        wl_variants = [
            'wavelength', 'wavelength (nm)', 'wavelength(nm)', 'wavelength [nm]', 'wavelength/nm',
            'wl', 'wl (nm)', 'wl(nm)', 'wave', 'lambda', 'x',
        ]
        for variant in wl_variants:
            if variant in cols_lower:
                wl_col = cols_lower[variant]
                break
        
        if wl_col is None:
            # Substring fallback for wavelength
            for col_l, orig in cols_lower.items():
                if 'wavelength' in col_l or col_l.startswith('wl') or 'lambda' in col_l:
                    wl_col = orig
                    break
        
        # 2. Detect intensity column
        int_col = None
        int_variants = [
            'corrected', 'corrected_intensity', 'corrected intensity', 'corrected_intens',
            'intensity', 'intensity (arb. u.)', 'intensity (a.u.)', 'intensity(a.u.)',
            'intensity (counts)', 'intensity/a.u.', 'intensity [a.u.]', 'intensity [counts]',
            'counts', 'signal', 'raw', 'smoothed_sg', 'data', 'y', 'val', 'value',
            'relative_intensity', 'rel_intensity', 'rel intensity', 'realtive_intensity',
        ]
        for variant in int_variants:
            if variant in cols_lower:
                int_col = cols_lower[variant]
                break
        
        if int_col is None:
            # Substring fallback for intensity
            for key in ['correct', 'intens', 'count', 'signal', 'smooth', 'raw', 'data', 'val']:
                for col_l, orig in cols_lower.items():
                    if orig != wl_col and key in col_l:
                        int_col = orig
                        break
                if int_col is not None:
                    break
        
        # 3. Positional fallback: if at least 2 columns exist
        if (wl_col is None or int_col is None) and df.shape[1] >= 2:
            num_cols = [c for c in df.columns if pd.to_numeric(df[c], errors='coerce').notna().sum() > 0]
            if len(num_cols) >= 2:
                if wl_col is None and int_col is None:
                    wl_col = num_cols[0]
                    int_col = num_cols[1]
                elif wl_col is None:
                    candidates = [c for c in num_cols if c != int_col]
                    if candidates:
                        wl_col = candidates[0]
                elif int_col is None:
                    candidates = [c for c in num_cols if c != wl_col]
                    if candidates:
                        int_col = candidates[0]

        if wl_col is None or int_col is None:
            raise ValidationError(f"Cannot detect wavelength and/or intensity columns from columns: {list(df.columns)}")
        
        # Create normalized DataFrame with numeric conversion
        result = pd.DataFrame({
            'wavelength': pd.to_numeric(df[wl_col], errors='coerce'),
            'intensity': pd.to_numeric(df[int_col], errors='coerce')
        }).dropna()
        
        logger.info(f"Normalized columns: {wl_col} -> wavelength, {int_col} -> intensity ({len(result)} valid rows)")
        
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
                     line_wavelength: float,
                     align_lag: bool = False,
                     max_lag: float = 0.10) -> Dict:
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
        align_lag : bool, default False
            If True, searches for peak shift within [-max_lag, max_lag] that maximizes VC.
        max_lag : float, default 0.10
            Maximum alignment search range (nm).
        
        Returns
        -------
        Dict with keys:
            - 'wavelength': line wavelength
            - 'validation_coefficient': correlation coefficient
            - 'peak_shift_nm': detected wavelength shift (nm)
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
            
            # Calculate base correlation
            vc = self.validation_coefficient(p_int_norm, r_int_norm)
            best_vc = vc
            best_shift = 0.0
            best_r_norm = r_int_norm

            # Optional peak alignment search across ±max_lag
            if align_lag and max_lag > 0 and len(p_wl) > 1:
                shifts = np.linspace(-max_lag, max_lag, 21)
                for s in shifts:
                    if s == 0.0:
                        continue
                    try:
                        shifted_p_wl = p_wl + s
                        shifted_r_int = interp_func(shifted_p_wl)
                        shifted_r_norm = shifted_r_int / np.max(np.abs(shifted_r_int)) if np.max(np.abs(shifted_r_int)) > 0 else shifted_r_int
                        c = self.validation_coefficient(p_int_norm, shifted_r_norm)
                        if not np.isnan(c) and (np.isnan(best_vc) or c > best_vc):
                            best_vc = c
                            best_shift = float(s)
                            best_r_norm = shifted_r_norm
                    except Exception:
                        pass
            
            logger.info(f"Validated line {line_wavelength} nm: VC = {best_vc:.4f} (shift={best_shift:+.3f} nm)")
            
            return {
                'wavelength': line_wavelength,
                'validation_coefficient': best_vc,
                'peak_shift_nm': best_shift,
                'processed_intensity': p_int_norm,
                'reference_intensity': best_r_norm,
                'processed_wl': p_wl,
                'reference_wl': r_wl,
                'normalized': True
            }
        
        except ValidationError as e:
            logger.warning(f"Line {line_wavelength} nm validation failed: {e}")
            return {
                'wavelength': line_wavelength,
                'validation_coefficient': np.nan,
                'peak_shift_nm': 0.0,
                'error': str(e)
            }
    
    def validate_spectrum(self, processed: pd.DataFrame,
                         reference: pd.DataFrame,
                         target_lines: List[float],
                         align_lag: bool = False,
                         max_lag: float = 0.10) -> pd.DataFrame:
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
        align_lag : bool, default False
            Whether to optimize for minor peak wavelength shifts (±max_lag).
        max_lag : float, default 0.10
            Maximum alignment search window (nm).
        
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
            result = self.validate_line(processed, reference, line_wl, align_lag=align_lag, max_lag=max_lag)
            results.append({
                'Wavelength_nm': result['wavelength'],
                'Validation_Coefficient': result.get('validation_coefficient', np.nan),
                'Peak_Shift_nm': result.get('peak_shift_nm', 0.0),
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
    
    def validate_element_spectra(
        self,
        processed: pd.DataFrame,
        element_reference_dict: Dict[str, pd.DataFrame],
        element_lines_dict: Dict[str, List[float]],
        reference_filenames: Optional[Dict[str, str]] = None,
        align_lag: bool = False,
        max_lag: float = 0.10
    ) -> Tuple[pd.DataFrame, List[Dict]]:
        """
        Validate spectral lines against element-matched pure reference spectra.
        Each element's lines are validated ONLY against that element's reference file,
        preventing cross-element spectrum concatenation artifacts.

        Parameters
        ----------
        processed : pd.DataFrame
            Processed spectrum.
        element_reference_dict : Dict[str, pd.DataFrame]
            Dictionary mapping element symbol (or name) to pure reference spectrum DataFrame.
        element_lines_dict : Dict[str, List[float]]
            Dictionary mapping element symbol (or name) to list of target line wavelengths (nm).
        reference_filenames : Dict[str, str], optional
            Optional mapping of element symbol to original reference filename.
        align_lag : bool, default False
            Whether to optimize for minor peak wavelength shifts (±max_lag).
        max_lag : float, default 0.10
            Maximum alignment lag search window (nm).

        Returns
        -------
        Tuple[pd.DataFrame, List[Dict]]
            - results_df: DataFrame with columns:
                ['Wavelength_nm', 'Element', 'Reference_File', 'Validation_Coefficient', 'Peak_Shift_nm', 'Tier', 'Status']
            - line_details: List of per-line detail dictionaries with overlay arrays.
        """
        proc_norm = self.normalize_spectrum_columns(processed)
        ref_filenames = reference_filenames or {}

        # Normalize reference DataFrames and index by multiple key variations
        norm_ref = {}
        for key, ref_df in element_reference_dict.items():
            if ref_df is None or ref_df.empty:
                continue
            try:
                ndf = self.normalize_spectrum_columns(ref_df)
                sym = extract_element_symbol(key)
                fname = ref_filenames.get(key, ref_filenames.get(sym, Path(str(key)).name if '.' in str(key) else f"{sym}.csv"))
                norm_ref[sym] = (ndf, fname, sym)
                norm_ref[sym.upper()] = (ndf, fname, sym)
                norm_ref[key] = (ndf, fname, sym)
                norm_ref[key.lower()] = (ndf, fname, sym)
            except Exception as e:
                logger.warning(f"Could not normalize reference spectrum for {key}: {e}")

        results = []
        line_details = []

        def _classify_tier(vc_val: float) -> str:
            if np.isnan(vc_val):
                return "Failed"
            if vc_val >= 0.80:
                return "High"
            if vc_val >= 0.60:
                return "Medium"
            if vc_val >= 0.0:
                return "Low"
            return "Poor"

        for elem_key, lines in element_lines_dict.items():
            elem_clean = str(elem_key).strip() if elem_key is not None else ""
            sym = extract_element_symbol(elem_clean) if elem_clean else ""

            # Check if reference exists for this element
            ref_entry = norm_ref.get(elem_clean) or norm_ref.get(sym) or norm_ref.get(sym.upper())

            if ref_entry is not None:
                ref_df_norm, fname, resolved_sym = ref_entry
                for wl in lines:
                    res = self.validate_line(proc_norm, ref_df_norm, wl, align_lag=align_lag, max_lag=max_lag)
                    vc = res.get('validation_coefficient', np.nan)
                    shift = res.get('peak_shift_nm', 0.0)
                    tier = _classify_tier(vc)
                    status = "Success" if 'error' not in res and not np.isnan(vc) else f"Failed: {res.get('error', 'Low correlation')}"
                    
                    res_copy = dict(res)
                    res_copy['element'] = resolved_sym
                    res_copy['reference_file'] = fname
                    res_copy['tier'] = tier
                    line_details.append(res_copy)

                    results.append({
                        'Wavelength_nm': wl,
                        'Element': resolved_sym,
                        'Reference_File': fname,
                        'Validation_Coefficient': vc,
                        'Peak_Shift_nm': shift,
                        'Tier': tier,
                        'Status': status,
                    })
            else:
                # No direct element match: check if element is unassigned / unknown
                if elem_clean in ["", "Unassigned", "Unknown", "None", None] and norm_ref:
                    # Multi-reference auto attribution: find best match among available references
                    for wl in lines:
                        best_vc = -999.0
                        best_res = None
                        best_sym = "Unknown"
                        best_fname = "N/A"
                        # Evaluate against unique references
                        seen_syms = set()
                        for s, (r_df, fn, r_sym) in norm_ref.items():
                            if r_sym in seen_syms:
                                continue
                            seen_syms.add(r_sym)
                            try:
                                candidate = self.validate_line(proc_norm, r_df, wl, align_lag=align_lag, max_lag=max_lag)
                                c = candidate.get('validation_coefficient', np.nan)
                                if not np.isnan(c) and c > best_vc:
                                    best_vc = c
                                    best_res = candidate
                                    best_sym = r_sym
                                    best_fname = fn
                            except Exception:
                                pass
                        
                        if best_res is not None and best_vc > -999.0:
                            tier = _classify_tier(best_vc)
                            res_copy = dict(best_res)
                            res_copy['element'] = best_sym
                            res_copy['reference_file'] = best_fname
                            res_copy['tier'] = tier
                            line_details.append(res_copy)
                            results.append({
                                'Wavelength_nm': wl,
                                'Element': best_sym,
                                'Reference_File': best_fname,
                                'Validation_Coefficient': best_vc,
                                'Peak_Shift_nm': best_res.get('peak_shift_nm', 0.0),
                                'Tier': tier,
                                'Status': "Success (Auto-attributed)",
                            })
                        else:
                            line_details.append({
                                'wavelength': wl,
                                'element': 'Unknown',
                                'reference_file': 'N/A',
                                'validation_coefficient': np.nan,
                                'peak_shift_nm': 0.0,
                                'error': 'No reference coverage for line',
                            })
                            results.append({
                                'Wavelength_nm': wl,
                                'Element': 'Unknown',
                                'Reference_File': 'N/A',
                                'Validation_Coefficient': np.nan,
                                'Peak_Shift_nm': 0.0,
                                'Tier': 'No Coverage',
                                'Status': 'No reference coverage',
                            })
                else:
                    # Missing reference spectrum for this explicit element
                    disp_elem = elem_clean if elem_clean else "Unknown"
                    for wl in lines:
                        line_details.append({
                            'wavelength': wl,
                            'element': disp_elem,
                            'reference_file': 'N/A',
                            'validation_coefficient': np.nan,
                            'peak_shift_nm': 0.0,
                            'error': f"Missing reference spectrum for element {disp_elem}",
                        })
                        results.append({
                            'Wavelength_nm': wl,
                            'Element': disp_elem,
                            'Reference_File': 'N/A',
                            'Validation_Coefficient': np.nan,
                            'Peak_Shift_nm': 0.0,
                            'Tier': 'Missing Ref',
                            'Status': f"Missing reference spectrum for {disp_elem}",
                        })

        results_df = pd.DataFrame(results)
        if results_df.empty:
            results_df = pd.DataFrame(columns=[
                'Wavelength_nm', 'Element', 'Reference_File',
                'Validation_Coefficient', 'Peak_Shift_nm', 'Tier', 'Status'
            ])
        return results_df, line_details
    
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
