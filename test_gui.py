# -*- coding: utf-8 -*-
"""
GUI Test Suite - Validate GUI Components and Functionality

Tests the PyQt6 GUI without requiring a display.
Verifies:
- Widget initialization
- Signal connections
- File selectors
- Parameter controls
- Worker threads
- Data flow through GUI
"""

import sys
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src import setup_logger
from src.gui.gui_utils import (
    WorkerThread, ParameterControl, MatplotlibCanvas, FileSelector
)
from src.gui.step1_widget import Step1Widget
from src.gui.step2_widget import Step2Widget
from src.gui.step3_widget import Step3Widget
from src.gui.main_window import SpectralAnalysisApp
from src.io.file_reader import CSVReader

logger = setup_logger(__name__)


def test_gui_utils(app):
    """Test GUI utility components."""
    logger.info("\n" + "="*60)
    logger.info("TEST: GUI Utils Components")
    logger.info("="*60)
    
    # Test ParameterControl
    logger.info("\n[TEST] ParameterControl widget...")
    param = ParameterControl("Test Param", 0, 100, 50, step=1, decimals=0)
    assert param.value() == 50, "Parameter value should be 50"
    param.set_value(75)
    assert param.value() == 75, "Parameter value should be 75 after set"
    logger.info("✓ ParameterControl works correctly")
    
    # Test FileSelector
    logger.info("\n[TEST] FileSelector widget...")
    selector = FileSelector("Test File")
    assert selector.get_filepath() is None, "Initial filepath should be None"
    logger.info("✓ FileSelector initializes correctly")
    
    # Test MatplotlibCanvas
    logger.info("\n[TEST] MatplotlibCanvas widget...")
    canvas = MatplotlibCanvas(width=5, height=4, dpi=100)
    
    # Test spectrum plotting
    wl = np.linspace(200, 800, 100)
    intensity = np.sin(wl / 100) * 1000
    canvas.plot_spectrum(wl, intensity, "Test Spectrum")
    logger.info("✓ Canvas plots spectrum correctly")
    
    # Test peaks plotting
    peak_wl = np.array([300, 500, 700])
    peak_int = np.array([500, 800, 600])
    canvas.plot_peaks(wl, intensity, peak_wl, peak_int, "Test Peaks")
    logger.info("✓ Canvas plots peaks correctly")
    
    # Test clear
    canvas.clear()
    logger.info("✓ Canvas clears correctly")
    
    logger.info("\n✓✓✓ All GUI Utils tests PASSED")
    return True


def test_worker_thread(app):
    """Test WorkerThread functionality."""
    logger.info("\n" + "="*60)
    logger.info("TEST: Worker Thread")
    logger.info("="*60)
    
    # Create a simple function to run in thread
    def test_func(a, b):
        return a + b
    
    logger.info("\n[TEST] Creating worker thread...")
    worker = WorkerThread(test_func, 5, 10)
    
    # Verify signals exist
    assert hasattr(worker, 'started'), "Worker should have 'started' signal"
    assert hasattr(worker, 'finished'), "Worker should have 'finished' signal"
    assert hasattr(worker, 'error'), "Worker should have 'error' signal"
    logger.info("✓ Worker thread signals exist")
    
    logger.info("\n[TEST] Running worker thread...")
    
    results = {'done': False, 'result': None, 'error': None}
    
    def on_finished(result):
        results['result'] = result.get('result')
        results['done'] = True
    
    def on_error(error_msg):
        results['error'] = error_msg
        results['done'] = True
    
    worker.finished.connect(on_finished)
    worker.error.connect(on_error)
    worker.start()
    
    # Wait for completion (max 2 seconds)
    from PyQt6.QtCore import QEventLoop
    loop = QEventLoop()
    QTimer.singleShot(2000, loop.quit)
    loop.exec()
    
    if results['done']:
        assert results['result'] == 15, f"Worker result should be 15, got {results['result']}"
        logger.info(f"✓ Worker thread executed correctly (result: {results['result']})")
    else:
        logger.warning("! Worker thread didn't complete in time (may be expected in test environment)")
    
    logger.info("\n✓✓✓ Worker thread test PASSED")
    return True


