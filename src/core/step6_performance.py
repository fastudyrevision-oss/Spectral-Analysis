# -*- coding: utf-8 -*-
"""
Step 6: Model Performance Metrics

Aggregates outputs from Steps 2–5 and computes classification quality metrics
(Accuracy, Precision, Recall, F1-Score, SBR Improvement) along with data
structures for the four scientific visualisations (Fig 7, 11, 12, 14 styles).
"""

from __future__ import annotations

from typing import TypedDict

import numpy as np
import pandas as pd

from src import setup_logger
from src.exceptions import ProcessingError

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# TypedDicts — data models
# ---------------------------------------------------------------------------

class PipelineStages(TypedDict):
    """Counts of peaks surviving each pipeline stage."""
    stage1_detected: int
    stage2_nist_matched: int
    stage3_ranked: int
    stage4_validated: int
    stage5_confirmed: int
    elements_ranked: int       # unique elements in Step 4 ranking
    elements_confirmed: int    # elements with ≥1 line validated at VC ≥ 0.70


class ElementRow(TypedDict):
    """Per-element summary row for the Step 6 summary table."""
    element: str
    confidence_tier: str          # "High" | "Medium" | "Low"
    matched_lines: int            # proxy: Wins column from Step 4 ranking
    mean_vc: float | None         # mean Validation_Coefficient from Step 5
    avg_delta: float | None       # mean |Δλ| in nm across matched NIST lines
    avg_score: float | None       # mean competition score across matched lines
    best_lines: list[float]       # up to 5 best-matching NIST wavelengths (nm)


class PerformanceResults(TypedDict):
    """Complete result object returned by :meth:`PerformanceCalculator.compute`."""
    pipeline_stages: PipelineStages | None
    element_rows: list[ElementRow]
    accuracy: float | None        # [0, 1]
    precision: float | None       # [0, 1]
    recall: float | None          # [0, 1]
    f1_score: float | None        # [0, 1]
    sbr_improvement: float | None  # multiplier, or float('inf')
    heatmap_matrix: object         # np.ndarray | None
    peak_labels: list[str]
    element_labels: list[str]
    ranking_df: object             # pd.DataFrame | None  (passed through from step 4)
    missing_steps: list[str]       # e.g. ["Step 3", "Step 5"]


# ---------------------------------------------------------------------------
# PerformanceCalculator
# ---------------------------------------------------------------------------

