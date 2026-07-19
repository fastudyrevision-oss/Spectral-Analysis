# -*- coding: utf-8 -*-
"""
Property-based tests for PerformanceCalculator (Step 6).

Feature: step6-model-performance
Properties 1-6 as defined in design.md
"""

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.core.step6_performance import PerformanceCalculator, PerformanceResults
from src.io.data_models import DetectedPeak, NISTMatch, ProcessedSpectra

calculator = PerformanceCalculator()


# ---------------------------------------------------------------------------
# Helpers / strategies
# ---------------------------------------------------------------------------

def make_processed_spectra(wl_array, corrected_array):
    """Build a minimal ProcessedSpectra from two numpy arrays."""
    n = len(wl_array)
    return ProcessedSpectra(
        wavelength=np.asarray(wl_array, dtype=float),
        raw=np.ones(n, dtype=float),
        smoothed_sg=np.ones(n, dtype=float),
        baseline_als=np.zeros(n, dtype=float),
        corrected=np.asarray(corrected_array, dtype=float),
        baseline_iterations=[],
    )


def make_nist_match(observed_wl: float, element: str = "Ca") -> NISTMatch:
    return NISTMatch(
        observed_wl=observed_wl,
        matched_wl=observed_wl,
        delta=0.0,
        aki=1e6,
        relative_intensity=100.0,
        score=1e8,
        element=element,
    )


def make_detected_peak(wl: float, intensity: float = 500.0) -> DetectedPeak:
    return DetectedPeak(wavelength=wl, intensity=intensity)


# ---------------------------------------------------------------------------
# Property 3 — Confidence tier classification is total and correct
# Feature: step6-model-performance, Property 3: Confidence tier classification is total and correct
# Validates: Requirements 3.4, 5.2, 5.3, 5.4
# ---------------------------------------------------------------------------

@given(wins=st.integers(min_value=0, max_value=500))
def test_property3_classify_confidence_tier_total(wins):
    """For any non-negative wins, result is always one of the three valid tiers."""
    tier = calculator._classify_confidence_tier(wins)
    assert tier in {"High", "Medium", "Low"}


def test_property3_boundary_values():
    """Boundary values 0, 2, 3, 9, 10 and 100 each map to the correct tier."""
    assert calculator._classify_confidence_tier(0) == "Low"
    assert calculator._classify_confidence_tier(2) == "Low"
    assert calculator._classify_confidence_tier(3) == "Medium"
    assert calculator._classify_confidence_tier(9) == "Medium"
    assert calculator._classify_confidence_tier(10) == "High"
    assert calculator._classify_confidence_tier(100) == "High"


@given(wins=st.integers(min_value=10, max_value=500))
def test_property3_high_tier_for_wins_ge_10(wins):
    assert calculator._classify_confidence_tier(wins) == "High"


@given(wins=st.integers(min_value=3, max_value=9))
def test_property3_medium_tier_for_3_to_9(wins):
    assert calculator._classify_confidence_tier(wins) == "Medium"


@given(wins=st.integers(min_value=0, max_value=2))
def test_property3_low_tier_for_lt_3(wins):
    assert calculator._classify_confidence_tier(wins) == "Low"


# ---------------------------------------------------------------------------
# Property 4 — All classification metrics are clamped to [0, 1]
# Feature: step6-model-performance, Property 4: All classification metrics are clamped to [0, 1]
# Validates: Requirements 4.2, 4.3, 4.4
# ---------------------------------------------------------------------------

@given(
    tp=st.integers(min_value=0, max_value=1000),
    fp=st.integers(min_value=0, max_value=1000),
    fn=st.integers(min_value=0, max_value=1000),
)
def test_property4_metrics_clamped_to_unit_interval(tp, fp, fn):
    """Every metric returned by _compute_metrics is in [0.0, 1.0]."""
    stage_counts = {"stage1": tp + fp, "stage2": tp + fp, "stage5": tp}
    # avg_lines_per_element chosen so fn = fn; unique_elements=1
    # fn = max(0, 1 * avg_lines - stage1)  →  avg_lines = fn + stage1
    unique_elements = 1
    avg_lines = float(fn + tp + fp)
    result = calculator._compute_metrics(stage_counts, unique_elements, avg_lines)

    for key in ("accuracy", "precision", "recall", "f1_score"):
        value = result[key]
        assert value is not None, f"{key} should not be None"
        assert isinstance(value, float), f"{key} should be float"
        assert 0.0 <= value <= 1.0, f"{key}={value} is out of [0, 1]"


