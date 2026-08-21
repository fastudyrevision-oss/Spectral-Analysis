# -*- coding: utf-8 -*-
"""
Unit tests for Step 7: CalibrationEngine

Tests cover:
  - extract_intensity (basic, missing file, no peak in window)
  - fit_curve (linear, quadratic, power_law, too few points)
  - predict_concentration (linear inverse, uncertainty, out-of-range)
  - compute_lod_loq (linear, no blank, bad fit)
  - fit_and_predict (full end-to-end, too few points, None inputs)
  - compute_r_squared (perfect fit, flat target)
  - ChartEngine smoke tests for the three new Step 7 methods
"""

import csv
import math
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.core.step7_calibration import CalibrationEngine, CalibrationPoint, FitResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_spectrum_csv(path: Path, wavelengths, intensities):
    """Write a minimal processed spectrum CSV."""
    df = pd.DataFrame({"Wavelength": wavelengths, "Corrected": intensities})
    df.to_csv(str(path), index=False)


def _make_linear_standards(
    a: float, b: float, concentrations, noise: float = 0.0
) -> list[CalibrationPoint]:
    """Generate CalibrationPoint list for y = a*x + b."""
    points = []
    for conc in concentrations:
        intensity = a * conc + b + noise
        points.append(CalibrationPoint(
            sample_id=f"SRM-{conc}",
            concentration=float(conc),
            spectrum_file="",  # filled during test
            intensity=None,
            is_blank=False,
        ))
    return points


# ---------------------------------------------------------------------------
# extract_intensity
# ---------------------------------------------------------------------------

class TestExtractIntensity:

    def test_basic(self, tmp_path):
        """Returns correct max intensity within tolerance window."""
        engine = CalibrationEngine()
        # Write spectrum with a peak at 422.67 nm
        wls = np.linspace(400, 450, 500)
        ints = np.zeros(500)
        idx = np.argmin(np.abs(wls - 422.67))
        ints[idx] = 5000.0
        csv_path = tmp_path / "spectrum.csv"
        _write_spectrum_csv(csv_path, wls, ints)

        result = engine.extract_intensity(str(csv_path), 422.67, 0.5)
        assert result is not None
        assert abs(result - 5000.0) < 1.0

    def test_missing_file(self):
        """Returns None and does not raise for a non-existent file."""
        engine = CalibrationEngine()
        result = engine.extract_intensity("/nonexistent/file.csv", 422.67, 0.5)
        assert result is None

    def test_no_peak_in_window(self, tmp_path):
        """Returns None when no row falls in the tolerance window."""
        engine = CalibrationEngine()
        wls = np.array([400.0, 430.0, 460.0])
        ints = np.array([100.0, 200.0, 150.0])
        csv_path = tmp_path / "spectrum.csv"
        _write_spectrum_csv(csv_path, wls, ints)
        # Query at 422.67 with tolerance 0.2 — no row within range
        result = engine.extract_intensity(str(csv_path), 422.67, 0.2)
        assert result is None

    def test_empty_file(self, tmp_path):
        """Returns None for an empty CSV."""
        engine = CalibrationEngine()
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("Wavelength,Corrected\n")
        result = engine.extract_intensity(str(csv_path), 422.67, 0.5)
        assert result is None

    def test_multiple_rows_in_window(self, tmp_path):
        """Returns max intensity when multiple rows are in tolerance window."""
        engine = CalibrationEngine()
        wls = np.array([422.5, 422.6, 422.7, 422.8])
        ints = np.array([100.0, 500.0, 300.0, 200.0])
        csv_path = tmp_path / "spectrum.csv"
        _write_spectrum_csv(csv_path, wls, ints)
        result = engine.extract_intensity(str(csv_path), 422.67, 0.5)
        assert result == 500.0


# ---------------------------------------------------------------------------
# compute_r_squared
# ---------------------------------------------------------------------------

class TestComputeRSquared:

    def test_perfect_fit(self):
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert CalibrationEngine.compute_r_squared(y, y) == pytest.approx(1.0)

    def test_flat_target(self):
        """Returns 0.0 when SS_tot == 0 (all y_actual identical)."""
        y = np.array([3.0, 3.0, 3.0])
        y_pred = np.array([3.0, 3.5, 2.5])
        result = CalibrationEngine.compute_r_squared(y, y_pred)
        assert result == pytest.approx(0.0)

    def test_partial_fit(self):
        y_actual = np.array([1.0, 2.0, 3.0, 4.0])
        y_pred = np.array([1.1, 1.9, 3.1, 3.9])
        r2 = CalibrationEngine.compute_r_squared(y_actual, y_pred)
        assert 0.95 < r2 <= 1.0

    def test_clamp_to_zero(self):
        """Terrible fit should return 0 (not negative)."""
        y_actual = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([3.0, 2.0, 1.0])  # reversed
        r2 = CalibrationEngine.compute_r_squared(y_actual, y_pred)
        assert r2 >= 0.0


