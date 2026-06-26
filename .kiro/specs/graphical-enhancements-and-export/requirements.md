# Requirements Document

## Introduction

This feature adds rich graphical visualizations and multi-format export capabilities to the
Spectral Analysis Software's Step 4 (Elemental Preferences) and Step 5 (Validation) pipeline
steps. It also improves the overall GUI aesthetic to be more prominent and polished. The goal
is to give analysts immediate visual insight into elemental dominance, score distributions,
and validation quality — alongside the ability to export results as CSV, PNG figures, or a
comprehensive PDF report.

---

## Glossary

- **Application**: The PyQt6 desktop application for LIBS spectral analysis.
- **Step4_Widget**: The PyQt6 widget managing Step 4 (Elemental Preferences & Peak Competition).
- **Step5_Widget**: The PyQt6 widget managing Step 5 (Validation with Reference Spectra).
- **Chart_Engine**: The matplotlib-based subsystem responsible for rendering all charts and
  figures embedded in the Application.
- **Export_Engine**: The subsystem responsible for producing CSV, PNG, and PDF output files.
- **PDF_Report**: A structured multi-page PDF document summarising a complete analysis session.
- **Ranking_Chart**: A horizontal bar chart showing each element's win count, rendered inside
  Step4_Widget.
- **Score_Scatter**: A scatter plot of Confidence_Score (Y-axis) vs. Observed_Wavelength (nm,
  X-axis) with per-element colour coding, rendered inside Step4_Widget.
- **VC_Histogram**: A histogram of Validation_Coefficient (VC) values grouped into quality
  bins, rendered inside Step5_Widget.
- **VC_Color_Badge**: A coloured status indicator applied to each VC row in the Step 5 results
  table, following the four-tier quality palette.
- **Validation_Coefficient (VC)**: A Pearson correlation value in [0, 1] measuring how well a
  processed spectrum matches a reference at a given wavelength.
- **Quality_Tier**: One of four classification levels for VC values —
  Excellent (VC > 0.95), Good (0.85 ≤ VC ≤ 0.95), Moderate (0.70 ≤ VC < 0.85), Weak (VC < 0.70).
- **ranking_df**: DataFrame output of Step 4 with columns Element, Wins, Total_Score, Avg_Score.
- **winner_lines_df**: DataFrame output of Step 4 with columns Winning_Element,
  Observed_Wavelength, NIST_Matched_Wavelength, Confidence_Score, Num_Competitors.
- **validation_results_df**: DataFrame output of Step 5 with columns Wavelength_nm,
  Validation_Coefficient, Status.
