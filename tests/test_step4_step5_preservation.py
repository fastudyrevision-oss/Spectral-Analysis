# -*- coding: utf-8 -*-
"""
Preservation Property Tests — Step 4 / Step 5

These tests cover non-buggy execution paths that MUST PASS on the unfixed code
and MUST CONTINUE TO PASS after the fix is applied, confirming no regressions.

Property 2: Preservation — Non-Buggy Paths Unchanged
Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from hypothesis.extra.pandas import column, data_frames, range_indexes


# ===========================================================================
# Helpers / Generators
# ===========================================================================

def _make_matching_df(observed_wls, elements, scores):
    """Build a minimal NIST-matching CSV DataFrame."""
    return pd.DataFrame({
        'Observed_WL': observed_wls,
        'Matched_WL': observed_wls,  # identical for simplicity
        'Score': scores,
        'Element': elements,
    })


def _write_matching_csv(tmp_path: Path, df: pd.DataFrame) -> Path:
    p = tmp_path / "matching.csv"
    df.to_csv(p, index=False)
    return p


# ===========================================================================
# 1. Step 4 analysis preservation
#    _analyze_worker with a valid matching CSV produces a dict with the
#    required keys.  Tested with multiple generated DataFrames.
#
#    Validates: Requirements 3.1
# ===========================================================================

class TestStep4AnalysisPreservation:
    """
    **Validates: Requirements 3.1**

    Step 4 elemental-preferences analysis (file loading, analyzer.analyze(),
    and result structure) must continue to work correctly.
    These tests never touch _on_save_clicked, so Bug 1 is never triggered.
    """

    # -- concrete baseline --------------------------------------------------

    def test_analyze_worker_returns_required_keys(self, app, tmp_path):
        """
        _analyze_worker() with a valid matching CSV returns a dict that
        contains all five required keys.
        """
        from src.gui.step4_widget import Step4Widget

        df = _make_matching_df(
            observed_wls=[300.0, 400.0, 500.0, 300.0, 400.0],
            elements=['Ca', 'Ca', 'Ca', 'Fe', 'Fe'],
            scores=[0.9, 0.8, 0.7, 0.5, 0.6],
        )
        csv_path = _write_matching_csv(tmp_path, df)

        widget = Step4Widget()
        widget.matching_files = [str(csv_path)]
        widget.notes_panel = None

        result = widget._analyze_worker()
        success, message = result

        assert success is True, f"_analyze_worker failed: {message}"
        assert widget.analysis_results is not None

        for key in ('ranking', 'competition', 'winner_lines',
                    'primary_element', 'combined_data'):
            assert key in widget.analysis_results, (
                f"Missing key '{key}' in analysis_results"
            )

    def test_analyze_worker_primary_element_is_string(self, app, tmp_path):
        """primary_element must be a non-empty string."""
        from src.gui.step4_widget import Step4Widget

        df = _make_matching_df(
            observed_wls=[300.0, 350.0, 400.0],
            elements=['Ca', 'Fe', 'Ca'],
            scores=[0.9, 0.7, 0.8],
        )
        csv_path = _write_matching_csv(tmp_path, df)

        widget = Step4Widget()
        widget.matching_files = [str(csv_path)]
        widget.notes_panel = None

        success, _ = widget._analyze_worker()
        assert success is True
        pe = widget.analysis_results['primary_element']
        assert isinstance(pe, str) and pe != '', (
            "primary_element must be a non-empty string"
        )

    # -- property-based: varied DataFrames ----------------------------------

    # Hypothesis strategy: generate varied matching DataFrames
    _wl_st = st.floats(min_value=200.0, max_value=800.0,
                       allow_nan=False, allow_infinity=False)
    _score_st = st.floats(min_value=0.01, max_value=1.0,
                          allow_nan=False, allow_infinity=False)
    _element_st = st.sampled_from(['Ca', 'Fe', 'Mg', 'Al', 'Si'])

    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    @given(
        wls=st.lists(_wl_st, min_size=4, max_size=20).map(
            lambda xs: [round(x, 2) for x in xs]
        ),
        elements=st.lists(_element_st, min_size=4, max_size=20),
        scores=st.lists(_score_st, min_size=4, max_size=20),
    )
    def test_analyze_worker_preserves_result_structure(
        self, app, tmp_path, wls, elements, scores
    ):
        """
        **Validates: Requirements 3.1**

        For any valid matching DataFrame, _analyze_worker must return success
        and produce a dict containing all five required keys.
        """
        from src.gui.step4_widget import Step4Widget

        # Align all three lists to the shortest length
        n = min(len(wls), len(elements), len(scores))
        wls, elements, scores = wls[:n], elements[:n], scores[:n]

        df = _make_matching_df(wls, elements, scores)
        csv_path = _write_matching_csv(tmp_path, df)

        widget = Step4Widget()
        widget.matching_files = [str(csv_path)]
        widget.notes_panel = None

        success, message = widget._analyze_worker()

        assert success is True, f"_analyze_worker failed: {message}"
        for key in ('ranking', 'competition', 'winner_lines',
                    'primary_element', 'combined_data'):
            assert key in widget.analysis_results, (
                f"Missing key '{key}' with input of {n} rows"
            )


# ===========================================================================
# 2. Step 5 manual wavelength entry preservation
#    Patching QInputDialog.getMultiLineText; asserting target_wavelengths.
#
#    Validates: Requirements 3.3
# ===========================================================================

class TestStep5ManualWavelengthPreservation:
    """
    **Validates: Requirements 3.3**

    Manual wavelength entry via QInputDialog must continue to parse and store
    wavelengths correctly — this path never touches any buggy code.
    """

    def test_manual_wavelengths_basic(self, app):
        """
        Patching QInputDialog.getMultiLineText to return '300.0\\n400.0\\n500.0'
        results in target_wavelengths == [300.0, 400.0, 500.0].
        """
        from src.gui.step5_widget import Step5Widget

        widget = Step5Widget()

        # QInputDialog is imported locally inside the method; patch at source.
        with patch(
            'PyQt6.QtWidgets.QInputDialog.getMultiLineText',
            return_value=('300.0\n400.0\n500.0', True),
        ):
            widget._on_manual_wavelengths()

        assert hasattr(widget, 'target_wavelengths'), (
            "target_wavelengths was not set after manual entry"
        )
        assert widget.target_wavelengths == pytest.approx([300.0, 400.0, 500.0])

    def test_manual_wavelengths_single_value(self, app):
        """A single wavelength entry produces a one-element list."""
        from src.gui.step5_widget import Step5Widget

        widget = Step5Widget()

        with patch(
            'PyQt6.QtWidgets.QInputDialog.getMultiLineText',
            return_value=('650.1', True),
        ):
            widget._on_manual_wavelengths()

        assert widget.target_wavelengths == pytest.approx([650.1])

    def test_manual_wavelengths_cancelled_leaves_list_unchanged(self, app):
        """Cancelling the dialog (ok=False) must not change target_wavelengths."""
        from src.gui.step5_widget import Step5Widget

        widget = Step5Widget()
        # Pre-set a list so we can verify it is not modified
        widget.target_wavelengths = [100.0, 200.0]

        with patch(
            'PyQt6.QtWidgets.QInputDialog.getMultiLineText',
            return_value=('999.0', False),  # ok = False
        ):
            widget._on_manual_wavelengths()

        assert widget.target_wavelengths == pytest.approx([100.0, 200.0])

    @settings(
        max_examples=15,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    @given(
        wls=st.lists(
            st.floats(min_value=200.0, max_value=900.0,
                      allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=10,
        )
    )
    def test_manual_wavelengths_roundtrip(self, app, wls):
        """
        **Validates: Requirements 3.3**

        For any list of valid floats, entering them as '\\n'-joined text must
        produce the same list back in target_wavelengths.
        """
        from src.gui.step5_widget import Step5Widget

        widget = Step5Widget()
        text = '\n'.join(str(w) for w in wls)

        with patch(
            'PyQt6.QtWidgets.QInputDialog.getMultiLineText',
            return_value=(text, True),
        ):
            widget._on_manual_wavelengths()

        assert len(widget.target_wavelengths) == len(wls)
        for expected, actual in zip(wls, widget.target_wavelengths):
            assert actual == pytest.approx(expected, rel=1e-6)


# ===========================================================================
# 3. Step 5 .txt file wavelength loading preservation
#    The txt branch of _on_load_wavelengths must work on unfixed code.
#
#    Validates: Requirements 3.2
# ===========================================================================

class TestStep5TxtFileWavelengthPreservation:
    """
    **Validates: Requirements 3.2**

    Loading wavelengths from a plain-text .txt file must continue to work.
    The .txt branch does NOT call CSVReader, so it is not affected by Bug 2.
    """

    def test_load_txt_wavelengths_basic(self, app, tmp_path):
        """
        Create a temp .txt file with '300.0\\n400.0\\n500.0',
        patch QFileDialog to return it, call _on_load_wavelengths().
        Assert correct wavelengths loaded.
        """
        from src.gui.step5_widget import Step5Widget

        widget = Step5Widget()

        txt_path = tmp_path / "wavelengths.txt"
        txt_path.write_text("300.0\n400.0\n500.0\n")

        with patch(
            'src.gui.step5_widget.QFileDialog.getOpenFileName',
            return_value=(str(txt_path), 'Text Files (*.txt)'),
        ):
            widget._on_load_wavelengths()

        assert hasattr(widget, 'target_wavelengths'), (
            "target_wavelengths was not set"
        )
        assert widget.target_wavelengths == pytest.approx([300.0, 400.0, 500.0])

    def test_load_txt_wavelengths_with_blank_lines(self, app, tmp_path):
        """Blank lines in the .txt file are ignored."""
        from src.gui.step5_widget import Step5Widget

        widget = Step5Widget()

        txt_path = tmp_path / "wavelengths.txt"
        txt_path.write_text("250.0\n\n350.0\n\n450.0\n")

        with patch(
            'src.gui.step5_widget.QFileDialog.getOpenFileName',
            return_value=(str(txt_path), 'Text Files (*.txt)'),
        ):
            widget._on_load_wavelengths()

        assert widget.target_wavelengths == pytest.approx([250.0, 350.0, 450.0])

    @settings(
        max_examples=15,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    @given(
        wls=st.lists(
            st.floats(min_value=200.0, max_value=900.0,
                      allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=15,
        )
    )
    def test_load_txt_wavelengths_roundtrip(self, app, tmp_path, wls):
        """
        **Validates: Requirements 3.2**

        For any list of valid floats written to a .txt file,
        _on_load_wavelengths() must recover the same list.
        """
        from src.gui.step5_widget import Step5Widget

        widget = Step5Widget()

        txt_path = tmp_path / "wl_roundtrip.txt"
        txt_path.write_text('\n'.join(str(w) for w in wls) + '\n')

        with patch(
            'src.gui.step5_widget.QFileDialog.getOpenFileName',
            return_value=(str(txt_path), 'Text Files (*.txt)'),
        ):
            widget._on_load_wavelengths()

        assert len(widget.target_wavelengths) == len(wls)
        for expected, actual in zip(wls, widget.target_wavelengths):
            assert actual == pytest.approx(expected, rel=1e-6)


# ===========================================================================
# 4. Step 5 results table population preservation
#    _populate_results_table with a mock validation_results DataFrame.
#
#    Validates: Requirements 3.4
# ===========================================================================

class TestStep5ResultsTablePreservation:
    """
    **Validates: Requirements 3.4**

    _populate_results_table() must correctly fill the results_table widget
    with row count and cell values matching validation_results.

    NOTE: On UNFIXED code, pd.isna() in _populate_results_table may raise
    NameError (Bug 4) if pd is not yet available.  However, because the
    module-level 'import pandas as pd' is at the bottom of the file,
    and by the time these tests run the whole module has been imported,
    pd IS available in practice.  So this test passes on unfixed code too.
    """

    def _make_validation_df(self, rows):
        """Build a minimal validation_results DataFrame."""
        return pd.DataFrame({
            'Wavelength_nm': [float(r['wl']) for r in rows],
            'Validation_Coefficient': [r['vc'] for r in rows],
            'Status': [r['status'] for r in rows],
        })

    def test_populate_results_table_basic(self, app):
        """
        Set widget.validation_results to a 3-row DataFrame,
        call _populate_results_table(), assert row count == 3 and
        a sample cell value is correct.
        """
        from src.gui.step5_widget import Step5Widget

        widget = Step5Widget()

        rows = [
            {'wl': 300.0, 'vc': 0.95, 'status': 'Success'},
            {'wl': 400.0, 'vc': 0.72, 'status': 'Success'},
            {'wl': 500.0, 'vc': float('nan'), 'status': 'Failed: insufficient data'},
        ]
        widget.validation_results = self._make_validation_df(rows)

        widget._populate_results_table()

        assert widget.results_table.rowCount() == 3, (
            "Row count must equal number of validation results"
        )
        # Check wavelength column (col 0) for first row
        item = widget.results_table.item(0, 0)
        assert item is not None
        assert float(item.text()) == pytest.approx(300.0, abs=0.01)

    def test_populate_results_table_nan_vc_shows_na(self, app):
        """NaN validation coefficient must be displayed as 'N/A'."""
        from src.gui.step5_widget import Step5Widget

        widget = Step5Widget()

        widget.validation_results = self._make_validation_df([
            {'wl': 450.0, 'vc': float('nan'), 'status': 'Failed: something'},
        ])

        widget._populate_results_table()

        vc_item = widget.results_table.item(0, 1)
        assert vc_item is not None
        assert vc_item.text() == 'N/A', (
            f"Expected 'N/A' for NaN VC, got '{vc_item.text()}'"
        )

    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    @given(
        rows=st.lists(
            st.fixed_dictionaries({
                'wl': st.floats(200.0, 900.0, allow_nan=False,
                                allow_infinity=False),
                'vc': st.one_of(
                    st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False),
                    st.just(float('nan')),
                ),
                'status': st.sampled_from(['Success', 'Failed: region too small']),
            }),
            min_size=1,
            max_size=20,
        )
    )
    def test_populate_results_table_row_count_matches(self, app, rows):
        """
        **Validates: Requirements 3.4**

        For any valid validation_results DataFrame, _populate_results_table()
        must set the table row count to len(validation_results).
        """
        from src.gui.step5_widget import Step5Widget

        widget = Step5Widget()
        widget.validation_results = self._make_validation_df(rows)

        widget._populate_results_table()

        assert widget.results_table.rowCount() == len(rows), (
            f"Expected {len(rows)} rows, got {widget.results_table.rowCount()}"
        )


# ===========================================================================
# 5. Step 5 save report preservation
#    _on_save_clicked (Step 5) writes validation_results to CSV.
#    This path uses self.validation_results.to_csv() — no buggy code.
#
#    Validates: Requirements 3.5
# ===========================================================================

class TestStep5SaveReportPreservation:
    """
    **Validates: Requirements 3.5**

    Step 5 "Save Report" must write validation_results to CSV correctly.
    This path uses self.validation_results.to_csv() and is completely
    separate from the buggy Step 4 _on_save_clicked.
    """

    def _make_validation_df(self):
        return pd.DataFrame({
            'Wavelength_nm': [300.0, 400.0, 500.0],
            'Validation_Coefficient': [0.95, 0.80, float('nan')],
            'Status': ['Success', 'Success', 'Failed: insufficient data'],
        })

    def test_save_report_creates_file(self, app, tmp_path):
        """
        Mocking QFileDialog.getSaveFileName to return a temp path,
        call _on_save_clicked(). Assert file exists.
        """
        from src.gui.step5_widget import Step5Widget

        widget = Step5Widget()
        widget.validation_results = self._make_validation_df()

        save_path = str(tmp_path / "report.csv")

        with patch(
            'src.gui.step5_widget.QFileDialog.getSaveFileName',
            return_value=(save_path, 'CSV Files (*.csv)'),
        ):
            widget._on_save_clicked()

        assert Path(save_path).exists(), (
            "Save report did not create the output file"
        )

    def test_save_report_content_matches_dataframe(self, app, tmp_path):
        """
        The saved CSV must be identical (round-trip) to validation_results.
        """
        from src.gui.step5_widget import Step5Widget

        expected_df = self._make_validation_df()

        widget = Step5Widget()
        widget.validation_results = expected_df.copy()

        save_path = str(tmp_path / "report_roundtrip.csv")

        with patch(
            'src.gui.step5_widget.QFileDialog.getSaveFileName',
            return_value=(save_path, 'CSV Files (*.csv)'),
        ):
            widget._on_save_clicked()

        loaded = pd.read_csv(save_path)
        assert list(loaded.columns) == list(expected_df.columns), (
            "Saved CSV columns do not match"
        )
        assert len(loaded) == len(expected_df), (
            "Saved CSV row count does not match"
        )
        # Check non-NaN numeric values
        assert loaded['Wavelength_nm'].tolist() == pytest.approx(
            expected_df['Wavelength_nm'].tolist()
        )
        assert loaded.loc[0, 'Validation_Coefficient'] == pytest.approx(0.95)
        assert loaded.loc[1, 'Validation_Coefficient'] == pytest.approx(0.80)
        assert pd.isna(loaded.loc[2, 'Validation_Coefficient'])

    @settings(
        max_examples=5,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    @given(
        wavelengths=st.lists(
            st.floats(200.0, 900.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=8,
        ),
        vcs=st.lists(
            st.one_of(
                st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False),
                st.just(float('nan')),
            ),
            min_size=1,
            max_size=8,
        ),
    )
    def test_save_report_roundtrip(self, app, tmp_path, wavelengths, vcs):
        """
        **Validates: Requirements 3.5**

        For any valid validation_results DataFrame, the file written by
        _on_save_clicked() must have the same row count as the DataFrame.

        Uses a single pre-created widget instance (set as class attribute by
        a setup method) to avoid Qt widget construction overhead per example.
        """
        # Reuse a single widget instance stored at class level to avoid
        # creating a new Qt widget for every Hypothesis example.
        if not hasattr(TestStep5SaveReportPreservation, '_shared_widget'):
            from src.gui.step5_widget import Step5Widget
            TestStep5SaveReportPreservation._shared_widget = Step5Widget()

        widget = TestStep5SaveReportPreservation._shared_widget

        n = min(len(wavelengths), len(vcs))
        wavelengths, vcs = wavelengths[:n], vcs[:n]

        df = pd.DataFrame({
            'Wavelength_nm': wavelengths,
            'Validation_Coefficient': vcs,
            'Status': ['Success'] * n,
        })

        widget.validation_results = df.copy()

        import uuid
        save_path = str(tmp_path / f"pbt_report_{uuid.uuid4().hex}.csv")

        with patch(
            'src.gui.step5_widget.QFileDialog.getSaveFileName',
            return_value=(save_path, 'CSV Files (*.csv)'),
        ):
            widget._on_save_clicked()

        assert Path(save_path).exists(), "File was not created"
        loaded = pd.read_csv(save_path)
        assert len(loaded) == n, (
            f"Expected {n} rows in saved CSV, got {len(loaded)}"
        )
