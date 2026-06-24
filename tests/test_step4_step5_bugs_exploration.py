# -*- coding: utf-8 -*-
"""
Bug Condition Exploration Tests — Step 4 / Step 5

These tests encode the EXPECTED (fixed) behavior.
On UNFIXED code they MUST FAIL — failure confirms each bug exists.
When they PASS, all four bugs have been fixed.

Property 1: Bug Condition — NameError and AttributeError on Four Buggy Paths
Validates: Requirements 1.1, 1.2, 1.3, 1.4
"""

import ast
import inspect
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ranking_df():
    return pd.DataFrame({
        'Element': ['Ca', 'Fe'],
        'Wins': [5, 3],
        'Total_Score': [12.5, 8.0],
        'Avg_Score': [0.92, 0.75],
    })


def _make_competition_df():
    return pd.DataFrame({
        'Matched_WL': [300.0, 400.0],
        'Winner': ['Ca', 'Fe'],
        'Max_Score': [0.95, 0.80],
        'Num_Competitors': [2, 3],
    })


def _make_winner_lines_df():
    return pd.DataFrame({
        'Winning_Element': ['Ca'],
        'Observed_Wavelength': [300.1],
        'NIST_Matched_Wavelength': [300.0],
        'Confidence_Score': [0.95],
        'Num_Competitors': [2],
    })


def _make_spectra_csv(tmp_path: Path, name: str) -> Path:
    """Write a minimal 2-column CSV resembling a processed spectrum."""
    p = tmp_path / name
    df = pd.DataFrame({
        'wavelength (nm)': np.linspace(200, 800, 50),
        'intensity': np.random.rand(50) * 1000,
    })
    df.to_csv(p, index=False)
    return p


def _make_wavelengths_csv(tmp_path: Path) -> Path:
    """Write a minimal wavelength CSV (first column = wavelengths)."""
    p = tmp_path / "wavelengths.csv"
    df = pd.DataFrame({'wavelength_nm': [300.0, 400.0, 500.0]})
    df.to_csv(p, index=False)
    return p


# ---------------------------------------------------------------------------
# Test 1.a — Bug 1: Dead CSVWriter instantiation in step4_widget._on_save_clicked
# ---------------------------------------------------------------------------

class TestBug1SaveResultsStep4:
    """
    **Validates: Requirements 1.1**

    On unfixed code: _on_save_clicked() raises NameError because CSVWriter is
    not imported in step4_widget.py.
    Expected (fixed) behavior: method completes without raising any exception
    and saves three CSV files.
    """

    def test_on_save_clicked_does_not_raise(self, app, tmp_path):
        """
        Call Step4Widget._on_save_clicked() with mocked analysis_results and
        a mocked QFileDialog.  On UNFIXED code this FAILS with NameError.
        On FIXED code it passes cleanly.
        """
        from src.gui.step4_widget import Step4Widget

        widget = Step4Widget()

        # Provide mock analysis results
        widget.analysis_results = {
            'ranking': _make_ranking_df(),
            'competition': _make_competition_df(),
            'winner_lines': _make_winner_lines_df(),
        }

        save_path = str(tmp_path / "results")

        with patch(
            'src.gui.step4_widget.QFileDialog.getSaveFileName',
            return_value=(save_path, 'CSV Files (*.csv)'),
        ):
            # On unfixed code: NameError — name 'CSVWriter' is not defined
            # On fixed code: should complete without exception
            widget._on_save_clicked()

        # Verify the three CSV files were actually created (only if no exception)
        assert Path(f"{save_path}_ranking.csv").exists(), (
            "ranking CSV was not written"
        )
        assert Path(f"{save_path}_competition.csv").exists(), (
            "competition CSV was not written"
        )
        assert Path(f"{save_path}_winners.csv").exists(), (
            "winners CSV was not written"
        )


# ---------------------------------------------------------------------------
# Test 1.b — Bug 2: read_generic_csv in step5_widget._on_load_wavelengths
# ---------------------------------------------------------------------------

class TestBug2LoadWavelengthsCSVStep5:
    """
    **Validates: Requirements 1.2**

    On unfixed code: _on_load_wavelengths() with a CSV file raises
    AttributeError: 'CSVReader' object has no attribute 'read_generic_csv'.
    Expected (fixed) behavior: wavelengths are read from the CSV first column
    and stored in self.target_wavelengths.
    """

    def test_load_wavelengths_csv_does_not_raise(self, app, tmp_path):
        """
        Mock QFileDialog to return a temp CSV path and call _on_load_wavelengths().
        On UNFIXED code this FAILS with AttributeError.
        On FIXED code it passes and populates target_wavelengths.
        """
        from src.gui.step5_widget import Step5Widget

        widget = Step5Widget()

        wl_csv = _make_wavelengths_csv(tmp_path)

        with patch(
            'src.gui.step5_widget.QFileDialog.getOpenFileName',
            return_value=(str(wl_csv), 'CSV Files (*.csv)'),
        ):
            # On unfixed code: AttributeError — 'CSVReader' has no attribute 'read_generic_csv'
            # On fixed code: should complete without exception
            widget._on_load_wavelengths()

        # Verify wavelengths were loaded
        assert hasattr(widget, 'target_wavelengths'), (
            "target_wavelengths was not set"
        )
        assert len(widget.target_wavelengths) == 3, (
            f"Expected 3 wavelengths, got {len(widget.target_wavelengths)}"
        )
        assert widget.target_wavelengths == pytest.approx([300.0, 400.0, 500.0]), (
            "Loaded wavelengths do not match expected values"
        )


