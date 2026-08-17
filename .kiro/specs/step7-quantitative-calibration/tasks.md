# Implementation Plan: Step 7 — Quantitative Calibration Curve

## Overview

Build the quantitative calibration layer on top of the existing 6-step pipeline.
Each wave is independently runnable and testable before the next wave starts.
The dependency order is: data models → core engine → chart extensions →
export extensions → widget → main window integration.

---

## Tasks

- [ ] 1. Create data models and core `CalibrationEngine` in `src/core/step7_calibration.py`

  - [ ] 1.1 Define `CalibrationPoint`, `FitResult`, `CalibrationResults` TypedDicts
    - `CalibrationPoint`: `sample_id`, `concentration`, `spectrum_file`,
      `intensity`, `is_blank` fields exactly as in design §2.
    - `FitResult`: `model`, `coefficients`, `covariance`, `r_squared`, `rmse`,
      `x_range`, `fit_ok`, `error_message`.
    - `CalibrationResults`: all fields from design §2.3.
    - Add module docstring referencing design §2.
    - _Requirements: NFR-3, NFR-5_

  - [ ] 1.2 Implement the three static model functions and `_MODELS` selector dict
    - `_model_linear(x, a, b)`, `_model_quadratic(x, a, b, c)`,
      `_model_power_law(x, a, b)` — as documented in design §3.1.1.
    - `_MODELS` dict maps model name → `(fn, n_params, lower_bounds, upper_bounds)`.
    - _Requirements: 3.1_

  - [ ] 1.3 Implement `extract_intensity(spectrum_path, wavelength_nm, tolerance_nm) -> float | None`
    - Read CSV with `pd.read_csv`; auto-detect wavelength column
      (case-insensitive search for "wavelength") and intensity column
      (search for "corrected", then "intensity").
    - Return `max(intensity_values)` within the tolerance window.
    - Return `None` if file unreadable or no rows in window; never raise.
    - _Requirements: 2.4_

  - [ ] 1.4 Implement `compute_r_squared(y_actual, y_predicted) -> float`
    - Formula as in design §3.1.3; clamp to [0, 1]; return 0.0 when SS_tot == 0.
    - _Requirements: 3.3_

  - [ ] 1.5 Implement `fit_curve(concentrations, intensities, model) -> FitResult`
    - Validate `len >= 3`; raise `ValueError` if not.
    - Call `scipy.optimize.curve_fit` with `maxfev=10000` and model bounds from `_MODELS`.
    - On `RuntimeError`: return `FitResult(fit_ok=False, error_message=..., ...)`.
    - On success: compute R², RMSE, return full `FitResult`.
    - _Requirements: 3.2, 3.3, 3.5, NFR-5_

  - [ ] 1.6 Write unit tests for `fit_curve` in `tests/test_step7_calibration.py`
    - `test_fit_linear_known_data`: synthesise `y = 2x + 1` for x in [1,10];
      assert coefficients within 1 % of [2, 1] and `r_squared > 0.999`.
    - `test_fit_quadratic_known_data`: synthesise `y = x² + x + 1`;
      assert `r_squared > 0.999`.
    - `test_fit_power_law_known_data`: synthesise `y = 3 * x^0.8`;
      assert coefficients within 2 %.
    - `test_fit_too_few_points`: 2 points → `fit_ok=False`, `error_message` not None.
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ] 1.7 Implement `predict_concentration(intensity, fit_result) -> tuple[float|None, float|None]`
    - Linear: closed-form inverse and first-order uncertainty propagation (design §3.1.5).
    - Quadratic: `numpy.roots` inversion; pick real root in `x_range`; propagate.
    - Power-law: logarithmic inversion; propagate via partial derivatives.
    - Return `(None, None)` on any arithmetic failure.
    - _Requirements: 4.2, 4.3_

  - [ ] 1.8 Write unit tests for `predict_concentration`
    - `test_predict_linear_inverse`: fit `y=2x+1`, predict at y=11 → x≈5.0 ±ε.
    - `test_predict_linear_uncertainty`: uncertainty > 0 and finite.
    - `test_predict_outside_range`: unknown above `x_range[1]` → `in_range=False`.
    - _Requirements: 4.2, 4.3, 4.4_

  - [ ] 1.9 Implement `estimate_blank_noise` and `compute_lod_loq`
    - `estimate_blank_noise(spectrum_path, wavelength_nm, tolerance_nm,
      window_nm=2.0) -> float | None`: returns `np.std` of intensities in window.
    - `compute_lod_loq(blank_noise, fit_result) -> tuple[float|None, float|None]`:
      linear: `3σ/a` and `10σ/a`; non-linear: `brentq` numerical inversion.
    - Return `(None, None)` when `blank_noise is None` or `fit_ok=False`.
    - _Requirements: 6.2, 6.3, 6.4_

  - [ ] 1.10 Write unit tests for `compute_lod_loq`
    - `test_lod_loq_linear`: known σ=0.1, a=2 → LOD≈0.15, LOQ≈0.5 ppm.
    - `test_lod_loq_no_blank`: `blank_noise=None` → `(None, None)`.
    - `test_lod_loq_not_fitted`: `fit_ok=False` → `(None, None)`.
    - `test_loq_ge_lod`: LOQ ≥ LOD for any valid blank_noise > 0.
    - _Requirements: 6.2_

  - [ ] 1.11 Implement `fit_and_predict(...)` top-level method
    - Full orchestration as in design §3.1.8.
    - Must never raise for any input combination (wrap body in `try/except`).
    - Populate `missing_info` for: < 3 valid points, fit failure, no unknown data.
    - _Requirements: 3.4, 3.5, 4.1–4.5, NFR-2, NFR-6_

  - [ ] 1.12 Write unit tests for `fit_and_predict`
    - `test_fit_and_predict_full`: end-to-end with three temp CSV spectra;
      assert `fit_ok=True`, `unknown_concentration` is float, `in_range` is bool.
    - `test_fit_and_predict_too_few`: 2 valid points → `missing_info` non-empty.
    - `test_fit_and_predict_none_inputs`: all args None → returns dict, no raise.
    - _Requirements: 3.4, NFR-2_

  - [ ] 1.13 Write property-based tests in `tests/test_step7_properties.py`
    - P1: `@given` synthetic (a, b, x_list) → fitted coefficients reproduce data
      within 0.1 % for linear model (no noise).
    - P2: `@given` random (conc, intensity) pairs (n≥3) → `0 ≤ r_squared ≤ 1`.
    - P3: `@given` random pairs → `rmse ≥ 0`.
    - P4: `@given` st.one_of(st.none(), valid) for each arg →
      `fit_and_predict` never raises.
    - P5: `@given` `blank_noise > 0` + converged linear fit → `loq ≥ lod`.
    - P6: `@given` linear fit (a ≠ 0) → `uncertainty > 0`.
    - P7: `@given` unknown outside x_range → `in_range=False`.
    - _Requirements: NFR-3, NFR-5_