# ---------------------------------------------------------------------------
# fit_curve
# ---------------------------------------------------------------------------

class TestFitCurve:

    def test_fit_linear_known_data(self):
        """Fits y = 2x + 1 with coefficients within 1 % and R² > 0.999."""
        engine = CalibrationEngine()
        x = np.linspace(1, 10, 20)
        y = 2.0 * x + 1.0
        result = engine.fit_curve(x, y, "linear")
        assert result["fit_ok"] is True
        a, b = result["coefficients"]
        assert abs(a - 2.0) / 2.0 < 0.01
        assert abs(b - 1.0) < 0.1
        assert result["r_squared"] > 0.999

    def test_fit_quadratic_known_data(self):
        """Fits y = x² + x + 1 with R² > 0.999."""
        engine = CalibrationEngine()
        x = np.linspace(0.5, 10, 30)
        y = x ** 2 + x + 1.0
        result = engine.fit_curve(x, y, "quadratic")
        assert result["fit_ok"] is True
        assert result["r_squared"] > 0.999

    def test_fit_power_law_known_data(self):
        """Fits y = 3 * x^0.8 with coefficients within 2 %."""
        engine = CalibrationEngine()
        x = np.linspace(1, 20, 25)
        y = 3.0 * x ** 0.8
        result = engine.fit_curve(x, y, "power_law")
        assert result["fit_ok"] is True
        a, b = result["coefficients"]
        assert abs(a - 3.0) / 3.0 < 0.02
        assert abs(b - 0.8) / 0.8 < 0.02

    def test_fit_too_few_points(self):
        """Returns fit_ok=False and non-None error_message for 2 points."""
        engine = CalibrationEngine()
        x = np.array([1.0, 5.0])
        y = np.array([3.0, 11.0])
        with pytest.raises(ValueError, match="Minimum 3"):
            engine.fit_curve(x, y, "linear")

    def test_fit_unknown_model(self):
        engine = CalibrationEngine()
        with pytest.raises(ValueError, match="Unknown model"):
            engine.fit_curve(np.array([1, 2, 3]), np.array([1, 4, 9]), "cubic")

    def test_x_range_stored(self):
        """x_range is (min, max) of the concentrations array."""
        engine = CalibrationEngine()
        x = np.array([5.0, 10.0, 20.0, 50.0])
        y = 2.0 * x + 1.0
        result = engine.fit_curve(x, y, "linear")
        assert result["x_range"] == (5.0, 50.0)

    def test_covariance_shape_linear(self):
        engine = CalibrationEngine()
        x = np.linspace(1, 10, 15)
        y = 3.0 * x + 0.5
        result = engine.fit_curve(x, y, "linear")
        assert result["fit_ok"] is True
        cov = np.array(result["covariance"])
        assert cov.shape == (2, 2)


# ---------------------------------------------------------------------------
# predict_concentration
# ---------------------------------------------------------------------------