def test_property4_zero_denominator_precision():
    """When TP+FP=0, Precision must be 0.0 (no ZeroDivisionError)."""
    result = calculator._compute_metrics({"stage1": 0, "stage2": 0, "stage5": 0}, 0, 0.0)
    assert result["precision"] == 0.0


def test_property4_zero_denominator_recall():
    """When TP+FN=0, Recall must be 0.0 (no ZeroDivisionError)."""
    # TP=0, FP=0, FN=0 → recall = 0/(0+0)
    result = calculator._compute_metrics({"stage1": 0, "stage2": 0, "stage5": 0}, 0, 0.0)
    assert result["recall"] == 0.0


# ---------------------------------------------------------------------------
# Property 5 — SBR Improvement handles all denominator cases correctly
# Feature: step6-model-performance, Property 5: SBR Improvement handles all denominator cases correctly
# Validates: Requirements 4.5
# ---------------------------------------------------------------------------

def test_property5_none_when_processed_data_is_none():
    """_compute_sbr returns None when processed_data is None."""
    result = calculator._compute_sbr([300.0], [], None)
    assert result is None


def test_property5_inf_when_zero_background():
    """_compute_sbr returns inf when background mean is zero."""
    wl = np.array([300.0, 300.05, 500.0, 600.0])
    intensity = np.array([100.0, 100.0, 0.0, 0.0])  # background = 0
    ps = make_processed_spectra(wl, intensity)
    # Validated peaks near 300.0, so background (500, 600) has mean=0
    result = calculator._compute_sbr([300.0], [], ps)
    assert result == float("inf")


@given(
    peak_int=st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    bg_int=st.floats(min_value=0.01, max_value=1e5, allow_nan=False, allow_infinity=False),
)
def test_property5_positive_ratio(peak_int, bg_int):
    """When both peak and background are positive, result equals mean_peak / mean_bg."""
    # Two-wavelength spectrum: one peak point, one background point
    wl = np.array([300.0, 600.0])
    intensity = np.array([peak_int, bg_int])
    ps = make_processed_spectra(wl, intensity)
    result = calculator._compute_sbr([300.0], [], ps)
    expected = peak_int / bg_int
    assert result is not None
    assert not math.isnan(result)
    assert math.isclose(result, expected, rel_tol=1e-6)


def test_property5_no_validated_peaks_returns_none():
    """When validated_peak_wls is empty, no peak matches → returns None."""
    wl = np.array([300.0, 400.0, 500.0])
    intensity = np.array([100.0, 200.0, 150.0])
    ps = make_processed_spectra(wl, intensity)
    result = calculator._compute_sbr([], [], ps)
    assert result is None


# ---------------------------------------------------------------------------
# Property 2 — Pipeline stage counts satisfy monotonicity and derivation invariants
# Feature: step6-model-performance, Property 2: Pipeline stage counts satisfy monotonicity and derivation invariants
# Validates: Requirements 3.3
# ---------------------------------------------------------------------------

def _make_validation_df(n_rows: int, vc_values) -> pd.DataFrame:
    """Build a minimal validation_results DataFrame."""
    return pd.DataFrame({
        "Wavelength_nm": [float(300 + i) for i in range(n_rows)],
        "Validation_Coefficient": list(vc_values),
        "Element": ["Ca"] * n_rows,
    })


@given(
    n_peaks=st.integers(min_value=0, max_value=20),
    n_matches=st.integers(min_value=0, max_value=20),
    vc_values=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        min_size=0,
        max_size=20,
    ),
)
@settings(max_examples=100)
def test_property2_stage_counts_invariants(n_peaks, n_matches, vc_values):
    """Pipeline stage counts must satisfy stage1=len(peaks), stage2<=stage1, stage5<=stage4."""
    peaks = [make_detected_peak(float(300 + i)) for i in range(n_peaks)]
    matches = [make_nist_match(float(300 + i % max(n_peaks, 1))) for i in range(n_matches)]

    n_vc = len(vc_values)
    if n_vc == 0:
        validation_df = pd.DataFrame({
            "Wavelength_nm": pd.Series([], dtype=float),
            "Validation_Coefficient": pd.Series([], dtype=float),
            "Element": pd.Series([], dtype=str),
        })
    else:
        validation_df = _make_validation_df(n_vc, vc_values)

    # Build a minimal ranking_df
    ranking_df = pd.DataFrame({
        "Element": ["Ca"],
        "Wins": [5],
        "Total_Score": [1000.0],
        "Avg_Score": [200.0],
    })
    analysis_results = {"ranking_df": ranking_df}

    counts = calculator._compute_stage_counts(peaks, matches, analysis_results, validation_df)

    stage1 = counts["stage1"]
    stage2 = counts["stage2"]
    stage4 = counts["stage4"]
    stage5 = counts["stage5"]

    # Invariant: stage1 = len(peaks)
    assert stage1 == n_peaks, f"stage1 {stage1} != n_peaks {n_peaks}"

    # Invariant: stage2 <= stage1
    assert stage2 <= stage1, f"stage2 {stage2} > stage1 {stage1}"

    # Invariant: stage5 <= stage4
    assert stage5 <= stage4, f"stage5 {stage5} > stage4 {stage4}"

    # Invariant: stage4 counts rows with VC >= 0.5
    expected_stage4 = sum(1 for v in vc_values if v >= 0.50)
    assert stage4 == expected_stage4, f"stage4 {stage4} != expected {expected_stage4}"

    # Invariant: stage5 counts rows with VC >= 0.7
    expected_stage5 = sum(1 for v in vc_values if v >= 0.70)
    assert stage5 == expected_stage5, f"stage5 {stage5} != expected {expected_stage5}"


