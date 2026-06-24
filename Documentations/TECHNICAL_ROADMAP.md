# SPECTRAL ANALYSIS SOFTWARE - TECHNICAL ROADMAP & CODING GUIDELINES

## PROJECT TIMELINE & MILESTONES

### PHASE 1: FOUNDATION & SETUP (Days 1-5)

#### Day 1-2: Project Structure & Configuration
- [ ] Create complete directory structure
- [ ] Initialize Git repository
- [ ] Create `requirements.txt` with dependencies:
  ```
  numpy>=1.21.0
  pandas>=1.3.0
  scipy>=1.7.0
  matplotlib>=3.4.0
  PyQt6>=6.3.0
  ```
- [ ] Create `config.py` with all parameters
- [ ] Create `.gitignore`

#### Day 3: Data Models & Exceptions
- [ ] Create `src/exceptions.py` with exception hierarchy
- [ ] Create `src/io/data_models.py` with dataclasses
- [ ] Create `src/logger.py` with logging configuration
- [ ] Create `src/validators.py` with validation rules

#### Day 4-5: Configuration & Utils
- [ ] Finalize `config.py` structure
- [ ] Create `src/utils/file_utils.py`
- [ ] Create test fixtures and sample data

**Deliverable**: Foundation ready for core algorithm implementation

---

### PHASE 2: CORE ALGORITHMS (Days 6-15)

#### Day 6-8: Step 1 - SG-ALS Baseline Correction
**File**: `src/core/step1_sg_als.py`

**Class Structure**:
```python
class BaselineCorrection:
    """
    Implements Savitzky-Golay smoothing and Asymmetric Least Squares (ALS)
    baseline correction for spectral data.
    """
    
    def __init__(self, config: dict):
        """Initialize with configuration parameters"""
        
    def validate_input(self, wavelength: np.ndarray, 
                      intensity: np.ndarray) -> bool:
        """
        Validate input data
        Returns: True if valid, raises exception if invalid
        """
        
    def apply_sg_smoothing(self, intensity: np.ndarray) -> np.ndarray:
        """
        Apply Savitzky-Golay filter
        Returns: Smoothed spectrum (float64)
        """
        
    def apply_als(self, smoothed: np.ndarray) -> tuple:
        """
        Apply ALS baseline correction with iteration tracking
        Returns: (baseline, baseline_iterations_list)
        """
        
    def process(self, wavelength: np.ndarray, 
               intensity: np.ndarray) -> ProcessedSpectra:
        """
        Full processing pipeline
        Returns: ProcessedSpectra dataclass
        """
```

**Key Requirements**:
```
✓ Input: wavelength (nm), intensity
✓ Process: SG Smoothing → ALS Baseline → Correction
✓ Output: ProcessedSpectra object with all intermediate data
✓ Precision: float64 throughout
✓ Logging: Log every major step
✓ Validation: Check ranges, NaN, monotonicity
✓ Error Handling: Raise DataValidationError if invalid
✓ Testing: Unit test against known results
```

**Algorithm Details**:
```python
# SG Smoothing
from scipy.signal import savgol_filter
smoothed = savgol_filter(intensity, WINDOW, POLY)

# ALS Baseline
from scipy import sparse
from scipy.sparse.linalg import spsolve

L = len(intensity)
D = sparse.diags([1, -2, 1], [0, -1, -2], shape=(L, L-2))
w = np.ones(L)
baselines = []

for i in range(NITER):
    W = sparse.diags(w, 0)
    Z = W + LAMBDA * D.dot(D.T)
    z = spsolve(Z, w * intensity)
    baselines.append(z.copy())
    w = P * (intensity > z) + (1 - P) * (intensity < z)

baseline = z
correction = intensity - baseline
```

---

#### Day 9-11: Step 2 - Peaks Detection
**File**: `src/core/step2_peaks.py`

**Class Structure**:
```python
class PeaksDetector:
    """
    Detects spectral peaks using scipy.signal.find_peaks with
    adaptive thresholding and baseline filtering.
    """
    
    def __init__(self, config: dict):
        """Initialize with configuration parameters"""
        
    def calculate_noise_level(self, intensity: np.ndarray) -> float:
        """
        Estimate noise level from first 10% of spectrum
        Returns: Noise level (float)
        """
        
    def remove_baseline_peaks(self, intensity: np.ndarray, 
                             peaks: np.ndarray) -> np.ndarray:
        """
        Filter peaks based on local baseline and noise level
        Returns: Filtered peak indices
        """
        
    def detect_peaks(self, wavelength: np.ndarray, 
                     intensity: np.ndarray) -> List[DetectedPeak]:
        """
        Full peak detection pipeline
        Returns: List of DetectedPeak objects
        """
```

