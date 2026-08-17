# Step 7 — Quantitative Calibration Curve: Design

## 1. Architecture Overview

Step 7 follows the exact same layered pattern used for Steps 4–6:

```
┌──────────────────────────────────────────────────────────────┐
│  src/gui/step7_widget.py   (Step7Widget)                      │
│  ├── Left panel  : element selector, standards table, params  │
│  └── Right panel : 3 chart tabs + results summary             │
├──────────────────────────────────────────────────────────────┤
│  src/core/step7_calibration.py  (CalibrationEngine)           │
│  ├── Data model : CalibrationPoint, CalibrationResults        │
│  ├── Intensity extraction from spectrum at a given λ          │
│  ├── Curve fitting  (linear / quadratic / power_law)          │
│  ├── Inverse prediction  (concentration from intensity)       │
│  └── LOD / LOQ  (from blank noise or residual noise)          │
├──────────────────────────────────────────────────────────────┤
│  src/gui/charts.py          (ChartEngine — extended)          │
│  ├── render_calibration_curve(ax, ...)                        │
│  ├── render_calibration_residuals(ax, ...)                    │
│  └── render_lod_loq_panel(ax, ...)                            │
├──────────────────────────────────────────────────────────────┤
│  src/gui/export_engine.py   (extended)                        │
│  ├── export_step7_csv(results, filepath)                      │
│  ├── export_step7_png(figs, directory)                        │
│  └── generate_pdf_report() — Step 7 optional section added   │
├──────────────────────────────────────────────────────────────┤
│  src/gui/main_window.py     (updated)                         │
│  ├── Step7Widget inserted at tab index 6                      │
│  ├── Analysis Summary shifts to index 7                       │
│  └── apply_theme() loop includes step7_tab                    │
└──────────────────────────────────────────────────────────────┘
```

No new dependencies are required beyond what is already installed.
`scipy.optimize.curve_fit` ships with SciPy (already in requirements).

---

## 2. Data Models

### 2.1 `CalibrationPoint` (TypedDict)

Represents one standard sample with a known concentration and its
extracted intensity at the analytical wavelength.

```python
class CalibrationPoint(TypedDict):
    sample_id:      str            # e.g. "SRM-1a"
    concentration:  float          # known value in ppm
    spectrum_file:  str            # absolute path to the standard's processed CSV
    intensity:      float | None   # extracted at analytical_wavelength; None until extracted
    is_blank:       bool           # True if this standard is the zero-concentration blank
```

### 2.2 `FitResult` (TypedDict)

The output of a single curve_fit call.

```python
class FitResult(TypedDict):
    model:          str            # "linear" | "quadratic" | "power_law"
    coefficients:   list[float]    # [a, b] / [a, b, c] / [a, b]
    covariance:     list[list[float]]  # pcov from curve_fit (2D)
    r_squared:      float          # coefficient of determination [0, 1]
    rmse:           float          # root mean square error (same units as intensity)
    x_range:        tuple[float, float]  # (min_concentration, max_concentration) of standards
    fit_ok:         bool           # False if curve_fit raised RuntimeError
    error_message:  str | None     # populated when fit_ok is False
```

### 2.3 `CalibrationResults` (TypedDict)

The full output returned by `CalibrationEngine.fit_and_predict()`.

```python
class CalibrationResults(TypedDict):
    element:                str
    analytical_wavelength:  float          # nm
    extraction_tolerance:   float          # nm
    fit_result:             FitResult | None
    points:                 list[CalibrationPoint]
    unknown_intensity:      float | None   # from Step 1 processed spectrum
    unknown_concentration:  float | None   # inferred via inverse curve
    unknown_uncertainty:    float | None   # ±ppm (95 % CI, propagated from pcov)
    in_range:               bool           # unknown within calibration range
    lod_ppm:                float | None   # Limit of Detection
    loq_ppm:                float | None   # Limit of Quantification
    blank_noise:            float | None   # σ_blank at analytical wavelength
    missing_info:           list[str]      # reasons why result is incomplete
```

---

## 3. Core Module: `src/core/step7_calibration.py`

### 3.1 Class: `CalibrationEngine`

