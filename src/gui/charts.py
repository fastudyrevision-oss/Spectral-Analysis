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
        # NOTE: the caller must use fig.clf() + add_subplot() before calling
        # this method — NOT ax.clear() — so that any colorbar axes added by a
        # previous render are fully removed from the figure.
        fig = ax.get_figure()
        try:
            # Relax guard: require at least 1 row AND 1 column with real data
            if (heatmap_matrix is None
                    or not hasattr(heatmap_matrix, "shape")
                    or heatmap_matrix.shape[0] < 1
                    or heatmap_matrix.shape[1] < 1
                    or heatmap_matrix.size == 0):
                ChartEngine._show_placeholder(ax, "Insufficient heatmap data")
                ChartEngine.apply_dark_style(fig, ax)
                return

            n_rows, n_cols = heatmap_matrix.shape

            # Determine real data range for colour scaling.
            # Use symmetric range around 0 so negative VC (anti-correlated) shows
            # as blue, positive as red/warm — more informative than 0→1 clamp.
            v_abs = np.abs(heatmap_matrix[np.isfinite(heatmap_matrix)])
            v_max = float(v_abs.max()) if len(v_abs) > 0 else 1.0
            v_max = max(v_max, 0.01)   # prevent vmin==vmax

            # Use RdYlGn: red=low/negative, yellow=mid, green=high/confirmed
            im = ax.imshow(
                heatmap_matrix,
                aspect="auto",
                cmap="RdYlGn",
                vmin=-v_max,
                vmax=v_max,
            )

            # Colorbar — safe because the caller cleared the whole figure first
            cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label("Validation Coefficient (VC)", color=get_chart_text2(), fontsize=8)
            cbar.ax.tick_params(colors=get_chart_text2(), labelsize=7)
            cbar.ax.yaxis.set_tick_params(color=get_chart_text2())

            # Cell annotations
            for i in range(n_rows):
                for j in range(n_cols):
                    val = heatmap_matrix[i, j]
                    if not np.isfinite(val):
                        label = "—"
                        text_colour = get_chart_text2()
                    else:
                        label = f"{val:.2f}"
                        # White text on dark/saturated cells, dark on light cells
                        norm_val = val / v_max  # in [-1, 1]
                        text_colour = "#FFFFFF" if abs(norm_val) >= 0.45 else "#1A1A1A"
                    ax.text(j, i, label,
                            ha="center", va="center",
                            color=text_colour,
                            fontsize=7, fontweight="bold")

            # Axis labels
            ax.set_yticks(range(n_rows))
            # Truncate long peak labels to keep the chart readable
            truncated_peak = [
                (lbl[:22] + "…") if len(lbl) > 25 else lbl
                for lbl in peak_labels
            ]
            ax.set_yticklabels(truncated_peak, fontsize=7)
            ax.set_xticks(range(n_cols))
            ax.set_xticklabels(element_labels, fontsize=8, rotation=45, ha="right")
            ax.set_xlabel("Elements", color=get_chart_text2(), fontsize=8)
            ax.set_ylabel("Peaks (wavelength)", color=get_chart_text2(), fontsize=8)
            ax.set_title(
                "Ambiguous Peaks vs Elements  (VC correlation)",
                color=get_chart_text(),
                fontsize=10, fontweight="bold",
            )

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
        """UX-optimised vertical funnel diagram for the multi-stage validation pipeline.

        UX principles applied:
          • Spatial separation — count INSIDE box (max contrast white-on-colour),
            title/description OUTSIDE LEFT (dark-on-dark bg, large enough to read),
            retention badge OUTSIDE RIGHT (coloured border pill).
          • Visual hierarchy — count (14 pt bold) > title (8.5 pt bold) >
            description (7.5 pt) > meta / filter labels (7 pt).
          • No text overlap — each element owns exactly one zone.
          • Colour consistency — filter annotations always C_WARN amber;
            retention badge border matches stage colour for quick association.
          • Minimum font size 7 pt so nothing is illegible at normal DPI.
        """
        ax.clear()
        fig = ax.get_figure()
        try:
            if stage_counts is None:
                ChartEngine._show_placeholder(ax, "Insufficient pipeline data")
                ChartEngine.apply_dark_style(fig, ax)
                return

            counts = [stage_counts.get(k, 0) for k in STAGE_KEYS]
            if sum(1 for c in counts if c > 0) < 2:
                ChartEngine._show_placeholder(ax, "Insufficient pipeline data")
                ChartEngine.apply_dark_style(fig, ax)
                return

            import matplotlib.patches as mpatches
            import matplotlib.colors as mcolors

            n = len(STAGE_KEYS)

            STAGE_TITLES = [
                "Detected Peaks",
                "NIST Matched",
                "Element Ranked",
                "Validated  (VC \u2265 0.50)",
                "Confirmed  (VC \u2265 0.70)",
            ]
            STAGE_STEPS = ["Step 2", "Step 3", "Step 4", "Step 5", "Step 5"]
            STAGE_DESC = [
                "All spectral peaks found by the detector",
                "Peaks matched against NIST atomic line database",
                "Element assigned & competition-ranked",
                "Line validated vs. reference (moderate confidence)",
                "High-confidence confirmed emission lines",
            ]

            # Blue → teal gradient
            rgb1 = mcolors.to_rgb(C_ACCENT)
            rgb2 = mcolors.to_rgb(C_ACCENT2)
            colours = [
                tuple(rgb1[k] + (rgb2[k] - rgb1[k]) * i / (n - 1) for k in range(3))
                for i in range(n)
            ]

            # ── Coordinate layout ────────────────────────────────────────────
            # x zones (normalised 0–1):
            #   [0.00–0.01]  left margin
            #   [0.01–0.30]  LEFT LABEL ZONE  (step badge, title, description)
            #   [0.30–0.72]  FUNNEL ZONE      (trapezoid + count)
            #   [0.72–0.74]  gap
            #   [0.74–0.99]  RIGHT BADGE ZONE (retention pill)
            LZ_X      = 0.01   # left label x anchor
            FZ_LEFT   = 0.30   # funnel zone left edge
            FZ_RIGHT  = 0.72   # funnel zone right edge
            FZ_CX     = (FZ_LEFT + FZ_RIGHT) / 2.0
            FZ_SPAN   = FZ_RIGHT - FZ_LEFT
            RZ_LEFT   = 0.745  # right zone left edge
            RZ_CX     = 0.865  # right zone centre x

            SLOT_H  = 1.10
            GAP_H   = 0.80    # taller gap = more space for filter annotation
            TOTAL_H = n * SLOT_H + (n - 1) * GAP_H

            max_count    = max(counts) if any(c > 0 for c in counts) else 1
            stage1_count = counts[0] if counts[0] > 0 else 1

            MAX_HALF = FZ_SPAN / 2.0
            MIN_HALF = FZ_SPAN * 0.14   # narrowest stage still clearly visible

            def _hw(count: int) -> float:
                r = count / max_count if max_count > 0 else 0
                return MIN_HALF + (MAX_HALF - MIN_HALF) * r

            ax.set_xlim(0.0, 1.0)
            ax.set_ylim(-0.15, TOTAL_H + 0.55)
            ax.axis("off")
            fig.patch.set_facecolor(get_chart_bg())
            ax.set_facecolor(get_chart_axes_bg())

            # ── Column header row ────────────────────────────────────────────
            HDR_Y = TOTAL_H + 0.42
            for x, label, ha in [
                (LZ_X,  "Stage",      "left"),
                (FZ_CX, "Count",      "center"),
                (RZ_CX, "Retention",  "center"),
            ]:
                ax.text(x, HDR_Y, label,
                        ha=ha, va="center",
                        color=get_chart_text2(),
                        fontsize=7.5, fontweight="bold")

            # thin separator under headers
            ax.axhline(TOTAL_H + 0.28, xmin=0.01, xmax=0.99,
                       color=get_chart_border(), linewidth=0.6, alpha=0.6)

            # ── Draw stages ──────────────────────────────────────────────────
            for i, (count, colour, title, step_lbl, desc) in enumerate(
                zip(counts, colours, STAGE_TITLES, STAGE_STEPS, STAGE_DESC)
            ):
                slot_top = TOTAL_H - i * (SLOT_H + GAP_H)
                slot_bot = slot_top - SLOT_H
                mid_y    = (slot_top + slot_bot) / 2.0

                hw_top = _hw(count)
                hw_bot = _hw(counts[i + 1]) if i < n - 1 else hw_top * 0.80

                # ── Trapezoid (funnel slice) ──────────────────────────────
                verts = [
                    (FZ_CX - hw_top, slot_top),
                    (FZ_CX + hw_top, slot_top),
                    (FZ_CX + hw_bot, slot_bot),
                    (FZ_CX - hw_bot, slot_bot),
                ]
                trap = mpatches.Polygon(
                    verts, closed=True,
                    facecolor=colour,
                    edgecolor=get_chart_bg(),
                    linewidth=2.0, zorder=3,
                )
                ax.add_patch(trap)

                # Subtle highlight stripe at top edge (depth cue)
                ax.plot(
                    [FZ_CX - hw_top + 0.005, FZ_CX + hw_top - 0.005],
                    [slot_top - 0.03, slot_top - 0.03],
                    color="#FFFFFF", alpha=0.15, linewidth=1.2, zorder=4,
                )

                # ── Count — dominant, white-on-colour ────────────────────
                ax.text(FZ_CX, mid_y + 0.15, f"{count:,}",
                        ha="center", va="center",
                        color="#FFFFFF",
                        fontsize=14, fontweight="bold", zorder=5)

                # "peaks / lines" unit label
                unit = "peaks" if i < 3 else "lines"
                ax.text(FZ_CX, mid_y - 0.12, unit,
                        ha="center", va="center",
                        color="#FFFFFF", alpha=0.65,
                        fontsize=7, zorder=5)

                # ── LEFT ZONE: step badge ─────────────────────────────────
                # Rounded pill badge: "Step N"
                badge_h = 0.24
                badge_w = 0.135
                badge_cx = LZ_X + badge_w / 2
                badge_cy = mid_y + 0.35
                badge = mpatches.FancyBboxPatch(
                    (LZ_X, badge_cy - badge_h / 2),
                    badge_w, badge_h,
                    boxstyle="round,pad=0.025",
                    facecolor=colour, edgecolor="none",
                    alpha=0.92, zorder=4,
                )
                ax.add_patch(badge)
                ax.text(badge_cx, badge_cy, step_lbl,
                        ha="center", va="center",
                        color="#FFFFFF",
                        fontsize=7, fontweight="bold", zorder=5)

                # Stage title
                ax.text(LZ_X, mid_y + 0.06, title,
                        ha="left", va="center",
                        color=get_chart_text(),
                        fontsize=8.5, fontweight="bold", zorder=4)

                # Description — secondary, smaller, muted
                ax.text(LZ_X, mid_y - 0.22, desc,
                        ha="left", va="center",
                        color=get_chart_text2(),
                        fontsize=7.0, zorder=4)

                # ── RIGHT ZONE: retention pill ────────────────────────────
                retention_pct = count / stage1_count * 100.0
                pill_h = 0.36
                pill_w = 0.225
                pill_box = mpatches.FancyBboxPatch(
                    (RZ_LEFT, mid_y - pill_h / 2),
                    pill_w, pill_h,
                    boxstyle="round,pad=0.025",
                    facecolor=get_chart_axes_bg(),
                    edgecolor=colour,
                    linewidth=1.2, zorder=4,
                )
                ax.add_patch(pill_box)
                ax.text(RZ_CX, mid_y + 0.08, f"{retention_pct:.0f}%",
                        ha="center", va="center",
                        color=colour,
                        fontsize=9, fontweight="bold", zorder=5)
                ax.text(RZ_CX, mid_y - 0.13, "retained",
                        ha="center", va="center",
                        color=get_chart_text2(),
                        fontsize=6.5, zorder=5)

                # ── ARROW + FILTER ANNOTATION between stages ──────────────
                if i < n - 1:
                    a_top = slot_bot - 0.05
                    a_bot = slot_bot - GAP_H + 0.09
                    a_mid = (a_top + a_bot) / 2.0

                    # Arrow centred in funnel zone
                    ax.annotate(
                        "",
                        xy=(FZ_CX, a_bot),
                        xytext=(FZ_CX, a_top),
                        arrowprops=dict(
                            arrowstyle="-|>",
                            color=get_chart_text2(),
                            lw=1.6,
                            mutation_scale=11,
                        ),
                        zorder=5,
                    )

                    nxt = counts[i + 1]
                    if count > 0 and nxt < count:
                        dropped = count - nxt
                        pct     = dropped / count * 100.0
                        # Amber pill to the right of the arrow
                        fp_x   = FZ_CX + 0.03
                        fp_w   = 0.18
                        fp_h   = 0.32
                        fp_box = mpatches.FancyBboxPatch(
                            (fp_x, a_mid - fp_h / 2),
                            fp_w, fp_h,
                            boxstyle="round,pad=0.02",
                            facecolor=get_chart_axes_bg(),
                            edgecolor=C_WARN,
                            linewidth=0.9, zorder=5,
                        )
                        ax.add_patch(fp_box)
                        fp_cx = fp_x + fp_w / 2
                        ax.text(fp_cx, a_mid + 0.07,
                                f"\u2212{dropped:,} filtered",
                                ha="center", va="center",
                                color=C_WARN,
                                fontsize=7, fontweight="bold", zorder=6)
                        ax.text(fp_cx, a_mid - 0.10,
                                f"{pct:.0f}% removed",
                                ha="center", va="center",
                                color=get_chart_text2(),
                                fontsize=6.5, zorder=6)
                    elif count > 0:
                        ax.text(FZ_CX + 0.03, a_mid,
                                "no reduction",
                                ha="left", va="center",
                                color=get_chart_text2(),
                                fontsize=7, zorder=5)

            ax.set_title(
                "Multi-Stage Validation Pipeline",
                color=get_chart_text(),
                fontsize=10, fontweight="bold", pad=10,
            )

            try:
                fig.tight_layout(pad=1.2)
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
