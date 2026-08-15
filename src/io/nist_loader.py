# -*- coding: utf-8 -*-
"""
NIST Database Loader

Scans the bundled 'NIST database' folder, normalises all column schema
variants, and serves DataFrames from a SQLite cache so the GUI never has
to manually upload files.

Cache file: <project_root>/NIST database/.nist_cache.db
Cache is rebuilt automatically whenever any source file is newer than the
cache, keeping the system self-maintaining.

Architecture notes
------------------
- Zero GUI dependencies — usable from CLI / headless pipelines.
- Two logical databases: NEUTRAL (suffix ' I') and IONIC (suffix ' II').
- Each element is queryable individually or as a merged DataFrame.
- Adding a new element = drop the file into the folder = cache auto-updates.
"""

import os
import re
import sys
import sqlite3
import logging
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Path resolution ───────────────────────────────────────────────────────────
#
# There are three environments to handle:
#
#  A) Development  — running from the repo with `python gui_launcher.py`
#     sys.executable = .../python.exe  (inside venv or system Python)
#     __file__       = .../src/io/nist_loader.py
#     → project root is __file__'s great-grandparent
#
#  B) PyInstaller one-folder build  — user runs LIBS_Analysis.exe
#     sys.executable = dist/LIBS_Analysis/LIBS_Analysis.exe
#     sys.frozen     = True
#     sys._MEIPASS   = temp extraction dir (READ-ONLY, deleted on exit)
#     → NIST database MUST live beside the .exe, not inside the bundle
#     → use sys.executable's parent as the root
#
#  C) Installed to Program Files or similar  (future)
#     → same as B; cache goes to user's writable AppData folder
#
# The NIST database folder is always resolved relative to the application root.
# The SQLite cache is written to a writable location (AppData on Windows, or
# the database folder itself when writable — development mode).


