# -*- coding: utf-8 -*-
"""
Configuration Management for Spectral Analysis Software

All tunable parameters are centralized here for easy configuration.
"""

# ==========================================
# STEP 1: SG-ALS BASELINE CORRECTION
# ==========================================
STEP1_PARAMS = {
    'LAMBDA': 1e5,              # Smoothness parameter (larger = smoother baseline)
    'P': 0.01,                  # Asymmetry parameter (lower = more asymmetric)
    'NITER': 10,                # Number of ALS iterations
    'WINDOW': 7,                # SG window size (must be odd)
    'POLY': 3,                  # SG polynomial degree
    'OFFSET': 4000,             # Visualization offset for display
    'PEAK_REGION': (548, 555),  # Visualization region
    'BACKGROUND_REGION': (560, 610),  # Background region
}

# ==========================================
# STEP 2: PEAKS DETECTION
# ==========================================
STEP2_PARAMS = {
    'HEIGHT_MULTIPLIER': 1.2,   # Peak height threshold = noise_level × multiplier
    'PROMINENCE': 0.01,         # Minimum peak prominence
    'BASELINE_WINDOW': 20,      # Local baseline filtering window
    'BASELINE_K': 2,            # K factor for noise-based threshold
}

# ==========================================
# STEP 3: NIST MATCHING
# ==========================================
STEP3_PARAMS = {
    'TOLERANCE': 0.2,           # Wavelength matching tolerance (nm)
    'MIN_SCORE_THRESHOLD': 0,   # Minimum score to report
}

# ==========================================
# STEP 4: ELEMENTAL PREFERENCES
# ==========================================
STEP4_PARAMS = {
    'MIN_SCORE': 0,             # Minimum score threshold for analysis
    # Note: confidence tier thresholds (High ≥10 wins, Medium 3–9, Low <3) are
    # implemented directly in PerformanceCalculator._classify_confidence_tier().
}

# ==========================================
# UPRSA: UNASSIGNED PEAK RECOVERY & ATTRIBUTION
# ==========================================
UPRSA_PARAMS = {
    'WAVELENGTH_TOLERANCE': 0.05,       # nm: tolerance for matching detected to confirmed
    'LOCAL_WINDOW': 2.0,                # nm: local spectral window for background & noise
    'PEAK_GUARD': 0.08,                 # nm: exclusion zone around peak for background
    'MIN_LOCAL_POINTS': 5,              # minimum data points in local background window
    'WEIGHT_INTENSITY': 0.30,           # PQI weight for normalized intensity
    'WEIGHT_SNR': 0.40,                 # PQI weight for normalized SNR
    'WEIGHT_PROMINENCE': 0.30,          # PQI weight for normalized prominence
    'ACCEPTANCE_THRESHOLD': 0.60,       # PQI threshold: >= 0.60 accepted, < 0.60 rejected
    'CONTINUOUS_PEAK_TOLERANCE': 0.15,  # nm: tolerance for matching continuous spectrum peak
    'NUMBER_OF_REJECTED_TO_PLOT': 20,   # number of representative rejected peaks to plot
    'PROFILE_HALF_WIDTH': 2.0,          # nm: half-width for line profile inspection
    'NOISE_MULTIPLIER': 1.0,            # noise band multiplier (background +/- multiplier * noise)
}

# ==========================================
# STEP 5: VALIDATION WITH REFERENCE SPECTRA
# ==========================================
STEP5_PARAMS = {
    'WINDOW': 0.5,              # Search window around each line (nm)
    'MIN_POINTS': 5,            # Minimum data points per region
    'INTERPOLATION_KIND': 'linear',  # 'linear' or 'cubic'
    'VC_THRESHOLD': 0.8,        # Validation coefficient threshold
}

# ==========================================
# OUTPUT FORMATTING
# ==========================================
OUTPUT_CONFIG = {
    'CSV_PRECISION': 12,        # Decimal places in CSV output
    'PLOT_DPI': 600,            # Resolution for PNG output
    'PLOT_FORMAT': 'png',       # Output image format
}

# ==========================================
# INPUT VALIDATION RANGES
# ==========================================
VALIDATION_CONFIG = {
    'MIN_DATA_POINTS': 100,
    'MIN_WAVELENGTH': 100,      # nm
    'MAX_WAVELENGTH': 2000,     # nm
    'MIN_INTENSITY': -1e6,      # Can be negative
    'MAX_INTENSITY': 1e6,
}

# ==========================================
# LOGGING
# ==========================================
LOGGING_CONFIG = {
    'LOG_LEVEL': 'INFO',        # DEBUG, INFO, WARNING, ERROR
    'LOG_FILE': 'spectral_analysis.log',
    'LOG_FORMAT': '[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
}