**Algorithm Details**:
```python
from scipy.signal import find_peaks

# Estimate noise
noise = np.std(intensity[:int(len(intensity)*0.1)])
height = config['HEIGHT_MULTIPLIER'] * noise

# Find peaks
peaks, properties = find_peaks(intensity, 
                               height=height, 
                               prominence=config['PROMINENCE'])

# Baseline filtering
def remove_baseline_peaks(intensity, peaks, window=20, k=2):
    filtered = []
    for p in peaks:
        left = max(0, p - window)
        right = min(len(intensity), p + window)
        region = intensity[left:right]
        baseline = np.percentile(region, 50)
        noise = np.std(region)
        if intensity[p] > baseline + k * noise:
            filtered.append(p)
    return np.array(filtered)

filtered_peaks = remove_baseline_peaks(intensity, peaks)
```

**Key Requirements**:
```
✓ Adaptive threshold based on noise estimation
✓ Baseline filtering to remove false peaks
✓ Preserve original wavelength-peak correspondence
✓ Return List[DetectedPeak] with wavelength & intensity
✓ Logging of peaks found and filtered
✓ Error handling for edge cases
```

---

#### Day 12-15: Step 3 - NIST Matching
**File**: `src/core/step3_nist_matching.py`

**Class Structure**:
```python
class NISTMatcher:
    """
    Matches detected peaks against NIST spectral databases
    with flexible column mapping and scoring algorithm.
    """
    
    def __init__(self, config: dict):
        """Initialize with configuration parameters"""
        
    def detect_column_names(self, df: pd.DataFrame) -> dict:
        """
        Auto-detect column names in NIST database
        Handles: Wavelength, Element, Aki, relative_intensity
        Returns: {'wavelength_col': '...', 'element_col': '...', ...}
        """
        
    def load_nist_database(self, filepath: str) -> pd.DataFrame:
        """
        Load and standardize NIST database
        Returns: DataFrame with columns: Wavelength, Element, Aki, relative_intensity
        """
        
    def calculate_score(self, aki: float, 
                       rel_int: float, 
                       delta: float) -> float:
        """
        Scoring formula: Score = (Aki × relative_intensity) / (Δλ + 1e-6)
        Returns: Score (float)
        """
        
    def match_peaks(self, detected_peaks: List[DetectedPeak], 
                   nist_df: pd.DataFrame) -> List[NISTMatch]:
        """
        Match each detected peak to best NIST entry
        Returns: List of NISTMatch objects with best matches
        """
        
    def match_multiple_databases(self, detected_peaks: List[DetectedPeak],
                                 nist_files: List[str]) -> pd.DataFrame:
        """
        Process multiple NIST databases and determine winner element
        Returns: DataFrame with combined results
        """
```

**Algorithm Details**:
```python
# Column detection (flexible)
possible_wl_cols = ["Wavelength", "wavelength", "Wavelength (nm)", "wl"]
possible_element_cols = ["element", "Element", "Ion"]
possible_aki_cols = ["Aki", "Intensity", "Strength", "aki"]
possible_rel_int = ["relative_intensity", "Rel_Int", "rel_int", "intensity"]

# Matching
tolerance = config['TOLERANCE']
for _, peak in detected_peaks:
    candidates = nist[np.abs(nist['Wavelength'] - peak.wavelength) <= tolerance]
    
    matches = []
    for _, row in candidates.iterrows():
        delta = abs(row['Wavelength'] - peak.wavelength)
        score = (row['Aki'] * row['relative_intensity']) / (delta + 1e-6)
        matches.append(NISTMatch(...))
    
    # Select best match (highest score)
    best = max(matches, key=lambda x: x.score)
    results.append(best)
```

**Key Requirements**:
```
✓ Auto-detect column names (handle variations)
✓ Support multiple NIST database formats
✓ Wavelength matching within tolerance (±0.2 nm)
✓ Scoring based on Aki × relative_intensity
✓ Best match selection per peak
✓ Element identification from multiple databases
✓ Robust error handling for missing columns
✓ Logging of match statistics
```

---

### PHASE 3: INPUT/OUTPUT HANDLERS (Days 16-20)

#### Day 16-17: File Reader
**File**: `src/io/file_reader.py`

