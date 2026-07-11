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
    QCheckBox,
)
from PyQt6.QtGui import QFont, QColor

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from src import setup_logger
from src.config import STEP5_PARAMS
from src.core.step5_validation import ValidationAnalyzer
from src.io.file_reader import CSVReader
from src.gui.gui_utils import (
    FileSelector, WorkerThread,
    show_error, show_info
)
from src.gui.charts import ChartEngine
from src.gui.export_engine import export_step5_csv, export_step5_png, generate_pdf_report
from src.gui.theme import (
    primary_button_style, instruction_banner_style, step_title_font,
    summary_banner_style, mean_vc_label_style, progress_bar_style
)

logger = setup_logger(__name__)

_CHART_BG = "#141519"


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
        self._overlay_page_size = 9   # 3×3 grid

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

        files_group = QGroupBox("Input Spectra")
        fl = QVBoxLayout()
        self.processed_selector = FileSelector("Processed Spectrum:", "CSV Files (*.csv)")
        fl.addWidget(self.processed_selector)
        self.reference_selector = FileSelector("Reference Spectrum:", "CSV Files (*.csv)")
        fl.addWidget(self.reference_selector)
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
        self.wavelengths_label = QLabel("No wavelengths specified")
        self.wavelengths_label.setWordWrap(True)
        ll.addWidget(self.wavelengths_label)
        wl_btns = QHBoxLayout()
        self.load_lines_button = QPushButton("Load from File…")
        self.load_lines_button.clicked.connect(self._on_load_wavelengths)
        wl_btns.addWidget(self.load_lines_button)
        self.manual_lines_button = QPushButton("Enter Manually…")
        self.manual_lines_button.clicked.connect(self._on_manual_wavelengths)
        wl_btns.addWidget(self.manual_lines_button)
        ll.addLayout(wl_btns)
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
        """Right panel: tab widget (histogram | overlay) + results table."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Chart tabs ─────────────────────────────────────────────────────
        self.chart_tabs = QTabWidget()

        # Tab 1: VC Histogram
        self.vc_fig = Figure(figsize=(8, 3), dpi=100)
        self.vc_fig.patch.set_facecolor(_CHART_BG)
        self.vc_canvas = FigureCanvasQTAgg(self.vc_fig)
        self.vc_canvas.setStyleSheet(f"background-color: {_CHART_BG};")
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
        self.overlay_fig = Figure(figsize=(8, 4), dpi=100)
        self.overlay_fig.patch.set_facecolor(_CHART_BG)
        self.overlay_canvas = FigureCanvasQTAgg(self.overlay_fig)
        self.overlay_canvas.setStyleSheet(f"background-color: {_CHART_BG};")
        self.overlay_toolbar = NavigationToolbar2QT(self.overlay_canvas)
        otl.addWidget(self.overlay_canvas, stretch=1)
        otl.addWidget(self.overlay_toolbar)

        self.chart_tabs.addTab(overlay_tab, "Spectral Overlays")

        chart_wrapper = QWidget()
        cwl = QVBoxLayout(chart_wrapper)
        cwl.setContentsMargins(0, 0, 0, 0); cwl.setSpacing(0)
        cwl.addWidget(self.chart_tabs)
        chart_wrapper.setMinimumHeight(280)
        splitter.addWidget(chart_wrapper)

        # ── Results table ─────────────────────────────────────────────────
        self.results_table = self._create_results_table()
        splitter.addWidget(self.results_table)

        splitter.setSizes([340, 340])
        layout.addWidget(splitter)
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
    # Wavelength loading
    # ──────────────────────────────────────────────────────────────────────

    def _on_load_wavelengths(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Wavelengths File", "",
            "CSV Files (*.csv);;Text Files (*.txt)")
        if not filepath:
            return
        try:
            if filepath.endswith('.csv'):
                df = pd.read_csv(filepath)
                wavelengths = df.iloc[:, 0].values
            else:
                with open(filepath, 'r') as f:
                    wavelengths = [float(l.strip()) for l in f if l.strip()]
            self.target_wavelengths = list(wavelengths)
            self.wavelengths_label.setText(
                f"{len(self.target_wavelengths)} wavelengths loaded")
            logger.info(f"Loaded {len(self.target_wavelengths)} wavelengths")
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
                    f"{len(self.target_wavelengths)} wavelengths entered")
                logger.info(f"Entered {len(self.target_wavelengths)} wavelengths")
            except ValueError as e:
                show_error("Error", f"Invalid wavelength format:\n{e}")

    # ──────────────────────────────────────────────────────────────────────
    # Validation
    # ──────────────────────────────────────────────────────────────────────

    def _on_validate_clicked(self):
        if self.processed_selector.get_filepath() is None:
            show_error("Error", "Please select processed spectrum file")
            return
        if self.reference_selector.get_filepath() is None:
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
            processed = pd.read_csv(str(self.processed_selector.get_filepath()))
            reference = pd.read_csv(str(self.reference_selector.get_filepath()))
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
        """Render the current page of the filtered overlay grid (3×3 max)."""
        from src.gui.theme import (
            C_ACCENT, C_ACCENT2, C_BG_BASE, C_BG_RAISED,
            C_BORDER_SUBTLE, C_TEXT2,
        )

        self.overlay_fig.clear()
        filtered = self._get_filtered_overlays()
        total = len(filtered)
        ps = self._overlay_page_size
        n_pages = max(1, (total + ps - 1) // ps)
        self._overlay_page = max(0, min(self._overlay_page, n_pages - 1))

        # Update pagination labels/buttons
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
        ncols = min(n, 3)
        nrows = (n + ncols - 1) // ncols

        axes = self.overlay_fig.subplots(nrows, ncols, squeeze=False)

        for idx, line_data in enumerate(page_entries):
            ax = axes[idx // ncols][idx % ncols]
            wl     = line_data['processed_wl']
            proc   = line_data['processed_intensity']
            ref    = line_data['reference_intensity']
            vc     = line_data.get('validation_coefficient', float('nan'))
            center = line_data['wavelength']
            tier_label, tier_colour, _ = ChartEngine.classify_vc(vc)

            ax.plot(wl, proc, color=C_ACCENT,  linewidth=1.2, alpha=0.9,
                    label="Processed")
            ax.plot(wl, ref,  color=C_ACCENT2, linewidth=1.2, alpha=0.9,
                    linestyle="--", label="Reference")

            import math as _math
            vc_str = f"{vc:.3f}" if not _math.isnan(vc) else "N/A"
            ax.set_title(f"{center:.1f} nm  VC={vc_str}  [{tier_label}]",
                         fontsize=7.5, color=tier_colour, pad=3,
                         fontweight="bold")
            ax.set_xlabel("λ (nm)", fontsize=6.5, color=C_TEXT2)
            ax.set_ylabel("Norm. Int.", fontsize=6.5, color=C_TEXT2)

            ax.set_facecolor(C_BG_RAISED)
            ax.tick_params(colors=C_TEXT2, which="both", labelsize=6)
            for spine in ax.spines.values():
                spine.set_edgecolor(C_BORDER_SUBTLE); spine.set_linewidth(0.6)
            ax.grid(True, color=C_BORDER_SUBTLE, alpha=0.4,
                    linewidth=0.4, linestyle="--")

            if idx == 0:
                leg = ax.legend(fontsize=6, framealpha=0.6, loc="upper right")
                leg.get_frame().set_facecolor(C_BG_RAISED)
                leg.get_frame().set_edgecolor(C_BORDER_SUBTLE)
                for t in leg.get_texts():
                    t.set_color(C_TEXT2)

        # Hide unused axes in the grid
        for idx in range(n, nrows * ncols):
            axes[idx // ncols][idx % ncols].set_visible(False)

        self.overlay_fig.patch.set_facecolor(C_BG_BASE)
        try:
            self.overlay_fig.tight_layout(pad=0.9, h_pad=1.4, w_pad=0.9)
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
