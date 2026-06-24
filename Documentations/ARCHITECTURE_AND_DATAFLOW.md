# SPECTRAL ANALYSIS SOFTWARE - ARCHITECTURE & DATA FLOW

## SYSTEM ARCHITECTURE DIAGRAM

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SPECTRAL ANALYSIS SOFTWARE                       │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │                    GUI LAYER (PyQt6)                       │   │
│  │  ┌──────────────────────────────────────────────────────┐ │   │
│  │  │  Tabbed Interface                                   │ │   │
│  │  │  ├─ Step 1: SG-ALS Baseline Correction            │ │   │
│  │  │  ├─ Step 2: Automatic Peaks Detection             │ │   │
│  │  │  ├─ Step 3: NIST Element Identification           │ │   │
│  │  │  └─ Results & Analysis Dashboard                 │ │   │
│  │  └──────────────────────────────────────────────────────┘ │   │
│  └────────────────────────────────────────────────────────────┘   │
│                            │                                       │
│                            ▼                                       │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │              APPLICATION LOGIC LAYER                       │   │
│  │  ┌──────────────────────────────────────────────────────┐ │   │
│  │  │  Configuration Manager                              │ │   │
│  │  │  - Load/Save parameters                             │ │   │
│  │  │  - Preset management                                │ │   │
│  │  │  - Defaults                                         │ │   │
│  │  └──────────────────────────────────────────────────────┘ │   │
│  │  ┌──────────────────────────────────────────────────────┐ │   │
│  │  │  Orchestrator                                        │ │   │
│  │  │  - Pipeline execution                               │ │   │
│  │  │  - Step sequencing                                  │ │   │
│  │  │  - Error handling                                   │ │   │
│  │  └──────────────────────────────────────────────────────┘ │   │
│  └────────────────────────────────────────────────────────────┘   │
│                            │                                       │
│                            ▼                                       │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │              PROCESSING CORE LAYER                         │   │
│  │  ┌─────────────────┬──────────────────┬─────────────────┐ │   │
│  │  │  Step 1: SG-ALS │  Step 2: Peaks   │  Step 3: NIST   │ │   │
│  │  │  Baseline       │  Detection       │  Matching       │ │   │
│  │  │  Correction     │                  │                 │ │   │
│  │  │                 │                  │                 │ │   │
│  │  │  • SG Filter    │  • Noise Est.    │  • Col Detect   │ │   │
│  │  │  • ALS baseline │  • Find Peaks    │  • DB Loading   │ │   │
│  │  │  • Correction   │  • Baseline Filt │  • Matching     │ │   │
│  │  │  • Visualization│  • Validation    │  • Scoring      │ │   │
│  │  └─────────────────┴──────────────────┴─────────────────┘ │   │
│  └────────────────────────────────────────────────────────────┘   │
│                            │                                       │
│                            ▼                                       │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │              DATA I/O LAYER                                │   │
│  │  ┌──────────────────────────────────────────────────────┐ │   │
│  │  │  CSV Reader              │  CSV Writer               │ │   │
│  │  │  • Auto delimiter detect │  • Precision formatting   │ │   │
│  │  │  • Column mapping        │  • Metadata headers       │ │   │
│  │  │  • Data validation       │  • Reproducibility       │ │   │
│  │  │  • Error recovery        │                           │ │   │
│  │  └──────────────────────────────────────────────────────┘ │   │
│  │  ┌──────────────────────────────────────────────────────┐ │   │
│  │  │  Plot Generator                                      │ │   │
│  │  │  • High-resolution PNG (600 DPI)                     │ │   │
│  │  │  • Interactive matplotlib figures                    │ │   │
│  │  └──────────────────────────────────────────────────────┘ │   │
│  └────────────────────────────────────────────────────────────┘   │
│                            │                                       │
│                            ▼                                       │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │         UTILITIES & SUPPORT LAYER                          │   │
│  │  ┌──────────────┬──────────────┬──────────────────────┐   │   │
│  │  │  Validators  │  Logger      │  Error Handlers      │   │   │
│  │  │              │              │                      │   │   │
│  │  │  • Data      │  • File log  │  • Custom Exceptions │   │   │
│  │  │  • Param     │  • Console   │  • Graceful Failure  │   │   │
│  │  │  • Column    │  • Metrics   │  • User Messages     │   │   │
│  │  └──────────────┴──────────────┴──────────────────────┘   │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## DATA FLOW PIPELINE

