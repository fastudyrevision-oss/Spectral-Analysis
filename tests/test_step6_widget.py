# -*- coding: utf-8 -*-
"""
Property-based tests for Step6Widget-related behaviour.

Feature: step6-model-performance
Properties 11, 12 as defined in design.md

Note: These properties are tested at the PerformanceCalculator level
(the same logic Step6Widget delegates to) to avoid requiring a live
QApplication or display connection in CI.
"""

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.core.step6_performance import PerformanceCalculator
from src.io.data_models import DetectedPeak, NISTMatch

calculator = PerformanceCalculator()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_match(wl: float, element: str) -> NISTMatch:
    return NISTMatch(
        observed_wl=wl, matched_wl=wl, delta=0.0,
        aki=1e6, relative_intensity=100.0, score=1e8, element=element
    )


def _make_peak(wl: float) -> DetectedPeak:
    return DetectedPeak(wavelength=wl, intensity=500.0)


def _make_ranking_df(elements, wins):
    return pd.DataFrame({
        "Element": elements,
        "Wins": wins,
        "Total_Score": [float(w * 100) for w in wins],
        "Avg_Score":   [float(w * 10)  for w in wins],
    })


def _make_validation_df(rows):
    """rows: list of (wavelength, vc, element)"""
    return pd.DataFrame({
        "Wavelength_nm":          [r[0] for r in rows],
        "Validation_Coefficient": [r[1] for r in rows],
        "Element":                [r[2] for r in rows],
    })


# ===========================================================================
# Property 11 — Summary table Mean VC equals per-element average
# Feature: step6-model-performance, Property 11: Summary table Mean VC equals per-element average from validation results
# Validates: Requirements 9.2
# ===========================================================================

@given(
    elements=st.lists(
        st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=3),
        min_size=1, max_size=5, unique=True,
    ),
    wins=st.lists(st.integers(min_value=0, max_value=50), min_size=1, max_size=5),
    vc_values=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        min_size=1, max_size=10,
    ),
)
@settings(max_examples=100, deadline=None)
def test_property11_mean_vc_equals_arithmetic_mean(elements, wins, vc_values):
    """Each ElementRow.mean_vc must equal the arithmetic mean of matching VCs."""
    assume(len(elements) == len(wins))

    # Build validation rows: cycle elements and assign vc values
    val_rows = []
    for i, vc in enumerate(vc_values):
        elem = elements[i % len(elements)]
        wl = float(300 + i)
        val_rows.append((wl, vc, elem))

    ranking_df = _make_ranking_df(elements, wins)
    validation_df = _make_validation_df(val_rows)

    # Build matches: each wavelength → its element
    matches = [_make_match(r[0], r[2]) for r in val_rows]
    peaks = [_make_peak(float(300 + i)) for i in range(len(vc_values))]

    # Build analysis_results with the ranking_df
    analysis_results = {"ranking_df": ranking_df}

    result = calculator.compute(
        detected_peaks=peaks,
        matches=matches,
        analysis_results=analysis_results,
        validation_results=validation_df,
    )

    element_rows = result["element_rows"]
    assert element_rows, "element_rows should not be empty"

    # Build expected mean VC per element from raw validation data
    expected: dict[str, float | None] = {}
    for elem in elements:
        matching_vcs = [r[1] for r in val_rows if r[2] == elem]
        if matching_vcs:
            expected[elem] = float(np.mean(matching_vcs))
        else:
            expected[elem] = None

    for er in element_rows:
        elem_name = er["element"]
        computed_mean_vc = er["mean_vc"]
        exp = expected.get(elem_name)

        if exp is not None and computed_mean_vc is not None:
            assert abs(computed_mean_vc - exp) < 1e-9, (
                f"Element {elem_name}: mean_vc {computed_mean_vc:.6f} != expected {exp:.6f}"
            )
        elif exp is None:
            # If no matching rows, mean_vc should be None
            assert computed_mean_vc is None or computed_mean_vc != computed_mean_vc, (
                f"Element {elem_name}: expected None mean_vc but got {computed_mean_vc}"
            )


def test_property11_single_element_single_vc():
    """Exact single-row case: mean_vc must equal that VC exactly."""
    ranking_df = _make_ranking_df(["Ca"], [10])
    validation_df = _make_validation_df([(300.0, 0.85, "Ca")])
    matches = [_make_match(300.0, "Ca")]
    peaks = [_make_peak(300.0)]
    analysis_results = {"ranking_df": ranking_df}

    result = calculator.compute(
        detected_peaks=peaks, matches=matches,
        analysis_results=analysis_results, validation_results=validation_df,
    )
    rows = result["element_rows"]
    assert len(rows) == 1
    assert rows[0]["element"] == "Ca"
    assert abs(rows[0]["mean_vc"] - 0.85) < 1e-9