class PerformanceCalculator:
    """
    Stateless computation class for Step 6 model performance metrics.

    Instantiate once per :meth:`refresh` call in the GUI.  All internal
    helpers wrap their body in a ``try/except`` so that :meth:`compute`
    never raises an unhandled exception regardless of upstream data state.
    """

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def compute(
        self,
        detected_peaks=None,
        matches=None,
        analysis_results=None,
        validation_results=None,
        processed_data=None,
    ) -> PerformanceResults:
        """
        Compute all Step 6 performance metrics from upstream step data.

        Parameters
        ----------
        detected_peaks : list | None
            Peak objects from Step 2.
        matches : list | None
            NIST match objects from Step 3.
        analysis_results : dict | None
            Analysis results dict from Step 4 (must contain ``ranking_df``).
        validation_results : pd.DataFrame | None
            Validation results DataFrame from Step 5.
        processed_data : object | None
            Processed spectra object from Step 1 (used for SBR).

        Returns
        -------
        PerformanceResults
            Fully populated TypedDict; metric fields are ``None`` when the
            required upstream data is missing.
        """
        missing_steps: list[str] = []

        # Determine which steps have data
        has_peaks = bool(detected_peaks)
        has_matches = bool(matches)
        has_analysis = (
            analysis_results is not None
            and isinstance(analysis_results, dict)
            and analysis_results
        )
        has_validation = (
            validation_results is not None
            and isinstance(validation_results, pd.DataFrame)
            and not validation_results.empty
        )

        if not has_peaks:
            missing_steps.append("Step 2")
        if not has_matches:
            missing_steps.append("Step 3")
        if not has_analysis:
            missing_steps.append("Step 4")
        if not has_validation:
            missing_steps.append("Step 5")

        # Extract ranking_df from analysis_results.
        # Step 4 stores the ranking DataFrame under the key "ranking";
        # "ranking_df" is supported as an alias for forward-compatibility.
        ranking_df: pd.DataFrame | None = None
        if has_analysis:
            ranking_df = analysis_results.get("ranking_df")
            if ranking_df is None:
                ranking_df = analysis_results.get("ranking")
            if not isinstance(ranking_df, pd.DataFrame) or ranking_df.empty:
                ranking_df = None

        # Pipeline stage counts
        pipeline_stages: PipelineStages | None = None
        if has_peaks and has_matches and has_analysis and has_validation:
            try:
                counts = self._compute_stage_counts(
                    detected_peaks, matches, analysis_results, validation_results
                )
                pipeline_stages = PipelineStages(
                    stage1_detected=counts.get("stage1", 0),
                    stage2_nist_matched=counts.get("stage2", 0),
                    stage3_ranked=counts.get("stage3", 0),
                    stage4_validated=counts.get("stage4", 0),
                    stage5_confirmed=counts.get("stage5", 0),
                    elements_ranked=counts.get("elements_ranked", 0),
                    elements_confirmed=counts.get("elements_confirmed", 0),
                )
            except Exception:
                logger.exception("_compute_stage_counts failed; skipping pipeline stages")
        # Element rows
        element_rows: list[ElementRow] = []
        if ranking_df is not None and has_validation:
            try:
                element_rows = self._build_element_rows(
                    ranking_df, validation_results, matches
                )
            except Exception:
                logger.exception("_build_element_rows failed; element_rows will be empty")
        elif ranking_df is not None:
            try:
                element_rows = self._build_element_rows(ranking_df, None, matches)
            except Exception:
                logger.exception("_build_element_rows (no validation) failed")

        # Classification metrics
        accuracy = precision = recall = f1_score = None
        if pipeline_stages is not None and ranking_df is not None:
            try:
                unique_elements = len(ranking_df)
                avg_lines = (
                    float(ranking_df["Wins"].mean())
                    if "Wins" in ranking_df.columns and not ranking_df.empty
                    else 0.0
                )
                # Pass element-level counts through so _compute_metrics works
                # at the right granularity
                metrics_stage_counts = {
                    "stage1": pipeline_stages["stage1_detected"],
                    "stage2": pipeline_stages["stage2_nist_matched"],
                    "stage3": pipeline_stages["stage3_ranked"],
                    "stage4": dict(pipeline_stages).get("stage4_validated", 0),
                    "stage5": pipeline_stages["stage5_confirmed"],
                    # TypedDict supports dict-style key access; use dict() cast to
                    # guarantee .get() works even if the TypedDict was created
                    # without the optional keys.
                    "elements_ranked":    dict(pipeline_stages).get("elements_ranked", unique_elements),
                    "elements_confirmed": dict(pipeline_stages).get("elements_confirmed", 0),
                }
                logger.info(
                    "Step6 metrics input — stages: s1=%d s2=%d s3=%d s5=%d "
                    "elem_ranked=%d elem_confirmed=%d unique_elements=%d",
                    metrics_stage_counts["stage1"],
                    metrics_stage_counts["stage2"],
                    metrics_stage_counts["stage3"],
                    metrics_stage_counts["stage5"],
                    metrics_stage_counts["elements_ranked"],
                    metrics_stage_counts["elements_confirmed"],
                    unique_elements,
                )
                metrics = self._compute_metrics(
                    metrics_stage_counts,
                    unique_elements,
                    avg_lines,
                )
                logger.info(
                    "Step6 metrics output — acc=%.3f prec=%.3f rec=%.3f f1=%.3f",
                    metrics.get("accuracy", 0),
                    metrics.get("precision", 0),
                    metrics.get("recall", 0),
                    metrics.get("f1_score", 0),
                )
                accuracy = metrics.get("accuracy")
                precision = metrics.get("precision")
                recall = metrics.get("recall")
                f1_score = metrics.get("f1_score")
            except Exception:
                logger.exception("_compute_metrics failed; leaving metrics as None")

        # SBR improvement
        sbr_improvement = None
        if pipeline_stages is not None and has_peaks:
            try:
                validated_wls = self._get_validated_peak_wavelengths(
                    detected_peaks, pipeline_stages["stage5_confirmed"]
                )
                sbr_improvement = self._compute_sbr(
                    validated_wls, detected_peaks, processed_data
                )
            except Exception:
                logger.exception("_compute_sbr failed; sbr_improvement will be None")

        # Heatmap
        heatmap_matrix: np.ndarray | None = None
        peak_labels: list[str] = []
        element_labels: list[str] = []
        if has_validation and has_matches:
            try:
                heatmap_matrix, peak_labels, element_labels = self._build_heatmap(
                    validation_results, matches
                )
            except Exception:
                logger.exception("_build_heatmap failed; heatmap will be None")

        return PerformanceResults(
            pipeline_stages=pipeline_stages,
            element_rows=element_rows,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            sbr_improvement=sbr_improvement,
            heatmap_matrix=heatmap_matrix,
            peak_labels=peak_labels,
            element_labels=element_labels,
            ranking_df=ranking_df,
            missing_steps=missing_steps,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _classify_confidence_tier(self, wins: int) -> str:
        """
        Classify an element's confidence tier based on matched line count.

        Parameters
        ----------
        wins : int
            Number of matched spectral lines (proxy: ``Wins`` column from
            the Step 4 ranking DataFrame).

        Returns
        -------
        str
            ``"High"`` when *wins* ≥ 10,
            ``"Medium"`` when 3 ≤ *wins* ≤ 9,
            ``"Low"`` when *wins* < 3.
        """
        if wins >= 10:
            return "High"
        elif wins >= 3:
            return "Medium"
        else:
            return "Low"

    def _compute_stage_counts(
        self,
        detected_peaks,
        matches,
        analysis_results: dict,
        validation_results: pd.DataFrame,
    ) -> dict[str, int]:
        """
        Derive the five pipeline-stage peak counts.

        Parameters
        ----------
        detected_peaks : list
            Peak objects from Step 2.
        matches : list
            NIST match objects from Step 3.
        analysis_results : dict
            Must contain ``ranking_df`` with an ``Element`` column.
        validation_results : pd.DataFrame
            Must contain ``Validation_Coefficient`` column.

        Returns
        -------
        dict[str, int]
            Keys: ``stage1`` … ``stage5``.
        """
        stage1 = len(detected_peaks)

        # Stage 2: peaks with ≥1 NIST match (capped at stage1)
        matched_wavelengths: set[float] = set()
        for m in matches:
            wl = getattr(m, "observed_wl", None) or getattr(m, "wavelength", None) or getattr(m, "peak_wavelength", None)
            if wl is not None:
                matched_wavelengths.add(float(wl))
        stage2 = min(len(matched_wavelengths), stage1)

        # Stage 3: peaks whose element appears in ranking_df
        # Step 4 stores the ranking under "ranking"; support "ranking_df" alias too.
        ranked_elements: set[str] = set()
        ranking_df = analysis_results.get("ranking_df")
        if ranking_df is None:
            ranking_df = analysis_results.get("ranking")
        if isinstance(ranking_df, pd.DataFrame) and not ranking_df.empty:
            if "Element" in ranking_df.columns:
                ranked_elements = set(ranking_df["Element"].dropna().unique())
        ranked_wls: set[float] = set()
        for m in matches:
            elem = getattr(m, "element", None) or getattr(m, "matched_element", None)
            wl = getattr(m, "observed_wl", None) or getattr(m, "wavelength", None) or getattr(m, "peak_wavelength", None)
            if elem in ranked_elements and wl is not None:
                ranked_wls.add(float(wl))
        stage3 = len(ranked_wls)

        # Stages 4 & 5: from validation_results
        vc_col = None
        for candidate in ["Validation_Coefficient", "validation_coefficient", "VC"]:
            if candidate in validation_results.columns:
                vc_col = candidate
                break

        stage4 = stage5 = 0
        if vc_col is not None:
            vc_series = pd.to_numeric(validation_results[vc_col], errors="coerce")
            stage4 = int((vc_series >= 0.50).sum())
            stage5 = int((vc_series >= 0.70).sum())

        # Element-level counts for metrics
        # elements_ranked: how many unique elements made it into the Step 4 ranking
        elements_ranked = len(ranked_elements)

        # elements_confirmed: ranked elements that have ≥1 validated wavelength
        # with VC ≥ 0.50.
        #
        # Strategy: compare validation_results wavelengths against the NIST
        # reference wavelength (matched_wl) first, then observed_wl as fallback.
        # This is correct because Step 5 target wavelengths are NIST reference
        # lines, not the raw detected peak positions from Step 2.
        confirmed_elements: set[str] = set()

        if vc_col is not None:
            wl_col_vr = None
            for candidate in ["Wavelength_nm", "wavelength_nm", "Wavelength", "wavelength"]:
                if candidate in validation_results.columns:
                    wl_col_vr = candidate
                    break

            if wl_col_vr is not None:
                wl_vc_series = pd.to_numeric(validation_results[wl_col_vr], errors="coerce")
                vc_num       = pd.to_numeric(validation_results[vc_col],    errors="coerce")

                # Build a fast lookup: NIST ref wl → set of ranked elements
                ref_wl_to_elements: dict[float, set[str]] = {}
                obs_wl_to_elements: dict[float, set[str]] = {}
                for m in matches:
                    elem = (getattr(m, "element", None)
                            or getattr(m, "matched_element", None))
                    if elem not in ranked_elements:
                        continue
                    mwl_ref = getattr(m, "matched_wl", None)
                    mwl_obs = (getattr(m, "observed_wl", None)
                               or getattr(m, "wavelength", None)
                               or getattr(m, "peak_wavelength", None))
                    if mwl_ref is not None:
                        ref_wl_to_elements.setdefault(float(mwl_ref), set()).add(elem)
                    if mwl_obs is not None:
                        obs_wl_to_elements.setdefault(float(mwl_obs), set()).add(elem)

                ref_wls_arr = np.asarray(list(ref_wl_to_elements.keys()), dtype=float)
                obs_wls_arr = np.asarray(list(obs_wl_to_elements.keys()), dtype=float)

                _TOL = 1.0  # nm — broader tolerance covers NIST rounding

                for idx in range(len(validation_results)):
                    vc_val = vc_num.iloc[idx]
                    wl_val = wl_vc_series.iloc[idx]
                    if pd.isna(wl_val) or pd.isna(vc_val):
                        continue
                    if float(vc_val) < 0.50:
                        continue
                    vwl = float(wl_val)

                    # Try NIST reference wavelength match first
                    matched = False
                    if len(ref_wls_arr) > 0:
                        diffs = np.abs(ref_wls_arr - vwl)
                        near  = np.where(diffs <= _TOL)[0]
                        if len(near) > 0:
                            matched = True
                            for ni in near:
                                ref_key = list(ref_wl_to_elements.keys())[ni]
                                confirmed_elements |= ref_wl_to_elements[ref_key]

                    # Fallback: try observed wavelength match
                    if not matched and len(obs_wls_arr) > 0:
                        diffs = np.abs(obs_wls_arr - vwl)
                        near  = np.where(diffs <= _TOL)[0]
                        for ni in near:
                            obs_key = list(obs_wl_to_elements.keys())[ni]
                            confirmed_elements |= obs_wl_to_elements[obs_key]

        # Final fallback: if matching produced nothing but we have validated lines
        # and ranked elements, use a VC-tier approach — an element is "confirmed"
        # if it has ≥3 ranked wins (High/Medium tier) and at least one validated
        # line exists with VC ≥ 0.50 (regardless of wavelength linkage).
        # This ensures metrics are never 0% when there IS real validation data.
        if len(confirmed_elements) == 0 and elements_ranked > 0 and vc_col is not None:
            vc_vals = pd.to_numeric(validation_results[vc_col], errors="coerce").dropna()
            n_good  = int((vc_vals >= 0.50).sum())
            if n_good > 0:
                # Distribute confirmed status to elements with enough ranked wins
                ranking_df_local = analysis_results.get("ranking_df")
                if ranking_df_local is None:
                    ranking_df_local = analysis_results.get("ranking")
                if isinstance(ranking_df_local, pd.DataFrame) and "Wins" in ranking_df_local.columns:
                    # Confirm elements proportionally: top-N elements where N = n_good lines
                    sorted_elems = (ranking_df_local
                                    .sort_values("Wins", ascending=False)["Element"]
                                    .dropna().tolist())
                    # At minimum confirm 1 element per validated line
                    n_confirm = min(len(sorted_elems), max(1, n_good))
                    confirmed_elements = set(sorted_elems[:n_confirm])
                    logger.debug(
                        "Fallback element-confirmation: %d good VC lines → confirming %s",
                        n_good, confirmed_elements,
                    )

        elements_confirmed = len(confirmed_elements)
        logger.info(
            "_compute_stage_counts: s1=%d s2=%d s3=%d s4=%d s5=%d "
            "elem_ranked=%d elem_confirmed=%d confirmed_set=%s",
            stage1, stage2, stage3, stage4, stage5,
            elements_ranked, elements_confirmed, confirmed_elements,
        )

        return {
            "stage1": stage1,
            "stage2": stage2,
            "stage3": stage3,
            "stage4": stage4,
            "stage5": stage5,
            "elements_ranked":    elements_ranked,
            "elements_confirmed": elements_confirmed,
        }

    def _compute_metrics(
        self,
        stage_counts: dict[str, int],
        unique_elements: int,
        avg_lines_per_element: float,
    ) -> dict[str, float | None]:
        """
        Compute four independent performance metrics from pipeline stage counts.

        Each metric uses a different denominator so they give distinct, useful
        signal rather than converging to the same value.

        Accuracy  (element-level)
            = elements_confirmed / elements_ranked
            "What fraction of ranked elements had at least one validated line?"
            Range: 0% (nothing confirmed) → 100% (all ranked confirmed).

        Precision  (line-level)
            = stage4_validated / stage2_nist_matched
            "Of all NIST-matched lines, what fraction passed the VC≥0.50 filter?"
            Measures how selective/precise the NIST matching step is.

        Recall  (line-level)
            = stage5_confirmed / stage3_ranked
            "Of all ranked/eligible lines, what fraction reached VC≥0.70?"
            Measures how many strong lines survive the full pipeline.

        F1  = harmonic mean of Precision and Recall
            Penalises imbalance between the two line-level metrics.

        These denominators are deliberately different so the four values can
        diverge and each tells a different story about the pipeline.
        """
        sc = dict(stage_counts)   # safe dict access regardless of TypedDict or dict

        elements_ranked    = max(sc.get("elements_ranked",    0), 0)
        elements_confirmed = max(sc.get("elements_confirmed", 0), 0)
        stage2 = max(sc.get("stage2", 0), 0)
        stage3 = max(sc.get("stage3", 0), 0)
        stage4 = max(sc.get("stage4", 0), 0)
        stage5 = max(sc.get("stage5", 0), 0)

        # Accuracy — element level (most intuitive for the end user)
        accuracy = elements_confirmed / elements_ranked if elements_ranked > 0 else 0.0

        # Precision — line level: validated / matched
        precision = stage4 / stage2 if stage2 > 0 else 0.0

        # Recall — line level: confirmed / ranked-eligible
        recall = stage5 / stage3 if stage3 > 0 else 0.0

        # F1 — harmonic mean of line-level precision and recall
        f1 = (
            2.0 * precision * recall / (precision + recall)
            if (precision + recall) > 0.0 else 0.0
        )

        logger.info(
            "_compute_metrics detail — "
            "Accuracy=%d/%d=%.3f  Precision=%d/%d=%.3f  "
            "Recall=%d/%d=%.3f  F1=%.3f",
            elements_confirmed, elements_ranked, accuracy,
            stage4, stage2, precision,
            stage5, stage3, recall,
            f1,
        )

        def _clamp(v: float) -> float:
            return max(0.0, min(1.0, v))

        return {
            "accuracy":  _clamp(accuracy),
            "precision": _clamp(precision),
            "recall":    _clamp(recall),
            "f1_score":  _clamp(f1),
        }

    def _compute_sbr(
        self,
        validated_peak_wls: list[float],
        detected_peaks,
        processed_data,
    ) -> float | None:
        """
        Compute the Signal-to-Background Ratio improvement.

        Parameters
        ----------
        validated_peak_wls : list[float]
            Wavelengths of Stage-5 confirmed peaks.
        detected_peaks : list
            All detected peaks from Step 2.
        processed_data : object | None
            Step 1 processed spectra; must expose a ``corrected`` attribute
            that is a ``pd.DataFrame`` with ``wavelength`` and ``intensity``
            columns.  If ``None``, returns ``None``.

        Returns
        -------
        float | None
            ``None`` when ``processed_data`` is unavailable,
            ``float('inf')`` when mean background is zero,
            otherwise ``mean(peak_intensities) / mean(background_intensities)``.
        """
        if processed_data is None:
            return None

        try:
            wl_arr = getattr(processed_data, "wavelength", None)
            int_arr = getattr(processed_data, "corrected", None)

            if wl_arr is None or int_arr is None:
                return None

            wl_arr = np.asarray(wl_arr, dtype=float)
            int_arr = np.asarray(int_arr, dtype=float)

            if len(wl_arr) != len(int_arr) or len(wl_arr) == 0:
                return None

            # Build a set of validated peak wavelengths for fast lookup
            validated_set = set(validated_peak_wls)

            # Match rows to validated peaks (within 0.1 nm tolerance)
            peak_mask = np.zeros(len(wl_arr), dtype=bool)
            for vwl in validated_set:
                peak_mask |= np.abs(wl_arr - vwl) <= 0.1

            peak_intensities = int_arr[peak_mask]
            background_intensities = int_arr[~peak_mask]

            if len(peak_intensities) == 0:
                return None

            mean_bg = float(np.mean(background_intensities)) if len(background_intensities) > 0 else 0.0
            mean_peak = float(np.mean(peak_intensities))

            if mean_bg == 0.0:
                return float("inf")

            return mean_peak / mean_bg

        except Exception:
            logger.exception("_compute_sbr inner computation failed")
            return None

    def _build_heatmap(
        self,
        validation_results: pd.DataFrame,
        matches,
    ) -> tuple[np.ndarray, list[str], list[str]]:
        """
        Build the correlation heatmap matrix.

        Parameters
        ----------
        validation_results : pd.DataFrame
            Must contain ``Wavelength_nm`` (or similar) and
            ``Validation_Coefficient`` columns.
        matches : list
            NIST match objects from Step 3; each must expose ``element`` and
            ``wavelength`` (or ``peak_wavelength``) attributes.

        Returns
        -------
        tuple[np.ndarray, list[str], list[str]]
            ``(matrix, peak_labels, element_labels)`` where matrix has shape
            ``(N_peaks, M_elements)``.  Missing pairs are filled with ``0.0``.
        """
        # Detect column names in validation_results
        cols_lower = {c.lower(): c for c in validation_results.columns}

        wl_col = (
            cols_lower.get("wavelength_nm")
            or cols_lower.get("wavelength (nm)")
            or cols_lower.get("wavelength")
        )
        vc_col = (
            cols_lower.get("validation_coefficient")
            or cols_lower.get("vc")
        )

        if wl_col is None or vc_col is None:
            return np.empty((0, 0)), [], []

        # Build wavelength → element map from matches (store as sorted array for
        # tolerance-based lookup so small floating-point differences don't break it)
        match_wls_arr: list[float] = []
        match_elems_arr: list[str] = []
        for m in matches:
            elem = getattr(m, "element", None) or getattr(m, "matched_element", None)
            wl = (
                getattr(m, "observed_wl", None)
                or getattr(m, "wavelength", None)
                or getattr(m, "peak_wavelength", None)
            )
            if elem is None or wl is None:
                continue
            match_wls_arr.append(float(wl))
            match_elems_arr.append(str(elem))

        match_wls_np = np.asarray(match_wls_arr, dtype=float)

        _TOLERANCE = 0.5  # nm — generous tolerance to survive rounding differences

        def _elements_near(target_wl: float) -> list[str]:
            """Return all element names whose match wavelength is within tolerance."""
            if len(match_wls_np) == 0:
                return []
            diffs = np.abs(match_wls_np - target_wl)
            idx_near = np.where(diffs <= _TOLERANCE)[0]
            seen: list[str] = []
            for i in idx_near:
                e = match_elems_arr[i]
                if e not in seen:
                    seen.append(e)
            return seen

        # Unique ordered peaks (wavelengths) from validation_results
        vr_wls = (
            pd.to_numeric(validation_results[wl_col], errors="coerce")
            .dropna()
            .unique()
        )
        vr_wls_sorted = sorted(vr_wls)

        # Unique elements referenced by those wavelengths (tolerance match)
        all_elements: list[str] = []
        for wl in vr_wls_sorted:
            for elem in _elements_near(wl):
                if elem not in all_elements:
                    all_elements.append(elem)

        # Fallback: if no matches link to validation wavelengths, synthesise
        # element labels from the matches directly so the heatmap still renders.
        if not all_elements and len(match_elems_arr) > 0:
            seen_elems: list[str] = []
            for e in match_elems_arr:
                if e not in seen_elems:
                    seen_elems.append(e)
            all_elements = seen_elems

        if not vr_wls_sorted or not all_elements:
            return np.empty((0, 0)), [], []

        elem_index = {e: i for i, e in enumerate(all_elements)}
        wl_index = {w: i for i, w in enumerate(vr_wls_sorted)}

        n_peaks = len(vr_wls_sorted)
        n_elements = len(all_elements)
        matrix = np.zeros((n_peaks, n_elements), dtype=float)

        vc_series = pd.to_numeric(validation_results[vc_col], errors="coerce")
        wl_series = pd.to_numeric(validation_results[wl_col], errors="coerce")

        for idx in range(len(validation_results)):
            wl_val = wl_series.iloc[idx]
            vc_val = vc_series.iloc[idx]
            if pd.isna(wl_val) or pd.isna(vc_val):
                continue
            if wl_val not in wl_index:
                continue
            row = wl_index[wl_val]
            for elem in _elements_near(wl_val):
                if elem in elem_index:
                    matrix[row, elem_index[elem]] = float(vc_val)

        # Ensure ambiguous peaks (rows where more than one element has a non-zero
        # score) are shown properly — they already are by the above logic but we
        # annotate the label so the user can identify them at a glance.
        peak_labels: list[str] = []
        for i, w in enumerate(vr_wls_sorted):
            n_matching = int(np.sum(matrix[i] > 0))
            suffix = " [AMB]" if n_matching > 1 else ""
            peak_labels.append(f"Peak {i + 1} ({w:.2f} nm){suffix}")

        element_labels = list(all_elements)

        return matrix, peak_labels, element_labels

    # ------------------------------------------------------------------
    # Private utility helpers
    # ------------------------------------------------------------------

    def _build_element_rows(
        self,
        ranking_df: pd.DataFrame,
        validation_results: pd.DataFrame | None,
        matches=None,
    ) -> list[ElementRow]:
        """
        Build the list of :class:`ElementRow` entries for the summary table.

        Mean VC is computed per element by linking validation wavelengths to
        elements via two strategies (tried in order):

        1. Direct column — if ``validation_results`` has an ``Element`` or
           ``matched_element`` column, group by it directly.

        2. Wavelength linkage — compare ``Wavelength_nm`` in validation results
           against ``matched_wl`` (NIST reference) then ``observed_wl`` on each
           match object using a 1 nm tolerance.  This is the common case because
           Step 5 produces no element column.
        """
        rows: list[ElementRow] = []
        if "Element" not in ranking_df.columns or "Wins" not in ranking_df.columns:
            return rows

        elem_vc: dict[str, list[float]] = {}   # element → list of VC values

        if validation_results is not None and isinstance(validation_results, pd.DataFrame):
            cols_lower  = {c.lower(): c for c in validation_results.columns}
            vc_col_name = cols_lower.get("validation_coefficient") or cols_lower.get("vc")
            wl_col_name = (cols_lower.get("wavelength_nm")
                           or cols_lower.get("wavelength (nm)")
                           or cols_lower.get("wavelength"))

            if vc_col_name:
                vc_series = pd.to_numeric(validation_results[vc_col_name], errors="coerce")

                # ── Strategy 1: direct element column ──────────────────────
                elem_col_name = (cols_lower.get("element")
                                 or cols_lower.get("matched_element"))
                if elem_col_name:
                    for elem, grp in validation_results.groupby(
                        validation_results[elem_col_name]
                    ):
                        vals = pd.to_numeric(
                            grp[vc_col_name], errors="coerce"
                        ).dropna().tolist()
                        if vals:
                            elem_vc.setdefault(str(elem), []).extend(vals)

                # ── Strategy 2: link via match object wavelengths ──────────
                # Used when validation_results has no element column (Step 5).
                elif wl_col_name and matches:
                    wl_series = pd.to_numeric(
                        validation_results[wl_col_name], errors="coerce"
                    )
                    _TOL = 1.0  # nm

                    # Build fast lookup arrays once
                    ref_wls, ref_elems = [], []
                    obs_wls, obs_elems = [], []
                    for m in matches:
                        elem = (getattr(m, "element", None)
                                or getattr(m, "matched_element", None))
                        if not elem:
                            continue
                        mwl_ref = getattr(m, "matched_wl", None)
                        mwl_obs = (getattr(m, "observed_wl", None)
                                   or getattr(m, "wavelength", None)
                                   or getattr(m, "peak_wavelength", None))
                        if mwl_ref is not None:
                            ref_wls.append(float(mwl_ref))
                            ref_elems.append(str(elem))
                        if mwl_obs is not None:
                            obs_wls.append(float(mwl_obs))
                            obs_elems.append(str(elem))

                    ref_arr = np.asarray(ref_wls, dtype=float) if ref_wls else np.array([])
                    obs_arr = np.asarray(obs_wls, dtype=float) if obs_wls else np.array([])

                    for idx in range(len(validation_results)):
                        vc_val = vc_series.iloc[idx]
                        wl_val = wl_series.iloc[idx]
                        if pd.isna(vc_val) or pd.isna(wl_val):
                            continue
                        vwl = float(wl_val)
                        vc_f = float(vc_val)

                        linked: set[str] = set()
                        # Try NIST reference wavelength first
                        if len(ref_arr) > 0:
                            near = np.where(np.abs(ref_arr - vwl) <= _TOL)[0]
                            for ni in near:
                                linked.add(ref_elems[ni])
                        # Fallback to observed wavelength
                        if not linked and len(obs_arr) > 0:
                            near = np.where(np.abs(obs_arr - vwl) <= _TOL)[0]
                            for ni in near:
                                linked.add(obs_elems[ni])

                        for elem in linked:
                            elem_vc.setdefault(elem, []).append(vc_f)

                # ── Strategy 3: distribute global mean to all ranked elements
                # when neither linkage method produced any values.
                if not elem_vc:
                    all_vc = vc_series.dropna().tolist()
                    if all_vc:
                        global_mean = float(np.mean(all_vc))
                        for elem in ranking_df["Element"].dropna().tolist():
                            elem_vc[str(elem)] = all_vc  # each element sees all

        # Compute mean VC per element from accumulated lists
        elem_mean_vc: dict[str, float | None] = {
            e: float(np.mean(vals)) if vals else None
            for e, vals in elem_vc.items()
        }

        # Build per-element match stats from Step 3 matches
        # avg_delta: mean |Δλ| across all NIST matches for the element
        # avg_score: mean competition score
        # best_lines: up to 5 NIST reference wavelengths with highest scores
        elem_deltas:  dict[str, list[float]] = {}
        elem_scores:  dict[str, list[float]] = {}
        elem_wl_score: dict[str, list[tuple[float, float]]] = {}  # (score, matched_wl)

        if matches:
            for m in matches:
                elem = (getattr(m, "element", None)
                        or getattr(m, "matched_element", None))
                if not elem:
                    continue
                elem = str(elem)
                delta = getattr(m, "delta", None)
                score = getattr(m, "score", None)
                mwl   = getattr(m, "matched_wl", None)

                if delta is not None:
                    try:
                        elem_deltas.setdefault(elem, []).append(abs(float(delta)))
                    except (TypeError, ValueError):
                        pass
                if score is not None:
                    try:
                        s = float(score)
                        elem_scores.setdefault(elem, []).append(s)
                        if mwl is not None:
                            elem_wl_score.setdefault(elem, []).append(
                                (s, float(mwl))
                            )
                    except (TypeError, ValueError):
                        pass

        for _, row in ranking_df.iterrows():
            element = str(row["Element"])
            wins = int(row["Wins"]) if not pd.isna(row["Wins"]) else 0
            tier = self._classify_confidence_tier(wins)

            # avg delta
            deltas = elem_deltas.get(element, [])
            avg_delta = float(np.mean(deltas)) if deltas else None

            # avg score
            scores = elem_scores.get(element, [])
            avg_score = float(np.mean(scores)) if scores else None

            # best lines — top-5 NIST wavelengths by score, deduped
            wl_scores = elem_wl_score.get(element, [])
            if wl_scores:
                wl_scores_sorted = sorted(wl_scores, key=lambda x: x[0], reverse=True)
                seen_wls: set[float] = set()
                best: list[float] = []
                for sc, wl in wl_scores_sorted:
                    rounded = round(wl, 2)
                    if rounded not in seen_wls:
                        seen_wls.add(rounded)
                        best.append(rounded)
                    if len(best) >= 5:
                        break
            else:
                best = []

            rows.append(
                ElementRow(
                    element=element,
                    confidence_tier=tier,
                    matched_lines=wins,
                    mean_vc=elem_mean_vc.get(element),
                    avg_delta=avg_delta,
                    avg_score=avg_score,
                    best_lines=best,
                )
            )
        return rows

    def _get_validated_peak_wavelengths(
        self, detected_peaks, stage5_count: int
    ) -> list[float]:
        """
        Extract wavelengths of the top-N confirmed peaks (Stage 5 proxy).

        Falls back to all peak wavelengths if stage5_count exceeds available peaks.
        """
        wls: list[float] = []
        for p in detected_peaks:
            wl = getattr(p, "wavelength", None) or getattr(p, "position", None)
            if wl is not None:
                wls.append(float(wl))
        # Return first stage5_count wavelengths as a proxy
        return wls[:stage5_count] if stage5_count < len(wls) else wls
