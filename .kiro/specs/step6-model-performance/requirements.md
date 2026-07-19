# Requirements Document

## Introduction

Step 6 adds a **Model Performance Metrics** tab to the existing LIBS (Laser-Induced Breakdown Spectroscopy) spectral analysis desktop application. After the user has run Steps 2–5, Step 6 aggregates the outputs of those steps, computes classification performance metrics (Accuracy, Precision, Recall, F1-Score, SBR Improvement), and presents four scientific visualisations modelled on reference Figures 7, 11, 12, and 14 from the supporting paper:

- **Figure 7 style** — Elemental Preference Ranking bar chart (matched lines per element, colour-coded by confidence tier)
- **Figure 11 style** — Multi-Stage Validation Pipeline funnel / waterfall chart (peak count reduction at each pipeline stage)
- **Figure 12 style** — Correlation Heatmap (ambiguous peaks × elements, 0–1 score matrix)
- **Figure 14 style** — Performance Metrics bar chart (Accuracy, Precision, Recall, F1-Score, SBR Improvement)

The feature integrates into the existing PyQt6 application by adding a new "⑥ Step 6: Model Performance" tab, a `step6_widget.py` GUI module, and a `step6_performance.py` core logic module, following the two-column layout (scrollable left panel + chart right panel) and dark/light theme conventions established by Steps 1–5.

---

## Glossary

- **Step6Widget**: The PyQt6 `QWidget` subclass implementing the Step 6 tab UI.
- **PerformanceCalculator**: The core class in `step6_performance.py` that computes all metrics from upstream step data.
- **Pipeline_Stages**: The five sequential processing stages whose peak counts are tracked: Detected Peaks, After NIST Matching, After Elemental Preference Ranking, After Pure Spectra Validation, Final Bayesian Confirmation.
- **Confidence_Tier**: Categorical label for an element's match confidence: High (≥ 10 matched lines), Medium (3–9 matched lines), Low (< 3 matched lines).
- **SBR**: Signal-to-Background Ratio — the ratio of the mean peak intensity of validated lines to the mean baseline (background) intensity after Step 1 correction.
- **SBR_Improvement**: The ratio of post-processing SBR to pre-processing SBR, expressed as a multiplier (e.g., 2.60×).
- **TP** (True Positive): A detected peak correctly matched to a NIST-confirmed element line.
- **FP** (False Positive): A detected peak matched to an element line not confirmed by validation.
- **FN** (False Negative): A known element line (from NIST matching) not detected as a peak.
- **Accuracy**: `(TP + TN) / (TP + TN + FP + FN)` — fraction of all peaks correctly classified.
- **Precision**: `TP / (TP + FP)` — fraction of positive identifications that are correct.
- **Recall**: `TP / (TP + FN)` — fraction of true positives that were identified.
- **F1_Score**: `2 × (Precision × Recall) / (Precision + Recall)` — harmonic mean of Precision and Recall.
- **Correlation_Heatmap**: A 2-D matrix where each cell `[peak_i, element_j]` holds the Pearson correlation score (0–1) from Step 5 validation for that peak–element pair.
- **Ambiguous_Peak**: A detected peak whose highest correlation score is < 0.90, meaning it is not unambiguously assigned to one element.
- **ChartEngine**: The existing stateless chart-rendering class in `src/gui/charts.py`.
- **apply_theme()**: A method present on each step widget that refreshes matplotlib canvas backgrounds when the application theme changes.
- **export_step6_csv / export_step6_png / generate_pdf_report**: Functions in `src/gui/export_engine.py` that persist Step 6 results to disk.

---

## Requirements

### Requirement 1: Tab Integration

**User Story:** As a spectral analyst, I want a dedicated Step 6 tab in the main window, so that I can access model performance metrics without leaving the application.

#### Acceptance Criteria

1. THE `SpectralAnalysisApp` SHALL add a tab labelled "⑥ Step 6: Model Performance" to the `QTabWidget` after the existing "⑤ Step 5: Validation" tab.
2. THE `SpectralAnalysisApp` SHALL instantiate `Step6Widget` with references to `step2_tab`, `step3_tab`, `step4_tab`, and `step5_tab` so that Step 6 can read their results without re-running analysis.
3. WHEN the user navigates to the Step 6 tab, THE `Step6Widget` SHALL automatically call its `refresh()` method to pull the latest data from Steps 2–5.
4. WHEN the application theme is toggled, THE `SpectralAnalysisApp` SHALL call `step6_tab.apply_theme()` alongside the existing per-step `apply_theme()` calls.