Stateless computation class — instantiate once per fit call.

#### 3.1.1 Fit model functions

Three static model functions, all of the form `f(x, *params) -> float`:

```python
@staticmethod
def _model_linear(x, a, b) -> float:
    """y = a*x + b"""

@staticmethod
def _model_quadratic(x, a, b, c) -> float:
    """y = a*x^2 + b*x + c"""

@staticmethod
def _model_power_law(x, a, b) -> float:
    """y = a * x^b   (requires x > 0, a > 0)"""
```

Model selector:

```python
_MODELS: dict[str, tuple[callable, int, list, list]] = {
    "linear":     (_model_linear,    2, [-np.inf, -np.inf], [np.inf, np.inf]),
    "quadratic":  (_model_quadratic, 3, [-np.inf, ...],     [np.inf, ...]),
    "power_law":  (_model_power_law, 2, [1e-12, 0.01],      [np.inf, 10.0]),
}
```

#### 3.1.2 `extract_intensity(spectrum_path, wavelength_nm, tolerance_nm) -> float | None`

- Reads the CSV at `spectrum_path` using `pd.read_csv` with column
  auto-detection (same logic as `CSVReader` in `file_reader.py`).
- Locates rows within `wavelength_nm ± tolerance_nm`.
- Returns the maximum intensity value in that window.
- Returns `None` if the file cannot be read or no row falls in the window.
- Wraps the entire body in `try/except Exception` — never raises.

#### 3.1.3 `compute_r_squared(y_actual, y_predicted) -> float`

```
SS_res = sum((y_actual - y_predicted)^2)
SS_tot = sum((y_actual - mean(y_actual))^2)
R² = 1 - SS_res / SS_tot    (clamped to [0, 1])
```

Returns 0.0 when SS_tot == 0.

#### 3.1.4 `fit_curve(concentrations, intensities, model) -> FitResult`

1. Validates: `len(concentrations) >= 3`, else raises `ValueError`.
2. Calls `scipy.optimize.curve_fit(model_fn, concentrations, intensities,
   p0=initial_guess, bounds=bounds, maxfev=10000)`.
3. On `RuntimeError` (convergence failure): returns `FitResult(fit_ok=False,
   error_message=str(e), ...)` with all numeric fields set to `None`.
4. On success: computes R², RMSE, returns `FitResult(fit_ok=True, ...)`.

#### 3.1.5 `predict_concentration(intensity, fit_result) -> tuple[float | None, float | None]`

Returns `(concentration_ppm, uncertainty_ppm)`.

- **Linear model inversion** (`y = a*x + b`):
  ```
  x = (y - b) / a
  dx/da = -(y - b) / a²    (partial derivative)
  dx/db = -1 / a
  Var(x) = (dx/da)² * Var(a) + (dx/db)² * Var(b) + 2*(dx/da)*(dx/db)*Cov(a,b)
  uncertainty = 1.96 * sqrt(Var(x))  — 95 % CI
  ```

- **Quadratic model inversion**: uses `numpy.roots` to find real positive root
  of `a*x² + b*x + (c - y_unknown) = 0`. Picks the root within `x_range`.
  Uncertainty computed via first-order error propagation with the 3×3 pcov.

- **Power-law inversion** (`y = a * x^b → x = (y/a)^(1/b)`):
  ```
  ln(x) = (ln(y) - ln(a)) / b
  Propagated via partial derivatives of ln(x) w.r.t. a and b.
  ```

- Returns `(None, None)` if the fit is not converged or arithmetic fails.

#### 3.1.6 `compute_lod_loq(blank_noise, fit_result) -> tuple[float | None, float | None]`

- **Linear model**: `LOD = 3 * blank_noise / a`, `LOQ = 10 * blank_noise / a`.
- **Quadratic/power-law**: solved numerically via `scipy.optimize.brentq` on
  `model(x) = k * blank_noise` for k=3 and k=10.
- Returns `(None, None)` when `blank_noise` is None or fit is not converged.

#### 3.1.7 `estimate_blank_noise(spectrum_path, wavelength_nm, tolerance_nm, window_nm) -> float | None`

