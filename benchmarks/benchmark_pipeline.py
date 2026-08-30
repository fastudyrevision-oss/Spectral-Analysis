# -*- coding: utf-8 -*-
"""
Benchmark Script — LIBS Spectral Analysis Software
====================================================

Measures end-to-end wall-clock time and peak-memory usage for each pipeline
stage (Steps 1–5) across a range of synthetic spectrum sizes and peak counts.

Usage
-----
    python benchmarks/benchmark_pipeline.py

Output
------
  benchmarks/results/benchmark_results.csv
  benchmarks/results/benchmark_timing_plot.png
  benchmarks/results/benchmark_memory_plot.png

Requirements
------------
  psutil  (pip install psutil)
  All standard project dependencies (numpy, scipy, pandas, matplotlib)

Notes
-----
- Synthetic spectra with Gaussian peaks are used so no sample file is needed.
- Each configuration is timed REPEATS=5 times; median is reported to reduce
  jitter from OS scheduling.
- Memory is measured as the peak RSS increase during each stage.
"""

import os
import sys
import time
import tracemalloc
import statistics
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")          # headless — no display needed
import matplotlib.pyplot as plt

# ── Ensure project root is on sys.path ───────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.step1_sg_als import BaselineCorrection
from src.core.step2_peaks import PeaksDetector
from src.core.step3_nist_matching import NISTMatcher
from src.core.step4_elemental_preferences import ElementalPreferencesAnalyzer
from src.core.step5_validation import ValidationAnalyzer

# ── Configuration ─────────────────────────────────────────────────────────────
REPEATS = 5          # repetitions per configuration (median taken)
OUTPUT_DIR = PROJECT_ROOT / "benchmarks" / "results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Spectrum sizes to benchmark (number of data points)
SPECTRUM_SIZES = [500, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000]

# Number of synthetic peaks injected per spectrum size
# (kept proportional so SNR is comparable across sizes)
PEAKS_PER_SIZE = {
     500:   10,
   1_000:   20,
   2_500:   40,
   5_000:   80,
  10_000:  150,
  25_000:  300,
  50_000:  500,
}

# ── Synthetic data generators ─────────────────────────────────────────────────

def make_spectrum(n_points: int, n_peaks: int, seed: int = 42):
    """
    Generate a synthetic LIBS spectrum with Gaussian emission lines.

    Returns
    -------
    wavelength : ndarray  shape (n_points,)
    intensity  : ndarray  shape (n_points,)
    """
    rng = np.random.default_rng(seed)
    wl = np.linspace(200.0, 900.0, n_points)

    # Smooth background baseline (low-frequency polynomial)
    baseline = (
        100.0
        + 0.05  * wl
        - 3e-5  * wl**2
        + rng.normal(0, 2.0, n_points)   # noise
    )

    # Inject Gaussian peaks
    signal = np.zeros(n_points)
    peak_wls = rng.uniform(210.0, 890.0, n_peaks)
    for pwl in peak_wls:
        amp   = rng.uniform(500.0, 5000.0)
        sigma = rng.uniform(0.3, 0.8)
        signal += amp * np.exp(-0.5 * ((wl - pwl) / sigma) ** 2)

    return wl, baseline + signal


def make_nist_df(n_lines: int = 200, seed: int = 7) -> pd.DataFrame:
    """Generate a small synthetic NIST-like DataFrame for matching."""
    rng = np.random.default_rng(seed)
    elements = ["Ca", "Fe", "Mg", "Al", "Si", "Na", "K", "Cu"]
    return pd.DataFrame({
        "Wavelength":         rng.uniform(200.0, 900.0, n_lines),
        "Element":            rng.choice(elements, n_lines),
        "Aki":                rng.uniform(1e6, 1e9,  n_lines),
        "relative_intensity": rng.uniform(10,  1000, n_lines),
    })


def make_reference_df(n_points: int = 1000) -> pd.DataFrame:
    """Generate a pure-element reference spectrum for Step 5 validation."""
    wl   = np.linspace(200.0, 900.0, n_points)
    inty = 100.0 + 50.0 * np.sin(wl / 50.0)
    return pd.DataFrame({"wavelength": wl, "intensity": inty})


# ── Timing/memory helpers ─────────────────────────────────────────────────────

def _time_and_memory(func, *args, **kwargs):
    """
    Run func(*args, **kwargs) once, returning (wall_seconds, peak_bytes).
    Uses tracemalloc for heap tracking; wall time via time.perf_counter.
    """
    tracemalloc.start()
    t0 = time.perf_counter()
    result = func(*args, **kwargs)
    t1 = time.perf_counter()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, t1 - t0, peak


def _median_benchmark(func, *args, repeats: int = REPEATS, **kwargs):
    """
    Run func REPEATS times, return (median_wall_s, median_peak_bytes, last_result).
    """
    times, mems, result = [], [], None
    for _ in range(repeats):
        result, t, m = _time_and_memory(func, *args, **kwargs)
        times.append(t)
        mems.append(m)
    return statistics.median(times), statistics.median(mems), result