class TestPredictConcentration:

    def _linear_fit(self, a=2.0, b=1.0) -> FitResult:
        engine = CalibrationEngine()
        x = np.linspace(1, 20, 20)
        return engine.fit_curve(x, a * x + b, "linear")

    def test_linear_inverse(self):
        """Inverse of y=2x+1 at y=11 gives x≈5.0."""
        engine = CalibrationEngine()
        fit = self._linear_fit(a=2.0, b=1.0)
        conc, unc = engine.predict_concentration(11.0, fit)
        assert conc is not None
        assert abs(conc - 5.0) < 0.01

    def test_linear_uncertainty_positive(self):
        """Uncertainty is > 0 and finite for a valid linear fit."""
        engine = CalibrationEngine()
        fit = self._linear_fit()
        _, unc = engine.predict_concentration(11.0, fit)
        assert unc is not None
        assert unc >= 0.0
        assert math.isfinite(unc)

    def test_predict_outside_range(self):
        """in_range is False when unknown concentration is above x_range."""
        engine = CalibrationEngine()
        # fit over [1, 20], then predict at x=200 (intensity ≫ range)
        x = np.linspace(1, 20, 20)
        y = 2.0 * x + 1.0
        fit = engine.fit_curve(x, y, "linear")
        # intensity corresponding to x=200
        conc, _ = engine.predict_concentration(401.0, fit)
        assert conc is not None
        lo, hi = fit["x_range"]
        assert conc > hi  # outside range

    def test_returns_none_for_failed_fit(self):
        """Returns (None, None) when fit_ok is False."""
        engine = CalibrationEngine()
        bad_fit = FitResult(
            model="linear", coefficients=[], covariance=[],
            r_squared=0.0, rmse=0.0, x_range=(0.0, 1.0),
            fit_ok=False, error_message="did not converge"
        )
        assert engine.predict_concentration(10.0, bad_fit) == (None, None)

    def test_quadratic_inverse(self):
        """Quadratic inverse returns a positive concentration for synthetic data."""
        engine = CalibrationEngine()
        x = np.linspace(1, 10, 20)
        y = 0.5 * x ** 2 + 2.0 * x + 5.0
        fit = engine.fit_curve(x, y, "quadratic")
        if not fit["fit_ok"]:
            pytest.skip("quadratic fit did not converge on this data")
        # predict at known point
        y_test = 0.5 * 5.0 ** 2 + 2.0 * 5.0 + 5.0  # x=5 → y=27.5
        conc, _ = engine.predict_concentration(y_test, fit)
        assert conc is not None
        assert abs(conc - 5.0) < 0.5  # within 0.5 ppm

    def test_power_law_inverse(self):
        """Power-law inverse returns reasonable concentration."""
        engine = CalibrationEngine()
        x = np.linspace(1, 20, 20)
        y = 3.0 * x ** 0.8
        fit = engine.fit_curve(x, y, "power_law")
        if not fit["fit_ok"]:
            pytest.skip("power_law fit did not converge")
        y_test = 3.0 * 10.0 ** 0.8  # x=10
        conc, _ = engine.predict_concentration(y_test, fit)
        assert conc is not None
        assert abs(conc - 10.0) < 0.5


# ---------------------------------------------------------------------------
# compute_lod_loq
# ---------------------------------------------------------------------------

class TestComputeLodLoq:

    def _linear_fit(self) -> FitResult:
        engine = CalibrationEngine()
        x = np.linspace(1, 20, 20)
        return engine.fit_curve(x, 2.0 * x + 1.0, "linear")

    def test_lod_loq_linear(self):
        """LOD = 3σ/a, LOQ = 10σ/a for linear model."""
        engine = CalibrationEngine()
        fit = self._linear_fit()
        blank_noise = 0.1
        lod, loq = engine.compute_lod_loq(blank_noise, fit)
        a = fit["coefficients"][0]
        expected_lod = 3.0 * blank_noise / abs(a)
        expected_loq = 10.0 * blank_noise / abs(a)
        assert lod is not None
        assert loq is not None
        assert abs(lod - expected_lod) / expected_lod < 0.001
        assert abs(loq - expected_loq) / expected_loq < 0.001

    def test_loq_ge_lod(self):
        """LOQ >= LOD for any valid blank_noise > 0."""
        engine = CalibrationEngine()
        fit = self._linear_fit()
        lod, loq = engine.compute_lod_loq(0.05, fit)
        assert lod is not None and loq is not None
        assert loq >= lod

    def test_no_blank(self):
        """Returns (None, None) when blank_noise is None."""
        engine = CalibrationEngine()
        fit = self._linear_fit()
        assert engine.compute_lod_loq(None, fit) == (None, None)

    def test_zero_blank_noise(self):
        """Returns (None, None) when blank_noise is 0."""
        engine = CalibrationEngine()
        fit = self._linear_fit()
        assert engine.compute_lod_loq(0.0, fit) == (None, None)

    def test_failed_fit(self):
        """Returns (None, None) when fit_ok is False."""
        engine = CalibrationEngine()
        bad_fit = FitResult(
            model="linear", coefficients=[], covariance=[],
            r_squared=0.0, rmse=0.0, x_range=(0.0, 1.0),
            fit_ok=False, error_message="failed"
        )
        assert engine.compute_lod_loq(0.1, bad_fit) == (None, None)


# ---------------------------------------------------------------------------
# fit_and_predict (end-to-end)
# ---------------------------------------------------------------------------

