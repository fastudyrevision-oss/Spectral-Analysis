# -*- coding: utf-8 -*-
"""
Conftest - Pytest Fixtures and Configuration

Provides common fixtures for all tests.
"""

import pytest
import numpy as np
from pathlib import Path
import tempfile
import pandas as pd
from PyQt6.QtWidgets import QApplication

from src.io.data_models import RawSpectra, ProcessedSpectra, DetectedPeak, NISTMatch


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for GUI tests (session-scoped)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(scope="function")
def app(qapp):
    """Provide QApplication instance for each test (function-scoped)."""
    yield qapp


@pytest.fixture
def sample_spectrum():
    """Create sample spectrum data."""
    wl = np.linspace(200, 800, 1000)
    intensity = np.sin(wl / 100) * 500 + 1000
    return RawSpectra(
        wavelength=wl,
        intensity=intensity,
        metadata={'source': 'test'},
        source_file='test.csv'
    )


@pytest.fixture
def processed_spectrum():
    """Create processed spectrum data."""
    wl = np.linspace(200, 800, 1000)
    raw = np.sin(wl / 100) * 500 + 1000
    smoothed = np.sin(wl / 100) * 490 + 1000
    baseline = np.linspace(50, 150, 1000)
    corrected = raw - baseline
    
    return ProcessedSpectra(
        wavelength=wl,
        raw=raw,
        smoothed_sg=smoothed,
        baseline_als=baseline,
        corrected=corrected,
        baseline_iterations=[baseline]
    )


@pytest.fixture
def detected_peaks():
    """Create sample detected peaks."""
    return [
        DetectedPeak(wavelength=300.0, intensity=500.0),
        DetectedPeak(wavelength=400.0, intensity=700.0),
        DetectedPeak(wavelength=500.0, intensity=600.0),
        DetectedPeak(wavelength=600.0, intensity=800.0),
        DetectedPeak(wavelength=700.0, intensity=550.0),
    ]


@pytest.fixture
def sample_csv_file(tmp_path):
    """Create sample CSV file."""
    csv_path = tmp_path / "sample.csv"
    df = pd.DataFrame({
        'wavelength (nm)': np.linspace(200, 800, 100),
        'intensity': np.random.rand(100) * 1000
    })
    df.to_csv(csv_path, index=False)
    return csv_path


@pytest.fixture
def sample_peaks_csv(tmp_path):
    """Create sample detected peaks CSV."""
    csv_path = tmp_path / "peaks.csv"
    df = pd.DataFrame({
        'Wavelength (nm)': [300.0, 400.0, 500.0],
        'Intensity': [500.0, 700.0, 600.0]
    })
    df.to_csv(csv_path, index=False)
    return csv_path


@pytest.fixture
def sample_nist_csv(tmp_path):
    """Create sample NIST database CSV."""
    csv_path = tmp_path / "nist.csv"
    df = pd.DataFrame({
        'Wavelength': [300.1, 400.0, 500.2],
        'element': ['Ca', 'Ca', 'Ca'],
        'Aki': [1e6, 1e7, 1e5],
        'relative_intensity': [100, 150, 80]
    })
    df.to_csv(csv_path, index=False)
    return csv_path


@pytest.fixture
def temp_dir():
    """Create temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)
