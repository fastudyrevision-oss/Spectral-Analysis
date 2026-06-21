# -*- coding: utf-8 -*-
"""
Integration Tests - Full Pipeline Testing

Tests the complete 3-step workflow with real and simulated data.
"""

import pytest
import numpy as np
from pathlib import Path

from src.core.step1_sg_als import BaselineCorrection
from src.core.step2_peaks import PeaksDetector
from src.core.step3_nist_matching import NISTMatcher
from src.io.file_reader import CSVReader
from src.io.file_writer import CSVWriter
from src.validators import validate_wavelength_intensity, validate_parameters


class TestFullPipeline:
    """Tests for complete 3-step analysis workflow."""
    
    def test_pipeline_step1_to_step2(self, sample_spectrum):
        """Test pipeline from Step 1 to Step 2."""
        # Step 1: Baseline correction
        corrector = BaselineCorrection()
        processed = corrector.process(sample_spectrum.wavelength, sample_spectrum.intensity)
        
        assert len(processed.corrected) == len(sample_spectrum.wavelength)
        assert not np.isnan(processed.corrected).any()
        
        # Step 2: Peak detection
        detector = PeaksDetector()
        peaks = detector.detect_peaks(processed.wavelength, processed.corrected)
        
        # Should return a list (may be empty if synthetic data doesn't create real peaks)
        assert isinstance(peaks, list)
    
    def test_pipeline_with_real_sample_data(self):
        """Test pipeline with real sample data file."""
        sample_file = Path("data/sample_inputs/soil3-unprocessed.csv")
        
        if not sample_file.exists():
            pytest.skip(f"Sample file not found: {sample_file}")
        
        # Read
        reader = CSVReader()
        raw = reader.read_raw_spectra(str(sample_file))
        
        # Step 1
        corrector = BaselineCorrection()
        processed = corrector.process(raw.wavelength, raw.intensity)
        
        # Step 2
        detector = PeaksDetector()
        peaks = detector.detect_peaks(processed.wavelength, processed.corrected)
        
        # Step 3 (optional - if NIST file exists)
        nist_file = Path("data/nist_databases/NIST-Ca.csv")
        if nist_file.exists():
            nist_db = reader.read_nist_database(str(nist_file))
            matcher = NISTMatcher()
            matches = matcher.match_peaks(peaks, nist_db)
            
            identified = [m for m in matches if m.element]
            assert len(identified) > 0, "Should identify at least some elements"
        
        # Verify all steps completed
        assert len(processed.corrected) > 0
        assert len(peaks) > 0
    
    def test_pipeline_output_consistency(self, sample_spectrum, temp_dir):
        """Test that pipeline outputs are consistent."""
        # Run pipeline
        corrector = BaselineCorrection()
        processed = corrector.process(sample_spectrum.wavelength, sample_spectrum.intensity)
        
        detector = PeaksDetector()
        peaks = detector.detect_peaks(processed.wavelength, processed.corrected)
        
        # Write outputs
        writer = CSVWriter()
        csv1 = writer.write_processed_spectra(
            str(temp_dir / "output1.csv"),
            processed
        )
        csv2 = writer.write_processed_spectra(
            str(temp_dir / "output2.csv"),
            processed
        )
        
        # Read both and compare
        import pandas as pd
        df1 = pd.read_csv(csv1)
        df2 = pd.read_csv(csv2)
        
        pd.testing.assert_frame_equal(df1, df2)


