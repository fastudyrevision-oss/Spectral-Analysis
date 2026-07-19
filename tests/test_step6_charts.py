# -*- coding: utf-8 -*-
"""
Property-based tests for the four new ChartEngine static methods (Step 6).

Feature: step6-model-performance
Properties 7, 8, 9, 10 as defined in design.md
"""

import matplotlib
matplotlib.use("Agg")  # headless backend — must be set before pyplot import

import math
import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
import matplotlib.pyplot as plt

from src.gui.charts import ChartEngine
from src.gui.theme import C_BG_DEEP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ranking_df(elements, wins):
    """Build a minimal ranking_df."""
    n = len(elements)
    return pd.DataFrame({
        "Element": elements,
        "Wins": wins,
        "Total_Score": [float(w * 100) for w in wins],
        "Avg_Score": [float(w * 10) for w in wins],
    })


def _make_fig_ax():
    fig, ax = plt.subplots()
    return fig, ax


def _make_fig_two_axes():
    fig, (ax, ax2) = plt.subplots(1, 2)
    return fig, ax, ax2


# ---------------------------------------------------------------------------
# Property 7 — Element ranking bar chart bars appear in descending order
# Feature: step6-model-performance, Property 7: Element ranking bar chart bars appear in descending order
# Validates: Requirements 5.1
# ---------------------------------------------------------------------------

@given(
    wins=st.lists(
        st.integers(min_value=0, max_value=100),
        min_size=1,
        max_size=15,
    )
)
@settings(max_examples=100, deadline=None)
def test_property7_bar_order_descending(wins):
    """Bar widths must be non-decreasing from bottom to top (barh bottom-to-top order)."""
    assume(len(wins) >= 1)
    elements = [f"El{i}" for i in range(len(wins))]
    ranking_df = _make_ranking_df(elements, wins)

    fig, ax = _make_fig_ax()
    try:
        ChartEngine.render_element_ranking_fig7(ax, ranking_df)
        bar_widths = [patch.get_width() for patch in ax.patches]
        # barh draws bottom-to-top; the method reverses the df so the highest-wins
        # element is at the top. That means bar_widths[0] <= bar_widths[1] <= ...
        for i in range(len(bar_widths) - 1):
            assert bar_widths[i] <= bar_widths[i + 1] + 1e-9, (
                f"Bar {i} width {bar_widths[i]} > bar {i+1} width {bar_widths[i+1]} "
                f"(not non-ascending from top to bottom)"
            )
    finally:
        plt.close(fig)


def test_property7_single_element_no_error():
    """Single-row ranking_df renders without error."""
    ranking_df = _make_ranking_df(["Ca"], [5])
    fig, ax = _make_fig_ax()
    try:
        ChartEngine.render_element_ranking_fig7(ax, ranking_df)
        assert len(ax.patches) == 1
    finally:
        plt.close(fig)


def test_property7_placeholder_on_empty_df():
    """Empty ranking_df renders placeholder, no bars."""
    fig, ax = _make_fig_ax()
    try:
        ChartEngine.render_element_ranking_fig7(ax, pd.DataFrame())
        assert len(ax.patches) == 0
    finally:
        plt.close(fig)


def test_property7_placeholder_on_none():
    """None ranking_df renders placeholder, no bars."""
    fig, ax = _make_fig_ax()
    try:
        ChartEngine.render_element_ranking_fig7(ax, None)
        assert len(ax.patches) == 0
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# Property 8 — Bar chart annotations equal number of bars
# Feature: step6-model-performance, Property 8: Bar chart annotations equal number of bars
# Validates: Requirements 5.5
# ---------------------------------------------------------------------------

@given(
    wins=st.lists(
        st.integers(min_value=0, max_value=100),
        min_size=1,
        max_size=15,
    )
)
@settings(max_examples=100, deadline=None)
def test_property8_annotation_count_equals_bar_count(wins):
    """Exactly K numeric text annotations exist for K-row ranking_df."""
    elements = [f"El{i}" for i in range(len(wins))]
    ranking_df = _make_ranking_df(elements, wins)
    k = len(wins)

    fig, ax = _make_fig_ax()
    try:
        ChartEngine.render_element_ranking_fig7(ax, ranking_df)
        # Count text annotations that are non-negative integers
        numeric_annotations = []
        for txt in ax.texts:
            content = txt.get_text().strip()
            try:
                val = int(content)
                if val >= 0:
                    numeric_annotations.append(val)
            except ValueError:
                pass
        assert len(numeric_annotations) == k, (
            f"Expected {k} numeric annotations, got {len(numeric_annotations)}"
        )
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# Property 10 — Heatmap cell text colour follows the 0.5 threshold rule
# Feature: step6-model-performance, Property 10: Heatmap cell text colour follows the 0.5 threshold rule
# Validates: Requirements 7.3
# ---------------------------------------------------------------------------

