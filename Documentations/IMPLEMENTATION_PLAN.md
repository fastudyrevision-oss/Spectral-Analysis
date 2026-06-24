# SPECTRAL ANALYSIS SOFTWARE - COMPLETE IMPLEMENTATION PLAN

## EXECUTIVE SUMMARY

Converting 3-step Google Colab spectral analysis pipeline into a production-grade desktop software with:
- **Step 1**: SG-ALS Spectral Processing (Baseline Correction)
- **Step 2**: Automatic Peaks Detection
- **Step 3**: NIST Database Matching & Element Identification

**Priority**: HIGH ACCURACY & CONSISTENCY - Zero compromise on precision

---

## PROJECT ARCHITECTURE

### Tech Stack
```
Backend:
  - Python 3.9+
  - sciPy (baseline correction, peak detection)
  - pandas (data handling, CSV I/O)
  - numpy (numerical operations)
  
Frontend:
  - PyQt6 or PySimpleGUI (desktop GUI)
  - matplotlib (scientific plotting)
  
Project Structure:
  - Core processing modules (logic isolation)
  - Input/Output handler (file management)
  - Configuration system (parameter management)
  - Error handling & validation layer
  - Logging system (audit trail)
  - Testing framework
```

---

## DETAILED IMPLEMENTATION PLAN

### PHASE 1: PROJECT SETUP & ARCHITECTURE (Week 1)

#### 1.1 Directory Structure
```
SpectralAnalysisSoftware/
├── src/
│   ├── __init__.py
│   ├── main.py                    # Application entry point
│   ├── config.py                  # Configuration management
│   ├── logger.py                  # Logging setup
│   ├── validators.py              # Input validation
│   ├── exceptions.py              # Custom exceptions
│   │
│   ├── core/                      # Processing logic
│   │   ├── __init__.py
│   │   ├── step1_sg_als.py        # Baseline correction
│   │   ├── step2_peaks.py         # Peak detection
│   │   └── step3_nist_matching.py # NIST matching
│   │
│   ├── io/                        # Input/Output handling
│   │   ├── __init__.py
│   │   ├── file_reader.py         # CSV reading with validation
│   │   ├── file_writer.py         # CSV writing with formatting
│   │   └── data_models.py         # Data structures (dataclasses)
│   │
│   ├── gui/                       # User interface
│   │   ├── __init__.py
│   │   ├── main_window.py         # Main application window
│   │   ├── step1_widget.py        # Step 1 UI
│   │   ├── step2_widget.py        # Step 2 UI
│   │   ├── step3_widget.py        # Step 3 UI
│   │   └── plots.py               # Plotting utilities
│   │
│   └── utils/                     # Helper functions
│       ├── __init__.py
│       └── file_utils.py          # File system utilities
│
├── tests/                         # Unit & integration tests
│   ├── __init__.py
│   ├── test_step1.py
│   ├── test_step2.py
│   ├── test_step3.py
│   ├── test_validators.py
│   └── test_io.py
│
├── data/                          # Sample data & NIST databases
│   ├── sample_inputs/
│   ├── nist_databases/
│   └── expected_outputs/
│
├── docs/                          # Documentation
│   ├── USAGE_GUIDE.md
│   ├── ALGORITHM_REFERENCE.md
│   └── API_REFERENCE.md
│
├── requirements.txt               # Python dependencies
├── setup.py                       # Package setup
├── .gitignore
└── README.md
```

#### 1.2 Configuration System
Create `config.py` with:
```python
# Parameters from original Colab (all parameterized)
STEP1_PARAMS = {
    'LAMBDA': 1e5,
    'P': 0.01,
    'NITER': 10,
    'WINDOW': 7,
    'POLY': 3,
    'OFFSET': 4000,
    'PEAK_REGION': (548, 555),
    'BACKGROUND_REGION': (560, 610)
}

STEP2_PARAMS = {
    'HEIGHT_MULTIPLIER': 1.2,  # Noise level multiplier
    'PROMINENCE': 0.01,
    'BASELINE_WINDOW': 20,
    'BASELINE_K': 2
}

STEP3_PARAMS = {
    'TOLERANCE': 0.2,  # nm
    'MIN_SCORE_THRESHOLD': 0  # Configurable cutoff
}

# Output formatting
OUTPUT_CONFIG = {
    'CSV_PRECISION': 12,
    'PLOT_DPI': 600,
    'PLOT_FORMAT': 'png'
}
```