- Reads the blank spectrum.
- Extracts intensity values in `wavelength_nm ± window_nm` (default 2 nm).
- Returns `std(intensities)` as σ_blank.
- Returns `None` on failure.

#### 3.1.8 `fit_and_predict(points, model_name, element, analytical_wavelength, extraction_tolerance, unknown_processed_data, blank_point) -> CalibrationResults`

Top-level method. Orchestrates:
1. Extract intensities for all non-blank points (calls `extract_intensity`).
2. Filter to points where `intensity is not None`.
3. If `< 3` valid points: return `CalibrationResults` with
   `missing_info=["Minimum 3 standards required"]`.
4. Call `fit_curve(concentrations, intensities, model_name)`.
5. Extract unknown intensity from `unknown_processed_data` (the Step 1
   `ProcessedSpectra` object already in memory — no file I/O).
6. Call `predict_concentration` if fit succeeded.
7. Call `compute_lod_loq` if blank is provided.
8. Populate and return `CalibrationResults`.

---

## 4. GUI Module: `src/gui/step7_widget.py`

### 4.1 Layout

Mirrors the Step 6 two-column layout exactly:

```
┌─────────────────────────────────────────────────────────────┐
│ Left panel (max 390 px, scrollable)                          │
│  ┌─────────────────────────────────────────┐                │
│  │ Step title                              │                │
│  │ Status / result banner                  │                │
│  │ ─────────────────────────────────────── │                │
│  │ Element: [ComboBox]                     │                │
│  │ Analytical λ: [DoubleSpinBox] nm        │                │
│  │ Tolerance:    [DoubleSpinBox] nm        │                │
│  │ Fit model:    [ComboBox]                │                │
│  │ ─────────────────────────────────────── │                │
│  │ Standards table (editable QTableWidget) │                │
│  │  [+] [−] [Load CSV] [Save CSV]          │                │
│  │  ✓ Skip baseline correction             │                │
│  │ ─────────────────────────────────────── │                │
│  │ Blank: [Load blank spectrum] / none     │                │
│  │ ─────────────────────────────────────── │                │
│  │ [⚙ Fit Calibration Curve]  (primary)   │                │
│  │ [Export CSV]  [Export PNG]  [PDF]        │                │
│  │ Progress bar (hidden until fitting)     │                │
│  └─────────────────────────────────────────┘                │
│                                                              │
│ Right panel (stretch)                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ QTabWidget                                           │   │
│  │  Tab 1: Calibration Curve (canvas + toolbar)         │   │
│  │  Tab 2: Residuals Plot    (canvas + toolbar)         │   │
│  │  Tab 3: LOD / LOQ Panel   (canvas + toolbar)         │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ QSplitter (vertical)                                 │   │
│  │  ─ Results summary QLabel (concentration estimate)   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Standards Table (`QTableWidget`)

Columns: `Sample ID`, `Concentration (ppm)`, `Spectrum File`, `Intensity`,
`Is Blank`.

- `Sample ID` and `Concentration (ppm)` are editable; `Spectrum File` opens a
  file-picker on double-click; `Intensity` is read-only (filled after fit);
  `Is Blank` is a `QCheckBox` in the cell widget.
- `[+]` appends a blank row. `[−]` removes the selected row.
- `[Load CSV]` reads a standards CSV matching the column order.
- `[Save CSV]` writes the table to a CSV.

### 4.3 Widget constructor signature

```python
def __init__(
    self,
    step1_tab,          # for ProcessedSpectra access
    step4_tab,          # for element list pre-population
    step5_tab,          # for analytical wavelength pre-population
    file_history=None,
    notes_panel=None,
):
```

### 4.4 Key methods

| Method | Purpose |
|--------|---------|
| `refresh()` | Re-reads Step 4 element list and Step 5 target wavelengths; does NOT re-fit. |
| `_on_element_changed()` | Switches calibration state per element; prompts if unsaved data. |
| `_on_fit_clicked()` | Validates table ≥ 3 rows, builds `CalibrationPoint` list, runs `CalibrationEngine.fit_and_predict()` in a `WorkerThread`. |
| `_on_fit_finished(results)` | Stores result, updates charts and summary banner, enables export buttons. |
| `_on_worker_error(msg)` | Shows error dialog, hides progress bar. |
| `_update_chart_curve()` | Calls `ChartEngine.render_calibration_curve()`. |
| `_update_chart_residuals()` | Calls `ChartEngine.render_calibration_residuals()`. |
| `_update_chart_lod_loq()` | Calls `ChartEngine.render_lod_loq_panel()`. |
| `_update_summary_banner(results)` | Formats concentration estimate ± uncertainty string. |
| `_on_export_csv_clicked()` | `QFileDialog.getSaveFileName` → `export_step7_csv`. |
| `_on_export_png_clicked()` | `QFileDialog.getExistingDirectory` → `export_step7_png`. |
| `_on_export_pdf_clicked()` | `QFileDialog.getSaveFileName` → `generate_pdf_report(step7_results=...)`. |
| `apply_theme()` | Re-applies theme to all three figures and redraws canvases. |
| `_save_session()` | Writes `.session/step7_standards.csv` and `.session/step7_results.json`. |
| `_load_session()` | Restores state from session files on startup. |

### 4.5 Per-element state storage

```python
# dict keyed by element name; value is a dict with:
#   "points":     list[CalibrationPoint]
#   "model":      str
#   "wavelength": float
#   "tolerance":  float
#   "results":    CalibrationResults | None
self._element_states: dict[str, dict] = {}
```

When the element combobox changes, the current element's state is flushed to
`self._element_states[current_element]` before loading the new one.

---

## 5. ChartEngine Extensions

Three new static methods added to `src/gui/charts.py`:

### 5.1 `render_calibration_curve(ax, points, fit_result, unknown_intensity, unknown_concentration, in_range)`

- **Scatter**: calibration point markers (concentration on X, intensity on Y),
  colour `C_ACCENT`, size 60, label "Standards".
- **Fit line**: smooth curve from `x_range[0]` to `x_range[1]` using 200
  evenly-spaced points. Colour `C_ACCENT2`, linewidth 2.
- **Confidence band**: ±1 σ envelope around fit line, computed via Monte Carlo
  over 500 samples drawn from `N(coefficients, covariance)`. Shaded with
  `alpha=0.25`, colour `C_ACCENT2`.
- **Unknown point**: vertical dashed line at `unknown_concentration`,
  horizontal dashed line at `unknown_intensity`, marker `*`, size 120,
  colour `C_WARN`. Label: "Unknown sample".
- **Extrapolation warning**: if `not in_range`, annotate the unknown point
  with "⚠ Extrapolation" in `C_ERROR` text.
- Axis labels: X = "Concentration (ppm)", Y = "Emission Intensity (a.u.)".
- Title: "Calibration Curve — {element}".
- Legend, dark style, tight layout.
- Placeholder "No calibration data" when `points` is empty.
- Entire body wrapped in `try/except`.

### 5.2 `render_calibration_residuals(ax, points, fit_result)`

- Computes residual = measured_intensity − model(concentration) for each
  standard.
- Scatter: concentration on X, residual on Y. Colour `C_ACCENT`.
- Horizontal line at y=0 (colour `C_BORDER`).
- Axis labels: X = "Concentration (ppm)", Y = "Residual (a.u.)".
- Title: "Calibration Residuals".
- Dark style. Placeholder when fit is None or `fit_ok=False`.
- Entire body wrapped in `try/except`.

### 5.3 `render_lod_loq_panel(ax, points, fit_result, lod_ppm, loq_ppm, blank_noise)`

- Re-renders the calibration curve (same as above, without the unknown point).
- Adds two horizontal dashed lines: LOD intensity = `3 * blank_noise`,
  LOQ intensity = `10 * blank_noise`, coloured `C_WARN` and `C_ERROR`.
- Adds vertical dashed lines at `lod_ppm` and `loq_ppm` on the X-axis.
- Annotates: "LOD = {lod_ppm:.3f} ppm" and "LOQ = {loq_ppm:.3f} ppm".
- If `lod_ppm` or `loq_ppm` is None, shows "LOD/LOQ: N/A (no blank)".
- Placeholder "Fit curve first to see LOD/LOQ" when `fit_result` is None.
- Entire body wrapped in `try/except`.

---

## 6. Export Engine Extensions

### 6.1 `export_step7_csv(results: CalibrationResults, filepath: Path) -> Path`

Writes a single CSV with two sections:

**Section 1 — Global results (one-row header block):**
```
Element, Model, R2, RMSE, LOD_ppm, LOQ_ppm,
Unknown_Concentration_ppm, Uncertainty_ppm, In_Range, Coefficients
```

**Section 2 — Per-standard table:**
```
Sample_ID, Concentration_ppm, Intensity, Is_Blank, Residual
```

Both sections separated by a blank row. Uses `csv.writer` directly for the
header block, then `pd.DataFrame.to_csv(mode='a')` for the per-standard rows.

### 6.2 `export_step7_png(curve_fig, residuals_fig, lod_fig, directory: Path) -> list[Path]`

Saves three separate PNG files via `save_figure_png`:
- `calibration_curve.png`
- `calibration_residuals.png`
- `lod_loq_panel.png`

Returns `list[Path]` of the three written files.

### 6.3 `generate_pdf_report()` — Step 7 section

New optional parameter `step7_results: CalibrationResults | None = None`.

When provided, adds a "Step 7 — Quantitative Analysis" section containing:
1. Element name and analytical wavelength.
2. Fit model and coefficients table (with ± CI).
3. R², RMSE, LOD, LOQ.
4. Concentration estimate paragraph (large, bold): `"{value} ± {unc} ppm (95 % CI)"`.
5. Extrapolation warning paragraph (if `not in_range`).
6. Calibration curve chart embedded as `RLImage`.
7. Per-standard table: Sample_ID, Concentration, Intensity, Residual.

---

## 7. Main Window Integration

### 7.1 Tab insertion (`src/gui/main_window.py`)

```python
# After step6_tab construction:
from src.gui.step7_widget import Step7Widget
self.step7_tab = Step7Widget(
    step1_tab=self.step1_tab,
    step4_tab=self.step4_tab,
    step5_tab=self.step5_tab,
    file_history=self.file_history,
    notes_panel=self.notes_panel,
)
self.tabs.insertTab(6, self.step7_tab, "⑦ Step 7: Calibration")
# Analysis Summary tab now at index 7
```

### 7.2 `_on_tab_changed()` update

```python
tab_names = [
    "Step 1: Baseline Correction",
    "Step 2: Peak Detection",
    "Step 3: Element Identification",
    "Step 4: Elemental Preferences",
    "Step 5: Validation",
    "Step 6: Model Performance",
    "Step 7: Calibration",       # new
    "Analysis Summary",          # shifted from 5 → 7
]
if index == 6:
    self.step7_tab.refresh()