class TestValidation:
    """Tests for input validation functions."""
    
    def test_validate_wavelength_intensity_valid(self):
        """Test validation of valid data."""
        wl = np.linspace(200, 800, 1000)
        intensity = np.ones(1000) * 100
        
        # Should not raise
        validate_wavelength_intensity(wl, intensity)
    
    def test_validate_wavelength_intensity_too_short(self):
        """Test rejection of short arrays."""
        wl = np.linspace(200, 800, 50)
        intensity = np.ones(50)
        
        from src.exceptions import DataValidationError
        with pytest.raises(DataValidationError):
            validate_wavelength_intensity(wl, intensity)
    
    def test_validate_wavelength_intensity_nan(self):
        """Test rejection of NaN values."""
        wl = np.linspace(200, 800, 1000)
        intensity = np.ones(1000)
        intensity[500] = np.nan
        
        from src.exceptions import DataValidationError
        with pytest.raises(DataValidationError):
            validate_wavelength_intensity(wl, intensity)
    
    def test_validate_wavelength_intensity_inf(self):
        """Test rejection of infinite values."""
        wl = np.linspace(200, 800, 1000)
        intensity = np.ones(1000)
        intensity[500] = np.inf
        
        from src.exceptions import DataValidationError
        with pytest.raises(DataValidationError):
            validate_wavelength_intensity(wl, intensity)
    
    def test_validate_wavelength_intensity_non_monotonic(self):
        """Test rejection of non-monotonic wavelength."""
        wl = np.linspace(200, 800, 1000)
        wl[500] = wl[499]  # Break monotonicity
        intensity = np.ones(1000)
        
        from src.exceptions import DataValidationError
        with pytest.raises(DataValidationError):
            validate_wavelength_intensity(wl, intensity)
    
    def test_validate_parameters_valid(self):
        """Test validation of valid parameters."""
        params = {
            'LAMBDA': 1e5,
            'P': 0.01,
            'NITER': 10
        }
        
        validate_parameters(params, ['LAMBDA', 'P', 'NITER'])
    
    def test_validate_parameters_missing(self):
        """Test rejection of missing parameters."""
        params = {
            'LAMBDA': 1e5,
            'P': 0.01
        }
        
        from src.exceptions import DataValidationError
        with pytest.raises(DataValidationError):
            validate_parameters(params, ['LAMBDA', 'P', 'NITER'])


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_minimum_valid_spectrum(self):
        """Test processing minimal valid spectrum."""
        corrector = BaselineCorrection()
        
        wl = np.linspace(200, 800, 100)  # Minimum valid size
        intensity = np.ones(100) * 100
        
        result = corrector.process(wl, intensity)
        assert len(result.corrected) == 100
    
    def test_very_noisy_spectrum(self):
        """Test processing very noisy spectrum."""
        corrector = BaselineCorrection()
        
        wl = np.linspace(200, 800, 1000)
        intensity = np.random.randn(1000) * 100 + 500
        
        result = corrector.process(wl, intensity)
        
        # Should still produce reasonable output
        assert np.isfinite(result.corrected).all()
        assert len(result.corrected) == 1000
    
    def test_constant_spectrum(self):
        """Test processing completely flat spectrum."""
        detector = PeaksDetector()
        
        wl = np.linspace(200, 800, 1000)
        intensity = np.ones(1000) * 100
        
        peaks = detector.detect_peaks(wl, intensity)
        
        # Flat spectrum should have zero or very few peaks
        assert len(peaks) == 0 or len(peaks) <= 2
    
    def test_spectrum_with_single_spike(self):
        """Test spectrum with single spike."""
        detector = PeaksDetector()
        
        wl = np.linspace(200, 800, 1000)
        intensity = np.ones(1000) * 100
        intensity[500] = 500
        
        peaks = detector.detect_peaks(wl, intensity)
        
        # Should detect the spike
        assert len(peaks) > 0
    
    def test_spectrum_at_wavelength_boundaries(self):
        """Test spectrum near wavelength boundaries."""
        corrector = BaselineCorrection()
        
        # Very narrow wavelength range
        wl = np.linspace(299.9, 300.1, 1000)
        intensity = np.ones(1000) * 100
        
        result = corrector.process(wl, intensity)
        assert len(result.corrected) == 1000


class TestNumericalStability:
    """Tests for numerical stability and precision."""
    
    def test_float64_preservation(self):
        """Test that float64 is preserved throughout."""
        corrector = BaselineCorrection()
        
        # Need at least 100 points for validation
        wl = np.array(np.linspace(200, 800, 100), dtype=np.float64)
        intensity = np.array(np.ones(100) * 100 + np.random.randn(100) * 10, dtype=np.float64)
        
        result = corrector.process(wl, intensity)
        
        assert result.corrected.dtype == np.float64
    
    def test_large_value_handling(self):
        """Test handling of large intensity values."""
        corrector = BaselineCorrection()
        
        wl = np.linspace(200, 800, 1000)
        intensity = np.ones(1000) * 1e6
        
        result = corrector.process(wl, intensity)
        
        # Should handle large values without overflow
        assert np.isfinite(result.corrected).all()
    
    def test_small_value_handling(self):
        """Test handling of small intensity values."""
        corrector = BaselineCorrection()
        
        wl = np.linspace(200, 800, 1000)
        intensity = np.ones(1000) * 1e-6
        
        result = corrector.process(wl, intensity)
        
        # Should handle small values
        assert np.isfinite(result.corrected).all()
    
    def test_mixed_scale_values(self):
        """Test handling of mixed scale values."""
        corrector = BaselineCorrection()
        
        wl = np.linspace(200, 800, 1000)
        intensity = np.concatenate([
            np.ones(300) * 1e6,
            np.ones(400) * 1e2,
            np.ones(300) * 1e-3
        ])
        
        result = corrector.process(wl, intensity)
        
        assert np.isfinite(result.corrected).all()