#### 1.3 Data Models (Type Safety)
```python
# data_models.py
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class RawSpectra:
    wavelength: np.ndarray  # nm
    intensity: np.ndarray
    metadata: dict
    source_file: str
    
@dataclass
class ProcessedSpectra:
    wavelength: np.ndarray
    raw: np.ndarray
    smoothed_sg: np.ndarray
    baseline_als: np.ndarray
    corrected: np.ndarray
    baseline_iterations: List[np.ndarray]  # For visualization
    
@dataclass
class DetectedPeak:
    wavelength: float
    intensity: float
    
@dataclass
class NISTMatch:
    observed_wl: float
    matched_wl: Optional[float]
    delta: Optional[float]
    aki: float
    relative_intensity: float
    score: float
    element: Optional[str]
```

---

### PHASE 2: CORE PROCESSING MODULES (Week 2-3)

#### 2.1 Step 1: SG-ALS Baseline Correction
File: `src/core/step1_sg_als.py`

**Requirements**:
- Savitzky-Golay smoothing with configurable window & polynomial
- Asymmetric Least Squares (ALS) baseline correction
- Full precision preservation
- Error handling for edge cases
- Logging of all processing steps

**Implementation structure**:
```python
class BaselineCorrection:
    def __init__(self, config: dict):
        self.lambda_ = config['LAMBDA']
        self.p = config['P']
        self.n_iter = config['NITER']
        self.sg_window = config['WINDOW']
        self.sg_poly = config['POLY']
        self.logger = setup_logger('BaselineCorrection')
    
    def validate_input(self, wavelength, intensity):
        # Check data types, NaN values, ranges
        
    def apply_sg_smoothing(self, intensity):
        # Savitzky-Goyal smoothing
        
    def apply_als(self, smoothed_intensity):
        # ALS baseline correction with iteration tracking
        
    def process(self, wavelength, intensity) -> ProcessedSpectra:
        # Full pipeline with validation and logging
```

**Key Features**:
- Track baseline iterations for visualization
- Full numerical precision (float64)
- Comprehensive input validation
- Progress logging

---

#### 2.2 Step 2: Peaks Detection
File: `src/core/step2_peaks.py`

**Requirements**:
- Adaptive peak detection using scipy.signal.find_peaks
- Baseline filtering to remove noise-induced false peaks
- Configurable thresholds based on noise level
- Reproducible results

**Implementation structure**:
```python
class PeaksDetector:
    def __init__(self, config: dict):
        self.height_mult = config['HEIGHT_MULTIPLIER']
        self.prominence = config['PROMINENCE']
        self.baseline_window = config['BASELINE_WINDOW']
        self.baseline_k = config['BASELINE_K']
        self.logger = setup_logger('PeaksDetector')
    
    def calculate_noise_level(self, intensity):
        # Use first 10% of spectrum to estimate baseline noise
        
    def remove_baseline_peaks(self, intensity, peaks):
        # Filter peaks based on local baseline & noise
        
    def detect_peaks(self, wavelength, intensity) -> List[DetectedPeak]:
        # Full peak detection pipeline
```

**Key Features**:
- Adaptive height threshold (1.2 × noise level)
- Local baseline filtering
- Noise estimation from spectral region
- Peak validation

---

#### 2.3 Step 3: NIST Matching
File: `src/core/step3_nist_matching.py`

**Requirements**:
- Flexible NIST database column mapping (handles variations)
- Precise wavelength matching (±0.2 nm)
- Scoring algorithm based on Aki + relative_intensity
- Best match selection per detected peak
- Handling of multiple NIST databases

**Implementation structure**:
```python
class NISTMatcher:
    def __init__(self, config: dict):
        self.tolerance = config['TOLERANCE']
        self.logger = setup_logger('NISTMatcher')
    
    def load_nist_database(self, filepath) -> pd.DataFrame:
        # Load with flexible column mapping
        
    def detect_nist_columns(self, df):
        # Auto-detect wavelength, element, aki, relative_intensity columns
        
    def calculate_score(self, aki, relative_intensity, delta):
        # Score = (Aki × relative_intensity) / (delta + epsilon)
        
    def match_peaks(self, detected_peaks, nist_db) -> List[NISTMatch]:
        # Full matching pipeline with best match selection
        
    def match_multiple_databases(self, detected_peaks, nist_files) -> pd.DataFrame:
        # Combine multiple element databases with winner selection
```

**Key Features**:
- Flexible NIST database format support
- Robust column name detection
- Best match per peak
- Multi-database support
- Comprehensive scoring

---

### PHASE 3: INPUT/OUTPUT HANDLERS (Week 2)