if index == 7:
    self.summary_tab.refresh()
```

### 7.3 Theme toggle update

```python
for widget in [
    self.step1_tab, self.step2_tab, self.step3_tab,
    self.step4_tab, self.step5_tab, self.step6_tab,
    self.step7_tab,   # added
    self.summary_tab,
]:
    widget.apply_theme()
```

---

## 8. Session Persistence

The session files live alongside the existing `.session/` CSVs:

| File | Contents |
|------|----------|
| `.session/step7_standards_{element}.csv` | CalibrationPoint table for each element |
| `.session/step7_results_{element}.json` | FitResult + scalar results (no figures) |

Serialisation: `json.dumps` with `default=str` for floats.

On startup, `Step7Widget.__init__` calls `_load_session()` which reads these
files if they exist and reconstructs `self._element_states`.

---

## 9. Testing Strategy

### Unit tests: `tests/test_step7_calibration.py`

| Test | What it verifies |
|------|-----------------|
| `test_extract_intensity_basic` | Returns correct max intensity in tolerance window |
| `test_extract_intensity_missing_file` | Returns `None`, does not raise |
| `test_extract_intensity_no_peak_in_window` | Returns `None` |
| `test_fit_linear_known_data` | Fits y=2x+1, checks coefficients within 1 % |
| `test_fit_quadratic_known_data` | Fits y=x²+x+1, checks R² > 0.999 |
| `test_fit_power_law_known_data` | Fits y=3*x^0.8, checks coefficients within 2 % |
| `test_fit_too_few_points` | Returns `fit_ok=False` with clear `error_message` |
| `test_predict_linear_inverse` | Inverse of `y=2x+1` at y=11 gives x=5.0 |
| `test_predict_linear_uncertainty` | Uncertainty > 0 and finite |
| `test_predict_outside_range` | `in_range=False` when unknown above x_range |
| `test_lod_loq_linear` | LOD = 3σ/a, LOQ = 10σ/a, correct to 4 dp |
| `test_lod_loq_no_blank` | Returns `(None, None)` |
| `test_fit_and_predict_full` | End-to-end with temp CSV files |
| `test_fit_and_predict_too_few` | Returns `missing_info` populated |
| `test_compute_r_squared_perfect` | Returns 1.0 |
| `test_compute_r_squared_flat` | Returns 0.0 (SS_tot == 0) |

### Property-based tests: `tests/test_step7_properties.py`

Using `hypothesis`:

| Property | Strategy | Invariant |
|----------|----------|-----------|
| P1: Coefficients reproduce data | `st.floats` for a, b; `st.lists` for x | `|fit(x_i) - y_i| / y_i < 0.001` |
| P2: R² ∈ [0, 1] | random (conc, int) pairs | `0 ≤ R² ≤ 1` always |
| P3: RMSE ≥ 0 | random (conc, int) pairs | `RMSE ≥ 0` always |
| P4: `fit_and_predict` never raises | `st.one_of(st.none(), valid_df)` for each input | no exception |
| P5: LOQ ≥ LOD | any `blank_noise > 0` + fitted result | `LOQ ≥ LOD` always |
| P6: Uncertainty > 0 for linear | any valid `a ≠ 0` linear fit | `uncertainty > 0` |
| P7: In-range flag correct | `unknown_concentration` inside/outside x_range | flag matches truth |

### Widget tests: `tests/test_step7_widget.py`

- Export buttons disabled on init.
- `_update_summary_banner` formats result string correctly.
- Session save + load roundtrip preserves all CalibrationPoint values.
- `apply_theme()` does not raise.

---

## 10. Property Invariants Summary (Hypothesis-style)

```
P1:  fit_and_predict(points≥3, model) → fit_result.fit_ok == True
     for any synthetic (concentration, intensity) pair following the chosen model

