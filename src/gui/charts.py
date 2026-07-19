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

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.axes import Axes

from src.gui.theme import (
    C_ACCENT, C_ACCENT2, C_BG_CARD, C_BG_DEEP,
    C_BORDER, C_ERROR, C_SUCCESS, C_TEXT, C_TEXT2, C_WARN,
    C_BG_RAISED, C_BG_BASE, C_BORDER_SUBTLE,
    get_chart_bg, get_chart_axes_bg, get_chart_text, get_chart_text2, get_chart_border,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

ACCENT_CYCLE: list[str] = [C_ACCENT, C_ACCENT2, C_SUCCESS, C_WARN]
TIER_BINS:    list[float] = [0.0, 0.50, 0.70, 0.90, 1.0]
TIER_COLOURS: list[str]  = [C_ERROR, C_WARN, C_ACCENT, C_SUCCESS]   # Weak→Excellent
TIER_LABELS:  list[str]  = ["Weak\n(VC<0.50)", "Moderate\n(0.50–0.69)",
                             "Good\n(0.70–0.89)", "Excellent\n(VC≥0.90)"]

# Constants for render_performance_metrics (Fig 14 style)
METRIC_LABELS_PERC: list[str] = ["Accuracy", "Precision", "Recall", "F1-Score"]
METRIC_KEYS_PERC:   list[str] = ["accuracy", "precision", "recall", "f1_score"]

# Pipeline funnel stage constants (Requirement 6 / Figure 11)
STAGE_LABELS: list[str] = [
    "① Detected Peaks",
    "② NIST Matched",
    "③ Element Ranked",
    "④ Validated (VC≥0.50)",
    "⑤ Confirmed (VC≥0.70)",
]
STAGE_KEYS: list[str] = [
    "stage1_detected",
    "stage2_nist_matched",
    "stage3_ranked",
    "stage4_validated",
    "stage5_confirmed",
]

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
    """Make legend text visible on the current theme background."""
    leg = ax.get_legend()
    if leg is None:
        return
    leg.get_frame().set_facecolor(get_chart_axes_bg())
    leg.get_frame().set_edgecolor(get_chart_border())
    leg.get_frame().set_alpha(0.9)
    for text in leg.get_texts():
        text.set_color(get_chart_text2())
        text.set_fontsize(8)


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
        """Apply the current theme style to figure and axes."""
        fig.patch.set_facecolor(get_chart_bg())
        ax.set_facecolor(get_chart_axes_bg())
        ax.tick_params(colors=get_chart_text2(), which="both", labelsize=8)
        ax.xaxis.label.set_color(get_chart_text2())
        ax.yaxis.label.set_color(get_chart_text2())
        ax.title.set_color(get_chart_text())
        for spine in ax.spines.values():
            spine.set_edgecolor(get_chart_border())
            spine.set_linewidth(0.8)
        ax.grid(True, color=get_chart_border(), alpha=0.6, linewidth=0.5,
                linestyle="--")

    # ------------------------------------------------------------------
    # Colour utilities
    # ------------------------------------------------------------------

    @staticmethod
    def get_bar_colours(n: int) -> list[str]:
        """Return n colours cycling through ACCENT_CYCLE."""
        return [ACCENT_CYCLE[i % len(ACCENT_CYCLE)] for i in range(n)]

    @staticmethod
    def classify_vc(vc) -> tuple[str, str, str]:
        """Return (tier_label, bg_hex, fg_hex) for a VC value.

        Tiers:
          Excellent : VC >= 0.90
          Good      : 0.70 <= VC < 0.90
          Moderate  : 0.50 <= VC < 0.70
          Weak      : VC  <  0.50
          Failed    : NaN / None
        """
        if vc is None:
            return ("Failed", C_BG_CARD, C_TEXT2)
        try:
            if math.isnan(float(vc)):
                return ("Failed", C_BG_CARD, C_TEXT2)
        except (TypeError, ValueError):
            return ("Failed", C_BG_CARD, C_TEXT2)
        v = float(vc)
        if v >= 0.90:  return ("Excellent", C_SUCCESS, "#FFFFFF")
        if v >= 0.70:  return ("Good",      C_ACCENT,  "#FFFFFF")
        if v >= 0.50:  return ("Moderate",  C_WARN,    "#FFFFFF")
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
        """VC quality histogram with tier annotations and per-bar wavelength lists (Step 5)."""
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

            # Build a mapping: tier index → list of wavelengths in that tier
            has_wl = "Wavelength_nm" in validation_results_df.columns
            tier_wavelengths: list[list[float]] = [[] for _ in range(len(TIER_BINS) - 1)]

            if has_wl:
                for _, row in validation_results_df.iterrows():
                    vc = row["Validation_Coefficient"]
                    wl = row["Wavelength_nm"]
                    if pd.isna(vc):
                        continue
                    v = float(vc)
                    for i in range(len(TIER_BINS) - 1):
                        lo, hi = TIER_BINS[i], TIER_BINS[i + 1]
                        if i == len(TIER_BINS) - 2:
                            if lo <= v <= hi:
                                tier_wavelengths[i].append(float(wl))
                                break
                        else:
                            if lo <= v < hi:
                                tier_wavelengths[i].append(float(wl))
                                break

            # Draw bars
            bars_drawn = []
            counts = []
            for i in range(len(TIER_BINS) - 1):
                lo, hi = TIER_BINS[i], TIER_BINS[i + 1]
                if i == len(TIER_BINS) - 2:
                    count = int(((vc_values >= lo) & (vc_values <= hi)).sum())
                else:
                    count = int(((vc_values >= lo) & (vc_values < hi)).sum())
                counts.append(count)
                mid   = (lo + hi) / 2.0
                width = (hi - lo) * 0.82
                bar = ax.bar(mid, count, width=width,
                             color=TIER_COLOURS[i],
                             label=TIER_LABELS[i],
                             edgecolor=C_BORDER_SUBTLE,
                             linewidth=0.6,
                             align="center")
                bars_drawn.append((bar, count, i, mid))

            y_max = max(counts) if counts else 1

            # Annotate each bar: tier label on top, then wavelengths inside
            for bar_container, count, tier_idx, mid in bars_drawn:
                if count == 0:
                    continue

                # Count label above bar
                ax.text(mid, count + y_max * 0.02,
                        str(count),
                        ha="center", va="bottom",
                        color=C_TEXT, fontsize=9, fontweight="bold")

                # Wavelength list inside bar (up to 8 to avoid overflow)
                wls = tier_wavelengths[tier_idx]
                if wls:
                    wls_sorted = sorted(wls)
                    max_show = 8
                    wl_lines = [f"{w:.1f}" for w in wls_sorted[:max_show]]
                    if len(wls) > max_show:
                        wl_lines.append(f"+{len(wls) - max_show} more")
                    wl_text = "\n".join(wl_lines)
                    # Place text in the middle of the bar
                    text_y = count / 2.0
                    ax.text(mid, text_y,
                            wl_text,
                            ha="center", va="center",
                            color="#FFFFFF", fontsize=6.5,
                            alpha=0.92,
                            linespacing=1.4)

            ax.set_title("Validation Coefficient Distribution", color=C_TEXT,
                         fontsize=10, fontweight="bold")
            ax.set_xlabel("Validation Coefficient (VC)", color=C_TEXT)
            ax.set_ylabel("Number of Lines", color=C_TEXT)
            ax.set_xticks(TIER_BINS)
            ax.set_xticklabels([f"{b:.2f}" for b in TIER_BINS], fontsize=8)
            ax.set_xlim(-0.04, 1.06)
            ax.set_ylim(0, y_max * 1.25)

            import matplotlib.ticker as ticker
            ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

            ax.legend(loc="upper left", fontsize=7.5, framealpha=0.7,
                      handlelength=1.2)
            _style_legend(ax)
            _finish(fig, ax)

        except Exception:
            logger.exception("render_vc_histogram failed")
            ax.clear()
            ChartEngine._show_placeholder(ax, "Chart unavailable")
            ChartEngine.apply_dark_style(fig, ax)

    # ------------------------------------------------------------------
    # Step 6 charts
    # ------------------------------------------------------------------

    @staticmethod
    def render_element_ranking_fig7(ax: Axes, ranking_df: pd.DataFrame | None) -> None:
        """Horizontal bar chart of elemental preference ranking (Figure 7 style).

        Bars are colour-coded by confidence tier:
          C_SUCCESS (green)  — matched_lines >= 10  (High)
          C_WARN    (orange) — 3 <= matched_lines <= 9  (Medium)
          C_ERROR   (red)    — matched_lines < 3  (Low)

        Requirements 5.1 – 5.7
        """
        ax.clear()
        fig = ax.get_figure()
        try:
            if ranking_df is None or ranking_df.empty:
                ChartEngine._show_placeholder(ax, "No ranking data available")
                ChartEngine.apply_dark_style(fig, ax)
                return

            # Sort descending by Wins so the dominant element is at top
            df = ranking_df.sort_values(by="Wins", ascending=False).reset_index(drop=True)

            # barh draws bottom-to-top, so reverse the df so the top entry
            # appears at the top visually.
            df_plot = df.iloc[::-1].reset_index(drop=True)
            elements = df_plot["Element"].tolist()
            wins = df_plot["Wins"].tolist()

            # Assign tier colours
            def _tier_colour(w: int) -> str:
                if w >= 10:
                    return C_SUCCESS
                if w >= 3:
                    return C_WARN
                return C_ERROR

            colours = [_tier_colour(w) for w in wins]

            bars = ax.barh(elements, wins, color=colours, edgecolor="none", height=0.65)
            x_max = max(wins) if wins else 1

            # Numeric count labels at the right end of each bar
            for bar, val in zip(bars, wins):
                ax.text(
                    bar.get_width() + x_max * 0.02,
                    bar.get_y() + bar.get_height() / 2.0,
                    str(int(val)),
                    va="center", ha="left", color=C_TEXT, fontsize=8,
                    fontweight="bold",
                )

            ax.set_xlim(0, x_max * 1.18)
            ax.set_xlabel("Matched Lines (Wins)", color=C_TEXT)
            ax.set_title("Elemental Preference Ranking", color=C_TEXT)

            # Scale Y-tick font by number of elements to prevent overlap
            tick_fs = max(6, min(9, 120 // max(len(df_plot), 1)))
            ax.tick_params(axis="y", labelsize=tick_fs)

            # Legend with three confidence-tier entries
            import matplotlib.patches as mpatches
            legend_handles = [
                mpatches.Patch(color=C_SUCCESS, label="High (≥10)"),
                mpatches.Patch(color=C_WARN,    label="Medium (3–9)"),
                mpatches.Patch(color=C_ERROR,   label="Low (<3)"),
            ]
            ax.legend(handles=legend_handles, loc="lower right", fontsize=8)
            _style_legend(ax)

            _finish(fig, ax)

        except Exception:
            logger.exception("render_element_ranking_fig7 failed")
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
    # Step 6 charts
    # ------------------------------------------------------------------

    @staticmethod
    def render_correlation_heatmap(
        ax: Axes,
        heatmap_matrix,
        peak_labels: list,
        element_labels: list,
    ) -> None:
        """Correlation heatmap: peaks × elements, coolwarm colormap (Step 6 / Figure 12)."""
        ax.clear()
        fig = ax.get_figure()
        try:
            if (heatmap_matrix is None
                    or not hasattr(heatmap_matrix, "shape")
                    or heatmap_matrix.shape[0] < 2
                    or heatmap_matrix.shape[1] < 2):
                ChartEngine._show_placeholder(ax, "Insufficient heatmap data")
                ChartEngine.apply_dark_style(fig, ax)
                return

            im = ax.imshow(heatmap_matrix, aspect="auto", cmap="coolwarm",
                           vmin=0.0, vmax=1.0)
            cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label("Correlation Score", color=get_chart_text2(), fontsize=8)
            cbar.ax.tick_params(colors=get_chart_text2(), labelsize=7)
            cbar.ax.yaxis.set_tick_params(color=get_chart_text2())

            n_rows, n_cols = heatmap_matrix.shape
            for i in range(n_rows):
                for j in range(n_cols):
                    val = heatmap_matrix[i, j]
                    text_colour = "#FFFFFF" if val >= 0.5 else C_BG_DEEP
                    ax.text(j, i, f"{val:.2f}",
                            ha="center", va="center",
                            color=text_colour, fontsize=7, fontweight="bold")

            ax.set_yticks(range(n_rows))
            ax.set_yticklabels(peak_labels, fontsize=7)
            ax.set_xticks(range(n_cols))
            ax.set_xticklabels(element_labels, fontsize=8, rotation=45, ha="right")
            ax.set_title("Correlation Heatmap", color=get_chart_text(),
                         fontsize=10, fontweight="bold")
            _finish(fig, ax)
        except Exception:
            logger.exception("render_correlation_heatmap failed")
            ax.clear()
            ChartEngine._show_placeholder(ax, "Chart unavailable")
            ChartEngine.apply_dark_style(fig, ax)

    # ------------------------------------------------------------------
    # Step 6 charts
    # ------------------------------------------------------------------

    @staticmethod
    def render_element_ranking_fig7(ax: Axes, ranking_df: "pd.DataFrame | None") -> None:
        """Figure 7 style — horizontal bar chart of matched line counts per element,
        colour-coded by confidence tier (High/Medium/Low).  Requirement 5.
        """
        ax.clear()
        fig = ax.get_figure()
        try:
            if ranking_df is None or (hasattr(ranking_df, "empty") and ranking_df.empty):
                ChartEngine._show_placeholder(ax, "No ranking data available")
                ChartEngine.apply_dark_style(fig, ax)
                return

            df = ranking_df.copy()
            if "Wins" not in df.columns:
                ChartEngine._show_placeholder(ax, "No ranking data available")
                ChartEngine.apply_dark_style(fig, ax)
                return

            df = df.sort_values("Wins", ascending=False).reset_index(drop=True)
            # barh draws bottom-to-top; reverse so top row = highest wins
            df_plot = df.iloc[::-1].reset_index(drop=True)

            elements = df_plot["Element"].tolist()
            wins     = df_plot["Wins"].tolist()

            # Colour by confidence tier (Requirements 5.2–5.4)
            def _tier_colour(w: int) -> str:
                if w >= 10:
                    return C_SUCCESS
                if w >= 3:
                    return C_WARN
                return C_ERROR

            colours = [_tier_colour(int(w)) for w in wins]

            bars  = ax.barh(elements, wins, color=colours, edgecolor="none", height=0.65)
            x_max = max(wins) if wins else 1
            for bar, val in zip(bars, wins):
                ax.text(
                    bar.get_width() + x_max * 0.02,
                    bar.get_y() + bar.get_height() / 2.0,
                    str(int(val)),
                    va="center", ha="left", color=C_TEXT, fontsize=8,
                    fontweight="bold",
                )

            # Legend for three tiers (Requirement 5.6)
            from matplotlib.patches import Patch
            legend_elements = [
                Patch(facecolor=C_SUCCESS, label="High ≥ 10"),
                Patch(facecolor=C_WARN,    label="Medium 3–9"),
                Patch(facecolor=C_ERROR,   label="Low < 3"),
            ]
            ax.legend(handles=legend_elements, loc="lower right",
                      fontsize=7.5, framealpha=0.6)
            _style_legend(ax)

            ax.set_xlabel("Matched Lines", color=C_TEXT)
            ax.set_title("Elemental Preference Ranking", color=C_TEXT,
                         fontsize=10, fontweight="bold")
            ax.set_xlim(0, x_max * 1.22)
            tick_fs = max(6, min(9, 120 // max(len(df_plot), 1)))
            ax.tick_params(axis="y", labelsize=tick_fs)
            _finish(fig, ax)

        except Exception:
            logger.exception("render_element_ranking_fig7 failed")
            ax.clear()
            ChartEngine._show_placeholder(ax, "Chart unavailable")
            ChartEngine.apply_dark_style(fig, ax)

    @staticmethod
    def render_pipeline_funnel(ax: Axes, stage_counts: "dict | None") -> None:
        """Modern Funnel Diagram for the multi-stage validation pipeline.

        Draws centred trapezoid shapes that narrow at each stage, with the
        stage name, peak count, and reduction annotation inside/below each
        shape.  Layout matches the requested design:

            350 ┌────────────────┐  Detected Peaks
                ↓ Reduction x%
            180 ┌──────────────┐   NIST Match
                ↓ ...
        """
        ax.clear()
        fig = ax.get_figure()
        try:
            # ── Guard ────────────────────────────────────────────────────────
            if stage_counts is None:
                ChartEngine._show_placeholder(ax, "Insufficient pipeline data")
                ChartEngine.apply_dark_style(fig, ax)
                return

            counts = [stage_counts.get(k, 0) for k in STAGE_KEYS]
            non_zero = sum(1 for c in counts if c > 0)
            if non_zero < 2:
                ChartEngine._show_placeholder(ax, "Insufficient pipeline data")
                ChartEngine.apply_dark_style(fig, ax)
                return

            import matplotlib.patches as mpatches
            import matplotlib.colors as mcolors

            n = len(STAGE_KEYS)

            # Short display names for the funnel boxes
            FUNNEL_NAMES = [
                "Detected Peaks",
                "NIST Match",
                "Ranking",
                "Pure",
                "Bayesian",
            ]

            # --- colour gradient (accent → accent2) -------------------------
            rgb1 = mcolors.to_rgb(C_ACCENT)
            rgb2 = mcolors.to_rgb(C_ACCENT2)

            def _lerp(t: float) -> tuple:
                return tuple(rgb1[i] + (rgb2[i] - rgb1[i]) * t for i in range(3))

            colours = [_lerp(i / (n - 1)) for i in range(n)]

            # --- layout constants -------------------------------------------
            # Each funnel stage occupies a vertical slot of height SLOT_H.
            # The gap between slots (for the arrow + reduction text) is GAP_H.
            SLOT_H = 1.0        # height of each trapezoid
            GAP_H  = 0.55       # gap between stages for arrow + text
            TOTAL_H = n * SLOT_H + (n - 1) * GAP_H

            # Widths: the widest box = MAX_W, narrowing proportionally to count
            max_count = max(counts) if any(c > 0 for c in counts) else 1
            MAX_W = 0.80        # fraction of axes width
            MIN_W = 0.25        # minimum fraction so tiny counts are still visible

            def _width(count: int) -> float:
                ratio = count / max_count if max_count > 0 else 0
                return MIN_W + (MAX_W - MIN_W) * ratio

            ax.set_xlim(0, 1)
            ax.set_ylim(0, TOTAL_H)
            ax.axis("off")
            fig.patch.set_facecolor(get_chart_bg())
            ax.set_facecolor(get_chart_axes_bg())

            for i, (count, colour, name) in enumerate(zip(counts, colours, FUNNEL_NAMES)):
                # y-coordinate of this stage's bottom edge
                # Stages drawn top-to-bottom: stage 0 at top
                slot_top = TOTAL_H - i * (SLOT_H + GAP_H)
                slot_bot = slot_top - SLOT_H

                w_top = _width(count)
                # The bottom edge narrows slightly relative to the top to give
                # a true trapezoid feel.  Use the next stage's width as the
                # bottom, unless it's the last stage.
                if i < n - 1:
                    w_bot = _width(counts[i + 1])
                else:
                    w_bot = w_top * 0.85

                cx = 0.5  # centre x

                # Trapezoid vertices (bottom-left, bottom-right, top-right, top-left)
                xs = [cx - w_bot / 2, cx + w_bot / 2,
                      cx + w_top / 2, cx - w_top / 2]
                ys = [slot_bot, slot_bot, slot_top, slot_top]

                trap = mpatches.Polygon(
                    list(zip(xs, ys)),
                    closed=True,
                    facecolor=colour,
                    edgecolor=get_chart_bg(),
                    linewidth=1.5,
                    zorder=3,
                )
                ax.add_patch(trap)

                # Count label (large, centred in box)
                mid_y = (slot_top + slot_bot) / 2.0
                ax.text(
                    cx, mid_y + 0.12,
                    str(int(count)),
                    ha="center", va="center",
                    color="#FFFFFF",
                    fontsize=13, fontweight="bold",
                    zorder=4,
                )
                # Stage name below the count
                ax.text(
                    cx, mid_y - 0.18,
                    name,
                    ha="center", va="center",
                    color="#FFFFFF",
                    fontsize=8,
                    zorder=4,
                )

                # Arrow + reduction annotation between this and next stage
                if i < n - 1:
                    arrow_y_top = slot_bot
                    arrow_y_bot = slot_bot - GAP_H
                    arrow_mid_y = (arrow_y_top + arrow_y_bot) / 2.0

                    ax.annotate(
                        "",
                        xy=(cx, arrow_y_bot + 0.04),
                        xytext=(cx, arrow_y_top - 0.04),
                        arrowprops=dict(
                            arrowstyle="-|>",
                            color=get_chart_text2(),
                            lw=1.5,
                        ),
                        zorder=5,
                    )

                    prev = counts[i]
                    nxt  = counts[i + 1]
                    if prev > 0 and nxt < prev:
                        reduction_pct = (prev - nxt) / prev * 100.0
                        red_label = f"Reduction {reduction_pct:.1f}%"
                    elif prev > 0 and nxt >= prev:
                        red_label = "No reduction"
                    else:
                        red_label = ""

                    if red_label:
                        ax.text(
                            cx + 0.03, arrow_mid_y,
                            red_label,
                            ha="left", va="center",
                            color=get_chart_text2(),
                            fontsize=7.5,
                            zorder=5,
                        )

            ax.set_title(
                "Multi-Stage Validation Pipeline",
                color=get_chart_text(),
                fontsize=10, fontweight="bold",
                pad=6,
            )

            try:
                fig.tight_layout(pad=1.0)
            except Exception:
                pass

            fig.patch.set_facecolor(get_chart_bg())

        except Exception:
            logger.exception("render_pipeline_funnel failed")
            ax.clear()
            ChartEngine._show_placeholder(ax, "Chart unavailable")
            ChartEngine.apply_dark_style(fig, ax)

    # ------------------------------------------------------------------
    # Step 6 charts
    # ------------------------------------------------------------------

    @staticmethod
    def render_performance_metrics(
        ax: Axes,
        metrics_dict: dict,
        ax2: Axes,
    ) -> None:
        """Figure 14 style — Performance Metrics bar chart (Step 6).

        Draws four percentage bars (Accuracy, Precision, Recall, F1-Score) on
        the primary Y-axis *ax* and a single SBR Improvement bar on the
        secondary Y-axis *ax2*.
        """
        ax.clear()
        ax2.clear()
        fig = ax.get_figure()
        try:
            # ── four percentage bars on primary axis ──────────────────────
            x_perc = range(len(METRIC_LABELS_PERC))
            for i, (label, key) in enumerate(zip(METRIC_LABELS_PERC, METRIC_KEYS_PERC)):
                val = metrics_dict.get(key) if metrics_dict else None
                if val is not None:
                    pct = val * 100
                    ax.bar(i, pct, color=C_SUCCESS, width=0.55, zorder=3)
                    ax.text(
                        i, pct + 1.5, f"{pct:.1f}%",
                        ha="center", va="bottom",
                        color=C_TEXT, fontsize=9, fontweight="bold",
                    )
                else:
                    ax.text(
                        i, 5, "N/A",
                        ha="center", va="bottom",
                        color=C_TEXT2, fontsize=9, style="italic",
                    )

            ax.set_xticks(list(x_perc))
            ax.set_xticklabels(METRIC_LABELS_PERC, fontsize=9)
            ax.set_ylim(0, 110)
            ax.set_ylabel("Score (%)", color=C_TEXT)
            ax.set_title(
                "Model Performance Metrics",
                color=C_TEXT, fontsize=10, fontweight="bold",
            )

            # ── SBR bar on secondary axis ──────────────────────────────────
            sbr = metrics_dict.get("sbr_improvement") if metrics_dict else None
            sbr_x = 4
            if sbr is not None and not (isinstance(sbr, float) and sbr == float("inf")):
                ax2.bar(sbr_x, sbr, color=C_ACCENT, width=0.55, zorder=3)
                ax2.text(
                    sbr_x, sbr * 1.02 + 0.05, f"{sbr:.2f}×",
                    ha="center", va="bottom",
                    color=C_TEXT, fontsize=9, fontweight="bold",
                )
            elif sbr == float("inf"):
                ax2.text(
                    sbr_x, 1, "∞×",
                    ha="center", va="bottom",
                    color=C_ACCENT, fontsize=12, fontweight="bold",
                )
            else:
                ax2.text(
                    sbr_x, 0.1, "N/A",
                    ha="center", va="bottom",
                    color=C_TEXT2, fontsize=9, style="italic",
                )

            ax2.set_ylabel("SBR Improvement (×)", color=C_TEXT)
            ax2.tick_params(colors=get_chart_text2(), labelsize=8)

            # Extend x-range to include the SBR position; share labels with ax
            all_labels = METRIC_LABELS_PERC + ["SBR"]
            ax.set_xticks(list(range(5)))
            ax.set_xticklabels(all_labels, fontsize=9)
            ax.set_xlim(-0.6, 4.6)
            ax2.set_xlim(-0.6, 4.6)

            _finish(fig, ax)

        except Exception:
            logger.exception("render_performance_metrics failed")
            ax.clear()
            ax2.clear()
            ChartEngine._show_placeholder(ax, "Chart unavailable")
            ChartEngine.apply_dark_style(fig, ax)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _show_placeholder(ax: Axes, message: str) -> None:
        """Display a centred placeholder with label text on a cleared axes."""
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_facecolor(get_chart_axes_bg())
        # Large muted dash as visual anchor (no emoji — font may not support it)
        ax.text(0.5, 0.56, "- -",
                transform=ax.transAxes,
                ha="center", va="center",
                color=get_chart_border(), fontsize=28, fontweight="bold",
                fontfamily="monospace")
        ax.text(0.5, 0.36, message,
                transform=ax.transAxes,
                ha="center", va="center",
                color=get_chart_text2(), fontsize=10,
                style="italic", alpha=0.7)
