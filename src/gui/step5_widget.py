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
    QCheckBox, QFrame, QListWidget, QListWidgetItem, QAbstractItemView,
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
        self._custom_ref_history = FileHistory(role="step5_custom_ref")

        # Stored file paths (replaces FileSelector)
        self._processed_path: Path | None = None
        self._reference_path: Path | None = None

        # Multi-file reference lists
        self._ref_paths: list[str] = []        # paths from Processed Data folder checklist
        # Restore persisted custom reference files from history (survives restarts)
        self._custom_ref_paths: list[str] = [
            p for p in self._custom_ref_history.get_recent()
            if Path(p).exists()
        ]

        logger.info("Initializing Step 5 widget")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._create_left_panel(), stretch=0)
        main_layout.addWidget(self._create_right_panel(), stretch=1)

        # Restore persisted custom reference files into the list widget
        self._restore_custom_ref_list()

    # ──────────────────────────────────────────────────────────────────────
    # Panel builders
    # ──────────────────────────────────────────────────────────────────────

    def _create_left_panel(self) -> QWidget:
        """Scrollable control panel (fixed width)."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("Step 5: Validation with Reference Spectra")
        tf = QFont(); tf.setBold(True); tf.setPointSize(12)
        title.setFont(tf)
        title.setStyleSheet(step_title_font(13))
        title.setWordWrap(True)
        layout.addWidget(title)
        self._title_label = title

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

        self.summary_banner = QLabel("Run validation to see summary")
        self.summary_banner.setStyleSheet(summary_banner_style())
        self.summary_banner.setWordWrap(True)
        layout.addWidget(self.summary_banner)

        self.mean_vc_label = QLabel("—")
        layout.addWidget(self.mean_vc_label)

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
        proc_browse_btn = QPushButton("Browse")
        proc_browse_btn.setFixedWidth(75)
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

        files_group.setLayout(fl)
        layout.addWidget(files_group)

        # ── Pure Element Reference Files (Processed Data folder) ──────────
        layout.addWidget(self._create_processed_data_group())

        # ── Custom Reference Files ────────────────────────────────────────
        layout.addWidget(self._create_custom_ref_group())

        # ── Selected Reference Files summary ──────────────────────────────
        self._ref_sel_group = QGroupBox("Selected Reference Files")
        rsg = QVBoxLayout(self._ref_sel_group)
        rsg.setContentsMargins(6, 6, 6, 6)
        rsg.setSpacing(4)

        rsg_header = QHBoxLayout()
        self._ref_sel_count_label = QLabel("No reference files selected")
        self._ref_sel_count_label.setStyleSheet("font-size: 10px; font-weight: bold;")
        rsg_header.addWidget(self._ref_sel_count_label)
        rsg_header.addStretch()
        self._ref_sel_toggle_btn = QPushButton("▶ Show")
        self._ref_sel_toggle_btn.setFixedHeight(20)
        self._ref_sel_toggle_btn.setFixedWidth(60)
        self._ref_sel_toggle_btn.setStyleSheet(
            "QPushButton { font-size: 9px; padding: 0 4px; }")
        self._ref_sel_toggle_btn.clicked.connect(self._on_toggle_ref_sel_list)
        rsg_header.addWidget(self._ref_sel_toggle_btn)
        rsg.addLayout(rsg_header)

        self._ref_sel_list_frame = QFrame()
        self._ref_sel_list_frame.setVisible(False)
        rsl_layout = QVBoxLayout(self._ref_sel_list_frame)
        rsl_layout.setContentsMargins(0, 2, 0, 0)
        rsl_layout.setSpacing(2)
        self._ref_sel_list_widget = QListWidget()
        self._ref_sel_list_widget.setMaximumHeight(120)
        self._ref_sel_list_widget.setMinimumHeight(60)
        self._ref_sel_list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self._ref_sel_list_widget.setStyleSheet("font-size: 9pt;")
        rsl_layout.addWidget(self._ref_sel_list_widget)
        rsg.addWidget(self._ref_sel_list_frame)
        layout.addWidget(self._ref_sel_group)

        # Now all summary widgets exist — sync the initial state
        # (picks up any files that were already checked in the folder list)
        self._update_ref_sel_summary()

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

        # Manual entry + clear on one row
        manual_row = QHBoxLayout()
        manual_row.setSpacing(4)
        self.manual_lines_button = QPushButton("Enter Manually…")
        self.manual_lines_button.setFixedHeight(26)
        self.manual_lines_button.clicked.connect(self._on_manual_wavelengths)
        manual_row.addWidget(self.manual_lines_button, stretch=3)
        self._clear_wavelengths_btn = QPushButton("Clear")
        self._clear_wavelengths_btn.setFixedHeight(26)
        self._clear_wavelengths_btn.setToolTip("Clear all target wavelengths")
        self._clear_wavelengths_btn.clicked.connect(self._on_clear_wavelengths)
        manual_row.addWidget(self._clear_wavelengths_btn, stretch=1)
        ll.addLayout(manual_row)

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

    def _create_processed_data_group(self) -> QGroupBox:
        """
        'Processed Data' folder group — mirrors Step 3's Built-in Database group.
        Scans the bundled 'Processed Data' folder for pure-element CSV files and
        presents them as a checkable list so the user can pick which elements to
        validate against.
        """
        group = QGroupBox("Pure Element Reference Files (Processed Data)")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(6)

        # ── Status / installer caution banner ─────────────────────────────
        self._ref_db_status_label = QLabel("⏳ Scanning Processed Data folder…")
        self._ref_db_status_label.setStyleSheet(
            "font-size: 10px; color: #888; padding: 2px;")
        self._ref_db_status_label.setWordWrap(True)
        layout.addWidget(self._ref_db_status_label)

        # Installer caution — same pattern as Step 3's database folder note
        caution_lbl = QLabel(
            "ℹ️  Drop new pure-element CSVs into the 'Processed Data' folder "
            "and click Refresh — they will appear automatically.")
        caution_lbl.setWordWrap(True)
        caution_lbl.setStyleSheet(
            "font-size: 9px; color: #AEB7C4; padding: 2px;")
        layout.addWidget(caution_lbl)

        # ── Open folder + Refresh row ─────────────────────────────────────
        folder_row = QHBoxLayout()
        folder_row.setSpacing(4)
        self._open_ref_folder_btn = QPushButton("📂 Open Folder")
        self._open_ref_folder_btn.setToolTip(
            "Open the 'Processed Data' folder in File Explorer.\n"
            "Add pure-element CSV files here and click Refresh.")
        self._open_ref_folder_btn.setFixedHeight(24)
        self._open_ref_folder_btn.clicked.connect(self._on_open_ref_folder)
        folder_row.addWidget(self._open_ref_folder_btn)

        self._refresh_ref_btn = QPushButton("🔄 Refresh")
        self._refresh_ref_btn.setToolTip(
            "Rescan the Processed Data folder and rebuild the file list.\n"
            "Use after adding or removing pure-element files.")
        self._refresh_ref_btn.setFixedHeight(24)
        self._refresh_ref_btn.clicked.connect(self._on_refresh_ref_folder)
        folder_row.addWidget(self._refresh_ref_btn)
        layout.addLayout(folder_row)

        # ── File checklist ────────────────────────────────────────────────
        self._ref_file_list = QListWidget()
        self._ref_file_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self._ref_file_list.setMinimumHeight(80)
        self._ref_file_list.setMaximumHeight(160)
        self._ref_file_list.setToolTip(
            "Check the pure-element files you want to validate against.\n"
            "All checked files will be merged before validation.")
        layout.addWidget(self._ref_file_list)

        # Select all / None row
        sel_row = QHBoxLayout()
        sel_row.setSpacing(4)
        sel_all_btn = QPushButton("All")
        sel_all_btn.setFixedHeight(22)
        sel_all_btn.clicked.connect(self._on_ref_select_all)
        sel_row.addWidget(sel_all_btn)
        sel_none_btn = QPushButton("None")
        sel_none_btn.setFixedHeight(22)
        sel_none_btn.clicked.connect(self._on_ref_select_none)
        sel_row.addWidget(sel_none_btn)
        self._ref_checked_count_lbl = QLabel("0 selected")
        self._ref_checked_count_lbl.setStyleSheet("font-size: 10px; color: grey;")
        sel_row.addWidget(self._ref_checked_count_lbl)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # Populate immediately
        self._populate_ref_file_list()

        return group

    def _create_custom_ref_group(self) -> QGroupBox:
        """Collapsible group for custom (manually uploaded) reference files."""
        group = QGroupBox("Custom Reference Files  (optional)")
        group.setCheckable(True)
        group.setChecked(False)
        group.setToolTip(
            "Upload your own pure-element CSV files to supplement or replace "
            "the files in the Processed Data folder."
        )
        layout = QVBoxLayout(group)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._custom_ref_list_widget = QListWidget()
        self._custom_ref_list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._custom_ref_list_widget.setMaximumHeight(70)
        layout.addWidget(self._custom_ref_list_widget)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add File(s)…")
        add_btn.clicked.connect(self._on_add_custom_ref_files)
        btn_row.addWidget(add_btn)
        rem_btn = QPushButton("Remove")
        rem_btn.clicked.connect(self._on_remove_custom_ref_files)
        btn_row.addWidget(rem_btn)
        clr_btn = QPushButton("Clear")
        clr_btn.clicked.connect(self._on_clear_custom_ref_files)
        btn_row.addWidget(clr_btn)
        layout.addLayout(btn_row)

        recent_row = QHBoxLayout()
        self._custom_ref_recent_btn = RecentFilesButton(self._custom_ref_history)
        self._custom_ref_recent_btn.file_selected.connect(
            self._on_recent_custom_ref_selected)
        recent_row.addWidget(self._custom_ref_recent_btn)
        recent_row.addStretch()
        layout.addLayout(recent_row)

        return group

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
    # Processed Data folder helpers
    # ──────────────────────────────────────────────────────────────────────

    def _get_processed_data_folder(self) -> Path:
        """
        Resolve the 'Processed Data' folder in all three environments:

          A) Development  — repo root / Processed Data
          B) Installed    — registry key → ProgramData\\LIBS_Analysis\\Processed Data
                            (written there by the Inno Setup installer)
          C) Portable     — beside the .exe  or  _internal/ beside the .exe
        """
        import sys, os

        if getattr(sys, "frozen", False):
            # ── 1. Registry (installer sets this) ─────────────────────────
            try:
                import winreg
                access_mask = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"Software\JFD Tech\LIBS Spectral Analysis",
                    0,
                    access_mask,
                )
                path_str, _ = winreg.QueryValueEx(key, "ProcessedDataPath")
                winreg.CloseKey(key)
                reg_path = Path(path_str)
                if reg_path.exists():
                    return reg_path
            except Exception:
                pass  # registry key absent (portable build or first run)

            # ── 2. ProgramData (standard installer layout) ─────────────────
            prog_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
            installed = prog_data / "LIBS_Analysis" / "Processed Data"
            if installed.exists():
                return installed

            # ── 3. _internal subfolder (PyInstaller 6.x one-folder layout) ─
            exe_dir = Path(sys.executable).parent
            internal = exe_dir / "_internal" / "Processed Data"
            if internal.exists():
                return internal

            # ── 4. Beside the exe (portable / PyInstaller <6) ──────────────
            beside = exe_dir / "Processed Data"
            if beside.exists():
                return beside

            # Final fallback — return best-guess so the UI shows the warning
            return installed

        # Development: src/gui/step5_widget.py → src/gui → src → project root
        return Path(__file__).resolve().parent.parent.parent / "Processed Data"

    def _populate_ref_file_list(self):
        """Scan Processed Data folder and populate the checklist."""
        folder = self._get_processed_data_folder()
        self._ref_file_list.clear()

        if not folder.exists():
            self._ref_db_status_label.setText(
                f"⚠ Folder not found: {folder}\n"
                "Place pure-element CSV files in 'Processed Data' next to the project.")
            self._ref_db_status_label.setStyleSheet(
                "font-size: 10px; color: #F44336; padding: 2px;")
            return

        csv_files = sorted(folder.glob("*.csv"))
        if not csv_files:
            self._ref_db_status_label.setText(
                "⚠ No CSV files found in Processed Data folder.")
            self._ref_db_status_label.setStyleSheet(
                "font-size: 10px; color: #F4B942; padding: 2px;")
            return

        for fp in csv_files:
            item = QListWidgetItem(fp.stem)
            item.setData(Qt.ItemDataRole.UserRole, str(fp))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setToolTip(str(fp))
            self._ref_file_list.addItem(item)

        self._ref_db_status_label.setText(
            f"✅ {len(csv_files)} pure-element file(s) found in Processed Data")
        self._ref_db_status_label.setStyleSheet(
            "font-size: 10px; color: #4CAF50; padding: 2px;")
        self._ref_file_list.itemChanged.connect(self._on_ref_checklist_changed)
        # Don't call _update_ref_sel_summary here — the summary widgets
        # (_ref_sel_count_label etc.) are built later in _create_left_panel.

    def _on_ref_checklist_changed(self):
        self._update_ref_sel_summary()

    def _on_ref_select_all(self):
        for i in range(self._ref_file_list.count()):
            self._ref_file_list.item(i).setCheckState(Qt.CheckState.Checked)

    def _on_ref_select_none(self):
        for i in range(self._ref_file_list.count()):
            self._ref_file_list.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _on_open_ref_folder(self):
        """Open the Processed Data folder in the system file explorer."""
        import subprocess
        folder = self._get_processed_data_folder()
        if not folder.exists():
            show_error(
                "Folder Not Found",
                f"Processed Data folder does not exist:\n{folder}")
            return
        try:
            subprocess.Popen(f'explorer "{folder}"')
        except Exception as exc:
            logger.warning(f"Could not open folder: {exc}")
            show_info("Processed Data Folder", str(folder))

    def _on_refresh_ref_folder(self):
        """Rescan the Processed Data folder and rebuild the checklist."""
        self._ref_file_list.itemChanged.disconnect() if self._ref_file_list.count() else None
        self._populate_ref_file_list()

    def _get_checked_ref_paths(self) -> list[str]:
        """Return paths of all checked items in the Processed Data checklist."""
        paths = []
        for i in range(self._ref_file_list.count()):
            item = self._ref_file_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                paths.append(item.data(Qt.ItemDataRole.UserRole))
        return paths

    def _update_ref_sel_summary(self):
        """Refresh the Selected Reference Files summary panel and count label."""
        # Guard: summary widgets are built after the processed data group,
        # so this can be called before they exist during construction.
        if not hasattr(self, "_ref_sel_count_label"):
            return

        folder_paths = self._get_checked_ref_paths()
        custom_paths = list(self._custom_ref_paths)
        all_paths = folder_paths + custom_paths

        n = len(all_paths)
        n_checked = len(folder_paths)
        self._ref_checked_count_lbl.setText(f"{n_checked} selected")
        self._ref_checked_count_lbl.setStyleSheet(
            f"font-size: 10px; color: {'#4CAF50' if n_checked else 'grey'};")

        if n == 0:
            self._ref_sel_count_label.setText("No reference files selected")
            self._ref_sel_count_label.setStyleSheet(
                "font-size: 10px; font-weight: bold; color: grey;")
        else:
            self._ref_sel_count_label.setText(
                f"{n} reference file{'s' if n != 1 else ''} selected")
            self._ref_sel_count_label.setStyleSheet(
                "font-size: 10px; font-weight: bold; color: #4CAF50;")

        self._ref_sel_list_widget.clear()
        for fp in all_paths:
            item = QListWidgetItem(Path(fp).name)
            item.setToolTip(fp)
            item.setForeground(QColor("#3FA9F5"))
            self._ref_sel_list_widget.addItem(item)

    def _on_toggle_ref_sel_list(self):
        visible = not self._ref_sel_list_frame.isVisible()
        self._ref_sel_list_frame.setVisible(visible)
        self._ref_sel_toggle_btn.setText("▼ Hide" if visible else "▶ Show")

    # ──────────────────────────────────────────────────────────────────────
    # Custom reference file helpers
    # ──────────────────────────────────────────────────────────────────────

    def _on_add_custom_ref_files(self):
        recent = self._custom_ref_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add Custom Reference Files", start_dir,
            "CSV Files (*.csv);;All Files (*)")
        for fp in files:
            if fp not in self._custom_ref_paths:
                self._custom_ref_paths.append(fp)
                self._custom_ref_list_widget.addItem(
                    QListWidgetItem(Path(fp).name))
                self._custom_ref_history.add_file(fp)
        if files:
            self._custom_ref_recent_btn.refresh()
            self._update_ref_sel_summary()

    def _on_remove_custom_ref_files(self):
        for item in self._custom_ref_list_widget.selectedItems():
            row = self._custom_ref_list_widget.row(item)
            self._custom_ref_list_widget.takeItem(row)
            if row < len(self._custom_ref_paths):
                self._custom_ref_paths.pop(row)
        self._update_ref_sel_summary()

    def _on_clear_custom_ref_files(self):
        self._custom_ref_list_widget.clear()
        self._custom_ref_paths.clear()
        self._update_ref_sel_summary()

    def _on_recent_custom_ref_selected(self, path_str: str):
        if path_str not in self._custom_ref_paths:
            self._custom_ref_paths.append(path_str)
            self._custom_ref_list_widget.addItem(
                QListWidgetItem(Path(path_str).name))
            self._update_ref_sel_summary()

    def _restore_custom_ref_list(self):
        """
        Re-populate the custom reference QListWidget from the persisted list.
        Called once after the UI is fully built so widgets exist.
        Paths that no longer exist on disk are silently skipped.
        """
        for fp in self._custom_ref_paths:
            self._custom_ref_list_widget.addItem(QListWidgetItem(Path(fp).name))
        if self._custom_ref_paths:
            self._update_ref_sel_summary()

    # ──────────────────────────────────────────────────────────────────────
    # File selection helpers
    # ──────────────────────────────────────────────────────────────────────

    def _on_browse_processed(self):
        recent = self._processed_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        fp, _ = QFileDialog.getOpenFileName(
            self, "Select Processed Spectrum", start_dir, "CSV Files (*.csv)")
        if fp:
            self._set_processed_path(Path(fp))

    def _on_recent_processed(self, path_str: str):
        self._set_processed_path(Path(path_str))

    def _set_processed_path(self, path: Path):
        # Persist first — so history is saved even if UI update throws
        self._processed_path = path
        self._processed_history.add_file(str(path))
        # Update UI
        try:
            self._proc_path_label.setText(path.name)
            self._proc_path_label.setStyleSheet(
                f"font-size: 9pt; font-weight: 600; color: {C_ACCENT2}; "
                f"border: 1px solid #3A4055; border-radius: 4px; padding: 3px 6px;")
            self._proc_path_label.setToolTip(str(path))
            self._proc_recent_btn.refresh()
        except AttributeError:
            pass   # widget not yet fully constructed — path is stored, UI will catch up
        logger.info(f"Processed spectrum: {path.name}")

    # ──────────────────────────────────────────────────────────────────────
    # Wavelength loading
    # ──────────────────────────────────────────────────────────────────────

    def _on_load_wavelengths(self):
        recent = self._wavelengths_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Wavelengths File", start_dir,
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

    def _on_clear_wavelengths(self):
        """Clear all target wavelengths and reset the wavelength UI labels."""
        self.target_wavelengths = []
        self.wavelengths_label.setText("No wavelengths specified")
        self._wl_path_label.setText("(No file loaded)")
        self._wl_path_label.setStyleSheet(
            f"font-size: 9pt; font-style: italic; color: {C_TEXT_MUTED}; "
            f"border: 1px solid #3A4055; border-radius: 4px; padding: 3px 6px;")
        logger.info("Target wavelengths cleared")

    # ──────────────────────────────────────────────────────────────────────
    # Validation
    # ──────────────────────────────────────────────────────────────────────

    def _on_validate_clicked(self):
        has_inmemory = getattr(self, '_step1_inmemory_data', None) is not None
        if self._processed_path is None and not has_inmemory:
            show_error("Error", "Please select a processed spectrum file")
            return

        # Collect all selected reference paths (folder checklist + custom)
        ref_paths = self._get_checked_ref_paths() + list(self._custom_ref_paths)
        if not ref_paths:
            show_error("Error",
                       "Please select at least one pure-element reference file.\n"
                       "Check files in 'Pure Element Reference Files' or add "
                       "custom files.")
            return
        if not self.target_wavelengths:
            show_error("Error", "Please specify target wavelengths")
            return

        # Stash for the worker
        self._active_ref_paths = ref_paths

        # Ensure processed path is persisted to history
        self._processed_history.add_file(str(self._processed_path))
        self._proc_recent_btn.refresh()

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
            # Use in-memory Step 1 data when available (no file read needed)
            inmemory = getattr(self, '_step1_inmemory_data', None)
            if inmemory is not None:
                processed = pd.DataFrame({
                    'Wavelength': inmemory.wavelength,
                    'Intensity':  inmemory.corrected,
                    'Corrected':  inmemory.corrected,
                })
            else:
                try:
                    processed = pd.read_csv(str(self._processed_path))
                except Exception:
                    processed = pd.read_csv(str(self._processed_path), sep=None, engine='python')
            # Merge all selected reference files into one DataFrame
            ref_frames = []
            for rp in getattr(self, "_active_ref_paths", []):
                try:
                    ref_frames.append(pd.read_csv(rp))
                except Exception as e:
                    logger.warning(f"Could not read reference file {rp}: {e}")
            if not ref_frames:
                raise ValueError("No reference files could be loaded.")
            # Concatenate then deduplicate on wavelength column (keep first)
            reference = pd.concat(ref_frames, ignore_index=True)
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
        recent = self._processed_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export CSV",
            str(Path(start_dir) / "validation_results"),
            "CSV Files (*.csv)")
        if not filepath:
            return
        try:
            export_step5_csv(self.validation_results, Path(filepath))
            show_info("Export Successful", f"CSV saved to:\n{filepath}")
        except Exception as e:
            logger.error(f"CSV export failed: {e}")
            show_error("Export Failed", f"Failed to export CSV:\n{e}")

    def _on_export_png_clicked(self):
        recent = self._processed_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export PNG",
            str(Path(start_dir) / "vc_histogram"),
            "PNG Files (*.png)")
        if not filepath:
            return
        try:
            export_step5_png(self.vc_fig, Path(filepath))
            show_info("Export Successful", f"PNG saved to:\n{filepath}")
        except Exception as e:
            logger.error(f"PNG export failed: {e}")
            show_error("Export Failed", f"Failed to export PNG:\n{e}")

    def _on_export_pdf_clicked(self):
        recent = self._processed_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Report",
            str(Path(start_dir) / "LIBS_Validation_Report"),
            "PDF Files (*.pdf)")
        if not filepath:
            return
        params = {
            'WINDOW': self.window_spinbox.value(),
            'MIN_POINTS': self.min_points_spinbox.value(),
            'VC_THRESHOLD': self.threshold_spinbox.value(),
        }
        processed_path = str(self._processed_path) if self._processed_path else None
        reference_paths = getattr(self, "_active_ref_paths", [])
        reference_names = ", ".join(
            Path(p).name for p in reference_paths) if reference_paths else "Unknown"
        try:
            generate_pdf_report(
                validation_results_df=self.validation_results,
                params=params,
                vc_fig=self.vc_fig,
                processed_filename=Path(processed_path).name if processed_path else "Unknown",
                reference_filename=reference_names,
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

    def load_from_step1(self, processed_data) -> None:
        """
        Auto-load Step 1 processed spectrum directly into Step 5.

        processed_data — a ProcessedSpectra object with .wavelength and .corrected arrays.
        Stores it in-memory so the validation worker doesn't need to read a file.
        """
        if processed_data is None:
            return
        self._step1_inmemory_data = processed_data
        self._processed_path = None   # no file — using in-memory object

        n = len(processed_data.wavelength)
        self._proc_path_label.setText("← loaded from Step 1")
        self._proc_path_label.setStyleSheet(
            f"font-size: 9pt; font-weight: 600; color: {C_ACCENT2}; "
            f"border: 1px solid #3A4055; border-radius: 4px; padding: 3px 6px;")
        self._proc_path_label.setToolTip(
            "Spectrum data was passed in-memory from Step 1 — no file needed.")
        self.info_label.setText(
            f"✅ {n:,}-point spectrum loaded from Step 1.\n"
            "Select reference files, set wavelengths, then validate."
        )
        logger.info("Step 5: in-memory spectrum loaded from Step 1 (%d points)", n)

    def load_from_step4(self, analysis_results: dict) -> None:
        """
        Receive Step 4 analysis results (primary element hint).

        Currently used only to pre-populate the status label with the
        identified primary element — no hard dependency on this data for
        validation to proceed.
        """
        if not analysis_results:
            return
        primary = analysis_results.get("primary_element", "")
        if primary:
            self.summary_banner.setText(
                f"Primary element from Step 4: <b>{primary}</b> — "
                "ready for validation."
            )
        logger.info("Step 5: received Step 4 primary element hint: %s", primary)

    def _on_save_clicked(self):
        if self.validation_results is None:
            show_error("Error", "No results to save")
            return
        recent = self._processed_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Validation Report",
            str(Path(start_dir) / "validation_results"),
            "CSV Files (*.csv)")
        if filepath:
            try:
                self.validation_results.to_csv(filepath, index=False)
                show_info("Success", f"Report saved to:\n{filepath}")
            except Exception as e:
                logger.error(f"Failed to save report: {e}")
                show_error("Error", f"Failed to save report:\n{e}")
