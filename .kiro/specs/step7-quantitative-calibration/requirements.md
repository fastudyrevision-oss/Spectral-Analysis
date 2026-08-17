# Step 7 — Quantitative Calibration Curve: Requirements

## Overview

Step 7 extends the LIBS Spectral Analysis Software from qualitative element
identification (Steps 1–6) to **quantitative elemental analysis** — answering
not just "is Calcium present?" but "how much Calcium is there?".

This is achieved through a calibration curve workflow: the user supplies a set
of standard samples with known elemental concentrations (standard reference
materials, SRMs), the software maps emission line intensity at the validated
wavelength to concentration, and then applies that curve to the unknown sample
to produce a concentration estimate with uncertainty bounds.

---

## Functional Requirements

### 1. Calibration Standard Input

**1.1** The system MUST allow the user to load a calibration standards table.
The table contains one row per standard sample with columns:

| Column | Type | Description |
|--------|------|-------------|
| `Sample_ID` | string | Identifier (e.g. "SRM-1a") |
| `Concentration_ppm` | float | Known concentration in parts-per-million |
| `Spectrum_File` | string | Path to the processed spectrum CSV for that standard |

**1.2** The table MUST be editable within the UI — users can add, delete, and
edit rows directly in the application without touching the CSV file.

**1.3** The system MUST support loading the calibration standards table from
a CSV file via a file-picker dialog.

**1.4** The system MUST support saving the standards table to CSV so the
session is reproducible.

**1.5** Each standard spectrum MUST pass through the same Step 1 baseline
correction before intensity extraction. The system MUST provide a checkbox
option to skip this if the standard spectra are already baseline-corrected.

---

### 2. Emission Line Selection

**2.1** The system MUST allow the user to select which analytical emission line
wavelength (in nm) is used for quantification. Default: the top-ranked line
from Step 4 for the chosen element.

**2.2** The line selection control MUST be pre-populated from Step 4 winner
lines and Step 5 target wavelengths so the user does not need to remember
numbers.

**2.3** The user MUST be able to override the wavelength by typing a custom
value (free text, validated to float).

**2.4** The system MUST extract the peak intensity at the selected wavelength
from each standard spectrum using the same local-maximum search as Step 2
(±tolerance window). The extraction tolerance in nm MUST be configurable.

---

### 3. Calibration Curve Fitting

**3.1** The system MUST fit a calibration curve through the (intensity, concentration)
pairs. The following fit models MUST be supported, selectable by the user:

| Model ID | Equation | Use case |
|----------|----------|----------|
| `linear` | y = a·x + b | Low-concentration linear range |
| `quadratic` | y = a·x² + b·x + c | Moderate self-absorption |
| `power_law` | y = a·x^b | Wide dynamic range |

**3.2** The fitting MUST use `scipy.optimize.curve_fit` for all model types
with sensible parameter bounds to prevent unphysical fits.

**3.3** The system MUST compute and display:
- Fitted coefficients with 95 % confidence intervals (from the covariance
  matrix returned by `curve_fit`)
- R² coefficient of determination
- RMSE (root mean square error) across calibration points

**3.4** If fewer than 3 standards are loaded, the system MUST disable fitting
and show a clear warning: "Minimum 3 standards required for calibration."

**3.5** The system MUST handle `curve_fit` convergence failures gracefully —
show an error dialog with the exception message and leave results blank.

---

### 4. Unknown Sample Concentration Estimation

**4.1** Once a calibration curve is fitted, the system MUST extract the
intensity of the same analytical line from the Step 1 processed spectrum of
the unknown sample (already present from earlier steps).

**4.2** The system MUST invert the fitted curve to compute the estimated
concentration of the unknown sample.

**4.3** The system MUST propagate uncertainty from the calibration curve
covariance matrix to produce a ± uncertainty on the concentration estimate.
The uncertainty MUST be displayed as: `[value] ± [uncertainty] ppm (95 % CI)`.

**4.4** If the unknown sample's intensity falls outside the calibrated range,
the system MUST display a warning: "Extrapolation warning: sample intensity is
outside the calibration range. Result may be unreliable."

**4.5** The concentration estimate MUST be shown in the Step 7 summary banner
prominently (large font, colour-coded by whether the value falls within the
calibrated range).

---

### 5. Visualisation

**5.1** The system MUST display a **Calibration Curve Chart** showing:
- Calibration points as scatter markers (concentration on X-axis, intensity
  on Y-axis)
- Fitted curve as a smooth line across the calibration range
- Unknown sample point highlighted (different colour/marker)
- Error bars on fit (shaded ±1 σ confidence band around the fitted line)
- Legend, axis labels, and plot title

