# -*- coding: utf-8 -*-
"""
Tests for chart legend layout and element scaling in ChartEngine.

Ensures that when many elements are present, legends and labels do not
overflow or extend outside the chart boundaries.
"""

import warnings
import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
import matplotlib.pyplot as plt
import pandas as pd
import pytest

from src.gui.charts import ChartEngine, _compute_legend_layout, _style_legend


class DummyMatch:
    def __init__(self, element, observed_wl, score):
        self.element = element
        self.observed_wl = observed_wl
        self.score = score


ALL_ELEMENTS = [
    "Ag I", "Ag II", "Al I", "Al II", "As I", "Au I", "B I", "Ba I", "Ba II", "Be I",
    "Bi I", "C I", "Ca I", "Ca II", "Cd I", "Ce I", "Co I", "Cr I", "Cu I", "Cu II",
    "Fe I", "Fe II", "Li I", "Mg I", "Mn I", "Mo I", "Na I", "Ni I", "O I", "P I",
    "Pb I", "Si I", "Ti I", "V I", "Zn I", "W I", "Zr I", "Sn I", "Sb I", "Te I",
]


def test_compute_legend_layout():
    """Verify dynamic column and font size computation across counts."""
    assert _compute_legend_layout(1) == (1, 9.5)
    assert _compute_legend_layout(6) == (1, 9.5)
    assert _compute_legend_layout(7) == (2, 9.0)
    assert _compute_legend_layout(12) == (2, 9.0)
    assert _compute_legend_layout(13) == (3, 8.5)
    assert _compute_legend_layout(24) == (3, 8.5)
    assert _compute_legend_layout(25) == (4, 8.0)
    assert _compute_legend_layout(35) == (4, 8.0)
    assert _compute_legend_layout(40) == (5, 7.5)
    assert _compute_legend_layout(60)[0] <= 6
    assert _compute_legend_layout(60)[1] == 7.0


@pytest.mark.parametrize("count", [1, 5, 12, 20, 32, 40])
def test_match_score_scatter_legend_does_not_overflow(count):
    """Verify that match score scatter legend never overflows canvas with many elements."""
    elems = ALL_ELEMENTS[:count]
    matches = [DummyMatch(e, 300 + i * 10, 1e14 * (i + 1)) for i, e in enumerate(elems)]

    fig = plt.Figure(figsize=(8, 4), dpi=100)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)

    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        ChartEngine.render_match_score_scatter(ax, matches)
        canvas.draw()

    # Must not produce Tight layout warnings
    tight_warnings = [
        w for w in recorded_warnings if "Tight layout not applied" in str(w.message)
    ]
    assert len(tight_warnings) == 0, f"Tight layout warning triggered: {tight_warnings}"

    leg = ax.get_legend()
    assert leg is not None
    assert leg.get_draggable() is True

    renderer = canvas.get_renderer()
    bbox = leg.get_window_extent(renderer)
    fig_height = fig.get_figheight() * fig.dpi
    fig_width = fig.get_figwidth() * fig.dpi

    # Legend must stay strictly within the vertical and horizontal figure limits
    assert bbox.y0 >= 0, f"Legend bottom {bbox.y0} went below figure (count={count})"
    assert bbox.y1 <= fig_height, f"Legend top {bbox.y1} exceeded figure height (count={count})"
    assert bbox.x0 >= 0, f"Legend left {bbox.x0} went outside figure (count={count})"
    assert bbox.x1 <= fig_width, f"Legend right {bbox.x1} went outside figure (count={count})"


def test_match_score_scatter_empty():
    """Verify empty/missing matches renders placeholder gracefully."""
    fig = plt.Figure(figsize=(8, 4), dpi=100)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)

    ChartEngine.render_match_score_scatter(ax, [])
    canvas.draw()
    assert ax.get_legend() is None


@pytest.mark.parametrize("count", [2, 10, 35])
def test_score_scatter_legend_does_not_overflow(count):
    """Verify that score scatter legend in Step 4 does not overflow."""
    elems = ALL_ELEMENTS[:count]
    df = pd.DataFrame([
        {
            "Winning_Element": e,
            "Observed_Wavelength": 300 + i * 10,
            "Confidence_Score": 1e12 * (i + 1),
            "Num_Competitors": 2,
        }
        for i, e in enumerate(elems)
    ])

    fig = plt.Figure(figsize=(8, 4), dpi=100)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)

    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        ChartEngine.render_score_scatter(ax, df)
        canvas.draw()

    tight_warnings = [
        w for w in recorded_warnings if "Tight layout not applied" in str(w.message)
    ]
    assert len(tight_warnings) == 0

    leg = ax.get_legend()
    assert leg is not None
    assert leg.get_draggable() is True
    bbox = leg.get_window_extent(canvas.get_renderer())
    fig_height = fig.get_figheight() * fig.dpi
    assert bbox.y0 >= 0
    assert bbox.y1 <= fig_height


@pytest.mark.parametrize("count", [5, 30])
def test_element_frequency_chart_scales_ticks(count):
    """Verify that element frequency chart scales y-ticks and labels for many elements."""
    elems = ALL_ELEMENTS[:count]
    matches = [DummyMatch(e, 300, 50) for e in elems]

    fig = plt.Figure(figsize=(8, 4), dpi=100)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)

    ChartEngine.render_element_frequency_chart(ax, matches)
    canvas.draw()

    assert len(ax.patches) == count
    # Y-axis ticks should be configured
    yticklabels = ax.get_yticklabels()
    assert len(yticklabels) == count
