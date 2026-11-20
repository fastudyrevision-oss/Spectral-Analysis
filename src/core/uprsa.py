# -*- coding: utf-8 -*-
"""
UPRSA: Unassigned Peak Recovery and Spectral Attribution
src/core/uprsa.py

Implements two-category spectral feature screening for LIBS unassigned peaks:
- Category 1: Accepted (PQI >= 0.60) — suitable for secondary elemental identification
- Category 2: Rejected (PQI < 0.60) — insufficient spectral quality (noise/artifacts)

Directly follows the physical modeling and algorithm of unassigned_peaks_1.py.
"""

from __future__ import annotations

import re
from typing import List, Dict, Optional, Tuple, Union, Any
import numpy as np
import pandas as pd
from scipy.signal import find_peaks, peak_prominences

from src import setup_logger
from src.config import UPRSA_PARAMS
from src.exceptions import ProcessingError
from src.io.data_models import DetectedPeak, ProcessedSpectra, UPRSAPeak, UPRSAResult

logger = setup_logger(__name__)


def extract_numbers_from_string(value: Any) -> List[float]:
    """
    Extract all float numbers from a string or numeric cell.
    
    Example:
        'Al I | 257.51, 308.22, 309.27' -> [257.51, 308.22, 309.27]
    """
    if pd.isna(value):
        return []
    text = str(value)
    numbers = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)
    return [float(n) for n in numbers]


def find_wavelength_column(df: pd.DataFrame) -> Optional[str]:
    """Find wavelength column in DataFrame with flexible header detection."""
    columns = list(df.columns)
    preferred = [
        "Wavelength", "Wavelength (nm)", "wavelength", "wavelength (nm)",
        "Observed_Wavelength", "Matched_WL", "WL", "wl", "Lambda", "lambda",
    ]
    for name in preferred:
        if name in columns:
            return name

    for col in columns:
        clean = str(col).lower().replace(" ", "").replace("_", "")
        if "wavelength" in clean or clean in ("wl", "lambda") or "observedwl" in clean:
            return col
    return None


def find_intensity_column(df: pd.DataFrame) -> Optional[str]:
    """Find intensity column in DataFrame with flexible header detection."""
    columns = list(df.columns)
    preferred = [
        "Corrected", "corrected", "Intensity", "intensity",
        "Intensity (a.u.)", "Intensity (AU)", "Signal", "signal",
    ]
    for name in preferred:
        if name in columns:
            return name

    for col in columns:
        clean = str(col).lower().replace(" ", "").replace("_", "")
        if "correct" in clean or "intensity" in clean or "signal" in clean:
            return col
    return None


def normalize_positive_series(values: np.ndarray) -> np.ndarray:
    """Normalize non-negative 1D array to [0, 1] by its maximum."""
    clean = np.nan_to_num(values, nan=0.0)
    clean = np.clip(clean, 0.0, None)
    max_val = np.max(clean) if len(clean) > 0 else 0.0
    if max_val <= 0.0 or not np.isfinite(max_val):
        return np.zeros_like(clean, dtype=float)
    return clean / max_val