def _app_root() -> Path:
    """
    Return the directory that contains (or should contain) the 'NIST database'
    folder.

    Resolution order (frozen / installed exe):
      1. Registry key  HKLM\\Software\\JFD Tech\\LIBS Spectral Analysis\\DatabasePath
         Written by the Inno Setup installer.
      2. {ProgramData}\\LIBS_Analysis  — standard installer fallback
      3. _internal\\ beside the .exe   — PyInstaller 6.x one-folder layout
      4. Beside the .exe               — PyInstaller <6 / portable layout
      5. Final fallback (UI will warn if DB missing)

    Development (not frozen):
      Repository root — great-grandparent of this source file.
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent

        # ── 1. Registry (installer sets this) ────────────────────────────
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"Software\JFD Tech\LIBS Spectral Analysis",
            )
            db_path_str, _ = winreg.QueryValueEx(key, "DatabasePath")
            winreg.CloseKey(key)
            db_path = Path(db_path_str)
            if db_path.exists():
                return db_path.parent   # DatabasePath IS the NIST database dir
        except Exception:
            pass   # registry key absent (portable build or first run)

        # ── 2. ProgramData (standard installer layout) ────────────────────
        prog_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        installed_root = prog_data / "LIBS_Analysis"
        if (installed_root / "NIST database").exists():
            return installed_root

        # ── 3. _internal subfolder (PyInstaller 6.x one-folder layout) ───
        internal_dir = exe_dir / "_internal"
        if (internal_dir / "NIST database").exists():
            return internal_dir

        # ── 4. Beside the exe (PyInstaller <6 / portable) ────────────────
        if (exe_dir / "NIST database").exists():
            return exe_dir

        # ── 5. Final fallback ─────────────────────────────────────────────
        return exe_dir

    # Development: src/io/nist_loader.py -> src/io -> src -> project root
    return Path(__file__).resolve().parent.parent.parent


def _cache_dir() -> Path:
    """
    Return a writable directory for the SQLite cache.

    Always %APPDATA%\\LIBS_Analysis when frozen (works for both portable and
    installed layouts because AppData is always user-writable).
    Falls back to the NIST database folder in development mode.
    """
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA")
        if appdata:
            cache_home = Path(appdata) / "LIBS_Analysis"
            cache_home.mkdir(parents=True, exist_ok=True)
            return cache_home
    # Development — write cache next to the source database folder
    nist_folder = _app_root() / "NIST database"
    return nist_folder


_NIST_ROOT      = _app_root()    / "NIST database"
_CACHE_PATH     = _cache_dir()   / ".nist_cache.db"
NEUTRAL_FOLDER  = _NIST_ROOT     / "Neutral lines"
IONIC_FOLDER    = _NIST_ROOT     / "Ionic lines"

# ── Column normalisation map ─────────────────────────────────────────────────
# Maps known column name variants → canonical names.
# Matching is done after strip + lower, so whitespace/case is irrelevant.
_WAVELENGTH_ALIASES = {
    "wavelength", "wl", "wavelength (nm)", "wave", "lambda",
}
_ELEMENT_ALIASES = {
    "element", "elements", "element_symbol", "ion", "species", "atom",
}
_AKI_ALIASES = {
    "aki", "aki(s^-1)", "aki(s-1)", "aki)", "strength", "transition", "gf",
}
_REL_INT_ALIASES = {
    "relative_intensity", "rel_int", "rel intensity", "relative int",
    "realtive_intensity",   # typo in Cr I
    "relaive_intensity",    # typo in Zr I
    "relative _intensity",  # space in Au I
    "relative_intensty",    # possible future typo
}

_FOOTNOTE_RE = re.compile(r"[^0-9.\-eE+]")   # strip non-numeric chars from values


# ─────────────────────────────────────────────────────────────────────────────
class NISTDatabaseLoader:
    """
    Load and serve the bundled NIST spectral line databases.

    Usage
    -----
    loader = NISTDatabaseLoader()

    # All neutral lines merged
    df_neutral = loader.get_neutral()

    # All ionic lines merged
    df_ionic = loader.get_ionic()

    # Available element names
    neutral_elements = loader.list_elements('neutral')
    ionic_elements   = loader.list_elements('ionic')

    # Filtered by selected elements
    df = loader.get_dataframe('neutral', elements=['Fe I', 'Ca I', 'Mg I'])
    df = loader.get_dataframe('ionic',  elements=['Fe II', 'Ca II'])

    # Combined neutral + ionic
    df_both = loader.get_dataframe('both', elements=['Fe I', 'Fe II'])
    """

    def __init__(self, nist_root: Optional[Path] = None):
        self._nist_root   = Path(nist_root) if nist_root else _NIST_ROOT
        self._neutral_dir = self._nist_root / "Neutral lines"
        self._ionic_dir   = self._nist_root / "Ionic lines"
        # Cache lives in the writable location determined at module load time,
        # unless a custom nist_root is provided (tests / headless usage).
        self._cache_path  = (
            _CACHE_PATH if nist_root is None
            else Path(nist_root) / ".nist_cache.db"
        )

        self._neutral_df: Optional[pd.DataFrame] = None
        self._ionic_df:   Optional[pd.DataFrame] = None

        logger.info(f"NISTDatabaseLoader: db_root={self._nist_root}")
        logger.info(f"NISTDatabaseLoader: cache={self._cache_path}")
        self._ensure_cache()

    # ── Public API ────────────────────────────────────────────────────────────

    def list_elements(self, line_type: str) -> List[str]:
        """
        Return sorted list of element names available for a given type.

        Parameters
        ----------
        line_type : str
            'neutral', 'ionic', or 'both'
        """
        df = self._get_raw(line_type)
        return sorted(df["Element"].unique().tolist())

    def get_neutral(self) -> pd.DataFrame:
        """Return all neutral lines as a standardised DataFrame."""
        df = self._get_raw("neutral").copy()
        return df.drop(columns=["_line_type"], errors="ignore")

    def get_ionic(self) -> pd.DataFrame:
        """Return all ionic lines as a standardised DataFrame."""
        df = self._get_raw("ionic").copy()
        return df.drop(columns=["_line_type"], errors="ignore")

    def get_dataframe(
        self,
        line_type: str,
        elements: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Return a (optionally filtered) standardised DataFrame ready for
        NISTMatcher.

        Parameters
        ----------
        line_type : str
            'neutral', 'ionic', or 'both'
        elements : list[str] | None
            If provided, only rows whose Element is in this list are returned.
            Pass None to get all elements.

        Returns
        -------
        pd.DataFrame
            Columns: Element, Wavelength, Aki, relative_intensity
        """
        df = self._get_raw(line_type).copy()
        if elements:
            df = df[df["Element"].isin(elements)]
        # Drop internal tracking column before returning
        df = df.drop(columns=["_line_type"], errors="ignore")
        return df.reset_index(drop=True)

    def element_count(self, line_type: str) -> int:
        """Number of distinct elements for the given type."""
        return len(self.list_elements(line_type))

    def row_count(self, line_type: str) -> int:
        """Total spectral lines for the given type."""
        return len(self._get_raw(line_type))

    # ── Cache management ─────────────────────────────────────────────────────

    def _ensure_cache(self):
        """Build or refresh the SQLite cache if source files have changed."""
        if self._cache_is_fresh():
            logger.info("NIST cache is up-to-date, loading from cache.")
            self._load_from_cache()
        else:
            logger.info("NIST cache is stale or missing — rebuilding.")
            self._build_cache()

    def _cache_is_fresh(self) -> bool:
        """True if the cache DB exists and is newer than all source files."""
        if not self._cache_path.exists():
            return False
        cache_mtime = self._cache_path.stat().st_mtime
        for folder in (self._neutral_dir, self._ionic_dir):
            if not folder.exists():
                continue
            for fp in folder.iterdir():
                if fp.suffix.lower() in (".csv", ".xlsx") or \
                   fp.name.lower().endswith(".csv.xlsx") or \
                   fp.name.lower().endswith(".scv.xlsx"):
                    if fp.stat().st_mtime > cache_mtime:
                        return False
        return True

    def _build_cache(self):
        """Parse all source files and write to SQLite cache."""
        neutral_frames = []
        ionic_frames   = []

        for folder, frames, db_type in [
            (self._neutral_dir, neutral_frames, "neutral"),
            (self._ionic_dir,   ionic_frames,   "ionic"),
        ]:
            if not folder.exists():
                logger.warning(f"NIST folder not found: {folder}")
                continue

            for fp in sorted(folder.iterdir()):
                if not self._is_data_file(fp):
                    continue
                try:
                    df = self._load_single_file(fp)
                    if df is not None and not df.empty:
                        df["_line_type"] = db_type
                        frames.append(df)
                        logger.debug(f"  Loaded {len(df):5d} rows from {fp.name}")
                except Exception as exc:
                    logger.warning(f"  Skipped {fp.name}: {exc}")

        self._neutral_df = pd.concat(neutral_frames, ignore_index=True) if neutral_frames else _empty_df()
        self._ionic_df   = pd.concat(ionic_frames,   ignore_index=True) if ionic_frames   else _empty_df()

        logger.info(
            f"Cache built: neutral={len(self._neutral_df):,} rows, "
            f"ionic={len(self._ionic_df):,} rows"
        )
        self._write_cache()

    def _write_cache(self):
        """Persist the in-memory DataFrames to SQLite."""
        try:
            con = sqlite3.connect(str(self._cache_path))
            self._neutral_df.to_sql("neutral", con, if_exists="replace", index=False)
            self._ionic_df.to_sql("ionic",   con, if_exists="replace", index=False)
            # Store schema version so future code changes can force a rebuild
            con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            con.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', '2')")
            con.commit()
            con.close()
            logger.info(f"NIST cache written to {self._cache_path}")
        except Exception as exc:
            logger.warning(f"Could not write NIST cache: {exc}")

    def _load_from_cache(self):
        """Read DataFrames from the SQLite cache."""
        try:
            con = sqlite3.connect(str(self._cache_path))
            # Verify schema version
            try:
                ver = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
                if ver is None or ver[0] != "2":
                    con.close()
                    logger.info("Cache schema mismatch — rebuilding.")
                    self._build_cache()
                    return
            except Exception:
                con.close()
                self._build_cache()
                return

            self._neutral_df = pd.read_sql("SELECT * FROM neutral", con)
            self._ionic_df   = pd.read_sql("SELECT * FROM ionic",   con)
            con.close()

            # Drop internal column if present
            for df in (self._neutral_df, self._ionic_df):
                if "_line_type" in df.columns:
                    df.drop(columns=["_line_type"], inplace=True)

            logger.info(
                f"Cache loaded: neutral={len(self._neutral_df):,} rows, "
                f"ionic={len(self._ionic_df):,} rows"
            )
        except Exception as exc:
            logger.warning(f"Cache load failed ({exc}) — rebuilding from source.")
            self._build_cache()

    # ── File parsing ─────────────────────────────────────────────────────────

    @staticmethod
    def _is_data_file(fp: Path) -> bool:
        name = fp.name.lower()
        return (
            name.endswith(".csv") or
            name.endswith(".xlsx") or
            name.endswith(".csv.xlsx") or
            name.endswith(".scv.xlsx")   # typo variant in source data
        ) and not fp.name.startswith("~")  # skip Excel temp files

    def _load_single_file(self, fp: Path) -> Optional[pd.DataFrame]:
        """
        Load one source file, normalise columns, and return a clean DataFrame
        with columns [Element, Wavelength, Aki, relative_intensity].
        """
        name_lower = fp.name.lower()

        # ── Read raw data ──────────────────────────────────────────────────
        if name_lower.endswith(".xlsx") or \
           name_lower.endswith(".csv.xlsx") or \
           name_lower.endswith(".scv.xlsx"):
            raw = pd.read_excel(fp)
        else:
            raw = pd.read_csv(fp)

        if raw.empty:
            return None

        # Strip whitespace from column names
        raw.columns = [str(c).strip() for c in raw.columns]

        # ── Map columns ───────────────────────────────────────────────────
        col_map = self._detect_columns(raw, fp.stem)
        df = pd.DataFrame()

        # Wavelength (required)
        wl_raw = raw[col_map["wavelength"]]
        df["Wavelength"] = pd.to_numeric(wl_raw, errors="coerce")

        # Element
        if col_map["element"]:
            df["Element"] = raw[col_map["element"]].astype(str).str.strip()
        else:
            # Infer from filename stem (e.g. "Au I", "Fe II")
            inferred = _infer_element_from_stem(fp.stem)
            df["Element"] = inferred

        # Aki (transition probability)
        if col_map["aki"]:
            df["Aki"] = _clean_numeric(raw[col_map["aki"]])
        else:
            df["Aki"] = np.nan

        # Relative intensity
        if col_map["rel_int"]:
            df["relative_intensity"] = _clean_numeric(raw[col_map["rel_int"]])
        else:
            df["relative_intensity"] = np.nan

        # ── Sanitise ──────────────────────────────────────────────────────
        df = df.dropna(subset=["Wavelength"])
        df["Wavelength"] = df["Wavelength"].astype(np.float64)
        df["Aki"] = df["Aki"].fillna(np.nan).astype(np.float64)
        df["relative_intensity"] = df["relative_intensity"].fillna(np.nan).astype(np.float64)

        # Normalise element: replace 'nan' / empty strings with inferred name
        bad_elem = df["Element"].isin(["nan", "None", "", "NaN"])
        if bad_elem.any():
            df.loc[bad_elem, "Element"] = _infer_element_from_stem(fp.stem)

        return df[["Element", "Wavelength", "Aki", "relative_intensity"]]

    def _detect_columns(self, df: pd.DataFrame, file_stem: str) -> dict:
        """
        Return a dict mapping canonical roles to actual column names.
        Falls back gracefully when columns are missing or have typos.
        """
        col_lower = {c.strip().lower(): c for c in df.columns}

        def find(aliases):
            for alias in aliases:
                if alias in col_lower:
                    return col_lower[alias]
            return None

        wl = find(_WAVELENGTH_ALIASES)
        if wl is None:
            raise ValueError(f"No wavelength column found in {file_stem!r}. "
                             f"Columns: {list(df.columns)}")

        # Element column: also try the file stem itself as a column name
        elem = find(_ELEMENT_ALIASES)
        if elem is None:
            # Some files use the element symbol itself as column header (Au I, Cr II…)
            inferred = _infer_element_from_stem(file_stem)
            if inferred.lower() in col_lower:
                elem = col_lower[inferred.lower()]

        aki     = find(_AKI_ALIASES)
        rel_int = find(_REL_INT_ALIASES)

        return {"wavelength": wl, "element": elem, "aki": aki, "rel_int": rel_int}

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_raw(self, line_type: str) -> pd.DataFrame:
        """Return the in-memory DataFrame for the requested type."""
        if self._neutral_df is None or self._ionic_df is None:
            self._ensure_cache()

        lt = line_type.lower()
        if lt == "neutral":
            return self._neutral_df
        elif lt == "ionic":
            return self._ionic_df
        elif lt == "both":
            return pd.concat([self._neutral_df, self._ionic_df], ignore_index=True)
        else:
            raise ValueError(f"line_type must be 'neutral', 'ionic', or 'both', got {line_type!r}")

    def force_rebuild(self):
        """Delete cache and rebuild from source files."""
        if self._cache_path.exists():
            self._cache_path.unlink()
        self._neutral_df = None
        self._ionic_df   = None
        self._build_cache()

    def db_folder(self) -> Path:
        """Return the path to the 'NIST database' root folder."""
        return self._nist_root

    def neutral_folder(self) -> Path:
        """Return the path to the 'Neutral lines' folder."""
        return self._neutral_dir

    def ionic_folder(self) -> Path:
        """Return the path to the 'Ionic lines' folder."""
        return self._ionic_dir


