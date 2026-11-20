# -*- coding: utf-8 -*-
"""
Tests for UPRSA (Unassigned Peak Recovery and Spectral Attribution)
tests/test_uprsa.py
"""

import numpy as np
import pandas as pd
import pytest

from src.core.uprsa import (
    UPRSAAnalyzer,
    extract_numbers_from_string,
    find_wavelength_column,
    find_intensity_column,
    normalize_positive_series,
)
from src.io.data_models import DetectedPeak, ProcessedSpectra, UPRSAResult


class TestUPRSAParsingHelpers:
    """Test string and column detection utilities."""

    def test_extract_numbers_from_string(self):
        s1 = "Al I | 257.51, 308.22, 309.27, 394.40, 396.15"
        res = extract_numbers_from_string(s1)
        assert len(res) == 5
        assert np.isclose(res[0], 257.51)
        assert np.isclose(res[4], 396.15)

    def test_extract_numbers_scientific_notation(self):
        s = "Peak 1.25e2 and -3.4E-1"
        res = extract_numbers_from_string(s)
        assert len(res) == 2
        assert np.isclose(res[0], 125.0)
        assert np.isclose(res[1], -0.34)

    def test_find_wavelength_column(self):
        df1 = pd.DataFrame({"Wavelength (nm)": [200, 300], "Intensity": [10, 20]})
        assert find_wavelength_column(df1) == "Wavelength (nm)"

        df2 = pd.DataFrame({"observed_wl": [200, 300], "signal": [10, 20]})
        assert find_wavelength_column(df2) == "observed_wl"

    def test_find_intensity_column(self):
        df = pd.DataFrame({"wl": [200, 300], "Corrected": [10, 20]})
        assert find_intensity_column(df) == "Corrected"

    def test_normalize_positive_series(self):
        arr = np.array([0.0, 50.0, 100.0, -10.0])
        norm = normalize_positive_series(arr)
        assert np.isclose(norm[0], 0.0)
        assert np.isclose(norm[1], 0.5)
        assert np.isclose(norm[2], 1.0)
        assert np.isclose(norm[3], 0.0)  # negative clamped to 0