**Class Structure**:
```python
class CSVReader:
    """
    Reads CSV files with robust validation and column detection
    """
    
    def __init__(self, auto_detect_delimiter: bool = True):
        pass
    
    def detect_delimiter(self, filepath: str) -> str:
        """Detect CSV delimiter (comma, tab, semicolon)"""
        
    def read_raw_spectra(self, filepath: str) -> RawSpectra:
        """Read raw spectrum (wavelength, intensity)"""
        
    def read_processed_spectra(self, filepath: str) -> ProcessedSpectra:
        """Read processed spectrum (from Step 1)"""
        
    def read_detected_peaks(self, filepath: str) -> List[DetectedPeak]:
        """Read detected peaks (from Step 2)"""
        
    def read_nist_database(self, filepath: str) -> pd.DataFrame:
        """Read NIST database with flexible columns"""
```

**Requirements**:
```
✓ Handle multiple delimiters (auto-detect)
✓ Handle encodings (UTF-8, Latin-1)
✓ Column name standardization
✓ Data validation and type checking
✓ Preserve full precision (float64)
✓ Handle missing values appropriately
✓ Return type-safe objects (RawSpectra, ProcessedSpectra, etc.)
✓ Detailed error messages if file invalid
```

#### Day 18-19: File Writer & Plot Generator
**File**: `src/io/file_writer.py`

**Class Structure**:
```python
class CSVWriter:
    """Writes CSV output with consistent formatting"""
    
    def write_processed_spectra(self, filepath: str, 
                               data: ProcessedSpectra) -> None:
        """Write Step 1 output CSV"""
        
    def write_detected_peaks(self, filepath: str, 
                            peaks: List[DetectedPeak]) -> None:
        """Write Step 2 output CSV"""
        
    def write_nist_matches(self, filepath: str, 
                          matches: List[NISTMatch]) -> None:
        """Write Step 3 output CSV"""

class PlotGenerator:
    """Generates high-quality scientific plots"""
    
    def plot_step1_baseline_correction(self, data: ProcessedSpectra) -> Path:
        """Generate baseline correction plot (600 DPI PNG)"""
        
    def plot_step1_als_convergence(self, data: ProcessedSpectra) -> Path:
        """Generate ALS convergence heatmap"""
        
    def plot_step2_peaks_detection(self, wavelength: np.ndarray,
                                  intensity: np.ndarray,
                                  peaks: np.ndarray) -> Path:
        """Generate peaks detection plot"""
```

**Requirements**:
```
✓ CSV output with 12+ decimal precision
✓ Proper column headers and units
✓ Metadata comments in CSV (optional)
✓ High-resolution plots (600 DPI)
✓ Professional matplotlib styling
✓ Reproducible figure layouts
✓ PNG format output
✓ Include axis labels, titles, legends
✓ Grid and proper scaling
```

#### Day 20: Data Models Finalization
- [ ] Finalize all dataclasses
- [ ] Add validation methods to dataclasses
- [ ] Create factory methods for creation from raw data

---

### PHASE 4: GUI IMPLEMENTATION (Days 21-30)

#### Day 21-25: Main Application Window
**File**: `src/gui/main_window.py`

**Structure**:
```python
class MainWindow(QMainWindow):
    """
    Main application window with tabbed interface for 3 steps
    """
    
    def __init__(self):
        pass
    
    def create_menu_bar(self):
        """Create File, Edit, Tools, Help menus"""
        
    def create_tabs(self):
        """Create 3 main tabs for steps"""
        
    def create_status_bar(self):
        """Create status bar with progress"""
```

**Tabs to Implement**:
1. **Step 1 Tab** (`step1_widget.py`):
   - Input file selector
   - Parameter controls (sliders)
   - Preview panel
   - Process button
   - Results visualization

2. **Step 2 Tab** (`step2_widget.py`):
   - Input file selector (with Step 1 auto-link)
   - Parameter controls
   - Detected peaks table
   - Results visualization

3. **Step 3 Tab** (`step3_widget.py`):
   - Input files selector (multi-select for NIST)
   - Parameter controls
   - Results table (sortable, filterable)
   - Export options

#### Day 26-27: Plot Integration
**File**: `src/gui/plots.py`

```python
class PlotCanvas(FigureCanvas):
    """Matplotlib canvas embedded in PyQt6"""
    
    def plot_baseline_correction(self, data: ProcessedSpectra):
        pass
    
    def plot_peaks_detection(self, wavelength, intensity, peaks):
        pass
```