- **Theme_Palette**: The colour constants defined in `src/gui/theme.py`
  (C_ACCENT=#4A9EFF, C_ACCENT2=#2DD4BF, C_SUCCESS=#22C55E, C_WARN=#F59E0B, C_ERROR=#EF4444,
  C_BG_DEEP=#0F1117, C_BG_CARD=#222536, C_BG_PANEL=#1A1D27, C_TEXT=#E8EAF0,
  C_TEXT2=#8B90A4, C_BORDER=#3A3D52).

---

## Requirements

---

### Requirement 1: Elemental Dominance Bar Chart (Step 4)

**User Story:** As a spectral analyst, I want to see a horizontal bar chart of element wins
inside Step 4, so that I can immediately identify which elements dominate the spectrum without
reading tabular data.

#### Acceptance Criteria

1. WHEN Step4_Widget completes a competition analysis (analysis_results is populated without
   error), THE Chart_Engine SHALL render a Ranking_Chart as a horizontal bar chart inside
   Step4_Widget, placed below the existing result tabs.

2. THE Ranking_Chart SHALL display one bar per element, with bar length proportional to the
   element's Wins count from ranking_df.

3. THE Ranking_Chart SHALL sort bars in descending order of Wins so that the dominant element
   appears at the top; WHEN two or more elements have equal Wins counts, THE Ranking_Chart
   SHALL break ties by descending Total_Score.

4. THE Ranking_Chart SHALL annotate each bar with the numeric Wins value displayed to the
   right of (outside) the bar end.

5. THE Ranking_Chart SHALL use distinct colours for bars, cycling through Theme_Palette accent
   colours in order (C_ACCENT, C_ACCENT2, C_SUCCESS, C_WARN) and repeating the cycle for
   any elements beyond four, so that each element is visually distinguishable.

6. THE Ranking_Chart SHALL use the dark background style matching Theme_Palette: C_BG_DEEP as
   figure background, C_BG_CARD as axes background, C_TEXT as tick and label colour, C_BORDER
   as grid line colour.

7. IF ranking_df contains zero rows, THEN THE Chart_Engine SHALL display a placeholder message
   "No data available" centred in the Ranking_Chart axes instead of an empty plot.

---

### Requirement 2: Wavelength vs. Score Scatter Plot (Step 4)

**User Story:** As a spectral analyst, I want a scatter plot of observed wavelength versus
confidence score with per-element colour coding, so that I can see how scores are distributed
across the spectrum for each element.

#### Acceptance Criteria

1. WHEN Step4_Widget completes a competition analysis, THE Chart_Engine SHALL render a
   Score_Scatter plot inside Step4_Widget using winner_lines_df.

2. THE Score_Scatter SHALL plot Observed_Wavelength (nm) on the X-axis and Confidence_Score
   on the Y-axis, with the Y-axis range fixed to [0.0, 1.0].

3. THE Score_Scatter SHALL assign unique colours to distinct elements in Winning_Element by
   cycling through Theme_Palette accent colours in order (C_ACCENT, C_ACCENT2, C_SUCCESS,
   C_WARN) for up to four elements, and using matplotlib's default colour cycle for any
   additional elements; each element SHALL have exactly one legend entry mapping its colour
   to its element name.

4. THE Score_Scatter SHALL display axis labels "Wavelength (nm)" and "Confidence Score", and
   a chart title "Emission Line Scores by Element".

5. THE Score_Scatter SHALL use the dark background style: C_BG_DEEP as figure background,
   C_BG_CARD as axes background, C_TEXT as tick and label colour, C_BORDER as grid line colour.

6. IF winner_lines_df contains zero rows, THEN THE Chart_Engine SHALL display a placeholder
   message "No data available" centred in the Score_Scatter axes instead of an empty plot.

---

### Requirement 3: Validation Coefficient Histogram (Step 5)

**User Story:** As a spectral analyst, I want a histogram of VC values grouped by quality
tier, so that I can quickly assess the overall distribution of validation quality across all
target wavelengths.

#### Acceptance Criteria

1. WHEN Step5_Widget completes a validation run (validation_results is populated without
   error), THE Chart_Engine SHALL render a VC_Histogram inside Step5_Widget using the
   Validation_Coefficient column of validation_results_df.

2. THE VC_Histogram SHALL use fixed bin boundaries aligned to Quality_Tier thresholds:
   [0.0, 0.70, 0.85, 0.95, 1.0], producing four bins (Weak, Moderate, Good, Excellent).

3. THE VC_Histogram SHALL colour each bin according to its Quality_Tier using Theme_Palette
   constants: Excellent → C_SUCCESS, Good → C_ACCENT, Moderate → C_WARN, Weak → C_ERROR.

4. THE VC_Histogram SHALL display a chart title "Validation Coefficient Distribution",
   a Y-axis label "Count", and an X-axis label "Validation Coefficient (VC)".

5. THE VC_Histogram SHALL include a legend displayed inside the axes area that is always
   visible, mapping each bin colour to its tier name (Excellent, Good, Moderate, Weak).

6. THE VC_Histogram SHALL use the dark background style: C_BG_DEEP as figure background,
   C_BG_CARD as axes background, C_TEXT as tick and label colour, C_BORDER as grid line colour.

7. IF validation_results_df contains no non-null Validation_Coefficient values, THEN THE
   Chart_Engine SHALL display a placeholder message "No data available" centred in the
   VC_Histogram axes instead of an empty plot.

8. WHEN validation_results_df contains a mix of null and non-null Validation_Coefficient
   values, THE Chart_Engine SHALL exclude null values from the histogram and render it
   normally using only the non-null values.

---

### Requirement 4: Validation Coefficient Colour Badge (Step 5)

**User Story:** As a spectral analyst, I want each row in the Step 5 results table to show a
colour-coded quality badge, so that I can identify at a glance which wavelengths have
excellent, good, moderate, or weak validation.

#### Acceptance Criteria

1. WHEN Step5_Widget populates the results table, THE Step5_Widget SHALL apply a
   VC_Color_Badge to the Quality column cell of each row using the four-tier classification:
   VC > 0.95 → "Excellent" (background C_SUCCESS), 0.85 ≤ VC ≤ 0.95 → "Good"
   (background C_ACCENT), 0.70 ≤ VC < 0.85 → "Moderate" (background C_WARN),
   VC < 0.70 → "Weak" (background C_ERROR).

2. THE Step5_Widget SHALL display the tier label text ("Excellent", "Good", "Moderate",
   "Weak") in white text (contrasting with all four tier background colours: C_SUCCESS,
   C_ACCENT, C_WARN, C_ERROR) to ensure legibility.

3. WHEN a Validation_Coefficient value is null or missing (validation failed), THE
   Step5_Widget SHALL display "Failed" in the Quality cell with background colour C_BG_CARD
   and text colour C_TEXT2.

4. WHEN the next validation run completes, THE Step5_Widget SHALL replace any existing
   three-tier labels (Good/Fair/Poor) with the four-tier Quality_Tier labels, so that no
   Good/Fair/Poor labels remain in the Quality column after the run completes.

---

### Requirement 5: CSV Export

**User Story:** As a spectral analyst, I want to export results to CSV with a single button
click from both Step 4 and Step 5, so that I can load the data into other tools for further
analysis.

#### Acceptance Criteria

1. WHEN the user clicks "Export CSV" in Step4_Widget, THE Export_Engine SHALL open a
   directory-selection dialog and, upon confirmation, save ranking_df, winner_lines_df, and
   competition_df as three separate CSV files to the selected directory using filenames
   `{base}_ranking.csv`, `{base}_competition.csv`, and `{base}_winners.csv`.

2. WHEN the user clicks "Export CSV" in Step5_Widget, THE Export_Engine SHALL open a
   save-file dialog and, upon confirmation, save validation_results_df as a single CSV file
   to the selected path.

3. WHEN the Export_Engine writes a CSV file, THE Export_Engine SHALL include a header row
   matching the DataFrame column names.

4. WHEN a CSV export succeeds, THE Application SHALL display a success notification
   showing the full file path(s) written.

5. IF a CSV export fails due to a file system error (e.g., permission denied, disk full),
   THEN THE Export_Engine SHALL display an error dialog with a human-readable description
   of the failure (including the OS error message) and SHALL NOT leave partial files on disk.

---

### Requirement 6: PNG Figure Export

**User Story:** As a spectral analyst, I want to export all charts from Step 4 and Step 5 as
PNG image files, so that I can include them in reports or presentations.

#### Acceptance Criteria

1. WHEN the user clicks "Export PNG" in Step4_Widget, THE Export_Engine SHALL open a
   directory-selection dialog and, upon confirmation, save the Ranking_Chart as
   `ranking_chart.png` and the Score_Scatter as `score_scatter.png` in the selected directory.

2. WHEN the user clicks "Export PNG" in Step5_Widget, THE Export_Engine SHALL open a
   save-file dialog filtered to PNG files and, upon confirmation, save the VC_Histogram
   to the selected path.

3. WHEN the Export_Engine saves a PNG figure, THE Export_Engine SHALL save it at a resolution
   of at least 150 DPI using C_BG_DEEP as the background colour.

4. WHEN the user cancels either dialog without selecting a path, THE Export_Engine SHALL take
   no action and leave the current application state unchanged.

5. WHEN a PNG export succeeds, THE Application SHALL display a success notification showing
   the full file path(s) written.

6. IF a PNG export fails due to a file system error (e.g., permission denied, disk full),
   THEN THE Export_Engine SHALL display an error dialog with the OS error message, SHALL
   delete any partially written file at the chosen path, and SHALL NOT crash the Application.

---

### Requirement 7: PDF Report Export

**User Story:** As a spectral analyst, I want to export a comprehensive PDF report from
Step 5, so that I can share a complete, self-contained analysis summary with colleagues or
archive it as a project deliverable.

#### Acceptance Criteria

1. WHEN the user clicks "Export PDF Report" in Step5_Widget, THE Step5_Widget SHALL open a
   save-file dialog filtered to PDF files with a default filename of
   `LIBS_Validation_Report.pdf`.

2. WHEN the user confirms a save path in the dialog, THE Export_Engine SHALL generate a
   PDF_Report at the chosen path.

3. THE PDF_Report SHALL include the following sections in order:
   a. Cover page: application name, report title "LIBS Validation Report", generation date
      and time (ISO 8601 format), and input filenames for processed and reference spectra.
   b. Parameters section: window size (nm), minimum points, VC threshold values used.
   c. Results summary: total wavelengths validated, count per Quality_Tier, average VC.
   d. Detailed results table: Wavelength_nm, Validation_Coefficient, Status, Quality_Tier
      for every row in validation_results_df; WHEN validation_results_df is empty, the
      table section SHALL display "No results available" instead of an empty table.
   e. VC_Histogram figure embedded as an image.
   f. Selected wavelengths list.

4. IF Step4_Widget analysis results are available at the time of PDF export, THEN THE
   PDF_Report SHALL include an optional Step 4 summary section containing the Ranking_Chart
   figure and top-5 elements by Wins count.

5. THE Export_Engine SHALL generate the PDF_Report using the `reportlab` library and SHALL
   set document metadata: Title = "LIBS Validation Report",
   Author = "Spectral Analysis Software".

6. WHEN a PDF export succeeds, THE Application SHALL display a success notification showing
   the full file path written.

7. IF a PDF export fails due to a file system error or rendering exception (e.g., permission
   denied, disk full, reportlab rendering error), THEN THE Export_Engine SHALL display an
   error dialog describing the failure, SHALL delete any partially written file at the chosen
   path, and SHALL NOT crash the Application.

8. WHEN the Export_Engine detects that `reportlab` is not installed, THE Application SHALL
   display an informative error dialog instructing the user to run `pip install reportlab`,
   and SHALL NOT crash.

9. WHEN the user cancels the save-file dialog without confirming a path, THE Export_Engine
   SHALL take no action and leave the current application state unchanged.

---

### Requirement 8: GUI Visual Improvements

**User Story:** As a user, I want the application's interface to look more polished and
prominent, so that the tool feels professional and the most important information stands out.

#### Acceptance Criteria

1. THE Application SHALL display each step tab label with a numbered Unicode icon prefix:
   "① Step 1: Baseline Correction", "② Step 2: Peak Detection",
   "③ Step 3: Element Identification", "④ Step 4: Elemental Preferences",
   "⑤ Step 5: Validation", so that the pipeline order is immediately visible in the tab bar.

2. WHEN Step4_Widget completes a competition analysis, THE Step4_Widget SHALL display a
   summary statistics banner showing: primary element name, its Wins count, total elements
   analysed, and total peaks analysed; using C_ACCENT2 as the highlight colour for values.
   BEFORE any analysis is run, the banner SHALL display placeholder text "Run analysis to
   see summary".

3. WHEN Step4_Widget completes a competition analysis, THE Step4_Widget SHALL display the
   primary element name in a prominent label (font size ≥ 14 pt, colour C_ACCENT2, bold).
   IF no analysis has been run yet, THE Step4_Widget SHALL display "—" in the primary
   element label.

4. WHEN Step5_Widget completes a validation run, THE Step5_Widget SHALL display the mean VC
   value in a prominent label (font size ≥ 14 pt, bold) coloured using the Quality_Tier of
   the mean VC: > 0.95 → C_SUCCESS, 0.85–0.95 → C_ACCENT, 0.70–0.85 → C_WARN,
   < 0.70 → C_ERROR. IF no validation has been run yet, THE Step5_Widget SHALL display
   "—" in the mean VC label.

5. WHEN Step5_Widget completes a validation run, THE Step5_Widget SHALL display a summary
   statistics banner showing: mean VC, total wavelengths validated, and count per
   Quality_Tier; using C_ACCENT2 as the highlight colour for values.
   BEFORE any validation is run, the banner SHALL display placeholder text
   "Run validation to see summary".

6. THE Application SHALL apply consistent 8 px spacing and 8 px margin to all group boxes,
   button rows, and chart containers throughout Step 4 and Step 5.

7. WHEN a long-running operation (analysis in Step4_Widget or validation in Step5_Widget)
   is in progress, THE Application SHALL disable the primary trigger button (Analyze
   Competition or Validate Spectrum) and SHALL display a visible progress indicator
   (spinner or indeterminate progress bar) until the operation completes or fails.

---

### Requirement 9: Chart Interactivity and Layout

**User Story:** As a spectral analyst, I want charts to be embedded directly in the
application and be reasonably interactive, so that I do not need to switch to an external
window to inspect plot details.

#### Acceptance Criteria

1. THE Chart_Engine SHALL embed all charts (Ranking_Chart, Score_Scatter, VC_Histogram) as
   inline `matplotlib.backends.backend_qtagg.FigureCanvasQTAgg` widgets inside the
   respective step widgets; no chart SHALL open in a separate pop-up window.

2. THE Chart_Engine SHALL include a `matplotlib.backends.backend_qtagg.NavigationToolbar2QT`
   toolbar below each embedded FigureCanvasQTAgg so the user can pan, zoom, and save
   figures from within the Application.

3. WHEN Step4_Widget analysis results are updated by a new run, THE Chart_Engine SHALL
   refresh the Ranking_Chart and Score_Scatter by clearing and redrawing on the existing
   FigureCanvasQTAgg objects, without creating new canvas widgets; zoom and pan state SHALL
   be reset to the home view on each refresh.

4. WHEN Step5_Widget validation results are updated by a new run, THE Chart_Engine SHALL
   refresh the VC_Histogram by clearing and redrawing on the existing FigureCanvasQTAgg
   object, without creating new canvas widgets; zoom and pan state SHALL be reset to the
   home view on each refresh.

5. THE Chart_Engine SHALL set a minimum canvas height of 220 px and minimum canvas width of
   300 px for each embedded chart.

6. IF a chart rendering operation raises an exception, THEN THE Chart_Engine SHALL display a
   placeholder message "Chart unavailable" centred in the affected axes, SHALL log the
   exception, and SHALL NOT propagate the exception or crash the Application.

---

### Requirement 10: Export Button State Management

**User Story:** As a user, I want export buttons to be enabled only when data is available,
so that I am not presented with buttons that would fail silently.

#### Acceptance Criteria

1. WHEN Step4_Widget is first loaded (before any analysis is run), THE Step4_Widget SHALL
   render "Export CSV" and "Export PNG" buttons in the disabled state.

2. WHEN Step5_Widget is first loaded (before any validation is run), THE Step5_Widget SHALL
   render "Export CSV", "Export PNG", and "Export PDF Report" buttons in the disabled state.

3. WHEN Step4_Widget completes a competition analysis successfully (analysis_results is
   populated without error), THE Step4_Widget SHALL enable the "Export CSV" and "Export PNG"
   buttons.

4. WHEN Step5_Widget completes a validation run successfully (validation_results is populated
   without error), THE Step5_Widget SHALL enable the "Export CSV", "Export PNG", and
   "Export PDF Report" buttons.

5. WHEN a new analysis or validation run starts, THE Application SHALL re-disable the
   corresponding export buttons and keep them disabled until the new run completes
   successfully or fails.

6. WHEN the user hovers over a disabled export button, THE Application SHALL display a
   tooltip with the text "No data — run analysis first".