---

### Requirement 2: Two-Column Layout

**User Story:** As a spectral analyst, I want Step 6 to follow the same two-column layout as the other steps, so that the interface feels consistent.

#### Acceptance Criteria

1. THE `Step6Widget` SHALL render a scrollable left panel with a maximum width of 370 px containing: step title, a status/summary banner, action buttons, and export buttons.
2. THE `Step6Widget` SHALL render a right panel that fills remaining horizontal space, containing a `QTabWidget` with four chart tabs (one per figure style) and a summary results table below the charts.
3. WHILE the application window width is less than 900 px, THE `Step6Widget` SHALL keep the left panel scrollable without clipping its content.
4. THE `Step6Widget` SHALL expose an `apply_theme()` method that refreshes all matplotlib canvas backgrounds and redraws charts using the active theme colours from `src/gui/theme.py`.

---

### Requirement 3: Data Aggregation from Upstream Steps

**User Story:** As a spectral analyst, I want Step 6 to automatically pull results from Steps 2–5, so that I do not have to re-import or manually enter data.

#### Acceptance Criteria

1. THE `PerformanceCalculator` SHALL accept `detected_peaks` (list from Step 2), `matches` (list from Step 3), `analysis_results` (dict from Step 4), and `validation_results` (`DataFrame` from Step 5) as inputs to its `compute()` method.
2. WHEN any upstream step has not been executed and its data attribute is `None` or empty, THE `PerformanceCalculator` SHALL return a result object with `None` values for metrics that depend on the missing step, and SHALL NOT raise an unhandled exception.
3. THE `PerformanceCalculator` SHALL derive Pipeline_Stages counts as follows: Stage 1 = `len(detected_peaks)`; Stage 2 = number of peaks with at least one NIST match (from `matches`); Stage 3 = number of peaks whose matched element appears in the Step 4 ranking DataFrame; Stage 4 = number of peaks with a `Validation_Coefficient` ≥ 0.50 in `validation_results`; Stage 5 = number of peaks with `Validation_Coefficient` ≥ 0.70 (the "Bayesian Confirmation" proxy).
4. THE `PerformanceCalculator` SHALL classify each element in the Step 4 ranking by Confidence_Tier: High if matched_lines ≥ 10, Medium if 3 ≤ matched_lines ≤ 9, Low if matched_lines < 3, using the `Wins` column as the matched_lines proxy.
5. THE `PerformanceCalculator` SHALL build the Correlation_Heatmap matrix from `validation_results` by mapping each wavelength in `validation_results` to its element assignment from `matches`, producing a peaks × elements matrix of `Validation_Coefficient` values (0 where no match exists).

---

### Requirement 4: Performance Metric Computation

**User Story:** As a spectral analyst, I want Accuracy, Precision, Recall, F1-Score, and SBR Improvement computed from the pipeline data, so that I can evaluate overall model quality.

#### Acceptance Criteria

1. THE `PerformanceCalculator` SHALL define TP as the count of validated peaks (Stage 5 count), FP as Stage 2 count minus Stage 5 count, and FN as the count of NIST-matched element lines not represented in the detected peaks list (estimated as max(0, number of unique elements × average_lines_per_element − Stage 1)).
2. THE `PerformanceCalculator` SHALL compute Precision as `TP / (TP + FP)`, Recall as `TP / (TP + FN)`, F1_Score as `2 × Precision × Recall / (Precision + Recall)`, and Accuracy as `(TP) / (TP + FP + FN)`, each clamped to [0.0, 1.0].
3. IF `TP + FP == 0`, THEN THE `PerformanceCalculator` SHALL set Precision to 0.0 rather than raising a division-by-zero error.
4. IF `TP + FN == 0`, THEN THE `PerformanceCalculator` SHALL set Recall to 0.0 rather than raising a division-by-zero error.
5. THE `PerformanceCalculator` SHALL compute SBR_Improvement as `mean(peak_intensities_validated) / mean(background_intensities)`, where `peak_intensities_validated` are the intensities of Stage-5 peaks from Step 2 `detected_peaks`, and `background_intensities` are the non-peak intensities from Step 1 `processed_data.corrected`. IF Step 1 data is unavailable, THE `PerformanceCalculator` SHALL set SBR_Improvement to `None`. WHEN `mean(background_intensities)` equals zero, THE `PerformanceCalculator` SHALL set SBR_Improvement to `float('inf')` to represent a perfect signal-to-background ratio.