# ── Per-stage benchmark runners ───────────────────────────────────────────────

def bench_step1(wl, intensity):
    """Benchmark Step 1: baseline correction."""
    corrector = BaselineCorrection()
    return _median_benchmark(corrector.process, wl, intensity)


def bench_step2(wl, corrected):
    """Benchmark Step 2: peak detection."""
    detector = PeaksDetector()
    return _median_benchmark(detector.detect_peaks, wl, corrected)


def bench_step3(peaks, nist_df):
    """Benchmark Step 3: NIST matching."""
    matcher = NISTMatcher()
    return _median_benchmark(matcher.match_peaks, peaks, nist_df)


def bench_step4(matches):
    """Benchmark Step 4: elemental preference competition."""
    analyzer = ElementalPreferencesAnalyzer()
    # Build DataFrames in the format Step 4 expects
    rows = []
    for m in matches:
        if m.element:
            rows.append({
                "Observed_WL": m.observed_wl,
                "Matched_WL":  m.matched_wl or m.observed_wl,
                "Score":       m.score,
                "Element":     m.element,
            })
    if not rows:
        # No matched peaks — return trivially
        return 0.0, 0, None
    df = pd.DataFrame(rows)
    return _median_benchmark(analyzer.analyze, [df])


def bench_step5(processed_df, reference_df, target_wavelengths):
    """Benchmark Step 5: spectral validation."""
    if not target_wavelengths:
        return 0.0, 0, None
    analyzer = ValidationAnalyzer({'WINDOW': 0.5, 'MIN_POINTS': 3,
                                    'INTERPOLATION_KIND': 'linear'})
    return _median_benchmark(
        analyzer.validate_spectrum, processed_df, reference_df, target_wavelengths
    )


# ── Main benchmark loop ────────────────────────────────────────────────────────