#### 3.1 File Reader
File: `src/io/file_reader.py`

**Requirements**:
- Read CSV files with robust error handling
- Auto-detect delimiters (,, \t, ;)
- Handle different encoding (UTF-8, Latin-1)
- Column name standardization
- Data validation and sanity checks

**Features**:
```python
class CSVReader:
    def read_raw_spectra(self, filepath) -> RawSpectra:
        # Read wavelength + intensity
        # Validate: monotonic wavelength, numeric intensity
        
    def read_processed_spectra(self, filepath) -> ProcessedSpectra:
        # Read Step 1 output
        
    def read_detected_peaks(self, filepath) -> List[DetectedPeak]:
        # Read Step 2 output
        
    def read_nist_database(self, filepath) -> pd.DataFrame:
        # Read NIST database with flexible column mapping
```

#### 3.2 File Writer
File: `src/io/file_writer.py`

**Requirements**:
- Write CSV files with consistent formatting
- Preserve numerical precision (12+ decimal places)
- Add metadata headers
- Generate plots with high resolution
- Create reproducible outputs

**Features**:
```python
class CSVWriter:
    def write_processed_spectra(self, filepath, data: ProcessedSpectra):
        # Write Step 1 output with all columns
        
    def write_detected_peaks(self, filepath, peaks: List[DetectedPeak]):
        # Write Step 2 output
        
    def write_nist_matches(self, filepath, matches: List[NISTMatch]):
        # Write Step 3 output
        
class PlotGenerator:
    def plot_step1_results(self, data: ProcessedSpectra) -> Path:
        # Generate baseline separation & convergence plots
        
    def plot_step2_results(self, wavelength, intensity, peaks) -> Path:
        # Generate peaks detection plot
```

---

### PHASE 4: VALIDATION & ERROR HANDLING (Week 2)

#### 4.1 Input Validators
File: `src/validators.py`

**Validation Rules**:
```
1. Wavelength data:
   - Numeric values, no NaN/Inf
   - Monotonically increasing
   - Positive values (typically 200-1000 nm for LIBS)
   - Minimum 100 data points
   
2. Intensity data:
   - Numeric values
   - Same length as wavelength
   - Range check (typically 0-10000 for normalized)
   
3. NIST Database:
   - Must have wavelength column
   - Numeric wavelength values
   - Optional: Element, Aki, relative_intensity columns
   
4. Processing parameters:
   - LAMBDA: positive float (1e4 - 1e7 typical)
   - P: 0 < P < 1 (0.01 - 0.1 typical)
   - WINDOW: odd integer (5-21 typical)
```

#### 4.2 Exception Hierarchy
```python
class SpectralAnalysisError(Exception):
    """Base exception"""
    
class DataValidationError(SpectralAnalysisError):
    """Invalid input data"""
    
class ConfigurationError(SpectralAnalysisError):
    """Invalid parameters"""
    
class FileIOError(SpectralAnalysisError):
    """File read/write problems"""
    
class ProcessingError(SpectralAnalysisError):
    """Algorithm execution errors"""
```

---

### PHASE 5: LOGGING & AUDIT TRAIL (Week 2)

#### 5.1 Logging System
File: `src/logger.py`

**Requirements**:
- All operations logged with timestamp
- Separate log levels (DEBUG, INFO, WARNING, ERROR)
- File + console output
- Audit trail for reproducibility
- Performance metrics

**Log Structure**:
```
[2024-06-21 14:30:45.123] [INFO] SpectralAnalysis: Starting Step 1
[2024-06-21 14:30:45.234] [DEBUG] BaselineCorrection: Loaded 2048 data points
[2024-06-21 14:30:45.456] [DEBUG] BaselineCorrection: Parameters: LAMBDA=100000, P=0.01
[2024-06-21 14:30:46.789] [INFO] BaselineCorrection: SG smoothing completed (7-point window)
[2024-06-21 14:30:48.123] [INFO] BaselineCorrection: ALS baseline converged in 10 iterations
[2024-06-21 14:30:48.234] [INFO] Step 1 completed in 2.891 seconds
```

---

### PHASE 6: GUI IMPLEMENTATION (Week 3-4)

