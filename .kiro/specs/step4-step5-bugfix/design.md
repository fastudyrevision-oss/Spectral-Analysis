# Step 4 / Step 5 Bugfix Design

## Overview

Four bugs across two GUI widget files cause `NameError` or `AttributeError` crashes when users click specific buttons. The fixes are surgical removals or replacements of single lines — no logic, algorithm, or precision changes are required.

| # | File | Method | Error | Fix |
|---|------|--------|-------|-----|
| 1 | `step4_widget.py` | `_on_save_clicked` | `NameError: name 'CSVWriter' is not defined` | Remove `writer = CSVWriter()` |
| 2 | `step5_widget.py` | `_on_load_wavelengths` | `AttributeError: 'CSVReader' object has no attribute 'read_generic_csv'` | Replace with `pd.read_csv(filepath)` + first-column extraction |
| 3 | `step5_widget.py` | `_validate_worker` | `AttributeError: 'CSVReader' object has no attribute 'read_generic_csv'` | Replace both calls with `pd.read_csv(...)` |
| 4 | `step5_widget.py` | module level | `NameError: name 'pd' is not defined` (fragile) | Move `import pandas as pd` to top of file |

---

## Glossary

- **Bug_Condition (C)**: The condition that triggers a crash — any of the four buggy code paths being reached during execution.
- **Property (P)**: The desired behavior — the affected action completes without raising an exception, and the expected side-effect (file saved, data loaded, table populated) occurs.
- **Preservation**: All other GUI interactions and data-processing paths that must remain unchanged after the fix.
- **`CSVReader`**: The class in `src/io/file_reader.py` with methods `read_raw_spectra`, `read_detected_peaks`, and `read_nist_database`. It has **no** `read_generic_csv` method.
- **`CSVWriter`**: The class in `src/io/file_writer.py`. It is **not imported** in `step4_widget.py`.
- **`_on_save_clicked`**: The Step 4 method that saves analysis results to CSV. The actual saving is done by calling `df.to_csv()` directly on the DataFrames; `CSVWriter` is not needed.
- **`_on_load_wavelengths`**: The Step 5 method that loads target wavelengths from a user-selected CSV or text file.
- **`_validate_worker`**: The Step 5 worker-thread method that loads processed and reference spectra and runs `ValidationAnalyzer.validate_spectrum()`.
- **`_populate_results_table`**: The Step 5 method that fills the results table; it calls `pd.isna()`.

---

## Bug Details

### Bug Condition

A crash occurs whenever an execution path reaches one of the four buggy lines:

1. `writer = CSVWriter()` inside `_on_save_clicked` — `CSVWriter` is undefined in this module.
2. `reader.read_generic_csv(filepath)` inside `_on_load_wavelengths` — method does not exist on `CSVReader`.
3. `reader.read_generic_csv(...)` inside `_validate_worker` (×2 calls) — same nonexistent method.
4. `pd.isna(vc_val)` inside `_populate_results_table` when the module-level `import pandas as pd` at the bottom of the file has not yet been executed (fragile; guaranteed crash if the class is imported before the bottom of the module is evaluated in some import paths).

**Formal Specification:**

```
FUNCTION isBugCondition(action)
  INPUT: action of type UserAction
  OUTPUT: boolean

  RETURN (action = CLICK_SAVE_RESULTS_STEP4)
      OR (action = CLICK_LOAD_WAVELENGTHS_CSV_STEP5)
      OR (action = CLICK_VALIDATE_SPECTRUM_STEP5)
      OR (action = POPULATE_RESULTS_TABLE_WITH_PD_NOT_YET_IMPORTED)
END FUNCTION
```

### Examples

- **Bug 1**: User opens Step 4, adds a matching file, runs analysis, then clicks "Save Results" → `NameError: name 'CSVWriter' is not defined` raised immediately; no files are written.
- **Bug 2**: User opens Step 5, clicks "Load from File...", selects a `.csv` → `AttributeError: 'CSVReader' object has no attribute 'read_generic_csv'`; wavelength list stays empty.
- **Bug 3**: User opens Step 5, selects processed and reference spectra files, enters wavelengths, clicks "Validate Spectrum" → worker thread raises `AttributeError: 'CSVReader' object has no attribute 'read_generic_csv'`; validation never completes.
- **Bug 4**: `pd.isna()` is called inside `_populate_results_table` but `import pandas as pd` is at the bottom of the file; in an import environment where class methods are accessed before the bottom of the module is evaluated, `NameError: name 'pd' is not defined` is raised.