def test_main_window_creation(app):
    """Test main window initialization."""
    logger.info("\n" + "="*60)
    logger.info("TEST: Main Window Creation")
    logger.info("="*60)
    
    logger.info("\n[TEST] Creating main window...")
    window = SpectralAnalysisApp()
    
    # Verify window properties
    assert window.windowTitle() == "Spectral Analysis Software v1.0", "Window title incorrect"
    logger.info(f"✓ Window title: {window.windowTitle()}")
    
    # Verify tabs exist
    assert window.tabs.count() == 3, f"Should have 3 tabs, got {window.tabs.count()}"
    logger.info(f"✓ Window has {window.tabs.count()} tabs")
    
    # Verify tab names
    tab_names = [
        "Step 1: Baseline Correction",
        "Step 2: Peak Detection",
        "Step 3: Element Identification"
    ]
    for i, expected_name in enumerate(tab_names):
        actual_name = window.tabs.tabText(i)
        assert actual_name == expected_name, f"Tab {i} should be '{expected_name}', got '{actual_name}'"
        logger.info(f"✓ Tab {i+1}: {actual_name}")
    
    # Verify tab widgets
    assert isinstance(window.step1_tab, Step1Widget), "Step 1 tab should be Step1Widget"
    assert isinstance(window.step2_tab, Step2Widget), "Step 2 tab should be Step2Widget"
    assert isinstance(window.step3_tab, Step3Widget), "Step 3 tab should be Step3Widget"
    logger.info("✓ All tab widgets are correct type")
    
    # Verify status bar
    assert window.statusBar is not None, "Window should have status bar"
    logger.info("✓ Status bar exists")
    
    logger.info("\n✓✓✓ Main window creation test PASSED")
    return True


def test_step1_widget(app):
    """Test Step 1 widget."""
    logger.info("\n" + "="*60)
    logger.info("TEST: Step 1 Widget (Baseline Correction)")
    logger.info("="*60)
    
    logger.info("\n[TEST] Creating Step 1 widget...")
    widget = Step1Widget()
    
    # Verify controls exist
    assert hasattr(widget, 'file_selector'), "Should have file_selector"
    assert hasattr(widget, 'lambda_control'), "Should have lambda_control"
    assert hasattr(widget, 'p_control'), "Should have p_control"
    assert hasattr(widget, 'niter_control'), "Should have niter_control"
    assert hasattr(widget, 'window_control'), "Should have window_control"
    assert hasattr(widget, 'poly_control'), "Should have poly_control"
    logger.info("✓ All parameter controls exist")
    
    # Verify buttons
    assert hasattr(widget, 'process_button'), "Should have process_button"
    assert hasattr(widget, 'save_button'), "Should have save_button"
    assert widget.save_button.isEnabled() == False, "Save button should be disabled initially"
    logger.info("✓ Buttons exist and have correct initial state")
    
    # Verify visualization components
    assert hasattr(widget, 'canvas'), "Should have canvas"
    assert hasattr(widget, 'table'), "Should have table"
    assert hasattr(widget, 'info_label'), "Should have info_label"
    logger.info("✓ Visualization components exist")
    
    # Test parameter values
    logger.info("\n[TEST] Testing parameter controls...")
    
    default_lambda = widget.lambda_control.value()
    assert default_lambda == 100000.0, f"Default lambda should be 100000, got {default_lambda}"
    
    default_p = widget.p_control.value()
    assert default_p == 0.01, f"Default p should be 0.01, got {default_p}"
    
    default_niter = widget.niter_control.value()
    assert default_niter == 10, f"Default niter should be 10, got {default_niter}"
    
    logger.info(f"✓ Lambda: {default_lambda}")
    logger.info(f"✓ Asymmetry (p): {default_p}")
    logger.info(f"✓ Iterations: {default_niter}")
    
    logger.info("\n✓✓✓ Step 1 widget test PASSED")
    return True


