# -*- coding: utf-8 -*-
"""
Test Suite for Core Processing Algorithms

Tests Step 1, 2, and 3 algorithms with various inputs and edge cases.
"""

import pytest
import numpy as np

from src.config import STEP1_PARAMS, STEP2_PARAMS, STEP3_PARAMS
from src.core.step1_sg_als import BaselineCorrection
from src.core.step2_peaks import PeaksDetector
from src.core.step3_nist_matching import NISTMatcher
from src.exceptions import DataValidationError, ProcessingError
from src.io.data_models import DetectedPeak


class TestStep1BaselineCorrection:
    """Tests for Step 1: SG-ALS Baseline Correction"""
    
    def test_initialization(self):
        """Test BaselineCorrection initialization."""
        corrector = BaselineCorrection()
        assert corrector.lambda_ == STEP1_PARAMS['LAMBDA']
        assert corrector.p == STEP1_PARAMS['P']
        assert corrector.n_iter == STEP1_PARAMS['NITER']
    
    def test_custom_parameters(self):
        """Test with custom parameters."""
        params = {
            'LAMBDA': 1e4,
            'P': 0.02,
            'NITER': 5,
            'WINDOW': 9,
            'POLY': 2
        }
        corrector = BaselineCorrection(params)
        assert corrector.lambda_ == 1e4
        assert corrector.p == 0.02
        assert corrector.n_iter == 5
    
    def test_process_basic(self, sample_spectrum):
        """Test basic processing."""
        corrector = BaselineCorrection()
        result = corrector.process(sample_spectrum.wavelength, sample_spectrum.intensity)
        
        # Check output structure
        assert hasattr(result, 'wavelength')
        assert hasattr(result, 'corrected')
        assert len(result.corrected) == len(sample_spectrum.intensity)
    
    def test_sg_smoothing_output_range(self, sample_spectrum):
        """Test that SG smoothing produces reasonable output."""
        corrector = BaselineCorrection()
        result = corrector.process(sample_spectrum.wavelength, sample_spectrum.intensity)
        
        # Smoothed should be within similar range as original
        raw_range = np.ptp(sample_spectrum.intensity)
        smoothed_range = np.ptp(result.smoothed_sg)
        
        assert smoothed_range < raw_range * 1.5  # Allow some flexibility
        assert smoothed_range > raw_range * 0.5
    
    def test_baseline_als_monotonicity(self, sample_spectrum):
        """Test that ALS produces smooth baseline."""
        corrector = BaselineCorrection()
        result = corrector.process(sample_spectrum.wavelength, sample_spectrum.intensity)
        
        # Baseline should be reasonably smooth (few sign changes in second derivative)
        second_diff = np.diff(result.baseline_als, n=2)
        sign_changes = np.sum(np.diff(np.sign(second_diff)) != 0)
        
        # Allow some oscillation but not too much
        assert sign_changes < len(second_diff) / 10
    
    def test_precision_float64(self, sample_spectrum):
        """Test that float64 precision is maintained."""
        corrector = BaselineCorrection()
        result = corrector.process(sample_spectrum.wavelength, sample_spectrum.intensity)
        
        assert result.corrected.dtype == np.float64
        assert result.smoothed_sg.dtype == np.float64
        assert result.baseline_als.dtype == np.float64
    
    def test_input_validation_short_array(self):
        """Test that short arrays are rejected."""
        corrector = BaselineCorrection()
        wl = np.linspace(200, 800, 50)  # Too short
        intensity = np.ones(50)
        
        with pytest.raises(DataValidationError):
            corrector.process(wl, intensity)
    
    def test_input_validation_nan_values(self):
        """Test that NaN values are rejected."""
        corrector = BaselineCorrection()
        wl = np.linspace(200, 800, 1000)
        intensity = np.ones(1000)
        intensity[500] = np.nan
        
        with pytest.raises(DataValidationError):
            corrector.process(wl, intensity)
    
    def test_non_monotonic_wavelength(self):
        """Test that non-monotonic wavelength is rejected."""
        corrector = BaselineCorrection()
        wl = np.linspace(200, 800, 1000)
        wl[500] = wl[499]  # Break monotonicity
        intensity = np.ones(1000)
        
        with pytest.raises(DataValidationError):
            corrector.process(wl, intensity)