# ---------------------------------------------------------------------------
# Test 1.c — Bug 3: read_generic_csv in step5_widget._validate_worker
# ---------------------------------------------------------------------------

class TestBug3ValidateWorkerStep5:
    """
    **Validates: Requirements 1.3**

    On unfixed code: _validate_worker() raises
    AttributeError: 'CSVReader' object has no attribute 'read_generic_csv'
    when trying to load the processed and reference spectra.
    Expected (fixed) behavior: worker loads both DataFrames via pd.read_csv()
    and calls ValidationAnalyzer.validate_spectrum() without error.
    """

    def test_validate_worker_does_not_raise(self, app, tmp_path):
        """
        Set up Step5Widget with valid file paths and target_wavelengths,
        then call _validate_worker() directly.
        On UNFIXED code this FAILS with AttributeError.
        On FIXED code it passes and populates self.validation_results.
        """
        from src.gui.step5_widget import Step5Widget

        widget = Step5Widget()

        processed_csv = _make_spectra_csv(tmp_path, "processed.csv")
        reference_csv = _make_spectra_csv(tmp_path, "reference.csv")

        # Mock the file selectors
        widget.processed_selector = MagicMock()
        widget.processed_selector.get_filepath.return_value = processed_csv

        widget.reference_selector = MagicMock()
        widget.reference_selector.get_filepath.return_value = reference_csv

        # Set target wavelengths
        widget.target_wavelengths = [300.0, 400.0]

        # Mock spinboxes so they return valid numeric values
        widget.window_spinbox = MagicMock()
        widget.window_spinbox.value.return_value = 2.0

        widget.min_points_spinbox = MagicMock()
        widget.min_points_spinbox.value.return_value = 3

        widget.threshold_spinbox = MagicMock()
        widget.threshold_spinbox.value.return_value = 0.7

        # On unfixed code: AttributeError — 'CSVReader' has no attribute 'read_generic_csv'
        # On fixed code: should return (True, "Validation completed successfully")
        result = widget._validate_worker()

        success, message = result
        assert success is True, (
            f"_validate_worker() failed: {message}"
        )
        assert widget.validation_results is not None, (
            "validation_results was not populated"
        )


# ---------------------------------------------------------------------------
# Test 1.d — Bug 4: import pandas as pd at module bottom in step5_widget.py
# ---------------------------------------------------------------------------

class TestBug4PandasImportPosition:
    """
    **Validates: Requirements 1.4**

    On unfixed code: 'import pandas as pd' is placed at the BOTTOM of
    step5_widget.py (after the class definition), which is fragile and
    violates PEP 8. The test checks that the import appears in the
    module-level top-of-file import block.
    Expected (fixed) behavior: 'import pandas as pd' is at the top of
    the file, before the class definition.
    """

    def test_pandas_import_is_at_module_top(self):
        """
        Parse step5_widget.py source and assert 'import pandas as pd'
        appears before any class definition.
        On UNFIXED code this FAILS because the import is after the class.
        On FIXED code it passes.
        """
        import src.gui.step5_widget as step5_module

        source_file = Path(inspect.getfile(step5_module))
        source = source_file.read_text(encoding='utf-8')

        tree = ast.parse(source)

        # Find line numbers of 'import pandas as pd' and 'class Step5Widget'
        pandas_import_lineno = None
        class_def_lineno = None

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == 'pandas' and alias.asname == 'pd':
                        pandas_import_lineno = node.lineno
            if isinstance(node, ast.ClassDef) and node.name == 'Step5Widget':
                class_def_lineno = node.lineno

        assert pandas_import_lineno is not None, (
            "'import pandas as pd' not found anywhere in step5_widget.py"
        )
        assert class_def_lineno is not None, (
            "'class Step5Widget' not found in step5_widget.py"
        )

        # The import must appear BEFORE the class definition
        assert pandas_import_lineno < class_def_lineno, (
            f"'import pandas as pd' is at line {pandas_import_lineno}, "
            f"but 'class Step5Widget' starts at line {class_def_lineno}. "
            f"The import must be moved above the class definition."
        )
