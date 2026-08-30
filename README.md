# LIBS Spectral Analysis Software

A desktop scientific application for end-to-end processing and interpretation of **Laser-Induced Breakdown Spectroscopy (LIBS)** data.

---

## What It Does

Raw LIBS spectra contain emission peaks buried under a broad fluorescence background. This software automates the full identification pipeline:

1. **Baseline Correction** — Savitzky-Golay smoothing + Asymmetric Least Squares (ALS) background removal
2. **Peak Detection** — Noise-adaptive thresholding with `scipy.signal.find_peaks`
3. **Element Identification** — Fuzzy matching against built-in NIST neutral/ionic line databases
4. **Elemental Preferences** — Peak-wise competition scoring to determine the primary element
5. **Validation** — Line-by-line Pearson correlation against pure-element reference spectra
6. **Model Performance** — Accuracy, Precision, Recall, F1-Score, and SBR improvement metrics

Results from each step are **automatically passed to the next step** in memory — no intermediate file saves required.

---

## Screenshots

| Dark Theme | Light Theme |
|-----------|------------|
| Step 1 — Baseline Correction | Analysis Summary Dashboard |

*(Screenshots can be found in `data/sample_outputs/`)*

---

## Quick Start

### Standalone EXE (Windows, no Python required)

```
dist/LIBS_Analysis/LIBS_Analysis.exe
```

Double-click to launch. No installation needed.

### From Source

**Requirements:** Python 3.11+, Windows / macOS / Linux

```bash
# 1. Clone
git clone <repository_url>
cd SpectralAnalysisSoftware

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Install reportlab for PDF export in Steps 5 & 6
pip install reportlab

# 5. Launch
python gui_launcher.py
```

---

## Usage — Recommended Workflow

The fastest way to run a full analysis is to let the auto-handoff system carry data between steps:

```
Step 1 → Process raw CSV
        ↓ (auto-loads into Step 2 and Step 5)
Step 2 → Detect peaks
        ↓ (auto-loads into Step 3)
Step 3 → Match against NIST database
        ↓ (auto-loads into Step 4)
Step 4 → Analyze elemental competition
        ↓ (primary element hint auto-loaded into Step 5)
Step 5 → Validate against reference spectra
        ↓
Step 6 → Model performance metrics  (auto-computed on tab switch)
        ↓
📊 Analysis Summary  (auto-refreshed on tab switch)
```

After each step completes, the status bar shows a confirmation, e.g.:
> `Step 1 done — Step 2 and Step 5 ready (data loaded)`

You can still use **Browse / Add File** buttons at any step to load data manually — this overrides the auto-loaded data for that step.

---

## Input File Format

Any CSV with at minimum two columns:

| Column name (case-insensitive) | Meaning |
|-------------------------------|---------|
| `Wavelength` / `wl` / `wavelength (nm)` | Wavelength in nm — must be monotonically increasing, 100–2000 nm |
| `Intensity` / `Signal` / `Counts` / `Data` | Raw signal counts |

Step 1's output CSV adds `Smoothed_SG`, `Baseline_ALS`, and `Corrected` columns. Step 2 uses the `Corrected` column automatically when it is present.

---

## Features

### Analysis Pipeline
- 5-tab parameter controls with live charts and interactive `NavigationToolbar` (zoom, pan, save)
- Paginated data tables on every step
- All heavy processing runs in background threads — UI stays responsive

### Step 3 — NIST Database
- Built-in Neutral Lines (I) and Ionic Lines (II) toggle buttons
- Searchable element checklists with Select All / None
- Optional custom CSV/XLSX database files
- Open Database Folder and Refresh buttons

### Step 5 — Validation
- Multi-file reference spectrum support (folder checklist + custom uploads)
- Wavelength entry via file (CSV/TXT) or "Enter Manually…" dialog
- **Clear** button to instantly reset the wavelength list
- Paginated spectral overlay grid with tier filter checkboxes (Excellent / Good / Moderate / Weak / Failed)

### Analysis Summary Dashboard
- Key metric cards: Detected Peaks, Identified Elements, Primary Element, Mean VC
- Mini-charts from all five steps
- Auto-generated conclusions paragraph
- **Export PNG** — saves all 7 charts as individual PNG files
- **Export CSV** — saves all tables and full DataFrames
- **Export PDF** — dark-themed multi-page PDF (cover + charts + conclusions, no extra dependencies)

### Export
- Per-step: CSV results, PNG charts, PDF reports (Steps 5 & 6 use reportlab; Summary uses matplotlib)
- All exports use timestamped filenames

