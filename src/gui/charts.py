# -*- coding: utf-8 -*-
"""
ChartEngine — Spectral Analysis Software
src/gui/charts.py

Stateless chart rendering functions for Step 4 (Elemental Preferences),
Step 5 (Validation), and Step 3 (Element Identification).
All methods operate on existing matplotlib Figure/Axes objects passed from
the owning widget.
"""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.axes import Axes

from src.gui.theme import (
    C_ACCENT, C_ACCENT2, C_BG_CARD, C_BG_DEEP,
    C_BORDER, C_ERROR, C_SUCCESS, C_TEXT, C_TEXT2, C_WARN,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

ACCENT_CYCLE: list[str] = [C_ACCENT, C_ACCENT2, C_SUCCESS, C_WARN]
TIER_BINS:    list[float] = [0.0, 0.70, 0.85, 0.95, 1.0]
TIER_COLOURS: list[str]  = [C_ERROR, C_WARN, C_ACCENT, C_SUCCESS]   # Weak→Excellent
TIER_LABELS:  list[str]  = ["Weak", "Moderate", "Good", "Excellent"]

_MPL_EXTRA = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
    "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
    "#bcbd22", "#17becf",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _element_colours(elements: list[str]) -> dict[str, str]:
    """Return a {element: hex_colour} dict, cycling ACCENT_CYCLE then _MPL_EXTRA."""
    result = {}
    extra = 0
    for i, elem in enumerate(elements):
        if i < len(ACCENT_CYCLE):
            result[elem] = ACCENT_CYCLE[i]
        else:
            result[elem] = _MPL_EXTRA[extra % len(_MPL_EXTRA)]
            extra += 1
    return result


def _style_legend(ax: Axes) -> None:
    """Make legend text visible on the dark background (compatible with all mpl versions)."""
    leg = ax.get_legend()
    if leg is None:
        return
    leg.get_frame().set_facecolor(C_BG_CARD)
    leg.get_frame().set_edgecolor(C_BORDER)
    for text in leg.get_texts():
        text.set_color(C_TEXT)


def _finish(fig: Figure, ax: Axes) -> None:
    """Apply dark style and tighten layout."""
    ChartEngine.apply_dark_style(fig, ax)
    try:
        fig.tight_layout(pad=1.2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ChartEngine
# ---------------------------------------------------------------------------

class ChartEngine:
    """Stateless chart rendering — all methods are @staticmethod."""

    # ------------------------------------------------------------------
    # Style helpers
    # ------------------------------------------------------------------

    @staticmethod
    def apply_dark_style(fig: Figure, ax: Axes) -> None:
        """Apply Theme_Palette dark background to figure and axes."""
        fig.patch.set_facecolor(C_BG_DEEP)
        ax.set_facecolor(C_BG_CARD)
        ax.tick_params(colors=C_TEXT, which="both")
        ax.xaxis.label.set_color(C_TEXT)
        ax.yaxis.label.set_color(C_TEXT)
        ax.title.set_color(C_TEXT)
        for spine in ax.spines.values():
            spine.set_edgecolor(C_BORDER)
        ax.grid(True, color=C_BORDER, alpha=0.4, linewidth=0.5)

    # ------------------------------------------------------------------
    # Colour utilities
    # ------------------------------------------------------------------

    @staticmethod
    def get_bar_colours(n: int) -> list[str]:
        """Return n colours cycling through ACCENT_CYCLE."""
        return [ACCENT_CYCLE[i % len(ACCENT_CYCLE)] for i in range(n)]

    @staticmethod
    def classify_vc(vc) -> tuple[str, str, str]:
        """Return (tier_label, bg_hex, fg_hex) for a VC value."""
        if vc is None:
            return ("Failed", C_BG_CARD, C_TEXT2)
        try:
            if math.isnan(float(vc)):
                return ("Failed", C_BG_CARD, C_TEXT2)
        except (TypeError, ValueError):
            return ("Failed", C_BG_CARD, C_TEXT2)
        v = float(vc)
        if v > 0.95:   return ("Excellent", C_SUCCESS, "#FFFFFF")
        if v >= 0.85:  return ("Good",      C_ACCENT,  "#FFFFFF")
        if v >= 0.70:  return ("Moderate",  C_WARN,    "#FFFFFF")
        return              ("Weak",       C_ERROR,   "#FFFFFF")

    # ------------------------------------------------------------------
    # Step 4 charts
    # ------------------------------------------------------------------

    @staticmethod
    def render_ranking_chart(ax: Axes, ranking_df: pd.DataFrame) -> None:
        """Horizontal bar chart of element win counts (Step 4)."""
        ax.clear()
        fig = ax.get_figure()
        try:
            if ranking_df is None or ranking_df.empty:
                ChartEngine._show_placeholder(ax, "No data available")
                ChartEngine.apply_dark_style(fig, ax)
                return

            # Sort descending so dominant element is at top of the chart.
            df = ranking_df.sort_values(
                by=["Wins", "Total_Score"], ascending=[False, False]
            ).reset_index(drop=True)

            # Cap at top 15 for readability
            if len(df) > 15:
                df = df.head(15)

            # barh draws bottom-to-top so we reverse the df so that the
            # #1 element ends up at the top visually.
            df_plot   = df.iloc[::-1].reset_index(drop=True)
            elements  = df_plot["Element"].tolist()
            wins      = df_plot["Wins"].tolist()

            n = len(df_plot)
            colours = [ACCENT_CYCLE[(n - 1 - i) % len(ACCENT_CYCLE)] for i in range(n)]

            bars  = ax.barh(elements, wins, color=colours, edgecolor="none",
                            height=0.65)
            x_max = max(wins) if wins else 1
            for bar, val, colour in zip(bars, wins, colours):
                ax.text(
                    bar.get_width() + x_max * 0.02,
                    bar.get_y() + bar.get_height() / 2.0,
                    str(int(val)),
                    va="center", ha="left", color=C_TEXT, fontsize=8,
                    fontweight="bold",
                )

            ax.set_xlabel("Wins", color=C_TEXT)
            ax.set_title("Element Ranking by Wins", color=C_TEXT)
            ax.set_xlim(0, x_max * 1.18)
            # Scale Y-tick font by number of elements to prevent overlap
            tick_fs = max(6, min(9, 120 // max(len(df_plot), 1)))
            ax.tick_params(axis="y", labelsize=tick_fs)
            _finish(fig, ax)

        except Exception:
            logger.exception("render_ranking_chart failed")
            ax.clear()
            ChartEngine._show_placeholder(ax, "Chart unavailable")
            ChartEngine.apply_dark_style(fig, ax)

    @staticmethod
    def render_score_scatter(ax: Axes, winner_lines_df: pd.DataFrame) -> None:
        """Wavelength vs. competition score scatter, coloured by element (Step 4).

        Confidence_Score here is the raw Max_Score from peak competition
        (Aki × relative_intensity / Δλ), spanning many orders of magnitude.
        Log scale is used on the Y-axis.  Marker size encodes Num_Competitors.
        """
        ax.clear()
        fig = ax.get_figure()
        try:
            if winner_lines_df is None or winner_lines_df.empty:
                ChartEngine._show_placeholder(ax, "No data available")
                ChartEngine.apply_dark_style(fig, ax)
                return

            elements   = list(winner_lines_df["Winning_Element"].unique())
            colour_map = _element_colours(elements)

            has_comp = "Num_Competitors" in winner_lines_df.columns

            for elem in elements:
                subset = winner_lines_df[winner_lines_df["Winning_Element"] == elem]

                # Only plot rows with positive scores (log scale requires > 0)
                valid = subset[subset["Confidence_Score"] > 0]
                if valid.empty:
                    continue

                if has_comp:
                    raw   = valid["Num_Competitors"].fillna(1).clip(lower=1)
                    sizes = (raw / raw.max() * 100 + 20).values
                else:
                    sizes = 40

                ax.scatter(
                    valid["Observed_Wavelength"],
                    valid["Confidence_Score"],
                    label=elem,
                    color=colour_map[elem],
                    s=sizes,
                    alpha=0.78,
                    edgecolors="none",
                    zorder=3,
                )

            # Log scale for the wide score range
            try:
                ax.set_yscale("log")
            except Exception:
                pass

            ax.set_xlabel("Wavelength (nm)", color=C_TEXT, fontsize=9)
            ax.set_ylabel("Score (log)", color=C_TEXT, fontsize=9)
            ax.set_title("Emission Line Scores by Element", color=C_TEXT,
                         fontsize=10, fontweight="bold", pad=6)

            n_elem = len(elements)
            ncols  = min(n_elem, 3) if n_elem <= 9 else 4
            ax.legend(loc="upper right", fontsize=7, framealpha=0.5,
                      ncol=ncols, handlelength=1.0, borderpad=0.5,
                      labelspacing=0.3)
            _style_legend(ax)
            _finish(fig, ax)

        except Exception:
            logger.exception("render_score_scatter failed")
            ax.clear()
            ChartEngine._show_placeholder(ax, "Chart unavailable")
            ChartEngine.apply_dark_style(fig, ax)

    # ------------------------------------------------------------------
    # Step 5 chart
    # ------------------------------------------------------------------

    @staticmethod
    def render_vc_histogram(ax: Axes, validation_results_df: pd.DataFrame) -> None:
        """VC quality histogram with fixed tier bins (Step 5)."""
        ax.clear()
        fig = ax.get_figure()
        try:
            if validation_results_df is None or validation_results_df.empty:
                ChartEngine._show_placeholder(ax, "No data available")
                ChartEngine.apply_dark_style(fig, ax)
                return

            vc_values = validation_results_df["Validation_Coefficient"].dropna().values
            if len(vc_values) == 0:
                ChartEngine._show_placeholder(ax, "No data available")
                ChartEngine.apply_dark_style(fig, ax)
                return

            bin_edges = TIER_BINS
            for i in range(len(bin_edges) - 1):
                lo, hi  = bin_edges[i], bin_edges[i + 1]
                if i == len(bin_edges) - 2:   # last bin: inclusive upper edge
                    count = int(((vc_values >= lo) & (vc_values <= hi)).sum())
                else:
                    count = int(((vc_values >= lo) & (vc_values < hi)).sum())
                mid   = (lo + hi) / 2.0
                width = (hi - lo) * 0.85
                ax.bar(mid, count, width=width, color=TIER_COLOURS[i],
                       label=TIER_LABELS[i], edgecolor="none", align="center")

            ax.set_title("Validation Coefficient Distribution", color=C_TEXT)
            ax.set_xlabel("Validation Coefficient (VC)", color=C_TEXT)
            ax.set_ylabel("Count", color=C_TEXT)
            ax.set_xticks(bin_edges)
            ax.set_xlim(-0.02, 1.05)
            # Y axis: integer ticks only
            import matplotlib.ticker as ticker
            ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
            ax.legend(loc="upper left", fontsize=8, framealpha=0.6)
            _style_legend(ax)
            _finish(fig, ax)

        except Exception:
            logger.exception("render_vc_histogram failed")
            ax.clear()
            ChartEngine._show_placeholder(ax, "Chart unavailable")
            ChartEngine.apply_dark_style(fig, ax)

    # ------------------------------------------------------------------
    # Step 3 charts
    # ------------------------------------------------------------------

    @staticmethod
    def render_element_frequency_chart(ax: Axes, matches) -> None:
        """Horizontal bar chart of peak-match count per element (Step 3)."""
        ax.clear()
        fig = ax.get_figure()
        try:
            identified = [m for m in (matches or [])
                          if getattr(m, "element", None) not in (None, "", "—")]
            if not identified:
                ChartEngine._show_placeholder(ax, "No elements identified")
                ChartEngine.apply_dark_style(fig, ax)
                return

            counts = Counter(m.element for m in identified)
            # Sort ascending so largest count ends at top (barh is bottom-to-top)
            sorted_items = sorted(counts.items(), key=lambda x: x[1])
            elements = [k for k, _ in sorted_items]
            values   = [v for _, v in sorted_items]
            colours  = ChartEngine.get_bar_colours(len(elements))

            bars  = ax.barh(elements, values, color=colours, edgecolor="none")
            x_max = max(values) if values else 1
            for bar, val in zip(bars, values):
                ax.text(
                    bar.get_width() + x_max * 0.02,
                    bar.get_y() + bar.get_height() / 2.0,
                    str(int(val)),
                    va="center", ha="left", color=C_TEXT, fontsize=9,
                )
            ax.set_xlim(0, x_max * 1.18)
            ax.set_xlabel("Matched Peaks", color=C_TEXT)
            ax.set_title("Element Identification Frequency", color=C_TEXT)
            _finish(fig, ax)

        except Exception:
            logger.exception("render_element_frequency_chart failed")
            ax.clear()
            ChartEngine._show_placeholder(ax, "Chart unavailable")
            ChartEngine.apply_dark_style(fig, ax)

    @staticmethod
    def render_match_score_scatter(ax: Axes, matches) -> None:
        """Scatter of observed wavelength vs. match score, by element (Step 3)."""
        ax.clear()
        fig = ax.get_figure()
        try:
            identified = [m for m in (matches or [])
                          if getattr(m, "element", None) not in (None, "", "—")
                          and getattr(m, "score", 0)]
            if not identified:
                ChartEngine._show_placeholder(ax, "No data available")
                ChartEngine.apply_dark_style(fig, ax)
                return

            by_elem: dict = defaultdict(list)
            for m in identified:
                by_elem[m.element].append(m)

            colour_map = _element_colours(sorted(by_elem))

            for elem, pts in sorted(by_elem.items()):
                wls    = [m.observed_wl for m in pts]
                scores = [m.score for m in pts]
                ax.scatter(wls, scores, label=elem,
                           color=colour_map[elem],
                           s=35, alpha=0.85, edgecolors="none")

            ax.set_xlabel("Wavelength (nm)", color=C_TEXT)
            ax.set_ylabel("Match Score", color=C_TEXT)
            ax.set_title("Match Score vs. Wavelength", color=C_TEXT)
            ax.legend(loc="best", fontsize=8, framealpha=0.5)
            _style_legend(ax)
            _finish(fig, ax)

        except Exception:
            logger.exception("render_match_score_scatter failed")
            ax.clear()
            ChartEngine._show_placeholder(ax, "Chart unavailable")
            ChartEngine.apply_dark_style(fig, ax)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _show_placeholder(ax: Axes, message: str) -> None:
        """Display centred placeholder text on a cleared axes."""
        ax.set_xticks([])
        ax.set_yticks([])
        ax.text(0.5, 0.5, message,
                transform=ax.transAxes,
                ha="center", va="center",
                color=C_TEXT2, fontsize=11, style="italic")
