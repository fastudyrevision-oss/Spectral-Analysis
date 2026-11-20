# -*- coding: utf-8 -*-
"""
Data Models for Spectral Analysis Software

Type-safe data structures using Python dataclasses.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
import numpy as np


@dataclass
class RawSpectra:
    """Raw spectral data from input file."""
    wavelength: np.ndarray          # nm, shape (n,)
    intensity: np.ndarray           # shape (n,)
    metadata: Dict = field(default_factory=dict)
    source_file: str = ""


@dataclass
class ProcessedSpectra:
    """Processed spectral data from Step 1."""
    wavelength: np.ndarray          # Original wavelength
    raw: np.ndarray                 # Original intensity
    smoothed_sg: np.ndarray         # After SG smoothing
    baseline_als: np.ndarray        # ALS baseline
    corrected: np.ndarray           # Raw - Baseline
    baseline_iterations: List[np.ndarray] = field(default_factory=list)


@dataclass
class DetectedPeak:
    """A detected spectral peak."""
    wavelength: float               # nm
    intensity: float


@dataclass
class NISTMatch:
    """NIST database match result."""
    observed_wl: float
    matched_wl: Optional[float]
    delta: Optional[float]          # Wavelength difference
    aki: float                      # Line strength
    relative_intensity: float
    score: float
    element: Optional[str]


@dataclass
class UPRSAPeak:
    """A single evaluated unassigned peak from UPRSA."""
    peak_id: int
    wavelength: float
    intensity: float
    local_background: float
    local_noise: float
    signal: float
    snr: float
    prominence: float
    spectrum_peak_wavelength: float
    local_points: int
    intensity_normalized: float
    snr_normalized: float
    prominence_normalized: float
    pqi: float
    decision: str                     # "Accepted" | "Rejected"
    interpretation: str               # e.g. "Suitable for secondary elemental identification"


@dataclass
class UPRSAResult:
    """Aggregated output from UPRSA analysis."""
    detected_count: int
    confirmed_count: int
    unassigned_count: int
    accepted_count: int
    rejected_count: int
    accepted_percentage: float
    rejected_percentage: float
    all_peaks: List[UPRSAPeak] = field(default_factory=list)
    accepted_peaks: List[UPRSAPeak] = field(default_factory=list)
    rejected_peaks: List[UPRSAPeak] = field(default_factory=list)
    df_all: Optional[object] = None       # pd.DataFrame
    df_accepted: Optional[object] = None  # pd.DataFrame
    df_rejected: Optional[object] = None  # pd.DataFrame
    df_summary: Optional[object] = None   # pd.DataFrame