---

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Step 4 elemental-preferences analysis (file loading, `ElementalPreferencesAnalyzer.analyze()`, table population) must continue to work exactly as before.
- Step 5 manual wavelength entry via `QInputDialog` must continue to work exactly as before.
- Step 5 wavelength loading from plain-text `.txt` files must continue to work exactly as before.
- Step 5 validation results table population (row count, column values, sorting) must continue to work exactly as before.
- Step 5 "Save Report" (`self.validation_results.to_csv()`) must continue to work exactly as before.
- All other Step 1–3 widgets and their interactions must be completely unaffected.

**Scope:**
All execution paths that do NOT reach the four buggy lines should be completely unaffected by this fix. The fix touches only:
- One line removal in `step4_widget.py`
- Two method-call replacements in `step5_widget.py`
- One import relocation in `step5_widget.py`

---

## Hypothesized Root Cause

1. **Missing import / dead instantiation (Bug 1)**: `CSVWriter` was never added to the import block of `step4_widget.py`. The `writer` variable that was presumably planned for use was later superseded by calling `df.to_csv()` directly, but the vestigial instantiation line was never removed.

2. **Nonexistent method call (Bugs 2 & 3)**: `CSVReader` exposes three specific domain methods (`read_raw_spectra`, `read_detected_peaks`, `read_nist_database`). A generic `read_generic_csv` helper was never implemented. The Step 5 code was written assuming such a method existed, likely as a shortcut for reading arbitrary CSV files, but it was never added to the class.

3. **Import at end of module (Bug 4)**: `import pandas as pd` was placed at the bottom of `step5_widget.py` as an afterthought. While Python allows this in normal sequential execution, placing it outside the standard import block at the top of the file is fragile — it violates PEP 8 and can produce `NameError` in some import/reload scenarios.

---

## Correctness Properties

Property 1: Bug Condition — Affected Actions Complete Without Crashing

_For any_ user action where `isBugCondition(action)` is true (clicking "Save Results" in Step 4, clicking "Load from File..." with a CSV in Step 5, clicking "Validate Spectrum" in Step 5, or `_populate_results_table` running with `pd` not yet available), the fixed code SHALL complete that action without raising a `NameError` or `AttributeError`, and the expected side-effect (files written, wavelengths loaded, validation run, or table populated) SHALL occur.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation — Non-Buggy Paths Unchanged

_For any_ user action where `isBugCondition(action)` is false (analysis in Step 4, manual wavelength entry, txt-file wavelength loading, saving the validation report, or any other interaction), the fixed code SHALL produce exactly the same behavior as the original code, preserving all existing functionality for those paths.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

---

## Fix Implementation

### Changes Required

#### File: `src/gui/step4_widget.py`

**Method:** `_on_save_clicked`

**Specific Changes:**

1. **Remove dead instantiation (Bug 1)**: Delete the line `writer = CSVWriter()`. The three `df.to_csv()` calls that follow it already perform the saving correctly. No other changes to this method are needed.

---

#### File: `src/gui/step5_widget.py`

**Change 1 — Move pandas import (Bug 4):**  
Move `import pandas as pd` from the bottom of the file (currently placed after the class definition) to the top-of-file import block, alongside the other standard-library and third-party imports.

**Change 2 — Fix `_on_load_wavelengths` (Bug 2):**  
Replace:
```python
reader = CSVReader()
df = reader.read_generic_csv(filepath)
# Get first column as wavelengths
wavelengths = df.iloc[:, 0].values
```
With:
```python
df = pd.read_csv(filepath)
# Get first column as wavelengths
wavelengths = df.iloc[:, 0].values
```
The `reader` variable is only used for this one call within the CSV branch, so it can be removed entirely.

**Change 3 — Fix `_validate_worker` (Bug 3):**  
Replace:
```python
reader = CSVReader()

# Load spectra
processed = reader.read_generic_csv(
    str(self.processed_selector.get_filepath())
)
reference = reader.read_generic_csv(
    str(self.reference_selector.get_filepath())
)
```
With:
```python
# Load spectra
processed = pd.read_csv(str(self.processed_selector.get_filepath()))
reference = pd.read_csv(str(self.reference_selector.get_filepath()))
```
`ValidationAnalyzer.validate_spectrum()` already calls `self.normalize_spectrum_columns()` internally, so passing a raw DataFrame is correct. The `CSVReader` import at the top of the file can remain as-is (it may be used elsewhere or in future work).