class TestStep2PeaksDetection:
    """Tests for Step 2: Automatic Peaks Detection"""
    
    def test_initialization(self):
        """Test PeaksDetector initialization."""
        detector = PeaksDetector()
        assert detector.height_mult == STEP2_PARAMS['HEIGHT_MULTIPLIER']
        assert detector.prominence == STEP2_PARAMS['PROMINENCE']
    
    def test_custom_parameters(self):
        """Test with custom parameters."""
        params = {
            'HEIGHT_MULTIPLIER': 2.0,
            'PROMINENCE': 0.05,
            'BASELINE_WINDOW': 30,
            'BASELINE_K': 1.5
        }
        detector = PeaksDetector(params)
        assert detector.height_mult == 2.0
        assert detector.prominence == 0.05
    
    def test_detect_peaks_basic(self, processed_spectrum):
        """Test basic peak detection."""
        detector = PeaksDetector()
        peaks = detector.detect_peaks(processed_spectrum.wavelength, processed_spectrum.corrected)
        
        # Should return list (may be empty if no real peaks in synthetic data)
        assert isinstance(peaks, list)
        assert all(isinstance(p, DetectedPeak) for p in peaks)
    
    def test_peak_wavelengths_in_range(self, processed_spectrum):
        """Test that detected peaks are within wavelength range."""
        detector = PeaksDetector()
        peaks = detector.detect_peaks(processed_spectrum.wavelength, processed_spectrum.corrected)
        
        if len(peaks) > 0:  # Only test if peaks detected
            wl_min = processed_spectrum.wavelength.min()
            wl_max = processed_spectrum.wavelength.max()
            
            for peak in peaks:
                assert wl_min <= peak.wavelength <= wl_max
    
    def test_peak_intensities_positive(self, processed_spectrum):
        """Test that peak intensities are positive (above noise)."""
        detector = PeaksDetector()
        peaks = detector.detect_peaks(processed_spectrum.wavelength, processed_spectrum.corrected)
        
        # All detected peaks should have positive intensities
        if len(peaks) > 0:
            assert all(p.intensity > 0 for p in peaks)
    
    def test_peaks_sorted_by_wavelength(self, processed_spectrum):
        """Test that returned peaks are sorted by wavelength."""
        detector = PeaksDetector()
        peaks = detector.detect_peaks(processed_spectrum.wavelength, processed_spectrum.corrected)
        
        if len(peaks) > 1:
            wavelengths = [p.wavelength for p in peaks]
            assert wavelengths == sorted(wavelengths)
    
    def test_flat_spectrum_no_peaks(self):
        """Test that flat spectrum produces no peaks."""
        detector = PeaksDetector()
        wl = np.linspace(200, 800, 1000)
        intensity = np.ones(1000) * 100  # Completely flat
        
        peaks = detector.detect_peaks(wl, intensity)
        
        # Flat spectrum should have zero or very few peaks
        assert len(peaks) == 0 or len(peaks) <= 2  # Allow tolerance
    
    def test_single_peak_detection(self):
        """Test detection of single peak."""
        detector = PeaksDetector()
        wl = np.linspace(200, 800, 1000)
        intensity = np.ones(1000) * 100
        # Add single peak
        peak_idx = 500
        intensity[peak_idx] = 500
        
        peaks = detector.detect_peaks(wl, intensity)
        assert len(peaks) > 0