def run_benchmarks():
    nist_df = make_nist_df(n_lines=300)
    ref_df  = make_reference_df(n_points=2000)

    records = []

    for n_points in SPECTRUM_SIZES:
        n_peaks = PEAKS_PER_SIZE[n_points]
        print(f"\n{'='*60}")
        print(f"  Spectrum size: {n_points:,} pts | ~{n_peaks} injected peaks")
        print(f"{'='*60}")

        wl, intensity = make_spectrum(n_points, n_peaks)

        # ── Step 1 ────────────────────────────────────────────────────
        t1, m1, processed = bench_step1(wl, intensity)
        print(f"  Step 1 (SG+ALS):      {t1*1000:8.1f} ms  |  {m1/1024**2:6.1f} MB peak")

        # ── Step 2 ────────────────────────────────────────────────────
        t2, m2, peaks = bench_step2(processed.wavelength, processed.corrected)
        n_detected = len(peaks) if peaks else 0
        print(f"  Step 2 (Peaks):       {t2*1000:8.1f} ms  |  {m2/1024**2:6.1f} MB peak  "
              f"|  detected={n_detected}")

        # ── Step 3 ────────────────────────────────────────────────────
        if peaks:
            t3, m3, matches = bench_step3(peaks, nist_df)
            n_matched = sum(1 for m in matches if m.element) if matches else 0
            print(f"  Step 3 (NIST match):  {t3*1000:8.1f} ms  |  {m3/1024**2:6.1f} MB peak  "
                  f"|  matched={n_matched}")
        else:
            t3, m3, matches = 0.0, 0, []
            print(f"  Step 3 (NIST match):  skipped (no peaks)")

        # ── Step 4 ────────────────────────────────────────────────────
        t4, m4, _ = bench_step4(matches or [])
        print(f"  Step 4 (Competition): {t4*1000:8.1f} ms  |  {m4/1024**2:6.1f} MB peak")

        # ── Step 5 ────────────────────────────────────────────────────
        # Use first 20 matched wavelengths as target lines (representative)
        target_wls = [m.observed_wl for m in (matches or []) if m.element][:20]
        proc_df = pd.DataFrame({
            "wavelength": processed.wavelength,
            "intensity":  processed.corrected,
        })
        t5, m5, _ = bench_step5(proc_df, ref_df, target_wls)
        print(f"  Step 5 (Validation):  {t5*1000:8.1f} ms  |  {m5/1024**2:6.1f} MB peak  "
              f"|  lines={len(target_wls)}")

        total_t = t1 + t2 + t3 + t4 + t5
        total_m = max(m1, m2, m3, m4, m5)
        print(f"  {'─'*54}")
        print(f"  TOTAL (Steps 1–5):    {total_t*1000:8.1f} ms  |  {total_m/1024**2:6.1f} MB peak RSS")

        records.append({
            "n_points":          n_points,
            "n_injected_peaks":  n_peaks,
            "n_detected_peaks":  n_detected,
            "step1_ms":          round(t1 * 1000, 2),
            "step2_ms":          round(t2 * 1000, 2),
            "step3_ms":          round(t3 * 1000, 2),
            "step4_ms":          round(t4 * 1000, 2),
            "step5_ms":          round(t5 * 1000, 2),
            "total_ms":          round(total_t * 1000, 2),
            "step1_MB":          round(m1 / 1024**2, 2),
            "step2_MB":          round(m2 / 1024**2, 2),
            "step3_MB":          round(m3 / 1024**2, 2),
            "step4_MB":          round(m4 / 1024**2, 2),
            "step5_MB":          round(m5 / 1024**2, 2),
            "peak_RSS_MB":       round(total_m / 1024**2, 2),
        })

    return pd.DataFrame(records)


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_timing(df: pd.DataFrame, out_path: Path):
    """Stacked-area timing chart: time per stage vs. spectrum size."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # ── Left: time vs. n_points ───────────────────────────────────────
    ax = axes[0]
    stages = ["step1_ms", "step2_ms", "step3_ms", "step4_ms", "step5_ms"]
    labels = ["Step 1: SG+ALS", "Step 2: Peaks", "Step 3: NIST",
              "Step 4: Competition", "Step 5: Validation"]
    colours = ["#3FA9F5", "#3DDC97", "#F4B942", "#E85D75", "#9B59B6"]

    bottom = np.zeros(len(df))
    x = df["n_points"].values
    for col, lbl, col_hex in zip(stages, labels, colours):
        vals = df[col].values
        ax.bar(range(len(x)), vals, bottom=bottom, label=lbl,
               color=col_hex, edgecolor="white", linewidth=0.4)
        bottom += vals

    ax.set_xticks(range(len(x)))
    ax.set_xticklabels([f"{v:,}" for v in x], rotation=30, ha="right", fontsize=8)
    ax.set_xlabel("Spectrum size (data points)", fontsize=10)
    ax.set_ylabel("Processing time (ms)", fontsize=10)
    ax.set_title("Pipeline Processing Time vs. Spectrum Size", fontsize=11, fontweight="bold")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(axis="y", alpha=0.4, linewidth=0.5)

    # ── Right: detected peaks vs. time ───────────────────────────────
    ax2 = axes[1]
    ax2.scatter(df["n_detected_peaks"], df["total_ms"],
                color="#3FA9F5", s=80, zorder=3, label="Total time")
    for _, row in df.iterrows():
        ax2.annotate(f"{row['n_points']:,}",
                     (row["n_detected_peaks"], row["total_ms"]),
                     textcoords="offset points", xytext=(4, 3), fontsize=7)
    ax2.set_xlabel("Detected peaks", fontsize=10)
    ax2.set_ylabel("Total processing time (ms)", fontsize=10)
    ax2.set_title("Processing Time vs. Detected Peaks", fontsize=11, fontweight="bold")
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.4, linewidth=0.5)

    fig.suptitle("LIBS Spectral Analysis Software — Computational Performance",
                 fontsize=12, fontweight="bold", y=1.01)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Timing plot saved: {out_path}")


def plot_memory(df: pd.DataFrame, out_path: Path):
    """Peak memory usage per stage vs. spectrum size."""
    fig, ax = plt.subplots(figsize=(9, 5))

    stages = ["step1_MB", "step2_MB", "step3_MB", "step4_MB", "step5_MB"]
    labels = ["Step 1: SG+ALS", "Step 2: Peaks", "Step 3: NIST",
              "Step 4: Competition", "Step 5: Validation"]
    markers = ["o", "s", "^", "D", "v"]
    colours = ["#3FA9F5", "#3DDC97", "#F4B942", "#E85D75", "#9B59B6"]

    x = df["n_points"].values
    for col, lbl, marker, col_hex in zip(stages, labels, markers, colours):
        ax.plot(x, df[col].values, marker=marker, label=lbl,
                color=col_hex, linewidth=1.5, markersize=6)

    ax.set_xlabel("Spectrum size (data points)", fontsize=10)
    ax.set_ylabel("Peak heap allocation (MB)", fontsize=10)
    ax.set_title("Peak Memory Usage per Stage vs. Spectrum Size", fontsize=11, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.4, linewidth=0.5)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Memory plot saved:  {out_path}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("LIBS Spectral Analysis Software — Pipeline Benchmark")
    print(f"Repeats per configuration: {REPEATS}")
    print(f"Output directory: {OUTPUT_DIR}")

    df = run_benchmarks()

    # Save CSV
    csv_path = OUTPUT_DIR / "benchmark_results.csv"
    df.to_csv(csv_path, index=False)
    print(f"\n  Results CSV saved:  {csv_path}")

    # Print summary table
    print("\n" + "="*90)
    print("SUMMARY TABLE")
    print("="*90)
    print(df.to_string(index=False))

    # Save plots
    plot_timing(df, OUTPUT_DIR / "benchmark_timing_plot.png")
    plot_memory(df, OUTPUT_DIR / "benchmark_memory_plot.png")

    print("\nBenchmark complete.")