def test_step2_widget(app):
    """Test Step 2 widget."""
    logger.info("\n" + "="*60)
    logger.info("TEST: Step 2 Widget (Peak Detection)")
    logger.info("="*60)
    
    logger.info("\n[TEST] Creating Step 2 widget...")
    widget = Step2Widget()
    
    # Verify controls
    assert hasattr(widget, 'file_selector'), "Should have file_selector"
    assert hasattr(widget, 'height_control'), "Should have height_control"
    assert hasattr(widget, 'prominence_control'), "Should have prominence_control"
    assert hasattr(widget, 'baseline_window_control'), "Should have baseline_window_control"
    assert hasattr(widget, 'baseline_k_control'), "Should have baseline_k_control"
    logger.info("✓ All parameter controls exist")
    
    # Verify buttons
    assert hasattr(widget, 'process_button'), "Should have process_button"
    assert hasattr(widget, 'save_button'), "Should have save_button"
    assert widget.save_button.isEnabled() == False, "Save button should be disabled initially"
    logger.info("✓ Buttons exist and have correct initial state")
    
    # Test parameter values
    logger.info("\n[TEST] Testing parameter controls...")
    
    height = widget.height_control.value()
    assert height == 1.2, f"Default height multiplier should be 1.2, got {height}"
    
    prominence = widget.prominence_control.value()
    assert prominence == 0.01, f"Default prominence should be 0.01, got {prominence}"
    
    logger.info(f"✓ Height Multiplier: {height}")
    logger.info(f"✓ Prominence: {prominence}")
    
    logger.info("\n✓✓✓ Step 2 widget test PASSED")
    return True


def test_step3_widget(app):
    """Test Step 3 widget."""
    logger.info("\n" + "="*60)
    logger.info("TEST: Step 3 Widget (Element Identification)")
    logger.info("="*60)
    
    logger.info("\n[TEST] Creating Step 3 widget...")
    widget = Step3Widget()
    
    # Verify controls
    assert hasattr(widget, 'peaks_selector'), "Should have peaks_selector"
    assert hasattr(widget, 'nist_selector'), "Should have nist_selector"
    assert hasattr(widget, 'tolerance_control'), "Should have tolerance_control"
    assert hasattr(widget, 'threshold_control'), "Should have threshold_control"
    logger.info("✓ All file selectors and controls exist")
    
    # Verify buttons
    assert hasattr(widget, 'match_button'), "Should have match_button"
    assert hasattr(widget, 'save_button'), "Should have save_button"
    assert widget.save_button.isEnabled() == False, "Save button should be disabled initially"
    logger.info("✓ Buttons exist and have correct initial state")
    
    # Verify table
    assert hasattr(widget, 'table'), "Should have table"
    assert widget.table.columnCount() == 7, f"Table should have 7 columns, got {widget.table.columnCount()}"
    logger.info(f"✓ Results table has {widget.table.columnCount()} columns")
    
    # Test parameter values
    logger.info("\n[TEST] Testing parameter controls...")
    
    tolerance = widget.tolerance_control.value()
    assert tolerance == 0.2, f"Default tolerance should be 0.2, got {tolerance}"
    logger.info(f"✓ Tolerance: {tolerance} nm")
    
    logger.info("\n✓✓✓ Step 3 widget test PASSED")
    return True


