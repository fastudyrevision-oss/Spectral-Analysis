# -*- coding: utf-8 -*-
"""
Step 3: NIST Database Matching & Element Identification

Matches detected peaks against NIST spectral databases with flexible column
mapping, scoring algorithm, and best-match selection per peak.
"""

import numpy as np
import pandas as pd
from typing import List, Optional

from src import (
    STEP3_PARAMS, setup_logger,
    ProcessingError, NISTMatchingError
)
from src.io.data_models import DetectedPeak, NISTMatch


logger = setup_logger(__name__)


class NISTMatcher:
    """
    Match detected peaks against NIST spectral databases.
    
    Features:
    - Flexible column mapping (handles database format variations)
    - Wavelength matching within tolerance
    - Scoring algorithm: Score = (Aki × relative_intensity) / (Δλ + ε)
    - Best match selection per peak
    - Support for multiple element databases
    """
    
    def __init__(self, config: dict = None):
        """
        Initialize NIST matcher.
        
        Parameters
        ----------
        config : dict, optional
            Configuration with keys:
            - TOLERANCE: wavelength matching tolerance (nm)
            - MIN_SCORE_THRESHOLD: minimum score to report
            
            If None, uses defaults from STEP3_PARAMS
        """
        if config is None:
            config = STEP3_PARAMS
        
        self.tolerance = float(config['TOLERANCE'])
        self.min_score = float(config['MIN_SCORE_THRESHOLD'])
        
        logger.info(f"NISTMatcher initialized with:")
        logger.info(f"  TOLERANCE={self.tolerance} nm, MIN_SCORE={self.min_score}")
    
    @staticmethod
    def detect_column_names(df: pd.DataFrame) -> dict:
        """
        Auto-detect column names in NIST database.
        
        Handles variations in column naming conventions.
        
        Parameters
        ----------
        df : pd.DataFrame
            DataFrame to analyze
        
        Returns
        -------
        dict
            Detected column mapping
            Keys: 'wavelength_col', 'element_col', 'aki_col', 'rel_int_col'
        
        Raises
        ------
        NISTMatchingError
            If wavelength column cannot be detected
        """
        cols_lower = {col.lower(): col for col in df.columns}
        
        # Wavelength (required)
        wl_candidates = ['wavelength', 'wl', 'wavelength (nm)', 'wave', 'lambda']
        wl_col = None
        for candidate in wl_candidates:
            if candidate in cols_lower:
                wl_col = cols_lower[candidate]
                break
        
        if wl_col is None:
            raise NISTMatchingError("Wavelength column not found in NIST database")
        
        # Element
        elem_candidates = ['element', 'element_symbol', 'ion', 'species', 'atom']
        elem_col = None
        for candidate in elem_candidates:
            if candidate in cols_lower:
                elem_col = cols_lower[candidate]
                break
        
        # Aki (line strength)
        aki_candidates = ['aki', 'intensity', 'strength', 'transition', 'gf']
        aki_col = None
        for candidate in aki_candidates:
            if candidate in cols_lower:
                aki_col = cols_lower[candidate]
                break
        
        # Relative intensity
        rel_int_candidates = ['relative_intensity', 'rel_int', 'rel intensity', 'relative int']
        rel_int_col = None
        for candidate in rel_int_candidates:
            if candidate in cols_lower:
                rel_int_col = cols_lower[candidate]
                break
        
        logger.debug(f"Detected columns: wl={wl_col}, elem={elem_col}, aki={aki_col}, rel_int={rel_int_col}")
        
        return {
            'wavelength_col': wl_col,
            'element_col': elem_col,
            'aki_col': aki_col,
            'rel_int_col': rel_int_col
        }
    
    @staticmethod
    def calculate_score(aki: float, rel_int: float, delta: float) -> float:
        """
        Calculate matching score.
        
        Scoring formula: Score = (Aki × relative_intensity) / (Δλ + 1e-6)
        
        Parameters
        ----------
        aki : float
            Line strength (Aki value)
        rel_int : float
            Relative intensity
        delta : float
            Wavelength difference
        
        Returns
        -------
        float
            Matching score
        """
        if aki <= 0 or rel_int <= 0:
            return 0
        
        score = (aki * rel_int) / (delta + 1e-6)
        return score
    
    def match_peaks(self, detected_peaks: List[DetectedPeak], 
                   nist_df: pd.DataFrame) -> List[NISTMatch]:
        """
        Match detected peaks to NIST database.
        
        Parameters
        ----------
        detected_peaks : List[DetectedPeak]
            Detected spectral peaks
        nist_df : pd.DataFrame
            NIST database (standardized columns)
        
        Returns
        -------
        List[NISTMatch]
            Best match for each detected peak
        
        Raises
        ------
        ProcessingError
            If matching fails
        """
        logger.info(f"Matching {len(detected_peaks)} peaks against {len(nist_df)} NIST entries")
        
        try:
            results = []
            
            for peak in detected_peaks:
                # Find candidates within tolerance
                candidates = nist_df[
                    np.abs(nist_df['Wavelength'] - peak.wavelength) <= self.tolerance
                ]
                
                if candidates.empty:
                    # No match found
                    results.append(NISTMatch(
                        observed_wl=peak.wavelength,
                        matched_wl=None,
                        delta=None,
                        aki=0,
                        relative_intensity=0,
                        score=0,
                        element=None
                    ))
                    continue
                
                # Score all candidates
                scores = []
                for _, row in candidates.iterrows():
                    delta = abs(row['Wavelength'] - peak.wavelength)
                    score = self.calculate_score(row['Aki'], row['relative_intensity'], delta)
                    scores.append((score, row, delta))
                
                # Select best match (highest score)
                best_score, best_row, best_delta = max(scores, key=lambda x: x[0])
                
                if best_score >= self.min_score:
                    results.append(NISTMatch(
                        observed_wl=peak.wavelength,
                        matched_wl=float(best_row['Wavelength']),
                        delta=float(best_delta),
                        aki=float(best_row['Aki']),
                        relative_intensity=float(best_row['relative_intensity']),
                        score=float(best_score),
                        element=str(best_row['Element'])
                    ))
                else:
                    # Score below threshold
                    results.append(NISTMatch(
                        observed_wl=peak.wavelength,
                        matched_wl=float(best_row['Wavelength']),
                        delta=float(best_delta),
                        aki=float(best_row['Aki']),
                        relative_intensity=float(best_row['relative_intensity']),
                        score=0,  # Below threshold
                        element=None
                    ))
            
            logger.info(f"Matching complete: {len([r for r in results if r.element])} peaks identified")
            return results
        
        except Exception as e:
            logger.error(f"Matching failed: {e}")
            raise ProcessingError(f"NIST matching failed: {e}") from e
    
    def match_multiple_databases(self, detected_peaks: List[DetectedPeak],
                                nist_dataframes: List[pd.DataFrame]) -> pd.DataFrame:
        """
        Match peaks against multiple NIST databases and determine winners.
        
        Parameters
        ----------
        detected_peaks : List[DetectedPeak]
            Detected peaks
        nist_dataframes : List[pd.DataFrame]
            List of NIST databases (each element)
        
        Returns
        -------
        pd.DataFrame
            Results with winner determination
        """
        logger.info(f"Matching against {len(nist_dataframes)} NIST databases")
        
        all_results = []
        
        # Match against each database
        for i, nist_df in enumerate(nist_dataframes):
            logger.info(f"Database {i+1}/{len(nist_dataframes)}: {len(nist_df)} entries")
            matches = self.match_peaks(detected_peaks, nist_df)
            all_results.extend(matches)
        
        # Create DataFrame
        df = pd.DataFrame([
            {
                'Observed_WL': m.observed_wl,
                'Matched_WL': m.matched_wl,
                'Delta': m.delta,
                'Aki': m.aki,
                'relative_intensity': m.relative_intensity,
                'Score': m.score,
                'Element': m.element
            }
            for m in all_results
        ])
        
        logger.info(f"Total results: {len(df)} matches")
        logger.info(f"Identified elements: {df[df['Element'].notna()]['Element'].unique()}")
        
        return df