### Complete 3-Step Pipeline

```
                    ┌─────────────────────────┐
                    │  User Input: Raw CSV    │
                    │  (Wavelength, Intensity)│
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   STEP 1: SG-ALS        │
                    │  Baseline Correction    │
                    └────────────┬────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
          ▼                      ▼                      ▼
    ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
    │  SG Smoothing│      │ ALS Baseline │      │  Validation  │
    │              │      │ Correction   │      │   & Logging  │
    │ • Window: 7  │      │              │      │              │
    │ • Poly: 3    │      │ • Iterations:10     │ • Precision  │
    │              │      │ • Lambda:1e5 │      │ • Range chk  │
    └──────────────┘      └──────────────┘      └──────────────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                ┌────────────────▼────────────────┐
                │  Output: Step 1 CSV + Plot      │
                │  • Wavelength                   │
                │  • Raw Intensity                │
                │  • Smoothed (SG)                │
                │  • Baseline (ALS)               │
                │  • Corrected Spectra            │
                │  • Baseline convergence plot    │
                └────────────────┬────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   STEP 2: Peak Detection│
                    │  (Optional Input: Step1 │
                    │   or User Spectra)      │
                    └────────────┬────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
          ▼                      ▼                      ▼
    ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
    │ Noise Level  │      │ Find Peaks   │      │ Baseline     │
    │ Estimation   │      │ (scipy)      │      │ Filtering    │
    │              │      │              │      │              │
    │ σ = 1.2×noise       │ Height:      │      │ • Window: 20 │
    │              │      │ 1.2×σ        │      │ • K: 2×noise │
    └──────────────┘      │ Prominence:  │      └──────────────┘
          │               │ 0.01         │            │
          └───────────────┼──────────────┼────────────┘
                          │
                ┌─────────▼────────┐
                │ Validation       │
                │ • Remove false   │
                │   peaks          │
                │ • Check ranges   │
                └────────┬─────────┘
                         │
                ┌────────▼────────────────────┐
                │  Output: Step 2 CSV + Plot  │
                │  • Detected Wavelengths     │
                │  • Detected Intensities     │
                │  • Peak identification plot │
                └────────┬────────────────────┘
                         │
                         ▼
          ┌─────────────────────────────────┐
          │  User Input: NIST Database(s)   │
          │  (Multiple element databases)   │
          └────────────┬────────────────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │   STEP 3: Matching   │
            │   NIST Identification│
            └────────────┬─────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │Load NIST │  │Auto-Detect│  │ Wavelength
    │Database  │  │Columns    │  │ Matching │
    │          │  │           │  │ (±0.2nm) │
    │• Element │  │• Wavelength   │
    │• Aki     │  │• Aki      │  │Tolerance │
    │• Rel Int │  │• Element  │  │
    └──────────┘  └──────────┘  └──────────┘
        │                │                │
        └────────────────┼────────────────┘
                         │
                ┌────────▼─────────┐
                │ Scoring Algorithm│
                │                  │
                │ Score = Aki ×    │
                │ relative_int /   │
                │ (Δλ + 1e-6)      │
                └────────┬─────────┘
                         │
                ┌────────▼──────────────────┐
                │ Select Best Match         │
                │ per Detected Peak         │
                │ (Highest score)           │
                └────────┬──────────────────┘
                         │
                ┌────────▼──────────────────┐
                │  Output: Step 3 CSV       │
                │  • Observed Wavelength    │
                │  • Matched Wavelength     │
                │  • Delta (Δλ)             │
                │  • Aki                    │
                │  • Relative Intensity     │
                │  • Score                  │
                │  • Element Identification │
                └───────────────────────────┘
```

---

## DATA STRUCTURE SPECIFICATIONS

### Step 1 Input Format
```
CSV File: soil3-unprocessed.csv
────────────────────────────────
wavelength (nm),intensity
228.96178,-0.6
229.01555,0.4
229.06931,0.4
...
```

### Step 1 Output Format
```
CSV File: SG_ALS_LIBS_processed.csv
────────────────────────────────────
Wavelength,Raw,Smoothed_SG,Baseline_ALS,Corrected
228.96178,-0.6,-0.980952381,-2.923647168,1.942694787
229.01555,0.4,1.280952381,-2.844261116,4.125213497
229.06931,0.4,0.566666667,-2.76487487,3.331541537
...

PNG File: SG_ALS_LIBS_processed.jpg
───────────────────────────────────
(a) Baseline Separation plot
(b) ALS Convergence heatmap with iteration overlays
```

