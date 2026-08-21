# -*- coding: utf-8 -*-
"""
Step 7: Quantitative Calibration Curve

Provides curve-fitting, inverse concentration prediction, and LOD/LOQ
calculation to convert LIBS emission-line intensities into quantitative
elemental concentrations (ppm).

Three fit models are supported:
  linear     — y = a·x + b
  quadratic  — y = a·x² + b·x + c
  power_law  — y = a·x^b  (x > 0)

Usage
-----
engine = CalibrationEngine()
results = engine.fit_and_predict(
    points, model_name="linear", element="Ca",
    analytical_wavelength=422.67, extraction_tolerance=0.2,
    unknown_processed_data=step1_widget.processed_data,
    blank_point=blank_point,
)
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import TypedDict

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit, brentq

from src import setup_logger

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# TypedDicts — data models
# ---------------------------------------------------------------------------

class CalibrationPoint(TypedDict):
    """One standard sample with known concentration and extracted intensity."""
    sample_id:     str
    concentration: float          # known value in ppm
    spectrum_file: str            # absolute path to the standard's processed CSV
    intensity:     float | None   # extracted at analytical_wavelength; None until extracted
    is_blank:      bool           # True if this standard is the zero-concentration blank


class FitResult(TypedDict):
    """Output of a single curve_fit call."""
    model:         str                    # "linear" | "quadratic" | "power_law"
    coefficients:  list[float]            # [a, b] / [a, b, c] / [a, b]
    covariance:    list[list[float]]      # pcov from curve_fit (2-D list)
    r_squared:     float                  # coefficient of determination [0, 1]
    rmse:          float                  # root mean square error (intensity units)
    x_range:       tuple[float, float]    # (min_concentration, max_concentration)
    fit_ok:        bool                   # False if curve_fit raised RuntimeError
    error_message: str | None             # populated when fit_ok is False


class CalibrationResults(TypedDict):
    """Complete result returned by :meth:`CalibrationEngine.fit_and_predict`."""
    element:                str
    analytical_wavelength:  float          # nm
    extraction_tolerance:   float          # nm
    fit_result:             FitResult | None
    points:                 list[CalibrationPoint]
    unknown_intensity:      float | None
    unknown_concentration:  float | None   # inferred via inverse curve
    unknown_uncertainty:    float | None   # ±ppm (95 % CI, propagated from pcov)
    in_range:               bool           # unknown within calibration range
    lod_ppm:                float | None
    loq_ppm:                float | None
    blank_noise:            float | None   # σ_blank at analytical wavelength
    missing_info:           list[str]      # reasons why result is incomplete


# ---------------------------------------------------------------------------
# CalibrationEngine
# ---------------------------------------------------------------------------

class CalibrationEngine:
    """
    Stateless computation class for Step 7 quantitative calibration.

    All public methods wrap their bodies in ``try/except`` so that
    :meth:`fit_and_predict` never raises for any combination of inputs.
    """

    # ------------------------------------------------------------------
    # Model functions  (static, same signature as curve_fit expects)
    # ------------------------------------------------------------------

    @staticmethod
    def _model_linear(x, a, b):
        """y = a*x + b"""
        return a * x + b

    @staticmethod
    def _model_quadratic(x, a, b, c):
        """y = a*x^2 + b*x + c"""
        return a * x**2 + b * x + c

    @staticmethod
    def _model_power_law(x, a, b):
        """y = a * x^b   (requires x > 0, a > 0)"""
        return a * np.power(np.abs(x), b)

    # model_name → (function, n_params, lower_bounds, upper_bounds, p0)
    _MODELS: dict[str, tuple] = {
        "linear": (
            _model_linear.__func__,
            2,
            [-np.inf, -np.inf],
            [np.inf, np.inf],
            [1.0, 0.0],
        ),
        "quadratic": (
            _model_quadratic.__func__,
            3,
            [-np.inf, -np.inf, -np.inf],
            [np.inf, np.inf, np.inf],
            [0.001, 1.0, 0.0],
        ),
        "power_law": (
            _model_power_law.__func__,
            2,
            [1e-12, 0.01],
            [np.inf, 10.0],
            [1.0, 0.8],
        ),
    }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fit_and_predict(
        self,
        points: list[CalibrationPoint],
        model_name: str,
        element: str,
        analytical_wavelength: float,
        extraction_tolerance: float,
        unknown_processed_data=None,
        blank_point: CalibrationPoint | None = None,
    ) -> CalibrationResults:
        """
        Top-level method: extract intensities, fit curve, predict concentration.

        Parameters
        ----------
        points :
            Standard calibration points (``is_blank=False``).
        model_name :
            One of ``"linear"``, ``"quadratic"``, ``"power_law"``.
        element :
            Element being quantified (for labelling only).
        analytical_wavelength :
            Emission line wavelength in nm.
        extraction_tolerance :
            Half-window in nm for intensity extraction.
        unknown_processed_data :
            Step 1 ``ProcessedSpectra`` object (already in memory).
        blank_point :
            Optional blank standard (``is_blank=True``).

        Returns
        -------
        CalibrationResults
            Always returns a dict; never raises.
        """
        missing_info: list[str] = []

        # --- Step 1: extract intensities from standard spectra -----------
        populated: list[CalibrationPoint] = []
        for pt in (points or []):
            if pt.get("is_blank"):
                continue
            intensity = self.extract_intensity(
                pt["spectrum_file"],
                analytical_wavelength,
                extraction_tolerance,
            )
            new_pt: CalibrationPoint = dict(pt)  # type: ignore[assignment]
            new_pt["intensity"] = intensity
            populated.append(new_pt)

        # Filter to only points where extraction succeeded
        valid = [p for p in populated if p["intensity"] is not None]

        if len(valid) < 3:
            missing_info.append(
                f"Minimum 3 standards required (only {len(valid)} have valid intensities)"
            )
            return CalibrationResults(
                element=element,
                analytical_wavelength=analytical_wavelength,
                extraction_tolerance=extraction_tolerance,
                fit_result=None,
                points=populated,
                unknown_intensity=None,
                unknown_concentration=None,
                unknown_uncertainty=None,
                in_range=False,
                lod_ppm=None,
                loq_ppm=None,
                blank_noise=None,
                missing_info=missing_info,
            )

        concentrations = np.array([p["concentration"] for p in valid], dtype=float)
        intensities = np.array([p["intensity"] for p in valid], dtype=float)

        # --- Step 2: fit curve -------------------------------------------
        try:
            fit_result = self.fit_curve(concentrations, intensities, model_name)
        except Exception as exc:
            fit_result = FitResult(
                model=model_name,
                coefficients=[],
                covariance=[],
                r_squared=0.0,
                rmse=0.0,
                x_range=(float(concentrations.min()), float(concentrations.max())),
                fit_ok=False,
                error_message=str(exc),
            )
            missing_info.append(f"Curve fitting failed: {exc}")

        # --- Step 3: extract unknown intensity from processed_data -------
        unknown_intensity: float | None = None
        try:
            if unknown_processed_data is not None:
                wl_arr = np.asarray(getattr(unknown_processed_data, "wavelength", []), dtype=float)
                int_arr = np.asarray(getattr(unknown_processed_data, "corrected", []), dtype=float)
                if len(wl_arr) > 0 and len(wl_arr) == len(int_arr):
                    mask = np.abs(wl_arr - analytical_wavelength) <= extraction_tolerance
                    if mask.any():
                        unknown_intensity = float(np.max(int_arr[mask]))
        except Exception as exc:
            logger.warning("Failed to extract unknown intensity: %s", exc)
            missing_info.append(f"Unknown intensity extraction failed: {exc}")

        if unknown_intensity is None:
            missing_info.append("No unknown sample data available (run Step 1 first)")

        # --- Step 4: predict concentration --------------------------------
        unknown_concentration: float | None = None
        unknown_uncertainty: float | None = None
        in_range = False

        if fit_result["fit_ok"] and unknown_intensity is not None:
            try:
                unknown_concentration, unknown_uncertainty = self.predict_concentration(
                    unknown_intensity, fit_result
                )
                if unknown_concentration is not None:
                    lo, hi = fit_result["x_range"]
                    in_range = lo <= unknown_concentration <= hi
            except Exception as exc:
                logger.warning("Concentration prediction failed: %s", exc)
                missing_info.append(f"Concentration prediction failed: {exc}")

        # --- Step 5: blank noise + LOD/LOQ --------------------------------
        blank_noise: float | None = None
        lod_ppm: float | None = None
        loq_ppm: float | None = None

        if blank_point is not None:
            try:
                blank_noise = self.estimate_blank_noise(
                    blank_point["spectrum_file"],
                    analytical_wavelength,
                    extraction_tolerance,
                    window_nm=2.0,
                )
            except Exception as exc:
                logger.warning("Blank noise estimation failed: %s", exc)

        if blank_noise is not None and fit_result["fit_ok"]:
            try:
                lod_ppm, loq_ppm = self.compute_lod_loq(blank_noise, fit_result)
            except Exception as exc:
                logger.warning("LOD/LOQ computation failed: %s", exc)

        return CalibrationResults(
            element=element,
            analytical_wavelength=analytical_wavelength,
            extraction_tolerance=extraction_tolerance,
            fit_result=fit_result,
            points=populated,
            unknown_intensity=unknown_intensity,
            unknown_concentration=unknown_concentration,
            unknown_uncertainty=unknown_uncertainty,
            in_range=in_range,
            lod_ppm=lod_ppm,
            loq_ppm=loq_ppm,
            blank_noise=blank_noise,
            missing_info=missing_info,
        )

    # ------------------------------------------------------------------
    # extract_intensity
    # ------------------------------------------------------------------

    def extract_intensity(
        self,
        spectrum_path: str,
        wavelength_nm: float,
        tolerance_nm: float,
    ) -> float | None:
        """
        Read a processed spectrum CSV and return the maximum intensity
        within ``wavelength_nm ± tolerance_nm``.

        Returns ``None`` if the file cannot be read or no row falls in
        the window.  Never raises.
        """
        try:
            path = Path(spectrum_path)
            if not path.exists():
                logger.debug("Spectrum file not found: %s", path)
                return None

            df = pd.read_csv(str(path))
            if df.empty:
                return None

            # Auto-detect wavelength column (case-insensitive)
            wl_col = None
            for col in df.columns:
                if "wavelength" in col.lower():
                    wl_col = col
                    break
            if wl_col is None:
                logger.debug("No wavelength column found in %s", path.name)
                return None

            # Auto-detect intensity column: prefer "corrected" then "intensity"
            int_col = None
            priority = ["corrected", "intensity", "signal", "counts"]
            cols_lower = {c.lower(): c for c in df.columns}
            for candidate in priority:
                if candidate in cols_lower:
                    int_col = cols_lower[candidate]
                    break
            if int_col is None:
                # fallback: second column
                if len(df.columns) >= 2:
                    int_col = df.columns[1]
                else:
                    return None

            wl_arr = pd.to_numeric(df[wl_col], errors="coerce").values
            int_arr = pd.to_numeric(df[int_col], errors="coerce").values

            mask = np.abs(wl_arr - wavelength_nm) <= tolerance_nm
            valid_intensities = int_arr[mask & np.isfinite(int_arr) & np.isfinite(wl_arr)]

            if len(valid_intensities) == 0:
                return None

            return float(np.max(valid_intensities))

        except Exception as exc:
            logger.debug("extract_intensity failed for %s: %s", spectrum_path, exc)
            return None

    # ------------------------------------------------------------------
    # compute_r_squared
    # ------------------------------------------------------------------

    @staticmethod
    def compute_r_squared(y_actual: np.ndarray, y_predicted: np.ndarray) -> float:
        """
        R² coefficient of determination, clamped to [0, 1].

        Returns 0.0 when SS_tot == 0 (flat target).
        """
        try:
            y_actual = np.asarray(y_actual, dtype=float)
            y_predicted = np.asarray(y_predicted, dtype=float)
            ss_res = float(np.sum((y_actual - y_predicted) ** 2))
            ss_tot = float(np.sum((y_actual - np.mean(y_actual)) ** 2))
            if ss_tot == 0.0:
                return 0.0
            r2 = 1.0 - ss_res / ss_tot
            return float(np.clip(r2, 0.0, 1.0))
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # fit_curve
    # ------------------------------------------------------------------

    def fit_curve(
        self,
        concentrations: np.ndarray,
        intensities: np.ndarray,
        model: str,
    ) -> FitResult:
        """
        Fit a calibration model to (concentrations, intensities) pairs.

        Parameters
        ----------
        concentrations :
            1-D array of known concentrations (ppm).
        intensities :
            1-D array of extracted intensities (same order).
        model :
            ``"linear"``, ``"quadratic"``, or ``"power_law"``.

        Returns
        -------
        FitResult

        Raises
        ------
        ValueError
            When fewer than 3 data points are provided.
        """
        concentrations = np.asarray(concentrations, dtype=float)
        intensities = np.asarray(intensities, dtype=float)

        if len(concentrations) < 3:
            raise ValueError(
                f"Minimum 3 calibration points required; got {len(concentrations)}"
            )

        if model not in self._MODELS:
            raise ValueError(
                f"Unknown model '{model}'. Choose from: {list(self._MODELS)}"
            )

        fn, _n_params, lower, upper, p0 = self._MODELS[model]
        x_range = (float(concentrations.min()), float(concentrations.max()))

        try:
            popt, pcov = curve_fit(
                fn,
                concentrations,
                intensities,
                p0=p0,
                bounds=(lower, upper),
                maxfev=10_000,
            )

            y_pred = fn(concentrations, *popt)
            r2 = self.compute_r_squared(intensities, y_pred)
            rmse = float(np.sqrt(np.mean((intensities - y_pred) ** 2)))

            return FitResult(
                model=model,
                coefficients=popt.tolist(),
                covariance=pcov.tolist(),
                r_squared=r2,
                rmse=rmse,
                x_range=x_range,
                fit_ok=True,
                error_message=None,
            )

        except RuntimeError as exc:
            logger.warning("curve_fit did not converge: %s", exc)
            return FitResult(
                model=model,
                coefficients=[],
                covariance=[],
                r_squared=0.0,
                rmse=0.0,
                x_range=x_range,
                fit_ok=False,
                error_message=str(exc),
            )

    # ------------------------------------------------------------------
    # predict_concentration
    # ------------------------------------------------------------------

    def predict_concentration(
        self,
        intensity: float,
        fit_result: FitResult,
    ) -> tuple[float | None, float | None]:
        """
        Invert the calibration curve to predict concentration from intensity.

        Returns
        -------
        (concentration_ppm, uncertainty_ppm)
            Both are ``None`` when prediction cannot be made.
        """
        if not fit_result["fit_ok"] or not fit_result["coefficients"]:
            return None, None

        try:
            model = fit_result["model"]
            coeffs = np.asarray(fit_result["coefficients"], dtype=float)
            pcov = np.asarray(fit_result["covariance"], dtype=float)
            y = float(intensity)

            if model == "linear":
                a, b = coeffs[0], coeffs[1]
                if abs(a) < 1e-15:
                    return None, None
                x = (y - b) / a

                # First-order uncertainty propagation
                # dx/da = -(y-b)/a²,  dx/db = -1/a
                dx_da = -(y - b) / (a ** 2)
                dx_db = -1.0 / a
                var_a = float(pcov[0, 0]) if pcov.shape == (2, 2) else 0.0
                var_b = float(pcov[1, 1]) if pcov.shape == (2, 2) else 0.0
                cov_ab = float(pcov[0, 1]) if pcov.shape == (2, 2) else 0.0
                var_x = (dx_da ** 2 * var_a
                         + dx_db ** 2 * var_b
                         + 2 * dx_da * dx_db * cov_ab)
                uncertainty = 1.96 * math.sqrt(max(var_x, 0.0))
                return float(x), float(uncertainty)

            elif model == "quadratic":
                a, b, c = coeffs[0], coeffs[1], coeffs[2]
                # Solve a*x² + b*x + (c - y) = 0
                discriminant = b ** 2 - 4 * a * (c - y)
                if discriminant < 0 or abs(a) < 1e-15:
                    # Degenerate: fall back to linear approximation
                    if abs(b) < 1e-15:
                        return None, None
                    x = (y - c) / b
                else:
                    x1 = (-b + math.sqrt(discriminant)) / (2 * a)
                    x2 = (-b - math.sqrt(discriminant)) / (2 * a)
                    lo, hi = fit_result["x_range"]
                    # Pick the root that falls within (or nearest to) the calibration range
                    candidates = [
                        (abs(xi - (lo + hi) / 2), xi)
                        for xi in (x1, x2)
                        if math.isfinite(xi)
                    ]
                    if not candidates:
                        return None, None
                    x = min(candidates, key=lambda t: t[0])[1]

                # Uncertainty via numerical gradient of the inverse function
                uncertainty = self._quadratic_uncertainty(x, a, b, pcov)
                return float(x), float(uncertainty)

            elif model == "power_law":
                a, b = coeffs[0], coeffs[1]
                if a <= 0 or b == 0 or y <= 0:
                    return None, None
                # x = (y / a)^(1/b)
                x = (y / a) ** (1.0 / b)

                # Propagate via partial derivatives of ln(x) w.r.t. ln(a) and b
                # ln(x) = (ln(y) - ln(a)) / b
                # d(ln x)/d(ln a) = -1/b   → dx/da = -x/(a*b)
                # d(ln x)/db      = -ln(y/a)/b²  → dx/db = x * (-ln(y/a)) / b²
                if a > 0 and b != 0 and y > 0:
                    dx_da = -x / (a * b)
                    ratio = y / a
                    dx_db = x * (-math.log(ratio)) / (b ** 2) if ratio > 0 else 0.0
                    var_a = float(pcov[0, 0]) if pcov.shape == (2, 2) else 0.0
                    var_b = float(pcov[1, 1]) if pcov.shape == (2, 2) else 0.0
                    cov_ab = float(pcov[0, 1]) if pcov.shape == (2, 2) else 0.0
                    var_x = (dx_da ** 2 * var_a
                             + dx_db ** 2 * var_b
                             + 2 * dx_da * dx_db * cov_ab)
                    uncertainty = 1.96 * math.sqrt(max(var_x, 0.0))
                else:
                    uncertainty = 0.0
                return float(x), float(uncertainty)

            else:
                return None, None

        except Exception as exc:
            logger.debug("predict_concentration failed: %s", exc)
            return None, None

    @staticmethod
    def _quadratic_uncertainty(
        x: float, a: float, b: float, pcov: np.ndarray
    ) -> float:
        """First-order uncertainty for quadratic inversion at point x."""
        try:
            # derivative of inverse quadratic: dx/da, dx/db, dx/dc
            # x = root of a*x²+b*x+(c-y)=0; differentiate implicitly
            denom = 2 * a * x + b
            if abs(denom) < 1e-15:
                return 0.0
            dx_da = -(x ** 2) / denom
            dx_db = -x / denom
            dx_dc = -1.0 / denom
            grad = np.array([dx_da, dx_db, dx_dc])
            if pcov.shape == (3, 3):
                var_x = float(grad @ pcov @ grad)
                return 1.96 * math.sqrt(max(var_x, 0.0))
        except Exception:
            pass
        return 0.0

    # ------------------------------------------------------------------
    # estimate_blank_noise
    # ------------------------------------------------------------------

    def estimate_blank_noise(
        self,
        spectrum_path: str,
        wavelength_nm: float,
        tolerance_nm: float,
        window_nm: float = 2.0,
    ) -> float | None:
        """
        Estimate σ_blank as std of intensities near the analytical wavelength
        in the blank spectrum.

        Returns ``None`` on any failure.
        """
        try:
            path = Path(spectrum_path)
            if not path.exists():
                return None
            df = pd.read_csv(str(path))
            if df.empty:
                return None

            wl_col = None
            for col in df.columns:
                if "wavelength" in col.lower():
                    wl_col = col
                    break
            if wl_col is None:
                return None

            int_col = None
            cols_lower = {c.lower(): c for c in df.columns}
            for candidate in ["corrected", "intensity", "signal", "counts"]:
                if candidate in cols_lower:
                    int_col = cols_lower[candidate]
                    break
            if int_col is None and len(df.columns) >= 2:
                int_col = df.columns[1]
            if int_col is None:
                return None

            wl_arr = pd.to_numeric(df[wl_col], errors="coerce").values
            int_arr = pd.to_numeric(df[int_col], errors="coerce").values
            mask = np.abs(wl_arr - wavelength_nm) <= window_nm
            vals = int_arr[mask & np.isfinite(int_arr)]
            if len(vals) < 2:
                return None
            return float(np.std(vals))

        except Exception as exc:
            logger.debug("estimate_blank_noise failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # compute_lod_loq
    # ------------------------------------------------------------------

    def compute_lod_loq(
        self,
        blank_noise: float | None,
        fit_result: FitResult,
    ) -> tuple[float | None, float | None]:
        """
        Compute LOD = 3σ/slope and LOQ = 10σ/slope.

        For non-linear models, the equivalent concentration is found
        numerically using ``scipy.optimize.brentq``.

        Returns ``(None, None)`` when ``blank_noise`` is None or
        ``fit_result.fit_ok`` is False.
        """
        if blank_noise is None or blank_noise <= 0:
            return None, None
        if not fit_result["fit_ok"] or not fit_result["coefficients"]:
            return None, None

        try:
            model = fit_result["model"]
            coeffs = fit_result["coefficients"]
            lo, hi = fit_result["x_range"]
            fn = self._MODELS[model][0]

            def _invert(target_intensity: float) -> float | None:
                """Find x such that model(x) ≈ target_intensity."""
                try:
                    # Estimate baseline intensity at x=0 for the reference
                    baseline_y = float(fn(max(lo * 0.01, 1e-6), *coeffs))
                    target_y = baseline_y + target_intensity

                    # Search over a generous range
                    x_lo = max(lo * 0.001, 1e-6)
                    x_hi = hi * 10.0

                    def _f(x):
                        return float(fn(x, *coeffs)) - target_y

                    # brentq needs sign change
                    if _f(x_lo) * _f(x_hi) > 0:
                        # Fall back to linear approximation with the slope at x_lo
                        slope = (float(fn(x_lo * 1.01, *coeffs)) - float(fn(x_lo, *coeffs))) / (x_lo * 0.01)
                        if abs(slope) < 1e-15:
                            return None
                        return target_intensity / slope
                    return float(brentq(_f, x_lo, x_hi, xtol=1e-6, maxiter=200))
                except Exception:
                    return None

            if model == "linear":
                a = coeffs[0]
                if abs(a) < 1e-15:
                    return None, None
                lod = 3.0 * blank_noise / abs(a)
                loq = 10.0 * blank_noise / abs(a)
            else:
                lod = _invert(3.0 * blank_noise)
                loq = _invert(10.0 * blank_noise)

            return lod, loq

        except Exception as exc:
            logger.debug("compute_lod_loq failed: %s", exc)
            return None, None

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    @staticmethod
    def results_to_json(results: CalibrationResults) -> str:
        """Serialise results to a JSON string (no Figure objects)."""
        safe = {
            k: v for k, v in results.items()
            if k not in ("fit_result",)
        }
        # Serialise fit_result separately (numpy types need conversion)
        fr = results.get("fit_result")
        if fr is not None:
            safe["fit_result"] = {
                "model": fr.get("model", ""),
                "coefficients": [float(c) for c in (fr.get("coefficients") or [])],
                "covariance": [
                    [float(v) for v in row]
                    for row in (fr.get("covariance") or [])
                ],
                "r_squared": float(fr.get("r_squared", 0)),
                "rmse": float(fr.get("rmse", 0)),
                "x_range": list(fr.get("x_range", [0, 0])),
                "fit_ok": bool(fr.get("fit_ok", False)),
                "error_message": fr.get("error_message"),
            }
        else:
            safe["fit_result"] = None

        # Convert numpy types in points
        safe_points = []
        for pt in (results.get("points") or []):
            safe_points.append({
                "sample_id": str(pt.get("sample_id", "")),
                "concentration": float(pt.get("concentration", 0)),
                "spectrum_file": str(pt.get("spectrum_file", "")),
                "intensity": (float(pt["intensity"]) if pt.get("intensity") is not None else None),
                "is_blank": bool(pt.get("is_blank", False)),
            })
        safe["points"] = safe_points

        # Convert any remaining numpy scalars
        for k in ("unknown_intensity", "unknown_concentration",
                  "unknown_uncertainty", "lod_ppm", "loq_ppm", "blank_noise"):
            v = safe.get(k)
            if v is not None:
                try:
                    safe[k] = float(v)
                except (TypeError, ValueError):
                    safe[k] = None

        return json.dumps(safe, indent=2, default=str)

    @staticmethod
    def results_from_json(json_str: str) -> CalibrationResults | None:
        """Restore a CalibrationResults from a JSON string. Returns None on failure."""
        try:
            data = json.loads(json_str)
            fr_data = data.get("fit_result")
            if fr_data is not None:
                data["fit_result"] = FitResult(
                    model=fr_data.get("model", "linear"),
                    coefficients=fr_data.get("coefficients", []),
                    covariance=fr_data.get("covariance", []),
                    r_squared=float(fr_data.get("r_squared", 0)),
                    rmse=float(fr_data.get("rmse", 0)),
                    x_range=tuple(fr_data.get("x_range", [0, 0])),
                    fit_ok=bool(fr_data.get("fit_ok", False)),
                    error_message=fr_data.get("error_message"),
                )
            return CalibrationResults(**data)
        except Exception as exc:
            logger.warning("results_from_json failed: %s", exc)
            return None
