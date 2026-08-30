# -*- coding: utf-8 -*-
"""
Generate Figure 1: Overall architecture of the LIBS spectral analysis pipeline,
from raw spectrum import to the final analysis report.

Run:
    python docs/generate_figure1.py

Output:
    docs/figure1_pipeline_architecture.png
    docs/figure1_pipeline_architecture.pdf
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent

# ── colour palette ──────────────────────────────────────────────────────────
BG          = "#0D1117"   # figure background
PANEL_DARK  = "#161B22"   # step-box background
BORDER_COL  = "#30363D"   # default border / subtle lines
TEXT_MAIN   = "#E6EDF3"   # primary label text
TEXT_SUB    = "#8B949E"   # secondary / caption text
TEXT_STEP   = "#58A6FF"   # step number accent

STEP_COLORS = [
    "#1F6FEB",  # Step 1 – blue
    "#388BFD",  # Step 2 – lighter blue
    "#3FB950",  # Step 3 – green
    "#F78166",  # Step 4 – coral/orange
    "#D2A8FF",  # Step 5 – purple
    "#79C0FF",  # Step 6 – sky
]

ARROW_COLOR = "#58A6FF"

# ── figure layout ────────────────────────────────────────────────────────────
FIG_W, FIG_H = 16, 14
fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), facecolor=BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 16)
ax.set_ylim(0, 14)
ax.axis("off")

# ── helper: rounded box ──────────────────────────────────────────────────────
def rounded_box(ax, x, y, w, h, color, alpha=1.0, zorder=3, linewidth=1.5):
    """Draw a rounded rectangle and return its patch."""
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.06",
        linewidth=linewidth,
        edgecolor=color,
        facecolor=PANEL_DARK,
        alpha=alpha,
        zorder=zorder,
    )
    ax.add_patch(box)
    return box


def arrow(ax, x1, y1, x2, y2, color=ARROW_COLOR, zorder=4):
    """Draw a straight annotating arrow."""
    ax.annotate(
        "",
        xy=(x2, y2),
        xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            lw=1.8,
            mutation_scale=14,
        ),
        zorder=zorder,
    )


# ════════════════════════════════════════════════════════════════════════════
# 0.  TITLE
# ════════════════════════════════════════════════════════════════════════════
ax.text(
    8, 13.55,
    "Figure 1.  Overall Architecture of the LIBS Spectral Analysis Pipeline",
    ha="center", va="center",
    fontsize=14, fontweight="bold",
    color=TEXT_MAIN,
    zorder=5,
)
ax.text(
    8, 13.15,
    "From raw spectrum import to the final analysis report",
    ha="center", va="center",
    fontsize=10, style="italic",
    color=TEXT_SUB,
    zorder=5,
)

# thin separator
ax.axhline(12.90, xmin=0.03, xmax=0.97, color=BORDER_COL, lw=0.8, zorder=3)

# ════════════════════════════════════════════════════════════════════════════
# 1.  INPUT  (top)
# ════════════════════════════════════════════════════════════════════════════
IN_X, IN_Y, IN_W, IN_H = 5.8, 11.8, 4.4, 0.95
rounded_box(ax, IN_X, IN_Y, IN_W, IN_H, color="#58A6FF", linewidth=2)
ax.text(IN_X + IN_W/2, IN_Y + IN_H/2 + 0.13,
        "RAW LIBS SPECTRUM  (CSV input)",
        ha="center", va="center", fontsize=10.5, fontweight="bold",
        color="#58A6FF", zorder=5)
ax.text(IN_X + IN_W/2, IN_Y + IN_H/2 - 0.18,
        "Wavelength (nm)  ×  Intensity (a.u.)",
        ha="center", va="center", fontsize=8.5,
        color=TEXT_SUB, zorder=5)

# arrow from input box down to step 1
arrow(ax, 8.0, IN_Y, 8.0, 11.18)

# ════════════════════════════════════════════════════════════════════════════
# 2.  SIX PIPELINE STEPS  (centre column, evenly spaced)
# ════════════════════════════════════════════════════════════════════════════
STEP_DATA = [
    # (label, subtitle, algorithm_hints, output_label, colour)
    (
        "Step 1",
        "Baseline Correction",
        "Savitzky-Golay smoothing  ·  Asymmetric Least Squares (ALS) background removal",
        "Corrected spectrum CSV",
        STEP_COLORS[0],
    ),
    (
        "Step 2",
        "Peak Detection",
        "scipy find_peaks  ·  noise-adaptive threshold  ·  local baseline filter",
        "Detected peaks CSV  (λ, intensity)",
        STEP_COLORS[1],
    ),
    (
        "Step 3",
        "NIST Element Identification",
        "Fuzzy match ±0.2 nm  ·  score = (Aki × rel_int) / (Δλ + ε)  ·  multi-database",
        "Per-element match CSVs",
        STEP_COLORS[2],
    ),
    (
        "Step 4",
        "Elemental Preference Analysis",
        "Peak-wise scoring competition  ·  win-count ranking  ·  primary element ID",
        "Ranking CSV  ·  winner-lines CSV",
        STEP_COLORS[3],
    ),
    (
        "Step 5",
        "Reference Spectrum Validation",
        "Pearson correlation (VC)  ·  tier classification: Excellent / Good / Moderate / Weak",
        "Validation results CSV  ·  PDF report",
        STEP_COLORS[4],
    ),
    (
        "Step 6",
        "Model Performance Metrics",
        "Pipeline funnel  ·  Accuracy / Precision / Recall / F1-Score  ·  SBR improvement",
        "Metrics CSV  ·  summary table",
        STEP_COLORS[5],
    ),
]

# vertical positions of step-box bottoms (descending)
STEP_TOP    = 11.10   # bottom of first step box top edge
STEP_H      = 1.12    # box height
STEP_GAP    = 0.30    # gap between boxes
BOX_X       = 2.40    # left edge of step boxes
BOX_W       = 11.20   # width of step boxes

step_centers_y = []   # record y-centre of each box for arrows

for i, (lbl, title, algo, output, col) in enumerate(STEP_DATA):
    y_top = STEP_TOP - i * (STEP_H + STEP_GAP)
    y_bot = y_top - STEP_H
    cy    = (y_top + y_bot) / 2
    step_centers_y.append(cy)

    # main box
    rounded_box(ax, BOX_X, y_bot, BOX_W, STEP_H, color=col, linewidth=1.6)

    # coloured left accent bar
    bar = FancyBboxPatch(
        (BOX_X + 0.05, y_bot + 0.07),
        0.28, STEP_H - 0.14,
        boxstyle="round,pad=0.02",
        linewidth=0,
        facecolor=col,
        zorder=5,
    )
    ax.add_patch(bar)

    # step number inside bar
    ax.text(
        BOX_X + 0.19, cy,
        str(i + 1),
        ha="center", va="center",
        fontsize=13, fontweight="bold",
        color="white", zorder=6,
    )

    # title
    ax.text(
        BOX_X + 0.60, cy + 0.22,
        f"{lbl}: {title}",
        ha="left", va="center",
        fontsize=10.5, fontweight="bold",
        color=col, zorder=5,
    )

    # algorithm hint
    ax.text(
        BOX_X + 0.60, cy - 0.04,
        algo,
        ha="left", va="center",
        fontsize=8.0,
        color=TEXT_SUB, zorder=5,
    )

    # output badge (right-aligned)
    OUT_X = BOX_X + BOX_W - 0.15
    ax.text(
        OUT_X, cy - 0.28,
        f"↳  {output}",
        ha="right", va="center",
        fontsize=7.8, style="italic",
        color=TEXT_MAIN, zorder=5,
    )

    # downward arrow to next step
    if i < len(STEP_DATA) - 1:
        arrow(ax, 8.0, y_bot, 8.0, y_bot - STEP_GAP + 0.02)

# ════════════════════════════════════════════════════════════════════════════
# 3.  SESSION PERSISTENCE  (right side panel)
# ════════════════════════════════════════════════════════════════════════════
SP_X, SP_Y, SP_W, SP_H = 14.10, 5.20, 1.65, 2.90
rounded_box(ax, SP_X, SP_Y, SP_W, SP_H, color="#6E7681", linewidth=1.2)
ax.text(
    SP_X + SP_W / 2, SP_Y + SP_H - 0.28,
    "Session\nPersistence",
    ha="center", va="center",
    fontsize=8.5, fontweight="bold",
    color="#8B949E", zorder=5,
)
ax.text(
    SP_X + SP_W / 2, SP_Y + SP_H / 2 - 0.25,
    "Auto save/restore\nSteps 2 – 5\n.session/*.csv",
    ha="center", va="center",
    fontsize=7.5,
    color=TEXT_SUB, zorder=5,
    linespacing=1.5,
)

# dashed bracket lines from right edge of step boxes 2-5 to the session panel
for i in range(1, 5):  # step indices 1..4  →  Steps 2-5
    cy = step_centers_y[i]
    ax.annotate(
        "",
        xy=(SP_X, SP_Y + SP_H / 2),
        xytext=(BOX_X + BOX_W + 0.05, cy),
        arrowprops=dict(
            arrowstyle="-",
            color="#6E7681",
            lw=0.9,
            linestyle="dashed",
            connectionstyle="arc3,rad=0.0",
        ),
        zorder=2,
    )

# ════════════════════════════════════════════════════════════════════════════
# 4.  NIST DATABASE  (left side panel, beside step 3)
# ════════════════════════════════════════════════════════════════════════════
DB_X, DB_Y, DB_W, DB_H = 0.25, 7.30, 1.85, 1.75
rounded_box(ax, DB_X, DB_Y, DB_W, DB_H, color=STEP_COLORS[2], linewidth=1.2)
ax.text(
    DB_X + DB_W / 2, DB_Y + DB_H - 0.30,
    "NIST\nDatabase",
    ha="center", va="center",
    fontsize=9, fontweight="bold",
    color=STEP_COLORS[2], zorder=5,
)
ax.text(
    DB_X + DB_W / 2, DB_Y + DB_H / 2 - 0.25,
    "Multi-file CSV\nAtomic lines\n(λ, Aki, rel_int)",
    ha="center", va="center",
    fontsize=7.5,
    color=TEXT_SUB, zorder=5,
    linespacing=1.5,
)

# arrow from NIST DB to step 3 left edge
cy3 = step_centers_y[2]
arrow(ax, DB_X + DB_W, DB_Y + DB_H / 2, BOX_X - 0.02, cy3, color=STEP_COLORS[2])

# ════════════════════════════════════════════════════════════════════════════
# 5.  REFERENCE SPECTRUM  (left side, beside step 5)
# ════════════════════════════════════════════════════════════════════════════
RF_X, RF_Y, RF_W, RF_H = 0.25, 4.20, 1.85, 1.65
rounded_box(ax, RF_X, RF_Y, RF_W, RF_H, color=STEP_COLORS[4], linewidth=1.2)
ax.text(
    RF_X + RF_W / 2, RF_Y + RF_H - 0.30,
    "Reference\nSpectrum",
    ha="center", va="center",
    fontsize=9, fontweight="bold",
    color=STEP_COLORS[4], zorder=5,
)
ax.text(
    RF_X + RF_W / 2, RF_Y + RF_H / 2 - 0.28,
    "Pure-element\nCSV\n(user-supplied)",
    ha="center", va="center",
    fontsize=7.5,
    color=TEXT_SUB, zorder=5,
    linespacing=1.5,
)

# arrow from reference spectrum to step 5 left edge
cy5 = step_centers_y[4]
arrow(ax, RF_X + RF_W, RF_Y + RF_H / 2, BOX_X - 0.02, cy5, color=STEP_COLORS[4])

# ════════════════════════════════════════════════════════════════════════════
# 6.  OUTPUT  (bottom)
# ════════════════════════════════════════════════════════════════════════════
# compute bottom of last step
y_last_bot = STEP_TOP - (len(STEP_DATA) - 1) * (STEP_H + STEP_GAP) - STEP_H
arrow(ax, 8.0, y_last_bot, 8.0, y_last_bot - 0.28 + 0.02)

OUT_BOX_Y = y_last_bot - 0.30 - 0.85
OUT_BOX_H = 0.85

rounded_box(ax, 1.40, OUT_BOX_Y, 13.2, OUT_BOX_H, color="#3FB950", linewidth=2.0)
ax.text(
    8.0, OUT_BOX_Y + OUT_BOX_H / 2 + 0.16,
    "FINAL ANALYSIS REPORT",
    ha="center", va="center",
    fontsize=11, fontweight="bold",
    color="#3FB950", zorder=5,
)

# output format badges
BADGES = [
    ("CSV", STEP_COLORS[0]),
    ("PNG charts", STEP_COLORS[1]),
    ("PDF report", STEP_COLORS[2]),
    ("Performance metrics", STEP_COLORS[3]),
    ("Analysis Summary", STEP_COLORS[4]),
]
total_w = 13.2
bx = 1.40 + 0.30
for badge_text, badge_col in BADGES:
    bw = total_w / len(BADGES) - 0.20
    rect = FancyBboxPatch(
        (bx, OUT_BOX_Y + 0.06), bw, 0.27,
        boxstyle="round,pad=0.03",
        linewidth=1,
        edgecolor=badge_col,
        facecolor=BG,
        zorder=5,
    )
    ax.add_patch(rect)
    ax.text(
        bx + bw / 2, OUT_BOX_Y + 0.195,
        badge_text,
        ha="center", va="center",
        fontsize=7.5,
        color=badge_col, zorder=6,
    )
    bx += bw + 0.20

# ════════════════════════════════════════════════════════════════════════════
# 7.  LEGEND / ANNOTATIONS
# ════════════════════════════════════════════════════════════════════════════
ax.axhline(0.85, xmin=0.03, xmax=0.97, color=BORDER_COL, lw=0.6, zorder=2)

legend_items = [
    mpatches.Patch(color=STEP_COLORS[0], label="Signal conditioning"),
    mpatches.Patch(color=STEP_COLORS[1], label="Feature extraction"),
    mpatches.Patch(color=STEP_COLORS[2], label="Database matching"),
    mpatches.Patch(color=STEP_COLORS[3], label="Elemental analysis"),
    mpatches.Patch(color=STEP_COLORS[4], label="Validation"),
    mpatches.Patch(color=STEP_COLORS[5], label="Performance metrics"),
]
leg = ax.legend(
    handles=legend_items,
    loc="lower center",
    ncol=6,
    bbox_to_anchor=(0.5, 0.01),
    frameon=True,
    framealpha=0.15,
    edgecolor=BORDER_COL,
    fontsize=8,
    labelcolor=TEXT_MAIN,
    facecolor=PANEL_DARK,
    handlelength=1.2,
    handleheight=0.9,
    borderpad=0.6,
)

# ════════════════════════════════════════════════════════════════════════════
# 8.  SAVE
# ════════════════════════════════════════════════════════════════════════════
for ext in ("png", "pdf"):
    out_path = OUTPUT_DIR / f"figure1_pipeline_architecture.{ext}"
    fig.savefig(
        out_path,
        dpi=220,
        bbox_inches="tight",
        facecolor=BG,
        edgecolor="none",
    )
    print(f"Saved: {out_path}")

plt.close(fig)
print("Done.")