### Step 2 Input Format
```
CSV File: SG_ALS_LIBS_processed (corrected data from Step 1)
Use either the "Corrected" column or raw intensity
```

### Step 2 Output Format
```
CSV File: detected_peaks.csv
──────────────────────────────
Wavelength (nm),Intensity
238.47412,68.87129423
249.22414,66.04516284
251.78087,126.8869723
...

PNG File: Automatic peaks identification.jpg
─────────────────────────────────────────────
Red spectrum curve with black scatter points at peaks
```

### Step 3 Input Formats
```
CSV File 1: detected_peaks.csv (from Step 2)
─────────────────────────────────────────────
Wavelength (nm),Intensity
238.47412,68.87129423
...

CSV File 2+: NIST-Ca.csv (or any element)
─────────────────────────────────────────
Column formats (auto-detected):
Option A: Wavelength, Aki, relative_intensity, element
Option B: wavelength, element, Aki
Option C: Other variations (detected automatically)
```

### Step 3 Output Format
```
CSV File: LIBS_matching_results.csv
───────────────────────────────────
Observed_WL,Matched_WL,Delta,Aki,relative_intensity,Score,Element
238.47412,238.505,0.033,1234.5,0.9,1099.15,Ca
249.22414,249.195,0.029,987.3,0.85,826.88,Ca
...
```

---

## ACCURACY & CONSISTENCY GUARANTEES

### Numerical Precision
```
Data Type: float64 (double precision)
Decimal Places: 12+ for all calculations
Output Format: CSV with .12e scientific notation when needed
Rounding: No rounding until final output (preserve intermediate precision)
```

### Consistency Measures
```
1. Validation:
   ✓ Input range checks
   ✓ Data type verification
   ✓ NaN/Inf detection
   ✓ Monotonicity checks for wavelength

2. Reproducibility:
   ✓ All parameters logged
   ✓ Seed for random operations (if any)
   ✓ Version tracking
   ✓ Timestamp on all outputs

3. Testing:
   ✓ Unit tests for each algorithm
   ✓ Integration tests for pipeline
   ✓ Data comparison against Colab originals
   ✓ Edge case handling

4. Error Handling:
   ✓ No silent failures
   ✓ Detailed error messages
   ✓ Log all exceptions
   ✓ Graceful degradation
```

---

## PROCESSING PARAMETERS & DEFAULTS

### Step 1: SG-ALS Baseline Correction
```
LAMBDA = 1e5              # Smoothness parameter (larger = smoother)
P = 0.01                  # Asymmetry parameter (lower = more asymmetric)
NITER = 10                # Iteration count (more = better convergence)
WINDOW = 7                # SG window (must be odd)
POLY = 3                  # SG polynomial degree
OFFSET = 4000             # Visualization offset
PEAK_REGION = (548, 555)  # For visualization
BACKGROUND_REGION = (560, 610)  # For visualization
```

### Step 2: Peak Detection
```
HEIGHT_MULTIPLIER = 1.2   # Threshold = noise_level × multiplier
PROMINENCE = 0.01         # Minimum peak prominence
BASELINE_WINDOW = 20      # Local baseline window
BASELINE_K = 2            # K factor for noise threshold
```

### Step 3: NIST Matching
```
TOLERANCE = 0.2           # Wavelength tolerance (nm)
MIN_SCORE_THRESHOLD = 0   # Minimum score to report
```

---

## GUI WORKFLOW

