# Implementation Plan: Step 6 — Model Performance Metrics

## Overview

Implement the Model Performance Metrics tab by building the core `PerformanceCalculator`
class first, then adding the four new `ChartEngine` static methods, then the export
helpers, and finally the `Step6Widget` and `main_window.py` integration. Each layer
builds on the previous one, and property-based tests (Hypothesis) validate each
correctness property close to the code that introduces it.

---

## Tasks

- [x] 1. Create `PerformanceCalculator` core module
  - Create `src/core/step6_performance.py` with `PerformanceResults`, `PipelineStages`,
    and `ElementRow` TypedDicts as defined in the design data-models section.
  - Implement `PerformanceCalculator` class with `compute()`, `_compute_stage_counts()`,
    `_classify_confidence_tier()`, `_compute_metrics()`, `_compute_sbr()`, and
    `_build_heatmap()` methods.
  - All internal helpers must catch every exception, log it, and return a safe default
    (`None`, empty dict, empty array) so that `compute()` never raises for any
    combination of None/empty upstream inputs.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 1.1 Implement `_classify_confidence_tier(wins)` with boundary-correct thresholds
    - wins ≥ 10 → "High" (C_SUCCESS), 3–9 → "Medium" (C_WARN), < 3 → "Low" (C_ERROR)
    - _Requirements: 3.4_

  - [x] 1.2 Write property test for `_classify_confidence_tier` (Property 3)
    - **Property 3: Confidence tier classification is total and correct**
    - **Validates: Requirements 3.4, 5.2, 5.3, 5.4**
    - Use `st.integers(min_value=0, max_value=500)` for wins; assert return value is one
      of {"High", "Medium", "Low"} and boundary values 0, 3, 9, 10 each map correctly.

  - [x] 1.3 Implement `_compute_metrics(stage_counts, unique_elements, avg_lines_per_element)`
    - Apply TP/FP/FN formulas from design; clamp results to [0.0, 1.0]; guard all
      zero-division cases (Precision when TP+FP=0, Recall when TP+FN=0).
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 1.4 Write property test for `_compute_metrics` (Property 4)
    - **Property 4: All classification metrics are clamped to [0, 1]**
    - **Validates: Requirements 4.2, 4.3, 4.4**
    - Use `st.tuples(st.integers(min_value=0, max_value=1000), ...)` for (TP, FP, FN);
      assert every returned metric float is in [0.0, 1.0] and no ZeroDivisionError.

  - [x] 1.5 Implement `_compute_sbr(validated_peak_wls, detected_peaks, processed_data)`
    - Return `None` when `processed_data` is None; `float('inf')` when mean background
      is 0; otherwise `mean(validated_intensities) / mean(background_intensities)`.
    - _Requirements: 4.5_

  - [x] 1.6 Write property test for `_compute_sbr` (Property 5)
    - **Property 5: SBR Improvement handles all denominator cases correctly**
    - **Validates: Requirements 4.5**
    - Test all three branches: `processed_data=None → None`, zero background → `inf`,
      positive arrays → expected ratio. Use `st.floats(min_value=0.0, max_value=1e6)`.

  - [x] 1.7 Implement `_compute_stage_counts(detected_peaks, matches, analysis_results, validation_results)`
    - Derive the five stage counts per Requirements 3.3 definition.
    - _Requirements: 3.3_

  - [x] 1.8 Write property test for `_compute_stage_counts` (Property 2)
    - **Property 2: Pipeline stage counts satisfy monotonicity and derivation invariants**
    - **Validates: Requirements 3.3**
    - Assert stage1 = len(detected_peaks), stage2 ≤ stage1, stage5 ≤ stage4; use
      randomly generated peaks/matches/results DataFrames.

  - [x] 1.9 Implement `_build_heatmap(validation_results, matches)`
    - Return `(matrix, peak_labels, element_labels)` with shape (N, M); fill missing
      peak-element pairs with 0.0.
    - _Requirements: 3.5_

  - [x] 1.10 Write property test for `_build_heatmap` (Property 6)
    - **Property 6: Correlation heatmap matrix dimensions and values match inputs**
    - **Validates: Requirements 3.5, 7.1**
    - Assert matrix shape equals (N unique wavelengths, M unique elements); cells with
      a match equal the DataFrame's `Validation_Coefficient`; others equal 0.0.

  - [x] 1.11 Implement `compute()` top-level method
    - Collect `missing_steps`, call all helpers with appropriate guards, populate and
      return a `PerformanceResults` TypedDict.
    - _Requirements: 3.1, 3.2_

  - [x] 1.12 Write property test for `compute()` with missing upstream data (Property 1)
    - **Property 1: Missing upstream data never raises**
    - **Validates: Requirements 3.2**
    - Use `st.one_of(st.none(), st.just([]))` for each of the four upstream inputs;
      assert `compute()` always returns a dict and never raises.

