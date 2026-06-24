# Implementation Plan

- [x] 1. Write bug condition exploration tests
  - **Property 1: Bug Condition** - NameError and AttributeError on Four Buggy Paths
  - **CRITICAL**: These tests MUST FAIL on unfixed code — failure confirms the bugs exist
  - **DO NOT attempt to fix the tests or the code when they fail**
  - **NOTE**: These tests encode expected behavior — they will validate the fix when they pass after implementation
  - **GOAL**: Surface counterexamples that demonstrate each of the four bugs exists
  - **Scoped PBT Approach**: Each test targets one deterministic crash, making them concrete and reproducible
  - Test 1.a — Bug 1: Instantiate `Step4Widget`, set `self.analysis_results` to mock DataFrames, call `_on_save_clicked()` directly (mock `QFileDialog.getSaveFileName` to return a temp path). Assert `NameError` is raised on unfixed code.
  - Test 1.b — Bug 2: Instantiate `Step5Widget`, mock `QFileDialog.getOpenFileName` to return a temp CSV path, call `_on_load_wavelengths()`. Assert `AttributeError` is raised on unfixed code.
  - Test 1.c — Bug 3: Instantiate `Step5Widget`, set `processed_selector` and `reference_selector` to return temp CSV paths, set `target_wavelengths`, call `_validate_worker()`. Assert `AttributeError` is raised on unfixed code.
  - Test 1.d — Bug 4: In a fresh import, verify `import pandas as pd` is at the module top (not bottom); on unfixed code this check fails because the import is misplaced.
  - Run all four tests on **UNFIXED** code
  - **EXPECTED OUTCOME**: All four tests FAIL (proves all four bugs exist)
  - Document counterexamples (exact exception type and message for each)
  - Mark task complete when tests are written, run, and failures are documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Buggy Paths Unchanged
  - **IMPORTANT**: Follow observation-first methodology — observe actual outputs on unfixed code first
  - Observe: `Step4Widget._analyze_worker()` with a valid matching CSV produces a dict with `ranking`, `competition`, `winner_lines` DataFrames → record shape and column names
  - Observe: `Step5Widget._on_manual_wavelengths()` with `"300.0\n400.0\n500.0"` sets `target_wavelengths = [300.0, 400.0, 500.0]`
  - Observe: The `.txt` branch of `Step5Widget._on_load_wavelengths()` with a temp text file sets the correct wavelength list
  - Observe: `Step5Widget._populate_results_table()` with a mock `validation_results` DataFrame populates `results_table` with the correct row count and cell values
  - Observe: `Step5Widget._on_save_clicked()` with a valid `validation_results` writes a correct CSV (Step 5 save — not the buggy Step 4 save)
  - Write property-based tests that assert all observed behaviors hold across many generated inputs (varied DataFrames, varied wavelength lists, varied CSV structures)
  - Run all preservation tests on **UNFIXED** code
  - **EXPECTED OUTCOME**: All preservation tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3. Fix four bugs in step4_widget.py and step5_widget.py

  - [x] 3.1 Bug 1 — Remove dead `CSVWriter()` instantiation from `step4_widget.py`
    - Open `src/gui/step4_widget.py`, method `_on_save_clicked`
    - Delete the single line `writer = CSVWriter()`
    - The three `df.to_csv()` calls below it already handle all file saving correctly
    - Do NOT add a `CSVWriter` import — it is not needed
    - Do NOT change any other line in this method
    - _Bug_Condition: isBugCondition(CLICK_SAVE_RESULTS_STEP4) — `CSVWriter` is undefined in this module_
    - _Expected_Behavior: `_on_save_clicked` writes three CSV files without raising any exception_
    - _Preservation: `_analyze_worker` and table-population logic must remain unchanged_
    - _Requirements: 2.1, 3.1_

  - [x] 3.2 Bug 4 — Move `import pandas as pd` to top of `step5_widget.py`
    - Open `src/gui/step5_widget.py`
    - Remove `# Import pandas for isna check` comment and `import pandas as pd` from the bottom of the file
    - Add `import pandas as pd` to the top-of-file import block, after the existing third-party imports (e.g., after `import numpy as np`)
    - Do NOT change any other line
    - _Bug_Condition: isBugCondition(POPULATE_RESULTS_TABLE_WITH_PD_NOT_YET_IMPORTED)_
    - _Expected_Behavior: `pd` is available throughout the module at class-definition time_
    - _Preservation: All method logic remains identical_
    - _Requirements: 2.4, 3.4, 3.6_

  - [x] 3.3 Bug 2 — Fix `_on_load_wavelengths` in `step5_widget.py`
    - Open `src/gui/step5_widget.py`, method `_on_load_wavelengths`
    - Inside the `if filepath.endswith('.csv'):` branch, replace:
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
    - The `reader` variable is unused after this replacement — remove it
    - Do NOT change the `.txt` file branch or any other part of the method
    - _Bug_Condition: isBugCondition(CLICK_LOAD_WAVELENGTHS_CSV_STEP5) — `read_generic_csv` does not exist on `CSVReader`_
    - _Expected_Behavior: Wavelengths are read from the first column of the CSV and stored in `self.target_wavelengths`_
    - _Preservation: `.txt` file loading path, manual entry, and all other Step 5 interactions unchanged_
    - _Requirements: 2.2, 3.2, 3.3_

  - [x] 3.4 Bug 3 — Fix `_validate_worker` in `step5_widget.py`
    - Open `src/gui/step5_widget.py`, method `_validate_worker`
    - Replace:
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
    - Note: `ValidationAnalyzer.validate_spectrum()` calls `self.normalize_spectrum_columns()` internally, so passing a raw DataFrame is correct
    - The `CSVReader` import at the top of the file may remain — do NOT remove it
    - Do NOT change the `ValidationAnalyzer` construction, the `params` dict, or the `validate_spectrum` call
    - _Bug_Condition: isBugCondition(CLICK_VALIDATE_SPECTRUM_STEP5) — `read_generic_csv` does not exist on `CSVReader`_
    - _Expected_Behavior: Both spectra DataFrames are loaded and passed to `ValidationAnalyzer.validate_spectrum()` without error_
    - _Preservation: Analyzer parameters, result storage, and all downstream validation logic unchanged_
    - _Requirements: 2.3, 3.4, 3.5_

  - [x] 3.5 Verify bug condition exploration tests now pass
    - **Property 1: Expected Behavior** - All Four Buggy Paths Resolved
    - **IMPORTANT**: Re-run the SAME tests from task 1 — do NOT write new tests
    - The tests from task 1 encode the expected (fixed) behavior
    - When these tests pass, it confirms all four bugs are resolved
    - Run all four exploration tests (1.a, 1.b, 1.c, 1.d) from step 1
    - **EXPECTED OUTCOME**: All four tests PASS (confirms all bugs are fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.6 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Buggy Paths Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run all preservation property tests from step 2
    - **EXPECTED OUTCOME**: All preservation tests still PASS (confirms no regressions)
    - Confirm no regressions in Step 4 analysis, Step 5 manual entry, txt loading, table population, or report saving

- [x] 4. Checkpoint — Ensure all tests pass
  - Run the full test suite to confirm no regressions in any other widget or module
  - Ensure all four exploration tests pass (bugs fixed)
  - Ensure all preservation tests pass (no regressions)
  - Ask the user if any questions arise before marking complete
