# LIBS Spectral Analysis Software — Research Context
> Prepared for external AI-assisted research and advanced development planning.
> Use this document as the primary context when prompting Claude / ChatGPT for
> improvements, new features, or research directions.

---

## 1. What This Project Is

A **desktop scientific application** (Python + PyQt6, Windows-first) for the complete
analysis of **Laser-Induced Breakdown Spectroscopy (LIBS)** data. LIBS fires a
high-power laser pulse at a sample, generates a plasma plume, and captures the
resulting atomic emission spectrum. The spectrum identifies elements present in the
sample by matching observed emission lines to known atomic line databases (NIST).

The software automates the full identification pipeline in six sequential steps and
presents results in a GUI with live charts, exportable tables, and session persistence.

**Target users:** researchers and lab technicians analysing elemental composition of
solid/liquid samples via LIBS instruments.

---

## 2. Current Architecture

### 2.1 Repository Layout

```
SpectralAnalysisSoftware/
├── gui_launcher.py          ← entry point (python gui_launcher.py)
├── requirements.txt
├── LIBS_Analysis.spec       ← PyInstaller one-folder build config
├── libs_spectral_analysis_ci.iss  ← Inno Setup installer script
│
├── src/
│   ├── __init__.py          ← package-wide setup_logger, constants, exceptions
│   ├── config.py            ← ALL tunable algorithm parameters (single source of truth)
│   ├── exceptions.py        ← ProcessingError, DataValidationError, NISTMatchingError
│   │
│   ├── core/                ← 6 algorithm classes, one per step
│   │   ├── step1_sg_als.py          BaselineCorrection
│   │   ├── step2_peaks.py           PeaksDetector
│   │   ├── step3_nist_matching.py   NISTMatcher
│   │   ├── step4_elemental_preferences.py  ElementalPreferencesAnalyzer
│   │   ├── step5_validation.py      ValidationAnalyzer
│   │   └── step6_performance.py     PerformanceCalculator
│   │
│   ├── gui/                 ← PyQt6 widgets and presentation layer
│   │   ├── main_window.py   SpectralAnalysisApp  (QMainWindow, wires all steps)
│   │   ├── step1_widget.py … step6_widget.py
│   │   ├── summary_widget.py   Analysis Summary dashboard
│   │   ├── theme.py         dark/light stylesheets, colour constants
│   │   ├── charts.py        reusable Matplotlib-in-Qt chart helpers
│   │   ├── export_engine.py CSV / PNG / PDF export (reportlab for PDF)
│   │   ├── session_manager.py  pickle-based session persistence
│   │   └── gui_utils.py     NotesPanel, FileHistory, ThemeSwitchOverlay, dialogs
│   │
│   └── io/
│       ├── data_models.py   RawSpectra, ProcessedSpectra, DetectedPeak, NISTMatch
│       ├── file_reader.py   CSV/XLSX reader with flexible column detection
│       ├── file_writer.py   CSV writer with precision control
│       └── nist_loader.py   NISTDatabaseLoader — SQLite cache of NIST CSVs/XLSX
│
├── tests/                   ← pytest + hypothesis (property-based)
│   ├── conftest.py
│   ├── test_core.py
│   ├── test_io.py
│   ├── test_integration.py
│   ├── test_step6_performance.py
│   ├── test_step6_charts.py
│   ├── test_step6_widget.py
│   ├── test_export_step6.py
│   ├── test_step4_step5_bugs_exploration.py
│   └── test_step4_step5_preservation.py
│
├── NIST database/
│   ├── Neutral lines/   ← per-element CSV/XLSX  (e.g. "Fe I.csv")
│   └── Ionic lines/     ← per-element CSV/XLSX  (e.g. "Fe II.csv")
│
└── .github/workflows/build-installer.yml  ← CI: PyInstaller + Inno Setup → GitHub Release
```

### 2.2 Technology Stack

| Layer | Choice |
|---|---|
| Language | Python 3.13 |
| GUI | PyQt6 ≥ 6.3 |
| Numerics | NumPy, SciPy |
| Data | pandas |
| Plotting | Matplotlib (QtAgg backend, embedded) |
| PDF export | reportlab |
| DB / cache | SQLite (via stdlib `sqlite3`) |
| Testing | pytest, hypothesis |
| Packaging | PyInstaller 6 + Inno Setup 6 |
| CI | GitHub Actions (windows-latest) |

### 2.3 Data Flow