---

## Testing Strategy

### Validation Approach

The testing strategy follows the two-phase bug-condition methodology: first, write tests that run on the **unfixed** code to confirm each bug manifests as described (exploration); then, write preservation tests that observe correct behavior on non-buggy paths, verify those pass on unfixed code, and re-verify they still pass after the fix.

---

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate all four bugs exist on the unfixed code, and confirm the root-cause analysis.

**Test Plan**: Patch or isolate each affected method and call it directly with the minimum required context. Run on the **unfixed** code and expect failures.

**Test Cases:**

1. **Bug 1 — Dead CSVWriter instantiation**: Call `Step4Widget._on_save_clicked()` with mock analysis results. On unfixed code → `NameError: name 'CSVWriter' is not defined`.
2. **Bug 2 — read_generic_csv in _on_load_wavelengths**: Simulate a CSV filepath being passed through the CSV branch of `_on_load_wavelengths`. On unfixed code → `AttributeError: 'CSVReader' object has no attribute 'read_generic_csv'`.
3. **Bug 3 — read_generic_csv in _validate_worker**: Call `_validate_worker()` with valid file paths for processed and reference spectra. On unfixed code → `AttributeError: 'CSVReader' object has no attribute 'read_generic_csv'`.
4. **Bug 4 — pandas import position**: Import `step5_widget` in a fresh interpreter, access `Step5Widget._populate_results_table` before the module bottom is evaluated, and call `pd.isna()`. On unfixed code → fragile / `NameError`.

**Expected Counterexamples:**
- `NameError: name 'CSVWriter' is not defined` when `_on_save_clicked` runs.
- `AttributeError: 'CSVReader' object has no attribute 'read_generic_csv'` for both Step 5 CSV-loading paths.
- `pd` potentially unresolvable if module evaluation stops mid-class.

---

### Fix Checking

**Goal**: Verify that for all inputs where `isBugCondition(action)` holds, the fixed code produces the expected behavior (no exception, correct side-effect).

**Pseudocode:**
```
FOR ALL action WHERE isBugCondition(action) DO
  result := execute_fixed(action)
  ASSERT no_exception_raised(result)
  ASSERT expected_side_effect(result)
END FOR
```

---

### Preservation Checking

**Goal**: Verify that for all actions where `isBugCondition(action)` is false, the fixed code produces the same result as the original code.

**Pseudocode:**
```
FOR ALL action WHERE NOT isBugCondition(action) DO
  ASSERT execute_original(action) = execute_fixed(action)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because it generates many varied inputs automatically and provides stronger guarantees that non-buggy paths are unaffected.

**Test Cases:**

1. **Step 4 analysis preservation**: Run `_analyze_worker` with a valid matching CSV on both unfixed and fixed code → results must be identical.
2. **Step 5 manual wavelength entry preservation**: Call `_on_manual_wavelengths` with a valid multiline string → `target_wavelengths` list must be identical before and after fix.
3. **Step 5 .txt file wavelength loading preservation**: Call the `.txt` branch of `_on_load_wavelengths` → wavelength list must be identical.
4. **Step 5 results table population preservation**: Call `_populate_results_table` with a valid `validation_results` DataFrame → row count and cell values must be identical.
5. **Step 5 save report preservation**: Call `_on_save_clicked` in Step 5 with a valid `validation_results` → CSV file produced must be identical.

---

### Unit Tests

- Test that `_on_save_clicked` in Step 4 writes three CSV files and does not raise any exception.
- Test that `_on_load_wavelengths` with a CSV file returns the correct wavelength list.
- Test that `_validate_worker` correctly loads two DataFrames and passes them to `ValidationAnalyzer`.
- Test that `pd` is available at class definition time in `step5_widget.py`.

### Property-Based Tests

- Generate random DataFrames as analysis results and verify Step 4 save produces matching CSV output for all of them.
- Generate random valid CSV content as wavelength files and verify the first-column extraction always produces the correct list.
- Generate random pairs of spectra DataFrames and verify `_validate_worker` passes them through to `ValidationAnalyzer` without errors.

### Integration Tests

- Full Step 4 flow: add file → analyze → save results → verify files on disk.
- Full Step 5 load-wavelengths flow: load CSV → validate spectrum → save report.
- Verify no regression in Step 4 analysis results table population after fix.
- Verify no regression in Step 5 validation results table after fix.
