# -*- coding: utf-8 -*-
"""
Generate Figure 3: Flowchart of the software development pipeline
from raw spectrum input to exported report.

Clean, white-background style matching the reference image.

Run:
    python docs/generate_figure3.py

Output:
    docs/figure3_pipeline_flowchart.png
    docs/figure3_pipeline_flowchart.pdf
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent

# ── palette (matches reference image) ───────────────────────────────────────
WHITE       = "#FFFFFF"
NEUTRAL_BG  = "#F5EFE8"   # warm cream  – Import / Export boxes
NEUTRAL_BD  = "#C4A98A"   # warm border

GREEN_BG    = "#D6F0E8"   # mint green  – signal processing
GREEN_BD    = "#3BAF87"
GREEN_TT    = "#1A6B52"   # title text
GREEN_ST    = "#3BAF87"   # subtitle text

PURPLE_BG   = "#DDD8F5"   # lavender    – element identification
PURPLE_BD   = "#7B6FC4"
PURPLE_TT   = "#3D2F8A"
PURPLE_ST   = "#7B6FC4"

ORANGE_BG   = "#FAE0D4"   # peach       – quality assessment
ORANGE_BD   = "#D4724A"
ORANGE_TT   = "#8B3010"
ORANGE_ST   = "#D4724A"

ARROW_COL   = "#8A8A8A"
LEG_TEXT    = "#333333"
LABEL_DARK  = "#2C2C2C"   # title text for neutral boxes

# ── step definitions ─────────────────────────────────────────────────────────
#   (title, subtitle, bg, border, title_color, sub_color)
STEPS = [
    ("Import",               "Raw CSV spectrum",                  NEUTRAL_BG, NEUTRAL_BD, LABEL_DARK, "#666666"),
    ("Preprocessing",        "SG smoothing, ALS baseline",        GREEN_BG,   GREEN_BD,   GREEN_TT,   GREEN_ST),
    ("Peak detection",       "Adaptive threshold peaks",          GREEN_BG,   GREEN_BD,   GREEN_TT,   GREEN_ST),
    ("NIST search",          "Multi-parameter line matching",     PURPLE_BG,  PURPLE_BD,  PURPLE_TT,  PURPLE_ST),
    ("Preference ranking",   "Resolves multi-element ties",       PURPLE_BG,  PURPLE_BD,  PURPLE_TT,  PURPLE_ST),
    ("Validation",           "Pearson correlation vs reference",  ORANGE_BG,  ORANGE_BD,  ORANGE_TT,  ORANGE_ST),
    ("Performance evaluation","Summary classification metrics",   ORANGE_BG,  ORANGE_BD,  ORANGE_TT,  ORANGE_ST),
    ("Export / report",      "CSV, PNG, PDF output",              NEUTRAL_BG, NEUTRAL_BD, LABEL_DARK, "#666666"),
]

N        = len(STEPS)
BOX_W    = 4.80
BOX_H    = 0.82
GAP      = 0.36          # vertical gap between boxes
ARROW_H  = GAP           # arrow spans the full gap

FIG_W    = 7.0
# total height: N boxes + (N-1) gaps + top/bottom margin + legend
TOP_M    = 0.55
BOT_M    = 0.90
FIG_H    = TOP_M + N * BOX_H + (N - 1) * GAP + BOT_M

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), facecolor=WHITE)
ax.set_facecolor(WHITE)
ax.set_xlim(0, FIG_W)
ax.set_ylim(0, FIG_H)
ax.axis("off")

CX = FIG_W / 2           # horizontal centre
BX = CX - BOX_W / 2      # left edge of all boxes

def box_bottom(i):
    """Y-coordinate of the bottom edge of box i (0 = top step)."""
    return FIG_H - TOP_M - (i + 1) * BOX_H - i * GAP

# ── draw boxes + arrows ──────────────────────────────────────────────────────
for i, (title, subtitle, bg, bd, tc, sc) in enumerate(STEPS):
    yb = box_bottom(i)
    yt = yb + BOX_H
    cy = yb + BOX_H / 2

    # box
    patch = FancyBboxPatch(
        (BX, yb), BOX_W, BOX_H,
        boxstyle="round,pad=0.10",
        linewidth=1.3,
        edgecolor=bd,
        facecolor=bg,
        zorder=3,
    )
    ax.add_patch(patch)

    # title
    ax.text(CX, cy + 0.13, title,
            ha="center", va="center",
            fontsize=12, fontweight="bold",
            color=tc, zorder=4)

    # subtitle
    ax.text(CX, cy - 0.17, subtitle,
            ha="center", va="center",
            fontsize=9.5,
            color=sc, zorder=4)

    # downward arrow to next box
    if i < N - 1:
        arrow_y_top = yb          # bottom of current box
        arrow_y_bot = box_bottom(i + 1) + BOX_H  # top of next box
        mid_y = (arrow_y_top + arrow_y_bot) / 2
        ax.annotate(
            "",
            xy=(CX, arrow_y_bot + 0.03),
            xytext=(CX, arrow_y_top - 0.03),
            arrowprops=dict(
                arrowstyle="-|>",
                color=ARROW_COL,
                lw=1.4,
                mutation_scale=12,
            ),
            zorder=2,
        )

# ── legend ───────────────────────────────────────────────────────────────────
leg_patches = [
    mpatches.Patch(facecolor=GREEN_BG,  edgecolor=GREEN_BD,  label="Signal processing",      linewidth=1.1),
    mpatches.Patch(facecolor=PURPLE_BG, edgecolor=PURPLE_BD, label="Element identification", linewidth=1.1),
    mpatches.Patch(facecolor=ORANGE_BG, edgecolor=ORANGE_BD, label="Quality assessment",     linewidth=1.1),
]
leg = ax.legend(
    handles=leg_patches,
    loc="lower center",
    ncol=3,
    bbox_to_anchor=(0.5, 0.0),
    frameon=False,
    fontsize=9,
    labelcolor=LEG_TEXT,
    handlelength=1.6,
    handleheight=1.0,
    borderpad=0.4,
    columnspacing=1.2,
)

# ── save ─────────────────────────────────────────────────────────────────────
for ext in ("png", "pdf"):
    out = OUTPUT_DIR / f"figure3_pipeline_flowchart.{ext}"
    fig.savefig(out, dpi=220, bbox_inches="tight",
                facecolor=WHITE, edgecolor="none")
    print(f"Saved: {out}")

plt.close(fig)
print("Done.")