```
CSV/XLSX file
    │
    ▼
Step 1  BaselineCorrection           → ProcessedSpectra
  SG smoothing (scipy.savgol_filter)
  ALS baseline  (sparse least squares)
    │ auto-handoff via Qt signal
    ▼
Step 2  PeaksDetector                → list[DetectedPeak]
  Noise-adaptive threshold
  scipy.signal.find_peaks
  Local-baseline false-peak filter
    │ auto-handoff
    ▼
Step 3  NISTMatcher                  → list[NISTMatch]
  Wavelength window ± 0.2 nm
  Score = Aki × rel_intensity / (Δλ + ε)
  SQLite-cached NIST database (neutral + ionic lines)
    │ auto-handoff
    ▼
Step 4  ElementalPreferencesAnalyzer → dict (ranking_df, primary_element, …)
  Peak-wise competition: one winning element per peak
  Element ranking table (Wins, TotalScore columns)
  Confidence tier: High ≥10 wins, Medium 3–9, Low <3
    │ primary_element hint auto-forwarded
    ▼
Step 5  ValidationAnalyzer           → pd.DataFrame (Wavelength_nm, Validation_Coefficient)
  ±0.5 nm spectral window per target line
  Pearson correlation vs pure reference spectrum
  Tier: Excellent ≥0.90 | Good 0.70–0.89 | Moderate 0.50–0.69 | Weak <0.50
    │
    ▼
Step 6  PerformanceCalculator        → PerformanceResults TypedDict
  Accuracy  = elements_confirmed / elements_ranked  (element-level)
  Precision = stage4_validated / stage2_matched     (line-level)
  Recall    = stage5_confirmed / stage3_ranked      (line-level)
  F1        = harmonic mean(Precision, Recall)
  SBR       = mean(peak_intensities) / mean(background_intensities)
  Heatmap matrix: peaks × elements × VC values
    │
    ▼
Analysis Summary Dashboard
  Metric cards, mini-charts from all 5 steps, auto-conclusions paragraph
  Export: PNG / CSV / multi-page PDF
```

### 2.4 Key Data Models

```python
@dataclass
class ProcessedSpectra:
    wavelength: np.ndarray      # nm
    raw: np.ndarray
    smoothed_sg: np.ndarray
    baseline_als: np.ndarray
    corrected: np.ndarray
    baseline_iterations: list[np.ndarray]

@dataclass
class DetectedPeak:
    wavelength: float           # nm
    intensity: float
    prominence: float
    index: int

@dataclass
class NISTMatch:
    observed_wl: float          # detected peak wavelength
    matched_wl: float           # NIST reference wavelength
    element: str                # e.g. "Fe I", "Ca II"
    delta: float                # |observed - matched| nm
    score: float                # Aki × rel_int / (Δλ + ε)
    aki: float
    relative_intensity: float
```

### 2.5 Algorithm Formulae

**ALS baseline (iterative sparse):**
```
minimise  Σ wᵢ(yᵢ − zᵢ)² + λ · Σ (Δ²z)²
solved as (W + λ DᵀD) z = W y   (sparse O(N))
wᵢ = p if yᵢ > zᵢ else (1−p)
```
Default: λ=1×10⁵, p=0.01, 10 iterations, SG window=7 poly=3.

**NIST match score:**
```
Score = (Aki × relative_intensity) / (|Δλ| + 1×10⁻⁶)
```
Only lines with Aki ≥ 1×10⁶ s⁻¹ are eligible.

**Pearson Validation Coefficient:**
```
VC = Pearson(normalised_processed_region, interpolated_reference_region)
     over ±0.5 nm window around each target wavelength
```

**Performance metrics:**
```
Accuracy  = elements_confirmed / elements_ranked
Precision = peaks_VC≥0.50 / peaks_NIST_matched
Recall    = peaks_VC≥0.70 / peaks_ranked
F1        = 2·P·R / (P+R)
SBR       = mean(intensities at confirmed peak positions) /
             mean(intensities at non-peak positions)
```

---

## 3. Current State — What Works Well

1. **Complete end-to-end pipeline** — data enters at Step 1 and classification metrics exit at Step 6 with zero manual hand-offs between steps.
2. **Robust NIST loader** — SQLite cache with auto-rebuild on file change; handles 10+ column-naming variants and typos in source files; supports neutral and ionic lines separately.
3. **Session persistence** — all step results serialised to `.session/` on completion and restored silently on next launch.
4. **Export** — per-step CSV, PNG, PDF. Analysis Summary exports 7 charts as individual PNGs or a multi-page dark-themed PDF (reportlab).
5. **Dark / light theme** — animated overlay during switch; all embedded Matplotlib charts re-style reactively.
6. **Test coverage** — ~10 test files covering core algorithms with both unit tests and property-based hypothesis tests; `.coverage` present.
7. **CI/CD** — GitHub Actions builds a signed Windows installer (Inno Setup) and a portable ZIP on every tag push; artifacts uploaded to GitHub Releases.
8. **Defensive error handling** — every `PerformanceCalculator` helper is wrapped in try/except so a failure in one metric never crashes the entire Step 6 computation.
9. **Auto-handoff** — Qt signals carry data objects in-memory between steps (no file round-trip), with status-bar notifications.

