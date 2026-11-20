# -*- coding: utf-8 -*-
"""
Tests for Step 5 Element-Aware Multi-File Validation
"""

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtCore import Qt

from src.core.step5_validation import ValidationAnalyzer, extract_element_symbol
from src.gui.step5_widget import Step5Widget


def test_step5_load_from_step4_auto_matching(app):
    """Test auto-handoff of winner lines from Step 4 into Step 5."""
    widget = Step5Widget()

    # Mock Step 4 winner_lines DataFrame
    winners_df = pd.DataFrame({
        'Winning_Element': ['Ca', 'Ca', 'Al', 'Fe'],
        'Observed_Wavelength': [393.37, 422.67, 396.15, 404.58],
        'NIST_Matched_Wavelength': [393.366, 422.673, 396.152, 404.581],
        'Confidence_Score': [5000.0, 4200.0, 3100.0, 1500.0],
        'Num_Competitors': [3, 2, 4, 1],
    })
    analysis_results = {
        'primary_element': 'Ca',
        'winner_lines': winners_df,
    }

    widget.load_from_step4(analysis_results)

    # Verify target wavelengths and grouping
    assert len(widget.target_wavelengths) == 4
    assert widget.target_wavelengths == sorted([393.37, 422.67, 396.15, 404.58])
    assert 'Ca' in widget._step4_element_lines
    assert 'Al' in widget._step4_element_lines
    assert 'Fe' in widget._step4_element_lines
    assert len(widget._step4_element_lines['Ca']) == 2
    assert len(widget._step4_element_lines['Al']) == 1

    # Verify matching items in _ref_file_list are checked
    checked_symbols = set()
    for i in range(widget._ref_file_list.count()):
        item = widget._ref_file_list.item(i)
        if item.checkState() == Qt.CheckState.Checked:
            checked_symbols.add(extract_element_symbol(item.text()))

    # Processed Data folder contains Al.csv, Ca.csv, Fe-Cl2.csv, etc.
    if widget._ref_file_list.count() > 0:
        for expected in ['Ca', 'Al', 'Fe']:
            # If the folder has these files, they should be checked
            available = any(extract_element_symbol(widget._ref_file_list.item(j).text()) == expected 
                            for j in range(widget._ref_file_list.count()))
            if available:
                assert expected in checked_symbols


def test_step5_results_table_columns_and_population(app):
    """Test that Step 5 results table has 6 columns and populates Element, Reference File, and Tier."""
    widget = Step5Widget()

    assert widget.results_table.columnCount() == 6
    headers = [widget.results_table.horizontalHeaderItem(i).text() for i in range(6)]
    assert headers == ["Wavelength (nm)", "Element", "Reference File", "Validation Coefficient", "Tier", "Status"]

    # Populate mock validation results
    df = pd.DataFrame([
        {
            'Wavelength_nm': 396.15,
            'Element': 'Al',
            'Reference_File': 'Al.csv',
            'Validation_Coefficient': 0.9421,
            'Peak_Shift_nm': 0.01,
            'Tier': 'High',
            'Status': 'Success',
        },
        {
            'Wavelength_nm': 422.67,
            'Element': 'Ca',
            'Reference_File': 'Ca.csv',
            'Validation_Coefficient': 0.8123,
            'Peak_Shift_nm': -0.02,
            'Tier': 'High',
            'Status': 'Success',
        },
        {
            'Wavelength_nm': 404.58,
            'Element': 'Fe',
            'Reference_File': 'N/A',
            'Validation_Coefficient': np.nan,
            'Peak_Shift_nm': 0.0,
            'Tier': 'Missing Ref',
            'Status': 'Missing reference spectrum for Fe',
        }
    ])

    widget.validation_results = df
    widget._populate_results_table()

    assert widget.results_table.rowCount() == 3

    # Check row 0 (Al)
    assert widget.results_table.item(0, 0).text() == "396.15"
    assert widget.results_table.item(0, 1).text() == "Al"
    assert widget.results_table.item(0, 2).text() == "Al.csv"
    assert widget.results_table.item(0, 3).text() == "0.9421"
    assert "High" in widget.results_table.item(0, 4).text()
    assert widget.results_table.item(0, 5).text() == "Success"

    # Check row 2 (Fe missing ref)
    assert widget.results_table.item(2, 0).text() == "404.58"
    assert widget.results_table.item(2, 1).text() == "Fe"
    assert widget.results_table.item(2, 2).text() == "N/A"
    assert widget.results_table.item(2, 3).text() == "N/A"
    assert widget.results_table.item(2, 4).text() == "Missing Ref"


def test_step6_consumes_step5_element_column():
    """Verify that Step 6's Strategy 1 cleanly consumes the Step 5 validation results with Element column."""
    from src.core.step6_performance import PerformanceCalculator

    calc = PerformanceCalculator()

    # Step 5 validation results with Element column
    val_results = pd.DataFrame([
        {'Wavelength_nm': 396.15, 'Element': 'Al', 'Reference_File': 'Al.csv', 'Validation_Coefficient': 0.95, 'Tier': 'High', 'Status': 'Success'},
        {'Wavelength_nm': 422.67, 'Element': 'Ca', 'Reference_File': 'Ca.csv', 'Validation_Coefficient': 0.85, 'Tier': 'High', 'Status': 'Success'},
        {'Wavelength_nm': 393.37, 'Element': 'Ca', 'Reference_File': 'Ca.csv', 'Validation_Coefficient': 0.89, 'Tier': 'High', 'Status': 'Success'},
    ])

    ranking_df = pd.DataFrame({
        'Element': ['Al', 'Ca'],
        'Wins': [10, 8],
    })

    rows = calc._build_element_rows(ranking_df, val_results, matches=None)
    row_dict = {r['element']: r for r in rows}

    assert 'Al' in row_dict
    assert 'Ca' in row_dict
    assert row_dict['Al']['mean_vc'] == pytest.approx(0.95)
    assert row_dict['Ca']['mean_vc'] == pytest.approx(0.87)