---

- [ ] 2. Checkpoint — core engine tests pass
  - Run `pytest tests/test_step7_calibration.py tests/test_step7_properties.py -v`.
  - All tests must pass with no warnings about convergence on synthetic data.
  - Ask the user if questions arise before proceeding.

---

- [ ] 3. Add three new chart methods to `src/gui/charts.py`

  - [ ] 3.1 Implement `ChartEngine.render_calibration_curve(ax, points, fit_result, unknown_intensity, unknown_concentration, in_range, element_name)`
    - Standards scatter: `C_ACCENT`, size 60, label "Standards".
    - Fit line: 200-point smooth curve, `C_ACCENT2`, linewidth 2.
    - Confidence band: Monte Carlo (500 samples from `N(coefficients, covariance)`),
      `alpha=0.25`, `C_ACCENT2` fill.
    - Unknown point: `*` marker, `C_WARN`, size 120; crosshair dashed lines.
    - Extrapolation annotation in `C_ERROR` when `not in_range`.
    - Axis labels, title "Calibration Curve — {element_name}", legend, dark style.
    - Placeholder "No calibration data" when `points` is empty or `fit_result` is None.
    - Full `try/except` wrapper.
    - _Requirements: 5.1, 5.3_

  - [ ] 3.2 Implement `ChartEngine.render_calibration_residuals(ax, points, fit_result)`
    - Residual = measured_intensity − model(concentration) for each standard.
    - Scatter `C_ACCENT`; horizontal line at y=0 (`C_BORDER`).
    - Axis labels and title "Calibration Residuals"; dark style.
    - Placeholder "Fit curve first" when `fit_result` is None or `fit_ok=False`.
    - Full `try/except` wrapper.
    - _Requirements: 5.2_

  - [ ] 3.3 Implement `ChartEngine.render_lod_loq_panel(ax, points, fit_result, lod_ppm, loq_ppm, blank_noise)`
    - Re-render calibration curve (without unknown crosshair).
    - Horizontal dashed lines at `3*blank_noise` (`C_WARN`) and
      `10*blank_noise` (`C_ERROR`).
    - Vertical dashed lines at `lod_ppm` and `loq_ppm`.
    - Annotations "LOD = {:.3f} ppm" and "LOQ = {:.3f} ppm".
    - Show "LOD/LOQ: N/A (no blank provided)" text when values are None.
    - Placeholder "Fit curve first to see LOD/LOQ" when `fit_result` is None.
    - Full `try/except` wrapper.
    - _Requirements: 5.3, 6.3, 6.4_

  - [ ] 3.4 Write smoke tests for all three chart methods in `tests/test_step7_calibration.py`
    - For each method: call with empty/None inputs → no exception, axes contains
      placeholder text.
    - Call with minimal valid inputs → no exception, axes has at least one artist.
    - _Requirements: 5.1, 5.2, 5.3_

