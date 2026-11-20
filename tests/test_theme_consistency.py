# -*- coding: utf-8 -*-
"""
Theme consistency test:
Verifies that all GUI tabs and Matplotlib charts properly adapt to Dark and Light modes.
"""

import pytest
from PyQt6.QtWidgets import QApplication
from src.gui.theme import set_theme, is_dark, get_chart_bg, get_chart_axes_bg
from src.gui.main_window import SpectralAnalysisApp


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_theme_toggle_all_tabs(qapp):
    win = SpectralAnalysisApp()

    # App starts in dark mode
    assert win._dark_mode is True
    assert is_dark() is True
    assert get_chart_bg() == "#141519"
    assert get_chart_axes_bg() == "#2F3443"

    # All figures in dark mode should have chart_bg "#141519"
    for name, fig in [
        ("Step 1 raw", win.step1_tab.fig_raw),
        ("Step 2 fig", win.step2_tab.fig),
        ("Step 3 freq", win.step3_tab.freq_fig),
        ("Step 4 ranking", win.step4_tab.ranking_fig),
        ("UPRSA overview", win.uprsa_tab.fig_overview),
        ("Step 5 vc", win.step5_tab.vc_fig),
        ("Step 5 overlay", win.step5_tab.overlay_fig),
        ("Step 6 fig7", win.step6_tab.fig7),
    ]:
        bg = fig.get_facecolor()
        # Matplotlib get_facecolor returns RGBA float tuple; convert to hex
        r, g, b = int(bg[0] * 255), int(bg[1] * 255), int(bg[2] * 255)
        hex_color = f"#{r:02X}{g:02X}{b:02X}"
        assert hex_color == "#141519", f"{name} background in dark mode is {hex_color}, expected #141519"

    # Switch to Light Mode
    win._dark_mode = False
    win._apply_theme_work()

    assert is_dark() is False
    assert get_chart_bg() == "#FFFFFF"
    assert get_chart_axes_bg() == "#F4F5F8"

    # All figures in light mode should have chart_bg "#FFFFFF"
    for name, fig in [
        ("Step 1 raw", win.step1_tab.fig_raw),
        ("Step 2 fig", win.step2_tab.fig),
        ("Step 3 freq", win.step3_tab.freq_fig),
        ("Step 4 ranking", win.step4_tab.ranking_fig),
        ("UPRSA overview", win.uprsa_tab.fig_overview),
        ("UPRSA comparison", win.uprsa_tab.fig_comparison),
        ("UPRSA hist", win.uprsa_tab.fig_hist),
        ("UPRSA map", win.uprsa_tab.fig_map),
        ("UPRSA profiles", win.uprsa_tab.fig_profiles),
        ("Step 5 vc", win.step5_tab.vc_fig),
        ("Step 5 overlay", win.step5_tab.overlay_fig),
        ("Step 6 fig7", win.step6_tab.fig7),
        ("Step 6 fig11", win.step6_tab.fig11),
        ("Step 6 fig12", win.step6_tab.fig12),
        ("Step 6 fig14", win.step6_tab.fig14),
    ]:
        bg = fig.get_facecolor()
        r, g, b = int(bg[0] * 255), int(bg[1] * 255), int(bg[2] * 255)
        hex_color = f"#{r:02X}{g:02X}{b:02X}"
        assert hex_color == "#FFFFFF", f"{name} background in light mode is {hex_color}, expected #FFFFFF"

    # Verify UPRSA title is NOT light/white text in Light Mode
    title_style = win.uprsa_tab._title_label.styleSheet()
    assert "color: #000000" in title_style or "color: #1" in title_style, f"UPRSA title style: {title_style}"

    # Switch back to Dark Mode
    win._dark_mode = True
    win._apply_theme_work()

    assert is_dark() is True
    for name, fig in [
        ("UPRSA overview", win.uprsa_tab.fig_overview),
        ("Step 5 vc", win.step5_tab.vc_fig),
        ("Step 6 fig7", win.step6_tab.fig7),
    ]:
        bg = fig.get_facecolor()
        r, g, b = int(bg[0] * 255), int(bg[1] * 255), int(bg[2] * 255)
        hex_color = f"#{r:02X}{g:02X}{b:02X}"
        assert hex_color == "#141519", f"{name} background in dark mode is {hex_color}, expected #141519"