# ── Module-level singleton ────────────────────────────────────────────────────
# Instantiated once and reused across the application to avoid redundant I/O.
_loader_instance: Optional[NISTDatabaseLoader] = None


def get_loader() -> NISTDatabaseLoader:
    """Return the application-wide NISTDatabaseLoader singleton."""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = NISTDatabaseLoader()
    return _loader_instance


# ── Utility functions ─────────────────────────────────────────────────────────

def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["Element", "Wavelength", "Aki", "relative_intensity"])


def _infer_element_from_stem(stem: str) -> str:
    """
    Extract the element label from a filename stem.

    Examples
    --------
    'Fe I'      → 'Fe I'
    'Fe II'     → 'Fe II'
    'Ba-I'      → 'Ba I'
    'B II '     → 'B II'
    'Ni II '    → 'Ni II'
    'I II.scv'  → 'I II'   (handled upstream by Path.stem)
    """
    # Normalise dashes used as separators and collapse whitespace
    label = re.sub(r"[-_]+", " ", stem).strip()
    # Keep only the element symbol + ionisation suffix (e.g. 'Ca II')
    match = re.match(r"([A-Z][a-z]?\s*(?:I{1,3}V?|V?I{0,3}))\b", label)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    return label.strip()


def _clean_numeric(series: pd.Series) -> pd.Series:
    """
    Convert a Series to float, stripping non-numeric footnote characters
    like asterisks, trailing letters, etc.

    '130*'  → 130.0
    '2400r' → 2400.0
    ''      → NaN
    """
    def _parse(v):
        if pd.isna(v):
            return np.nan
        s = str(v).strip()
        # Remove any character that is not part of a number
        s = re.sub(r"[^0-9.\-eE+]", "", s)
        if s in ("", ".", "-", "+"):
            return np.nan
        try:
            return float(s)
        except ValueError:
            return np.nan

    return series.apply(_parse)