---

- [ ] 4. Extend `src/gui/export_engine.py`

  - [ ] 4.1 Implement `export_step7_csv(results: CalibrationResults, filepath: Path) -> Path`
    - Section 1 (global results): write one-row header block as in design §6.1.
    - Blank row separator.
    - Section 2 (per-standard table): `Sample_ID`, `Concentration_ppm`,
      `Intensity`, `Is_Blank`, `Residual`.
    - Remove partial file on `OSError`; re-raise.
    - _Requirements: 8.1_

  - [ ] 4.2 Implement `export_step7_png(curve_fig, residuals_fig, lod_fig, directory: Path) -> list[Path]`
    - Save three separate PNGs via `save_figure_png`: `calibration_curve.png`,
      `calibration_residuals.png`, `lod_loq_panel.png`.
    - Return list of three Paths.
    - _Requirements: 8.2_

  - [ ] 4.3 Add `step7_results: CalibrationResults | None = None` parameter to `generate_pdf_report`
    - When provided, append a "Step 7 — Quantitative Analysis" section with:
      element name + analytical wavelength, fit model + coefficients table (±CI),
      R² + RMSE + LOD + LOQ, concentration estimate paragraph (bold),
      extrapolation warning if `not in_range`, calibration curve image,
      per-standard table.
    - Must not break existing callers (parameter is optional with default None).
    - _Requirements: 8.3_

  - [ ] 4.4 Write integration tests for export functions
    - `test_export_step7_csv_roundtrip`: write and re-read CSV; assert header
      matches, per-standard rows match input points count.
    - `test_export_step7_png_creates_files`: assert three PNG files exist and
      size > 0 in tmp_path.
    - `test_generate_pdf_with_step7`: assert PDF file starts with `%PDF-`
      and size > 1 KB.
    - `test_generate_pdf_without_step7`: existing callers still work with
      `step7_results=None` (regression test).
    - _Requirements: 8.1, 8.2, 8.3_

---

