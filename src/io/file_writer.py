# -*- coding: utf-8 -*-
"""
File Writer & Plot Generator for Spectral Analysis Software

Writes CSV output with high precision formatting and generates
publication-quality plots.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from typing import List

from src import setup_logger, OUTPUT_CONFIG, FileIOError
from src.io.data_models import ProcessedSpectra, DetectedPeak, NISTMatch


logger = setup_logger(__name__)


class CSVWriter:
    """Write CSV files with consistent formatting and high precision."""
    
    def __init__(self, precision: int = None):
        """
        Initialize CSV writer.
        
        Parameters
        ----------
        precision : int, optional
            Decimal places in output (default from OUTPUT_CONFIG)
        """
        self.precision = precision or OUTPUT_CONFIG['CSV_PRECISION']
        logger.info(f"CSVWriter initialized with precision={self.precision}")
    
    def write_processed_spectra(self, filepath: str, 
                               data: ProcessedSpectra) -> Path:
        """
        Write processed spectra (Step 1 output).
        
        Parameters
        ----------
        filepath : str
            Output CSV file path
        data : ProcessedSpectra
            Processed spectra data
        
        Returns
        -------
        Path
            Path to written file
        
        Raises
        ------
        FileIOError
            If write fails
        """
        logger.info(f"Writing processed spectra to: {filepath}")
        
        try:
            df = pd.DataFrame({
                'Wavelength': data.wavelength,
                'Raw': data.raw,
                'Smoothed_SG': data.smoothed_sg,
                'Baseline_ALS': data.baseline_als,
                'Corrected': data.corrected
            })
            
            # Write with high precision
            with open(filepath, 'w') as f:
                f.write(df.to_csv(
                    index=False,
                    float_format=f'%.{self.precision}g'
                ))
            
            logger.info(f"Successfully wrote {len(df)} rows to {filepath}")
            return Path(filepath)
        
        except Exception as e:
            logger.error(f"Failed to write processed spectra: {e}")
            raise FileIOError(f"Failed to write to {filepath}: {e}") from e
    
    def write_detected_peaks(self, filepath: str, 
                            peaks: List[DetectedPeak]) -> Path:
        """
        Write detected peaks (Step 2 output).
        
        Parameters
        ----------
        filepath : str
            Output CSV file path
        peaks : List[DetectedPeak]
            Detected peaks
        
        Returns
        -------
        Path
            Path to written file
        """
        logger.info(f"Writing detected peaks to: {filepath}")
        
        try:
            df = pd.DataFrame({
                'Wavelength (nm)': [p.wavelength for p in peaks],
                'Intensity': [p.intensity for p in peaks]
            })
            
            with open(filepath, 'w') as f:
                f.write(df.to_csv(
                    index=False,
                    float_format=f'%.{self.precision}g'
                ))
            
            logger.info(f"Successfully wrote {len(df)} peaks to {filepath}")
            return Path(filepath)
        
        except Exception as e:
            logger.error(f"Failed to write detected peaks: {e}")
            raise FileIOError(f"Failed to write to {filepath}: {e}") from e
    
    def write_nist_matches(self, filepath: str, 
                          matches: List[NISTMatch]) -> Path:
        """
        Write NIST matching results (Step 3 output).
        
        Parameters
        ----------
        filepath : str
            Output CSV file path
        matches : List[NISTMatch]
            NIST match results
        
        Returns
        -------
        Path
            Path to written file
        """
        logger.info(f"Writing NIST matches to: {filepath}")
        
        try:
            df = pd.DataFrame({
                'Observed_WL': [m.observed_wl for m in matches],
                'Matched_WL': [m.matched_wl for m in matches],
                'Delta': [m.delta for m in matches],
                'Aki': [m.aki for m in matches],
                'relative_intensity': [m.relative_intensity for m in matches],
                'Score': [m.score for m in matches],
                'Element': [m.element for m in matches]
            })
            
            with open(filepath, 'w') as f:
                f.write(df.to_csv(
                    index=False,
                    float_format=f'%.{self.precision}g'
                ))
            
            logger.info(f"Successfully wrote {len(df)} matches to {filepath}")
            return Path(filepath)
        
        except Exception as e:
            logger.error(f"Failed to write NIST matches: {e}")
            raise FileIOError(f"Failed to write to {filepath}: {e}") from e


class PlotGenerator:
    """Generate high-quality scientific plots."""
    
    def __init__(self, dpi: int = None, fmt: str = None):
        """
        Initialize plot generator.
        
        Parameters
        ----------
        dpi : int, optional
            Plot resolution (default from OUTPUT_CONFIG)
        fmt : str, optional
            Image format (default from OUTPUT_CONFIG)
        """
        self.dpi = dpi or OUTPUT_CONFIG['PLOT_DPI']
        self.fmt = fmt or OUTPUT_CONFIG['PLOT_FORMAT']
        logger.info(f"PlotGenerator initialized: dpi={self.dpi}, format={self.fmt}")
    
    def plot_step1_baseline(self, data: ProcessedSpectra, 
                           filepath: str = None) -> Path:
        """
        Generate Step 1 baseline correction plot.
        
        Creates 2-subplot figure:
        - (a) Baseline separation with offset visualization
        - (b) ALS convergence heatmap with iteration overlays
        
        Parameters
        ----------
        data : ProcessedSpectra
            Processed spectra with baseline iterations
        filepath : str, optional
            Output file path
        
        Returns
        -------
        Path
            Path to saved figure
        """
        logger.info("Generating Step 1 baseline correction plot")
        
        try:
            if filepath is None:
                filepath = f"SG_ALS_LIBS_processed.{self.fmt}"
            
            fig, axs = plt.subplots(1, 2, figsize=(14, 5))
            
            # Subplot (a): Baseline Separation
            OFFSET = 4000
            ax = axs[0]
            
            ax.plot(data.wavelength, data.raw + OFFSET, 
                   alpha=0.5, label="Raw Spectra", linewidth=1.5)
            ax.plot(data.wavelength, data.smoothed_sg, 
                   label="SG Smoothed", linewidth=1.5)
            ax.plot(data.wavelength, data.baseline_als, '--', 
                   linewidth=2, label="ALS Baseline", color='black')
            ax.plot(data.wavelength, data.corrected - OFFSET, 
                   label="Corrected Spectra", linewidth=1.5)
            
            ax.set_title("(a) SG + ALS Baseline Separation", fontsize=12, fontweight='bold')
            ax.set_xlabel("Wavelength (nm)", fontsize=11)
            ax.set_ylabel("Intensity (offset)", fontsize=11)
            ax.legend(fontsize=10)
            ax.grid(True, alpha=0.3)
            
            # Subplot (b): ALS Convergence
            ax = axs[1]
            
            if data.baseline_iterations:
                baseline_matrix = np.array(data.baseline_iterations)
                
                im = ax.imshow(baseline_matrix,
                             aspect='auto',
                             extent=[data.wavelength.min(), data.wavelength.max(), 
                                    1, len(data.baseline_iterations)],
                             origin='lower',
                             cmap='plasma')
                
                # Overlay selected iterations
                selected_iters = [0, len(data.baseline_iterations)//3, 
                                2*len(data.baseline_iterations)//3, 
                                len(data.baseline_iterations)-1]
                colors = ['white', 'yellow', 'cyan', 'red']
                
                for i, c in zip(selected_iters, colors):
                    if i < len(data.baseline_iterations):
                        norm_curve = (data.baseline_iterations[i] / 
                                    np.max(data.baseline_iterations[i]) * 
                                    len(data.baseline_iterations))
                        ax.plot(data.wavelength, norm_curve,
                               linestyle='--', linewidth=1.5,
                               color=c, label=f"Iter {i+1}")
                
                fig.colorbar(im, ax=ax, label="Baseline Intensity")
                ax.legend(title="Iterations", fontsize=10)
            
            ax.set_title("(b) ALS Iterative Baseline Convergence", fontsize=12, fontweight='bold')
            ax.set_xlabel("Wavelength (nm)", fontsize=11)
            ax.set_ylabel("Iteration", fontsize=11)
            
            plt.tight_layout()
            plt.savefig(filepath, dpi=self.dpi, format=self.fmt)
            logger.info(f"Saved baseline correction plot to: {filepath}")
            plt.close()
            
            return Path(filepath)
        
        except Exception as e:
            logger.error(f"Failed to generate baseline plot: {e}")
            raise FileIOError(f"Failed to save plot: {e}") from e
    
    def plot_step2_peaks(self, wavelength: np.ndarray, 
                        intensity: np.ndarray,
                        peaks: List[DetectedPeak],
                        filepath: str = None) -> Path:
        """
        Generate Step 2 peaks detection plot.
        
        Parameters
        ----------
        wavelength : np.ndarray
            Wavelength array
        intensity : np.ndarray
            Intensity array
        peaks : List[DetectedPeak]
            Detected peaks
        filepath : str, optional
            Output file path
        
        Returns
        -------
        Path
            Path to saved figure
        """
        logger.info("Generating Step 2 peaks detection plot")
        
        try:
            if filepath is None:
                filepath = f"Automatic_peaks_identification.{self.fmt}"
            
            fig, ax = plt.subplots(figsize=(15, 8))
            
            # Plot spectrum
            ax.plot(wavelength, intensity, color='red', linewidth=1.5, label='Spectrum')
            
            # Plot peaks
            peak_wl = np.array([p.wavelength for p in peaks])
            peak_int = np.array([p.intensity for p in peaks])
            ax.scatter(peak_wl, peak_int, color='black', s=50, label=f'Peaks (n={len(peaks)})')
            
            ax.set_xlabel("Wavelength (nm)", fontsize=20)
            ax.set_ylabel("Intensity", fontsize=20)
            ax.tick_params(axis='both', which='major', labelsize=16)
            ax.grid(False)
            ax.legend(fontsize=14)
            
            ax.set_title("Automatic Peaks Identification", fontsize=14, fontweight='bold')
            
            plt.tight_layout()
            plt.savefig(filepath, dpi=self.dpi, format=self.fmt)
            logger.info(f"Saved peaks detection plot to: {filepath}")
            plt.close()
            
            return Path(filepath)
        
        except Exception as e:
            logger.error(f"Failed to generate peaks plot: {e}")
            raise FileIOError(f"Failed to save plot: {e}") from e
