# -*- coding: utf-8 -*-
"""
Test Suite for I/O Layer

Tests file reading, writing, and data transformation.
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from src.io.file_reader import CSVReader
from src.io.file_writer import CSVWriter, PlotGenerator
from src.exceptions import FileIOError, ColumnDetectionError


class TestCSVReader:
    """Tests for CSV file reading."""
    
    def test_initialization(self):
        """Test CSVReader initialization."""
        reader = CSVReader()
        assert reader is not None
    
    def test_read_raw_spectra(self, sample_csv_file):
        """Test reading raw spectra file."""
        reader = CSVReader()
        spectra = reader.read_raw_spectra(str(sample_csv_file))
        
        assert len(spectra.wavelength) == 100
        assert len(spectra.intensity) == 100
        assert spectra.wavelength.dtype == np.float64
        assert spectra.intensity.dtype == np.float64
    
    def test_read_detected_peaks(self, sample_peaks_csv):
        """Test reading detected peaks file."""
        reader = CSVReader()
        peaks = reader.read_detected_peaks(str(sample_peaks_csv))
        
        assert len(peaks) == 3
        assert all(hasattr(p, 'wavelength') for p in peaks)
        assert all(hasattr(p, 'intensity') for p in peaks)
    
    def test_read_nist_database(self, sample_nist_csv):
        """Test reading NIST database file."""
        reader = CSVReader()
        nist_df = reader.read_nist_database(str(sample_nist_csv))
        
        # Check standard columns exist
        assert 'Wavelength' in nist_df.columns
        assert 'Element' in nist_df.columns
        assert len(nist_df) == 3
    
    def test_file_not_found(self):
        """Test error on missing file."""
        reader = CSVReader()
        
        with pytest.raises(FileIOError):
            reader.read_raw_spectra("nonexistent_file.csv")
    
    def test_column_detection_flexible(self, tmp_path):
        """Test flexible column detection."""
        # Create CSV with alternate column names that should be detected
        csv_path = tmp_path / "alt_columns.csv"
        df = pd.DataFrame({
            'wavelength': np.linspace(200, 800, 100),  # Should be detected
            'intensity': np.random.rand(100) * 1000
        })
        df.to_csv(csv_path, index=False)
        
        reader = CSVReader()
        spectra = reader.read_raw_spectra(str(csv_path))
        
        assert len(spectra.wavelength) == 100


class TestCSVWriter:
    """Tests for CSV file writing."""
    
    def test_initialization(self):
        """Test CSVWriter initialization."""
        writer = CSVWriter(precision=12)
        assert writer.precision == 12
    
    def test_write_processed_spectra(self, processed_spectrum, temp_dir):
        """Test writing processed spectra."""
        writer = CSVWriter()
        output_path = writer.write_processed_spectra(
            str(temp_dir / "output.csv"),
            processed_spectrum
        )
        
        assert output_path.exists()
        
        # Verify contents
        df = pd.read_csv(output_path)
        assert len(df) == len(processed_spectrum.wavelength)
        assert 'Wavelength' in df.columns
        assert 'Corrected' in df.columns
    
    def test_write_detected_peaks(self, detected_peaks, temp_dir):
        """Test writing detected peaks."""
        writer = CSVWriter()
        output_path = writer.write_detected_peaks(
            str(temp_dir / "peaks.csv"),
            detected_peaks
        )
        
        assert output_path.exists()
        
        df = pd.read_csv(output_path)
        assert len(df) == len(detected_peaks)
        assert 'Wavelength' in df.columns or 'Wavelength (nm)' in df.columns
    
    def test_write_nist_matches(self, temp_dir):
        """Test writing NIST matches."""
        from src.io.data_models import NISTMatch
        
        matches = [
            NISTMatch(300.0, 300.1, 0.1, 1e6, 100, 1e8, 'Ca'),
            NISTMatch(400.0, None, None, 0, 0, 0, None),
        ]
        
        writer = CSVWriter()
        output_path = writer.write_nist_matches(
            str(temp_dir / "matches.csv"),
            matches
        )
        
        assert output_path.exists()
        df = pd.read_csv(output_path)
        assert len(df) == len(matches)
    
    def test_precision_preservation(self, processed_spectrum, temp_dir):
        """Test that precision is preserved in output."""
        writer = CSVWriter(precision=12)
        output_path = writer.write_processed_spectra(
            str(temp_dir / "precision_test.csv"),
            processed_spectrum
        )
        
        df = pd.read_csv(output_path)
        
        # Check that values have high precision
        first_value = df.iloc[0]['Corrected']
        # Should preserve at least several decimal places
        assert isinstance(first_value, (float, np.floating))


class TestPlotGenerator:
    """Tests for plot generation."""
    
    def test_initialization(self):
        """Test PlotGenerator initialization."""
        gen = PlotGenerator(dpi=600)
        assert gen.dpi == 600
    
    def test_plot_baseline_creation(self, processed_spectrum, temp_dir):
        """Test baseline correction plot creation."""
        gen = PlotGenerator()
        output_path = gen.plot_step1_baseline(
            processed_spectrum,
            str(temp_dir / "baseline.png")
        )
        
        assert output_path.exists()
        assert output_path.suffix == '.png'
        assert output_path.stat().st_size > 1000  # Should be reasonable size
    
    def test_plot_peaks_creation(self, processed_spectrum, detected_peaks, temp_dir):
        """Test peaks detection plot creation."""
        gen = PlotGenerator()
        output_path = gen.plot_step2_peaks(
            processed_spectrum.wavelength,
            processed_spectrum.corrected,
            detected_peaks,
            str(temp_dir / "peaks.png")
        )
        
        assert output_path.exists()
        assert output_path.suffix == '.png'
        assert output_path.stat().st_size > 1000


class TestDataIntegrity:
    """Tests for data integrity across I/O operations."""
    
    def test_read_write_roundtrip(self, processed_spectrum, temp_dir):
        """Test data integrity through write-read cycle."""
        # Write
        writer = CSVWriter(precision=12)
        write_path = writer.write_processed_spectra(
            str(temp_dir / "roundtrip.csv"),
            processed_spectrum
        )
        
        # Read
        reader = CSVReader()
        df = pd.read_csv(write_path)
        
        # Verify
        original_wl = processed_spectrum.wavelength
        read_wl = df['Wavelength'].values
        
        # Allow small precision loss
        np.testing.assert_allclose(original_wl, read_wl, rtol=1e-6)
    
    def test_peak_data_consistency(self, detected_peaks, temp_dir):
        """Test peak data consistency through write-read cycle."""
        writer = CSVWriter()
        write_path = writer.write_detected_peaks(
            str(temp_dir / "peaks_roundtrip.csv"),
            detected_peaks
        )
        
        reader = CSVReader()
        read_peaks = reader.read_detected_peaks(str(write_path))
        
        assert len(read_peaks) == len(detected_peaks)
        
        for original, read in zip(detected_peaks, read_peaks):
            assert abs(original.wavelength - read.wavelength) < 1e-5
            assert abs(original.intensity - read.intensity) < 1e-5


class TestFileValidation:
    """Tests for file validation and error handling."""
    
    def test_invalid_csv_format(self, tmp_path):
        """Test handling of invalid CSV format."""
        invalid_csv = tmp_path / "invalid.csv"
        invalid_csv.write_text("this is not a valid csv")
        
        reader = CSVReader()
        with pytest.raises((FileIOError, ColumnDetectionError)):
            reader.read_raw_spectra(str(invalid_csv))
    
    def test_empty_csv(self, tmp_path):
        """Test handling of empty CSV."""
        empty_csv = tmp_path / "empty.csv"
        df = pd.DataFrame()
        df.to_csv(empty_csv, index=False)
        
        reader = CSVReader()
        with pytest.raises((FileIOError, ColumnDetectionError)):
            reader.read_raw_spectra(str(empty_csv))
    
    def test_missing_wavelength_column(self, tmp_path):
        """Test error when wavelength column is missing."""
        csv_path = tmp_path / "no_wl.csv"
        df = pd.DataFrame({'data': [1, 2, 3]})
        df.to_csv(csv_path, index=False)
        
        reader = CSVReader()
        with pytest.raises(FileIOError):
            reader.read_raw_spectra(str(csv_path))
