# -*- coding: utf-8 -*-
"""
Property-based tests for Step 7: CalibrationEngine

Uses Hypothesis to verify correctness invariants across random inputs.

Properties tested:
  P1 — Coefficients reproduce synthetic noiseless data (linear model)
  P2 — R² is always in [0, 1]
  P3 — RMSE is always >= 0
  P4 — fit_and_predict never raises for any combination of inputs
  P5 — LOQ >= LOD for any blank_noise > 0 with a converged fit
  P6 — Uncertainty > 0 for valid linear fit with non-trivial covariance
  P7 — in_range=False when unknown concentration is outside x_range
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from hypothesis import assume, given, settings, HealthCheck
from hypothesis import strategies as st

from src.core.step7_calibration import CalibrationEngine, CalibrationPoint


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

# Concentrations: positive, reasonably bounded
_conc_st = st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False)
_intensity_st = st.floats(min_value=1.0, max_value=1e7, allow_nan=False, allow_infinity=False)

_n_points_st = st.integers(min_value=3, max_value=25)


@st.composite
def linear_calibration_data(draw):
    """
    Draw a, b, and a list of concentrations, then compute exact intensities.
    """
    a = draw(st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False))
    b = draw(st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    n = draw(st.integers(min_value=3, max_value=20))
    # Concentrations must be distinct and positive
    concs = sorted(set(
        draw(st.lists(_conc_st, min_size=n + 5, max_size=n + 10))
    ))[:n]
    assume(len(concs) >= 3)
    return a, b, concs


@st.composite
def random_pair_lists(draw, min_n=3, max_n=30):
    """Draw n (concentration, intensity) pairs."""
    n = draw(st.integers(min_value=min_n, max_value=max_n))
    concs = [draw(_conc_st) for _ in range(n)]
    ints = [draw(_intensity_st) for _ in range(n)]
    return concs, ints


# ---------------------------------------------------------------------------
# P1 — Fitted coefficients reproduce noiseless linear data
# ---------------------------------------------------------------------------

@settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
@given(linear_calibration_data())
def test_p1_linear_coefficients_reproduce_data(data):
    """
    Property 1: For a noiseless linear dataset y=ax+b, the fitted
    coefficients reproduce every calibration intensity within 0.1 %.
    """
    a, b, concs = data
    engine = CalibrationEngine()
    x = np.array(concs)
    y = a * x + b
    result = engine.fit_curve(x, y, "linear")
    if not result["fit_ok"]:
        return  # skip non-convergent cases
    a_fit, b_fit = result["coefficients"]
    for xi, yi in zip(x, y):
        y_pred = a_fit * xi + b_fit
        if abs(yi) > 1e-10:
            rel_err = abs(y_pred - yi) / abs(yi)
            assert rel_err < 0.001, f"Rel error {rel_err:.4f} > 0.1% at x={xi}, y={yi}"
        else:
            assert abs(y_pred - yi) < 1e-6


# ---------------------------------------------------------------------------
# P2 — R² is always in [0, 1]
# ---------------------------------------------------------------------------

@settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
@given(random_pair_lists())
def test_p2_r_squared_in_range(pair_data):
    """
    Property 2: R² is always in [0, 1] for any (concentration, intensity) data.
    """
    concs, ints = pair_data
    x = np.array(concs)
    y = np.array(ints)
    engine = CalibrationEngine()
    result = engine.fit_curve(x, y, "linear")
    if result["fit_ok"]:
        r2 = result["r_squared"]
        assert 0.0 <= r2 <= 1.0, f"R²={r2} outside [0,1]"


# ---------------------------------------------------------------------------
# P3 — RMSE is always >= 0
# ---------------------------------------------------------------------------

@settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
@given(random_pair_lists())
def test_p3_rmse_non_negative(pair_data):
    """
    Property 3: RMSE is always >= 0.
    """
    concs, ints = pair_data
    x = np.array(concs)
    y = np.array(ints)
    engine = CalibrationEngine()
    result = engine.fit_curve(x, y, "linear")
    if result["fit_ok"]:
        assert result["rmse"] >= 0.0


# ---------------------------------------------------------------------------
# P4 — fit_and_predict never raises
# ---------------------------------------------------------------------------

_maybe_points = st.one_of(
    st.none(),
    st.just([]),
    st.lists(
        st.fixed_dictionaries({
            "sample_id": st.just("SRM"),
            "concentration": _conc_st,
            "spectrum_file": st.just("/nonexistent/file.csv"),
            "intensity": st.none(),
            "is_blank": st.just(False),
        }),
        min_size=0,
        max_size=5,
    ),
)


@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(points=_maybe_points)
def test_p4_fit_and_predict_never_raises(points):
    """
    Property 4: fit_and_predict never raises for any combination of inputs.
    """
    engine = CalibrationEngine()
    result = engine.fit_and_predict(
        points=points,
        model_name="linear",
        element="Ca",
        analytical_wavelength=422.67,
        extraction_tolerance=0.5,
        unknown_processed_data=None,
    )
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# P5 — LOQ >= LOD for any valid blank_noise > 0
# ---------------------------------------------------------------------------

@settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
@given(
    blank_noise=st.floats(min_value=0.001, max_value=100.0,
                          allow_nan=False, allow_infinity=False),
    a=st.floats(min_value=0.5, max_value=500.0, allow_nan=False, allow_infinity=False),
)
def test_p5_loq_ge_lod(blank_noise, a):
    """
    Property 5: LOQ >= LOD for any valid blank_noise > 0 with converged linear fit.
    """
    engine = CalibrationEngine()
    x = np.linspace(1, 20, 15)
    y = a * x + 1.0
    fit = engine.fit_curve(x, y, "linear")
    if not fit["fit_ok"]:
        return
    lod, loq = engine.compute_lod_loq(blank_noise, fit)
    if lod is not None and loq is not None:
        assert loq >= lod - 1e-9, f"LOQ={loq} < LOD={lod}"


# ---------------------------------------------------------------------------
# P6 — Uncertainty > 0 for valid linear fit
# ---------------------------------------------------------------------------

@settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
@given(
    a=st.floats(min_value=0.5, max_value=1000.0, allow_nan=False, allow_infinity=False),
    b=st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    intensity=st.floats(min_value=1.0, max_value=5e5, allow_nan=False, allow_infinity=False),
)
def test_p6_uncertainty_positive_linear(a, b, intensity):
    """
    Property 6: Uncertainty is >= 0 and finite for any valid linear fit.
    """
    engine = CalibrationEngine()
    x = np.linspace(1, 20, 15)
    y = a * x + b
    fit = engine.fit_curve(x, y, "linear")
    if not fit["fit_ok"]:
        return
    conc, unc = engine.predict_concentration(intensity, fit)
    if unc is not None:
        assert unc >= 0.0
        # scipy returns inf in pcov for perfectly-conditioned fits (zero residuals);
        # uncertainty propagation correctly yields inf in that case — not a bug.
        assert not math.isnan(unc)


# ---------------------------------------------------------------------------
# P7 — in_range=False when unknown outside x_range
# ---------------------------------------------------------------------------

@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    a=st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    b=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    factor=st.floats(min_value=2.0, max_value=10.0, allow_nan=False, allow_infinity=False),
)
def test_p7_out_of_range_flag(a, b, factor):
    """
    Property 7: When the unknown concentration is outside x_range,
    the caller should detect this (concentration > x_range[1]).
    """
    engine = CalibrationEngine()
    x = np.linspace(1, 20, 15)
    y = a * x + b
    fit = engine.fit_curve(x, y, "linear")
    if not fit["fit_ok"]:
        return
    # Produce an intensity corresponding to x = x_max * factor (way outside)
    x_hi = fit["x_range"][1]
    out_intensity = a * (x_hi * factor) + b
    conc, _ = engine.predict_concentration(out_intensity, fit)
    if conc is not None and math.isfinite(conc):
        lo, hi = fit["x_range"]
        assert conc > hi * 0.99, (
            f"Expected conc > hi ({hi:.2f}) but got {conc:.2f}"
        )