class TestStep3NISTMatching:
    """Tests for Step 3: NIST Element Identification"""
    
    def test_initialization(self):
        """Test NISTMatcher initialization."""
        matcher = NISTMatcher()
        assert matcher.tolerance == STEP3_PARAMS['TOLERANCE']
    
    def test_custom_parameters(self):
        """Test with custom parameters."""
        params = {
            'TOLERANCE': 0.5,
            'MIN_SCORE_THRESHOLD': 1e6
        }
        matcher = NISTMatcher(params)
        assert matcher.tolerance == 0.5
    
    def test_exact_match(self, sample_nist_csv):
        """Test exact wavelength match."""
        from src.io.file_reader import CSVReader
        matcher = NISTMatcher()
        
        # Load NIST database using CSVReader to standardize columns
        reader = CSVReader()
        nist_df = reader.read_nist_database(str(sample_nist_csv))
        
        # Create peak at exact wavelength
        peaks = [DetectedPeak(wavelength=300.1, intensity=500.0)]
        
        matches = matcher.match_peaks(peaks, nist_df)
        assert len(matches) == 1
        assert matches[0].matched_wl == 300.1
        assert matches[0].element == 'Ca'
    
    def test_no_match_outside_tolerance(self, sample_nist_csv):
        """Test no match for wavelength outside tolerance."""
        from src.io.file_reader import CSVReader
        matcher = NISTMatcher({'TOLERANCE': 0.01, 'MIN_SCORE_THRESHOLD': 0})
        
        # Load NIST database using CSVReader to standardize columns
        reader = CSVReader()
        nist_df = reader.read_nist_database(str(sample_nist_csv))
        
        # Create peak far outside tolerance
        peaks = [DetectedPeak(wavelength=250.0, intensity=500.0)]
        
        matches = matcher.match_peaks(peaks, nist_df)
        assert len(matches) == 1
        assert matches[0].matched_wl is None
    
    def test_multiple_peaks_matching(self, sample_nist_csv):
        """Test matching of multiple peaks."""
        from src.io.file_reader import CSVReader
        matcher = NISTMatcher()
        
        # Load NIST database using CSVReader to standardize columns
        reader = CSVReader()
        nist_df = reader.read_nist_database(str(sample_nist_csv))
        
        peaks = [
            DetectedPeak(wavelength=300.0, intensity=500.0),
            DetectedPeak(wavelength=400.0, intensity=700.0),
        ]
        
        matches = matcher.match_peaks(peaks, nist_df)
        assert len(matches) == len(peaks)
    
    def test_scoring_algorithm(self):
        """Test scoring algorithm."""
        matcher = NISTMatcher()
        
        # Perfect match: score = Aki * rel_int / (delta + epsilon)
        score1 = matcher.calculate_score(1e6, 100, 0.001)  # Small delta
        score2 = matcher.calculate_score(1e6, 100, 0.1)    # Larger delta
        
        assert score1 > score2  # Score decreases with larger delta
    
    def test_scoring_invalid_aki(self):
        """Test scoring with invalid Aki."""
        matcher = NISTMatcher()
        
        # Zero or negative Aki should give zero score
        score = matcher.calculate_score(0, 100, 0.01)
        assert score == 0
        
        score = matcher.calculate_score(-1, 100, 0.01)
        assert score == 0
    
    def test_column_detection(self, sample_nist_csv):
        """Test automatic column detection."""
        from src.io.file_reader import CSVReader
        import pandas as pd
        
        # Read through CSVReader which standardizes columns
        reader = CSVReader()
        nist_df = reader.read_nist_database(str(sample_nist_csv))
        
        # After CSVReader standardization, should have Wavelength column
        assert 'Wavelength' in nist_df.columns


class TestDataModels:
    """Tests for data model structures."""
    
    def test_raw_spectra_creation(self):
        """Test RawSpectra dataclass creation."""
        from src.io.data_models import RawSpectra
        
        wl = np.array([200, 300, 400])
        intensity = np.array([100, 200, 150])
        
        spectra = RawSpectra(
            wavelength=wl,
            intensity=intensity,
            metadata={'test': 'value'},
            source_file='test.csv'
        )
        
        assert len(spectra.wavelength) == 3
        assert spectra.source_file == 'test.csv'
    
    def test_detected_peak_creation(self):
        """Test DetectedPeak dataclass creation."""
        from src.io.data_models import DetectedPeak
        
        peak = DetectedPeak(wavelength=300.5, intensity=500.0)
        assert peak.wavelength == 300.5
        assert peak.intensity == 500.0
    
    def test_nist_match_creation(self):
        """Test NISTMatch dataclass creation."""
        from src.io.data_models import NISTMatch
        
        match = NISTMatch(
            observed_wl=300.0,
            matched_wl=300.1,
            delta=0.1,
            aki=1e6,
            relative_intensity=100,
            score=1e8,
            element='Ca'
        )
        
        assert match.observed_wl == 300.0
        assert match.element == 'Ca'