### Session Persistence
- Results from Steps 2–5 are saved to `.session/*.csv` on completion
- Restored automatically on next launch — pick up where you left off

### Dark / Light Theme
- Toggle with the ☀ / 🌙 button in the status bar
- All charts and inline styles update reactively

---

## Project Structure

```
SpectralAnalysisSoftware/
├── gui_launcher.py          ← Entry point
├── requirements.txt
├── LIBS_Analysis.spec       ← PyInstaller build config
│
├── src/
│   ├── config.py            ← All algorithm parameters (edit here to tune)
│   ├── core/                ← Algorithm classes (Steps 1–6)
│   ├── gui/                 ← PyQt6 widgets, charts, export, session
│   └── io/                  ← CSV reader/writer, data models
│
├── tests/                   ← pytest test suite
├── data/
│   ├── nist_databases/      ← NIST reference CSVs (e.g. NIST-Ca.csv)
│   ├── sample_inputs/       ← Sample LIBS spectra
│   └── sample_outputs/
│
├── docs/
│   └── COMPLETE_DOCUMENTATION.md   ← Full technical reference
├── COMPLETE_DOCUMENTATION.md       ← Same file at repo root
└── .session/                ← Auto-generated session files
```

---

## Configuration

All algorithm parameters live in `src/config.py`. No code changes are needed for routine tuning:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `STEP1_PARAMS['LAMBDA']` | `1e5` | ALS smoothness — increase for a flatter baseline |
| `STEP1_PARAMS['P']` | `0.01` | ALS asymmetry — lower pushes baseline below peaks |
| `STEP2_PARAMS['HEIGHT_MULTIPLIER']` | `1.2` | Peak threshold multiplier relative to noise |
| `STEP3_PARAMS['TOLERANCE']` | `0.2` nm | NIST wavelength match window |
| `STEP5_PARAMS['WINDOW']` | `0.5` nm | Spectral region around each validation line |

---

## Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=src --cov-report=term-missing

# Fast tests only
pytest -m "not slow and not integration"
```

---

## Building the Standalone EXE

```bash
pip install pyinstaller
pyinstaller LIBS_Analysis.spec --clean
# Output: dist/LIBS_Analysis/LIBS_Analysis.exe
```

---

## Dependencies

| Library | Min version | Purpose |
|---------|------------|---------|
| Python | 3.11+ | Language runtime |
| PyQt6 | 6.3.0 | Desktop GUI |
| NumPy | 1.21.0 | Array operations |
| SciPy | 1.7.0 | SG filter, `find_peaks`, sparse solver, interpolation |
| pandas | 1.3.0 | DataFrame I/O and analysis |
| matplotlib | 3.4.0 | Embedded charts + export |
| reportlab | any *(optional)* | PDF reports for Steps 5 & 6 |
| pytest | 6.2.0 | Test framework |

---

## Technical Documentation

See [`COMPLETE_DOCUMENTATION.md`](COMPLETE_DOCUMENTATION.md) for:
- Full algorithm descriptions (SG, ALS, NIST scoring formula, Pearson VC, performance metrics)
- Class and function API reference
- UML diagrams, data flow, error handling strategy
- Developer guide for extending the pipeline
- Test suite documentation and spec traceability

---

## Algorithms at a Glance

**Baseline correction (ALS):**
```
minimise: Σ wᵢ(yᵢ - zᵢ)² + λ·Σ(Δ²z)²
solved as: (W + λ D^T D) z = W y   (sparse, O(N))
```

**NIST match scoring:**
```
Score = (Aki × rel_intensity) / (Δλ + 1e-6)
```
Only lines with Einstein A-coefficient ≥ 1×10⁶ s⁻¹ are eligible.

**Validation Coefficient:**
```
VC = Pearson correlation(normalised processed, interpolated reference)
     in ±0.5 nm window around each target wavelength
```

**Tier classification:**

| Tier | VC Range |
|------|---------|
| Excellent | ≥ 0.90 |
| Good | 0.70 – 0.89 |
| Moderate | 0.50 – 0.69 |
| Weak | < 0.50 |
| Failed | NaN (insufficient data) |

---

## License

Not specified. See repository owner for licensing terms.

---

## Acknowledgements

Built with [NumPy](https://numpy.org), [SciPy](https://scipy.org), [pandas](https://pandas.pydata.org), [matplotlib](https://matplotlib.org), [PyQt6](https://riverbankcomputing.com/software/pyqt/), and NIST Atomic Spectra Database reference data.
