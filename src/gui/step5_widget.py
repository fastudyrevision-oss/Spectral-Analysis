# -*- coding: utf-8 -*-
"""
Step 5 Widget - Validation with Reference Spectra

Two-column layout: scrollable controls on the left, chart + table on the right.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QDoubleSpinBox,
    QFileDialog, QSpinBox, QSplitter, QProgressBar, QScrollArea, QTabWidget,
    QCheckBox, QFrame,
)
from PyQt6.QtGui import QFont, QColor

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from src import setup_logger
from src.config import STEP5_PARAMS
from src.core.step5_validation import ValidationAnalyzer
from src.io.file_reader import CSVReader
from src.gui.gui_utils import (
    HighDpiToolbar as NavigationToolbar2QT,
    FileSelector, WorkerThread, FileHistory, RecentFilesButton,
    show_error, show_info
)
from src.gui.charts import ChartEngine
from src.gui.export_engine import export_step5_csv, export_step5_png, generate_pdf_report
from src.gui.theme import (
    primary_button_style, instruction_banner_style, step_title_font,
    summary_banner_style, mean_vc_label_style, progress_bar_style,
    get_chart_bg,
    C_TEXT_MUTED, C_ACCENT2,
)

logger = setup_logger(__name__)


class Step5Widget(QWidget):
    """
    UI widget for Step 5: Validation with Reference Spectra.

    Layout mirrors Step 1/2:
    - Left  (fixed ≤370 px, scrollable): title, instructions, file selectors,
      parameters, wavelength controls, action buttons, info label.
    - Right (stretch): vertical splitter → VC histogram chart (top) +
      results table (bottom).
    """

    def __init__(self, file_history=None, notes_panel=None):
        super().__init__()
        self.processed_spectrum = None
        self.reference_spectrum = None
        self.validation_results = None
        self.line_overlays = []      # list of dicts from validate_line (with wl arrays)
        self.analyzer = None
        self.worker_thread = None
        self.file_history = file_history
        self.notes_panel = notes_panel
        self.target_wavelengths = []
        # Overlay pagination state
        self._overlay_page = 0
        self._overlay_page_size = 4   # 2×2 grid — larger, more readable charts

        # Role-scoped recent-file histories
        self._processed_history = FileHistory(role="step5_processed")
        self._reference_history = FileHistory(role="step5_reference")
        self._wavelengths_history = FileHistory(role="step5_wavelengths")

        # Stored file paths (replaces FileSelector)
        self._processed_path: Path | None = None
        self._reference_path: Path | None = None

        logger.info("Initializing Step 5 widget")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._create_left_panel(), stretch=0)
        main_layout.addWidget(self._create_right_panel(), stretch=1)

    # ──────────────────────────────────────────────────────────────────────
    # Panel builders
    # ──────────────────────────────────────────────────────────────────────

    def _create_left_panel(self) -> QWidget:
        """Scrollable control panel (fixed width)."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        title = QLabel("Step 5: Validation with Reference Spectra")
        tf = QFont(); tf.setBold(True); tf.setPointSize(12)
        title.setFont(tf)
        title.setStyleSheet(step_title_font(13))
        layout.addWidget(title)
        self._title_label = title

        self.summary_banner = QLabel("Run validation to see summary")
        self.summary_banner.setStyleSheet(summary_banner_style())
        self.summary_banner.setWordWrap(True)
        layout.addWidget(self.summary_banner)

        self.mean_vc_label = QLabel("—")
        layout.addWidget(self.mean_vc_label)

        instructions = QLabel(
            "📋 Instructions:\n"
            "1. 'Processed Spectrum': load the baseline-corrected CSV from Step 1.\n"
            "2. 'Reference Spectrum': load a pure-element reference CSV.\n"
            "3. Specify target wavelengths (emission lines to validate):\n"
            "   • 'Load from File': CSV (1st column) or plain text (one per line).\n"
            "   • 'Enter Manually': type wavelengths directly.\n"
            "4. Adjust parameters if needed:\n"
            "   • Window (nm): spectral region ± window around each target line.\n"
            "   • Min Points: minimum data points required per region.\n"
            "   • VC Threshold: coefficient ≥ this value is rated 'Good'.\n"
            "5. Click 'Validate Spectrum' to compute Pearson correlation at each line.\n"
            "6. Use export buttons to save results as CSV, PNG, or PDF."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(instruction_banner_style())
        layout.addWidget(instructions)
        self._instructions_label = instructions

        files_group = QGroupBox("Input Spectra")
        fl = QVBoxLayout()
        fl.setContentsMargins(6, 8, 6, 8)
        fl.setSpacing(8)

        # ── Processed Spectrum ────────────────────────────────────────────
        proc_lbl = QLabel("Processed Spectrum (Step 1 output):")
        proc_lbl.setStyleSheet("font-size: 9pt; font-weight: 600;")
        fl.addWidget(proc_lbl)

        proc_path_row = QHBoxLayout()
        proc_path_row.setSpacing(4)
        self._proc_path_label = QLabel("(No file selected)")
        self._proc_path_label.setStyleSheet(
            f"font-size: 9pt; font-style: italic; color: {C_TEXT_MUTED}; "
            f"border: 1px solid #3A4055; border-radius: 4px; padding: 3px 6px;")
        self._proc_path_label.setWordWrap(False)
        proc_path_row.addWidget(self._proc_path_label, stretch=1)
        proc_browse_btn = QPushButton("Browse…")
        proc_browse_btn.setFixedWidth(70)
        proc_browse_btn.setFixedHeight(26)
        proc_browse_btn.clicked.connect(self._on_browse_processed)
        proc_path_row.addWidget(proc_browse_btn)
        fl.addLayout(proc_path_row)

        proc_recent_row = QHBoxLayout()
        proc_recent_row.setSpacing(4)
        self._proc_recent_btn = RecentFilesButton(self._processed_history)
        self._proc_recent_btn.file_selected.connect(self._on_recent_processed)
        proc_recent_row.addWidget(self._proc_recent_btn)
        proc_recent_row.addStretch()
        fl.addLayout(proc_recent_row)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #3A4055;")
        fl.addWidget(divider)

        # ── Reference Spectrum ────────────────────────────────────────────
        ref_lbl = QLabel("Reference Spectrum (pure-element CSV):")
        ref_lbl.setStyleSheet("font-size: 9pt; font-weight: 600;")
        fl.addWidget(ref_lbl)

        ref_path_row = QHBoxLayout()
        ref_path_row.setSpacing(4)
        self._ref_path_label = QLabel("(No file selected)")
        self._ref_path_label.setStyleSheet(
            f"font-size: 9pt; font-style: italic; color: {C_TEXT_MUTED}; "
            f"border: 1px solid #3A4055; border-radius: 4px; padding: 3px 6px;")
        self._ref_path_label.setWordWrap(False)
        ref_path_row.addWidget(self._ref_path_label, stretch=1)
        ref_browse_btn = QPushButton("Browse…")
        ref_browse_btn.setFixedWidth(70)
        ref_browse_btn.setFixedHeight(26)
        ref_browse_btn.clicked.connect(self._on_browse_reference)
        ref_path_row.addWidget(ref_browse_btn)
        fl.addLayout(ref_path_row)

        ref_recent_row = QHBoxLayout()
        ref_recent_row.setSpacing(4)
        self._ref_recent_btn = RecentFilesButton(self._reference_history)
        self._ref_recent_btn.file_selected.connect(self._on_recent_reference)
        ref_recent_row.addWidget(self._ref_recent_btn)
        ref_recent_row.addStretch()
        fl.addLayout(ref_recent_row)

        files_group.setLayout(fl)
        layout.addWidget(files_group)

        params_group = QGroupBox("Parameters")
        pl = QHBoxLayout()

        wl = QVBoxLayout()
        wl.addWidget(QLabel("Window (nm):"))
        self.window_spinbox = QDoubleSpinBox()
        self.window_spinbox.setRange(0.01, 10.0)
        self.window_spinbox.setValue(STEP5_PARAMS['WINDOW'])
        self.window_spinbox.setSingleStep(0.1)
        self.window_spinbox.setDecimals(2)
        wl.addWidget(self.window_spinbox)
        pl.addLayout(wl)

        ptl = QVBoxLayout()
        ptl.addWidget(QLabel("Min Points:"))
        self.min_points_spinbox = QSpinBox()
        self.min_points_spinbox.setRange(2, 100)
        self.min_points_spinbox.setValue(STEP5_PARAMS['MIN_POINTS'])
        ptl.addWidget(self.min_points_spinbox)
        pl.addLayout(ptl)

        thl = QVBoxLayout()
        thl.addWidget(QLabel("VC Threshold:"))
        self.threshold_spinbox = QDoubleSpinBox()
        self.threshold_spinbox.setRange(0.0, 1.0)
        self.threshold_spinbox.setValue(STEP5_PARAMS['VC_THRESHOLD'])
        self.threshold_spinbox.setSingleStep(0.1)
        self.threshold_spinbox.setDecimals(2)
        thl.addWidget(self.threshold_spinbox)
        pl.addLayout(thl)

        params_group.setLayout(pl)
        layout.addWidget(params_group)

        lines_group = QGroupBox("Target Wavelengths (nm)")
        ll = QVBoxLayout()
        ll.setContentsMargins(6, 8, 6, 8)
        ll.setSpacing(4)

        # Status label — shows count of loaded wavelengths
        self.wavelengths_label = QLabel("No wavelengths specified")
        self.wavelengths_label.setWordWrap(True)
        ll.addWidget(self.wavelengths_label)

        # Path label — shows the last loaded wavelengths file
        self._wl_path_label = QLabel("(No file loaded)")
        self._wl_path_label.setStyleSheet(
            f"font-size: 9pt; font-style: italic; color: {C_TEXT_MUTED}; "
            f"border: 1px solid #3A4055; border-radius: 4px; padding: 3px 6px;")
        self._wl_path_label.setWordWrap(False)
        ll.addWidget(self._wl_path_label)

        # Browse + Recent row
        wl_file_row = QHBoxLayout()
        wl_file_row.setSpacing(4)
        self.load_lines_button = QPushButton("Load from File…")
        self.load_lines_button.clicked.connect(self._on_load_wavelengths)
        wl_file_row.addWidget(self.load_lines_button)
        self._wl_recent_btn = RecentFilesButton(self._wavelengths_history)
        self._wl_recent_btn.file_selected.connect(self._on_recent_wavelengths)
        wl_file_row.addWidget(self._wl_recent_btn)
        ll.addLayout(wl_file_row)

        # Manual entry on its own row
        self.manual_lines_button = QPushButton("Enter Manually…")
        self.manual_lines_button.clicked.connect(self._on_manual_wavelengths)
        ll.addWidget(self.manual_lines_button)

        lines_group.setLayout(ll)
        layout.addWidget(lines_group)

        btn_row = QHBoxLayout()
        self.validate_button = QPushButton("✔  Validate Spectrum")
        self.validate_button.setStyleSheet(primary_button_style())
        self.validate_button.clicked.connect(self._on_validate_clicked)
        btn_row.addWidget(self.validate_button)
        self.save_button = QPushButton("Save Report")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save_clicked)
        btn_row.addWidget(self.save_button)
        layout.addLayout(btn_row)

        export_row = QHBoxLayout()
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

        self.info_label = QLabel("Ready to validate spectrum")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setStyleSheet(progress_bar_style())
        self.progress_bar.setMaximumHeight(6)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        layout.addStretch()
        panel.setMaximumWidth(350)

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setMaximumWidth(370)
        return scroll

    def _create_right_panel(self) -> QWidget:
        """Right panel: tab widget (histogram | overlay | results table)."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Chart tabs ─────────────────────────────────────────────────────
        self.chart_tabs = QTabWidget()

        # Tab 1: VC Histogram
        chart_bg = get_chart_bg()
        self.vc_fig = Figure(figsize=(8, 3), dpi=100)
        self.vc_fig.patch.set_facecolor(chart_bg)
        self.vc_canvas = FigureCanvasQTAgg(self.vc_fig)
        self.vc_canvas.setStyleSheet(f"background-color: {chart_bg};")
        self.vc_toolbar = NavigationToolbar2QT(self.vc_canvas)

        hist_container = QWidget()
        hcl = QVBoxLayout(hist_container)
        hcl.setContentsMargins(0, 0, 0, 0); hcl.setSpacing(2)
        hcl.addWidget(self.vc_canvas)
        hcl.addWidget(self.vc_toolbar)
        self.chart_tabs.addTab(hist_container, "VC Histogram")

        # Tab 2: Spectral Overlays with filter + pagination toolbar
        overlay_tab = QWidget()
        otl = QVBoxLayout(overlay_tab)
        otl.setContentsMargins(4, 4, 4, 2)
        otl.setSpacing(4)

        # ── Filter row ─────────────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)
        filter_lbl = QLabel("Show:")
        filter_lbl.setStyleSheet("color: #AEB7C4; font-size: 9pt;")
        filter_row.addWidget(filter_lbl)

        from src.gui.theme import C_SUCCESS, C_ACCENT, C_WARN, C_ERROR
        tier_defs = [
            ("Excellent", C_SUCCESS),
            ("Good",      C_ACCENT),
            ("Moderate",  C_WARN),
            ("Weak",      C_ERROR),
            ("Failed",    "#6B7589"),
        ]
        self._tier_checkboxes: dict[str, QCheckBox] = {}
        for tier_name, tier_colour in tier_defs:
            cb = QCheckBox(tier_name)
            cb.setChecked(True)
            cb.setStyleSheet(
                f"QCheckBox {{ color: {tier_colour}; font-size: 9pt; font-weight: 600; }}"
                f"QCheckBox::indicator {{ width: 13px; height: 13px; }}"
            )
            cb.toggled.connect(self._on_overlay_filter_changed)
            filter_row.addWidget(cb)
            self._tier_checkboxes[tier_name] = cb

        filter_row.addStretch()
        otl.addLayout(filter_row)

        # ── Pagination row ─────────────────────────────────────────────────
        page_row = QHBoxLayout()
        page_row.setSpacing(6)
        self._overlay_prev_btn = QPushButton("◀ Prev")
        self._overlay_prev_btn.setMaximumWidth(70)
        self._overlay_prev_btn.clicked.connect(self._on_overlay_prev)
        page_row.addWidget(self._overlay_prev_btn)

        self._overlay_page_label = QLabel("Page — / —")
        self._overlay_page_label.setStyleSheet("color: #AEB7C4; font-size: 9pt;")
        self._overlay_page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_row.addWidget(self._overlay_page_label)

        self._overlay_next_btn = QPushButton("Next ▶")
        self._overlay_next_btn.setMaximumWidth(70)
        self._overlay_next_btn.clicked.connect(self._on_overlay_next)
        page_row.addWidget(self._overlay_next_btn)

        page_row.addStretch()
        self._overlay_count_label = QLabel("")
        self._overlay_count_label.setStyleSheet("color: #6B7589; font-size: 8pt;")
        page_row.addWidget(self._overlay_count_label)
        otl.addLayout(page_row)

        # ── Canvas + toolbar ───────────────────────────────────────────────
        self.overlay_fig = Figure(figsize=(8, 6), dpi=100)
        self.overlay_fig.patch.set_facecolor(chart_bg)
        self.overlay_canvas = FigureCanvasQTAgg(self.overlay_fig)
        self.overlay_canvas.setStyleSheet(f"background-color: {chart_bg};")
        self.overlay_toolbar = NavigationToolbar2QT(self.overlay_canvas)
        otl.addWidget(self.overlay_canvas, stretch=1)
        otl.addWidget(self.overlay_toolbar)

        self.chart_tabs.addTab(overlay_tab, "Spectral Overlays")

        # Tab 3: Results table
        self.results_table = self._create_results_table()
        self.chart_tabs.addTab(self.results_table, "📋 Results Table")

        layout.addWidget(self.chart_tabs)
        return panel

    def _create_results_table(self) -> QTableWidget:
        t = QTableWidget()
        t.setColumnCount(4)
        t.setHorizontalHeaderLabels(
            ["Wavelength (nm)", "Validation Coefficient", "Status", "Quality"])
        t.setSortingEnabled(True)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return t

    # ──────────────────────────────────────────────────────────────────────
    # Theme
    # ──────────────────────────────────────────────────────────────────────

    def apply_theme(self):
        """Update chart backgrounds when the global theme changes."""
        from src.gui.theme import step_title_font, instruction_banner_style, summary_banner_style
        chart_bg = get_chart_bg()
        for fig, canvas in [(self.vc_fig,      self.vc_canvas),
                             (self.overlay_fig, self.overlay_canvas)]:
            fig.patch.set_facecolor(chart_bg)
            canvas.setStyleSheet(f"background-color: {chart_bg};")
            canvas.draw()
        self._title_label.setStyleSheet(step_title_font(13))
        self._instructions_label.setStyleSheet(instruction_banner_style())
        self.summary_banner.setStyleSheet(summary_banner_style())

    # ──────────────────────────────────────────────────────────────────────
    # File selection helpers
    # ──────────────────────────────────────────────────────────────────────

    def _on_browse_processed(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, "Select Processed Spectrum", "", "CSV Files (*.csv)")
        if fp:
            self._set_processed_path(Path(fp))

    def _on_recent_processed(self, path_str: str):
        self._set_processed_path(Path(path_str))

    def _set_processed_path(self, path: Path):
        self._processed_path = path
        self._proc_path_label.setText(path.name)
        self._proc_path_label.setStyleSheet(
            f"font-size: 9pt; font-weight: 600; color: {C_ACCENT2}; "
            f"border: 1px solid #3A4055; border-radius: 4px; padding: 3px 6px;")
        self._proc_path_label.setToolTip(str(path))
        self._processed_history.add_file(str(path))
        self._proc_recent_btn.refresh()
        logger.info(f"Processed spectrum: {path.name}")

    def _on_browse_reference(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, "Select Reference Spectrum", "", "CSV Files (*.csv)")
        if fp:
            self._set_reference_path(Path(fp))

    def _on_recent_reference(self, path_str: str):
        self._set_reference_path(Path(path_str))

    def _set_reference_path(self, path: Path):
        self._reference_path = path
        self._ref_path_label.setText(path.name)
        self._ref_path_label.setStyleSheet(
            f"font-size: 9pt; font-weight: 600; color: {C_ACCENT2}; "
            f"border: 1px solid #3A4055; border-radius: 4px; padding: 3px 6px;")
        self._ref_path_label.setToolTip(str(path))
        self._reference_history.add_file(str(path))
        self._ref_recent_btn.refresh()
        logger.info(f"Reference spectrum: {path.name}")

    # ──────────────────────────────────────────────────────────────────────
    # Wavelength loading
    # ──────────────────────────────────────────────────────────────────────

    def _on_load_wavelengths(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Wavelengths File", "",
            "CSV Files (*.csv);;Text Files (*.txt)")
        if not filepath:
            return
        self._load_wavelengths_from_path(filepath)

    def _on_recent_wavelengths(self, path_str: str):
        self._load_wavelengths_from_path(path_str)

    def _load_wavelengths_from_path(self, filepath: str):
        """Parse wavelengths from a CSV or text file, update UI and history."""
        try:
            if filepath.lower().endswith('.csv'):
                df = pd.read_csv(filepath)
                wavelengths = df.iloc[:, 0].values
            else:
                with open(filepath, 'r') as f:
                    wavelengths = [float(l.strip()) for l in f if l.strip()]
            self.target_wavelengths = list(wavelengths)

            # Update labels
            name = Path(filepath).name
            self.wavelengths_label.setText(
                f"✅ {len(self.target_wavelengths)} wavelengths loaded from {name}")
            self._wl_path_label.setText(name)
            self._wl_path_label.setStyleSheet(
                f"font-size: 9pt; font-weight: 600; color: {C_ACCENT2}; "
                f"border: 1px solid #3A4055; border-radius: 4px; padding: 3px 6px;")
            self._wl_path_label.setToolTip(filepath)

            # Persist and refresh dropdown
            self._wavelengths_history.add_file(filepath)
            self._wl_recent_btn.refresh()

            logger.info(f"Loaded {len(self.target_wavelengths)} wavelengths from {name}")
        except Exception as e:
            logger.error(f"Failed to load wavelengths: {e}")
            show_error("Error", f"Failed to load wavelengths:\n{e}")

    def _on_manual_wavelengths(self):
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getMultiLineText(
            self, "Enter Target Wavelengths",
            "Enter wavelengths (nm), one per line:")
        if ok and text:
            try:
                self.target_wavelengths = [
                    float(l.strip()) for l in text.split('\n') if l.strip()]
                self.wavelengths_label.setText(
                    f"✅ {len(self.target_wavelengths)} wavelengths entered manually")
                self._wl_path_label.setText("(entered manually)")
                self._wl_path_label.setStyleSheet(
                    f"font-size: 9pt; font-style: italic; color: {C_TEXT_MUTED}; "
                    f"border: 1px solid #3A4055; border-radius: 4px; padding: 3px 6px;")
                logger.info(f"Entered {len(self.target_wavelengths)} wavelengths")
            except ValueError as e:
                show_error("Error", f"Invalid wavelength format:\n{e}")

    # ──────────────────────────────────────────────────────────────────────
    # Validation
    # ──────────────────────────────────────────────────────────────────────

    def _on_validate_clicked(self):
        if self._processed_path is None:
            show_error("Error", "Please select processed spectrum file")
            return
        if self._reference_path is None:
            show_error("Error", "Please select reference spectrum file")
            return
        if not self.target_wavelengths:
            show_error("Error", "Please specify target wavelengths")
            return

        self.info_label.setText("Validating spectrum…")
        self.validate_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.progress_bar.show()
        self.export_csv_button.setEnabled(False)
        self.export_png_button.setEnabled(False)
        self.export_pdf_button.setEnabled(False)

        self.worker_thread = WorkerThread(self._validate_worker)
        self.worker_thread.finished.connect(self._on_validation_finished)
        self.worker_thread.error.connect(self._on_worker_error)
        self.worker_thread.start()

    def _validate_worker(self):
        try:
            processed = pd.read_csv(str(self._processed_path))
            reference = pd.read_csv(str(self._reference_path))
            params = {
                'WINDOW': self.window_spinbox.value(),
                'MIN_POINTS': self.min_points_spinbox.value(),
                'INTERPOLATION_KIND': STEP5_PARAMS['INTERPOLATION_KIND'],
                'VC_THRESHOLD': self.threshold_spinbox.value(),
            }
            analyzer = ValidationAnalyzer(params)

            # Normalize columns once (same as validate_spectrum does internally)
            proc_norm = analyzer.normalize_spectrum_columns(processed)
            ref_norm  = analyzer.normalize_spectrum_columns(reference)

            # Run per-line validation and collect overlay data
            results_rows = []
            self.line_overlays = []
            for wl in self.target_wavelengths:
                line_result = analyzer.validate_line(proc_norm, ref_norm, wl)
                self.line_overlays.append(line_result)
                results_rows.append({
                    'Wavelength_nm': line_result['wavelength'],
                    'Validation_Coefficient': line_result.get('validation_coefficient', np.nan),
                    'Status': 'Success' if 'error' not in line_result
                              else f"Failed: {line_result['error']}",
                })

            self.validation_results = pd.DataFrame(results_rows)
            try:
                from src.gui.session_manager import save_step5
                save_step5(self.validation_results)
            except Exception:
                pass
            return True, "Validation completed successfully"
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return False, str(e)

    def _on_worker_error(self, error_message: str):
        self.validate_button.setEnabled(True)
        self.progress_bar.hide()
        show_error("Validation Error", error_message)
        self.info_label.setText(f"Error: {error_message}")

    def _on_validation_finished(self, _result: dict = None):
        if self.worker_thread is None:
            return
        result = self.worker_thread.result
        if result is None:
            self.validate_button.setEnabled(True)
            self.progress_bar.hide()
            show_error("Validation Failed", "Worker returned no result")
            return

        success, message = result
        self.validate_button.setEnabled(True)
        if not success:
            self.progress_bar.hide()
            show_error("Validation Failed", message)
            self.info_label.setText(f"Error: {message}")
            return

        self._populate_results_table()
        self._update_chart()
        self._update_overlay_chart()
        self._update_summary_banner(self.validation_results)

        self.export_csv_button.setEnabled(True)
        self.export_png_button.setEnabled(True)
        self.export_pdf_button.setEnabled(True)
        self.progress_bar.hide()
        self.save_button.setEnabled(True)

        valid_vc = self.validation_results[
            self.validation_results['Validation_Coefficient'].notna()
        ]['Validation_Coefficient']
        if not valid_vc.empty:
            mean_vc = valid_vc.mean()
            self.info_label.setText(
                f"Validation complete! Mean VC: {mean_vc:.4f} "
                f"({len(valid_vc)} lines validated)")
        logger.info("Validation finished successfully")

    # ──────────────────────────────────────────────────────────────────────
    # Data renderers
    # ──────────────────────────────────────────────────────────────────────

    def _populate_results_table(self):
        if self.validation_results is None:
            return
        df = self.validation_results
        self.results_table.setRowCount(len(df))
        for row, (_, r) in enumerate(df.iterrows()):
            self.results_table.setItem(row, 0, QTableWidgetItem(f"{r['Wavelength_nm']:.2f}"))
            vc_val = r['Validation_Coefficient']
            self.results_table.setItem(row, 1, QTableWidgetItem(
                "N/A" if pd.isna(vc_val) else f"{vc_val:.4f}"))
            self.results_table.setItem(row, 2, QTableWidgetItem(r['Status']))
            tier_label, bg_hex, fg_hex = ChartEngine.classify_vc(vc_val)
            quality_item = QTableWidgetItem(tier_label)
            quality_item.setBackground(QColor(bg_hex))
            quality_item.setForeground(QColor(fg_hex))
            self.results_table.setItem(row, 3, quality_item)
        logger.info("Results table populated")

    def _update_chart(self):
        self.vc_fig.clear()
        ax = self.vc_fig.add_subplot(111)
        ChartEngine.render_vc_histogram(ax, self.validation_results)
        self.vc_canvas.draw()
        self.vc_toolbar.home()

    def _update_overlay_chart(self):
        """Reset to page 0 and redraw whenever new validation results arrive."""
        self._overlay_page = 0
        self._redraw_overlay_page()

    def _get_filtered_overlays(self) -> list:
        """Return overlay entries matching the currently checked tier filters."""
        active_tiers = {t for t, cb in self._tier_checkboxes.items() if cb.isChecked()}
        result = []
        for entry in self.line_overlays:
            vc = entry.get('validation_coefficient', float('nan'))
            tier_label, _, _ = ChartEngine.classify_vc(vc)
            if tier_label in active_tiers and 'processed_wl' in entry:
                result.append(entry)
        return result

    def _on_overlay_filter_changed(self):
        self._overlay_page = 0
        self._redraw_overlay_page()

    def _on_overlay_prev(self):
        if self._overlay_page > 0:
            self._overlay_page -= 1
            self._redraw_overlay_page()

    def _on_overlay_next(self):
        filtered = self._get_filtered_overlays()
        n_pages = max(1, (len(filtered) + self._overlay_page_size - 1)
                      // self._overlay_page_size)
        if self._overlay_page < n_pages - 1:
            self._overlay_page += 1
            self._redraw_overlay_page()

    def _redraw_overlay_page(self):
        """Render the current page of the filtered overlay grid (2×2 max)."""
        from src.gui.theme import (
            C_ACCENT, C_ACCENT2, C_BG_BASE, C_BG_RAISED,
            C_BORDER_SUBTLE, C_TEXT2,
        )

        self.overlay_fig.clear()
        filtered = self._get_filtered_overlays()
        total = len(filtered)
        ps = self._overlay_page_size          # 4 per page
        n_pages = max(1, (total + ps - 1) // ps)
        self._overlay_page = max(0, min(self._overlay_page, n_pages - 1))

        # Update pagination labels / buttons
        self._overlay_page_label.setText(
            f"Page {self._overlay_page + 1} / {n_pages}")
        self._overlay_prev_btn.setEnabled(self._overlay_page > 0)
        self._overlay_next_btn.setEnabled(self._overlay_page < n_pages - 1)
        self._overlay_count_label.setText(
            f"{total} line{'s' if total != 1 else ''} shown")

        if total == 0:
            ax = self.overlay_fig.add_subplot(111)
            ChartEngine._show_placeholder(ax, "No lines match the selected filters")
            ChartEngine.apply_dark_style(self.overlay_fig, ax)
            self.overlay_canvas.draw()
            return

        page_entries = filtered[self._overlay_page * ps:
                                 (self._overlay_page + 1) * ps]
        n = len(page_entries)

        # Always use a 2×2 grid; hide unused cells
        nrows, ncols = 2, 2

        axes = self.overlay_fig.subplots(nrows, ncols, squeeze=False)

        for idx, line_data in enumerate(page_entries):
            ax = axes[idx // ncols][idx % ncols]
            wl     = line_data['processed_wl']
            proc   = line_data['processed_intensity']
            ref    = line_data['reference_intensity']
            vc     = line_data.get('validation_coefficient', float('nan'))
            center = line_data['wavelength']
            tier_label, tier_colour, _ = ChartEngine.classify_vc(vc)

            ax.plot(wl, proc, color=C_ACCENT,  linewidth=1.5, alpha=0.9,
                    label="Processed")
            ax.plot(wl, ref,  color=C_ACCENT2, linewidth=1.5, alpha=0.9,
                    linestyle="--", label="Reference")

            import math as _math
            vc_str = f"{vc:.3f}" if not _math.isnan(vc) else "N/A"
            ax.set_title(f"{center:.1f} nm  VC={vc_str}  [{tier_label}]",
                         fontsize=9.5, color=tier_colour, pad=4,
                         fontweight="bold")
            ax.set_xlabel("Wavelength (nm)", fontsize=8.5, color=C_TEXT2)
            ax.set_ylabel("Norm. Intensity", fontsize=8.5, color=C_TEXT2)

            ax.set_facecolor(C_BG_RAISED)
            ax.tick_params(colors=C_TEXT2, which="both", labelsize=8)
            for spine in ax.spines.values():
                spine.set_edgecolor(C_BORDER_SUBTLE); spine.set_linewidth(0.7)
            ax.grid(True, color=C_BORDER_SUBTLE, alpha=0.45,
                    linewidth=0.5, linestyle="--")

            leg = ax.legend(fontsize=8, framealpha=0.6, loc="upper right")
            leg.get_frame().set_facecolor(C_BG_RAISED)
            leg.get_frame().set_edgecolor(C_BORDER_SUBTLE)
            for t in leg.get_texts():
                t.set_color(C_TEXT2)

        # Hide unused axes in the 2×2 grid
        for idx in range(n, nrows * ncols):
            axes[idx // ncols][idx % ncols].set_visible(False)

        self.overlay_fig.patch.set_facecolor(C_BG_BASE)
        try:
            self.overlay_fig.tight_layout(pad=1.2, h_pad=2.0, w_pad=1.2)
        except Exception:
            pass
        self.overlay_canvas.draw()
        self.overlay_toolbar.home()

    def _update_summary_banner(self, validation_results: pd.DataFrame):
        if validation_results is None or validation_results.empty:
            self.summary_banner.setText("No results to summarise.")
            self.mean_vc_label.setText("—")
            return
        valid_vc = validation_results['Validation_Coefficient'].dropna()
        total_count = len(validation_results)
        if valid_vc.empty:
            self.summary_banner.setText(
                f"Total wavelengths: {total_count} | All validations failed")
            self.mean_vc_label.setText("—")
            return
        mean_vc = valid_vc.mean()
        tier_counts: dict[str, int] = {}
        for vc_val in validation_results['Validation_Coefficient']:
            tier_label, _, _ = ChartEngine.classify_vc(vc_val)
            tier_counts[tier_label] = tier_counts.get(tier_label, 0) + 1
        tier_parts = []
        for label in ["Excellent", "Good", "Moderate", "Weak", "Failed"]:
            count = tier_counts.get(label, 0)
            if count > 0:
                tier_parts.append(f"{label}: {count}")
        self.summary_banner.setText(
            f"Mean VC: {mean_vc:.4f}  |  Total wavelengths: {total_count}  |  "
            + " | ".join(tier_parts))
        _, colour, _ = ChartEngine.classify_vc(mean_vc)
        self.mean_vc_label.setStyleSheet(mean_vc_label_style(colour))
        self.mean_vc_label.setText(f"{mean_vc:.4f}")

    # ──────────────────────────────────────────────────────────────────────
    # Export / save
    # ──────────────────────────────────────────────────────────────────────

    def _on_export_csv_clicked(self):
        if self.validation_results is None:
            show_error("Error", "No data to export")
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "validation_results", "CSV Files (*.csv)")
        if not filepath:
            return
        try:
            export_step5_csv(self.validation_results, Path(filepath))
            show_info("Export Successful", f"CSV saved to:\n{filepath}")
        except Exception as e:
            logger.error(f"CSV export failed: {e}")
            show_error("Export Failed", f"Failed to export CSV:\n{e}")

    def _on_export_png_clicked(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", "vc_histogram", "PNG Files (*.png)")
        if not filepath:
            return
        try:
            export_step5_png(self.vc_fig, Path(filepath))
            show_info("Export Successful", f"PNG saved to:\n{filepath}")
        except Exception as e:
            logger.error(f"PNG export failed: {e}")
            show_error("Export Failed", f"Failed to export PNG:\n{e}")

    def _on_export_pdf_clicked(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Report", "LIBS_Validation_Report", "PDF Files (*.pdf)")
        if not filepath:
            return
        params = {
            'WINDOW': self.window_spinbox.value(),
            'MIN_POINTS': self.min_points_spinbox.value(),
            'VC_THRESHOLD': self.threshold_spinbox.value(),
        }
        processed_path = self.processed_selector.get_filepath()
        reference_path = self.reference_selector.get_filepath()
        try:
            generate_pdf_report(
                validation_results_df=self.validation_results,
                params=params,
                vc_fig=self.vc_fig,
                processed_filename=Path(processed_path).name if processed_path else "Unknown",
                reference_filename=Path(reference_path).name if reference_path else "Unknown",
                target_wavelengths=self.target_wavelengths,
                filepath=Path(filepath),
            )
            show_info("Export Successful", f"PDF report saved to:\n{filepath}")
        except ImportError:
            show_error("Missing Dependency",
                       "reportlab is not installed.\nRun: pip install reportlab")
        except Exception as e:
            logger.error(f"PDF export failed: {e}")
            show_error("Export Failed", f"Failed to generate PDF:\n{e}")

    def _on_save_clicked(self):
        if self.validation_results is None:
            show_error("Error", "No results to save")
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Validation Report", "validation_results", "CSV Files (*.csv)")
        if filepath:
            try:
                self.validation_results.to_csv(filepath, index=False)
                show_info("Success", f"Report saved to:\n{filepath}")
            except Exception as e:
                logger.error(f"Failed to save report: {e}")
                show_error("Error", f"Failed to save report:\n{e}")
