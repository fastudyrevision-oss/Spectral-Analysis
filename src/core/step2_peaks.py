# -*- coding: utf-8 -*-
"""
Step 2: Automatic Peaks Detection

Detects spectral peaks using scipy.signal.find_peaks with adaptive
thresholding based on noise estimation and baseline filtering.
"""

import numpy as np
from scipy.signal import find_peaks
from typing import List

from src import (
    STEP2_PARAMS, setup_logger, 
    validate_wavelength_intensity, ProcessingError
)
from src.io.data_models import DetectedPeak


logger = setup_logger(__name__)


class PeaksDetector:
    """
    Automatic peak detection with adaptive thresholding and baseline filtering.
    
    Algorithm:
    1. Estimate noise level from beginning of spectrum
    2. Calculate height threshold = noise_level × HEIGHT_MULTIPLIER
    3. Find peaks using scipy.signal.find_peaks
    4. Filter false peaks using local baseline analysis
    5. Return detected peaks sorted by wavelength
    """
    
    def __init__(self, config: dict = None):
        """
        Initialize peaks detector.
        
        Parameters
        ----------
        config : dict, optional
            Configuration dictionary with keys:
            - HEIGHT_MULTIPLIER: threshold multiplier
            - PROMINENCE: minimum prominence
            - BASELINE_WINDOW: filtering window
            - BASELINE_K: noise threshold factor
            
            If None, uses defaults from STEP2_PARAMS
        """
        if config is None:
            config = STEP2_PARAMS
        
        self.height_mult = float(config['HEIGHT_MULTIPLIER'])
        self.prominence = float(config['PROMINENCE'])
        self.baseline_window = int(config['BASELINE_WINDOW'])
        self.baseline_k = float(config['BASELINE_K'])
        
        logger.info(f"PeaksDetector initialized with:")
        logger.info(f"  HEIGHT_MULTIPLIER={self.height_mult}, PROMINENCE={self.prominence}")
        logger.info(f"  BASELINE_WINDOW={self.baseline_window}, BASELINE_K={self.baseline_k}")
    
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
            If data invalid
        """
        logger.info(f"Validating input: {len(wavelength)} data points")
        validate_wavelength_intensity(wavelength, intensity)
        logger.info("Input validation passed")
        return True
    
    def calculate_noise_level(self, intensity: np.ndarray) -> float:
        """
        Estimate noise level from beginning of spectrum.
        
        Uses first 10% of spectrum as baseline noise estimate.
        
        Parameters
        ----------
        intensity : np.ndarray
            Intensity array
        
        Returns
        -------
        float
            Estimated noise level (std dev)
        """
        # Use first 10% as noise estimate
        noise_region = intensity[:int(len(intensity) * 0.1)]
        noise_level = np.std(noise_region)
        
        logger.debug(f"Noise level estimated: {noise_level:.6e}")
        return noise_level
    
    def remove_baseline_peaks(self, intensity: np.ndarray, 
                             peaks: np.ndarray) -> np.ndarray:
        """
        Filter false peaks based on local baseline analysis.
        
        For each peak, analyzes local baseline in window and removes
        peaks that don't exceed baseline + k*noise significantly.
        
        Parameters
        ----------
        intensity : np.ndarray
            Intensity array
        peaks : np.ndarray
            Peak indices from find_peaks
        
        Returns
        -------
        np.ndarray
            Filtered peak indices
        """
        logger.debug(f"Baseline filtering {len(peaks)} peaks")
        
        filtered = []
        
        for p in peaks:
            # Get local window
            left = max(0, p - self.baseline_window)
            right = min(len(intensity), p + self.baseline_window)
            
            region = intensity[left:right]
            
            # Estimate local baseline (median)
            baseline = np.percentile(region, 50)
            noise = np.std(region)
            
            # Check if peak exceeds threshold
            threshold = baseline + self.baseline_k * noise
            if intensity[p] > threshold:
                filtered.append(p)
        
        logger.debug(f"After baseline filtering: {len(filtered)} peaks remain")
        return np.array(filtered)
    
    def detect_peaks(self, wavelength: np.ndarray, 
                    intensity: np.ndarray) -> List[DetectedPeak]:
        """
        Full peak detection pipeline.
        
        Parameters
        ----------
        wavelength : np.ndarray
            Wavelength array (nm)
        intensity : np.ndarray
            Intensity array
        
        Returns
        -------
        List[DetectedPeak]
            Detected peaks sorted by wavelength
        
        Raises
        ------
        DataValidationError
            If input invalid
        ProcessingError
            If detection fails
        """
        logger.info("=== STEP 2: PEAKS DETECTION START ===")
        logger.info(f"Input: {len(wavelength)} points, intensity range [{intensity.min():.6e}, {intensity.max():.6e}]")
        
        try:
            # Validate
            self.validate_input(wavelength, intensity)
            
            # Ensure float64
            wavelength = np.array(wavelength, dtype=np.float64)
            intensity = np.array(intensity, dtype=np.float64)
            
            # Estimate noise
            noise_level = self.calculate_noise_level(intensity)
            height_threshold = self.height_mult * noise_level
            logger.info(f"Height threshold: {height_threshold:.6e}")
            
            # Find peaks
            logger.info("Finding peaks using scipy.signal.find_peaks")
            peaks, properties = find_peaks(intensity, 
                                          height=height_threshold,
                                          prominence=self.prominence)
            logger.info(f"Found {len(peaks)} peaks")
            
            # Baseline filtering
            peaks_filtered = self.remove_baseline_peaks(intensity, peaks)
            logger.info(f"After filtering: {len(peaks_filtered)} peaks")
            
            # Create DetectedPeak objects
            detected_peaks = [
                DetectedPeak(
                    wavelength=float(wavelength[p]),
                    intensity=float(intensity[p])
                )
                for p in peaks_filtered
            ]
            
            # Sort by wavelength
            detected_peaks.sort(key=lambda x: x.wavelength)
            
            if len(detected_peaks) > 0:
                logger.info(f"Peak wavelength range: [{detected_peaks[0].wavelength:.2f}, {detected_peaks[-1].wavelength:.2f}] nm")
            else:
                logger.info("No peaks detected after filtering")
            logger.info("=== STEP 2: PEAKS DETECTION COMPLETE ===")
            
            return detected_peaks
        
        except Exception as e:
            logger.error(f"Peak detection failed: {e}")
            raise ProcessingError(f"Peak detection failed: {e}") from e