- [ ] 5. Create `src/gui/step7_widget.py` — `Step7Widget`

  - [ ] 5.1 Implement widget skeleton: constructor, `_create_left_panel()`, `_create_right_panel()`
    - Constructor signature: `__init__(self, step1_tab, step4_tab, step5_tab,
      file_history=None, notes_panel=None)`.
    - Left panel: title label, summary banner (`summary_banner_style()`),
      element combobox (label + QComboBox), λ spinbox (0.0–1000.0, step 0.01),
      tolerance spinbox (0.01–5.0, step 0.01), fit model combobox
      ("linear" | "quadratic" | "power_law").
    - Standards table: 5-column `QTableWidget` with `[+]`, `[−]`,
      `[Load CSV]`, `[Save CSV]` buttons; `skip_baseline_checkbox`.
    - Blank row: `[Load Blank Spectrum]` button + `QLabel` showing filename or "None".
    - Primary button: `QPushButton("⚙  Fit Calibration Curve")` with
      `primary_button_style()`, disabled until ≥ 3 rows present.
    - Export buttons: `[Export CSV]`, `[Export PNG]`, `[Export PDF]` —
      all `setEnabled(False)` initially.
    - Progress bar: hidden, `progress_bar_style()`.
    - Right panel: `QTabWidget` with three chart tabs ("Calibration Curve",
      "Residuals", "LOD / LOQ"), each with `FigureCanvasQTAgg` (figsize 7×4,
      dpi 100) + `NavigationToolbar2QT`; a `QSplitter` below with a
      concentration-result `QLabel`.
    - Initialise `self._element_states: dict[str, dict] = {}`.
    - Call `_load_session()` at end of `__init__`.
    - _Requirements: 1.2, 7.1, 7.3, 9.2, 10.1_

  - [ ] 5.2 Implement `refresh()` and `_on_element_changed()`
    - `refresh()`: read element list from `step4_tab.analysis_results`;
      populate element combobox; set default analytical wavelength from
      `step5_tab.target_wavelengths[0]` if available; do NOT re-fit.
    - `_on_element_changed()`: flush current element state into
      `self._element_states`; load new element state if it exists; update
      spinboxes and table; call `_update_fit_button_state()`.
    - _Requirements: 2.1, 2.2, 7.1, 7.2, 10.2_

  - [ ] 5.3 Implement standards table editing methods
    - `_on_add_row()`: appends a row with editable Sample ID, Concentration,
      Spectrum File (double-click opens file-picker), read-only Intensity,
      checkbox Is Blank.
    - `_on_remove_row()`: removes selected row; shows nothing if none selected.
    - `_on_load_standards_csv(filepath)`: reads CSV via `pd.read_csv`,
      populates table rows; shows error dialog on malformed CSV.
    - `_on_save_standards_csv()`: `QFileDialog.getSaveFileName`; writes table
      to CSV; shows error dialog on `OSError`.
    - `_update_fit_button_state()`: enables Fit button when row count ≥ 3.
    - _Requirements: 1.2, 1.3, 1.4, 3.4_

  - [ ] 5.4 Implement `_on_fit_clicked()` and worker callbacks
    - Build `list[CalibrationPoint]` from table rows (skip rows where
      Spectrum File is empty).
    - Identify blank point from `Is Blank` checkbox.
    - Read analytical wavelength and tolerance from spinboxes.
    - Show progress bar, disable all action buttons.
    - Launch `WorkerThread` running `CalibrationEngine.fit_and_predict(...)`.
    - On success: call `_on_fit_finished(results)`.
    - On error: call `_on_worker_error(message)`.
    - _Requirements: 3.1–3.5, 4.1–4.5, NFR-1_

  - [ ] 5.5 Implement `_on_fit_finished(results)` and `_update_summary_banner(results)`
    - Store `self.calibration_results = results`.
    - Hide progress bar; re-enable Fit button; enable export buttons.
    - Call all three `_update_chart_*` methods.
    - Update `self.result_label` with concentration estimate string.
    - `_update_summary_banner`: format string:
      `"Element: {element}  λ = {wl:.2f} nm\nModel: {model}  R² = {r2:.4f}  RMSE = {rmse:.4f}\nConcentration: {conc:.4f} ± {unc:.4f} ppm (95 % CI)"`
      plus `"⚠ Extrapolation warning"` in `C_ERROR` colour when `not in_range`.
      Show "Minimum 3 standards required" if `missing_info` contains that string.
    - _Requirements: 4.3, 4.4, 4.5_

  - [ ] 5.6 Implement `_update_chart_curve()`, `_update_chart_residuals()`, `_update_chart_lod_loq()`
    - Each method calls the corresponding `ChartEngine` static method,
      passing either real data or appropriate placeholder args when data is absent.
    - After each call, invoke `canvas.draw()` and `toolbar.home()`.
    - _Requirements: 5.1–5.3_

  - [ ] 5.7 Implement export handlers `_on_export_csv_clicked()`, `_on_export_png_clicked()`, `_on_export_pdf_clicked()`
    - `_on_export_csv_clicked`: `getSaveFileName(filter="CSV Files (*.csv)")`;
      call `export_step7_csv`; show info or error dialog.
    - `_on_export_png_clicked`: `getExistingDirectory`; call `export_step7_png`;
      show info or error dialog.
    - `_on_export_pdf_clicked`: `getSaveFileName(filter="PDF Files (*.pdf)",
      default="LIBS_Calibration_Report.pdf")`; call `generate_pdf_report(
      ..., step7_results=self.calibration_results)`; handle `ImportError`
      (reportlab not installed) separately from other exceptions.
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ] 5.8 Implement `apply_theme()`, `_save_session()`, `_load_session()`
    - `apply_theme()`: iterate over three figures, call
      `fig.patch.set_facecolor(get_chart_bg())`; update canvas backgrounds;
      call `canvas.draw()` for each; re-apply `summary_banner_style()` and
      `progress_bar_style()`.
    - `_save_session()`: write `.session/step7_standards_{element}.csv` and
      `.session/step7_results_{element}.json` for each element with a non-None
      result; called from `_on_fit_finished`.
    - `_load_session()`: on startup, restore all `self._element_states` from
      session files if they exist.
    - _Requirements: 9.1, 9.2, 10.3_

  - [ ] 5.9 Write widget tests in `tests/test_step7_widget.py`
    - Export buttons disabled on init.
    - `_update_summary_banner` with valid results produces string containing
      "ppm" and element name.
    - `_update_summary_banner` with `missing_info` containing
      "Minimum 3 standards required" produces that text in banner.
    - Session save + load roundtrip preserves all CalibrationPoint values.
    - `apply_theme()` does not raise.
    - `refresh()` does not raise when step4_tab has no analysis_results.
    - _Requirements: 4.3, 4.5, 9.1, 9.2_