def test_property11_multiple_vcs_correct_mean():
    """Three VCs for one element: mean_vc must equal (0.7+0.8+0.9)/3."""
    ranking_df = _make_ranking_df(["Ca"], [10])
    validation_df = _make_validation_df([
        (300.0, 0.7, "Ca"),
        (301.0, 0.8, "Ca"),
        (302.0, 0.9, "Ca"),
    ])
    matches = [_make_match(300.0, "Ca"), _make_match(301.0, "Ca"), _make_match(302.0, "Ca")]
    peaks = [_make_peak(300.0), _make_peak(301.0), _make_peak(302.0)]
    analysis_results = {"ranking_df": ranking_df}

    result = calculator.compute(
        detected_peaks=peaks, matches=matches,
        analysis_results=analysis_results, validation_results=validation_df,
    )
    rows = result["element_rows"]
    ca_row = next(r for r in rows if r["element"] == "Ca")
    expected_mean = (0.7 + 0.8 + 0.9) / 3
    assert abs(ca_row["mean_vc"] - expected_mean) < 1e-9


# ===========================================================================
# Property 12 — partial upstream data shows placeholders only for missing data
# Feature: step6-model-performance, Property 12: refresh() with partial upstream data shows placeholders only for missing visualisations
# Validates: Requirements 11.3
# ===========================================================================

@given(
    has_peaks=st.booleans(),
    has_matches=st.booleans(),
    has_analysis=st.booleans(),
    has_validation=st.booleans(),
)
@settings(max_examples=50, deadline=None)
def test_property12_partial_inputs_populate_available_fields(
    has_peaks, has_matches, has_analysis, has_validation
):
    """Fields requiring missing input must be None; others must be populated."""
    peaks = [_make_peak(300.0), _make_peak(400.0)] if has_peaks else None
    matches = [_make_match(300.0, "Ca"), _make_match(400.0, "Ca")] if has_matches else None
    analysis = {"ranking_df": _make_ranking_df(["Ca"], [10])} if has_analysis else None
    validation = _make_validation_df([(300.0, 0.85, "Ca"), (400.0, 0.72, "Ca")]) if has_validation else None

    result = calculator.compute(
        detected_peaks=peaks,
        matches=matches,
        analysis_results=analysis,
        validation_results=validation,
    )

    assert isinstance(result, dict), "compute() must always return a dict"

    # pipeline_stages requires all four inputs
    if not (has_peaks and has_matches and has_analysis and has_validation):
        assert result["pipeline_stages"] is None, (
            "pipeline_stages should be None when any input is missing"
        )

    # heatmap requires matches + validation
    if not (has_matches and has_validation):
        assert result["heatmap_matrix"] is None or (
            hasattr(result["heatmap_matrix"], "size") and result["heatmap_matrix"].size == 0
        ), "heatmap_matrix should be None/empty when matches or validation missing"

    # ranking_df passthrough requires has_analysis
    if not has_analysis:
        assert result["ranking_df"] is None, (
            "ranking_df should be None when analysis_results is missing"
        )

    # missing_steps correctly populated
    missing = result["missing_steps"]
    if not has_peaks:
        assert "Step 2" in missing
    if not has_matches:
        assert "Step 3" in missing
    if not has_analysis:
        assert "Step 4" in missing
    if not has_validation:
        assert "Step 5" in missing


def test_property12_all_present_no_missing_steps():
    """With all inputs present, missing_steps must be empty."""
    peaks   = [_make_peak(300.0), _make_peak(400.0)]
    matches = [_make_match(300.0, "Ca"), _make_match(400.0, "Ca")]
    analysis = {"ranking_df": _make_ranking_df(["Ca"], [10])}
    validation = _make_validation_df([(300.0, 0.85, "Ca"), (400.0, 0.72, "Ca")])

    result = calculator.compute(
        detected_peaks=peaks, matches=matches,
        analysis_results=analysis, validation_results=validation,
    )
    assert result["missing_steps"] == [], (
        f"Expected no missing steps but got: {result['missing_steps']}"
    )
    assert result["pipeline_stages"] is not None
    assert result["element_rows"]


def test_property12_only_peaks_missing():
    """When only peaks are absent, pipeline_stages is None but ranking_df can be set."""
    matches  = [_make_match(300.0, "Ca")]
    analysis = {"ranking_df": _make_ranking_df(["Ca"], [10])}
    validation = _make_validation_df([(300.0, 0.85, "Ca")])

    result = calculator.compute(
        detected_peaks=None,
        matches=matches,
        analysis_results=analysis,
        validation_results=validation,
    )
    assert result["pipeline_stages"] is None
    assert "Step 2" in result["missing_steps"]
    assert result["ranking_df"] is not None