#### Day 28-30: Polish & Refinement
- [ ] Add progress bars
- [ ] Add file dialogs
- [ ] Add status messages
- [ ] Error dialog boxes
- [ ] Preferences dialog
- [ ] About dialog

---

### PHASE 5: TESTING & VALIDATION (Days 31-35)

#### Day 31-32: Unit Tests
**File**: `tests/test_*.py`

```
test_step1.py:
  - test_sg_smoothing()
  - test_als_baseline()
  - test_process_pipeline()
  - test_precision_preservation()

test_step2.py:
  - test_noise_estimation()
  - test_peak_detection()
  - test_baseline_filtering()

test_step3.py:
  - test_column_detection()
  - test_nist_matching()
  - test_scoring_algorithm()

test_validators.py:
  - test_wavelength_validation()
  - test_intensity_validation()
  - test_parameter_validation()

test_io.py:
  - test_csv_reader()
  - test_csv_writer()
  - test_plot_generation()
```

#### Day 33-34: Integration Tests
- [ ] Test Step 1 → Step 2 pipeline
- [ ] Test Step 2 → Step 3 pipeline
- [ ] Test full Step 1 → Step 2 → Step 3
- [ ] Compare outputs with Colab originals

#### Day 35: Accuracy Validation
- [ ] Verify numerical precision < 0.01% error vs. Colab
- [ ] Test edge cases and boundary conditions
- [ ] Performance profiling
- [ ] Memory usage optimization

---

### PHASE 6: DEPLOYMENT & DOCUMENTATION (Days 36-40)

#### Day 36: Documentation
- [ ] Write USAGE_GUIDE.md
- [ ] Write ALGORITHM_REFERENCE.md
- [ ] Write API_REFERENCE.md
- [ ] Create video tutorials (optional)

#### Day 37: Packaging
- [ ] Create setup.py
- [ ] Create requirements.txt with pinned versions
- [ ] Create Python wheel distribution

#### Day 38: Windows Executable
- [ ] Use PyInstaller to create .exe
- [ ] Create installer with InnoSetup
- [ ] Test on clean Windows system

#### Day 39-40: Final Testing & Release
- [ ] User acceptance testing
- [ ] Bug fixes
- [ ] Performance optimization
- [ ] Release preparation
- [ ] Create GitHub repository

---

## CODING STANDARDS & GUIDELINES

### Python Style (PEP 8)
```python
# Good
def calculate_baseline(intensity: np.ndarray, lambda_param: float) -> np.ndarray:
    """Calculate baseline using ALS algorithm."""
    pass

# Avoid
def calc_bl(i, l):
    pass
```

### Documentation
```python
def process_spectrum(wavelength: np.ndarray, 
                     intensity: np.ndarray,
                     config: dict) -> ProcessedSpectra:
    """
    Process raw spectrum through SG-ALS pipeline.
    
    Parameters
    ----------
    wavelength : np.ndarray
        Wavelength array in nm (shape: (n,))
    intensity : np.ndarray
        Intensity array (shape: (n,))
    config : dict
        Configuration with keys: LAMBDA, P, NITER, WINDOW, POLY
    
    Returns
    -------
    ProcessedSpectra
        Data object containing:
        - wavelength: Original wavelength
        - raw: Original intensity
        - smoothed_sg: SG smoothed
        - baseline_als: ALS baseline
        - corrected: Corrected spectra
        - baseline_iterations: List of baseline states per iteration
    
    Raises
    ------
    DataValidationError
        If wavelength or intensity arrays are invalid
    ProcessingError
        If algorithm fails to converge
    
    Notes
    -----
    All calculations performed in float64 for precision.
    Baseline iterations are tracked for visualization.
    
    Examples
    --------
    >>> wl = np.linspace(200, 1000, 1000)
    >>> intensity = np.random.rand(1000) * 1000
    >>> config = {...}
    >>> result = process_spectrum(wl, intensity, config)
    >>> print(result.corrected)
    """
```

### Error Handling
```python
# Good
try:
    baseline = compute_baseline(intensity, lambda_param)
except np.linalg.LinAlgError as e:
    logger.error(f"ALS matrix inversion failed: {e}")
    raise ProcessingError("Failed to compute baseline") from e

# Avoid
try:
    baseline = compute_baseline(intensity, lambda_param)
except:
    pass  # Silent failure
```

