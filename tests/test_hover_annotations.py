# -*- coding: utf-8 -*-
"""
Tests for PeakHoverAnnotator and hover peak tooltip functionality:
Verifies that when mouse cursor hovers over detected peaks, the exact (x, y) coordinates
and physical quantities are correctly formatted and displayed.
"""

from types import SimpleNamespace
import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from src.gui.gui_utils import PeakHoverAnnotator
from src.gui.step2_widget import Step2Widget
from src.gui.uprsa_widget import UPRSAWidget
from src.io.data_models import DetectedPeak, ProcessedSpectra


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_peak_hover_annotator_basic(qapp):
    fig = Figure(figsize=(6, 4), dpi=100)
    canvas = FigureCanvasQTAgg(fig)
    ax = fig.add_subplot(111)

    peak_x = np.array([396.15, 520.00, 670.50])
    peak_y = np.array([3500.25, 1200.50, 450.00])
    extra = ["Top Peak", "Mid Peak", "Low Peak"]

    ax.set_xlim(300, 800)
    ax.set_ylim(0, 4000)
    ax.scatter(peak_x, peak_y)
    fig.canvas.draw()

    annotator = PeakHoverAnnotator(
        canvas=canvas,
        radius_px=14.0,
        x_unit="nm",
        x_name="Wavelength",
        y_name="Intensity",
    )
    annotator.attach(ax, peak_x, peak_y, extra_info=extra)

    # Initial state: invisible
    assert annotator._annot is not None
    assert annotator._highlight is not None
    assert annotator._annot.get_visible() is False
    assert annotator._highlight.get_visible() is False

    # 1. Hover exactly on peak 0 (396.15, 3500.25)
    disp_pt0 = ax.transData.transform((396.15, 3500.25))
    ev_hit = SimpleNamespace(inaxes=ax, x=disp_pt0[0], y=disp_pt0[1])
    annotator._on_motion(ev_hit)

    assert annotator._annot.get_visible() is True
    assert annotator._highlight.get_visible() is True
    text = annotator._annot.get_text()
    assert "(396.15, 3500.25)" in text
    assert "Wavelength: 396.15 nm" in text
    assert "Intensity: 3500.25" in text
    assert "Top Peak" in text

    # Highlight marker position
    hl_x, hl_y = annotator._highlight.get_data()
    assert float(hl_x[0]) == pytest.approx(396.15)
    assert float(hl_y[0]) == pytest.approx(3500.25)

    # 2. Hover within radius (e.g., 5 pixels away)
    ev_near = SimpleNamespace(inaxes=ax, x=disp_pt0[0] + 5.0, y=disp_pt0[1] + 5.0)
    annotator._on_motion(ev_near)
    assert annotator._annot.get_visible() is True

    # 3. Hover outside radius (e.g., 30 pixels away)
    ev_miss = SimpleNamespace(inaxes=ax, x=disp_pt0[0] + 30.0, y=disp_pt0[1] + 30.0)
    annotator._on_motion(ev_miss)
    assert annotator._annot.get_visible() is False
    assert annotator._highlight.get_visible() is False

    # 4. Hover outside axes
    annotator._on_motion(ev_hit)
    assert annotator._annot.get_visible() is True
    ev_out = SimpleNamespace(inaxes=None, x=10, y=10)
    annotator._on_motion(ev_out)
    assert annotator._annot.get_visible() is False

    # 5. Mouse leave event
    annotator._on_motion(ev_hit)
    assert annotator._annot.get_visible() is True
    annotator._on_leave(None)
    assert annotator._annot.get_visible() is False

    # 6. Update theme should not crash
    annotator.update_theme()

    # 7. Clear / detach
    annotator.detach()
    assert annotator._peak_x is None
    assert annotator._annot.get_visible() is False


def test_step2_widget_hover_integration(qapp):
    widget = Step2Widget()
    assert hasattr(widget, "_hover_annotator")
    assert isinstance(widget._hover_annotator, PeakHoverAnnotator)

    # Supply mock spectrum and peaks
    wl = np.linspace(350, 750, 1000)
    spec = np.sin(wl / 20.0) * 1000.0 + 1500.0
    widget.processed_data = ProcessedSpectra(
        wavelength=wl,
        raw=spec,
        smoothed_sg=spec,
        baseline_als=np.zeros_like(wl),
        corrected=spec,
    )
    widget.detected_peaks = [
        DetectedPeak(wavelength=float(wl[100]), intensity=float(spec[100])),
        DetectedPeak(wavelength=float(wl[300]), intensity=float(spec[300])),
    ]

    widget._update_chart()

    assert widget._hover_annotator.ax is widget.axes
    assert len(widget._hover_annotator._peak_x) == 2
    assert widget._hover_annotator._peak_x[0] == pytest.approx(wl[100])
    assert widget._hover_annotator._peak_y[0] == pytest.approx(spec[100])


def test_uprsa_widget_hover_integration(qapp):
    widget = UPRSAWidget()
    assert hasattr(widget, "_hover_overview")
    assert hasattr(widget, "_hover_comparison")
    assert hasattr(widget, "_hover_map")
    assert isinstance(widget._hover_overview, PeakHoverAnnotator)
    assert isinstance(widget._hover_comparison, PeakHoverAnnotator)
    assert isinstance(widget._hover_map, PeakHoverAnnotator)