# ---------------------------------------------------------------------------
# Property 1 — Missing upstream data never raises
# Feature: step6-model-performance, Property 1: Missing upstream data never raises
# Validates: Requirements 3.2
# ---------------------------------------------------------------------------

@given(
    detected_peaks=st.one_of(st.none(), st.just([])),
    matches=st.one_of(st.none(), st.just([])),
    analysis_results=st.one_of(st.none(), st.just({})),
    validation_results=st.one_of(st.none(), st.just(pd.DataFrame())),
)
def test_property1_compute_never_raises(detected_peaks, matches, analysis_results, validation_results):
    """compute() must always return a dict and never raise, even with all-None/empty inputs."""
    result = calculator.compute(
        detected_peaks=detected_peaks,
        matches=matches,
        analysis_results=analysis_results,
        validation_results=validation_results,
        processed_data=None,
    )
    assert isinstance(result, dict)
    # Must have all expected keys
    for key in (
        "pipeline_stages", "element_rows", "accuracy", "precision",
        "recall", "f1_score", "sbr_improvement", "heatmap_matrix",
        "peak_labels", "element_labels", "ranking_df", "missing_steps",
    ):
        assert key in result, f"Key '{key}' missing from PerformanceResults"


def test_property1_missing_steps_listed_when_inputs_none():
    """When all inputs are None, missing_steps should list all four upstream steps."""
    result = calculator.compute(
        detected_peaks=None,
        matches=None,
        analysis_results=None,
        validation_results=None,
    )
    missing = result["missing_steps"]
    assert "Step 2" in missing
    assert "Step 3" in missing
    assert "Step 4" in missing
    assert "Step 5" in missing


def test_property1_metrics_none_when_inputs_missing():
    """When inputs are missing, all metric fields must be None."""
    result = calculator.compute(
        detected_peaks=None,
        matches=None,
        analysis_results=None,
        validation_results=None,
    )
    assert result["accuracy"] is None
    assert result["precision"] is None
    assert result["recall"] is None
    assert result["f1_score"] is None
    assert result["sbr_improvement"] is None
    assert result["pipeline_stages"] is None


# ---------------------------------------------------------------------------
# Property 6 — Correlation heatmap matrix dimensions and values match inputs
# Feature: step6-model-performance, Property 6: Correlation heatmap matrix dimensions and values match inputs
# Validates: Requirements 3.5, 7.1
# ---------------------------------------------------------------------------

@given(
    elements=st.lists(
        st.text(alphabet=st.characters(whitelist_categories=("Lu",)), min_size=1, max_size=3),
        min_size=1,
        max_size=5,
        unique=True,
    ),
    n_wls=st.integers(min_value=1, max_value=8),
    vc_values=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        min_size=1,
        max_size=8,
    ),
)
@settings(max_examples=80)
def test_property6_heatmap_shape(elements, n_wls, vc_values):
    """Matrix shape must equal (N_unique_wls, M_unique_elements) from matches."""
    assume(len(vc_values) >= 1)

    # Build validation_results: one row per wavelength (unique wavelengths)
    unique_wls = [float(300 + i) for i in range(n_wls)]
    # Assign each vc_value to a wavelength (cycle through)
    rows = []
    for idx, vc in enumerate(vc_values):
        wl = unique_wls[idx % n_wls]
        rows.append({"Wavelength_nm": wl, "Validation_Coefficient": vc})
    validation_df = pd.DataFrame(rows)

    # Build matches: each wavelength maps to the first element
    matches = [
        make_nist_match(observed_wl=wl, element=elements[0])
        for wl in unique_wls
    ]

    matrix, peak_labels, element_labels = calculator._build_heatmap(validation_df, matches)

    # Must return arrays of correct type
    assert isinstance(matrix, np.ndarray)
    assert isinstance(peak_labels, list)
    assert isinstance(element_labels, list)

    # Shape: rows = N unique wavelengths in validation_df, cols = M unique elements
    n_unique_wls = len(pd.to_numeric(validation_df["Wavelength_nm"], errors="coerce").dropna().unique())
    assert matrix.shape[0] == n_unique_wls, (
        f"Expected {n_unique_wls} rows, got {matrix.shape[0]}"
    )
    # At least 1 element column
    assert matrix.shape[1] >= 1


