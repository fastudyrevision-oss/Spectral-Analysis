# -*- coding: utf-8 -*-
"""
Step 1: SG-ALS Spectral Baseline Correction

Implements Savitzky-Golay smoothing and Asymmetric Least Squares (ALS)
baseline correction for LIBS spectral data.
"""

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve
from scipy.signal import savgol_filter
from typing import Tuple, List

from src import (
    STEP1_PARAMS, setup_logger, 
    validate_wavelength_intensity, DataValidationError, ProcessingError
)
from src.io.data_models import RawSpectra, ProcessedSpectra


logger = setup_logger(__name__)


class BaselineCorrection:
    """
    Performs SG smoothing and ALS baseline correction on spectral data.
    
    This class implements the full pipeline for spectral baseline correction:
    1. Savitzky-Golay smoothing to remove noise
    2. Asymmetric Least Squares baseline estimation
    3. Baseline subtraction for corrected spectra
    
    All calculations performed in float64 for precision preservation.
    """
    
    def __init__(self, config: dict = None):
        """
        Initialize baseline correction with parameters.
        
        Parameters
        ----------
        config : dict, optional
            Configuration dictionary with keys:
            - LAMBDA: smoothness parameter
            - P: asymmetry parameter
            - NITER: number of iterations
            - WINDOW: SG window size
            - POLY: SG polynomial degree
            
            If None, uses defaults from STEP1_PARAMS
        """
        if config is None:
            config = STEP1_PARAMS
        
        self.lambda_ = float(config['LAMBDA'])
        self.p = float(config['P'])
        self.n_iter = int(config['NITER'])
        self.sg_window = int(config['WINDOW'])
        self.sg_poly = int(config['POLY'])
        
        logger.info(f"BaselineCorrection initialized with:")
        logger.info(f"  LAMBDA={self.lambda_}, P={self.p}, NITER={self.n_iter}")
        logger.info(f"  SG Window={self.sg_window}, Poly={self.sg_poly}")
    
    def validate_input(self, wavelength: np.ndarray, 
                      intensity: np.ndarray) -> bool:
        """
        Validate input data.
        
        Parameters
        ----------
        wavelength : np.ndarray
            Wavelength array
        intensity : np.ndarray
            Intensity array
        
        Returns
        -------
        bool
            True if valid
        
        Raises
        ------
        DataValidationError
            If data is invalid
        """
        logger.info(f"Validating input: {len(wavelength)} data points")
        validate_wavelength_intensity(wavelength, intensity)
        logger.info("Input validation passed")
        return True
    
    def apply_sg_smoothing(self, intensity: np.ndarray) -> np.ndarray:
        """
        Apply Savitzky-Golay smoothing filter.
        
        Parameters
        ----------
        intensity : np.ndarray
            Raw intensity data
        
        Returns
        -------
        np.ndarray
            Smoothed intensity (float64)
        """
        logger.debug(f"Applying SG smoothing (window={self.sg_window}, poly={self.sg_poly})")
        
        smoothed = savgol_filter(intensity, self.sg_window, self.sg_poly)
        
        logger.debug(f"SG smoothing complete. Output shape: {smoothed.shape}")
        return smoothed.astype(np.float64)
    
    def apply_als(self, smoothed_intensity: np.ndarray) -> Tuple[np.ndarray, List[np.ndarray]]:
        """
        Apply Asymmetric Least Squares baseline correction.
        
        The ALS algorithm iteratively estimates the baseline by:
        1. Computing a weighted least squares solution
        2. Updating weights based on residuals
        3. Repeating for n_iter iterations
        
        Parameters
        ----------
        smoothed_intensity : np.ndarray
            Smoothed intensity data
        
        Returns
        -------
        tuple
            (baseline, baseline_iterations)
            - baseline: Final ALS baseline (float64)
            - baseline_iterations: List of baseline states per iteration
        
        Raises
        ------
        ProcessingError
            If ALS algorithm fails
        """
        logger.info(f"Starting ALS baseline correction ({self.n_iter} iterations)")
        
        try:
            L = len(smoothed_intensity)
            
            # Construct difference matrix (explicit float64 to avoid FutureWarning)
            D = sparse.diags([1.0, -2.0, 1.0], [0, -1, -2], shape=(L, L-2), dtype=np.float64, format='csc')
            w = np.ones(L, dtype=np.float64)
            baselines = []
            
            # Iterate
            for i in range(self.n_iter):
                W = sparse.diags(w, 0, dtype=np.float64, format='csc')
                Z = W + self.lambda_ * D.dot(D.T)
                
                # Solve sparse system (CSC format is efficient)
                z = spsolve(Z, w * smoothed_intensity)
                baselines.append(np.array(z, dtype=np.float64))
                
                # Update weights
                w = self.p * (smoothed_intensity > z) + (1 - self.p) * (smoothed_intensity < z)
                
                logger.debug(f"  Iteration {i+1}/{self.n_iter} complete")
            
            logger.info("ALS baseline correction converged")
            return np.array(z, dtype=np.float64), baselines
        
        except Exception as e:
            logger.error(f"ALS algorithm failed: {e}")
            raise ProcessingError(f"ALS baseline correction failed: {e}") from e
    
    def process(self, wavelength: np.ndarray, 
               intensity: np.ndarray) -> ProcessedSpectra:
        """
        Full baseline correction pipeline.
        
        Parameters
        ----------
        wavelength : np.ndarray
            Wavelength array (nm)
        intensity : np.ndarray
            Raw intensity array
        
        Returns
        -------
        ProcessedSpectra
            Data object with all processing results
        
        Raises
        ------
        DataValidationError
            If input data invalid
        ProcessingError
            If processing fails
        """
        logger.info("=== STEP 1: SG-ALS BASELINE CORRECTION START ===")
        logger.info(f"Input: {len(wavelength)} wavelength points, intensity range [{intensity.min():.6e}, {intensity.max():.6e}]")
        
        # Validate
        self.validate_input(wavelength, intensity)
        
        # Ensure float64
        wavelength = np.array(wavelength, dtype=np.float64)
        intensity = np.array(intensity, dtype=np.float64)
        
        # SG Smoothing
        smoothed = self.apply_sg_smoothing(intensity)
        logger.info(f"SG smoothed. Output range: [{smoothed.min():.6e}, {smoothed.max():.6e}]")
        
        # ALS Baseline
        baseline, baseline_iters = self.apply_als(smoothed)
        logger.info(f"ALS baseline. Range: [{baseline.min():.6e}, {baseline.max():.6e}]")
        
        # Correction
        corrected = smoothed - baseline
        logger.info(f"Corrected spectra. Range: [{corrected.min():.6e}, {corrected.max():.6e}]")
        
        # Create result
        result = ProcessedSpectra(
            wavelength=wavelength,
            raw=intensity,
            smoothed_sg=smoothed,
            baseline_als=baseline,
            corrected=corrected,
            baseline_iterations=baseline_iters
        )
        
        logger.info("=== STEP 1: SG-ALS BASELINE CORRECTION COMPLETE ===")
        return result
