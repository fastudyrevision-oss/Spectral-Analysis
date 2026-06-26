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
)
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from src.gui.charts import ChartEngine
from src.gui.theme import (
    C_ACCENT, C_ACCENT2, C_SUCCESS, C_WARN, C_ERROR,
    C_BG_DEEP, C_BG_CARD, C_BG_INPUT, C_BG_PANEL,
    C_TEXT, C_TEXT2, C_TEXT_MUTED, C_BORDER,
    step_title_font, summary_banner_style,
)

if TYPE_CHECKING:
    from src.gui.step1_widget import Step1Widget
    from src.gui.step2_widget import Step2Widget
    from src.gui.step3_widget import Step3Widget
    from src.gui.step4_widget import Step4Widget
    from src.gui.step5_widget import Step5Widget

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Tiny helper — a "stat card" (coloured metric box)
# ─────────────────────────────────────────────────────────────────────────────

def _stat_card(title: str, value: str, colour: str = C_ACCENT2) -> QWidget:
    """Return a compact card widget showing a metric value."""
    card = QFrame()
    card.setFrameShape(QFrame.Shape.StyledPanel)
    card.setStyleSheet(
        f"QFrame {{ background-color: {C_BG_CARD}; border: 1px solid {colour}; "
        f"border-left: 4px solid {colour}; border-radius: 6px; }}"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(2)

    val_lbl = QLabel(value)
    val_lbl.setStyleSheet(
        f"QLabel {{ color: {colour}; font-size: 18pt; font-weight: 700; "
        f"background: transparent; border: none; }}"
    )
    val_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)

    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        f"QLabel {{ color: {C_TEXT2}; font-size: 8pt; "
        f"background: transparent; border: none; }}"
    )
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)

    layout.addWidget(val_lbl)
    layout.addWidget(title_lbl)
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return card


def _section_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"QLabel {{ color: {C_ACCENT2}; font-size: 11pt; font-weight: 700; "
        f"border-bottom: 2px solid {C_ACCENT}; padding-bottom: 4px; "
        f"background: transparent; }}"
    )
    return lbl