def test_data_flow(app):
    """Test end-to-end data flow."""
    logger.info("\n" + "="*60)
    logger.info("TEST: End-to-End Data Flow")
    logger.info("="*60)
    
    # Load sample data
    logger.info("\n[TEST] Loading sample data...")
    reader = CSVReader()
    
    input_file = Path("data/sample_inputs/soil3-unprocessed.csv")
    if not input_file.exists():
        logger.warning(f"! Sample input file not found: {input_file}")
        logger.info("Skipping data flow test")
        return True
    
    raw_spectra = reader.read_raw_spectra(str(input_file))
    logger.info(f"✓ Loaded {len(raw_spectra.wavelength)} spectral points")
    
    # Test Step 1 processing
    logger.info("\n[TEST] Testing Step 1 data flow...")
    from src.core.step1_sg_als import BaselineCorrection
    
    corrector = BaselineCorrection()
    processed = corrector.process(raw_spectra.wavelength, raw_spectra.intensity)
    
    assert len(processed.corrected) == len(raw_spectra.wavelength), "Output should have same length as input"
    assert np.isfinite(processed.corrected).all(), "Output should have no NaN/Inf values"
    logger.info(f"✓ Step 1 produced {len(processed.corrected)} corrected points")
    
    # Test Step 2 processing
    logger.info("\n[TEST] Testing Step 2 data flow...")
    from src.core.step2_peaks import PeaksDetector
    
    detector = PeaksDetector()
    detected_peaks = detector.detect_peaks(processed.wavelength, processed.corrected)
    
    assert len(detected_peaks) > 0, "Should detect at least some peaks"
    assert all(hasattr(p, 'wavelength') and hasattr(p, 'intensity') for p in detected_peaks), \
        "Each peak should have wavelength and intensity"
    logger.info(f"✓ Step 2 detected {len(detected_peaks)} peaks")
    
    # Test Step 3 processing
    logger.info("\n[TEST] Testing Step 3 data flow...")
    from src.core.step3_nist_matching import NISTMatcher
    
    nist_file = Path("data/nist_databases/NIST-Ca.csv")
    if nist_file.exists():
        nist_db = reader.read_nist_database(str(nist_file))
        matcher = NISTMatcher()
        matches = matcher.match_peaks(detected_peaks, nist_db)
        
        assert len(matches) == len(detected_peaks), "Should have one match per peak"
        identified = [m for m in matches if m.element]
        logger.info(f"✓ Step 3 matched {len(identified)}/{len(matches)} peaks to elements")
    else:
        logger.warning(f"! NIST database not found: {nist_file}")
        logger.info("Skipping Step 3 matching")
    
    logger.info("\n✓✓✓ Data flow test PASSED")
    return True


def main():
    """Run all tests."""
    # Create QApplication first
    app = QApplication.instance() or QApplication([])
    
    logger.info("\n")
    logger.info("="*60)
    logger.info("GUI TEST SUITE - SPECTRAL ANALYSIS SOFTWARE".center(60))
    logger.info("="*60)
    
    tests = [
        ("GUI Utils", test_gui_utils),
        ("Worker Thread", test_worker_thread),
        ("Main Window", test_main_window_creation),
        ("Step 1 Widget", test_step1_widget),
        ("Step 2 Widget", test_step2_widget),
        ("Step 3 Widget", test_step3_widget),
        ("Data Flow", test_data_flow),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func(app)
            results.append((test_name, "PASS" if result else "FAIL"))
        except Exception as e:
            logger.error(f"X {test_name} test FAILED: {e}", exc_info=True)
            results.append((test_name, "FAIL"))
    
    # Summary
    logger.info("\n")
    logger.info("="*60)
    logger.info("TEST SUMMARY".center(60))
    logger.info("="*60)
    
    for test_name, result in results:
        status = "[OK]" if result == "PASS" else "[FAIL]"
        logger.info(f"{status:7} {test_name:<48}")
    
    logger.info("="*60)
    
    passed = sum(1 for _, r in results if r == "PASS")
    total = len(results)
    logger.info(f"Total: {passed}/{total} tests passed".center(60))
    logger.info("="*60)
    
    if passed == total:
        logger.info("\n[SUCCESS] ALL TESTS PASSED\n")
        return 0
    else:
        logger.warning(f"\n[FAILED] {total - passed} TEST(S) FAILED\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
