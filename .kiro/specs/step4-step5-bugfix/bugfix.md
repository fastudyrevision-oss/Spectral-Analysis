# Bugfix Requirements Document

## Introduction

Two GUI widget files — `src/gui/step4_widget.py` and `src/gui/step5_widget.py` — contain four bugs that crash the application when users interact with specific UI actions. All four bugs are incorrect method calls or misplaced imports; no logic, algorithm, or precision changes are involved.

**Bug 1** (`step4_widget.py`): Clicking "Save Results" raises `NameError: name 'CSVWriter' is not defined` because `CSVWriter` is never imported but is instantiated before the actual file-saving logic (which uses `df.to_csv()` directly).

**Bug 2** (`step5_widget.py`): Loading wavelengths from a CSV file raises `AttributeError: 'CSVReader' object has no attribute 'read_generic_csv'` because `read_generic_csv` does not exist on `CSVReader`.

**Bug 3** (`step5_widget.py`): Running spectrum validation raises `AttributeError: 'CSVReader' object has no attribute 'read_generic_csv'` for the same reason as Bug 2, but in a different method.

**Bug 4** (`step5_widget.py`): `import pandas as pd` is placed at the bottom of the file, after the class definition, while `pd.isna()` is used inside `_populate_results_table`. This is fragile and can produce a `NameError` in certain execution paths.

---

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the user clicks "Save Results" in Step 4 THEN the system raises `NameError: name 'CSVWriter' is not defined` before any file is saved, because `CSVWriter` is instantiated on line `writer = CSVWriter()` without being imported.

1.2 WHEN the user clicks "Load from File..." to load wavelengths in Step 5 and selects a CSV file THEN the system raises `AttributeError: 'CSVReader' object has no attribute 'read_generic_csv'` because `CSVReader` has no such method.

1.3 WHEN the user clicks "Validate Spectrum" in Step 5 THEN the system raises `AttributeError: 'CSVReader' object has no attribute 'read_generic_csv'` while attempting to load the processed and reference spectra inside the worker thread.

1.4 WHEN `_populate_results_table` executes and `import pandas as pd` has not yet been reached in the module's top-level execution order THEN the system raises `NameError: name 'pd' is not defined` because the import is placed at the bottom of the file, after the class definition.

### Expected Behavior (Correct)

2.1 WHEN the user clicks "Save Results" in Step 4 THEN the system SHALL save the ranking, competition, and winner-lines DataFrames to CSV files using `df.to_csv()` without crashing.

2.2 WHEN the user clicks "Load from File..." and selects a CSV file in Step 5 THEN the system SHALL load the file with `pd.read_csv()`, extract the first column as wavelengths, and display the wavelength count in the UI.

2.3 WHEN the user clicks "Validate Spectrum" in Step 5 THEN the system SHALL load the processed and reference spectra as raw DataFrames using `pd.read_csv()` and pass them to `ValidationAnalyzer.validate_spectrum()` without crashing.

2.4 WHEN any method in `Step5Widget` uses `pd.isna()` or any other `pandas` function THEN the system SHALL have `pandas` available as `pd` because `import pandas as pd` is placed at the top of the file with the other imports.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the user adds NIST matching files and clicks "Analyze Competition" in Step 4 THEN the system SHALL CONTINUE TO run the elemental preferences analysis and populate the results tables correctly.

3.2 WHEN the user clicks "Load from File..." and selects a plain text file (`.txt`) in Step 5 THEN the system SHALL CONTINUE TO read wavelengths line-by-line as before.

3.3 WHEN the user enters wavelengths manually via the dialog in Step 5 THEN the system SHALL CONTINUE TO parse and store the wavelengths correctly.

3.4 WHEN validation completes successfully in Step 5 THEN the system SHALL CONTINUE TO populate the results table and enable the "Save Report" button.

3.5 WHEN the user clicks "Save Report" in Step 5 THEN the system SHALL CONTINUE TO save validation results to a CSV file using `self.validation_results.to_csv()`.

3.6 WHEN all other UI interactions not related to the four buggy paths are performed THEN the system SHALL CONTINUE TO behave identically to the pre-fix state.