---

## 4. Current Limitations and Weaknesses

### 4.1 Science / Algorithm

| Limitation | Impact |
|---|---|
| Single spectrum only — no batch mode | Cannot compare multiple shots or average replicate spectra |
| No concentration quantification | Cannot produce wt% or ppm results — output is qualitative identification only |
| No plasma temperature / electron density | Cannot compute Boltzmann temperature or Stark electron density, limiting scientific depth |
| NIST scoring is heuristic | Score = Aki × rel_int / Δλ is physically motivated but not a likelihood; no Bayesian treatment |
| Validation is Pearson only | VC does not account for wavelength shift or intensity scaling differences |
| ALS assumes smooth baseline | Fails on spectra with sharp self-absorption dips or very uneven continuum |
| Step 5 reference spectra must be provided manually | No built-in reference library; user must supply CSVs |
| Confidence tiers are hard-coded thresholds | `High ≥10 wins` is arbitrary; no data-driven calibration |
| F1 / Precision / Recall use different denominators | This is intentional but non-standard; may confuse domain experts expecting all-elements F1 |

### 4.2 Software / Engineering

| Limitation | Impact |
|---|---|
| Windows-only CI packaging | macOS and Linux users must run from source; no `.dmg` or `AppImage` |
| No hardware interface | Cannot connect directly to spectrometer (e.g. Ocean Optics, Andor) |
| Session uses pickle | Pickle is not portable across Python versions |
| No undo / redo on parameter changes | Re-running a step is the only way to recover from a bad parameter |
| No project file format | Cannot save/open an entire analysis as a single file |
| GUI tests require display | Step 6 widget tests likely fail in headless CI without a virtual framebuffer |
| No async cancellation on long jobs | Worker threads cannot be cancelled mid-run |
| NIST database files not version-controlled | If NIST data updates, cache invalidation is file-mtime based only |

---

## 5. Potential Improvements

### 5.1 Near-term (algorithmic / low effort)

- **Multi-shot averaging** — accept N spectra, align by cross-correlation, average before Step 1.
- **Spectral calibration** — pixel-to-nm wavelength calibration using known emission lines (Ne/Ar lamp).
- **Savitzky-Golay window auto-selection** — use AIC/BIC or cross-validation to pick the optimal window length instead of a fixed value.
- **Lorentzian / Voigt peak fitting** — replace centroid-based detection with curve fitting to extract FWHM, area, and line shift.
- **Deconvolution of overlapping peaks** — multi-Gaussian / multi-Voigt fitting for blended lines.
- **Spectral range cropping UI** — let users mask out detector artefacts or atmospheric absorption bands before Step 1.

### 5.2 Medium-term (new analytical capabilities)

- **Concentration quantification**
  - Calibration Curve (univariate) — build intensity vs. concentration from standards
  - PLS / PCR multivariate calibration (scikit-learn)
  - Calibration-Free LIBS (CF-LIBS) — requires plasma temperature from Boltzmann plot
- **Boltzmann temperature** — log-linear plot of ln(I·λ/Aki·gk) vs Ek for multi-line elements
- **Electron density (Stark broadening)** — fit Lorentzian to Hα 656.3 nm or Hβ 486.1 nm
- **Machine-learning element classifier** — XGBoost / random forest trained on Aki, Δλ, intensity, prominence, FWHM features; replace or augment current scoring
- **Spectral library matching** — DTW or cosine similarity against a reference spectrum library instead of line-by-line matching

### 5.3 Software engineering

- **Replace pickle session with JSON / HDF5** — portable, inspectable, version-safe
- **Batch/headless processing mode** — CLI: `python -m libs_analysis --input dir/ --output results/`
- **Project file (.libsproj)** — ZIP containing spectra, NIST selection, parameters, results; fully reproducible
- **Async cancellation** — expose a `CancellationToken` to worker threads; connect a Cancel button in every step widget
- **Undo / redo** — command pattern on parameter changes
- **macOS / Linux packaging** — add `pyinstaller --target-arch universal2` job to CI; `.dmg` via `create-dmg`, AppImage via `appimage-builder`
- **Hardware integration** — Ocean Optics (seabreeze), Andor (pyandor), or generic OceanDirect SDK via plugin interface
- **Proper test isolation** — mock Qt display in CI; use `pytest-qt` with `QApplication` fixture

### 5.4 Research directions

- **Transfer learning** — fine-tune a 1-D CNN (e.g. ResNet-1D) on LIBS spectra for element presence/absence classification; train on NIST synthetic spectra + noise augmentation
- **Uncertainty quantification** — propagate shot noise and detector noise through the pipeline; report confidence intervals on VC and metrics
- **Self-supervised pre-training** — mask random spectral regions and train a transformer to reconstruct them; use learned embeddings for downstream element ID
- **Matrix effects correction** — model plasma-matrix interactions (self-absorption, inter-element interference) using neural networks trained on certified reference materials
- **Online / incremental learning** — update the model as the user confirms or rejects identifications (active learning loop)
- **Explainability** — SHAP or LIME on the element classifier to show which spectral features drove each identification