### Type Hints
```python
# Use everywhere
from typing import List, Dict, Optional, Tuple

def match_peaks(detected: List[DetectedPeak], 
               nist: pd.DataFrame,
               tolerance: float) -> List[NISTMatch]:
    pass

def load_config(filepath: Optional[str] = None) -> Dict[str, float]:
    pass
```

### Logging
```python
import logging

logger = logging.getLogger(__name__)

# Use appropriately
logger.debug("Processing 1024 data points")
logger.info("Baseline convergence achieved")
logger.warning("Peak intensity below threshold")
logger.error("Failed to read NIST database")
```

---

## TESTING TEMPLATE

```python
# tests/test_step1.py

import pytest
import numpy as np
from src.core.step1_sg_als import BaselineCorrection
from src.exceptions import DataValidationError

class TestBaselineCorrection:
    
    @pytest.fixture
    def config(self):
        return {
            'LAMBDA': 1e5,
            'P': 0.01,
            'NITER': 10,
            'WINDOW': 7,
            'POLY': 3
        }
    
    @pytest.fixture
    def sample_data(self):
        """Create realistic sample spectrum"""
        wl = np.linspace(200, 1000, 1024)
        intensity = 100 * np.sin(2 * np.pi * wl / 500) + 50
        return wl, intensity
    
    def test_process_returns_processed_spectra(self, config, sample_data):
        """Test that process returns correct type"""
        corrector = BaselineCorrection(config)
        result = corrector.process(*sample_data)
        
        assert result.wavelength.shape == sample_data[0].shape
        assert result.corrected.dtype == np.float64
        
    def test_invalid_wavelength_raises_error(self, config):
        """Test validation of invalid wavelength"""
        corrector = BaselineCorrection(config)
        
        invalid_wl = np.array([1000, 500, 200])  # Not increasing
        intensity = np.ones(3)
        
        with pytest.raises(DataValidationError):
            corrector.process(invalid_wl, intensity)
    
    def test_precision_preservation(self, config, sample_data):
        """Test numerical precision is preserved"""
        corrector = BaselineCorrection(config)
        result = corrector.process(*sample_data)
        
        # Verify float64 precision
        assert np.all(np.isfinite(result.corrected))
        assert result.corrected.dtype == np.float64
```

---

## GIT WORKFLOW

```bash
# Initial setup
git init
git add .
git commit -m "Initial project structure"
git branch -b develop

# Feature development
git checkout -b feature/step1-baseline
# ... make changes ...
git add src/core/step1_sg_als.py
git commit -m "Implement Step 1: SG-ALS baseline correction"
git push origin feature/step1-baseline

# Create pull request and review
# Merge to develop
git checkout develop
git merge feature/step1-baseline

# Final release
git checkout main
git merge develop
git tag v1.0.0
git push origin main
```

---

## PERFORMANCE TARGETS

```
Step 1 (SG-ALS):
  Input: 1024-2048 points
  Target time: < 500ms
  Memory: < 50MB

Step 2 (Peaks Detection):
  Input: 1024-2048 points
  Target time: < 200ms
  Memory: < 50MB

Step 3 (NIST Matching):
  Input: 50-500 peaks
  NIST database: 1000-10000 entries
  Target time: < 100ms
  Memory: < 100MB

Total 3-step pipeline: < 1 second
```

---

## ACCEPTANCE CRITERIA CHECKLIST

### Code Quality
- [ ] All code follows PEP 8 style
- [ ] All functions have docstrings
- [ ] All functions have type hints
- [ ] No code duplication
- [ ] Code coverage > 80%

### Functionality
- [ ] All 3 steps implemented
- [ ] GUI fully functional
- [ ] All parameters configurable
- [ ] Batch processing works
- [ ] History/undo works

### Accuracy
- [ ] Step 1 results match Colab (< 0.01% error)
- [ ] Step 2 peaks match Colab (exact)
- [ ] Step 3 matches match Colab (exact)
- [ ] 12+ decimal precision preserved
- [ ] Edge cases handled

### Testing
- [ ] Unit tests > 80% coverage
- [ ] Integration tests pass
- [ ] Data validation works
- [ ] Error handling complete
- [ ] Edge cases tested

### Documentation
- [ ] README.md complete
- [ ] USAGE_GUIDE.md complete
- [ ] API_REFERENCE.md complete
- [ ] Inline comments clear
- [ ] Example code provided

### Deployment
- [ ] Setup.py works
- [ ] Requirements.txt accurate
- [ ] .exe creation works
- [ ] Installer works
- [ ] No external dependencies

---

*This roadmap provides a complete step-by-step path to building the Spectral Analysis Software.*
