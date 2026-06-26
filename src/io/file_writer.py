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
        """Generate Step 1 baseline correction plot — dark theme, consistent with UI."""
        logger.info("Generating Step 1 baseline correction plot")

        _BG_BASE    = "#141519"
        _BG_RAISED  = "#2F3443"
        _BORDER     = "#3A4055"
        _ACCENT     = "#3FA9F5"   # corrected / SG smoothed
        _ACCENT2    = "#3DDC97"   # baseline
        _WARN       = "#F4B942"   # raw (offset)
        _ERROR      = "#E85D75"   # ALS baseline line
        _TEXT       = "#F0F2F5"
        _TEXT2      = "#AEB7C4"
        _GRID       = "#3A4055"

        def _dark_ax(ax_):
            ax_.set_facecolor(_BG_RAISED)
            ax_.tick_params(colors=_TEXT2, which="both", labelsize=9)
            ax_.xaxis.label.set_color(_TEXT2)
            ax_.yaxis.label.set_color(_TEXT2)
            ax_.title.set_color(_TEXT)
            for sp in ax_.spines.values():
                sp.set_edgecolor(_BORDER)
                sp.set_linewidth(0.8)
            ax_.grid(True, color=_GRID, alpha=0.4, linewidth=0.5, linestyle="--")

        try:
            if filepath is None:
                filepath = f"SG_ALS_LIBS_processed.{self.fmt}"

            fig, axs = plt.subplots(1, 2, figsize=(14, 5))
            fig.patch.set_facecolor(_BG_BASE)

            # ── Subplot (a): Baseline Separation ──────────────────────────
            OFFSET = 4000
            ax = axs[0]
            ax.plot(data.wavelength, data.raw + OFFSET,
                    color=_WARN,   linewidth=1.0, alpha=0.65, label="Raw (offset)")
            ax.plot(data.wavelength, data.smoothed_sg,
                    color=_ACCENT, linewidth=1.0, alpha=0.90, label="SG Smoothed")
            ax.plot(data.wavelength, data.baseline_als,
                    color=_ERROR,  linewidth=1.4, linestyle="--", label="ALS Baseline")
            ax.plot(data.wavelength, data.corrected - OFFSET,
                    color=_ACCENT2, linewidth=1.0, label="Corrected")
            ax.set_title("(a) SG + ALS Baseline Separation",
                         fontsize=11, fontweight="bold")
            ax.set_xlabel("Wavelength (nm)", fontsize=10)
            ax.set_ylabel("Intensity (offset)", fontsize=10)
            leg = ax.legend(fontsize=9, framealpha=0.7)
            leg.get_frame().set_facecolor(_BG_RAISED)
            leg.get_frame().set_edgecolor(_BORDER)
            for txt in leg.get_texts():
                txt.set_color(_TEXT2)
            _dark_ax(ax)

            # ── Subplot (b): ALS Convergence ──────────────────────────────
            ax = axs[1]
            if hasattr(data, "baseline_iterations") and data.baseline_iterations:
                baseline_matrix = np.array(data.baseline_iterations)
                im = ax.imshow(
                    baseline_matrix, aspect="auto",
                    extent=[data.wavelength.min(), data.wavelength.max(),
                            1, len(data.baseline_iterations)],
                    origin="lower", cmap="plasma",
                )
                iters = [0,
                         len(data.baseline_iterations) // 3,
                         2 * len(data.baseline_iterations) // 3,
                         len(data.baseline_iterations) - 1]
                colours = ["white", "yellow", "cyan", "red"]
                for i, c in zip(iters, colours):
                    if i < len(data.baseline_iterations):
                        norm = (data.baseline_iterations[i] /
                                np.max(data.baseline_iterations[i]) *
                                len(data.baseline_iterations))
                        ax.plot(data.wavelength, norm,
                                linestyle="--", linewidth=1.2,
                                color=c, label=f"Iter {i+1}")
                cb = fig.colorbar(im, ax=ax)
                cb.ax.tick_params(colors=_TEXT2, labelsize=8)
                cb.set_label("Baseline Intensity", color=_TEXT2, fontsize=9)
                leg2 = ax.legend(title="Iterations", fontsize=8, framealpha=0.7)
                leg2.get_frame().set_facecolor(_BG_RAISED)
                leg2.get_frame().set_edgecolor(_BORDER)
                for txt in leg2.get_texts():
                    txt.set_color(_TEXT2)
            ax.set_title("(b) ALS Iterative Baseline Convergence",
                         fontsize=11, fontweight="bold")
            ax.set_xlabel("Wavelength (nm)", fontsize=10)
            ax.set_ylabel("Iteration", fontsize=10)
            _dark_ax(ax)

            fig.tight_layout(pad=1.5)
            fig.savefig(filepath, dpi=self.dpi, facecolor=_BG_BASE,
                        format=self.fmt)
            logger.info(f"Saved baseline correction plot to: {filepath}")
            plt.close(fig)

            return Path(filepath)

        except Exception as e:
            logger.error(f"Failed to generate baseline plot: {e}")
            raise FileIOError(f"Failed to save plot: {e}") from e
    
    def plot_step2_peaks(self, wavelength: np.ndarray,
                        intensity: np.ndarray,
                        peaks: List[DetectedPeak],
                        filepath: str = None) -> Path:
        """Generate Step 2 peaks detection plot — dark theme, consistent with UI."""
        logger.info("Generating Step 2 peaks detection plot")

        # Dark palette (mirrors theme.py values)
        _BG_BASE    = "#141519"
        _BG_RAISED  = "#2F3443"
        _BORDER     = "#3A4055"
        _ACCENT     = "#3FA9F5"   # spectrum line  (blue)
        _WARN       = "#F4B942"   # peak markers   (amber)
        _TEXT       = "#F0F2F5"
        _TEXT2      = "#AEB7C4"

        try:
            if filepath is None:
                filepath = f"Automatic_peaks_identification.{self.fmt}"

            fig, ax = plt.subplots(figsize=(14, 6))

            # Dark figure/axes backgrounds
            fig.patch.set_facecolor(_BG_BASE)
            ax.set_facecolor(_BG_RAISED)

            # Spectrum
            ax.plot(wavelength, intensity,
                    color=_ACCENT, linewidth=1.0, alpha=0.92,
                    label="Corrected Spectrum")

            # Peak markers
            peak_wl  = np.array([p.wavelength for p in peaks])
            peak_int = np.array([p.intensity  for p in peaks])
            ax.scatter(peak_wl, peak_int,
                       color=_WARN, s=45, marker="x", linewidths=1.4,
                       zorder=3, label=f"Detected Peaks  (n={len(peaks)})")

            # Labels, ticks, grid
            ax.set_xlabel("Wavelength (nm)", fontsize=13, color=_TEXT2)
            ax.set_ylabel("Intensity",        fontsize=13, color=_TEXT2)
            ax.set_title("Peak Detection — LIBS Spectrum",
                         fontsize=14, fontweight="bold", color=_TEXT, pad=10)
            ax.tick_params(colors=_TEXT2, which="both", labelsize=11)
            for spine in ax.spines.values():
                spine.set_edgecolor(_BORDER)
                spine.set_linewidth(0.8)
            ax.grid(True, color=_BORDER, alpha=0.5, linewidth=0.5, linestyle="--")

            # Legend
            leg = ax.legend(fontsize=12, framealpha=0.7)
            leg.get_frame().set_facecolor(_BG_RAISED)
            leg.get_frame().set_edgecolor(_BORDER)
            for txt in leg.get_texts():
                txt.set_color(_TEXT2)

            fig.tight_layout(pad=1.5)
            fig.savefig(filepath, dpi=self.dpi, facecolor=_BG_BASE,
                        format=self.fmt)
            logger.info(f"Saved peaks detection plot to: {filepath}")
            plt.close(fig)

            return Path(filepath)

        except Exception as e:
            logger.error(f"Failed to generate peaks plot: {e}")
            raise FileIOError(f"Failed to save plot: {e}") from e