**5.2** The system MUST display a **Residuals Plot** showing:
- Residual = measured intensity − fitted intensity for each standard
- Horizontal reference line at zero
- Helps the user detect systematic deviations or outliers

**5.3** The system MUST display a **LOD/LOQ Indicator Chart**:
- Plots the 3σ (LOD) and 10σ (LOQ) lines on the calibration curve chart as
  horizontal dashed lines where σ is the standard deviation of the blank
  (see Requirement 6)
- Annotated with LOD and LOQ concentration values

**5.4** All charts MUST use the existing `ChartEngine.apply_dark_style()` and
respect the app-wide dark/light theme toggle.

---

### 6. Blank and Detection Limits

**6.1** The user MUST be able to optionally provide a blank spectrum (a sample
with zero analyte concentration — pure matrix or pure solvent).

**6.2** When a blank is provided, the system MUST compute:
- **LOD** (Limit of Detection) = 3σ_blank / slope (for linear model) or
  numerically for non-linear models
- **LOQ** (Limit of Quantification) = 10σ_blank / slope

where σ_blank is the standard deviation of the intensity at the analytical
line across repeated blank measurements, or approximated from a single blank
spectrum as the local noise level.

**6.3** LOD and LOQ values MUST be displayed in the results summary panel.

**6.4** If no blank is provided, LOD/LOQ are shown as "N/A (no blank provided)".

---

### 7. Element Selection

**7.1** The system MUST provide a dropdown to select which element is being
quantified. The list MUST be pre-populated from Step 4 element ranking results.

**7.2** When the selected element changes, all calibration data, curve fits,
and results MUST reset (with a confirmation dialog if calibration data has
already been entered).

**7.3** Multiple elements can be calibrated independently within one session
by switching the element dropdown. Each element's calibration data MUST be
stored separately.

---

### 8. Export

**8.1** The system MUST export calibration results to CSV with columns:
`Element`, `Model`, `Coefficients`, `R2`, `RMSE`, `LOD_ppm`, `LOQ_ppm`,
`Unknown_Concentration_ppm`, `Uncertainty_ppm`.

**8.2** The system MUST export the calibration curve and residuals plots as
PNG (minimum 150 DPI) into a user-chosen directory.

**8.3** The system MUST extend the existing `generate_pdf_report()` in
`export_engine.py` with an optional Step 7 section that includes: calibration
table, fitted coefficients, R², RMSE, LOD, LOQ, concentration estimate, and
embedded chart image.

---

### 9. Session Persistence

**9.1** On application close, the system MUST save the following to the
`.session/` directory:
- The calibration standards table (as `step7_standards.csv`)
- The fit model choice and extracted results (as `step7_results.json`)

**9.2** On application open, the system MUST restore the calibration state if
those files exist, so the user does not need to re-enter standards.

---

### 10. Integration with Existing Pipeline

**10.1** The Step 7 tab MUST appear at index 6 in the main tab widget, before
the Analysis Summary tab (which shifts to index 7).

**10.2** `main_window.py` MUST call `step7_tab.refresh()` when the Step 7 tab
is activated, which re-reads the unknown sample intensity from the already-
computed Step 1 output.

**10.3** The `apply_theme()` method MUST be included in the theme-toggle loop
in `main_window.py` so the Step 7 charts react to dark/light switches.

**10.4** The Analysis Summary tab MUST include a "Quantitative Result" row
showing the primary element concentration estimate when Step 7 has been run.

---

## Non-Functional Requirements

**NFR-1 Performance:** Curve fitting MUST complete within 2 seconds for up to
50 calibration standards.

**NFR-2 Robustness:** The system MUST never crash on malformed standard CSVs;
all file I/O MUST be wrapped in try/except with user-facing error dialogs.

**NFR-3 Reproducibility:** Given the same standards table, fit model, and
unknown spectrum, the concentration estimate MUST be deterministic (identical
across runs).

**NFR-4 Usability:** The minimum user interaction to get a concentration
estimate SHOULD be: (1) load standards table, (2) click "Fit Curve", (3) read
result — no more than three clicks from a prepared standards CSV.

**NFR-5 Accuracy:** The fitted curve MUST match `scipy.optimize.curve_fit`
output exactly — no reimplementation of least-squares.

---

## Out of Scope (Step 7 v1)

- Multi-line internal standard normalisation (ratio method) — planned for v2
- Matrix-matched calibration (plasma temperature correction)
- Certified uncertainty propagation per GUM (ISO Guide to Uncertainty in
  Measurement) — the simpler 95 % CI from covariance matrix is sufficient for v1
- Automatic outlier removal from calibration standards (user removes manually)
- Multi-element simultaneous calibration in a single model