P2:  fit_and_predict(points<3, ...) → results.missing_info is not empty

P3:  predict_concentration(intensity, fit_result).uncertainty > 0
     for any valid linear fit with non-zero covariance

P4:  LOQ ≥ LOD for any blank_noise > 0 and any converged fit

P5:  extract_intensity(any_path, ...) never raises — always returns float | None

P6:  CalibrationEngine.fit_and_predict never raises for any combination
     of None / empty / valid inputs
```

---

## 11. File Map

```
src/
  core/
    step7_calibration.py        ← NEW  (~350 lines)
  gui/
    step7_widget.py             ← NEW  (~550 lines)
    charts.py                   ← EXTENDED (3 new static methods, ~150 lines added)
    export_engine.py            ← EXTENDED (2 new functions + PDF section, ~120 lines added)
    main_window.py              ← UPDATED  (tab insertion + _on_tab_changed + theme loop)

tests/
  test_step7_calibration.py     ← NEW  (~300 lines)
  test_step7_properties.py      ← NEW  (~180 lines)
  test_step7_widget.py          ← NEW  (~120 lines)

.session/
  step7_standards_{element}.csv ← GENERATED at runtime
  step7_results_{element}.json  ← GENERATED at runtime
```

---

## 12. Dependency Notes

All required packages are already present in `requirements.txt`:

| Package | Used for |
|---------|----------|
| `scipy` | `scipy.optimize.curve_fit`, `scipy.optimize.brentq` |
| `numpy` | Array arithmetic, Monte Carlo confidence band |
| `pandas` | CSV I/O for standard spectra and session files |
| `matplotlib` | Three new chart methods |
| `PyQt6` | Widget, table, dialogs |
| `reportlab` | PDF extension (already a soft-dependency via `generate_pdf_report`) |

No new packages need to be added.