---

### Requirement 5: Figure 7 Style — Elemental Preference Ranking Chart

**User Story:** As a spectral analyst, I want a horizontal bar chart showing each element's matched line count colour-coded by confidence tier, so that I can visually compare element presence strength.

#### Acceptance Criteria

1. THE `ChartEngine` SHALL expose a `render_element_ranking_fig7(ax, ranking_df)` static method that draws a horizontal bar chart with elements on the Y-axis and matched line counts on the X-axis, sorted descending by line count.
2. WHEN an element's matched line count is ≥ 10 (including exactly 10), THE `ChartEngine` SHALL colour its bar with `C_SUCCESS` (green), treating exactly 10 lines as High confidence.
3. WHEN an element's matched line count is between 3 and 9 inclusive, THE `ChartEngine` SHALL colour its bar with `C_WARN` (orange/amber).
4. WHEN an element's matched line count is < 3, THE `ChartEngine` SHALL colour its bar with `C_ERROR` (red).
5. THE `ChartEngine` SHALL render numeric count labels at the right end of each bar.
6. THE `ChartEngine` SHALL include a legend mapping the three Confidence_Tier colours to their labels (High ≥ 10, Medium 3–9, Low < 3).
7. WHEN `ranking_df` is `None` or empty, THE `ChartEngine` SHALL render a placeholder using `_show_placeholder(ax, "No ranking data available")`.

---

### Requirement 6: Figure 11 Style — Multi-Stage Validation Pipeline Chart

**User Story:** As a spectral analyst, I want a funnel/waterfall chart showing how many peaks survive each pipeline stage and the percentage reduction at each stage, so that I can identify where the largest filtering occurs.

#### Acceptance Criteria

1. THE `ChartEngine` SHALL expose a `render_pipeline_funnel(ax, stage_counts)` static method that draws a horizontal bar chart where each bar represents one Pipeline_Stage, with bars ordered from top (Stage 1) to bottom (Stage 5), and bar width proportional to the stage's peak count.
2. THE `ChartEngine` SHALL render the absolute peak count at the right end of each bar.
3. WHEN stage N has a higher peak count than stage N−1 (count increased rather than decreased), THE `ChartEngine` SHALL render no reduction annotation for that stage; annotations are only shown when count decreases.
4. THE `ChartEngine` SHALL colour each bar with a gradient from `C_ACCENT` (stage 1) to `C_ACCENT2` (stage 5), distributing colours evenly across the five stages.
5. WHEN `stage_counts` is `None` or contains fewer than two non-zero stages, THE `ChartEngine` SHALL render a placeholder using `_show_placeholder(ax, "Insufficient pipeline data")`.

---

### Requirement 7: Figure 12 Style — Correlation Heatmap

**User Story:** As a spectral analyst, I want a colour-coded heatmap of peak-to-element correlation scores, so that I can visually identify which element best explains each ambiguous peak.

#### Acceptance Criteria

1. THE `ChartEngine` SHALL expose a `render_correlation_heatmap(ax, heatmap_matrix, peak_labels, element_labels)` static method that renders a 2-D matrix with peaks on the Y-axis (rows) and elements on the X-axis (columns).
2. THE `ChartEngine` SHALL use a `blue → red` (`"coolwarm"`) colormap with range [0.0, 1.0] and SHALL render a colourbar annotated "Correlation Score".
3. THE `ChartEngine` SHALL render each cell's numeric value (2 decimal places) centred inside the cell, with text colour white when cell value ≥ 0.5 and dark (`C_BG_DEEP`) when cell value < 0.5 to ensure legibility.
4. THE `ChartEngine` SHALL label Y-axis rows with the format `"Peak N (wavelength nm)"` and X-axis columns with element symbols.
5. WHEN `heatmap_matrix` is `None` or has fewer than 2 rows or 2 columns, THE `ChartEngine` SHALL render a placeholder using `_show_placeholder(ax, "Insufficient heatmap data")`.

---

### Requirement 8: Figure 14 Style — Performance Metrics Bar Chart

**User Story:** As a spectral analyst, I want a bar chart displaying Accuracy, Precision, Recall, F1-Score, and SBR Improvement, so that I can assess the model's classification quality at a glance.

#### Acceptance Criteria