```
START
  │
  ├─ User launches application
  │
  ├─ Main window opens with 3 tabs
  │
  ├─ TAB 1: STEP 1 WORKFLOW
  │  │
  │  ├─ User clicks "Select Input File"
  │  ├─ File dialog opens
  │  ├─ User selects CSV file (wavelength, intensity)
  │  ├─ Preview shows first 100 data points
  │  ├─ Validation report displayed
  │  │
  │  ├─ User adjusts parameters (optional)
  │  │  └─ LAMBDA, P, NITER, WINDOW, POLY sliders
  │  │
  │  ├─ User clicks "Process"
  │  ├─ Progress bar shows execution
  │  ├─ Results displayed in plots
  │  ├─ User clicks "Save Results"
  │  │  └─ CSV + PNG files saved to output directory
  │  │
  │  └─ Proceed to Tab 2
  │
  ├─ TAB 2: STEP 2 WORKFLOW
  │  │
  │  ├─ Input automatically populated from Step 1 output (optional)
  │  ├─ Or user can select custom input
  │  ├─ Preview shown
  │  │
  │  ├─ User adjusts peak detection parameters
  │  │  └─ HEIGHT_MULTIPLIER, BASELINE_WINDOW sliders
  │  │
  │  ├─ User clicks "Detect Peaks"
  │  ├─ Detected peaks displayed in table + plot
  │  ├─ User can filter/review results
  │  ├─ User clicks "Save Results"
  │  │  └─ CSV + PNG files saved
  │  │
  │  └─ Proceed to Tab 3
  │
  ├─ TAB 3: STEP 3 WORKFLOW
  │  │
  │  ├─ Input automatically populated from Step 2 output
  │  ├─ User selects NIST database files (multi-select)
  │  ├─ Files validated and preview shown
  │  │
  │  ├─ User sets tolerance (default 0.2 nm)
  │  │
  │  ├─ User clicks "Match NIST"
  │  ├─ Matching executed
  │  ├─ Results table shows:
  │  │  • Observed wavelength
  │  │  • Matched wavelength
  │  │  • Delta
  │  │  • Score
  │  │  • Element identification
  │  │
  │  ├─ Table is sortable/filterable by element
  │  ├─ User can export results
  │  ├─ User clicks "Save Results"
  │  │  └─ CSV file saved
  │  │
  │  └─ Analysis complete
  │
  └─ EXIT

```

---

## ERROR HANDLING SCENARIOS

```
Scenario 1: Invalid Input File
  ├─ File not readable
  ├─ Action: Display error dialog
  ├─ Message: "Cannot read file: [reason]"
  └─ Log: Full exception traceback

Scenario 2: Missing Required Column
  ├─ CSV doesn't have "wavelength" or "intensity"
  ├─ Action: Display error
  ├─ Message: "CSV must contain 'wavelength (nm)' and 'intensity' columns"
  └─ Log: Column names found in file

Scenario 3: Invalid Parameter Values
  ├─ User enters WINDOW = 6 (must be odd)
  ├─ Action: Display validation error
  ├─ Message: "WINDOW must be odd number (7, 9, 11, ...)"
  └─ Log: Invalid parameter value

Scenario 4: Processing Failure
  ├─ Algorithm crashes during execution
  ├─ Action: Graceful error handling
  ├─ Message: "Processing failed: [reason]. See log file."
  └─ Log: Full traceback + input data summary

Scenario 5: Output Write Failure
  ├─ Cannot write to output directory
  ├─ Action: Suggest alternate directory
  ├─ Message: "Cannot write to [path]. Select another directory?"
  └─ Log: File system error details
```

---

## GENERATED OUTPUTS

### Step 1 Outputs
```
SG_ALS_LIBS_processed.csv
├─ Wavelength (original scale)
├─ Raw (input intensity)
├─ Smoothed_SG (after Savitzky-Golay)
├─ Baseline_ALS (computed baseline)
└─ Corrected (Raw - Baseline)

SG_ALS_LIBS_processed.jpg (600 DPI)
├─ Subplot (a): Baseline Separation
│  ├─ Raw spectra (offset)
│  ├─ SG smoothed
│  ├─ ALS baseline
│  └─ Corrected spectra
└─ Subplot (b): ALS Convergence Heatmap
   ├─ Baseline iterations as heatmap
   └─ 4 selected iterations overlaid
```

### Step 2 Outputs
```
detected_peaks.csv
├─ Wavelength (nm)
└─ Intensity

Automatic peaks identification.jpg (600 DPI)
├─ Full spectrum (red line)
└─ Detected peaks (black scatter)
```

### Step 3 Outputs
```
LIBS_matching_results.csv
├─ Observed_WL
├─ Matched_WL
├─ Delta (wavelength difference)
├─ Aki (line strength)
├─ relative_intensity
├─ Score (matching score)
└─ Element (identified element)
```

---

*This architecture ensures high accuracy, consistency, and reproducibility across all processing steps.*