class UPRSAAnalyzer:
    """
    Core engine for Unassigned Peak Recovery and Spectral Attribution (UPRSA).
    
    Evaluates unassigned peaks using Peak Quality Index (PQI) derived from:
    - Guarded local background estimation (Median)
    - Robust local noise estimation (Median Absolute Deviation, MAD)
    - Local Signal-to-Noise Ratio (SNR)
    - Continuous-spectrum peak prominence via SciPy
    """

    def __init__(self, config: Optional[dict] = None):
        """
        Initialize UPRSA Analyzer with parameters.
        
        Parameters
        ----------
        config : dict, optional
            Configuration dictionary. If None, uses UPRSA_PARAMS from src/config.py.
        """
        cfg = config if config is not None else UPRSA_PARAMS
        self.wavelength_tolerance = float(cfg.get("WAVELENGTH_TOLERANCE", 0.05))
        self.local_window = float(cfg.get("LOCAL_WINDOW", 2.0))
        self.peak_guard = float(cfg.get("PEAK_GUARD", 0.08))
        self.min_local_points = int(cfg.get("MIN_LOCAL_POINTS", 5))
        self.weight_intensity = float(cfg.get("WEIGHT_INTENSITY", 0.30))
        self.weight_snr = float(cfg.get("WEIGHT_SNR", 0.40))
        self.weight_prominence = float(cfg.get("WEIGHT_PROMINENCE", 0.30))
        self.acceptance_threshold = float(cfg.get("ACCEPTANCE_THRESHOLD", 0.60))
        self.continuous_peak_tolerance = float(cfg.get("CONTINUOUS_PEAK_TOLERANCE", 0.15))

        logger.info(
            f"UPRSAAnalyzer initialized: tol={self.wavelength_tolerance} nm, "
            f"window=±{self.local_window} nm, guard=±{self.peak_guard} nm, "
            f"threshold={self.acceptance_threshold}"
        )

    def extract_confirmed_wavelengths(self, confirmed_input: Any) -> np.ndarray:
        """
        Extract unique float wavelengths from confirmed input.
        
        Handles:
        - List[float] / np.ndarray
        - pd.DataFrame (reads wavelength column or parses strings)
        - List[str] with comma-separated numbers
        """
        if confirmed_input is None:
            return np.array([], dtype=float)

        extracted: List[float] = []

        if isinstance(confirmed_input, (list, tuple, np.ndarray)):
            for item in confirmed_input:
                if isinstance(item, (int, float)):
                    if np.isfinite(item):
                        extracted.append(float(item))
                elif isinstance(item, str):
                    extracted.extend(extract_numbers_from_string(item))
        elif isinstance(confirmed_input, pd.DataFrame):
            if confirmed_input.empty:
                return np.array([], dtype=float)
            col = find_wavelength_column(confirmed_input)
            if col is not None:
                for val in confirmed_input[col]:
                    extracted.extend(extract_numbers_from_string(val))
            else:
                for c in confirmed_input.columns:
                    for val in confirmed_input[c]:
                        extracted.extend(extract_numbers_from_string(val))

        arr = np.array(extracted, dtype=float)
        arr = arr[np.isfinite(arr)]
        return np.unique(arr)

    def extract_detected_peaks(self, detected_input: Any) -> List[Tuple[float, float]]:
        """
        Extract (wavelength, intensity) pairs from detected peaks input.
        """
        if detected_input is None:
            return []

        peaks_list: List[Tuple[float, float]] = []

        if isinstance(detected_input, pd.DataFrame):
            wl_col = find_wavelength_column(detected_input)
            int_col = find_intensity_column(detected_input)
            if wl_col is None or int_col is None:
                raise ProcessingError("Detected peaks DataFrame must contain Wavelength and Intensity columns")
            for _, row in detected_input.iterrows():
                try:
                    w = float(row[wl_col])
                    i = float(row[int_col])
                    if np.isfinite(w) and np.isfinite(i):
                        peaks_list.append((w, i))
                except (ValueError, TypeError):
                    continue
        elif isinstance(detected_input, (list, tuple)):
            for p in detected_input:
                if isinstance(p, DetectedPeak):
                    peaks_list.append((float(p.wavelength), float(p.intensity)))
                elif isinstance(p, dict):
                    w = p.get("wavelength") or p.get("Wavelength") or p.get("Observed_WL")
                    i = p.get("intensity") or p.get("Intensity") or 0.0
                    if w is not None:
                        peaks_list.append((float(w), float(i)))
                elif isinstance(p, (list, tuple)) and len(p) >= 2:
                    peaks_list.append((float(p[0]), float(p[1])))

        # Sort by wavelength
        peaks_list.sort(key=lambda x: x[0])
        return peaks_list

    def filter_unassigned_peaks(
        self,
        detected_peaks: List[Tuple[float, float]],
        confirmed_wavelengths: np.ndarray,
        tolerance: Optional[float] = None
    ) -> List[Tuple[float, float]]:
        """
        Subtract confirmed wavelengths from detected peaks using tolerance.
        
        Returns
        -------
        List of (wavelength, intensity) tuples representing unassigned peaks.
        """
        tol = tolerance if tolerance is not None else self.wavelength_tolerance
        if len(confirmed_wavelengths) == 0:
            return list(detected_peaks)

        unassigned: List[Tuple[float, float]] = []
        for wl, intensity in detected_peaks:
            diffs = np.abs(confirmed_wavelengths - wl)
            nearest_diff = np.min(diffs)
            if nearest_diff > tol:
                unassigned.append((wl, intensity))

        logger.info(
            f"Filtered peaks: {len(detected_peaks)} detected - "
            f"{len(detected_peaks) - len(unassigned)} confirmed = "
            f"{len(unassigned)} unassigned (tol={tol} nm)"
        )
        return unassigned

    def find_continuous_spectrum_peaks(
        self,
        spectrum_wl: np.ndarray,
        spectrum_intensity: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Identify local maxima and prominences in the continuous processed spectrum.
        
        Returns
        -------
        Tuple of (peak_indices, peak_wavelengths, peak_prominences)
        """
        if len(spectrum_intensity) == 0:
            return np.array([], dtype=int), np.array([], dtype=float), np.array([], dtype=float)

        peak_indices, _ = find_peaks(spectrum_intensity, prominence=0)
        if len(peak_indices) > 0:
            prominences = peak_prominences(spectrum_intensity, peak_indices)[0]
            peak_wavelengths = spectrum_wl[peak_indices]
        else:
            prominences = np.array([], dtype=float)
            peak_wavelengths = np.array([], dtype=float)

        return peak_indices, peak_wavelengths, prominences

    def nearest_spectrum_peak(
        self,
        target_wl: float,
        continuous_indices: np.ndarray,
        continuous_wavelengths: np.ndarray,
        continuous_prominences: np.ndarray,
        tolerance: Optional[float] = None
    ) -> Optional[Dict[str, float]]:
        """Find the nearest continuous-spectrum peak within tolerance."""
        tol = tolerance if tolerance is not None else self.continuous_peak_tolerance
        if len(continuous_wavelengths) == 0:
            return None

        diffs = np.abs(continuous_wavelengths - target_wl)
        nearest_idx = int(np.argmin(diffs))

        if diffs[nearest_idx] <= tol:
            return {
                "index": int(continuous_indices[nearest_idx]),
                "wavelength": float(continuous_wavelengths[nearest_idx]),
                "prominence": float(continuous_prominences[nearest_idx]),
            }
        return None

    def analyze(
        self,
        processed_input: Union[ProcessedSpectra, pd.DataFrame, Tuple[np.ndarray, np.ndarray]],
        detected_input: Any,
        confirmed_input: Any = None,
    ) -> UPRSAResult:
        """
        Run the complete UPRSA evaluation on unassigned peaks.
        
        Parameters
        ----------
        processed_input : ProcessedSpectra, pd.DataFrame, or tuple of (wavelength, intensity)
            Processed spectrum data from Step 1.
        detected_input : List[DetectedPeak], pd.DataFrame, or list of tuples
            Detected spectral peaks from Step 2.
        confirmed_input : List[float], pd.DataFrame, or None
            Confirmed/assigned wavelengths from Step 4 (or Step 5).
            
        Returns
        -------
        UPRSAResult
            Result object containing categorized peaks, DataFrames, and summary statistics.
        """
        # 1. Parse processed spectrum arrays
        if isinstance(processed_input, ProcessedSpectra):
            spectrum_wl = np.asarray(processed_input.wavelength, dtype=float)
            spectrum_int = np.asarray(processed_input.corrected, dtype=float)
        elif isinstance(processed_input, pd.DataFrame):
            wl_col = find_wavelength_column(processed_input)
            int_col = find_intensity_column(processed_input)
            if wl_col is None or int_col is None:
                raise ProcessingError("Processed spectrum DataFrame must contain Wavelength and Intensity/Corrected columns")
            clean_df = processed_input.dropna(subset=[wl_col, int_col]).sort_values(wl_col)
            spectrum_wl = clean_df[wl_col].to_numpy(dtype=float)
            spectrum_int = clean_df[int_col].to_numpy(dtype=float)
        elif isinstance(processed_input, (tuple, list)) and len(processed_input) == 2:
            spectrum_wl = np.asarray(processed_input[0], dtype=float)
            spectrum_int = np.asarray(processed_input[1], dtype=float)
        else:
            raise ProcessingError(f"Unsupported processed spectrum input type: {type(processed_input)}")

        if len(spectrum_wl) < self.min_local_points:
            raise ProcessingError(f"Insufficient spectral points ({len(spectrum_wl)}) for UPRSA")

        # Sort spectrum by wavelength ascending
        sort_order = np.argsort(spectrum_wl)
        spectrum_wl = spectrum_wl[sort_order]
        spectrum_int = spectrum_int[sort_order]

        # 2. Parse detected peaks and confirmed wavelengths
        detected_peaks = self.extract_detected_peaks(detected_input)
        confirmed_wls = self.extract_confirmed_wavelengths(confirmed_input)

        # 3. Filter unassigned peaks
        unassigned_peaks = self.filter_unassigned_peaks(detected_peaks, confirmed_wls)

        detected_count = len(detected_peaks)
        confirmed_count = len(confirmed_wls)
        unassigned_count = len(unassigned_peaks)

        if unassigned_count == 0:
            logger.info("No unassigned peaks found to evaluate")
            empty_df = pd.DataFrame(columns=[
                "UPRSA_Peak_ID", "Wavelength", "Intensity", "Local_Background", "Local_Noise",
                "Signal", "SNR", "Prominence", "Intensity_Normalized", "SNR_Normalized",
                "Prominence_Normalized", "PQI", "Decision", "Interpretation",
            ])
            summary_df = pd.DataFrame({
                "Category": ["Detected peaks", "Confirmed peaks", "Unassigned peaks", "Accepted peaks", "Rejected peaks"],
                "Number": [detected_count, confirmed_count, 0, 0, 0],
            })
            return UPRSAResult(
                detected_count=detected_count,
                confirmed_count=confirmed_count,
                unassigned_count=0,
                accepted_count=0,
                rejected_count=0,
                accepted_percentage=0.0,
                rejected_percentage=0.0,
                all_peaks=[],
                accepted_peaks=[],
                rejected_peaks=[],
                df_all=empty_df,
                df_accepted=empty_df.copy(),
                df_rejected=empty_df.copy(),
                df_summary=summary_df,
            )

        # 4. Continuous-spectrum peak finding for prominence estimation
        cont_indices, cont_wls, cont_prominences = self.find_continuous_spectrum_peaks(
            spectrum_wl, spectrum_int
        )

        # 5. Evaluate local quality parameters for each unassigned peak
        raw_rows: List[Dict[str, Any]] = []

        for target_wl, detected_int in unassigned_peaks:
            # Find nearest wavelength index in spectrum
            target_idx = int(np.argmin(np.abs(spectrum_wl - target_wl)))
            observed_intensity = float(spectrum_int[target_idx])

            # Local spectral window
            local_mask = (
                (spectrum_wl >= target_wl - self.local_window) &
                (spectrum_wl <= target_wl + self.local_window)
            )
            local_wl = spectrum_wl[local_mask]
            local_intensity = spectrum_int[local_mask]

            # Peak guard region exclusion
            background_mask = np.abs(local_wl - target_wl) > self.peak_guard
            background_values = local_intensity[background_mask]

            if len(background_values) < self.min_local_points:
                background_values = local_intensity

            # Local background (median)
            local_background = float(np.median(background_values)) if len(background_values) > 0 else 0.0

            # Robust local noise (MAD * 1.4826)
            mad = float(np.median(np.abs(background_values - local_background))) if len(background_values) > 0 else 0.0
            local_noise = 1.4826 * mad

            if local_noise <= 0.0 or not np.isfinite(local_noise):
                if len(background_values) > 1:
                    local_noise = float(np.std(background_values, ddof=1))
                else:
                    local_noise = 1e-12

            if local_noise <= 0.0 or not np.isfinite(local_noise):
                local_noise = 1e-12

            # Signal & SNR
            signal = observed_intensity - local_background
            positive_signal = max(signal, 0.0)
            snr = positive_signal / (local_noise + 1e-12)

            # Continuous-spectrum prominence
            matched_peak = self.nearest_spectrum_peak(
                target_wl, cont_indices, cont_wls, cont_prominences
            )
            if matched_peak is not None:
                prominence = max(matched_peak["prominence"], 0.0)
                actual_peak_wl = matched_peak["wavelength"]
            else:
                prominence = max(positive_signal, 0.0)
                actual_peak_wl = target_wl

            raw_rows.append({
                "Wavelength": target_wl,
                "Intensity": observed_intensity,
                "Local_Background": local_background,
                "Local_Noise": local_noise,
                "Signal": positive_signal,
                "SNR": snr,
                "Prominence": prominence,
                "Spectrum_Peak_Wavelength": actual_peak_wl,
                "Local_Points": len(local_intensity),
            })

        df_quality = pd.DataFrame(raw_rows)

        # 6. Normalization
        df_quality["Intensity_Normalized"] = normalize_positive_series(df_quality["Intensity"].to_numpy())
        df_quality["SNR_Normalized"] = normalize_positive_series(df_quality["SNR"].to_numpy())
        df_quality["Prominence_Normalized"] = normalize_positive_series(df_quality["Prominence"].to_numpy())

        # 7. PQI calculation
        df_quality["Intensity_Contribution"] = self.weight_intensity * df_quality["Intensity_Normalized"]
        df_quality["SNR_Contribution"] = self.weight_snr * df_quality["SNR_Normalized"]
        df_quality["Prominence_Contribution"] = self.weight_prominence * df_quality["Prominence_Normalized"]
        df_quality["PQI"] = (
            df_quality["Intensity_Contribution"] +
            df_quality["SNR_Contribution"] +
            df_quality["Prominence_Contribution"]
        )

        # 8. Two-category decision
        df_quality["Decision"] = np.where(
            df_quality["PQI"] >= self.acceptance_threshold,
            "Accepted",
            "Rejected"
        )
        df_quality["Interpretation"] = np.where(
            df_quality["Decision"] == "Accepted",
            "Suitable for secondary elemental identification",
            "Insufficient spectral quality for further attribution"
        )

        # 9. Sort by PQI descending
        df_quality = df_quality.sort_values("PQI", ascending=False).reset_index(drop=True)
        df_quality.insert(0, "UPRSA_Peak_ID", np.arange(1, len(df_quality) + 1))

        # Split into accepted and rejected
        df_accepted = df_quality[df_quality["Decision"] == "Accepted"].copy().reset_index(drop=True)
        df_rejected = df_quality[df_quality["Decision"] == "Rejected"].copy().reset_index(drop=True)

        accepted_count = len(df_accepted)
        rejected_count = len(df_rejected)
        accepted_pct = (100.0 * accepted_count / unassigned_count) if unassigned_count > 0 else 0.0
        rejected_pct = (100.0 * rejected_count / unassigned_count) if unassigned_count > 0 else 0.0

        # Create UPRSAPeak object list
        all_peaks: List[UPRSAPeak] = []
        for _, row in df_quality.iterrows():
            all_peaks.append(UPRSAPeak(
                peak_id=int(row["UPRSA_Peak_ID"]),
                wavelength=float(row["Wavelength"]),
                intensity=float(row["Intensity"]),
                local_background=float(row["Local_Background"]),
                local_noise=float(row["Local_Noise"]),
                signal=float(row["Signal"]),
                snr=float(row["SNR"]),
                prominence=float(row["Prominence"]),
                spectrum_peak_wavelength=float(row["Spectrum_Peak_Wavelength"]),
                local_points=int(row["Local_Points"]),
                intensity_normalized=float(row["Intensity_Normalized"]),
                snr_normalized=float(row["SNR_Normalized"]),
                prominence_normalized=float(row["Prominence_Normalized"]),
                pqi=float(row["PQI"]),
                decision=str(row["Decision"]),
                interpretation=str(row["Interpretation"]),
            ))

        accepted_peaks = [p for p in all_peaks if p.decision == "Accepted"]
        rejected_peaks = [p for p in all_peaks if p.decision == "Rejected"]

        summary_df = pd.DataFrame({
            "Category": [
                "Detected peaks",
                "Confirmed peaks",
                "Unassigned peaks",
                "Accepted peaks",
                "Rejected peaks"
            ],
            "Number": [
                detected_count,
                confirmed_count,
                unassigned_count,
                accepted_count,
                rejected_count
            ]
        })

        logger.info(
            f"UPRSA completed: {unassigned_count} unassigned -> "
            f"{accepted_count} accepted ({accepted_pct:.1f}%), "
            f"{rejected_count} rejected ({rejected_pct:.1f}%)"
        )

        return UPRSAResult(
            detected_count=detected_count,
            confirmed_count=confirmed_count,
            unassigned_count=unassigned_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            accepted_percentage=accepted_pct,
            rejected_percentage=rejected_pct,
            all_peaks=all_peaks,
            accepted_peaks=accepted_peaks,
            rejected_peaks=rejected_peaks,
            df_all=df_quality,
            df_accepted=df_accepted,
            df_rejected=df_rejected,
            df_summary=summary_df,
        )