class TestUPRSAAnalyzer:
    """Test UPRSAAnalyzer core mathematical and classification methods."""

    @pytest.fixture
    def analyzer(self):
        return UPRSAAnalyzer({
            "WAVELENGTH_TOLERANCE": 0.05,
            "LOCAL_WINDOW": 2.0,
            "PEAK_GUARD": 0.08,
            "MIN_LOCAL_POINTS": 5,
            "WEIGHT_INTENSITY": 0.30,
            "WEIGHT_SNR": 0.40,
            "WEIGHT_PROMINENCE": 0.30,
            "ACCEPTANCE_THRESHOLD": 0.60,
            "CONTINUOUS_PEAK_TOLERANCE": 0.15,
        })

    @pytest.fixture
    def synthetic_spectrum(self):
        """Synthetic spectrum with 3 emission lines on a flat baseline with small noise."""
        wl = np.linspace(200.0, 400.0, 2001)  # step = 0.1 nm
        # Baseline = 10.0
        intensity = np.full_like(wl, 10.0)
        
        # Line 1: Strong peak at 250.0 nm (Intensity ~ 110.0, prominence 100)
        idx1 = np.argmin(np.abs(wl - 250.0))
        intensity[idx1] = 110.0
        intensity[idx1 - 1] = 60.0
        intensity[idx1 + 1] = 60.0

        # Line 2: Medium peak at 300.0 nm (Intensity ~ 70.0)
        idx2 = np.argmin(np.abs(wl - 300.0))
        intensity[idx2] = 70.0

        # Line 3: Tiny noisy peak at 350.0 nm (Intensity ~ 12.0)
        idx3 = np.argmin(np.abs(wl - 350.0))
        intensity[idx3] = 12.0

        return wl, intensity

    def test_filter_unassigned_peaks(self, analyzer):
        detected = [(250.0, 110.0), (300.0, 70.0), (350.0, 12.0)]
        confirmed = np.array([250.02])  # 250.0 is within 0.05 nm tolerance
        unassigned = analyzer.filter_unassigned_peaks(detected, confirmed, tolerance=0.05)
        
        assert len(unassigned) == 2
        assert unassigned[0][0] == 300.0
        assert unassigned[1][0] == 350.0

    def test_analyze_full_pipeline(self, analyzer, synthetic_spectrum):
        wl, intensity = synthetic_spectrum
        detected = [
            DetectedPeak(250.0, 110.0),
            DetectedPeak(300.0, 70.0),
            DetectedPeak(350.0, 12.0),
        ]
        confirmed = [250.0]  # Line 1 is confirmed, lines 2 & 3 are unassigned

        result = analyzer.analyze((wl, intensity), detected, confirmed)

        assert isinstance(result, UPRSAResult)
        assert result.detected_count == 3
        assert result.confirmed_count == 1
        assert result.unassigned_count == 2

        # 300 nm is strong -> should be Accepted
        # 350 nm is weak -> should be Rejected
        assert result.accepted_count >= 1
        assert result.rejected_count >= 1

        top_peak = result.all_peaks[0]
        assert top_peak.wavelength == 300.0
        assert top_peak.decision == "Accepted"
        assert top_peak.pqi >= 0.60

        low_peak = result.all_peaks[-1]
        assert low_peak.wavelength == 350.0
        assert low_peak.decision == "Rejected"
        assert low_peak.pqi < 0.60

    def test_empty_unassigned_peaks(self, analyzer, synthetic_spectrum):
        wl, intensity = synthetic_spectrum
        detected = [DetectedPeak(250.0, 110.0)]
        confirmed = [250.0]

        result = analyzer.analyze((wl, intensity), detected, confirmed)
        assert result.unassigned_count == 0
        assert result.accepted_count == 0
        assert result.rejected_count == 0
        assert len(result.all_peaks) == 0

    def test_peak_guard_exclusion(self, analyzer):
        """Verify peak guard region excludes peak itself from background estimation."""
        wl = np.linspace(290.0, 310.0, 201)  # step = 0.1 nm
        intensity = np.full_like(wl, 5.0)
        target_idx = np.argmin(np.abs(wl - 300.0))
        intensity[target_idx] = 1000.0  # huge peak

        result = analyzer.analyze(
            (wl, intensity),
            [DetectedPeak(300.0, 1000.0)],
            []
        )
        assert len(result.all_peaks) == 1
        peak = result.all_peaks[0]
        # Local background should be close to 5.0, NOT 1000.0
        assert np.isclose(peak.local_background, 5.0, atol=0.5)


class TestUPRSAExportsAndWidget:
    """Test UPRSA exports and GUI widget integration."""

    def test_export_uprsa_csv(self, tmp_path):
        from src.gui.export_engine import export_uprsa_csv
        analyzer = UPRSAAnalyzer()
        wl = np.linspace(200.0, 400.0, 500)
        intensity = np.full_like(wl, 10.0)
        intensity[250] = 100.0
        res = analyzer.analyze((wl, intensity), [DetectedPeak(300.0, 100.0)], [])

        paths = export_uprsa_csv(res, tmp_path, base="TEST_UPRSA")
        assert len(paths) == 4
        for p in paths:
            assert p.exists()
            assert p.stat().st_size > 0

    def test_uprsa_widget_init_and_handoff(self, qapp):
        from src.gui.uprsa_widget import UPRSAWidget
        widget = UPRSAWidget()

        # Simulate auto-handoff
        proc = ProcessedSpectra(
            wavelength=np.linspace(200, 400, 200),
            raw=np.ones(200),
            smoothed_sg=np.ones(200),
            baseline_als=np.zeros(200),
            corrected=np.ones(200) * 15.0,
        )
        peaks = [DetectedPeak(250.0, 50.0), DetectedPeak(320.0, 80.0)]
        winners = pd.DataFrame({
            "Observed_Wavelength": [250.0],
            "Winning_Element": ["Fe"],
            "Confidence_Score": [10.5]
        })

        widget.load_from_step1(proc)
        assert widget._step1_data is proc

        widget.load_from_step2(peaks)
        assert widget._step2_peaks is peaks

        widget.load_from_step4({"winner_lines": winners})
        assert widget._step4_winners is not None

        widget._on_reset_clicked()
        assert widget.threshold_ctrl.value() == 0.60

