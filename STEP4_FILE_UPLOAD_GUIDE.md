# Step 4: Elemental Preferences - File Upload Guide

## 📋 Overview

**Step 4** analyzes which elements best match detected peaks by examining competition between elements. It takes the matching results from **Step 3** and ranks elements based on their competitive scoring.

---

## 🎯 Which Files to Upload?

### ✅ **CORRECT Files** (Upload These)

**File Type:** NIST Matching Results CSV  
**Source:** Output from **Step 3: NIST Element Identification**  
**File Pattern:** `LIBS_matching_results*.csv`

**Location in your workspace:**
```
NIST matching (3rd step)/
└── LIBS_matching_results (Output file).csv  ← Upload this!
```

**File Content:**
The file should contain columns like:
- `Wavelength (nm)` - Detected peak wavelengths
- `Element` - Matched element names
- `NIST_Wavelength (nm)` - NIST database wavelength
- `Score` - Matching score/confidence
- Plus other matching metadata

### Example Correct File Path:
```
C:\Users\User\Desktop\Spectral Analysis\NIST matching (3rd step)\LIBS_matching_results (Output file).csv
```

---

## ❌ **INCORRECT Files** (Do NOT Upload These)

| File Type | Location | Why Not? |
|-----------|----------|---------|
| Raw spectrum | `SG-ALS spectral processing (1st step)/` | Wrong format - needs matching results |
| Detected peaks | `Peaks detection (2nd step)/` | Wrong format - needs matching results |
| NIST database | `NIST database/` | Wrong format - reference data, not results |
| Elemental preferences | `Elemental preference (4th step)/` | Wrong step - this IS the output from Step 4 |

---

## 🚀 Step-by-Step Instructions

### 1️⃣ Check if You Have the Right File

✅ **File exists at:** `NIST matching (3rd step)/LIBS_matching_results (Output file).csv`  
✅ **File size:** Should be > 1 KB (has data)  
✅ **File format:** CSV with matching results  

### 2️⃣ Open Step 4 Tab

In the GUI, navigate to: **Step 4: Elemental Preferences & Peak Competition**

### 3️⃣ Add Files

**You will see:**
```
📋 Instructions: Select NIST matching result files from Step 3.
Look for files named 'LIBS_matching_results*.csv' in the 
'NIST matching (3rd step)' folder.
```

Click: **"Add Files..."** button

### 4️⃣ Select File(s)

In the file dialog:
1. Navigate to: `NIST matching (3rd step)`
2. Find: `LIBS_matching_results (Output file).csv`
3. Click it to select it
4. Click **"Open"** to add to Step 4

### 5️⃣ You Can Add Multiple Files

If you have multiple NIST matching results from different analyses:
- They will be automatically combined
- Elements will be ranked across all files
- Provides comprehensive analysis

**Example with multiple files:**
```
NIST matching (3rd step)/
├── LIBS_matching_results (Output file).csv
├── LIBS_matching_results Fe.csv
└── LIBS_matching_results Fe II.csv
```

All three can be uploaded at once using Ctrl+Click or Shift+Click in the file dialog.

### 6️⃣ Verify Files Are Loaded

**You should see:**
```
✅ 1 file(s): LIBS_matching_results (Output file).csv
✅ Loaded 1 file(s). Click 'Analyze Competition' to start analysis.
```

### 7️⃣ Click "Analyze Competition"

Once files are selected, click the blue **"Analyze Competition"** button.

---

## 🔍 Troubleshooting

### Error: "Please select at least one matching file"
**Solution:** Click "Add Files..." and select a CSV file from Step 3

### Error: "No data loaded from files"
**Cause:** File is empty or not a matching results file  
**Solution:** Verify the file contains data by:
- Right-click file → Open with Notepad
- Check it has more than just headers
- Verify columns like "Element" and "Score" exist

### Error: "Permission denied" when loading file
**Cause:** File is open in another program (Excel, etc.)  
**Solution:** Close the file in other programs first

### File not showing in Recent Files
**Cause:** This is the first time you're loading this file  
**Solution:** It will appear in Recent files after first load

---

## 📊 What Happens After Upload

### Analysis Results Show:

**Tab 1: Element Ranking**
- Ranked list of elements by "wins" (how many peaks they won)
- Shows total score and average score per element
- **Primary element:** Top-ranked element from the list

**Tab 2: Peak Competition**
- For each wavelength, shows which element won
- Shows competing elements and their scores
- Identifies close matches and clear winners

**Tab 3: Winner Lines**
- Detailed wavelength information for winning elements
- Shows confidence scores
- Number of competitors for each line

---

## 💡 Pro Tips

✨ **Tip 1:** Always run Step 3 first to get matching results  
✨ **Tip 2:** You can upload multiple matching result files for comprehensive analysis  
✨ **Tip 3:** Use Recent Files dropdown to quickly reload files you've analyzed before  
✨ **Tip 4:** Check Notes Panel (bottom of window) for processing status and any errors  

---

## 🔗 Related Steps

| Step | Task | Output |
|------|------|--------|
| Step 1 | Baseline Correction | `SG_ALS_LIBS_processed.csv` |
| Step 2 | Peak Detection | `detected_peaks.csv` |
| **Step 3** | **Element Identification** | **`LIBS_matching_results.csv`** ← **Use This** |
| **Step 4** | **Elemental Preferences** | **Competition Analysis** |
| Step 5 | Validation | Correlation Results |

---

## ✅ Success Checklist

Before uploading, verify:

- [ ] I have completed **Step 3** to generate matching results
- [ ] File exists: `NIST matching (3rd step)/LIBS_matching_results*.csv`
- [ ] File size is > 1 KB (contains data)
- [ ] File is not open in Excel or other programs
- [ ] I'm in the **Step 4** tab of the GUI
- [ ] File path shows the correct location

---

## 📞 Need More Help?

1. **Check GUI Instructions:** Read the blue instruction box at top of Step 4
2. **Review Notes Panel:** See bottom of window for error messages
3. **Check File Format:** Open file in Notepad to verify it's CSV format
4. **Test with Provided Data:** Use sample files from the workspace folders

---

## 🎯 Expected Workflow

```
1. Complete Steps 1-3 ✅
        ↓
2. Go to Step 4 ✅
        ↓
3. Click "Add Files..." ✅
        ↓
4. Select LIBS_matching_results.csv ✅
        ↓
5. Verify file loaded (see ✅ checkmark) ✅
        ↓
6. Click "Analyze Competition" ✅
        ↓
7. View results in three tabs ✅
        ↓
8. Click "Save Results" (optional) ✅
```

---

## 📈 Example Session

**What you type in your head:** "I want to analyze element preferences"

**What you do:**
1. Open Step 4
2. Click "Add Files..."
3. Navigate to `NIST matching (3rd step)`
4. Select `LIBS_matching_results (Output file).csv`
5. Click "Open"
6. See: `✅ 1 file(s): LIBS_matching_results (Output file).csv`
7. Click "Analyze Competition"
8. **BOOM!** → See element rankings appear in the tables

**What happens in the background:**
- GUI reads the CSV file using pandas
- Passes data to ElementalPreferencesAnalyzer
- Analyzer finds winning elements for each peak
- Rankings calculated
- Three result tables populated

---

**Version:** v1.1 (Updated 2026-06-22)  
**Status:** ✅ Ready for Production
