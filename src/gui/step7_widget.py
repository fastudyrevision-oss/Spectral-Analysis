# -*- coding: utf-8 -*-
"""
Step 7 Widget - Quantitative Calibration Curve

Two-column layout mirroring Step 6:
  Left  (scrollable, ≤390 px): title, status banner, element selector,
                                 parameters, standards table, blank loader,
                                 primary fit button, export buttons, progress bar.
  Right (stretch): QTabWidget with three chart tabs (Calibration Curve,
                   Residuals, LOD/LOQ) above a QSplitter-mounted result label.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QScrollArea, QTabWidget, QProgressBar, QFileDialog,
    QComboBox, QDoubleSpinBox, QCheckBox, QGroupBox,
)
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from src import setup_logger
from src.core.step7_calibration import CalibrationEngine, CalibrationPoint, CalibrationResults
from src.gui.charts import ChartEngine
from src.gui.export_engine import export_step7_csv, export_step7_png, generate_pdf_report
from src.gui.gui_utils import HighDpiToolbar as NavigationToolbar2QT, WorkerThread, show_error, show_info
from src.gui.theme import (
    primary_button_style, secondary_button_style, step_title_font,
    summary_banner_style, progress_bar_style, instruction_banner_style,
    C_ERROR, C_TEXT, C_TEXT2,
    get_chart_bg,
)

logger = setup_logger(__name__)

# Column indices for the standards table
_COL_SAMPLE_ID    = 0
_COL_CONC         = 1
_COL_SPECTRUM     = 2
_COL_INTENSITY    = 3
_COL_IS_BLANK     = 4


class Step7Widget(QWidget):
    """
    UI widget for Step 7: Quantitative Calibration Curve.

    Accepts a set of standard spectra with known concentrations, fits a
    calibration model, and predicts the concentration of the unknown sample
    from Step 1.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        step1_tab,
        step4_tab,
        step5_tab,
        file_history=None,
        notes_panel=None,
    ):
        super().__init__()

        self.step1_tab    = step1_tab
        self.step4_tab    = step4_tab
        self.step5_tab    = step5_tab
        self.file_history = file_history
        self.notes_panel  = notes_panel

        # Computation state
        self.calibration_results: CalibrationResults | None = None
        self.worker_thread: WorkerThread | None = None

        # Per-element state cache
        self._element_states: dict[str, dict] = {}

        # Blank spectrum path
        self._blank_spectrum_path: str | None = None

        # Guard to prevent recursive element-change callbacks
        self._loading_element_state = False

        logger.info("Initialising Step 7 widget")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._create_left_panel(), stretch=0)
        main_layout.addWidget(self._create_right_panel(), stretch=1)

        # Restore previous session
        self._load_session()

    # ------------------------------------------------------------------
    # Panel builders
    # ------------------------------------------------------------------

    def _create_left_panel(self) -> QWidget:
        """Scrollable control panel (max width 390 px)."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ── Title ──────────────────────────────────────────────────────
        title = QLabel("Step 7: Quantitative Calibration")
        title.setStyleSheet(step_title_font(13))
        layout.addWidget(title)
        self._title_label = title

        # ── Status / result banner ─────────────────────────────────────
        self.summary_banner = QLabel("Add ≥ 3 standards and click Fit Calibration Curve.")
        self.summary_banner.setStyleSheet(summary_banner_style())
        self.summary_banner.setWordWrap(True)
        layout.addWidget(self.summary_banner)

        # ── Element selector ───────────────────────────────────────────
        elem_group = QGroupBox("Target Element")
        elem_layout = QVBoxLayout(elem_group)
        elem_layout.setSpacing(4)

        elem_row = QHBoxLayout()
        elem_row.addWidget(QLabel("Element:"))
        self.element_combo = QComboBox()
        self.element_combo.setToolTip("Select the element to calibrate")
        self.element_combo.currentTextChanged.connect(self._on_element_changed)
        elem_row.addWidget(self.element_combo, stretch=1)
        elem_layout.addLayout(elem_row)

        wl_row = QHBoxLayout()
        wl_row.addWidget(QLabel("Analytical λ (nm):"))
        self.wavelength_spin = QDoubleSpinBox()
        self.wavelength_spin.setRange(0.0, 1000.0)
        self.wavelength_spin.setSingleStep(0.01)
        self.wavelength_spin.setDecimals(2)
        self.wavelength_spin.setValue(0.0)
        self.wavelength_spin.setToolTip("Emission line wavelength in nm")
        wl_row.addWidget(self.wavelength_spin, stretch=1)
        elem_layout.addLayout(wl_row)

        tol_row = QHBoxLayout()
        tol_row.addWidget(QLabel("Tolerance (nm):"))
        self.tolerance_spin = QDoubleSpinBox()
        self.tolerance_spin.setRange(0.01, 5.0)
        self.tolerance_spin.setSingleStep(0.01)
        self.tolerance_spin.setDecimals(2)
        self.tolerance_spin.setValue(0.20)
        self.tolerance_spin.setToolTip("Half-window for intensity extraction in nm")
        tol_row.addWidget(self.tolerance_spin, stretch=1)
        elem_layout.addLayout(tol_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Fit model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["linear", "quadratic", "power_law"])
        self.model_combo.setToolTip(
            "linear: y=ax+b  |  quadratic: y=ax²+bx+c  |  power_law: y=a·xᵇ"
        )
        model_row.addWidget(self.model_combo, stretch=1)
        elem_layout.addLayout(model_row)

        layout.addWidget(elem_group)

        # ── Standards table ────────────────────────────────────────────
        std_group = QGroupBox("Calibration Standards")
        std_layout = QVBoxLayout(std_group)
        std_layout.setSpacing(4)

        # Table buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        add_btn = QPushButton("[+]")
        add_btn.setToolTip("Add a blank row")
        add_btn.setMaximumWidth(40)
        add_btn.clicked.connect(self._on_add_row)
        btn_row.addWidget(add_btn)

        remove_btn = QPushButton("[−]")
        remove_btn.setToolTip("Remove selected row")
        remove_btn.setMaximumWidth(40)
        remove_btn.clicked.connect(self._on_remove_row)
        btn_row.addWidget(remove_btn)

        load_csv_btn = QPushButton("Load CSV")
        load_csv_btn.setToolTip("Load standards from a CSV file")
        load_csv_btn.clicked.connect(self._on_load_standards_csv)
        btn_row.addWidget(load_csv_btn)

        save_csv_btn = QPushButton("Save CSV")
        save_csv_btn.setToolTip("Save standards table to a CSV file")
        save_csv_btn.clicked.connect(self._on_save_standards_csv)
        btn_row.addWidget(save_csv_btn)

        std_layout.addLayout(btn_row)

        # The table itself
        self.standards_table = QTableWidget()
        self.standards_table.setColumnCount(5)
        self.standards_table.setHorizontalHeaderLabels([
            "Sample ID", "Conc (ppm)", "Spectrum File", "Intensity", "Blank"
        ])
        hdr = self.standards_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.standards_table.setAlternatingRowColors(True)
        self.standards_table.setMinimumHeight(160)
        self.standards_table.setMaximumHeight(260)
        self.standards_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.standards_table.itemChanged.connect(self._on_table_item_changed)
        std_layout.addWidget(self.standards_table)

        # Skip baseline checkbox
        self.skip_baseline_checkbox = QCheckBox("Skip baseline correction for standards")
        self.skip_baseline_checkbox.setToolTip(
            "If checked, raw intensity is used instead of corrected intensity"
        )
        std_layout.addWidget(self.skip_baseline_checkbox)

        layout.addWidget(std_group)

        # ── Blank spectrum ─────────────────────────────────────────────
        blank_group = QGroupBox("Blank Spectrum (for LOD/LOQ)")
        blank_layout = QHBoxLayout(blank_group)
        blank_layout.setSpacing(6)

        load_blank_btn = QPushButton("Load Blank Spectrum")
        load_blank_btn.setToolTip("Load a blank/zero-concentration spectrum for LOD/LOQ calculation")
        load_blank_btn.clicked.connect(self._on_load_blank_clicked)
        blank_layout.addWidget(load_blank_btn)

        self.blank_label = QLabel("None")
        self.blank_label.setStyleSheet(f"color: {C_TEXT2}; font-size: 8pt;")
        self.blank_label.setWordWrap(True)
        blank_layout.addWidget(self.blank_label, stretch=1)

        layout.addWidget(blank_group)

        # ── Primary action button ──────────────────────────────────────
        self.fit_button = QPushButton("⚙  Fit Calibration Curve")
        self.fit_button.setStyleSheet(primary_button_style())
        self.fit_button.setEnabled(False)
        self.fit_button.setToolTip("Requires ≥ 3 standard rows with spectrum files")
        self.fit_button.clicked.connect(self._on_fit_clicked)
        layout.addWidget(self.fit_button)

        # ── Export buttons ─────────────────────────────────────────────
        export_row = QHBoxLayout()
        export_row.setSpacing(4)

        self.export_csv_button = QPushButton("Export CSV")
        self.export_csv_button.setEnabled(False)
        self.export_csv_button.clicked.connect(self._on_export_csv_clicked)
        export_row.addWidget(self.export_csv_button)

        self.export_png_button = QPushButton("Export PNG")
        self.export_png_button.setEnabled(False)
        self.export_png_button.clicked.connect(self._on_export_png_clicked)
        export_row.addWidget(self.export_png_button)

        self.export_pdf_button = QPushButton("Export PDF")
        self.export_pdf_button.setEnabled(False)
        self.export_pdf_button.clicked.connect(self._on_export_pdf_clicked)
        export_row.addWidget(self.export_pdf_button)

        layout.addLayout(export_row)

        # ── Info label ─────────────────────────────────────────────────
        self.info_label = QLabel(
            "Add ≥ 3 standards (Sample ID, concentration, spectrum file) "
            "then click Fit Calibration Curve."
        )
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet(instruction_banner_style())
        layout.addWidget(self.info_label)

        # ── Progress bar ───────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setStyleSheet(progress_bar_style())
        self.progress_bar.setMaximumHeight(6)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        layout.addStretch()

        # Wrap in scroll area
        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setMaximumWidth(390)
        return scroll

    def _create_right_panel(self) -> QWidget:
        """Right panel: three chart tabs + concentration result label."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        chart_bg = get_chart_bg()

        # ── Chart tab widget ───────────────────────────────────────────
        self.chart_tabs = QTabWidget()

        # Tab 1: Calibration Curve
        self.fig_curve = Figure(figsize=(7, 4), dpi=100)
        self.fig_curve.patch.set_facecolor(chart_bg)
        self.ax_curve = self.fig_curve.add_subplot(111)
        self.canvas_curve = FigureCanvasQTAgg(self.fig_curve)
        self.canvas_curve.setStyleSheet(f"background-color: {chart_bg};")
        self.toolbar_curve = NavigationToolbar2QT(self.canvas_curve)
        self.chart_tabs.addTab(
            self._wrap_canvas(self.canvas_curve, self.toolbar_curve),
            "Calibration Curve"
        )

        # Tab 2: Residuals
        self.fig_resid = Figure(figsize=(7, 4), dpi=100)
        self.fig_resid.patch.set_facecolor(chart_bg)
        self.ax_resid = self.fig_resid.add_subplot(111)
        self.canvas_resid = FigureCanvasQTAgg(self.fig_resid)
        self.canvas_resid.setStyleSheet(f"background-color: {chart_bg};")
        self.toolbar_resid = NavigationToolbar2QT(self.canvas_resid)
        self.chart_tabs.addTab(
            self._wrap_canvas(self.canvas_resid, self.toolbar_resid),
            "Residuals"
        )

        # Tab 3: LOD / LOQ
        self.fig_lod = Figure(figsize=(7, 4), dpi=100)
        self.fig_lod.patch.set_facecolor(chart_bg)
        self.ax_lod = self.fig_lod.add_subplot(111)
        self.canvas_lod = FigureCanvasQTAgg(self.fig_lod)
        self.canvas_lod.setStyleSheet(f"background-color: {chart_bg};")
        self.toolbar_lod = NavigationToolbar2QT(self.canvas_lod)
        self.chart_tabs.addTab(
            self._wrap_canvas(self.canvas_lod, self.toolbar_lod),
            "LOD / LOQ"
        )

        # ── Splitter with result label ─────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.chart_tabs)

        result_container = QWidget()
        result_layout = QVBoxLayout(result_container)
        result_layout.setContentsMargins(10, 6, 10, 6)
        self.result_label = QLabel("No calibration result yet.")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet(
            f"color: {C_TEXT}; font-size: 10pt; font-weight: 600;"
        )
        result_layout.addWidget(self.result_label)
        splitter.addWidget(result_container)
        splitter.setSizes([520, 80])

        layout.addWidget(splitter)
        return panel

    @staticmethod
    def _wrap_canvas(canvas: FigureCanvasQTAgg, toolbar: NavigationToolbar2QT) -> QWidget:
        """Wrap a canvas + toolbar into a container widget."""
        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(2)
        cl.addWidget(canvas)
        cl.addWidget(toolbar)
        return container

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """
        Re-read Step 4 element list and Step 5 analytical wavelength.
        Does NOT re-fit — preserves existing calibration results.
        """
        try:
            # Populate element combo from step4 analysis_results
            # The ranking key holds a DataFrame with an "Element" column
            analysis_results = getattr(self.step4_tab, "analysis_results", None)
            elements: list[str] = []
            if isinstance(analysis_results, dict):
                ranking_df = analysis_results.get("ranking")
                if ranking_df is None:
                    ranking_df = analysis_results.get("ranking_df")
                if ranking_df is not None and hasattr(ranking_df, "columns") and "Element" in ranking_df.columns and not ranking_df.empty:
                    elements = [str(v) for v in ranking_df["Element"].tolist() if v]

            current_text = self.element_combo.currentText()
            self.element_combo.blockSignals(True)
            self.element_combo.clear()
            if elements:
                self.element_combo.addItems(elements)
                # Restore previous selection if still present
                idx = self.element_combo.findText(current_text)
                if idx >= 0:
                    self.element_combo.setCurrentIndex(idx)
            self.element_combo.blockSignals(False)

            # Pre-populate analytical wavelength from step5
            target_wavelengths = getattr(self.step5_tab, "target_wavelengths", None)
            if target_wavelengths and len(target_wavelengths) > 0:
                try:
                    wl = float(target_wavelengths[0])
                    if 0.0 < wl <= 1000.0:
                        self.wavelength_spin.setValue(wl)
                except (TypeError, ValueError):
                    pass

        except Exception as exc:
            logger.warning("Step7Widget.refresh() failed: %s", exc)

    # ------------------------------------------------------------------
    # Element state management
    # ------------------------------------------------------------------

    def _flush_current_element_state(self) -> None:
        """Save current UI state into _element_states for the current element."""
        element = self.element_combo.currentText()
        if not element:
            return
        self._element_states[element] = {
            "points":     self._read_table_points(),
            "model":      self.model_combo.currentText(),
            "wavelength": self.wavelength_spin.value(),
            "tolerance":  self.tolerance_spin.value(),
            "results":    self.calibration_results,
            "blank_path": self._blank_spectrum_path,
        }

    def _on_element_changed(self, element: str) -> None:
        """Switch calibration state when the element combobox changes."""
        if self._loading_element_state or not element:
            return

        # First flush the outgoing element's state
        # (we need the *previous* element — find it from what's not `element`)
        prev = None
        for e in self._element_states:
            if e != element:
                prev = e  # most recently cached element that isn't the new one
        # Actually, just flush whatever current state is, keyed by prev combo value.
        # We do this by saving current table state under the element that was active
        # before the signal fired. The combo has already changed by the time we get
        # here, so we save under a temporary key then clean up.
        # Simpler: track previous element explicitly.
        if hasattr(self, "_current_element") and self._current_element and self._current_element != element:
            prev_element = self._current_element
            self._element_states[prev_element] = {
                "points":     self._read_table_points(),
                "model":      self.model_combo.currentText(),
                "wavelength": self.wavelength_spin.value(),
                "tolerance":  self.tolerance_spin.value(),
                "results":    self.calibration_results,
                "blank_path": self._blank_spectrum_path,
            }

        self._current_element = element

        # Load the new element's state if it exists
        self._loading_element_state = True
        try:
            if element in self._element_states:
                state = self._element_states[element]
                self._populate_table_from_points(state.get("points", []))
                model = state.get("model", "linear")
                idx = self.model_combo.findText(model)
                if idx >= 0:
                    self.model_combo.setCurrentIndex(idx)
                self.wavelength_spin.setValue(state.get("wavelength", 0.0))
                self.tolerance_spin.setValue(state.get("tolerance", 0.20))
                self.calibration_results = state.get("results")
                self._blank_spectrum_path = state.get("blank_path")
                bp = self._blank_spectrum_path
                self.blank_label.setText(Path(bp).name if bp else "None")
                if self.calibration_results is not None:
                    self._update_summary_banner(self.calibration_results)
                    self._update_chart_curve()
                    self._update_chart_residuals()
                    self._update_chart_lod_loq()
                    self._enable_exports(True)
            else:
                # Fresh element — clear the table and reset results
                self.standards_table.setRowCount(0)
                self.calibration_results = None
                self._blank_spectrum_path = None
                self.blank_label.setText("None")
                self.summary_banner.setText("Add ≥ 3 standards and click Fit Calibration Curve.")
                self._enable_exports(False)
        finally:
            self._loading_element_state = False

        self._update_fit_button_state()

    # ------------------------------------------------------------------
    # Standards table methods
    # ------------------------------------------------------------------

    def _on_add_row(self) -> None:
        """Append a blank editable row to the standards table."""
        self.standards_table.blockSignals(True)
        row = self.standards_table.rowCount()
        self.standards_table.insertRow(row)

        # Sample ID
        self.standards_table.setItem(row, _COL_SAMPLE_ID, QTableWidgetItem(f"Std-{row + 1}"))

        # Concentration
        conc_item = QTableWidgetItem("0.0")
        self.standards_table.setItem(row, _COL_CONC, conc_item)

        # Spectrum File (read-only via double-click)
        spec_item = QTableWidgetItem("")
        spec_item.setToolTip("Double-click to browse for a spectrum CSV file")
        self.standards_table.setItem(row, _COL_SPECTRUM, spec_item)

        # Intensity (read-only)
        intensity_item = QTableWidgetItem("")
        intensity_item.setFlags(intensity_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        intensity_item.setForeground(self.palette().color(self.foregroundRole()))
        self.standards_table.setItem(row, _COL_INTENSITY, intensity_item)

        # Is Blank checkbox
        chk = QCheckBox()
        chk.setChecked(False)
        chk_container = QWidget()
        chk_layout = QHBoxLayout(chk_container)
        chk_layout.addWidget(chk)
        chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chk_layout.setContentsMargins(0, 0, 0, 0)
        self.standards_table.setCellWidget(row, _COL_IS_BLANK, chk_container)

        self.standards_table.blockSignals(False)
        self._update_fit_button_state()

    def _on_remove_row(self) -> None:
        """Remove the currently selected row."""
        selected = self.standards_table.currentRow()
        if selected >= 0:
            self.standards_table.removeRow(selected)
            self._update_fit_button_state()

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        """Open a file picker when the Spectrum File cell is double-clicked."""
        if col == _COL_SPECTRUM:
            filepath, _ = QFileDialog.getOpenFileName(
                self, "Select Spectrum File", "",
                "CSV Files (*.csv);;All Files (*)"
            )
            if filepath:
                self.standards_table.blockSignals(True)
                item = self.standards_table.item(row, _COL_SPECTRUM)
                if item is None:
                    item = QTableWidgetItem()
                    self.standards_table.setItem(row, _COL_SPECTRUM, item)
                item.setText(filepath)
                item.setToolTip(filepath)
                self.standards_table.blockSignals(False)
                self._update_fit_button_state()

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        """Update fit button state whenever the table changes."""
        if not self._loading_element_state:
            self._update_fit_button_state()

    def _on_load_standards_csv(self) -> None:
        """Load a standards CSV file and populate the table."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Standards CSV", "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not filepath:
            return
        try:
            df = pd.read_csv(filepath)
            # Normalise column names
            df.columns = [c.strip().lower() for c in df.columns]

            self.standards_table.blockSignals(True)
            self.standards_table.setRowCount(0)

            col_map = {
                "sample_id":        "sample_id",
                "sample id":        "sample_id",
                "concentration":    "concentration",
                "conc":             "concentration",
                "concentration_ppm":"concentration",
                "conc (ppm)":       "concentration",
                "spectrum_file":    "spectrum_file",
                "spectrum file":    "spectrum_file",
                "file":             "spectrum_file",
                "is_blank":         "is_blank",
                "blank":            "is_blank",
            }
            cols = {col_map.get(c, c): c for c in df.columns}

            for _, dfrow in df.iterrows():
                row = self.standards_table.rowCount()
                self.standards_table.insertRow(row)

                sid = str(dfrow.get(cols.get("sample_id", ""), f"Std-{row + 1}"))
                self.standards_table.setItem(row, _COL_SAMPLE_ID, QTableWidgetItem(sid))

                try:
                    conc = float(dfrow.get(cols.get("concentration", ""), 0.0))
                except (TypeError, ValueError):
                    conc = 0.0
                self.standards_table.setItem(row, _COL_CONC, QTableWidgetItem(str(conc)))

                spec = str(dfrow.get(cols.get("spectrum_file", ""), ""))
                spec_item = QTableWidgetItem(spec)
                spec_item.setToolTip(spec)
                self.standards_table.setItem(row, _COL_SPECTRUM, spec_item)

                intensity_item = QTableWidgetItem("")
                intensity_item.setFlags(intensity_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.standards_table.setItem(row, _COL_INTENSITY, intensity_item)

                is_blank_raw = dfrow.get(cols.get("is_blank", ""), False)
                is_blank = bool(is_blank_raw) if not isinstance(is_blank_raw, str) else is_blank_raw.lower() in ("true", "1", "yes")
                chk = QCheckBox()
                chk.setChecked(is_blank)
                chk_container = QWidget()
                chk_layout = QHBoxLayout(chk_container)
                chk_layout.addWidget(chk)
                chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                chk_layout.setContentsMargins(0, 0, 0, 0)
                self.standards_table.setCellWidget(row, _COL_IS_BLANK, chk_container)

            self.standards_table.blockSignals(False)
            self._update_fit_button_state()
            show_info("Standards Loaded", f"Loaded {self.standards_table.rowCount()} standard rows.")
        except Exception as exc:
            logger.error("Failed to load standards CSV: %s", exc)
            show_error("Load Failed", f"Failed to load standards CSV:\n{exc}")

    def _on_save_standards_csv(self) -> None:
        """Save the standards table to a CSV file."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Standards CSV", "step7_standards.csv",
            "CSV Files (*.csv)"
        )
        if not filepath:
            return
        try:
            points = self._read_table_points()
            rows = []
            for pt in points:
                rows.append({
                    "Sample_ID":        pt["sample_id"],
                    "Concentration_ppm": pt["concentration"],
                    "Spectrum_File":    pt["spectrum_file"],
                    "Is_Blank":         pt["is_blank"],
                })
            pd.DataFrame(rows).to_csv(filepath, index=False)
            show_info("Saved", f"Standards table saved to:\n{filepath}")
        except Exception as exc:
            logger.error("Failed to save standards CSV: %s", exc)
            show_error("Save Failed", f"Failed to save standards CSV:\n{exc}")

    def _update_fit_button_state(self) -> None:
        """Enable the Fit button when at least 3 rows have a non-empty spectrum file."""
        count = 0
        for row in range(self.standards_table.rowCount()):
            spec_item = self.standards_table.item(row, _COL_SPECTRUM)
            if spec_item and spec_item.text().strip():
                count += 1
        self.fit_button.setEnabled(count >= 3)

    # ------------------------------------------------------------------
    # Blank spectrum
    # ------------------------------------------------------------------

    def _on_load_blank_clicked(self) -> None:
        """Open a file picker to select the blank spectrum."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Blank Spectrum", "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if filepath:
            self._blank_spectrum_path = filepath
            self.blank_label.setText(Path(filepath).name)
            self.blank_label.setToolTip(filepath)

    # ------------------------------------------------------------------
    # Fit logic
    # ------------------------------------------------------------------

    def _on_fit_clicked(self) -> None:
        """Build CalibrationPoint list, validate, and launch WorkerThread."""
        element = self.element_combo.currentText() or "Unknown"
        model = self.model_combo.currentText()

        # Warn about power_law with zero-concentration standards
        if model == "power_law":
            for row in range(self.standards_table.rowCount()):
                conc_item = self.standards_table.item(row, _COL_CONC)
                is_blank_widget = self.standards_table.cellWidget(row, _COL_IS_BLANK)
                is_blank = False
                if is_blank_widget:
                    chk = is_blank_widget.findChild(QCheckBox)
                    if chk:
                        is_blank = chk.isChecked()
                if not is_blank and conc_item:
                    try:
                        c = float(conc_item.text())
                        if c <= 0:
                            show_error(
                                "Power-Law Warning",
                                "Power-law model requires all concentrations > 0.\n"
                                "Mark zero-concentration standards as 'Blank' instead."
                            )
                            return
                    except ValueError:
                        pass

        points = self._read_table_points()

        # Identify blank point
        blank_point: CalibrationPoint | None = None
        if self._blank_spectrum_path:
            blank_point = CalibrationPoint(
                sample_id="blank",
                concentration=0.0,
                spectrum_file=self._blank_spectrum_path,
                intensity=None,
                is_blank=True,
            )

        wavelength   = self.wavelength_spin.value()
        tolerance    = self.tolerance_spin.value()
        unknown_data = getattr(self.step1_tab, "processed_data", None)

        # Show progress, disable buttons
        self.progress_bar.show()
        self.fit_button.setEnabled(False)
        self._enable_exports(False)
        self.summary_banner.setText("Fitting calibration curve…")
        self.info_label.setText("Running — please wait.")

        def _worker():
            engine = CalibrationEngine()
            return engine.fit_and_predict(
                points=points,
                model_name=model,
                element=element,
                analytical_wavelength=wavelength,
                extraction_tolerance=tolerance,
                unknown_processed_data=unknown_data,
                blank_point=blank_point,
            )

        self.worker_thread = WorkerThread(_worker)
        self.worker_thread.finished.connect(self._on_fit_finished)
        self.worker_thread.error.connect(self._on_worker_error)
        self.worker_thread.start()

    def _on_fit_finished(self, _signal_dict: dict = None) -> None:
        """Handle completed calibration fit."""
        self.progress_bar.hide()
        self.fit_button.setEnabled(True)

        if self.worker_thread is None:
            return

        results: CalibrationResults = self.worker_thread.result
        if results is None:
            self.summary_banner.setText("Fit returned no results.")
            self.info_label.setText("No results available.")
            return

        self.calibration_results = results

        # Write back extracted intensities into table
        self._write_intensities_to_table(results)

        # Update UI
        self._update_summary_banner(results)
        self._update_chart_curve()
        self._update_chart_residuals()
        self._update_chart_lod_loq()

        # Enable exports if fit succeeded
        fit_ok = (results.get("fit_result") or {}).get("fit_ok", False)
        self._enable_exports(fit_ok)

        # Update result label
        conc = results.get("unknown_concentration")
        unc  = results.get("unknown_uncertainty")
        if conc is not None and unc is not None:
            self.result_label.setText(
                f"Concentration: {conc:.4f} ± {unc:.4f} ppm (95 % CI)"
            )
        elif conc is not None:
            self.result_label.setText(f"Concentration: {conc:.4f} ppm")
        else:
            missing = results.get("missing_info", [])
            self.result_label.setText(
                "; ".join(missing) if missing else "Concentration: N/A"
            )

        # Persist session
        self._save_session()

        self.info_label.setText("Calibration fit complete.")
        logger.info("Step 7 fit finished for element: %s", results.get("element"))

    def _on_worker_error(self, error_message: str) -> None:
        """Handle worker thread error."""
        self.progress_bar.hide()
        self.fit_button.setEnabled(True)
        self.summary_banner.setText(f"Error: {error_message}")
        self.info_label.setText(f"Fit failed: {error_message}")
        logger.error("Step 7 worker error: %s", error_message)
        show_error("Step 7 Error", f"Calibration fit failed:\n{error_message}")

    def _write_intensities_to_table(self, results: CalibrationResults) -> None:
        """Write back extracted intensities from results into the Intensity column."""
        points = results.get("points", [])
        # Match by sample_id + spectrum_file
        self.standards_table.blockSignals(True)
        for pt in points:
            sid = pt.get("sample_id", "")
            intensity = pt.get("intensity")
            for row in range(self.standards_table.rowCount()):
                sid_item = self.standards_table.item(row, _COL_SAMPLE_ID)
                if sid_item and sid_item.text() == sid:
                    intensity_item = self.standards_table.item(row, _COL_INTENSITY)
                    if intensity_item is None:
                        intensity_item = QTableWidgetItem()
                        intensity_item.setFlags(intensity_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.standards_table.setItem(row, _COL_INTENSITY, intensity_item)
                    intensity_item.setText(f"{intensity:.2f}" if intensity is not None else "N/A")
                    break
        self.standards_table.blockSignals(False)

    # ------------------------------------------------------------------
    # Summary banner
    # ------------------------------------------------------------------

    def _update_summary_banner(self, results: CalibrationResults) -> None:
        """Format and display the calibration summary in the status banner."""
        missing = results.get("missing_info", [])
        if any("Minimum 3 standards" in m for m in missing):
            self.summary_banner.setText("Minimum 3 standards required.")
            return

        element  = results.get("element", "?")
        wl       = results.get("analytical_wavelength", 0.0)
        fit_r    = results.get("fit_result")
        conc     = results.get("unknown_concentration")
        unc      = results.get("unknown_uncertainty")
        in_range = results.get("in_range", False)

        if fit_r and fit_r.get("fit_ok"):
            model = fit_r.get("model", "?")
            r2    = fit_r.get("r_squared", 0.0)
            rmse  = fit_r.get("rmse", 0.0)
            if conc is not None and unc is not None:
                conc_str = f"Concentration: {conc:.4f} ± {unc:.4f} ppm (95 % CI)"
            elif conc is not None:
                conc_str = f"Concentration: {conc:.4f} ppm"
            else:
                conc_str = "Concentration: N/A  " + ("; ".join(missing) if missing else "")

            text = (
                f"Element: {element}  λ = {wl:.2f} nm\n"
                f"Model: {model}  R² = {r2:.4f}  RMSE = {rmse:.4f}\n"
                f"{conc_str}"
            )
            if not in_range and conc is not None:
                text += f"\n⚠ Extrapolation warning"
        else:
            err = (fit_r or {}).get("error_message", "")
            text = f"Fit failed for {element}."
            if err:
                text += f"\n{err}"
            if missing:
                text += "\n" + "; ".join(missing)

        self.summary_banner.setText(text)

    # ------------------------------------------------------------------
    # Chart update helpers
    # ------------------------------------------------------------------

    def _update_chart_curve(self) -> None:
        """Render the Calibration Curve chart."""
        self.ax_curve.clear()
        results = self.calibration_results

        if results is None:
            ChartEngine._show_placeholder(self.ax_curve, "No calibration data")
            ChartEngine.apply_dark_style(self.fig_curve, self.ax_curve)
            self.canvas_curve.draw()
            return

        ChartEngine.render_calibration_curve(
            ax=self.ax_curve,
            points=results.get("points", []),
            fit_result=results.get("fit_result"),
            unknown_intensity=results.get("unknown_intensity"),
            unknown_concentration=results.get("unknown_concentration"),
            in_range=results.get("in_range", False),
            element_name=results.get("element", ""),
        )
        self.canvas_curve.draw()
        self.toolbar_curve.home()

    def _update_chart_residuals(self) -> None:
        """Render the Residuals chart."""
        self.ax_resid.clear()
        results = self.calibration_results

        if results is None:
            ChartEngine._show_placeholder(self.ax_resid, "No calibration data")
            ChartEngine.apply_dark_style(self.fig_resid, self.ax_resid)
            self.canvas_resid.draw()
            return

        ChartEngine.render_calibration_residuals(
            ax=self.ax_resid,
            points=results.get("points", []),
            fit_result=results.get("fit_result"),
        )
        self.canvas_resid.draw()
        self.toolbar_resid.home()

    def _update_chart_lod_loq(self) -> None:
        """Render the LOD/LOQ panel chart."""
        self.ax_lod.clear()
        results = self.calibration_results

        if results is None:
            ChartEngine._show_placeholder(self.ax_lod, "Fit curve first to see LOD/LOQ")
            ChartEngine.apply_dark_style(self.fig_lod, self.ax_lod)
            self.canvas_lod.draw()
            return

        ChartEngine.render_lod_loq_panel(
            ax=self.ax_lod,
            points=results.get("points", []),
            fit_result=results.get("fit_result"),
            lod_ppm=results.get("lod_ppm"),
            loq_ppm=results.get("loq_ppm"),
            blank_noise=results.get("blank_noise"),
        )
        self.canvas_lod.draw()
        self.toolbar_lod.home()

    # ------------------------------------------------------------------
    # Export handlers
    # ------------------------------------------------------------------

    def _on_export_csv_clicked(self) -> None:
        """Export calibration results as CSV."""
        if self.calibration_results is None:
            show_error("Export Error", "No results to export. Run Fit first.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "step7_calibration.csv",
            "CSV Files (*.csv)"
        )
        if not filepath:
            return
        try:
            export_step7_csv(self.calibration_results, Path(filepath))
            show_info("Export Successful", f"CSV saved to:\n{filepath}")
        except Exception as exc:
            logger.error("Step 7 CSV export failed: %s", exc)
            show_error("Export Failed", f"Failed to export CSV:\n{exc}")

    def _on_export_png_clicked(self) -> None:
        """Export all three calibration charts as PNG files."""
        if self.calibration_results is None:
            show_error("Export Error", "No results to export. Run Fit first.")
            return

        directory = QFileDialog.getExistingDirectory(
            self, "Select Directory for PNG Export", ""
        )
        if not directory:
            return
        try:
            paths = export_step7_png(
                self.fig_curve, self.fig_resid, self.fig_lod,
                Path(directory)
            )
            show_info("Export Successful", "PNG files saved:\n" + "\n".join(str(p) for p in paths))
        except Exception as exc:
            logger.error("Step 7 PNG export failed: %s", exc)
            show_error("Export Failed", f"Failed to export PNG:\n{exc}")

    def _on_export_pdf_clicked(self) -> None:
        """Export a PDF report including the Step 7 calibration section."""
        if self.calibration_results is None:
            show_error("Export Error", "No results to export. Run Fit first.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Report", "LIBS_Calibration_Report.pdf",
            "PDF Files (*.pdf)"
        )
        if not filepath:
            return

        # Build minimal params for generate_pdf_report
        validation_results_df = getattr(self.step5_tab, "validation_results", None)
        if validation_results_df is None:
            import pandas as _pd
            validation_results_df = _pd.DataFrame()

        target_wavelengths = getattr(self.step5_tab, "target_wavelengths", []) or []
        vc_fig = getattr(self.step5_tab, "vc_fig", None)
        if vc_fig is None:
            vc_fig = Figure(figsize=(6, 3), dpi=100)

        try:
            generate_pdf_report(
                validation_results_df=validation_results_df,
                params={},
                vc_fig=vc_fig,
                processed_filename="(Step 7 export)",
                reference_filename="",
                target_wavelengths=target_wavelengths,
                filepath=Path(filepath),
                step7_results=self.calibration_results,
            )
            show_info("Export Successful", f"PDF report saved to:\n{filepath}")
        except ImportError:
            show_error(
                "Missing Dependency",
                "reportlab is not installed.\nRun: pip install reportlab",
            )
        except Exception as exc:
            logger.error("Step 7 PDF export failed: %s", exc)
            show_error("Export Failed", f"Failed to generate PDF:\n{exc}")

    # ------------------------------------------------------------------
    # apply_theme()
    # ------------------------------------------------------------------

    def apply_theme(self) -> None:
        """Refresh all chart canvas backgrounds for the active theme."""
        chart_bg = get_chart_bg()
        for fig, canvas in [
            (self.fig_curve, self.canvas_curve),
            (self.fig_resid, self.canvas_resid),
            (self.fig_lod,   self.canvas_lod),
        ]:
            fig.patch.set_facecolor(chart_bg)
            canvas.setStyleSheet(f"background-color: {chart_bg};")
            canvas.draw()

        # Refresh inline styles
        self._title_label.setStyleSheet(step_title_font(13))
        self.summary_banner.setStyleSheet(summary_banner_style())
        self.summary_banner.setStyleSheet(summary_banner_style())
        self.info_label.setStyleSheet(instruction_banner_style())
        self.progress_bar.setStyleSheet(progress_bar_style())
        self.fit_button.setStyleSheet(primary_button_style())

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    def _save_session(self) -> None:
        """Write per-element standards CSV and results JSON to .session/."""
        element = (self.calibration_results or {}).get("element", "")
        if not element:
            return
        try:
            session_dir = Path(".session")
            session_dir.mkdir(exist_ok=True)

            # Save standards
            points = (self.calibration_results or {}).get("points", [])
            rows = [
                {
                    "Sample_ID":        pt.get("sample_id", ""),
                    "Concentration_ppm": pt.get("concentration", 0.0),
                    "Spectrum_File":    pt.get("spectrum_file", ""),
                    "Is_Blank":         pt.get("is_blank", False),
                }
                for pt in points
            ]
            pd.DataFrame(rows).to_csv(
                session_dir / f"step7_standards_{element}.csv", index=False
            )

            # Save results JSON
            if self.calibration_results is not None:
                json_str = CalibrationEngine.results_to_json(self.calibration_results)
                (session_dir / f"step7_results_{element}.json").write_text(
                    json_str, encoding="utf-8"
                )
        except Exception as exc:
            logger.warning("Step 7 session save failed: %s", exc)

    def _load_session(self) -> None:
        """Restore per-element states from .session/ on startup."""
        try:
            session_dir = Path(".session")
            if not session_dir.exists():
                return

            # Find all step7_results_*.json files
            for results_path in sorted(session_dir.glob("step7_results_*.json")):
                try:
                    element = results_path.stem.replace("step7_results_", "")
                    json_str = results_path.read_text(encoding="utf-8")
                    results = CalibrationEngine.results_from_json(json_str)
                    if results is None:
                        continue

                    # Load standards CSV if it exists
                    std_path = session_dir / f"step7_standards_{element}.csv"
                    points: list[CalibrationPoint] = results.get("points", [])
                    if std_path.exists():
                        try:
                            df = pd.read_csv(str(std_path))
                            df.columns = [c.strip().lower() for c in df.columns]
                            points = []
                            for _, row in df.iterrows():
                                try:
                                    conc = float(row.get("concentration_ppm", 0.0))
                                except (TypeError, ValueError):
                                    conc = 0.0
                                is_blank_raw = row.get("is_blank", False)
                                is_blank = (
                                    bool(is_blank_raw)
                                    if not isinstance(is_blank_raw, str)
                                    else is_blank_raw.lower() in ("true", "1", "yes")
                                )
                                points.append(CalibrationPoint(
                                    sample_id=str(row.get("sample_id", "")),
                                    concentration=conc,
                                    spectrum_file=str(row.get("spectrum_file", "")),
                                    intensity=None,
                                    is_blank=is_blank,
                                ))
                        except Exception as exc:
                            logger.debug("Could not reload standards for %s: %s", element, exc)

                    self._element_states[element] = {
                        "points":     points,
                        "model":      (results.get("fit_result") or {}).get("model", "linear"),
                        "wavelength": results.get("analytical_wavelength", 0.0),
                        "tolerance":  results.get("extraction_tolerance", 0.20),
                        "results":    results,
                        "blank_path": None,
                    }
                    logger.info("Session restored for Step 7 element: %s", element)
                except Exception as exc:
                    logger.debug("Failed to restore step7 session for %s: %s", results_path, exc)
        except Exception as exc:
            logger.warning("Step 7 session load failed: %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_table_points(self) -> list[CalibrationPoint]:
        """Read all rows from the standards table and return as CalibrationPoint list."""
        points: list[CalibrationPoint] = []
        for row in range(self.standards_table.rowCount()):
            sid_item   = self.standards_table.item(row, _COL_SAMPLE_ID)
            conc_item  = self.standards_table.item(row, _COL_CONC)
            spec_item  = self.standards_table.item(row, _COL_SPECTRUM)
            chk_widget = self.standards_table.cellWidget(row, _COL_IS_BLANK)

            sid  = sid_item.text() if sid_item else f"Std-{row + 1}"
            spec = spec_item.text().strip() if spec_item else ""

            try:
                conc = float(conc_item.text()) if conc_item else 0.0
            except ValueError:
                conc = 0.0

            is_blank = False
            if chk_widget:
                chk = chk_widget.findChild(QCheckBox)
                if chk:
                    is_blank = chk.isChecked()

            points.append(CalibrationPoint(
                sample_id=sid,
                concentration=conc,
                spectrum_file=spec,
                intensity=None,
                is_blank=is_blank,
            ))
        return points

    def _populate_table_from_points(self, points: list[CalibrationPoint]) -> None:
        """Clear the standards table and populate it from a list of CalibrationPoints."""
        self.standards_table.blockSignals(True)
        self.standards_table.setRowCount(0)
        for pt in points:
            row = self.standards_table.rowCount()
            self.standards_table.insertRow(row)

            self.standards_table.setItem(row, _COL_SAMPLE_ID, QTableWidgetItem(str(pt.get("sample_id", ""))))

            conc_val = pt.get("concentration", 0.0)
            self.standards_table.setItem(row, _COL_CONC, QTableWidgetItem(str(conc_val)))

            spec_path = str(pt.get("spectrum_file", ""))
            spec_item = QTableWidgetItem(spec_path)
            spec_item.setToolTip(spec_path)
            self.standards_table.setItem(row, _COL_SPECTRUM, spec_item)

            intensity_val = pt.get("intensity")
            intensity_item = QTableWidgetItem(
                f"{intensity_val:.2f}" if intensity_val is not None else ""
            )
            intensity_item.setFlags(intensity_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.standards_table.setItem(row, _COL_INTENSITY, intensity_item)

            chk = QCheckBox()
            chk.setChecked(bool(pt.get("is_blank", False)))
            chk_container = QWidget()
            chk_layout = QHBoxLayout(chk_container)
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            self.standards_table.setCellWidget(row, _COL_IS_BLANK, chk_container)

        self.standards_table.blockSignals(False)

    def _enable_exports(self, enabled: bool) -> None:
        """Enable or disable all three export buttons."""
        self.export_csv_button.setEnabled(enabled)
        self.export_png_button.setEnabled(enabled)
        self.export_pdf_button.setEnabled(enabled)
