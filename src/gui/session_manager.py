# -*- coding: utf-8 -*-
"""
Session Persistence — save and restore step results between app launches.

Saves to .session/ in the workspace root.  All functions are silent on
failure (log only) so a broken session never blocks the application.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# .session/ lives next to src/ at the workspace root
SESSION_DIR = Path(__file__).resolve().parent.parent.parent / ".session"


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
        pd.DataFrame(rows).to_csv(SESSION_DIR / "step2_peaks.csv", index=False)
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
        pd.DataFrame(rows).to_csv(SESSION_DIR / "step3_matches.csv", index=False)
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
            ranking.to_csv(SESSION_DIR / "step4_ranking.csv", index=False)
        if isinstance(competition, pd.DataFrame):
            competition.to_csv(SESSION_DIR / "step4_competition.csv", index=False)
        if isinstance(winners, pd.DataFrame):
            winners.to_csv(SESSION_DIR / "step4_winners.csv", index=False)
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
        validation_results.to_csv(SESSION_DIR / "step5_validation.csv", index=False)
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