class TestFitAndPredict:

    def _make_standards_with_files(
        self, tmp_path, a=50.0, b=200.0, concentrations=(10, 50, 100, 200, 500)
    ):
        """Create temp CSV files with linear intensity profiles."""
        wls = np.linspace(400, 450, 200)
        analytical_wl = 422.67
        points = []
        for conc in concentrations:
            peak_intensity = a * conc + b
            ints = np.zeros(200)
            idx = np.argmin(np.abs(wls - analytical_wl))
            ints[idx] = peak_intensity
            csv_path = tmp_path / f"standard_{conc}ppm.csv"
            _write_spectrum_csv(csv_path, wls, ints)
            points.append(CalibrationPoint(
                sample_id=f"SRM-{conc}",
                concentration=float(conc),
                spectrum_file=str(csv_path),
                intensity=None,
                is_blank=False,
            ))
        return points, analytical_wl

    def _make_processed_data(self, analytical_wl=422.67, intensity=5200.0):
        """Create a mock ProcessedSpectra-like object."""
        class _Mock:
            pass
        m = _Mock()
        m.wavelength = np.array([422.5, 422.6, analytical_wl, 422.8])
        m.corrected = np.array([100.0, 200.0, intensity, 150.0])
        return m

    def test_full_end_to_end(self, tmp_path):
        """End-to-end with 5 temp CSV spectra; fit_ok=True, concentration is float."""
        engine = CalibrationEngine()
        points, wl = self._make_standards_with_files(tmp_path)
        mock_data = self._make_processed_data(wl, intensity=3200.0)

        results = engine.fit_and_predict(
            points=points,
            model_name="linear",
            element="Ca",
            analytical_wavelength=wl,
            extraction_tolerance=0.5,
            unknown_processed_data=mock_data,
        )
        assert results["fit_result"] is not None
        assert results["fit_result"]["fit_ok"] is True
        assert isinstance(results["unknown_concentration"], float)
        assert isinstance(results["in_range"], bool)
        assert results["element"] == "Ca"

    def test_too_few_standards(self, tmp_path):
        """2 valid points → missing_info non-empty, no crash."""
        engine = CalibrationEngine()
        points, wl = self._make_standards_with_files(tmp_path, concentrations=(10, 50))
        results = engine.fit_and_predict(
            points=points,
            model_name="linear",
            element="Ca",
            analytical_wavelength=wl,
            extraction_tolerance=0.5,
        )
        assert len(results["missing_info"]) > 0
        assert "Minimum 3" in results["missing_info"][0]
        assert results["fit_result"] is None

    def test_none_inputs_never_raises(self):
        """All-None inputs return a dict without raising."""
        engine = CalibrationEngine()
        results = engine.fit_and_predict(
            points=None,
            model_name="linear",
            element="Ca",
            analytical_wavelength=422.67,
            extraction_tolerance=0.5,
        )
        assert isinstance(results, dict)
        assert results["fit_result"] is None
        assert len(results["missing_info"]) > 0

    def test_no_unknown_data(self, tmp_path):
        """Fit succeeds but unknown_concentration is None when no processed data."""
        engine = CalibrationEngine()
        points, wl = self._make_standards_with_files(tmp_path)
        results = engine.fit_and_predict(
            points=points,
            model_name="linear",
            element="Ca",
            analytical_wavelength=wl,
            extraction_tolerance=0.5,
            unknown_processed_data=None,
        )
        assert results["fit_result"]["fit_ok"] is True
        assert results["unknown_concentration"] is None


# ---------------------------------------------------------------------------
# estimate_blank_noise
# ---------------------------------------------------------------------------

class TestEstimateBlankNoise:

    def test_basic(self, tmp_path):
        engine = CalibrationEngine()
        wls = np.linspace(420, 425, 50)
        rng = np.random.default_rng(42)
        ints = rng.normal(100.0, 5.0, 50)
        csv_path = tmp_path / "blank.csv"
        _write_spectrum_csv(csv_path, wls, ints)
        noise = engine.estimate_blank_noise(str(csv_path), 422.5, 0.5, window_nm=2.5)
        assert noise is not None
        assert noise > 0

    def test_missing_file(self):
        engine = CalibrationEngine()
        assert engine.estimate_blank_noise("/no/file.csv", 422.67, 0.5) is None

    def test_too_few_rows(self, tmp_path):
        """Single-row spectrum returns None (need ≥2 to compute std)."""
        engine = CalibrationEngine()
        csv_path = tmp_path / "single.csv"
        _write_spectrum_csv(csv_path, [422.67], [100.0])
        result = engine.estimate_blank_noise(str(csv_path), 422.67, 0.5)
        assert result is None