---

## 6. Key Parameters (from `src/config.py`)

```python
STEP1_PARAMS = {
    'LAMBDA': 1e5,     # ALS smoothness — increase for flatter baseline
    'P': 0.01,         # ALS asymmetry — lower pushes baseline below peaks
    'NITER': 10,       # ALS iterations
    'WINDOW': 7,       # SG window (must be odd)
    'POLY': 3,         # SG polynomial degree
}
STEP2_PARAMS = {
    'HEIGHT_MULTIPLIER': 1.2,   # threshold = noise × multiplier
    'PROMINENCE': 0.01,
    'BASELINE_WINDOW': 20,
    'BASELINE_K': 2,
}
STEP3_PARAMS = {
    'TOLERANCE': 0.2,           # nm — NIST match window
    'MIN_SCORE_THRESHOLD': 0,
}
STEP5_PARAMS = {
    'WINDOW': 0.5,              # nm — validation window per line
    'MIN_POINTS': 5,
    'VC_THRESHOLD': 0.8,
}
```

---

## 7. Test Infrastructure

- Framework: **pytest** with **hypothesis** (property-based)
- Coverage: `.coverage` file present; run `pytest --cov=src --cov-report=term-missing`
- Test files map 1-to-1 with source modules plus integration and bug-exploration suites
- Known gap: GUI widget tests (`test_step6_widget.py`) need a display; may fail headless

---

## 8. CI / Build Pipeline

Trigger: push to `main` (artifact only) | push `v*.*.*` tag (GitHub Release) | manual dispatch

Steps:
1. `actions/checkout@v4`
2. Python 3.13, pip cache keyed on `requirements.txt`
3. `pip install -r requirements.txt pyinstaller reportlab`
4. PyInstaller cache (keyed on spec + source hash) — reduces analysis phase ~8 min → ~2 min on hit
5. `pyinstaller LIBS_Analysis.spec`
6. Verify `.exe` exists
7. Install Inno Setup 6 via Chocolatey (cached)
8. `iscc libs_spectral_analysis_ci.iss` → `installer/*.exe`
9. Create portable `LIBS_Analysis_Portable.zip`
10. Upload installer + ZIP as artifacts (30-day retention)
11. On tag or manual: create GitHub Release with both files

---

## 9. Suggested Prompts for External AI Research Sessions

Use this file as attachment context, then ask:

**Algorithm improvements:**
> "Given the LIBS pipeline described in sections 2–3, design a Voigt peak-fitting module that can replace the current scipy.find_peaks centroid approach in Step 2. Provide Python code using scipy.optimize.curve_fit."

**ML integration:**
> "Design a scikit-learn / PyTorch classifier that replaces Step 3's heuristic NIST scoring. Input features: Δλ, Aki, relative_intensity, peak_prominence, peak_FWHM. Output: probability vector over element symbols. Suggest a training data generation strategy using the existing NIST database."

**Concentration quantification:**
> "Implement PLS-1 calibration for LIBS concentration prediction. Inputs: full corrected spectrum (wavelength × intensity vector). Output: predicted wt% for a target element. Show how to integrate this as a Step 7 widget in the existing PyQt6 architecture."

**Plasma diagnostics:**
> "Add Boltzmann-plot temperature calculation to the pipeline. Given a list of confirmed emission lines (wavelength, Aki, Ek, gk) from Step 3, compute the plasma temperature and its uncertainty. Show the maths and the Python implementation."

**Session / project file:**
> "Replace the current pickle-based session_manager.py with an HDF5-based project file (.libsproj). The file should store all step results (NumPy arrays, pandas DataFrames, Python dicts) in a portable, version-tagged format. Provide the new session_manager.py."

**Batch processing CLI:**
> "Design a headless CLI mode for this application: `python -m libs_analysis --input spectra/ --output results/ --config my_params.json`. It should run Steps 1–6 for every CSV in the input directory and write per-file result CSVs plus a summary CSV. Show the argument parser and main loop."

---

## 10. Dependency Versions (requirements.txt)

```
numpy>=1.21.0
pandas>=1.3.0
scipy>=1.7.0
matplotlib>=3.4.0
PyQt6>=6.3.0
reportlab>=3.6.0
pytest>=6.2.0
pytest-cov>=2.12.0
```

Runtime: Python 3.13 (pinned in CI). reportlab is optional (PDF export only).

---

*Document generated: 2026-10-25. Update this file whenever major architectural changes are made.*