#### 6.1 Main Window Architecture
```
Main Application Window
├── Tab 1: Step 1 - Baseline Correction
│   ├── Input File Selection
│   ├── Parameter Controls (LAMBDA, P, NITER, WINDOW, POLY)
│   ├── Preview/Validation Panel
│   ├── Process Button
│   └── Output Visualization Panel
│
├── Tab 2: Step 2 - Peaks Detection
│   ├── Input File Selection (from Step 1 output)
│   ├── Parameter Controls (Height Multiplier, etc.)
│   ├── Preview Panel
│   ├── Process Button
│   └── Peaks List + Visualization
│
├── Tab 3: Step 3 - NIST Matching
│   ├── Detected Peaks File Selection
│   ├── NIST Database File Selection (multi-select)
│   ├── Parameter Controls (Tolerance)
│   ├── Process Button
│   └── Results Table (sortable, filterable)
│
├── Menu Bar
│   ├── File (Open, Save, Exit)
│   ├── Edit (Parameters, Preferences)
│   ├── Tools (Batch Processing, Database Manager)
│   └── Help (Documentation, About)
│
└── Status Bar (Progress, Logs)
```

#### 6.2 Key Features
- Real-time parameter preview
- Undo/Redo functionality
- Batch processing mode
- Result export to multiple formats
- Previous results history
- Parameter presets
- Progress bar with time estimation

---

### PHASE 7: TESTING & VALIDATION (Week 4)

#### 7.1 Test Suite Structure
```
Unit Tests:
  - test_validators.py (input validation)
  - test_step1.py (baseline correction algorithm)
  - test_step2.py (peaks detection algorithm)
  - test_step3.py (NIST matching algorithm)
  - test_io.py (file reading/writing)

Integration Tests:
  - test_pipeline_step1_2.py (Step 1 → Step 2)
  - test_pipeline_full.py (Step 1 → Step 2 → Step 3)

Data Tests:
  - Verify against original Colab outputs
  - Numerical precision comparison
  - Edge case handling
```

#### 7.2 Acceptance Criteria
```
Step 1:
  ✓ Output matches Colab baseline correction (< 0.01% error)
  ✓ Baseline convergence plot identical
  ✓ CSV output has 12+ decimal precision
  
Step 2:
  ✓ Detected peaks match Colab output (exact match)
  ✓ Peak filtering logic identical
  
Step 3:
  ✓ Matching results match Colab output (exact)
  ✓ Scoring algorithm identical
  ✓ NIST database handling robust
```

---

### PHASE 8: OPTIMIZATION & PACKAGING (Week 5)

#### 8.1 Performance Optimization
- NumPy vectorization (no Python loops)
- Cache NIST database in memory
- Lazy loading for large datasets
- Profiling to identify bottlenecks

#### 8.2 Packaging
```
Requirements:
  - Create requirements.txt with pinned versions
  - Create setup.py for installability
  - Generate executable (.exe for Windows)
  - Create installer with InnoSetup
```

---

## IMPLEMENTATION SEQUENCE

### Week 1: Foundation
1. Set up project structure ✓
2. Create data models ✓
3. Implement configuration system ✓
4. Setup logging ✓

### Week 2: Core Engines
1. Implement Step 1 (SG-ALS) ✓
2. Implement Step 2 (Peaks Detection) ✓
3. Implement Step 3 (NIST Matching) ✓
4. Create I/O handlers ✓
5. Implement validators ✓

### Week 3: GUI
1. Create main window ✓
2. Create Step 1 widget ✓
3. Create Step 2 widget ✓
4. Create Step 3 widget ✓

### Week 4: Testing & Refinement
1. Unit tests ✓
2. Integration tests ✓
3. Data accuracy verification ✓
4. Bug fixes & optimization ✓

### Week 5: Deployment
1. Performance optimization ✓
2. Documentation ✓
3. Packaging & distribution ✓

---

## KEY REQUIREMENTS FOR ACCURACY

1. **Precision**: All calculations in float64 (12+ decimal places)
2. **Validation**: Every input validated before processing
3. **Logging**: All operations logged for reproducibility
4. **Testing**: Outputs compared against Colab originals
5. **Versioning**: Parameter sets versioned for reproducibility
6. **Error Handling**: Graceful failures with clear error messages

---

## DEPLOYMENT DELIVERABLES

1. **Executable**: SpectralAnalysis.exe for Windows
2. **Documentation**: User guide, API reference, algorithm documentation
3. **Sample Data**: Test datasets with expected outputs
4. **Source Code**: Fully commented, well-structured Python code
5. **Installer**: Professional installer with shortcuts

---

## NEXT STEPS

1. **Ready to start?** Begin with Phase 1 (Project Setup)
2. **All phases implemented**, then proceed to testing
3. **Create GUI** once core engines are validated
4. **Package** for distribution

---

*Generated: 2024-06-21*