1. THE `ChartEngine` SHALL expose a `render_performance_metrics(ax, metrics_dict, ax2)` static method that draws four vertical bars (Accuracy, Precision, Recall, F1-Score) as percentages on the primary Y-axis (`ax`) and a fifth bar (SBR Improvement) on a secondary Y-axis (`ax2`).
2. THE `ChartEngine` SHALL colour the four percentage bars with `C_SUCCESS` (green) and the SBR bar with `C_ACCENT` (blue).
3. THE `ChartEngine` SHALL annotate each percentage bar with its value to one decimal place (e.g., "78.1%") and the SBR bar with its multiplier to two decimal places (e.g., "2.60×").
4. THE `ChartEngine` SHALL set the primary Y-axis range to [0, 110] to provide headroom above 100%, and SHALL label the primary axis "Score (%)".
5. THE `ChartEngine` SHALL label the secondary Y-axis "SBR Improvement (×)".
6. WHEN any metric value is `None`, THE `ChartEngine` SHALL skip that bar and annotate its position with "N/A" text, rendering the remaining available metric bars normally.

---

### Requirement 9: Summary Table

**User Story:** As a spectral analyst, I want a tabular summary of element-level results beneath the charts, so that I can read exact values without interpreting chart graphics.

#### Acceptance Criteria

1. THE `Step6Widget` SHALL render a `QTableWidget` below the chart tabs with columns: Element, Confidence Tier, Matched Lines, Mean VC, Status.
2. THE `Step6Widget` SHALL populate one row per unique element from the Step 4 ranking, setting Mean VC from the mean `Validation_Coefficient` of all `validation_results` rows whose wavelength is attributed to that element.
3. THE `Step6Widget` SHALL colour the "Confidence Tier" cell background using `C_SUCCESS`, `C_WARN`, or `C_ERROR` matching the element's Confidence_Tier (High/Medium/Low). WHEN the tier colour cannot be determined from the data, THE `Step6Widget` SHALL display the cell in an error state with `C_ERROR` background and log a warning.
4. WHEN no upstream data is available, THE `Step6Widget` SHALL display an empty table with a status row reading "Run Steps 2–5 first". WHEN upstream data exists but the table widget fails to populate, THE `Step6Widget` SHALL still display the empty table with the "Run Steps 2–5 first" status row.

---

### Requirement 10: Export Functionality

**User Story:** As a spectral analyst, I want to export Step 6 results as CSV, PNG, and PDF, so that I can include them in scientific reports.

#### Acceptance Criteria

1. THE `Step6Widget` SHALL provide an "Export CSV" button that, when clicked, saves a CSV file containing: element name, confidence tier, matched lines, Accuracy, Precision, Recall, F1-Score, SBR Improvement, and all Pipeline_Stage counts.
2. THE `Step6Widget` SHALL provide an "Export PNG" button that, when clicked, saves a composite PNG image containing all four charts (Figures 7, 11, 12, 14 style) at 150 DPI minimum.
3. THE `Step6Widget` SHALL provide an "Export PDF" button that, when clicked, generates a multi-page PDF report including the summary table and all four charts.
4. WHEN no performance results have been computed, THE `Step6Widget` SHALL disable all three export buttons and SHALL re-enable all three together only after a successful `refresh()` or "Compute Metrics" action that produces results — buttons SHALL be re-disabled at the start of each new refresh cycle and only re-enabled upon success.
5. IF a file save dialog is dismissed without selecting a path, THE `Step6Widget` SHALL silently cancel the export without showing an error dialog.

---

### Requirement 11: Refresh and State Management

**User Story:** As a spectral analyst, I want Step 6 to update its display whenever I return to its tab after running earlier steps, so that the metrics always reflect the current analysis state.

#### Acceptance Criteria

1. THE `Step6Widget.refresh()` method SHALL read `detected_peaks` from Step 2, `matches` from Step 3, `analysis_results` from Step 4, and `validation_results` from Step 5, calling `PerformanceCalculator.compute()` with those values.
2. WHEN `refresh()` is called and all required upstream data is present, THE `Step6Widget` SHALL re-render all four charts and repopulate the summary table with updated values.
3. WHEN `refresh()` is called and any required upstream data is missing, THE `Step6Widget` SHALL render charts using whatever partial data is available, showing placeholders only for the specific visualisations that require the missing data, and SHALL update the status banner to identify which steps have not yet been completed.
4. THE `Step6Widget` SHALL store the computed metrics in a `performance_results` instance attribute so that subsequent export calls do not require recomputation.
