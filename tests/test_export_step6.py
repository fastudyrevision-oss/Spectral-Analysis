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
            {"element": "Ca", "confidence_tier": "High", "matched_lines": 12, "mean_vc": 0.85},
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
    expected_cols = [
        "Element", "Confidence_Tier", "Matched_Lines", "Mean_VC",
        "Accuracy", "Precision", "Recall", "F1_Score", "SBR_Improvement",
        "Pipeline_Stage_1", "Pipeline_Stage_2", "Pipeline_Stage_3",
        "Pipeline_Stage_4", "Pipeline_Stage_5",
    ]
    for col in expected_cols:
        assert col in df.columns, f"Missing column: {col}"


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