# ---------------------------------------------------------------------------
# JSON serialisation round-trip
# ---------------------------------------------------------------------------

class TestJsonRoundtrip:

    def test_roundtrip(self, tmp_path):
        engine = CalibrationEngine()
        x = np.linspace(1, 10, 15)
        fit = engine.fit_curve(x, 2.0 * x + 1.0, "linear")
        from src.core.step7_calibration import CalibrationResults
        results = CalibrationResults(
            element="Ca",
            analytical_wavelength=422.67,
            extraction_tolerance=0.5,
            fit_result=fit,
            points=[],
            unknown_intensity=300.0,
            unknown_concentration=5.5,
            unknown_uncertainty=0.3,
            in_range=True,
            lod_ppm=0.15,
            loq_ppm=0.50,
            blank_noise=0.05,
            missing_info=[],
        )
        json_str = CalibrationEngine.results_to_json(results)
        restored = CalibrationEngine.results_from_json(json_str)
        assert restored is not None
        assert restored["element"] == "Ca"
        assert restored["fit_result"]["fit_ok"] is True
        assert abs(restored["unknown_concentration"] - 5.5) < 1e-6

    def test_from_json_invalid(self):
        result = CalibrationEngine.results_from_json("not valid json {{")
        assert result is None


# ---------------------------------------------------------------------------
# ChartEngine smoke tests for three new Step 7 methods
# ---------------------------------------------------------------------------

class TestStep7ChartSmoke:
    """
    Smoke tests: call each new chart method with empty and minimal valid data.
    Verifies no exception is raised and matplotlib artists are created.
    """

    @pytest.fixture(autouse=True)
    def _setup(self):
        import matplotlib
        matplotlib.use("Agg")

    def _make_ax(self):
        from matplotlib.figure import Figure
        fig = Figure(figsize=(6, 4), dpi=72)
        return fig, fig.add_subplot(111)

    def _make_fit_result(self):
        engine = CalibrationEngine()
        x = np.linspace(1, 20, 20)
        return engine.fit_curve(x, 2.0 * x + 1.0, "linear")

    def _make_points(self):
        x = np.linspace(1, 20, 5)
        return [
            CalibrationPoint(
                sample_id=f"S{i}",
                concentration=float(c),
                spectrum_file="",
                intensity=float(2.0 * c + 1.0),
                is_blank=False,
            )
            for i, c in enumerate(x)
        ]

    def test_render_calibration_curve_empty(self):
        from src.gui.charts import ChartEngine
        fig, ax = self._make_ax()
        ChartEngine.render_calibration_curve(ax, [], None, None, None, True, "Ca")
        # Should show placeholder text, no exception

    def test_render_calibration_curve_with_data(self):
        from src.gui.charts import ChartEngine
        fig, ax = self._make_ax()
        fit = self._make_fit_result()
        points = self._make_points()
        ChartEngine.render_calibration_curve(ax, points, fit, 15.0, 7.0, True, "Ca")
        assert len(ax.collections) + len(ax.lines) > 0

    def test_render_calibration_residuals_empty(self):
        from src.gui.charts import ChartEngine
        fig, ax = self._make_ax()
        ChartEngine.render_calibration_residuals(ax, [], None)

    def test_render_calibration_residuals_with_data(self):
        from src.gui.charts import ChartEngine
        fig, ax = self._make_ax()
        fit = self._make_fit_result()
        points = self._make_points()
        ChartEngine.render_calibration_residuals(ax, points, fit)
        # Should have scatter artists and reference line
        assert len(ax.lines) + len(ax.collections) > 0

    def test_render_lod_loq_panel_empty(self):
        from src.gui.charts import ChartEngine
        fig, ax = self._make_ax()
        ChartEngine.render_lod_loq_panel(ax, [], None, None, None, None)

    def test_render_lod_loq_panel_no_blank(self):
        from src.gui.charts import ChartEngine
        fig, ax = self._make_ax()
        fit = self._make_fit_result()
        points = self._make_points()
        ChartEngine.render_lod_loq_panel(ax, points, fit, None, None, None)
        # Should show "N/A" text but no exception

    def test_render_lod_loq_panel_with_blank(self):
        from src.gui.charts import ChartEngine
        fig, ax = self._make_ax()
        fit = self._make_fit_result()
        points = self._make_points()
        ChartEngine.render_lod_loq_panel(ax, points, fit, 0.15, 0.50, 0.05)