@given(
    vc=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_property6_heatmap_cell_equals_vc(vc):
    """Cell [i, j] must equal the Validation_Coefficient when a match exists."""
    wl = 400.0
    element = "Ca"
    validation_df = pd.DataFrame({
        "Wavelength_nm": [wl],
        "Validation_Coefficient": [vc],
    })
    matches = [make_nist_match(observed_wl=wl, element=element)]

    matrix, peak_labels, element_labels = calculator._build_heatmap(validation_df, matches)

    assert matrix.shape == (1, 1)
    assert math.isclose(matrix[0, 0], vc, rel_tol=1e-9, abs_tol=1e-12)


def test_property6_missing_pairs_are_zero():
    """Cells where no match exists must be 0.0."""
    # Two wavelengths; matches only cover one of them for element "Ca"
    validation_df = pd.DataFrame({
        "Wavelength_nm": [300.0, 400.0],
        "Validation_Coefficient": [0.8, 0.6],
    })
    matches = [make_nist_match(observed_wl=300.0, element="Ca")]
    # 400.0 has a VC row but no match → should be 0.0 in the matrix

    matrix, peak_labels, element_labels = calculator._build_heatmap(validation_df, matches)

    assert matrix.shape == (2, 1)
    assert math.isclose(matrix[0, 0], 0.8, rel_tol=1e-9)
    assert math.isclose(matrix[1, 0], 0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# Integration smoke test — full compute() with realistic data
# ---------------------------------------------------------------------------

def test_compute_full_pipeline_returns_valid_results():
    """Smoke test: compute() with realistic data populates all fields."""
    # Use 6001 points over 200-800 nm so the step is 0.1 nm — peaks will
    # land exactly on a wavelength grid point within the 0.1 nm tolerance.
    wl = np.linspace(200.0, 800.0, 6001)   # step = 0.1 nm

    # Pick wavelengths that are exactly in the array
    peak_wl1 = wl[1000]   # 300.0 nm
    peak_wl2 = wl[2000]   # 400.0 nm

    peaks = [make_detected_peak(peak_wl1, 500.0), make_detected_peak(peak_wl2, 700.0)]
    matches = [make_nist_match(peak_wl1, "Ca"), make_nist_match(peak_wl2, "Ca")]
    ranking_df = pd.DataFrame({
        "Element": ["Ca"],
        "Wins": [12],
        "Total_Score": [5000.0],
        "Avg_Score": [416.0],
    })
    analysis_results = {"ranking_df": ranking_df}
    validation_df = pd.DataFrame({
        "Wavelength_nm": [peak_wl1, peak_wl2],
        "Validation_Coefficient": [0.85, 0.72],
        "Element": ["Ca", "Ca"],
    })

    corrected = np.ones(6001) * 50.0
    corrected[1000] = 500.0
    corrected[2000] = 700.0
    ps = make_processed_spectra(wl, corrected)

    result = calculator.compute(
        detected_peaks=peaks,
        matches=matches,
        analysis_results=analysis_results,
        validation_results=validation_df,
        processed_data=ps,
    )

    assert isinstance(result, dict)
    assert result["pipeline_stages"] is not None
    assert result["pipeline_stages"]["stage1_detected"] == 2

    # Element rows
    assert len(result["element_rows"]) == 1
    assert result["element_rows"][0]["confidence_tier"] == "High"

    # Metrics
    assert result["accuracy"] is not None
    assert 0.0 <= result["accuracy"] <= 1.0
    assert result["precision"] is not None
    assert result["recall"] is not None
    assert result["f1_score"] is not None

    # SBR — with dense grid peak wavelengths hit exactly, background is 50.0
    assert result["sbr_improvement"] is not None

    # Heatmap
    assert result["heatmap_matrix"] is not None
    assert result["missing_steps"] == []