@given(
    n_rows=st.integers(min_value=2, max_value=4),
    n_cols=st.integers(min_value=2, max_value=4),
    flat_values=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        min_size=4, max_size=16,
    ),
)
@settings(max_examples=80, deadline=None)
def test_property10_cell_text_colour_threshold(n_rows, n_cols, flat_values):
    """Cell text must be white (#FFFFFF) for val>=0.5 and C_BG_DEEP for val<0.5."""
    total = n_rows * n_cols
    # Pad or truncate flat_values to exactly total elements
    values = (flat_values * (total // len(flat_values) + 1))[:total]
    matrix = np.array(values, dtype=float).reshape(n_rows, n_cols)
    peak_labels = [f"Peak {i+1} (300.0 nm)" for i in range(n_rows)]
    element_labels = [f"El{j}" for j in range(n_cols)]

    fig, ax = _make_fig_ax()
    try:
        ChartEngine.render_correlation_heatmap(ax, matrix, peak_labels, element_labels)

        # Collect cell text objects — the chart draws them in row-major order (i, j)
        # using ax.text(j, i, ...) so we identify them by their (x, y) position.
        # Simpler: collect texts in order and match against matrix in (i, j) order.
        cell_texts = []
        for txt in ax.texts:
            content = txt.get_text().strip()
            try:
                parsed = float(content)
                if 0.0 <= parsed <= 1.01:  # allow slight overshoot from rounding
                    cell_texts.append((parsed, txt.get_color(), txt.get_position()))
            except ValueError:
                pass

        # Every cell value should have a corresponding annotation
        assert len(cell_texts) == n_rows * n_cols, (
            f"Expected {n_rows * n_cols} cell annotations, got {len(cell_texts)}"
        )

        # Sort by (y, x) position to recover row-major order matching matrix indices
        cell_texts_sorted = sorted(cell_texts, key=lambda t: (t[2][1], t[2][0]))

        for idx, (parsed_val, colour, pos) in enumerate(cell_texts_sorted):
            i = idx // n_cols
            j = idx % n_cols
            raw_val = matrix[i, j]  # use raw matrix value, not rounded display value

            if raw_val >= 0.5:
                colour_str = str(colour).lower()
                is_white = (
                    colour_str in {"#ffffff", "white"}
                    or colour == "#FFFFFF"
                    or colour == (1.0, 1.0, 1.0)
                    or colour == (1.0, 1.0, 1.0, 1.0)
                )
                assert is_white, (
                    f"Cell ({i},{j}) raw={raw_val:.4f} >= 0.5 but text colour is {colour!r}"
                )
            else:
                colour_str = str(colour).lower()
                assert colour_str in {"#141519"} or colour == C_BG_DEEP.lower() or colour == C_BG_DEEP, (
                    f"Cell ({i},{j}) raw={raw_val:.4f} < 0.5 but text colour is {colour!r} "
                    f"(expected {C_BG_DEEP})"
                )
    finally:
        plt.close(fig)


def test_property10_placeholder_for_small_matrix():
    """Matrices with < 2 rows or < 2 cols show placeholder, no cell texts."""
    fig, ax = _make_fig_ax()
    try:
        small_matrix = np.array([[0.8]])
        ChartEngine.render_correlation_heatmap(ax, small_matrix, ["Peak 1"], ["El"])
        # Should have rendered placeholder — no numeric cell texts
        cell_texts = []
        for txt in ax.texts:
            try:
                val = float(txt.get_text().strip())
                if 0.0 <= val <= 1.0:
                    cell_texts.append(val)
            except ValueError:
                pass
        assert len(cell_texts) == 0
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# Property 9 — Performance metrics chart handles partial None inputs
# Feature: step6-model-performance, Property 9: Performance metrics chart handles partial None inputs
# Validates: Requirements 8.6
# ---------------------------------------------------------------------------

_METRIC_KEYS = ["accuracy", "precision", "recall", "f1_score", "sbr_improvement"]


@given(
    acc=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
    prec=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
    rec=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
    f1=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
    sbr=st.one_of(st.none(), st.floats(min_value=0.0, max_value=20.0, allow_nan=False)),
)
@settings(max_examples=200, deadline=None)
def test_property9_no_exception_with_partial_none(acc, prec, rec, f1, sbr):
    """render_performance_metrics must never raise for any subset of None values."""
    metrics_dict = {
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1_score": f1,
        "sbr_improvement": sbr,
    }
    fig, ax, ax2 = _make_fig_two_axes()
    try:
        # Must not raise
        ChartEngine.render_performance_metrics(ax, metrics_dict, ax2)
    finally:
        plt.close(fig)


def test_property9_all_none_renders_na_annotations():
    """When all metrics are None, five 'N/A' text annotations appear."""
    metrics_dict = {k: None for k in _METRIC_KEYS}
    fig, ax, ax2 = _make_fig_two_axes()
    try:
        ChartEngine.render_performance_metrics(ax, metrics_dict, ax2)
        all_texts = [t.get_text() for t in ax.texts] + [t.get_text() for t in ax2.texts]
        na_count = sum(1 for t in all_texts if "N/A" in t or "n/a" in t.lower())
        assert na_count >= 4, f"Expected at least 4 'N/A' annotations, got {na_count}"
    finally:
        plt.close(fig)


@given(
    acc=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    prec=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    rec=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    f1=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    sbr=st.floats(min_value=0.01, max_value=10.0, allow_nan=False),
)
@settings(max_examples=50, deadline=None)
def test_property9_all_present_renders_bars(acc, prec, rec, f1, sbr):
    """When all metrics are non-None, exactly 5 bars (4 on ax + 1 on ax2) exist."""
    metrics_dict = {
        "accuracy": acc, "precision": prec, "recall": rec,
        "f1_score": f1, "sbr_improvement": sbr,
    }
    fig, ax, ax2 = _make_fig_two_axes()
    try:
        ChartEngine.render_performance_metrics(ax, metrics_dict, ax2)
        perc_bars = len(ax.patches)
        sbr_bars  = len(ax2.patches)
        assert perc_bars == 4, f"Expected 4 percentage bars, got {perc_bars}"
        assert sbr_bars  == 1, f"Expected 1 SBR bar, got {sbr_bars}"
    finally:
        plt.close(fig)
