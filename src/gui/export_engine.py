# -*- coding: utf-8 -*-
"""
ExportEngine — Spectral Analysis Software
src/gui/export_engine.py

Stateless export functions for Step 4 (Elemental Preferences) and
Step 5 (Validation).  Handles CSV, PNG, and PDF (via reportlab) output.

All functions are module-level; no class instantiation is required.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd
from matplotlib.figure import Figure

from src.gui.theme import C_BG_DEEP
from src.gui.charts import ChartEngine

if TYPE_CHECKING:
    pass  # kept for future type-only imports

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _figure_to_image_buffer(fig: Figure) -> BytesIO:
    """Render a matplotlib *fig* to an in-memory PNG buffer.

    Parameters
    ----------
    fig:
        The matplotlib Figure to render.

    Returns
    -------
    BytesIO
        A seeked-to-start buffer containing the PNG byte data.
    """
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor())
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# PNG export helpers
# ---------------------------------------------------------------------------

def save_figure_png(fig: Figure, filepath: Path, dpi: int = 150) -> Path:
    """Save a matplotlib *fig* as a PNG file.

    The figure facecolor is set to ``C_BG_DEEP`` before saving so that the
    exported image matches the application's dark theme.  On ``OSError`` any
    partially written file is removed and the exception is re-raised.

    Parameters
    ----------
    fig:
        The matplotlib Figure to save.
    filepath:
        Destination path (including filename and ``.png`` extension).
    dpi:
        Resolution in dots-per-inch; clamped to at least 150.

    Returns
    -------
    Path
        The path that was written.

    Raises
    ------
    OSError
        If the file cannot be written.
    """
    effective_dpi = max(150, dpi)
    filepath = Path(filepath)

    # Store original facecolor so we can restore it afterwards
    original_facecolor = fig.get_facecolor()
    fig.set_facecolor(C_BG_DEEP)

    try:
        fig.savefig(filepath, format="png", dpi=effective_dpi, facecolor=C_BG_DEEP)
    except OSError:
        filepath.unlink(missing_ok=True)
        raise
    finally:
        # Restore original facecolor so the live canvas is not affected
        fig.set_facecolor(original_facecolor)

    return filepath


def export_step4_png(
    ranking_fig: Figure,
    scatter_fig: Figure,
    directory: Path,
) -> list[Path]:
    """Save the Ranking Chart and Score Scatter as PNG files.

    Parameters
    ----------
    ranking_fig:
        The matplotlib Figure containing the ranking bar chart.
    scatter_fig:
        The matplotlib Figure containing the score scatter plot.
    directory:
        Target directory.  Must already exist.

    Returns
    -------
    list[Path]
        ``[ranking_chart.png path, score_scatter.png path]``

    Raises
    ------
    OSError
        If either file cannot be written.
    """
    directory = Path(directory)
    ranking_path = save_figure_png(ranking_fig, directory / "ranking_chart.png")
    scatter_path = save_figure_png(scatter_fig, directory / "score_scatter.png")
    return [ranking_path, scatter_path]


def export_step5_png(vc_fig: Figure, filepath: Path) -> Path:
    """Save the VC Histogram as a PNG file.

    Parameters
    ----------
    vc_fig:
        The matplotlib Figure containing the VC histogram.
    filepath:
        Destination file path.

    Returns
    -------
    Path
        The written path.

    Raises
    ------
    OSError
        If the file cannot be written.
    """
    return save_figure_png(vc_fig, filepath)


# ---------------------------------------------------------------------------
# CSV export helpers
# ---------------------------------------------------------------------------

def export_step4_csv(
    ranking_df: pd.DataFrame,
    winner_lines_df: pd.DataFrame,
    competition_df: pd.DataFrame,
    directory: Path,
    base: str = "analysis",
) -> list[Path]:
    """Write Step 4 results to three CSV files in *directory*.

    Files written:
    - ``{base}_ranking.csv``
    - ``{base}_competition.csv``
    - ``{base}_winners.csv``

    Each file contains a header row matching the DataFrame column names.
    On ``OSError`` any partially written files are removed and the exception
    is re-raised.

    Parameters
    ----------
    ranking_df:
        DataFrame with Element ranking data.
    winner_lines_df:
        DataFrame with per-wavelength winner line data.
    competition_df:
        DataFrame with full competition data.
    directory:
        Target directory (must already exist).
    base:
        Filename prefix; defaults to ``"analysis"``.

    Returns
    -------
    list[Path]
        Paths of the three written files (ranking, competition, winners).

    Raises
    ------
    OSError
        If any file cannot be written.
    """
    directory = Path(directory)
    ranking_path    = directory / f"{base}_ranking.csv"
    competition_path = directory / f"{base}_competition.csv"
    winners_path    = directory / f"{base}_winners.csv"

    written: list[Path] = []
    try:
        ranking_df.to_csv(ranking_path, index=False)
        written.append(ranking_path)

        competition_df.to_csv(competition_path, index=False)
        written.append(competition_path)

        winner_lines_df.to_csv(winners_path, index=False)
        written.append(winners_path)

    except OSError:
        for p in written:
            p.unlink(missing_ok=True)
        raise

    return [ranking_path, competition_path, winners_path]


def export_step5_csv(
    validation_results_df: pd.DataFrame,
    filepath: Path,
) -> Path:
    """Write Step 5 validation results to a single CSV file.

    The file contains a header row matching the DataFrame column names.
    ``OSError`` is re-raised without swallowing.

    Parameters
    ----------
    validation_results_df:
        DataFrame with Validation results.
    filepath:
        Destination file path.

    Returns
    -------
    Path
        The written path.

    Raises
    ------
    OSError
        If the file cannot be written.
    """
    filepath = Path(filepath)
    try:
        validation_results_df.to_csv(filepath, index=False)
    except OSError:
        raise
    return filepath


# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------

def generate_pdf_report(
    validation_results_df: pd.DataFrame,
    params: dict,
    vc_fig: Figure,
    processed_filename: str,
    reference_filename: str,
    target_wavelengths: list[float],
    filepath: Path,
    step4_results: dict | None = None,
    ranking_fig: Figure | None = None,
) -> Path:
    """Generate a comprehensive LIBS Validation Report PDF.

    The report contains:
    1. Cover page — application name, report title, ISO 8601 timestamp,
       input filenames.
    2. Parameters section — WINDOW, MIN_POINTS, VC_THRESHOLD.
    3. Summary section — total validated, per-tier counts, average VC.
    4. Detailed results table — one row per wavelength; "No results available"
       if *validation_results_df* is empty.
    5. VC Histogram embedded as an image.
    6. Selected wavelengths list.
    7. (Optional) Step 4 summary — top-5 elements table + ranking chart image;
       included when *step4_results* is not ``None``.

    Document metadata: title = "LIBS Validation Report",
    author = "Spectral Analysis Software".

    On any exception the partial file is deleted and the exception is re-raised.

    Parameters
    ----------
    validation_results_df:
        DataFrame with columns Wavelength_nm, Validation_Coefficient, Status.
    params:
        Dict with keys ``WINDOW``, ``MIN_POINTS``, ``VC_THRESHOLD``.
    vc_fig:
        Pre-rendered VC Histogram Figure.
    processed_filename:
        Name of the processed spectrum input file.
    reference_filename:
        Name of the reference spectrum input file.
    target_wavelengths:
        List of target wavelength floats.
    filepath:
        Destination PDF file path.
    step4_results:
        Optional analysis results dict from Step4Widget (must contain
        ``"ranking_df"`` key).
    ranking_fig:
        Optional pre-rendered Ranking Chart Figure (used when
        *step4_results* is provided).

    Returns
    -------
    Path
        The path of the written PDF.

    Raises
    ------
    ImportError
        If ``reportlab`` is not installed.
    OSError
        If the file cannot be written.
    Exception
        Any other rendering exception is re-raised after cleanup.
    """
    # --- Guard: reportlab must be available -----------------------------------
    try:
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            Image as RLImage,
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors as rl_colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
    except ImportError:
        raise ImportError("reportlab is not installed. Run: pip install reportlab")

    filepath = Path(filepath)

    try:
        # --- Document setup --------------------------------------------------
        doc = SimpleDocTemplate(
            str(filepath),
            title="LIBS Validation Report",
            author="Spectral Analysis Software",
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()

        # Custom styles
        style_h1 = ParagraphStyle(
            "H1",
            parent=styles["Heading1"],
            fontSize=20,
            spaceAfter=6,
            alignment=TA_CENTER,
        )
        style_h2 = ParagraphStyle(
            "H2",
            parent=styles["Heading2"],
            fontSize=14,
            spaceAfter=4,
            spaceBefore=12,
        )
        style_normal = styles["Normal"]
        style_center = ParagraphStyle(
            "Center",
            parent=style_normal,
            alignment=TA_CENTER,
        )

        # Table style helper
        def _base_table_style() -> TableStyle:
            return TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#0F1117")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), rl_colors.white),
                ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",   (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("BACKGROUND", (0, 1), (-1, -1), rl_colors.HexColor("#222536")),
                ("TEXTCOLOR",  (0, 1), (-1, -1), rl_colors.HexColor("#E8EAF0")),
                ("FONTSIZE",   (0, 1), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [rl_colors.HexColor("#222536"), rl_colors.HexColor("#1A1D27")]),
                ("GRID",       (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#3A3D52")),
                ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING",  (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING",   (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ])

        flowables = []

        # ------------------------------------------------------------------ #
        # 1. Cover page                                                        #
        # ------------------------------------------------------------------ #
        flowables.append(Spacer(1, 1 * cm))
        flowables.append(Paragraph("Spectral Analysis Software", style_h1))
        flowables.append(Paragraph("LIBS Validation Report", style_center))
        flowables.append(Spacer(1, 0.5 * cm))

        now_str = datetime.now().isoformat(timespec="seconds")
        flowables.append(Paragraph(f"Generated: {now_str}", style_center))
        flowables.append(Spacer(1, 0.3 * cm))
        flowables.append(
            Paragraph(f"Processed file: {processed_filename}", style_normal)
        )
        flowables.append(
            Paragraph(f"Reference file: {reference_filename}", style_normal)
        )
        flowables.append(Spacer(1, 0.8 * cm))

        # ------------------------------------------------------------------ #
        # 2. Parameters section                                                #
        # ------------------------------------------------------------------ #
        flowables.append(Paragraph("Analysis Parameters", style_h2))

        param_data = [
            ["Parameter", "Value"],
            ["Window (nm)", str(params.get("WINDOW", "—"))],
            ["Minimum Points", str(params.get("MIN_POINTS", "—"))],
            ["VC Threshold", str(params.get("VC_THRESHOLD", "—"))],
        ]
        param_table = Table(param_data, colWidths=[8 * cm, 8 * cm])
        param_table.setStyle(_base_table_style())
        flowables.append(param_table)
        flowables.append(Spacer(1, 0.5 * cm))

        # ------------------------------------------------------------------ #
        # 3. Summary section                                                   #
        # ------------------------------------------------------------------ #
        flowables.append(Paragraph("Results Summary", style_h2))

        total_validated = len(validation_results_df)
        tier_counts = {"Excellent": 0, "Good": 0, "Moderate": 0, "Weak": 0, "Failed": 0}
        vc_values_for_avg = []

        for _, row in validation_results_df.iterrows():
            vc_val = row.get("Validation_Coefficient") if not validation_results_df.empty else None
            tier_label, _bg, _fg = ChartEngine.classify_vc(vc_val)
            tier_counts[tier_label] = tier_counts.get(tier_label, 0) + 1
            if vc_val is not None:
                try:
                    import math
                    if not math.isnan(float(vc_val)):
                        vc_values_for_avg.append(float(vc_val))
                except (TypeError, ValueError):
                    pass

        avg_vc = (
            f"{sum(vc_values_for_avg) / len(vc_values_for_avg):.4f}"
            if vc_values_for_avg
            else "N/A"
        )

        summary_data = [
            ["Metric", "Value"],
            ["Total Wavelengths Validated", str(total_validated)],
            ["Excellent (VC > 0.95)", str(tier_counts.get("Excellent", 0))],
            ["Good (0.85 ≤ VC ≤ 0.95)", str(tier_counts.get("Good", 0))],
            ["Moderate (0.70 ≤ VC < 0.85)", str(tier_counts.get("Moderate", 0))],
            ["Weak (VC < 0.70)", str(tier_counts.get("Weak", 0))],
            ["Failed / N/A", str(tier_counts.get("Failed", 0))],
            ["Average VC", avg_vc],
        ]
        summary_table = Table(summary_data, colWidths=[10 * cm, 6 * cm])
        summary_table.setStyle(_base_table_style())
        flowables.append(summary_table)
        flowables.append(Spacer(1, 0.5 * cm))

        # ------------------------------------------------------------------ #
        # 4. Detailed results table                                            #
        # ------------------------------------------------------------------ #
        flowables.append(Paragraph("Detailed Results", style_h2))

        if validation_results_df.empty:
            flowables.append(Paragraph("No results available", style_normal))
        else:
            results_header = [
                "Wavelength (nm)",
                "Validation Coefficient",
                "Status",
                "Quality Tier",
            ]
            results_rows = [results_header]
            for _, row in validation_results_df.iterrows():
                wl = row.get("Wavelength_nm", "")
                vc_val = row.get("Validation_Coefficient")
                status = row.get("Status", "")
                tier_label, _bg, _fg = ChartEngine.classify_vc(vc_val)

                vc_str = f"{float(vc_val):.4f}" if vc_val is not None else "—"
                try:
                    import math
                    if math.isnan(float(vc_val)):
                        vc_str = "—"
                except (TypeError, ValueError):
                    pass

                results_rows.append([
                    str(wl),
                    vc_str,
                    str(status),
                    tier_label,
                ])

            col_widths = [4 * cm, 5 * cm, 4 * cm, 4 * cm]
            results_table = Table(results_rows, colWidths=col_widths)
            results_table.setStyle(_base_table_style())
            flowables.append(results_table)

        flowables.append(Spacer(1, 0.5 * cm))

        # ------------------------------------------------------------------ #
        # 5. VC Histogram image                                                #
        # ------------------------------------------------------------------ #
        flowables.append(Paragraph("Validation Coefficient Distribution", style_h2))

        vc_buf = _figure_to_image_buffer(vc_fig)
        vc_image = RLImage(vc_buf, width=14 * cm, height=6 * cm)
        flowables.append(vc_image)
        flowables.append(Spacer(1, 0.5 * cm))

        # ------------------------------------------------------------------ #
        # 6. Selected wavelengths list                                          #
        # ------------------------------------------------------------------ #
        flowables.append(Paragraph("Target Wavelengths", style_h2))

        if target_wavelengths:
            wl_text = ", ".join(
                f"{float(w):.2f}" for w in target_wavelengths
            )
            flowables.append(Paragraph(wl_text, style_normal))
        else:
            flowables.append(Paragraph("No target wavelengths specified.", style_normal))

        flowables.append(Spacer(1, 0.5 * cm))

        # ------------------------------------------------------------------ #
        # 7. Optional Step 4 summary                                           #
        # ------------------------------------------------------------------ #
        if step4_results is not None:
            flowables.append(Paragraph("Step 4 — Elemental Preferences Summary", style_h2))

            ranking_df: pd.DataFrame | None = step4_results.get("ranking_df")
            if ranking_df is not None and not ranking_df.empty:
                top5 = ranking_df.sort_values(
                    by=["Wins", "Total_Score"], ascending=[False, False]
                ).head(5)

                top5_header = ["Rank", "Element", "Wins", "Total Score", "Avg Score"]
                top5_rows = [top5_header]
                for rank, (_, row) in enumerate(top5.iterrows(), start=1):
                    top5_rows.append([
                        str(rank),
                        str(row.get("Element", "")),
                        str(int(row.get("Wins", 0))),
                        f"{float(row.get('Total_Score', 0)):.4f}",
                        f"{float(row.get('Avg_Score', 0)):.4f}",
                    ])

                top5_col_widths = [2 * cm, 4 * cm, 3 * cm, 4 * cm, 4 * cm]
                top5_table = Table(top5_rows, colWidths=top5_col_widths)
                top5_table.setStyle(_base_table_style())
                flowables.append(top5_table)
                flowables.append(Spacer(1, 0.4 * cm))
            else:
                flowables.append(Paragraph("No ranking data available.", style_normal))
                flowables.append(Spacer(1, 0.4 * cm))

            if ranking_fig is not None:
                ranking_buf = _figure_to_image_buffer(ranking_fig)
                ranking_image = RLImage(ranking_buf, width=14 * cm, height=6 * cm)
                flowables.append(ranking_image)

        # ------------------------------------------------------------------ #
        # Build PDF                                                            #
        # ------------------------------------------------------------------ #
        doc.build(flowables)

    except Exception:
        filepath.unlink(missing_ok=True)
        raise

    return filepath
