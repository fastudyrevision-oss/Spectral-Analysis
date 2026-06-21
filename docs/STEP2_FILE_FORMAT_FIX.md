# STEP 2 GUI FIX - File Format Error

## Problem
When loading a file in Step 2 (Peak Detection) that doesn't have a "Corrected" column, the GUI crashes with:
```
AttributeError: 'RawSpectra' object has no attribute 'corrected'
```

## Root Cause
The file you loaded was likely from the **Peaks Detection output folder** (`detected_peaks (Input file).csv`), which contains detected peaks data rather than the processed spectrum.

Step 2 requires the **output from Step 1** (Baseline Correction), which contains:
- Wavelength
- Raw
- Smoothed_SG
- Baseline_ALS
- **Corrected** ← This is what Step 2 needs!

## Solution Applied
The Step 2 widget now:
1. ✅ Checks if the file has a "Corrected" column
2. ✅ Detects if you're trying to load a detected_peaks file
3. ✅ Shows a **helpful error message** telling you which file to use
4. ✅ Prevents the crash

## How to Use Step 2 Correctly

### Correct Workflow:
```
Step 1: Load raw data (soil3-unprocessed.csv)
        ↓ (Click "Process")
        ↓ Outputs: SG_ALS_LIBS_processed.csv ✓ USE THIS IN STEP 2

Step 2: Load SG_ALS_LIBS_processed.csv (from Step 1 output)
        ↓ (Click "Detect Peaks")
        ↓ Outputs: detected_peaks.csv
```

### Common Mistake (Now Fixed):
❌ Loading `detected_peaks.csv` in Step 2  
→ **Now shows friendly error message instead of crash**

## Files to Use

| Step | Input File | Output File |
|------|-----------|------------|
| 1 | `soil3-unprocessed.csv` | `SG_ALS_LIBS_processed.csv` ✓ Use this in Step 2 |
| 2 | `SG_ALS_LIBS_processed.csv` | `detected_peaks.csv` |
| 3 | `detected_peaks.csv` + NIST database | `LIBS_matching_results.csv` |

## How to Use GUI Correctly

### Option 1: Complete Sequential Workflow (Recommended)
```bash
1. Open GUI: python gui_launcher.py
2. Go to Step 1 tab:
   - Select: soil3-unprocessed.csv
   - Click: Process
   - Click: Save Results
   
3. Go to Step 2 tab:
   - Select: SG_ALS_LIBS_processed.csv (from Step 1 output)
   - Click: Detect Peaks
   - Click: Save Results
   
4. Go to Step 3 tab:
   - Select Peaks: detected_peaks.csv (from Step 2 output)
   - Select NIST DB: NIST-Ca.csv
   - Click: Match Peaks
   - Click: Save Results
```

### Option 2: Skip Step 1 (If You Have Pre-Processed Data)
If you already have a processed spectrum file:
- Make sure it has these columns:
  - Wavelength (or similar name)
  - Corrected (or similar name)
- Load it in Step 2

### Option 3: Command Line (All Steps At Once)
```bash
python test_pipeline.py
```

## Error Messages (Now Improved)

### What You'll See If You Load The Wrong File:
```
Error: This file appears to be a detected peaks output file.

Step 2 requires the PROCESSED spectrum output from Step 1.

Please load the 'SG_ALS_LIBS_processed.csv' file from Step 1 output.
```

This tells you exactly what went wrong and how to fix it!

## Fix Summary
✅ Better error detection  
✅ Helpful error messages  
✅ No more crashes  
✅ Clear guidance on which files to use  

The GUI is now more user-friendly and will guide you to use the correct files!

---

**Status**: ✅ FIXED  
**Date**: 2026-06-21  
