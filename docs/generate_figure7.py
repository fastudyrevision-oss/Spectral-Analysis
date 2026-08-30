# -*- coding: utf-8 -*-
"""
Generate Figure 7: Elemental preference algorithm flowchart.
Same clean vertical style as Figure 3.

Run:
    python docs/generate_figure7.py

Output:
    docs/figure7_elemental_preference.png
    docs/figure7_elemental_preference.pdf
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent

# ── palette ──────────────────────────────────────────────────────────────────
WHITE      = "#FFFFFF"

# Neutral (input / output)
NEUTRAL_BG = "#F5EFE8"
NEUTRAL_BD = "#C4A98A"
NEUTRAL_TT = "#2C2C2C"
NEUTRAL_ST = "#666666"

# Blue – data loading
BLUE_BG = "#DDEEFF"
BLUE_BD = "#2E6DA4"
BLUE_TT = "#1A3F6F"
BLUE_ST = "#2E6DA4"

# Green – signal processing
GREEN_BG = "#D6F0E8"
GREEN_BD = "#3BAF87"
GREEN_TT = "#1A6B52"
GREEN_ST = "#3BAF87"

# Purple – competition / ranking
PURPLE_BG = "#DDD8F5"
PURPLE_BD = "#7B6FC4"
PURPLE_TT = "#3D2F8A"
PURPLE_ST = "#7B6FC4"

# Orange – output / winner
ORANGE_BG = "#FAE0D4"
ORANGE_BD = "#D4724A"
ORANGE_TT = "#8B3010"
ORANGE_ST = "#D4724A"

ARROW_COL = "#999999"

# ── step definitions ──────────────────────────────────────────────────────────
#  (title, subtitle, bg, border, title_color, subtitle_color)
STEPS = [
    (
        "Load NIST match files",
        "Per-element CSVs from Step 3",
        NEUTRAL_BG, NEUTRAL_BD, NEUTRAL_TT, NEUTRAL_ST,
    ),
    (
        "Combine & filter matches",
        "Merge all elements · drop Score ≤ MIN_SCORE",
        BLUE_BG, BLUE_BD, BLUE_TT, BLUE_ST,
    ),
    (
        "Build score pivot table",
        "Rows = wavelengths · columns = elements · values = max score",
        GREEN_BG, GREEN_BD, GREEN_TT, GREEN_ST,
    ),
    (
        "Peak-wise competition",
        "Each peak won by element with highest score",
        PURPLE_BG, PURPLE_BD, PURPLE_TT, PURPLE_ST,
    ),
    (
        "Score formula applied",
        "Score = (Aki × I_rel) / (Δλ + ε)",
        PURPLE_BG, PURPLE_BD, PURPLE_TT, PURPLE_ST,
    ),
    (
        "Count wins per element",
        "Winner tallied across all peaks",
        PURPLE_BG, PURPLE_BD, PURPLE_TT, PURPLE_ST,
    ),
    (
        "Rank elements",
        "Sort by win count · aggregate total score",
        ORANGE_BG, ORANGE_BD, ORANGE_TT, ORANGE_ST,
    ),
    (
        "Identify primary element",
        "Element with highest win count = preferred assignment",
        ORANGE_BG, ORANGE_BD, ORANGE_TT, ORANGE_ST,
    ),
    (
        "Export results",
        "Ranking CSV · competition CSV · winner-lines CSV",
        NEUTRAL_BG, NEUTRAL_BD, NEUTRAL_TT, NEUTRAL_ST,
    ),
]

N       = len(STEPS)
BOX_W   = 4.80
BOX_H   = 0.82
GAP     = 0.36

FIG_W   = 7.0
TOP_M   = 0.55
BOT_M   = 0.90
FIG_H   = TOP_M + N * BOX_H + (N - 1) * GAP + BOT_M

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), facecolor=WHITE)
ax.set_facecolor(WHITE)
ax.set_xlim(0, FIG_W)
ax.set_ylim(0, FIG_H)
ax.axis("off")

CX = FIG_W / 2
BX = CX - BOX_W / 2


def box_bottom(i):
    return FIG_H - TOP_M - (i + 1) * BOX_H - i * GAP


# ── draw boxes + arrows ───────────────────────────────────────────────────────
for i, (title, subtitle, bg, bd, tc, sc) in enumerate(STEPS):
    yb = box_bottom(i)
    cy = yb + BOX_H / 2

    patch = FancyBboxPatch(
        (BX, yb), BOX_W, BOX_H,
        boxstyle="round,pad=0.10",
        linewidth=1.3,
        edgecolor=bd,
        facecolor=bg,
        zorder=3,
    )
    ax.add_patch(patch)

    ax.text(CX, cy + 0.13, title,
            ha="center", va="center",
            fontsize=12, fontweight="bold", color=tc, zorder=4)

    ax.text(CX, cy - 0.17, subtitle,
            ha="center", va="center",
            fontsize=9.5, color=sc, zorder=4)

    # arrow to next box
    if i < N - 1:
        y_top_next = box_bottom(i + 1) + BOX_H
        ax.annotate(
            "",
            xy=(CX, y_top_next + 0.03),
            xytext=(CX, yb - 0.03),
            arrowprops=dict(
                arrowstyle="-|>",
                color=ARROW_COL,
                lw=1.4,
                mutation_scale=12,
            ),
            zorder=2,
        )

# ── legend ────────────────────────────────────────────────────────────────────
leg_patches = [
    mpatches.Patch(facecolor=BLUE_BG,   edgecolor=BLUE_BD,   label="Data loading",        linewidth=1.1),
    mpatches.Patch(facecolor=GREEN_BG,  edgecolor=GREEN_BD,  label="Score computation",   linewidth=1.1),
    mpatches.Patch(facecolor=PURPLE_BG, edgecolor=PURPLE_BD, label="Competition & ranking", linewidth=1.1),
    mpatches.Patch(facecolor=ORANGE_BG, edgecolor=ORANGE_BD, label="Assignment & output",  linewidth=1.1),
]
ax.legend(
    handles=leg_patches,
    loc="lower center",
    ncol=2,
    bbox_to_anchor=(0.5, 0.0),
    frameon=False,
    fontsize=9,
    labelcolor="#333333",
    handlelength=1.6,
    handleheight=1.0,
    borderpad=0.4,
    columnspacing=1.2,
)

# ── save ──────────────────────────────────────────────────────────────────────
for ext in ("png", "pdf"):
    out = OUTPUT_DIR / f"figure7_elemental_preference.{ext}"
    fig.savefig(out, dpi=220, bbox_inches="tight",
                facecolor=WHITE, edgecolor="none")
    print(f"Saved: {out}")

plt.close(fig)
print("Done.")
