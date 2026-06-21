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
