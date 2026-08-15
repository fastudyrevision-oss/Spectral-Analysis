# -*- coding: utf-8 -*-
"""
File Reader for Spectral Analysis Software

Reads CSV files with robust validation, flexible column detection,
and automatic delimiter detection.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Optional, Dict

from src import setup_logger, FileIOError, ColumnDetectionError
from src.io.data_models import RawSpectra, ProcessedSpectra, DetectedPeak


logger = setup_logger(__name__)


class CSVReader:
    """
    Read CSV files with robust validation and flexible column detection.
    
    Handles:
    - Multiple delimiters (auto-detection)
    - Multiple encodings
    - Flexible column name matching
    - Data type validation
    - Precision preservation (float64)
    """
    
    def __init__(self, auto_detect_delimiter: bool = True):
        """
        Initialize CSV reader.
        
        Parameters
        ----------
        auto_detect_delimiter : bool
            Whether to auto-detect delimiter
        """
        self.auto_detect_delimiter = auto_detect_delimiter
        logger.info("CSVReader initialized")
    
    def detect_delimiter(self, filepath: str) -> str:
        """
        Detect CSV delimiter.
        
        Parameters
        ----------
        filepath : str
            Path to CSV file
        
        Returns
        -------
        str
            Detected delimiter (comma, tab, semicolon)
        """
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
        
        if ',' in first_line:
            return ','
        elif '\t' in first_line:
            return '\t'
        elif ';' in first_line:
            return ';'
        else:
            return ','  # default
    
    def read_raw_spectra(self, filepath: str) -> RawSpectra:
        """
        Read raw spectra (wavelength + intensity).
        
        Parameters
        ----------
        filepath : str
            Path to CSV file
        
        Returns
        -------
        RawSpectra
            Raw spectra data object
        
        Raises
        ------
        FileIOError
            If file cannot be read
        ColumnDetectionError
            If required columns not found
        """
        logger.info(f"Reading raw spectra from: {filepath}")
        
        try:
            # Detect delimiter
            delimiter = self.detect_delimiter(filepath) if self.auto_detect_delimiter else ','
            logger.debug(f"Using delimiter: {repr(delimiter)}")
            
            # Read CSV
            df = pd.read_csv(filepath, sep=delimiter, skiprows=0)
            df.columns = df.columns.str.strip()
            
            logger.debug(f"CSV loaded. Columns: {list(df.columns)}")
            logger.debug(f"Shape: {df.shape}")
            
            # Detect wavelength column
            wl_col = self._find_column(df, ['wavelength', 'wl', 'wavelength (nm)'])
            if wl_col is None:
                raise ColumnDetectionError("Cannot find wavelength column")
            
            # Detect intensity column
            int_col = self._find_column(df, ['intensity', 'signal', 'counts', 'data'])
            if int_col is None:
                raise ColumnDetectionError("Cannot find intensity column")
            
            logger.info(f"Detected columns: wavelength={wl_col}, intensity={int_col}")
            
            # Extract and convert
            wavelength = pd.to_numeric(df[wl_col], errors='coerce').values.astype(np.float64)
            intensity = pd.to_numeric(df[int_col], errors='coerce').values.astype(np.float64)
            
            # Check for NaN
            if np.any(np.isnan(wavelength)):
                raise FileIOError(f"NaN values in wavelength column")
            if np.any(np.isnan(intensity)):
                raise FileIOError(f"NaN values in intensity column")
            
            logger.info(f"Successfully read {len(wavelength)} data points")
            logger.info(f"Wavelength range: [{wavelength.min():.2f}, {wavelength.max():.2f}] nm")
            logger.info(f"Intensity range: [{intensity.min():.6e}, {intensity.max():.6e}]")
            
            return RawSpectra(
                wavelength=wavelength,
                intensity=intensity,
                source_file=str(filepath)
            )
        
        except Exception as e:
            logger.error(f"Failed to read raw spectra: {e}")
            raise FileIOError(f"Failed to read {filepath}: {e}") from e
    
    def read_detected_peaks(self, filepath: str) -> List[DetectedPeak]:
        """
        Read detected peaks (from Step 2 output).
        
        Parameters
        ----------
        filepath : str
            Path to CSV file
        
        Returns
        -------
        List[DetectedPeak]
            List of detected peaks
        
        Raises
        ------
        FileIOError
            If file cannot be read
        """
        logger.info(f"Reading detected peaks from: {filepath}")
        
        try:
            delimiter = self.detect_delimiter(filepath) if self.auto_detect_delimiter else ','
            df = pd.read_csv(filepath, sep=delimiter)
            df.columns = df.columns.str.strip()
            
            # Detect columns
            wl_col = self._find_column(df, ['wavelength', 'wl', 'wavelength (nm)'])
            int_col = self._find_column(df, ['intensity', 'signal', 'counts'])
            
            if wl_col is None or int_col is None:
                raise ColumnDetectionError(f"Cannot find required columns in {filepath}")
            
            peaks = [
                DetectedPeak(float(row[wl_col]), float(row[int_col]))
                for _, row in df.iterrows()
            ]
            
            logger.info(f"Read {len(peaks)} detected peaks")
            return peaks
        
        except Exception as e:
            logger.error(f"Failed to read detected peaks: {e}")
            raise FileIOError(f"Failed to read {filepath}: {e}") from e
    
    def read_nist_database(self, filepath: str) -> pd.DataFrame:
        """
        Read NIST database with flexible column mapping.

        Supports .csv, .xlsx, .csv.xlsx, and .scv.xlsx file formats.

        Parameters
        ----------
        filepath : str
            Path to NIST database file (.csv or .xlsx)

        Returns
        -------
        pd.DataFrame
            NIST database with standardized columns

        Raises
        ------
        FileIOError
            If file cannot be read
        ColumnDetectionError
            If wavelength column not found
        """
        logger.info(f"Reading NIST database from: {filepath}")

        try:
            name_lower = Path(filepath).name.lower()
            if (name_lower.endswith(".xlsx") or
                    name_lower.endswith(".csv.xlsx") or
                    name_lower.endswith(".scv.xlsx")):
                df = pd.read_excel(filepath)
            else:
                delimiter = self.detect_delimiter(filepath) if self.auto_detect_delimiter else ","
                df = pd.read_csv(filepath, sep=delimiter, skiprows=0)
            df.columns = df.columns.str.strip()
            
            logger.debug(f"NIST CSV loaded. Columns: {list(df.columns)}")
            
            # Detect wavelength column (required)
            wl_col = self._find_column(df, ['wavelength', 'wl', 'wavelength (nm)', 'wave'])
            if wl_col is None:
                raise ColumnDetectionError("NIST database must contain wavelength column")
            
            # Detect optional columns
            element_col = self._find_column(df, ['element', 'element_symbol', 'ion'])
            aki_col = self._find_column(df, ['aki', 'intensity', 'strength', 'transition'])
            rel_int_col = self._find_column(df, ['relative_intensity', 'rel_int', 'rel intensity'])
            
            logger.info(f"NIST columns detected: wl={wl_col}, element={element_col}, aki={aki_col}, rel_int={rel_int_col}")
            
            # Standardize columns
            df_std = pd.DataFrame()
            df_std['Wavelength'] = pd.to_numeric(df[wl_col], errors='coerce')
            
            if element_col:
                df_std['Element'] = df[element_col].astype(str)
            else:
                df_std['Element'] = 'Unknown'
            
            if aki_col:
                df_std['Aki'] = pd.to_numeric(df[aki_col], errors='coerce').fillna(1)
            else:
                df_std['Aki'] = 1.0
            
            if rel_int_col:
                df_std['relative_intensity'] = pd.to_numeric(df[rel_int_col], errors='coerce').fillna(1)
            else:
                df_std['relative_intensity'] = 1.0
            
            # Drop rows with NaN wavelength
            df_std = df_std.dropna(subset=['Wavelength'])
            
            logger.info(f"NIST database loaded: {len(df_std)} entries")
            
            return df_std
        
        except Exception as e:
            logger.error(f"Failed to read NIST database: {e}")
            raise FileIOError(f"Failed to read NIST database {filepath}: {e}") from e
    
    @staticmethod
    def _find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
        """
        Find column in DataFrame by multiple candidate names (case-insensitive).
        
        Parameters
        ----------
        df : pd.DataFrame
            DataFrame to search
        candidates : List[str]
            List of candidate column names
        
        Returns
        -------
        Optional[str]
            Column name if found, None otherwise
        """
        df_cols_lower = [col.lower() for col in df.columns]
        
        for candidate in candidates:
            candidate_lower = candidate.lower()
            if candidate_lower in df_cols_lower:
                idx = df_cols_lower.index(candidate_lower)
                return df.columns[idx]
        
        return None
