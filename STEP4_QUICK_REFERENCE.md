# Step 4 - Quick Start Card

## 🎯 What to Upload

| ✅ YES | ❌ NO |
|--------|-------|
| `LIBS_matching_results*.csv` from Step 3 | Spectrum files from Step 1 |
| Matching results CSV | Peak detection output |
| Files from `NIST matching (3rd step)/` | NIST database files |
| Output files from Step 3 | Input files to Step 3 |

---

## 🚀 5-Minute Workflow

### 1. Click "Add Files..."
```
Look in: NIST matching (3rd step)
File:    LIBS_matching_results*.csv
```

### 2. See ✅ File Loaded
```
✅ 1 file(s): LIBS_matching_results (Output file).csv
✅ Loaded 1 file(s). Click 'Analyze Competition' to start analysis.
```

### 3. Click "Analyze Competition"
- Green button in the controls area
- Waits for analysis to complete

### 4. View Results
Three tabs appear automatically:
- **Ranking:** Elements by wins
- **Competition:** Peak-by-peak winners
- **Winners:** Wavelength details

### 5. Click "Save Results" (Optional)
Export results to CSV files for later review.

---

## 🆘 If Something Goes Wrong

| Error | Solution |
|-------|----------|
| "Please select at least one matching file" | Click "Add Files..." button |
| File not visible in dialog | Make sure you're in `NIST matching (3rd step)` folder |
| "Permission denied" | Close file if open in Excel |
| No results appear | Check Notes Panel (bottom of window) for error |

---

## 📁 File Location Reminder

```
Your Workspace/
├── NIST matching (3rd step)/
│   ├── NIST matching (3rd step)/
│   │   └── LIBS_matching_results (Output file).csv  ← SELECT THIS
│   └── nist_data/
└── [other folders]
```

---

## ✅ Expected Output

**Primary Element:** Ca (or Fe, Mg, etc. depending on your data)

**Element Ranking Table:**
```
Rank | Element | Wins | Total Score | Avg Score
-----|---------|------|-------------|----------
 1   |   Ca    |  45  |   42.3      |  0.940
 2   |   Fe    |  12  |   10.1      |  0.842
 3   |   Mg    |   8  |    7.2      |  0.900
```

**Peak Competition Table:**
```
Wavelength | Winner | Max Score | Competitors
-----------|--------|-----------|-------------
  500.1    |   Ca   |   0.95    |    Fe, Mg
  510.2    |   Fe   |   0.88    |    Ca, Mg
  520.3    |   Ca   |   0.92    |    Fe
```

---

## 🔄 Workflow Position

```
Step 1: Baseline Correction
    ↓
Step 2: Peak Detection
    ↓
Step 3: Element Identification  ← Output files here
    ↓
Step 4: Elemental Preferences  ← YOU ARE HERE
    ↓
Step 5: Validation
```

---

## ⚡ Pro Tips

💡 **Tip 1:** You can select multiple files at once (Ctrl+Click) to analyze different NIST database matches together

💡 **Tip 2:** Use Recent Files dropdown to quickly reload files you've analyzed before

💡 **Tip 3:** Check the Notes Panel at the bottom to see analysis progress and any issues

💡 **Tip 4:** Save results after analysis - creates output files for documentation

---

## ✨ New in v1.1

✅ Fixed CSV reading error  
✅ Added clear file selection instructions  
✅ Improved file display feedback  
✅ Added Notes Panel integration  
✅ Better error messages  

---

## 📞 Documentation

- **Detailed Guide:** STEP4_FILE_UPLOAD_GUIDE.md
- **Fix Details:** STEP4_FIX_SUMMARY.md
- **GUI Features:** GUI_ENHANCEMENTS.md

---

## ✅ Quick Checklist

Before starting Step 4:
- [ ] Completed Steps 1-3
- [ ] Step 3 output file exists
- [ ] File is in `NIST matching (3rd step)` folder
- [ ] File name contains "LIBS_matching_results"
- [ ] File is not open in Excel or other programs

Ready to go? → Click "Add Files..." to begin! ✨

---

**Version:** v1.1  
**Last Updated:** 2026-06-22  
**Status:** ✅ Ready
