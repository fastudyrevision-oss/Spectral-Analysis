# tests/test_export_step6.py
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pytest
from pathlib import Path

from src.gui.export_engine import export_step6_csv, export_step6_png


def _make_results():
    return {
        "element_rows": [
            {
                "element": "Ca",
                "confidence_tier": "High",
                "matched_lines": 12,
                "mean_vc": 0.85,
                "avg_delta": 0.0023,
                "avg_score": 1.5e-4,
                "best_lines": [393.37, 396.85, 422.67],
            },
        ],
        "pipeline_stages": {
            "stage1_detected": 10, "stage2_nist_matched": 8,
            "stage3_ranked": 6, "stage4_validated": 5, "stage5_confirmed": 4,
        },
        "accuracy": 0.8, "precision": 0.75, "recall": 0.9,
        "f1_score": 0.82, "sbr_improvement": 2.6,
    }


def test_export_step6_csv_creates_file(tmp_path):
    filepath = tmp_path / "step6.csv"
    result = export_step6_csv(_make_results(), filepath)
    assert result == filepath
    assert filepath.exists()
    df = pd.read_csv(filepath)
    assert "Element" in df.columns
    assert "Confidence_Tier" in df.columns
    assert len(df) == 1
    assert df.iloc[0]["Element"] == "Ca"


def test_export_step6_csv_correct_columns(tmp_path):
    filepath = tmp_path / "step6.csv"
    export_step6_csv(_make_results(), filepath)
    df = pd.read_csv(filepath)
    # Columns must mirror the GUI summary table exactly, plus global metrics
    expected_cols = [
        "Element", "Confidence_Tier", "Status",
        "Matched_Lines", "Mean_VC", "Avg_Delta_nm", "Avg_Score", "Best_Lines_nm",
        "Accuracy", "Precision", "Recall", "F1_Score", "SBR_Improvement",
    ]
    for col in expected_cols:
        assert col in df.columns, f"Missing column: {col}"
    # Pipeline_Stage_* must NOT appear — they are chart data, not table columns
    for i in range(1, 6):
        assert f"Pipeline_Stage_{i}" not in df.columns, \
            f"Unexpected pipeline column: Pipeline_Stage_{i}"


def test_export_step6_csv_status_derived_correctly(tmp_path):
    """Status column must follow the same tier→status mapping as the GUI."""
    results = {
        "element_rows": [
            {"element": "Ca", "confidence_tier": "High",   "matched_lines": 5,
             "mean_vc": 0.9, "avg_delta": 0.001, "avg_score": 1e-4, "best_lines": []},
            {"element": "Fe", "confidence_tier": "Medium", "matched_lines": 3,
             "mean_vc": 0.6, "avg_delta": 0.05,  "avg_score": 5e-5, "best_lines": []},
            {"element": "Pb", "confidence_tier": "Low",    "matched_lines": 1,
             "mean_vc": 0.2, "avg_delta": 0.2,   "avg_score": 1e-5, "best_lines": []},
        ],
        "accuracy": None, "precision": None, "recall": None,
        "f1_score": None, "sbr_improvement": None,
    }
    filepath = tmp_path / "status.csv"
    export_step6_csv(results, filepath)
    df = pd.read_csv(filepath)
    assert df.loc[df["Element"] == "Ca",  "Status"].iloc[0] == "Confirmed"
    assert df.loc[df["Element"] == "Fe",  "Status"].iloc[0] == "Probable"
    assert df.loc[df["Element"] == "Pb",  "Status"].iloc[0] == "Uncertain"


def test_export_step6_csv_best_lines_formatted(tmp_path):
    """Best_Lines_nm must be a comma-separated string of wavelengths."""
    filepath = tmp_path / "best.csv"
    export_step6_csv(_make_results(), filepath)
    df = pd.read_csv(filepath)
    best = df.iloc[0]["Best_Lines_nm"]
    assert "393.37" in str(best)
    assert "396.85" in str(best)


def test_export_step6_png_creates_file(tmp_path):
    figs = [plt.figure() for _ in range(4)]
    filepath = tmp_path / "step6.png"
    result = export_step6_png(figs, filepath, dpi=72)
    assert result == filepath
    assert filepath.exists()
    assert filepath.stat().st_size > 0
    for fig in figs:
        plt.close(fig)


def test_export_step6_png_restores_facecolor(tmp_path):
    from src.gui.theme import C_BG_DEEP
    figs = [plt.figure() for _ in range(2)]
    original_fcs = [fig.get_facecolor() for fig in figs]
    filepath = tmp_path / "step6.png"
    export_step6_png(figs, filepath, dpi=72)
    for fig, orig_fc in zip(figs, original_fcs):
        assert fig.get_facecolor() == orig_fc
    for fig in figs:
        plt.close(fig)