- [x] 2. Add four static methods to `ChartEngine` in `src/gui/charts.py`
  - Add `render_element_ranking_fig7`, `render_pipeline_funnel`,
    `render_correlation_heatmap`, and `render_performance_metrics` as `@staticmethod`
    methods following the existing `ax.clear()` / `_finish()` / `_show_placeholder()`
    pattern.
  - Each method must wrap its entire rendering body in `try/except` and fall back to
    `_show_placeholder` on any error.
  - _Requirements: 5.1–5.7, 6.1–6.5, 7.1–7.5, 8.1–8.6_

  - [x] 2.1 Implement `render_element_ranking_fig7(ax, ranking_df)`
    - Horizontal bar chart, elements on Y-axis, sorted descending by count; colour bars
      by confidence tier (C_SUCCESS / C_WARN / C_ERROR); numeric labels right of each
      bar; legend for three tiers; placeholder when ranking_df is None or empty.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x] 2.2 Write property test for `render_element_ranking_fig7` bar order (Property 7)
    - **Property 7: Element ranking bar chart bars appear in descending order**
    - **Validates: Requirements 5.1**
    - Generate random `ranking_df` with at least 1 row; assert rendered bar widths are
      non-ascending from top to bottom.

  - [x] 2.3 Write property test for `render_element_ranking_fig7` annotation count (Property 8)
    - **Property 8: Bar chart annotations equal number of bars**
    - **Validates: Requirements 5.5**
    - For K-row `ranking_df`, assert exactly K numeric text annotations exist on the axes.

  - [x] 2.4 Implement `render_pipeline_funnel(ax, stage_counts)`
    - Horizontal bar chart, Stage 1 top to Stage 5 bottom, width proportional to count;
      absolute count at right of each bar; reduction annotation only when count
      decreases; gradient colours from C_ACCENT to C_ACCENT2; placeholder when
      stage_counts is None or fewer than 2 non-zero stages.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 2.5 Implement `render_correlation_heatmap(ax, heatmap_matrix, peak_labels, element_labels)`
    - 2-D matrix, coolwarm colormap [0,1], colourbar labelled "Correlation Score"; cell
      values to 2 dp; text white when cell ≥ 0.5 and C_BG_DEEP when cell < 0.5; Y-axis
      labels "Peak N (wavelength nm)"; placeholder when matrix is None or < 2×2.
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 2.6 Write property test for `render_correlation_heatmap` cell text colours (Property 10)
    - **Property 10: Heatmap cell text colour follows the 0.5 threshold rule**
    - **Validates: Requirements 7.3**
    - Generate arbitrary matrix values in [0.0, 1.0]; assert each cell's text annotation
      colour is white (#FFFFFF) when value ≥ 0.5 and C_BG_DEEP when value < 0.5.

  - [x] 2.7 Implement `render_performance_metrics(ax, metrics_dict, ax2)`
    - Four percentage bars (Accuracy, Precision, Recall, F1) on primary Y-axis (range
      [0, 110], labelled "Score (%)"), SBR bar on secondary Y-axis (labelled "SBR
      Improvement (×)"); C_SUCCESS for percentage bars, C_ACCENT for SBR; annotate
      percentages to 1 dp and SBR multiplier to 2 dp; render "N/A" for None values.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 2.8 Write property test for `render_performance_metrics` with partial None inputs (Property 9)
    - **Property 9: Performance metrics chart handles partial None inputs**
    - **Validates: Requirements 8.6**
    - Use `st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0))` for each of
      the five metric values; assert no exception is raised and a bar or "N/A" text
      appears at each metric position.

- [x] 3. Add Step 6 export functions to `src/gui/export_engine.py`
  - Add `export_step6_csv(performance_results, filepath)` and
    `export_step6_png(figures, filepath, dpi=150)` following the existing
    `save_figure_png` / `export_step5_csv` patterns (restore facecolor, re-raise
    OSError after cleanup).
  - _Requirements: 10.1, 10.2_

  - [x] 3.1 Implement `export_step6_csv(performance_results, filepath)`
    - Write one row per element containing: element name, confidence tier, matched
      lines, Accuracy, Precision, Recall, F1-Score, SBR Improvement, and all five
      Pipeline_Stage counts; use `pd.DataFrame.to_csv(index=False)`.
    - _Requirements: 10.1_

  - [x] 3.2 Implement `export_step6_png(figures, filepath, dpi=150)`
    - Composite all four Step 6 chart Figures into a 2×2 grid PNG at minimum 150 DPI;
      save with `C_BG_DEEP` facecolor; restore original facecolors after; remove
      partial file on OSError before re-raising.
    - _Requirements: 10.2_

- [x] 4. Checkpoint — Core logic and chart tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Create `Step6Widget` in `src/gui/step6_widget.py`
  - New file mirroring the two-column layout of `Step5Widget` (scrollable left panel
    ≤ 370 px + chart right panel) using PyQt6, matplotlib FigureCanvasQTAgg, and the
    theme helpers from `src/gui/theme.py`.
  - _Requirements: 1.1–1.4, 2.1–2.4, 9.1–9.4, 10.1–10.5, 11.1–11.4_

  - [x] 5.1 Implement widget skeleton: constructor, `_create_left_panel()`, `_create_right_panel()`
    - Accept `step2_tab`, `step3_tab`, `step4_tab`, `step5_tab`, `step1_tab` (optional),
      `file_history`, `notes_panel` in `__init__`.
    - Left panel: step title, status/summary banner, "Compute Metrics" button, export
      buttons (CSV / PNG / PDF) all disabled initially, info label, progress bar (hidden).
    - Right panel: `QTabWidget` with four chart tabs (Fig 7 / Fig 11 / Fig 12 / Fig 14)
      each containing `FigureCanvasQTAgg` + `NavigationToolbar2QT`; a `QSplitter` with
      the chart tabs above and a `QTableWidget` below.
    - _Requirements: 2.1, 2.2, 2.3, 9.1_

  - [x] 5.2 Implement `refresh()` and `_on_compute_clicked()`
    - `refresh()`: read upstream step data, disable export buttons, call
      `PerformanceCalculator.compute()` in a `WorkerThread`, update status banner, re-
      enable exports on success.
    - `_on_compute_clicked()`: same flow, triggered by the "Compute Metrics" button.
    - Store result in `self.performance_results`.
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 10.4_

  - [x] 5.3 Implement `_update_chart_fig7()`, `_update_chart_fig11()`, `_update_chart_fig12()`, `_update_chart_fig14()`
    - Each method calls the corresponding `ChartEngine` static method, passing either
      real data or the appropriate placeholder arguments when data is absent.
    - Call all four from the worker-result callback.
    - _Requirements: 11.2, 11.3_

  - [x] 5.4 Implement `_populate_summary_table()`
    - One row per element from `performance_results.element_rows`; colour "Confidence
      Tier" cell with C_SUCCESS / C_WARN / C_ERROR; show "Run Steps 2–5 first" when
      no data is available.
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 5.5 Write property test for summary table Mean VC (Property 11)
    - **Property 11: Summary table Mean VC equals per-element average from validation results**
    - **Validates: Requirements 9.2**
    - Generate random `ranking_df` and `validation_results` DataFrame; compute expected
      per-element mean VC; assert that after calling `_populate_summary_table()` (or
      inspecting `PerformanceCalculator.compute()` element_rows) each row's mean_vc
      equals the arithmetic mean of all matching Validation_Coefficient values.

  - [x] 5.6 Implement `apply_theme()`
    - Update all four figure `patch.set_facecolor` and canvas backgrounds; redraw
      canvases without recomputing data.
    - _Requirements: 2.4_

  - [x] 5.7 Implement export handlers `_on_export_csv_clicked()`, `_on_export_png_clicked()`, `_on_export_pdf_clicked()`
    - Use `QFileDialog.getSaveFileName`; silently cancel if path is empty; call
      `export_step6_csv`, `export_step6_png`, and `generate_pdf_report` respectively;
      show error dialog on exception.
    - _Requirements: 10.1, 10.2, 10.3, 10.5_

  - [x] 5.8 Write property test for `Step6Widget.refresh()` with partial upstream data (Property 12)
    - **Property 12: refresh() with partial upstream data shows placeholders only for missing visualisations**
    - **Validates: Requirements 11.3**
    - For each subset of the four upstream inputs being None, assert that after
      `PerformanceCalculator.compute()` only the charts requiring the missing data
      receive placeholder data (i.e. the relevant fields in `PerformanceResults` are
      None or empty) while other fields remain populated.

- [x] 6. Integrate `Step6Widget` into `src/gui/main_window.py`
  - [x] 6.1 Add `Step6Widget` import and instantiation after `step5_tab`
    - `from src.gui.step6_widget import Step6Widget`
    - Instantiate with all five step tab references plus `file_history` and
      `notes_panel`.
    - `self.tabs.insertTab(5, self.step6_tab, "⑥ Step 6: Model Performance")`
      so that "📊 Analysis Summary" shifts to index 6.
    - _Requirements: 1.1, 1.2_

  - [x] 6.2 Update `_on_tab_changed()` for new tab indices
    - Update `tab_names` list to include "Step 6: Model Performance" at position 5 and
      "Analysis Summary" at position 6.
    - Change `if index == 5: self.summary_tab.refresh()` to `index == 6`.
    - Add `if index == 5: self.step6_tab.refresh()`.
    - _Requirements: 1.3_

  - [x] 6.3 Update `_on_toggle_theme()` to include `step6_tab`
    - Add `self.step6_tab` to the `for widget in [...]` loop that calls
      `widget.apply_theme()`.
    - _Requirements: 1.4_

- [x] 7. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP.
- Each task references specific requirements for traceability.
- Property tests use the Hypothesis strategies documented in `design.md`; the
  `.hypothesis/` directory is already present in the repo.
- The design uses Python throughout — no language selection was required.
- `main_window.py` currently uses `insertTab(5, ...)` to place Step 6 before
  "Analysis Summary"; the summary tab's auto-refresh index must be updated from 5 to 6
  as part of task 6.2.
- `export_step6_png` produces a composite 2×2 grid from four separate Figure objects,
  so it must create a new figure rather than modify the originals.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3", "1.5", "1.7", "1.9"] },
    { "id": 1, "tasks": ["1.2", "1.4", "1.6", "1.8", "1.10", "1.11"] },
    { "id": 2, "tasks": ["1.12", "2.1", "2.4", "2.5", "2.7"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.6", "2.8", "3.1", "3.2"] },
    { "id": 4, "tasks": ["5.1"] },
    { "id": 5, "tasks": ["5.2", "5.3", "5.4", "5.6", "5.7"] },
    { "id": 6, "tasks": ["5.5", "5.8", "6.1"] },
    { "id": 7, "tasks": ["6.2", "6.3"] }
  ]
}
```