def _mini_canvas(figsize=(5, 2.6), dpi=90) -> tuple[Figure, FigureCanvasQTAgg]:
    fig = Figure(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor("#141519")
    canvas = FigureCanvasQTAgg(fig)
    canvas.setStyleSheet("background-color: #141519;")
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

        # ── stat-card references (updated on refresh) ─────────────────────
        self._card_peaks: QLabel | None = None
        self._card_elements: QLabel | None = None
        self._card_primary: QLabel | None = None
        self._card_mean_vc: QLabel | None = None

        # ── chart canvases ────────────────────────────────────────────────
        self._peak_fig,    self._peak_canvas    = _mini_canvas((5, 2.8))
        self._s1_fig,      self._s1_canvas      = _mini_canvas((5, 2.8))
        self._elem_fig,    self._elem_canvas     = _mini_canvas((5, 2.8))
        self._score_fig,   self._score_canvas    = _mini_canvas((5, 2.8))
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

        # ── Title ─────────────────────────────────────────────────────────
        title = QLabel("📊  Analysis Summary")
        title.setStyleSheet(step_title_font(14))
        content_layout.addWidget(title)

        subtitle = QLabel(
            "A consolidated overview of all five analysis steps.  "
            "Switch to any step tab, run its analysis, then return here — "
            "click Refresh or navigate back to update."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"QLabel {{ color: {C_TEXT2}; font-size: 9pt; background: transparent; }}"
        )
        content_layout.addWidget(subtitle)

        # ── Stat cards row ────────────────────────────────────────────────
        content_layout.addWidget(_section_header("Key Metrics"))
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)

        self._card_peaks    = self._make_card("Detected Peaks",     "—", C_ACCENT,  cards_row)
        self._card_elements = self._make_card("Identified Elements", "—", C_ACCENT2, cards_row)
        self._card_primary  = self._make_card("Primary Element",     "—", C_SUCCESS, cards_row)
        self._card_mean_vc  = self._make_card("Mean VC",             "—", C_WARN,    cards_row)
        content_layout.addLayout(cards_row)

        # ── Step 1 section ────────────────────────────────────────────────
        content_layout.addWidget(_section_header("① Baseline Correction"))
        s1_row = QHBoxLayout()
        s1_row.setSpacing(10)
        s1_row.addWidget(self._wrap_canvas(self._s1_canvas, "Corrected Spectrum Preview"))
        self._s1_stats_lbl = QLabel("No baseline correction data available.")
        self._s1_stats_lbl.setWordWrap(True)
        self._s1_stats_lbl.setStyleSheet(
            f"QLabel {{ color: {C_TEXT2}; font-size: 9pt; background: transparent; }}"
        )
        s1_row.addWidget(self._s1_stats_lbl)
        content_layout.addLayout(s1_row)

        # ── Step 2 section ────────────────────────────────────────────────
        content_layout.addWidget(_section_header("② Peak Detection"))
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
        content_layout.addWidget(_section_header("③ Element Identification"))
        s3_row = QHBoxLayout()
        s3_row.setSpacing(10)
        s3_row.addWidget(self._wrap_canvas(self._elem_canvas, "Element Frequency"))
        s3_row.addWidget(self._wrap_canvas(self._score_canvas, "Match Scores"))
        content_layout.addLayout(s3_row)

        # ── Step 4 section ────────────────────────────────────────────────
        content_layout.addWidget(_section_header("④ Elemental Preferences"))
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
        content_layout.addWidget(_section_header("⑤ Validation with Reference Spectra"))
        content_layout.addWidget(self._wrap_canvas(self._vc_canvas, "Validation Coefficient Distribution"))

        self._vc_table = self._make_small_table(
            ["Wavelength (nm)", "VC", "Quality"], 180
        )
        content_layout.addWidget(self._wrap_table(self._vc_table, "Validation Results"))

        # ── Conclusions ───────────────────────────────────────────────────
        content_layout.addWidget(_section_header("Conclusions"))
        self._conclusions_lbl = QLabel(
            "Run all five analysis steps, then navigate back to this tab "
            "to see an automated summary of key findings."
        )
        self._conclusions_lbl.setWordWrap(True)
        self._conclusions_lbl.setStyleSheet(
            f"QLabel {{ color: {C_TEXT2}; font-size: 9pt; "
            f"background-color: {C_BG_CARD}; border: 1px solid {C_BORDER}; "
            f"border-left: 4px solid {C_ACCENT2}; border-radius: 6px; padding: 10px; }}"
        )
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
        card.setStyleSheet(
            f"QFrame {{ background-color: {C_BG_CARD}; border: 1px solid {colour}; "
            f"border-left: 4px solid {colour}; border-radius: 6px; }}"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setSpacing(2)
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(
            f"QLabel {{ color: {colour}; font-size: 18pt; font-weight: 700; "
            f"background: transparent; border: none; }}"
        )
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"QLabel {{ color: {C_TEXT2}; font-size: 8pt; "
            f"background: transparent; border: none; }}"
        )
        cl.addWidget(val_lbl)
        cl.addWidget(title_lbl)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(card)
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
            ChartEngine.apply_dark_style(fig, ax)
            canvas.draw()

    # ──────────────────────────────────────────────────────────────────────
    # Refresh  (called when user switches to this tab)
    # ──────────────────────────────────────────────────────────────────────

    def refresh(self):
        """Pull the latest data from every step widget and update all panels."""
        self._refresh_step1()
        self._refresh_step2()
        self._refresh_step3()
        self._refresh_step4()
        self._refresh_step5()
        self._refresh_conclusions()

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
                ax.plot(wl, corr, color="#3FA9F5", linewidth=0.9, alpha=0.95)
                ax.set_xlabel("Wavelength (nm)", color="#AEB7C4", fontsize=8)
                ax.set_ylabel("Intensity", color="#AEB7C4", fontsize=8)
                ax.set_title("Corrected Spectrum", color="#F0F2F5", fontsize=9)
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
                self._rank_table.setItem(i, 2, QTableWidgetItem(f"{row['Total_Score']:.2f}"))
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
                quality_item.setBackground(QColor(bg))
                quality_item.setForeground(QColor(fg))
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
