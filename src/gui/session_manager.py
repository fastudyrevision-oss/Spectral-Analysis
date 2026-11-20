# -*- coding: utf-8 -*-
"""
Session Persistence — save and restore step results between app launches.

Saves to .session/ in the workspace root.  All functions are silent on
failure (log only) so a broken session never blocks the application.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def _session_dir() -> Path:
    """
    Return a writable directory for session files.

    - Frozen (installed exe) → %APPDATA%\\LIBS_Analysis\\.session\\
    - Development            → .session\\ beside the project root
    """
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            d = Path(appdata) / "LIBS_Analysis" / ".session"
            d.mkdir(parents=True, exist_ok=True)
            return d
    # Development: session_manager.py is in src/gui/, root is 3 levels up
    return Path(__file__).resolve().parent.parent.parent / ".session"


# Resolve once at import time
SESSION_DIR = _session_dir()


def _ensure_dir() -> None:
    SESSION_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Step 2 — detected peaks
# ---------------------------------------------------------------------------

def save_step2(detected_peaks) -> None:
    """Save list[DetectedPeak] → .session/step2_peaks.csv"""
    if not detected_peaks:
        return
    try:
        _ensure_dir()
        rows = [{"wavelength": p.wavelength, "intensity": p.intensity}
                for p in detected_peaks]
        pd.DataFrame(rows).to_csv(SESSION_DIR / "step2_peaks.csv", index=False,
                                   lineterminator='\n')
        logger.info("Session: saved %d detected peaks", len(detected_peaks))
    except Exception:
        logger.exception("Session: failed to save step2 peaks")


def load_step2():
    """Return list[DetectedPeak] or None."""
    from src.io.data_models import DetectedPeak
    path = SESSION_DIR / "step2_peaks.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        if df.empty:
            return None
        peaks = [DetectedPeak(wavelength=float(r["wavelength"]),
                              intensity=float(r["intensity"]))
                 for _, r in df.iterrows()]
        logger.info("Session: restored %d detected peaks", len(peaks))
        return peaks or None
    except Exception:
        logger.exception("Session: failed to load step2 peaks")
        return None


# ---------------------------------------------------------------------------
# Step 3 — NIST matches
# ---------------------------------------------------------------------------

def save_step3(matches) -> None:
    """Save list[NISTMatch] → .session/step3_matches.csv"""
    if not matches:
        return
    try:
        _ensure_dir()
        rows = [{
            "observed_wl":        m.observed_wl,
            "matched_wl":         "" if m.matched_wl is None else m.matched_wl,
            "delta":              "" if m.delta is None else m.delta,
            "aki":                m.aki,
            "relative_intensity": m.relative_intensity,
            "score":              m.score,
            "element":            "" if m.element is None else m.element,
        } for m in matches]
        pd.DataFrame(rows).to_csv(SESSION_DIR / "step3_matches.csv", index=False,
                                   lineterminator='\n')
        logger.info("Session: saved %d NIST matches", len(matches))
    except Exception:
        logger.exception("Session: failed to save step3 matches")


def load_step3():
    """Return list[NISTMatch] or None."""
    from src.io.data_models import NISTMatch
    path = SESSION_DIR / "step3_matches.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        if df.empty:
            return None

        def _opt_float(val):
            s = str(val).strip()
            return float(s) if s else None

        def _opt_str(val):
            s = str(val).strip()
            return s if s else None

        matches = [
            NISTMatch(
                observed_wl=float(r["observed_wl"]),
                matched_wl=_opt_float(r["matched_wl"]),
                delta=_opt_float(r["delta"]),
                aki=float(r["aki"]),
                relative_intensity=float(r["relative_intensity"]),
                score=float(r["score"]),
                element=_opt_str(r["element"]),
            )
            for _, r in df.iterrows()
        ]
        logger.info("Session: restored %d NIST matches", len(matches))
        return matches or None
    except Exception:
        logger.exception("Session: failed to load step3 matches")
        return None


# ---------------------------------------------------------------------------
# Step 4 — analysis results
# ---------------------------------------------------------------------------

def save_step4(analysis_results: dict) -> None:
    """Save Step 4 analysis results dict → .session/step4_*.csv + .txt"""
    if not analysis_results:
        return
    try:
        _ensure_dir()
        ranking    = analysis_results.get("ranking")
        competition = analysis_results.get("competition")
        winners    = analysis_results.get("winner_lines")
        primary    = analysis_results.get("primary_element", "")

        if isinstance(ranking, pd.DataFrame):
            ranking.to_csv(SESSION_DIR / "step4_ranking.csv", index=False,
                           lineterminator='\n')
        if isinstance(competition, pd.DataFrame):
            competition.to_csv(SESSION_DIR / "step4_competition.csv", index=False,
                               lineterminator='\n')
        if isinstance(winners, pd.DataFrame):
            winners.to_csv(SESSION_DIR / "step4_winners.csv", index=False,
                           lineterminator='\n')
        (SESSION_DIR / "step4_primary.txt").write_text(str(primary), encoding="utf-8")
        logger.info("Session: saved Step 4 results (primary=%s)", primary)
    except Exception:
        logger.exception("Session: failed to save step4 results")


def load_step4() -> dict | None:
    """Return analysis_results dict or None."""
    ranking_path = SESSION_DIR / "step4_ranking.csv"
    if not ranking_path.exists():
        return None
    try:
        ranking = pd.read_csv(ranking_path)
        if ranking.empty:
            return None

        comp_path = SESSION_DIR / "step4_competition.csv"
        competition = pd.read_csv(comp_path) if comp_path.exists() else pd.DataFrame()

        win_path = SESSION_DIR / "step4_winners.csv"
        winners = pd.read_csv(win_path) if win_path.exists() else pd.DataFrame()

        prim_path = SESSION_DIR / "step4_primary.txt"
        primary = prim_path.read_text(encoding="utf-8").strip() if prim_path.exists() else ""

        results = {
            "ranking":       ranking,
            "competition":   competition,
            "winner_lines":  winners,
            "primary_element": primary,
            "combined_data": competition,   # alias expected by some code paths
        }
        logger.info("Session: restored Step 4 results (primary=%s)", primary)
        return results
    except Exception:
        logger.exception("Session: failed to load step4 results")
        return None


# ---------------------------------------------------------------------------
# Step 5 — validation results
# ---------------------------------------------------------------------------

def save_step5(validation_results) -> None:
    """Save Step 5 validation_results DataFrame → .session/step5_validation.csv"""
    if validation_results is None:
        return
    if isinstance(validation_results, pd.DataFrame) and validation_results.empty:
        return
    try:
        _ensure_dir()
        validation_results.to_csv(SESSION_DIR / "step5_validation.csv", index=False,
                                   lineterminator='\n')
        logger.info("Session: saved %d validation rows", len(validation_results))
    except Exception:
        logger.exception("Session: failed to save step5 validation")


def load_step5():
    """Return pd.DataFrame or None."""
    path = SESSION_DIR / "step5_validation.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        if df.empty:
            return None
        logger.info("Session: restored %d validation rows", len(df))
        return df
    except Exception:
        logger.exception("Session: failed to load step5 validation")
        return None


# ---------------------------------------------------------------------------
# Step 1 — processed spectra
# ---------------------------------------------------------------------------

def save_step1(processed_data) -> None:
    """Save ProcessedSpectra → .session/step1_processed.csv

    Serialises all six numpy arrays as columns so no binary format is needed.
    The baseline_iterations list is intentionally skipped (too large, only
    needed for the convergence plot which can be omitted on restore).
    """
    if processed_data is None:
        return
    try:
        _ensure_dir()
        import numpy as np
        df = pd.DataFrame({
            "wavelength":    processed_data.wavelength,
            "raw":           processed_data.raw,
            "smoothed_sg":   processed_data.smoothed_sg,
            "baseline_als":  processed_data.baseline_als,
            "corrected":     processed_data.corrected,
        })
        df.to_csv(SESSION_DIR / "step1_processed.csv", index=False,
                  lineterminator='\n')
        logger.info("Session: saved Step 1 processed spectra (%d points)",
                    len(processed_data.wavelength))
    except Exception:
        logger.exception("Session: failed to save step1 processed spectra")


def load_step1():
    """Return ProcessedSpectra or None."""
    from src.io.data_models import ProcessedSpectra
    import numpy as np
    path = SESSION_DIR / "step1_processed.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        if df.empty:
            return None
        ps = ProcessedSpectra(
            wavelength=df["wavelength"].to_numpy(dtype=float),
            raw=df["raw"].to_numpy(dtype=float),
            smoothed_sg=df["smoothed_sg"].to_numpy(dtype=float),
            baseline_als=df["baseline_als"].to_numpy(dtype=float),
            corrected=df["corrected"].to_numpy(dtype=float),
            baseline_iterations=[],   # not persisted — convergence plot skipped
        )
        logger.info("Session: restored Step 1 processed spectra (%d points)",
                    len(ps.wavelength))
        return ps
    except Exception:
        logger.exception("Session: failed to load step1 processed spectra")
        return None


# ---------------------------------------------------------------------------
# Step 6 — performance results
# ---------------------------------------------------------------------------

def save_step6(performance_results: dict) -> None:
    """Save Step 6 performance_results dict → .session/step6_*.csv + step6_meta.json

    Scalar metrics go into step6_meta.json.
    DataFrames (ranking_df, heatmap_matrix, element_rows) go into separate CSVs.
    element_rows (list of dicts) is serialised as step6_element_rows.csv.
    """
    if not performance_results:
        return
    try:
        import json
        _ensure_dir()

        # ── Scalar / simple-value keys → JSON ─────────────────────────
        scalar_keys = [
            "accuracy", "precision", "recall", "f1_score", "sbr_improvement",
            "missing_steps", "pipeline_stages",
        ]
        meta = {k: performance_results.get(k) for k in scalar_keys}
        # peak_labels / element_labels are small lists — include in JSON too
        meta["peak_labels"]    = performance_results.get("peak_labels", [])
        meta["element_labels"] = performance_results.get("element_labels", [])
        (SESSION_DIR / "step6_meta.json").write_text(
            json.dumps(meta, default=str), encoding="utf-8"
        )

        # ── ranking_df DataFrame ───────────────────────────────────────
        ranking_df = performance_results.get("ranking_df")
        if isinstance(ranking_df, pd.DataFrame) and not ranking_df.empty:
            ranking_df.to_csv(SESSION_DIR / "step6_ranking_df.csv", index=False,
                              lineterminator='\n')

        # ── heatmap_matrix (2-D numpy array) ──────────────────────────
        heatmap = performance_results.get("heatmap_matrix")
        if heatmap is not None:
            import numpy as np
            try:
                pd.DataFrame(heatmap).to_csv(
                    SESSION_DIR / "step6_heatmap.csv", index=False, header=False,
                    lineterminator='\n'
                )
            except Exception:
                pass

        # ── element_rows (list[dict]) ──────────────────────────────────
        element_rows = performance_results.get("element_rows", [])
        if element_rows:
            # Flatten list items — best_lines is a list; join as semicolon string
            flat = []
            for row in element_rows:
                r = dict(row)
                if isinstance(r.get("best_lines"), list):
                    r["best_lines"] = ";".join(str(x) for x in r["best_lines"])
                flat.append(r)
            pd.DataFrame(flat).to_csv(
                SESSION_DIR / "step6_element_rows.csv", index=False,
                lineterminator='\n'
            )

        logger.info("Session: saved Step 6 performance results (%d element rows)",
                    len(element_rows))
    except Exception:
        logger.exception("Session: failed to save step6 performance results")


def load_step6() -> dict | None:
    """Return performance_results dict or None."""
    meta_path = SESSION_DIR / "step6_meta.json"
    if not meta_path.exists():
        return None
    try:
        import json
        import numpy as np

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        results: dict = dict(meta)

        # ── ranking_df ─────────────────────────────────────────────────
        rp = SESSION_DIR / "step6_ranking_df.csv"
        results["ranking_df"] = pd.read_csv(rp) if rp.exists() else pd.DataFrame()

        # ── heatmap_matrix ─────────────────────────────────────────────
        hp = SESSION_DIR / "step6_heatmap.csv"
        if hp.exists():
            results["heatmap_matrix"] = pd.read_csv(hp, header=None).to_numpy(dtype=float)
        else:
            results["heatmap_matrix"] = None

        # ── element_rows ───────────────────────────────────────────────
        ep = SESSION_DIR / "step6_element_rows.csv"
        if ep.exists():
            df = pd.read_csv(ep)
            rows = []
            for _, r in df.iterrows():
                row = r.to_dict()
                # Restore best_lines from semicolon-joined string
                bl = row.get("best_lines", "")
                if isinstance(bl, str) and bl:
                    try:
                        row["best_lines"] = [float(x) for x in bl.split(";") if x.strip()]
                    except ValueError:
                        row["best_lines"] = []
                else:
                    row["best_lines"] = []
                rows.append(row)
            results["element_rows"] = rows
        else:
            results["element_rows"] = []

        logger.info("Session: restored Step 6 performance results (%d element rows)",
                    len(results.get("element_rows", [])))
        return results
    except Exception:
        logger.exception("Session: failed to load step6 performance results")
        return None
