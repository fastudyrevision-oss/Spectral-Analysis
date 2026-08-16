# -*- coding: utf-8 -*-
"""
Analysis Summary Widget - Spectral Analysis Software

Read-only dashboard that aggregates and visualises results produced by
the five workflow steps.  No analysis logic lives here — it only reads
data already stored on the step widgets and presents it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QScrollArea, QSizePolicy, QFrame, QGridLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QPushButton,
)
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from src.gui.charts import ChartEngine
from src.gui.gui_utils import HighDpiToolbar as NavigationToolbar2QT
import src.gui.theme as _theme
from src.gui.theme import (
    C_ACCENT, C_ACCENT2, C_SUCCESS, C_WARN, C_ERROR,
    C_BG_DEEP, C_BG_CARD, C_BG_INPUT, C_BG_PANEL,
    C_TEXT, C_TEXT2, C_TEXT_MUTED, C_BORDER,
    step_title_font, summary_banner_style, secondary_button_style,
    get_chart_bg,
)

if TYPE_CHECKING:
    from src.gui.step1_widget import Step1Widget
    from src.gui.step2_widget import Step2Widget
    from src.gui.step3_widget import Step3Widget
    from src.gui.step4_widget import Step4Widget
    from src.gui.step5_widget import Step5Widget

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Theme-aware helpers
# ─────────────────────────────────────────────────────────────────────────────

def _card_bg() -> str:
    return _theme.C_BG_CARD if _theme.is_dark() else _theme.L_BG_RAISED

def _card_text() -> str:
    return _theme.C_TEXT2 if _theme.is_dark() else _theme.L_TEXT2

def _card_border(colour: str) -> str:
    return colour  # accent colours work on both themes

def _body_text() -> str:
    return _theme.C_TEXT2 if _theme.is_dark() else _theme.L_TEXT2

def _body_bg() -> str:
    return "transparent"

def _conclusions_bg() -> str:
    return _theme.C_BG_CARD if _theme.is_dark() else _theme.L_BG_RAISED

def _conclusions_border() -> str:
    return _theme.C_BORDER if _theme.is_dark() else _theme.L_BORDER

def _accent2() -> str:
    return _theme.C_ACCENT2 if _theme.is_dark() else _theme.L_ACCENT2

def _accent() -> str:
    return _theme.C_ACCENT if _theme.is_dark() else _theme.L_ACCENT

def _section_header_style() -> str:
    a2 = _accent2()
    a  = _accent()
    return (
        f"QLabel {{ color: {a2}; font-size: 11pt; font-weight: 700; "
        f"border-bottom: 2px solid {a}; padding-bottom: 4px; "
        f"background: transparent; }}"
    )

def _card_frame_style(colour: str) -> str:
    bg = _card_bg()
    return (
        f"QFrame {{ background-color: {bg}; border: 1px solid {colour}; "
        f"border-left: 4px solid {colour}; border-radius: 6px; }}"
    )

def _val_label_style(colour: str) -> str:
    return (
        f"QLabel {{ color: {colour}; font-size: 18pt; font-weight: 700; "
        f"background: transparent; border: none; }}"
    )

def _title_label_style() -> str:
    ct = _card_text()
    return (
        f"QLabel {{ color: {ct}; font-size: 8pt; "
        f"background: transparent; border: none; }}"
    )

def _subtitle_style() -> str:
    ct = _body_text()
    return f"QLabel {{ color: {ct}; font-size: 9pt; background: transparent; }}"

def _stats_label_style() -> str:
    ct = _body_text()
    return f"QLabel {{ color: {ct}; font-size: 9pt; background: transparent; }}"

def _conclusions_label_style() -> str:
    bg     = _conclusions_bg()
    border = _conclusions_border()
    a2     = _accent2()
    ct     = _body_text()
    return (
        f"QLabel {{ color: {ct}; font-size: 9pt; "
        f"background-color: {bg}; border: 1px solid {border}; "
        f"border-left: 4px solid {a2}; border-radius: 6px; padding: 10px; }}"
    )


def _section_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(_section_header_style())
    return lbl


def _mini_canvas(figsize=(5, 2.6), dpi=90) -> tuple[Figure, FigureCanvasQTAgg]:
    chart_bg = get_chart_bg()
    fig = Figure(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor(chart_bg)
    canvas = FigureCanvasQTAgg(fig)
    canvas.setStyleSheet(f"background-color: {chart_bg};")
    canvas.setMinimumHeight(180)
    canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return fig, canvas


# ─────────────────────────────────────────────────────────────────────────────
# Main widget
# ─────────────────────────────────────────────────────────────────────────────

class SummaryWidget(QWidget):
    """
    Read-only Analysis Summary dashboard.

    Parameters
    ----------
    step1..step5 : step widget instances
        References to the live step widgets — data is read from them on refresh.
    """

    def __init__(self, step1, step2, step3, step4, step5):
        super().__init__()
        self._s1 = step1
        self._s2 = step2
        self._s3 = step3
        self._s4 = step4
        self._s5 = step5

        self._cleared = False  # True after Clear; suppresses auto-refresh on tab-switch

        # ── stat-card references (updated on refresh) ─────────────────────
        self._card_peaks: QLabel | None = None
        self._card_elements: QLabel | None = None
        self._card_primary: QLabel | None = None
        self._card_mean_vc: QLabel | None = None

        # ── chart canvases ────────────────────────────────────────────────
        self._peak_fig,    self._peak_canvas    = _mini_canvas((5, 2.8))
        self._s1_fig,      self._s1_canvas      = _mini_canvas((5, 2.8))
        self._elem_fig,    self._elem_canvas     = _mini_canvas((5, 2.8))
        self._score_fig,   self._score_canvas    = _mini_canvas((5, 4.2))
        self._score_canvas.setMinimumHeight(300)
        self._rank_fig,    self._rank_canvas     = _mini_canvas((5, 2.8))
        self._scatter_fig, self._scatter_canvas  = _mini_canvas((5, 2.8))
        self._vc_fig,      self._vc_canvas       = _mini_canvas((8, 2.8))

        self._build_ui()
        self._show_all_placeholders()

    # ──────────────────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        """Build the full dashboard layout."""
        # Outer scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(14)

        # ── Title + action buttons row ────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        title = QLabel("📊  Analysis Summary")
        title.setStyleSheet(step_title_font(14))
        self._title_lbl = title
        title_row.addWidget(title, stretch=1)

        self._reload_button = QPushButton("↻  Reload Data")
        self._reload_button.setToolTip("Re-read all step results and refresh the dashboard")
        self._reload_button.setStyleSheet(secondary_button_style())
        self._reload_button.clicked.connect(self.refresh)
        title_row.addWidget(self._reload_button)

        self._clear_button = QPushButton("✕  Clear")
        self._clear_button.setToolTip("Reset all charts and tables to their placeholder state")
        self._clear_button.setStyleSheet(secondary_button_style())
        self._clear_button.clicked.connect(self._clear)
        title_row.addWidget(self._clear_button)

        content_layout.addLayout(title_row)

        subtitle = QLabel(
            "A consolidated overview of all five analysis steps.  "
            "Switch to any step tab, run its analysis, then return here — "
            "click Refresh or navigate back to update."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(_subtitle_style())
        self._subtitle_lbl = subtitle
        content_layout.addWidget(subtitle)

        # ── Stat cards row ────────────────────────────────────────────────
        self._section_key_metrics = _section_header("Key Metrics")
        content_layout.addWidget(self._section_key_metrics)
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)

        self._card_peaks    = self._make_card("Detected Peaks",     "—", C_ACCENT,  cards_row)
        self._card_elements = self._make_card("Identified Elements", "—", C_ACCENT2, cards_row)
        self._card_primary  = self._make_card("Primary Element",     "—", C_SUCCESS, cards_row)
        self._card_mean_vc  = self._make_card("Mean VC",             "—", C_WARN,    cards_row)
        content_layout.addLayout(cards_row)

        # ── Step 1 section ────────────────────────────────────────────────
        self._section_s1 = _section_header("① Baseline Correction")
        content_layout.addWidget(self._section_s1)
        s1_row = QHBoxLayout()
        s1_row.setSpacing(10)
        s1_row.addWidget(self._wrap_canvas(self._s1_canvas, "Corrected Spectrum Preview"))
        self._s1_stats_lbl = QLabel("No baseline correction data available.")
        self._s1_stats_lbl.setWordWrap(True)
        self._s1_stats_lbl.setStyleSheet(_stats_label_style())
        s1_row.addWidget(self._s1_stats_lbl)
        content_layout.addLayout(s1_row)

        # ── Step 2 section ────────────────────────────────────────────────
        self._section_s2 = _section_header("② Peak Detection")
        content_layout.addWidget(self._section_s2)
        s2_row = QHBoxLayout()
        s2_row.setSpacing(10)
        s2_row.addWidget(self._wrap_canvas(self._peak_canvas, "Peak Intensity Distribution"))

        # top-10 peaks table
        self._peaks_table = self._make_small_table(
            ["Wavelength (nm)", "Intensity"], 200
        )
        s2_row.addWidget(self._wrap_table(self._peaks_table, "Top Detected Peaks"))
        content_layout.addLayout(s2_row)

        # ── Step 3 section ────────────────────────────────────────────────
        self._section_s3 = _section_header("③ Element Identification")
        content_layout.addWidget(self._section_s3)
        s3_row = QHBoxLayout()
        s3_row.setSpacing(10)
        s3_row.addWidget(self._wrap_canvas(self._elem_canvas, "Element Frequency"))
        s3_row.addWidget(self._wrap_canvas(self._score_canvas, "Match Scores"))
        content_layout.addLayout(s3_row)

        # ── Step 4 section ────────────────────────────────────────────────
        self._section_s4 = _section_header("④ Elemental Preferences")
        content_layout.addWidget(self._section_s4)
        s4_row = QHBoxLayout()
        s4_row.setSpacing(10)
        s4_row.addWidget(self._wrap_canvas(self._rank_canvas, "Element Ranking"))
        s4_row.addWidget(self._wrap_canvas(self._scatter_canvas, "Emission Line Scores"))

        self._rank_table = self._make_small_table(
            ["Element", "Wins", "Total Score"], 200
        )
        s4_row.addWidget(self._wrap_table(self._rank_table, "Top Elements"))
        content_layout.addLayout(s4_row)

        # ── Step 5 section ────────────────────────────────────────────────
        self._section_s5 = _section_header("⑤ Validation with Reference Spectra")
        content_layout.addWidget(self._section_s5)
        content_layout.addWidget(self._wrap_canvas(self._vc_canvas, "Validation Coefficient Distribution"))

        self._vc_table = self._make_small_table(
            ["Wavelength (nm)", "VC", "Quality"], 180
        )
        content_layout.addWidget(self._wrap_table(self._vc_table, "Validation Results"))

        # ── Conclusions ───────────────────────────────────────────────────
        self._section_conclusions = _section_header("Conclusions")
        content_layout.addWidget(self._section_conclusions)
        self._conclusions_lbl = QLabel(
            "Run all five analysis steps, then navigate back to this tab "
            "to see an automated summary of key findings."
        )
        self._conclusions_lbl.setWordWrap(True)
        self._conclusions_lbl.setStyleSheet(_conclusions_label_style())
        content_layout.addWidget(self._conclusions_lbl)
        content_layout.addStretch()

        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ──────────────────────────────────────────────────────────────────────
    # Layout helpers
    # ──────────────────────────────────────────────────────────────────────

    def _make_card(self, title: str, value: str, colour: str,
                   layout: QHBoxLayout) -> QLabel:
        """Create a stat card, add to layout, return the value QLabel."""
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet(_card_frame_style(colour))
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setSpacing(2)
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(_val_label_style(colour))
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(_title_label_style())
        cl.addWidget(val_lbl)
        cl.addWidget(title_lbl)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(card)
        # Store card frame ref for theme updates
        if not hasattr(self, '_card_frames'):
            self._card_frames: list[tuple[QFrame, QLabel, QLabel, str]] = []
        self._card_frames.append((card, val_lbl, title_lbl, colour))
        return val_lbl

    def _wrap_canvas(self, canvas: FigureCanvasQTAgg, title: str) -> QGroupBox:
        box = QGroupBox(title)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(4, 4, 4, 4)
        bl.addWidget(canvas)
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return box

    def _wrap_table(self, table: QTableWidget, title: str) -> QGroupBox:
        box = QGroupBox(title)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(4, 4, 4, 4)
        bl.addWidget(table)
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return box

    def _make_small_table(self, headers: list[str], min_height: int) -> QTableWidget:
        t = QTableWidget()
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSortingEnabled(True)
        t.setMinimumHeight(min_height)
        hdr = t.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return t

    # ──────────────────────────────────────────────────────────────────────
    # Theme
    # ──────────────────────────────────────────────────────────────────────

    def apply_theme(self) -> None:
        """Refresh all inline styles and chart backgrounds when theme changes."""
        chart_bg = get_chart_bg()

        # Section headers
        for lbl in [self._section_key_metrics, self._section_s1, self._section_s2,
                    self._section_s3, self._section_s4, self._section_s5,
                    self._section_conclusions]:
            lbl.setStyleSheet(_section_header_style())

        # Title, subtitle, stat text
        self._title_lbl.setStyleSheet(step_title_font(14))
        self._subtitle_lbl.setStyleSheet(_subtitle_style())
        self._s1_stats_lbl.setStyleSheet(_stats_label_style())
        self._conclusions_lbl.setStyleSheet(_conclusions_label_style())

        # Action buttons
        from src.gui.theme import secondary_button_style
        self._reload_button.setStyleSheet(secondary_button_style())
        self._clear_button.setStyleSheet(secondary_button_style())

        # Stat cards
        if hasattr(self, '_card_frames'):
            for card, val_lbl, title_lbl, colour in self._card_frames:
                card.setStyleSheet(_card_frame_style(colour))
                title_lbl.setStyleSheet(_title_label_style())
                # val_lbl colour stays the accent — no change needed

        # Chart canvases — update background then fully re-render so
        # axis labels, titles and tick colors pick up the new theme.
        chart_bg = get_chart_bg()
        for fig, canvas in [
            (self._s1_fig,      self._s1_canvas),
            (self._peak_fig,    self._peak_canvas),
            (self._elem_fig,    self._elem_canvas),
            (self._score_fig,   self._score_canvas),
            (self._rank_fig,    self._rank_canvas),
            (self._scatter_fig, self._scatter_canvas),
            (self._vc_fig,      self._vc_canvas),
        ]:
            fig.patch.set_facecolor(chart_bg)
            canvas.setStyleSheet(f"background-color: {chart_bg};")

        # Re-render all charts with updated theme colors
        self.refresh()

    # ──────────────────────────────────────────────────────────────────────
    # Placeholder rendering
    # ──────────────────────────────────────────────────────────────────────

    def _show_all_placeholders(self):
        for fig, canvas in [
            (self._s1_fig,      self._s1_canvas),
            (self._peak_fig,    self._peak_canvas),
            (self._elem_fig,    self._elem_canvas),
            (self._score_fig,   self._score_canvas),
            (self._rank_fig,    self._rank_canvas),
            (self._scatter_fig, self._scatter_canvas),
            (self._vc_fig,      self._vc_canvas),
        ]:
            fig.clear()
            ax = fig.add_subplot(111)
            ChartEngine._show_placeholder(ax, "No data — run analysis first")
            ChartEngine.apply_dark_style(fig, ax)   # theme-aware: respects is_dark()
            canvas.draw()
            canvas.draw()

    # ──────────────────────────────────────────────────────────────────────
    # Refresh  (called when user switches to this tab)
    # ──────────────────────────────────────────────────────────────────────

    def refresh(self):
        """Pull the latest data from every step widget and update all panels."""
        self._cleared = False  # explicit refresh rearms auto-refresh
        self._refresh_step1()
        self._refresh_step2()
        self._refresh_step3()
        self._refresh_step4()
        self._refresh_step5()
        self._refresh_conclusions()

    def refresh_if_not_cleared(self) -> None:
        """Called on tab-switch. Skips refresh when user has explicitly cleared."""
        if not self._cleared:
            self.refresh()

    def _clear(self):
        """Reset all charts and tables to placeholder state without re-reading data."""
        self._cleared = True  # suppress auto-refresh on next tab-switch
        self._show_all_placeholders()

        # Reset stat cards
        for lbl, default in [
            (self._card_peaks,    "—"),
            (self._card_elements, "—"),
            (self._card_primary,  "—"),
            (self._card_mean_vc,  "—"),
        ]:
            if lbl is not None:
                lbl.setText(default)

        # Reset Step 1 stats label
        self._s1_stats_lbl.setText("No baseline correction data available.")

        # Clear tables
        for table in (self._peaks_table, self._rank_table, self._vc_table):
            table.setSortingEnabled(False)
            table.setRowCount(0)
            table.setSortingEnabled(True)

        # Reset conclusions
        self._conclusions_lbl.setText(
            "Run all five analysis steps, then navigate back to this tab "
            "to see an automated summary of key findings."
        )

        logger.debug("Analysis Summary cleared")

    # ── Step 1 ────────────────────────────────────────────────────────────

    def _refresh_step1(self):
        data = getattr(self._s1, 'processed_data', None)
        fig, canvas = self._s1_fig, self._s1_canvas
        fig.clear()
        ax = fig.add_subplot(111)
        if data is not None:
            try:
                wl = np.asarray(data.wavelength)
                corr = np.asarray(data.corrected)
                ax.plot(wl, corr, color=C_ACCENT, linewidth=0.9, alpha=0.95)
                ax.set_xlabel("Wavelength (nm)", fontsize=8)
                ax.set_ylabel("Intensity", fontsize=8)
                ax.set_title("Corrected Spectrum", fontsize=9)
                ChartEngine.apply_dark_style(fig, ax)
                pts = len(wl)
                rng = f"{wl.min():.2f} – {wl.max():.2f} nm"
                self._s1_stats_lbl.setText(
                    f"Points: {pts:,}\nWavelength range: {rng}\n"
                    f"Corrected range: {corr.min():.3g} – {corr.max():.3g}"
                )
            except Exception:
                logger.exception("summary step1 chart failed")
                ChartEngine._show_placeholder(ax, "Chart unavailable")
                ChartEngine.apply_dark_style(fig, ax)
        else:
            ChartEngine._show_placeholder(ax, "No data — run Step 1 first")
            ChartEngine.apply_dark_style(fig, ax)
            self._s1_stats_lbl.setText("No baseline correction data available.")
        canvas.draw()

    # ── Step 2 ────────────────────────────────────────────────────────────

    def _refresh_step2(self):
        peaks = getattr(self._s2, 'detected_peaks', None)
        fig, canvas = self._peak_fig, self._peak_canvas
        fig.clear()
        ax = fig.add_subplot(111)

        if peaks:
            try:
                intensities = np.array([p.intensity for p in peaks])
                ax.hist(intensities, bins=min(30, len(peaks)),
                        color=C_ACCENT2, edgecolor='none', alpha=0.85)
                ax.set_xlabel("Intensity", color=C_TEXT, fontsize=8)
                ax.set_ylabel("Count", color=C_TEXT, fontsize=8)
                ax.set_title("Peak Intensity Distribution", color=C_TEXT, fontsize=9)
                ChartEngine.apply_dark_style(fig, ax)

                # Update stat card
                self._card_peaks.setText(str(len(peaks)))

                # Top-10 peaks table
                sorted_peaks = sorted(peaks, key=lambda p: p.intensity, reverse=True)[:10]
                self._peaks_table.setRowCount(len(sorted_peaks))
                for i, pk in enumerate(sorted_peaks):
                    self._peaks_table.setItem(i, 0, QTableWidgetItem(f"{pk.wavelength:.4f}"))
                    self._peaks_table.setItem(i, 1, QTableWidgetItem(f"{pk.intensity:.4g}"))
            except Exception:
                logger.exception("summary step2 chart failed")
                ChartEngine._show_placeholder(ax, "Chart unavailable")
                ChartEngine.apply_dark_style(fig, ax)
        else:
            ChartEngine._show_placeholder(ax, "No data — run Step 2 first")
            ChartEngine.apply_dark_style(fig, ax)
            self._card_peaks.setText("—")
            self._peaks_table.setRowCount(0)
        canvas.draw()

    # ── Step 3 ────────────────────────────────────────────────────────────

    def _refresh_step3(self):
        matches = getattr(self._s3, 'matches', None)

        # Frequency chart
        self._elem_fig.clear()
        ax_f = self._elem_fig.add_subplot(111)
        if matches:
            ChartEngine.render_element_frequency_chart(ax_f, matches)
        else:
            ChartEngine._show_placeholder(ax_f, "No data — run Step 3 first")
            ChartEngine.apply_dark_style(self._elem_fig, ax_f)
        self._elem_canvas.draw()

        # Score scatter chart
        self._score_fig.clear()
        ax_s = self._score_fig.add_subplot(111)
        if matches:
            ChartEngine.render_match_score_scatter(ax_s, matches)
        else:
            ChartEngine._show_placeholder(ax_s, "No data — run Step 3 first")
            ChartEngine.apply_dark_style(self._score_fig, ax_s)
        self._score_canvas.draw()

        # Stat card
        if matches:
            identified = {m.element for m in matches if getattr(m, 'element', None)}
            self._card_elements.setText(str(len(identified)))
        else:
            self._card_elements.setText("—")

    # ── Step 4 ────────────────────────────────────────────────────────────

    def _refresh_step4(self):
        results = getattr(self._s4, 'analysis_results', None)

        # Ranking chart
        self._rank_fig.clear()
        ax_r = self._rank_fig.add_subplot(111)
        if results and 'ranking' in results:
            ChartEngine.render_ranking_chart(ax_r, results['ranking'])
        else:
            ChartEngine._show_placeholder(ax_r, "No data — run Step 4 first")
            ChartEngine.apply_dark_style(self._rank_fig, ax_r)
        self._rank_canvas.draw()

        # Scatter chart
        self._scatter_fig.clear()
        ax_sc = self._scatter_fig.add_subplot(111)
        if results and 'winner_lines' in results:
            ChartEngine.render_score_scatter(ax_sc, results['winner_lines'])
        else:
            ChartEngine._show_placeholder(ax_sc, "No data — run Step 4 first")
            ChartEngine.apply_dark_style(self._scatter_fig, ax_sc)
        self._scatter_canvas.draw()

        # Ranking table (top 5) and stat card
        if results and 'ranking' in results:
            rdf = results['ranking']
            top = rdf.sort_values(
                by=['Wins', 'Total_Score'], ascending=[False, False]
            ).head(5)
            self._rank_table.setRowCount(len(top))
            for i, (_, row) in enumerate(top.iterrows()):
                self._rank_table.setItem(i, 0, QTableWidgetItem(str(row['Element'])))
                self._rank_table.setItem(i, 1, QTableWidgetItem(str(int(row['Wins']))))
                self._rank_table.setItem(i, 2, QTableWidgetItem(f"{row['Total_Score']:.3e}"))
            primary = str(results.get('primary_element', '—'))
            self._card_primary.setText(primary)
        else:
            self._rank_table.setRowCount(0)
            self._card_primary.setText("—")

    # ── Step 5 ────────────────────────────────────────────────────────────

    def _refresh_step5(self):
        vresults = getattr(self._s5, 'validation_results', None)

        # VC Histogram
        self._vc_fig.clear()
        ax_v = self._vc_fig.add_subplot(111)
        if vresults is not None and not vresults.empty:
            ChartEngine.render_vc_histogram(ax_v, vresults)
        else:
            ChartEngine._show_placeholder(ax_v, "No data — run Step 5 first")
            ChartEngine.apply_dark_style(self._vc_fig, ax_v)
        self._vc_canvas.draw()

        # VC table and mean VC card
        if vresults is not None and not vresults.empty:
            self._vc_table.setRowCount(len(vresults))
            for i, (_, row) in enumerate(vresults.iterrows()):
                self._vc_table.setItem(i, 0, QTableWidgetItem(
                    f"{row['Wavelength_nm']:.2f}"))
                vc_val = row.get('Validation_Coefficient')
                tier, bg, fg = ChartEngine.classify_vc(vc_val)
                vc_str = f"{float(vc_val):.4f}" if (vc_val is not None and
                          not (isinstance(vc_val, float) and
                          __import__('math').isnan(vc_val))) else "—"
                self._vc_table.setItem(i, 1, QTableWidgetItem(vc_str))
                from PyQt6.QtGui import QColor
                quality_item = QTableWidgetItem(tier)
                # Always use white text on colored backgrounds — these accent
                # colors (SUCCESS, WARN, ERROR, ACCENT) are all dark enough to
                # carry white text on both themes.  For the "Failed" tier the
                # bg returned by classify_vc is C_BG_CARD (dark) which is
                # invisible in light mode, so we override it with a neutral grey.
                if tier == "Failed":
                    cell_bg  = "#888888" if not _theme.is_dark() else "#4A4F60"
                    cell_fg  = "#FFFFFF"
                else:
                    cell_bg  = bg    # accent colors — always dark enough
                    cell_fg  = "#FFFFFF"
                quality_item.setBackground(QColor(cell_bg))
                quality_item.setForeground(QColor(cell_fg))
                self._vc_table.setItem(i, 2, quality_item)

            valid = vresults['Validation_Coefficient'].dropna()
            if not valid.empty:
                mean_vc = valid.mean()
                _, colour, _ = ChartEngine.classify_vc(mean_vc)
                self._card_mean_vc.setText(f"{mean_vc:.3f}")
                self._card_mean_vc.setStyleSheet(
                    f"QLabel {{ color: {colour}; font-size: 18pt; font-weight: 700; "
                    f"background: transparent; border: none; }}"
                )
            else:
                self._card_mean_vc.setText("—")
        else:
            self._vc_table.setRowCount(0)
            self._card_mean_vc.setText("—")

    # ── Conclusions ───────────────────────────────────────────────────────

    def _refresh_conclusions(self):
        parts = []
        peaks = getattr(self._s2, 'detected_peaks', None)
        if peaks:
            parts.append(f"• <b>{len(peaks)}</b> spectral peaks detected.")
        matches = getattr(self._s3, 'matches', None)
        if matches:
            identified = {m.element for m in matches if getattr(m, 'element', None)}
            if identified:
                parts.append(
                    f"• <b>{len(identified)}</b> element(s) identified: "
                    + ", ".join(sorted(identified)) + "."
                )
        results4 = getattr(self._s4, 'analysis_results', None)
        if results4:
            primary = results4.get('primary_element', '')
            if primary:
                parts.append(f"• Primary element by competition: <b>{primary}</b>.")
        vresults = getattr(self._s5, 'validation_results', None)
        if vresults is not None and not vresults.empty:
            valid = vresults['Validation_Coefficient'].dropna()
            if not valid.empty:
                mean_vc = valid.mean()
                _, colour, _ = ChartEngine.classify_vc(mean_vc)
                parts.append(
                    f"• Validation: mean VC = "
                    f"<span style='color:{colour};font-weight:700'>{mean_vc:.4f}</span> "
                    f"over {len(valid)} wavelengths."
                )

        if parts:
            self._conclusions_lbl.setText("<br/>".join(parts))
        else:
            self._conclusions_lbl.setText(
                "Run all five analysis steps, then navigate back to this tab "
                "to see an automated summary of key findings."
            )
        self._conclusions_lbl.setTextFormat(Qt.TextFormat.RichText)