---

- [ ] 6. Integrate `Step7Widget` into `src/gui/main_window.py`

  - [ ] 6.1 Import and instantiate `Step7Widget`
    - Add `from src.gui.step7_widget import Step7Widget` after Step 6 import.
    - Instantiate with `step1_tab`, `step4_tab`, `step5_tab`, `file_history`,
      `notes_panel` arguments.
    - `self.tabs.insertTab(6, self.step7_tab, "⑦ Step 7: Calibration")`.
    - _Requirements: 10.1_

  - [ ] 6.2 Update `_on_tab_changed()` for new tab indices
    - Update `tab_names` list: insert `"Step 7: Calibration"` at index 6;
      shift `"Analysis Summary"` to index 7.
    - Add `if index == 6: self.step7_tab.refresh()`.
    - Change existing `if index == 5: self.summary_tab.refresh()` to `index == 7`.
    - Update step6 guard from old index to 5 (verify it was already correct).
    - _Requirements: 10.2_

  - [ ] 6.3 Update `_on_toggle_theme()` to include `step7_tab`
    - Add `self.step7_tab` to the theme-toggle loop that calls
      `widget.apply_theme()`.
    - _Requirements: 10.3_

  - [ ] 6.4 Update Analysis Summary tab to show Step 7 concentration
    - In `summary_widget.py`, add a "Quantitative Result" row to the
      summary table that reads `step7_tab.calibration_results` and displays
      `"{element}: {concentration:.4f} ± {uncertainty:.4f} ppm"` or
      `"Step 7 not run"` if no result exists.
    - _Requirements: 10.4_

---

- [ ] 7. Final checkpoint — all tests pass

  - Run the full test suite: `pytest tests/ -v --tb=short`.
  - Ensure all new tests pass: `test_step7_calibration.py`,
    `test_step7_properties.py`, `test_step7_widget.py`.
  - Ensure no regressions in existing tests: `test_core.py`, `test_io.py`,
    `test_integration.py`, `test_step6_performance.py`,
    `test_step4_step5_bugs_exploration.py`, `test_step4_step5_preservation.py`.
  - Ask the user if questions arise before marking complete.

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5"] },
    { "id": 2, "tasks": ["1.6", "1.7", "1.9"] },
    { "id": 3, "tasks": ["1.8", "1.10", "1.11"] },
    { "id": 4, "tasks": ["1.12", "1.13", "3.1", "3.2", "3.3"] },
    { "id": 5, "tasks": ["3.4", "4.1", "4.2", "4.3"] },
    { "id": 6, "tasks": ["4.4", "5.1"] },
    { "id": 7, "tasks": ["5.2", "5.3"] },
    { "id": 8, "tasks": ["5.4", "5.5"] },
    { "id": 9, "tasks": ["5.6", "5.7", "5.8"] },
    { "id": 10, "tasks": ["5.9", "6.1"] },
    { "id": 11, "tasks": ["6.2", "6.3", "6.4"] }
  ]
}
```

## Notes

- `CalibrationEngine` is intentionally stateless (mirrors `PerformanceCalculator`
  from Step 6) — easier to unit test and safe to instantiate in `WorkerThread`.
- The `power_law` model requires all concentrations > 0 and all intensities > 0.
  The widget should warn the user if any standard has concentration = 0 and the
  power_law model is selected; zero-concentration standards should be marked
  `is_blank=True` instead.
- The confidence band uses Monte Carlo rather than analytical propagation because
  `quadratic` and `power_law` models do not have closed-form envelopes.
  Monte Carlo with 500 samples is fast enough (< 50 ms) that it is acceptable to
  run on the main thread during chart updates.
- Session filenames are per-element to support Requirement 7.3 (multiple elements
  independently calibrated in one session).
- `generate_pdf_report` already has optional `step6_metrics` parameter; the new
  `step7_results` follows the same optional pattern so existing calls are unaffected.
