# -*- coding: utf-8 -*-
"""
UPRSA Widget - Unassigned Peak Recovery & Spectral Attribution
src/gui/uprsa_widget.py

Provides UI for UPRSA two-category screening (Accepted PQI >= 0.60 vs Rejected PQI < 0.60):
- Automatically receives processed spectrum from Step 1, detected peaks from Step 2,
  and confirmed/assigned lines from Step 4.
- Tunable parameter controls (tolerance, window, guard, weights, threshold).
- 5 publication-ready diagnostic charts + 2 result tables.
- CSV and PNG export.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, List, Any
import numpy as np
import pandas as pd

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QFileDialog, QSplitter, QProgressBar, QScrollArea,
)
from PyQt6.QtGui import QFont, QColor
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from src import setup_logger
from src.config import UPRSA_PARAMS
from src.core.uprsa import UPRSAAnalyzer
from src.io.data_models import UPRSAResult, ProcessedSpectra, DetectedPeak
from src.io.file_reader import CSVReader
from src.gui.gui_utils import (
    HighDpiToolbar as NavigationToolbar2QT,
    style_toolbar,
    ParameterControl, WorkerThread, FileHistory,
    show_error, show_info,
    make_table_toolbar, on_copy_table_clicked,
    PeakHoverAnnotator,
)
from src.gui.theme import (
    primary_button_style, secondary_button_style, instruction_banner_style,
    step_title_font, summary_banner_style, progress_bar_style,
    C_BG_BASE, C_BG_RAISED, C_BORDER_SUBTLE, C_ACCENT, C_WARN, C_TEXT, C_TEXT2,
    C_TEXT_MUTED, get_chart_bg, get_chart_axes_bg, get_chart_text, get_chart_text2,
    get_chart_border, is_dark, L_ACCENT, L_TEXT_MUTED,
)
from src.gui.charts import ChartEngine, _style_legend
from src.gui.export_engine import export_uprsa_csv, export_uprsa_png

logger = setup_logger(__name__)


class UPRSAWidget(QWidget):
    """
    UI widget for Unassigned Peak Recovery and Spectral Attribution (UPRSA).
    """

    # Emitted after successful UPRSA analysis — carries UPRSAResult
    result_ready = pyqtSignal(object)

    def __init__(self, file_history=None, notes_panel=None):
        super().__init__()
        self.file_history = file_history
        self.notes_panel = notes_panel

        self.analyzer = UPRSAAnalyzer()
        self.uprsa_result: Optional[UPRSAResult] = None
        self.worker_thread: Optional[WorkerThread] = None

        # Data sources
        self._step1_data: Optional[Any] = None
        self._step2_peaks: Optional[Any] = None
        self._step4_winners: Optional[Any] = None

        # Paths for manual file loading fallback
        self._spectrum_path: Optional[Path] = None
        self._detected_path: Optional[Path] = None
        self._confirmed_path: Optional[Path] = None

        # Figures dictionary
        self._figures: Dict[str, Figure] = {}

        # Toolbars for theme updates
        self._toolbars: List[NavigationToolbar2QT] = []

        logger.info("Initializing UPRSA widget")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._create_left_panel(), stretch=0)
        main_layout.addWidget(self._create_right_panel(), stretch=1)
        self._show_placeholders()

    # ──────────────────────────────────────────────────────────────────────
    # Left Control Panel
    # ──────────────────────────────────────────────────────────────────────

    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Title
        self._title_label = QLabel("🔬 Unassigned Peak Recovery (UPRSA)")
        self._title_label.setStyleSheet(step_title_font(13))
        layout.addWidget(self._title_label)

        # Instructions banner
        self._instructions_label = QLabel(
            "Instructions:\n"
            "1. Receives Processed Spectrum (Step 1), Detected Peaks (Step 2), "
            "and Confirmed Lines (Step 4) automatically.\n"
            "2. Unassigned peaks are isolated by subtracting confirmed lines within tolerance.\n"
            "3. Computes Peak Quality Index (PQI):\n"
            "   • Local Median Background & MAD Noise (guard-band excluded)\n"
            "   • Local SNR & Continuous Prominence\n"
            "4. Classification:\n"
            "   • PQI ≥ 0.60: ACCEPTED (Suitable for secondary identification)\n"
            "   • PQI < 0.60: REJECTED (Insufficient spectral quality / noise)"
        )
        self._instructions_label.setStyleSheet(instruction_banner_style())
        self._instructions_label.setWordWrap(True)
        layout.addWidget(self._instructions_label)

        # Data sources status group
        sources_group = QGroupBox("Data Sources")
        s_layout = QVBoxLayout(sources_group)
        s_layout.setSpacing(4)

        self._lbl_source_s1 = QLabel("Spectrum: Not loaded")
        self._lbl_source_s1.setStyleSheet(f"color: {C_TEXT_MUTED}; font-size: 11px;")
        s_layout.addWidget(self._lbl_source_s1)

        self._lbl_source_s2 = QLabel("Detected Peaks: Not loaded")
        self._lbl_source_s2.setStyleSheet(f"color: {C_TEXT_MUTED}; font-size: 11px;")
        s_layout.addWidget(self._lbl_source_s2)

        self._lbl_source_s4 = QLabel("Confirmed Lines: Not loaded")
        self._lbl_source_s4.setStyleSheet(f"color: {C_TEXT_MUTED}; font-size: 11px;")
        s_layout.addWidget(self._lbl_source_s4)

        btn_row_load = QHBoxLayout()
        self.btn_load_manual = QPushButton("Load Files Manually…")
        self.btn_load_manual.setStyleSheet(secondary_button_style())
        self.btn_load_manual.clicked.connect(self._on_load_files_clicked)
        btn_row_load.addWidget(self.btn_load_manual)
        s_layout.addLayout(btn_row_load)

        layout.addWidget(sources_group)

        # Tunable parameters group
        params_group = QGroupBox("UPRSA Parameters")
        p_layout = QVBoxLayout(params_group)
        p_layout.setSpacing(6)

        self.tol_ctrl = ParameterControl(
            "Wavelength Tolerance (nm)",
            0.01, 0.50,
            float(UPRSA_PARAMS["WAVELENGTH_TOLERANCE"]),
            0.01, 3
        )
        p_layout.addWidget(self.tol_ctrl)

        self.window_ctrl = ParameterControl(
            "Local Window (± nm)",
            0.5, 10.0,
            float(UPRSA_PARAMS["LOCAL_WINDOW"]),
            0.5, 1
        )
        p_layout.addWidget(self.window_ctrl)

        self.guard_ctrl = ParameterControl(
            "Peak Guard Band (± nm)",
            0.01, 0.50,
            float(UPRSA_PARAMS["PEAK_GUARD"]),
            0.01, 3
        )
        p_layout.addWidget(self.guard_ctrl)

        self.threshold_ctrl = ParameterControl(
            "Acceptance Threshold (PQI)",
            0.10, 0.95,
            float(UPRSA_PARAMS["ACCEPTANCE_THRESHOLD"]),
            0.05, 2
        )
        p_layout.addWidget(self.threshold_ctrl)

        # Weight controls in a sub-group
        weights_group = QGroupBox("PQI Weighting (Sum = 1.0)")
        w_layout = QVBoxLayout(weights_group)
        self.w_int_ctrl = ParameterControl("Weight: Intensity", 0.0, 1.0, float(UPRSA_PARAMS["WEIGHT_INTENSITY"]), 0.05, 2)
        self.w_snr_ctrl = ParameterControl("Weight: Local SNR", 0.0, 1.0, float(UPRSA_PARAMS["WEIGHT_SNR"]), 0.05, 2)
        self.w_prom_ctrl = ParameterControl("Weight: Prominence", 0.0, 1.0, float(UPRSA_PARAMS["WEIGHT_PROMINENCE"]), 0.05, 2)
        w_layout.addWidget(self.w_int_ctrl)
        w_layout.addWidget(self.w_snr_ctrl)
        w_layout.addWidget(self.w_prom_ctrl)
        p_layout.addWidget(weights_group)

        layout.addWidget(params_group)

        # Summary KPIs Banner
        self.summary_banner = QLabel("Ready to analyze unassigned peaks")
        self.summary_banner.setStyleSheet(summary_banner_style())
        self.summary_banner.setWordWrap(True)
        layout.addWidget(self.summary_banner)

        # Action Buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(6)

        self.analyze_button = QPushButton("Run UPRSA Analysis")
        self.analyze_button.setStyleSheet(primary_button_style())
        self.analyze_button.clicked.connect(self._on_run_clicked)
        btn_layout.addWidget(self.analyze_button)

        exp_row = QHBoxLayout()
        self.export_csv_btn = QPushButton("Export CSVs")
        self.export_csv_btn.setEnabled(False)
        self.export_csv_btn.setStyleSheet(secondary_button_style())
        self.export_csv_btn.clicked.connect(self._on_export_csv_clicked)
        exp_row.addWidget(self.export_csv_btn)

        self.export_png_btn = QPushButton("Export PNGs")
        self.export_png_btn.setEnabled(False)
        self.export_png_btn.setStyleSheet(secondary_button_style())
        self.export_png_btn.clicked.connect(self._on_export_png_clicked)
        exp_row.addWidget(self.export_png_btn)
        btn_layout.addLayout(exp_row)

        self.btn_reset = QPushButton("Reset to Defaults")
        self.btn_reset.setStyleSheet(secondary_button_style())
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        btn_layout.addWidget(self.btn_reset)

        layout.addLayout(btn_layout)

        # Info & Progress
        self.info_label = QLabel("Awaiting input data")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setStyleSheet(progress_bar_style())
        self.progress_bar.setMaximumHeight(8)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        layout.addStretch()
        panel.setMaximumWidth(360)

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setMaximumWidth(370)
        return scroll

    # ──────────────────────────────────────────────────────────────────────
    # Right Visualization & Results Panel
    # ──────────────────────────────────────────────────────────────────────

    def _create_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        self.tabs = QTabWidget()

        # Tab 1: Accepted Spectrum Overview
        tab1, self.fig_overview, self.canvas_overview = self._create_chart_tab()
        self._figures["accepted_overview"] = self.fig_overview
        self._hover_overview = PeakHoverAnnotator(
            self.canvas_overview, radius_px=14.0, x_unit="nm", x_name="Wavelength", y_name="Intensity"
        )
        self.tabs.addTab(tab1, "🌟 Accepted Peaks Spectrum")

        # Tab 2: Accepted & Representative Rejected
        tab2, self.fig_comparison, self.canvas_comparison = self._create_chart_tab()
        self._figures["accepted_rejected"] = self.fig_comparison
        self._hover_comparison = PeakHoverAnnotator(
            self.canvas_comparison, radius_px=14.0, x_unit="nm", x_name="Wavelength", y_name="Intensity"
        )
        self.tabs.addTab(tab2, "⚖ Accepted vs Rejected")

        # Tab 3: PQI Distribution Histogram
        tab3, self.fig_hist, self.canvas_hist = self._create_chart_tab()
        self._figures["pqi_distribution"] = self.fig_hist
        self.tabs.addTab(tab3, "📊 PQI Distribution")

        # Tab 4: Quality Space Map (SNR vs Prominence)
        tab4, self.fig_map, self.canvas_map = self._create_chart_tab()
        self._figures["quality_map"] = self.fig_map
        self._hover_map = PeakHoverAnnotator(
            self.canvas_map, radius_px=14.0, x_unit="", y_unit="", x_name="Local SNR", y_name="Norm Prom"
        )
        self.tabs.addTab(tab4, "🗺 Quality Map")

        # Tab 5: Representative Line Profiles (3 subplots)
        tab5, self.fig_profiles, self.canvas_profiles = self._create_chart_tab()
        self._figures["line_profiles"] = self.fig_profiles
        self.tabs.addTab(tab5, "🔍 Line Profiles")

        # Tab 6: Accepted Peaks Table
        tab6 = QWidget()
        t6_layout = QVBoxLayout(tab6)
        self.table_accepted = self._create_peaks_table()
        container6, self._btn_copy_acc, self._lbl_count_acc = make_table_toolbar(self.table_accepted, row_label_text="0 rows")
        self._btn_copy_acc.clicked.connect(lambda: on_copy_table_clicked(self.table_accepted, self._btn_copy_acc, self._lbl_count_acc))
        t6_layout.addWidget(container6)
        self.tabs.addTab(tab6, "✅ Accepted Table")

        # Tab 7: All Unassigned Table
        tab7 = QWidget()
        t7_layout = QVBoxLayout(tab7)
        self.table_all = self._create_peaks_table()
        container7, self._btn_copy_all, self._lbl_count_all = make_table_toolbar(self.table_all, row_label_text="0 rows")
        self._btn_copy_all.clicked.connect(lambda: on_copy_table_clicked(self.table_all, self._btn_copy_all, self._lbl_count_all))
        t7_layout.addWidget(container7)
        self.tabs.addTab(tab7, "📋 All Unassigned Table")

        layout.addWidget(self.tabs)
        return panel

    def _create_chart_tab(self) -> tuple[QWidget, Figure, FigureCanvasQTAgg]:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        chart_bg = get_chart_bg()
        fig = Figure(facecolor=chart_bg)
        canvas = FigureCanvasQTAgg(fig)
        canvas.setStyleSheet(f"background-color: {chart_bg};")
        toolbar = NavigationToolbar2QT(canvas, container)
        style_toolbar(toolbar)
        self._toolbars.append(toolbar)

        layout.addWidget(toolbar)
        layout.addWidget(canvas)
        return container, fig, canvas

    def _create_peaks_table(self) -> QTableWidget:
        table = QTableWidget()
        cols = [
            "ID", "Wavelength (nm)", "Intensity", "Background", "Noise",
            "Signal", "SNR", "Prominence", "PQI", "Decision"
        ]
        table.setColumnCount(len(cols))
        table.setHorizontalHeaderLabels(cols)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    # ──────────────────────────────────────────────────────────────────────
    # Auto-Handoff Loaders
    # ──────────────────────────────────────────────────────────────────────

    def load_from_step1(self, processed_data: ProcessedSpectra) -> None:
        """Receive processed spectra from Step 1."""
        if processed_data is None:
            return
        self._step1_data = processed_data
        n_pts = len(processed_data.wavelength) if hasattr(processed_data, "wavelength") else 0
        accent = C_ACCENT if is_dark() else L_ACCENT
        self._lbl_source_s1.setText(f"Spectrum: ✅ Step 1 ({n_pts:,} pts)")
        self._lbl_source_s1.setStyleSheet(f"color: {accent}; font-size: 11px; font-weight: bold;")
        self.info_label.setText("Processed spectrum loaded from Step 1")
        logger.info("UPRSA received Step 1 data")

    def load_from_step2(self, detected_peaks: List[DetectedPeak]) -> None:
        """Receive detected peaks from Step 2."""
        if not detected_peaks:
            return
        self._step2_peaks = detected_peaks
        n_peaks = len(detected_peaks)
        accent = C_ACCENT if is_dark() else L_ACCENT
        self._lbl_source_s2.setText(f"Detected Peaks: ✅ Step 2 ({n_peaks} peaks)")
        self._lbl_source_s2.setStyleSheet(f"color: {accent}; font-size: 11px; font-weight: bold;")
        self.info_label.setText(f"{n_peaks} detected peaks loaded from Step 2")
        logger.info("UPRSA received Step 2 data")

    def load_from_step4(self, analysis_results: dict) -> None:
        """Receive winner lines from Step 4."""
        if not analysis_results:
            return
        winners_df = analysis_results.get("winner_lines")
        self._step4_winners = winners_df
        n_win = len(winners_df) if isinstance(winners_df, pd.DataFrame) else 0
        accent = C_ACCENT if is_dark() else L_ACCENT
        self._lbl_source_s4.setText(f"Confirmed Lines: ✅ Step 4 ({n_win} winners)")
        self._lbl_source_s4.setStyleSheet(f"color: {accent}; font-size: 11px; font-weight: bold;")
        self.info_label.setText(f"{n_win} winning lines loaded from Step 4. Ready to run UPRSA.")
        logger.info("UPRSA received Step 4 data")

    # ──────────────────────────────────────────────────────────────────────
    # Manual File Loading Fallback
    # ──────────────────────────────────────────────────────────────────────

    def _on_load_files_clicked(self):
        """Allow user to manually pick files if not using pipeline auto-handoff."""
        # 1. Processed spectrum
        s_path, _ = QFileDialog.getOpenFileName(
            self, "Select Processed Spectrum CSV (Step 1)", "", "CSV Files (*.csv)"
        )
        if not s_path:
            return
        reader = CSVReader()
        try:
            self._step1_data = reader.read_raw_spectrum(s_path)
            self._lbl_source_s1.setText(f"Spectrum: {Path(s_path).name}")
            self._lbl_source_s1.setStyleSheet(f"color: {C_ACCENT}; font-size: 11px;")
        except Exception as e:
            show_error("Load Error", f"Failed to load spectrum: {e}")
            return

        # 2. Detected peaks
        p_path, _ = QFileDialog.getOpenFileName(
            self, "Select Detected Peaks CSV (Step 2)", "", "CSV Files (*.csv)"
        )
        if p_path:
            try:
                self._step2_peaks = reader.read_detected_peaks(p_path)
                self._lbl_source_s2.setText(f"Detected: {Path(p_path).name}")
                self._lbl_source_s2.setStyleSheet(f"color: {C_ACCENT}; font-size: 11px;")
            except Exception as e:
                show_error("Load Error", f"Failed to load detected peaks: {e}")

        # 3. Confirmed peaks
        c_path, _ = QFileDialog.getOpenFileName(
            self, "Select Confirmed Lines CSV (Step 4 Winners or custom)", "", "CSV Files (*.csv)"
        )
        if c_path:
            try:
                self._step4_winners = pd.read_csv(c_path)
                self._lbl_source_s4.setText(f"Confirmed: {Path(c_path).name}")
                self._lbl_source_s4.setStyleSheet(f"color: {C_ACCENT}; font-size: 11px;")
            except Exception as e:
                show_error("Load Error", f"Failed to load confirmed lines: {e}")

    # ──────────────────────────────────────────────────────────────────────
    # Analysis Execution
    # ──────────────────────────────────────────────────────────────────────

    def _on_reset_clicked(self):
        """Reset parameter controls to default values from UPRSA_PARAMS."""
        self.tol_ctrl.set_value(float(UPRSA_PARAMS["WAVELENGTH_TOLERANCE"]))
        self.window_ctrl.set_value(float(UPRSA_PARAMS["LOCAL_WINDOW"]))
        self.guard_ctrl.set_value(float(UPRSA_PARAMS["PEAK_GUARD"]))
        self.threshold_ctrl.set_value(float(UPRSA_PARAMS["ACCEPTANCE_THRESHOLD"]))
        self.w_int_ctrl.set_value(float(UPRSA_PARAMS["WEIGHT_INTENSITY"]))
        self.w_snr_ctrl.set_value(float(UPRSA_PARAMS["WEIGHT_SNR"]))
        self.w_prom_ctrl.set_value(float(UPRSA_PARAMS["WEIGHT_PROMINENCE"]))

    def _on_run_clicked(self):
        """Run UPRSA analysis in background worker thread."""
        if self._step1_data is None:
            show_error("Missing Spectrum", "Please run Step 1 or load a processed spectrum CSV.")
            return

        if self._step2_peaks is None:
            show_error("Missing Detected Peaks", "Please run Step 2 or load detected peaks.")
            return

        config = {
            "WAVELENGTH_TOLERANCE": self.tol_ctrl.value(),
            "LOCAL_WINDOW": self.window_ctrl.value(),
            "PEAK_GUARD": self.guard_ctrl.value(),
            "ACCEPTANCE_THRESHOLD": self.threshold_ctrl.value(),
            "WEIGHT_INTENSITY": self.w_int_ctrl.value(),
            "WEIGHT_SNR": self.w_snr_ctrl.value(),
            "WEIGHT_PROMINENCE": self.w_prom_ctrl.value(),
        }
        self.analyzer = UPRSAAnalyzer(config)

        self.analyze_button.setEnabled(False)
        self.progress_bar.show()
        self.info_label.setText("Evaluating unassigned peaks with UPRSA…")

        self.worker_thread = WorkerThread(
            self.analyzer.analyze,
            self._step1_data,
            self._step2_peaks,
            self._step4_winners
        )
        self.worker_thread.finished.connect(self._on_analysis_finished)
        self.worker_thread.error.connect(self._on_analysis_error)
        self.worker_thread.start()

    def _on_analysis_error(self, err_msg: str):
        self.analyze_button.setEnabled(True)
        self.progress_bar.hide()
        show_error("UPRSA Error", f"Analysis failed: {err_msg}")
        self.info_label.setText(f"Error: {err_msg}")

    def _on_analysis_finished(self, result: dict):
        self.analyze_button.setEnabled(True)
        self.progress_bar.hide()

        uprsa_res = result.get("result")
        if uprsa_res is None or not isinstance(uprsa_res, UPRSAResult):
            show_error("UPRSA Failed", "Analysis did not return valid results.")
            return

        self.uprsa_result = uprsa_res
        self.export_csv_btn.setEnabled(True)
        self.export_png_btn.setEnabled(True)

        self._update_kpi_banner()
        self._populate_tables()
        self._render_charts()

        self.info_label.setText(
            f"Done: {uprsa_res.unassigned_count} unassigned peaks analyzed → "
            f"{uprsa_res.accepted_count} Accepted, {uprsa_res.rejected_count} Rejected."
        )

        if self.notes_panel:
            self.notes_panel.add_note(
                f"UPRSA complete: {uprsa_res.accepted_count} of {uprsa_res.unassigned_count} "
                f"unassigned peaks accepted for secondary identification ({uprsa_res.accepted_percentage:.1f}%)",
                "SUCCESS"
            )

        # Notify downstream
        self.result_ready.emit(self.uprsa_result)

    def _update_kpi_banner(self):
        if self.uprsa_result is None:
            return
        res = self.uprsa_result
        text = (
            f"Detected: {res.detected_count}  |  Confirmed: {res.confirmed_count}  |  Unassigned: {res.unassigned_count}\n"
            f"✅ Accepted: {res.accepted_count} ({res.accepted_percentage:.1f}%)   "
            f"❌ Rejected: {res.rejected_count} ({res.rejected_percentage:.1f}%)   "
            f"(Threshold: PQI ≥ {self.threshold_ctrl.value():.2f})"
        )
        self.summary_banner.setText(text)

    # ──────────────────────────────────────────────────────────────────────
    # Data & Table Renderers
    # ──────────────────────────────────────────────────────────────────────

    def _populate_tables(self):
        if self.uprsa_result is None:
            return

        # Accepted table
        self._fill_table(self.table_accepted, self.uprsa_result.df_accepted)
        n_acc = len(self.uprsa_result.df_accepted)
        self._lbl_count_acc.setText(f"{n_acc} row{'s' if n_acc != 1 else ''}")
        self._btn_copy_acc.setEnabled(n_acc > 0)

        # All unassigned table
        self._fill_table(self.table_all, self.uprsa_result.df_all)
        n_all = len(self.uprsa_result.df_all)
        self._lbl_count_all.setText(f"{n_all} row{'s' if n_all != 1 else ''}")
        self._btn_copy_all.setEnabled(n_all > 0)

    def _fill_table(self, table: QTableWidget, df: pd.DataFrame):
        table.setRowCount(0)
        if df is None or df.empty:
            return
        table.setRowCount(len(df))
        for r_idx, (_, row) in enumerate(df.iterrows()):
            table.setItem(r_idx, 0, QTableWidgetItem(str(int(row.get("UPRSA_Peak_ID", r_idx + 1)))))
            table.setItem(r_idx, 1, QTableWidgetItem(f"{row['Wavelength']:.3f}"))
            table.setItem(r_idx, 2, QTableWidgetItem(f"{row['Intensity']:.2f}"))
            table.setItem(r_idx, 3, QTableWidgetItem(f"{row['Local_Background']:.2f}"))
            table.setItem(r_idx, 4, QTableWidgetItem(f"{row['Local_Noise']:.2f}"))
            table.setItem(r_idx, 5, QTableWidgetItem(f"{row['Signal']:.2f}"))
            table.setItem(r_idx, 6, QTableWidgetItem(f"{row['SNR']:.2f}"))
            table.setItem(r_idx, 7, QTableWidgetItem(f"{row['Prominence']:.2f}"))
            table.setItem(r_idx, 8, QTableWidgetItem(f"{row['PQI']:.3f}"))
            dec_item = QTableWidgetItem(str(row["Decision"]))
            if row["Decision"] == "Accepted":
                dec_item.setForeground(QColor("#4CAF50"))
            else:
                dec_item.setForeground(QColor("#F44336"))
            table.setItem(r_idx, 9, dec_item)

    # ──────────────────────────────────────────────────────────────────────
    # Theme & Placeholders
    # ──────────────────────────────────────────────────────────────────────

    def _show_placeholders(self) -> None:
        """Display clean themed placeholder on all 5 diagnostic figure canvases."""
        if hasattr(self, "_hover_overview"):
            self._hover_overview.detach()
        if hasattr(self, "_hover_comparison"):
            self._hover_comparison.detach()
        if hasattr(self, "_hover_map"):
            self._hover_map.detach()

        chart_bg = get_chart_bg()
        items = [
            (self.fig_overview, self.canvas_overview, "No data — run UPRSA analysis"),
            (self.fig_comparison, self.canvas_comparison, "No data — run UPRSA analysis"),
            (self.fig_hist, self.canvas_hist, "No data — run UPRSA analysis"),
            (self.fig_map, self.canvas_map, "No data — run UPRSA analysis"),
            (self.fig_profiles, self.canvas_profiles, "No data — run UPRSA analysis"),
        ]
        for fig, canvas, msg in items:
            fig.clear()
            fig.patch.set_facecolor(chart_bg)
            canvas.setStyleSheet(f"background-color: {chart_bg};")
            ax = fig.add_subplot(111)
            ChartEngine._show_placeholder(ax, msg)
            ChartEngine.apply_dark_style(fig, ax)
            canvas.draw()

    def apply_theme(self) -> None:
        """Update inline styles, label colours, and chart backgrounds for active theme."""
        chart_bg = get_chart_bg()

        self._title_label.setStyleSheet(step_title_font(13))
        self._instructions_label.setStyleSheet(instruction_banner_style())
        self.summary_banner.setStyleSheet(summary_banner_style())
        self.btn_load_manual.setStyleSheet(secondary_button_style())
        self.analyze_button.setStyleSheet(primary_button_style())
        self.export_csv_btn.setStyleSheet(secondary_button_style())
        self.export_png_btn.setStyleSheet(secondary_button_style())
        self.btn_reset.setStyleSheet(secondary_button_style())

        muted = C_TEXT_MUTED if is_dark() else L_TEXT_MUTED
        accent = C_ACCENT if is_dark() else L_ACCENT

        if self._step1_data is None:
            self._lbl_source_s1.setStyleSheet(f"color: {muted}; font-size: 11px;")
        else:
            self._lbl_source_s1.setStyleSheet(f"color: {accent}; font-size: 11px; font-weight: bold;")

        if self._step2_peaks is None:
            self._lbl_source_s2.setStyleSheet(f"color: {muted}; font-size: 11px;")
        else:
            self._lbl_source_s2.setStyleSheet(f"color: {accent}; font-size: 11px; font-weight: bold;")

        if self._step4_winners is None:
            self._lbl_source_s4.setStyleSheet(f"color: {muted}; font-size: 11px;")
        else:
            self._lbl_source_s4.setStyleSheet(f"color: {accent}; font-size: 11px; font-weight: bold;")

        for tb in self._toolbars:
            style_toolbar(tb)

        for fig, canvas in [
            (self.fig_overview, self.canvas_overview),
            (self.fig_comparison, self.canvas_comparison),
            (self.fig_hist, self.canvas_hist),
            (self.fig_map, self.canvas_map),
            (self.fig_profiles, self.canvas_profiles),
        ]:
            fig.patch.set_facecolor(chart_bg)
            canvas.setStyleSheet(f"background-color: {chart_bg};")

        if hasattr(self, "_hover_overview"):
            self._hover_overview.update_theme()
        if hasattr(self, "_hover_comparison"):
            self._hover_comparison.update_theme()
        if hasattr(self, "_hover_map"):
            self._hover_map.update_theme()

        if self.uprsa_result is not None and self._step1_data is not None:
            self._render_charts()
        else:
            self._show_placeholders()

    # ──────────────────────────────────────────────────────────────────────
    # Chart Renderers (Faithfully matching unassigned_peaks_1.py)
    # ──────────────────────────────────────────────────────────────────────

    def _render_charts(self):
        if self.uprsa_result is None or self._step1_data is None:
            return

        # Extract spectrum array
        if isinstance(self._step1_data, ProcessedSpectra):
            spec_wl = np.asarray(self._step1_data.wavelength, dtype=float)
            spec_int = np.asarray(self._step1_data.corrected, dtype=float)
        elif isinstance(self._step1_data, pd.DataFrame):
            spec_wl = self._step1_data.iloc[:, 0].to_numpy(dtype=float)
            spec_int = self._step1_data.iloc[:, 1].to_numpy(dtype=float)
        elif hasattr(self._step1_data, "wavelength") and hasattr(self._step1_data, "intensity"):
            spec_wl = np.asarray(self._step1_data.wavelength, dtype=float)
            spec_int = np.asarray(self._step1_data.intensity, dtype=float)
        else:
            return

        df_acc = self.uprsa_result.df_accepted
        df_rej = self.uprsa_result.df_rejected
        thresh = self.threshold_ctrl.value()

        # ── 1. Accepted Overview ──────────────────────────────────────────
        self.fig_overview.clear()
        self.fig_overview.patch.set_facecolor(get_chart_bg())
        self.canvas_overview.setStyleSheet(f"background-color: {get_chart_bg()};")
        ax1 = self.fig_overview.add_subplot(111)
        ax1.plot(spec_wl, spec_int, color=get_chart_text2(), alpha=0.7, linewidth=1.0, label="Processed SG–ALS spectrum")
        if len(df_acc) > 0:
            ax1.scatter(df_acc["Wavelength"], df_acc["Intensity"], color="#4CAF50", edgecolor="black", s=65, zorder=5, label=f"Accepted peaks (n={len(df_acc)})")
            # Label top 15 highest PQI
            top15 = df_acc.nlargest(min(15, len(df_acc)), "PQI")
            for _, r in top15.iterrows():
                ax1.annotate(f"{r['Wavelength']:.2f}", (r["Wavelength"], r["Intensity"]), xytext=(4, 6), textcoords="offset points", fontsize=8, fontweight="bold", color=get_chart_text())
        ax1.set_xlabel("Wavelength (nm)")
        ax1.set_ylabel("Intensity (a.u.)")
        ax1.set_title("UPRSA: All Accepted Unassigned Peaks", fontweight="bold")
        ax1.legend(loc="upper right")
        _style_legend(ax1)
        ChartEngine.apply_dark_style(self.fig_overview, ax1)
        if len(df_acc) > 0:
            extra_acc = [f"PQI: {r['PQI']:.3f} | SNR: {r['SNR']:.1f}" for _, r in df_acc.iterrows()]
            self._hover_overview.attach(ax1, df_acc["Wavelength"].to_numpy(), df_acc["Intensity"].to_numpy(), extra_info=extra_acc)
        else:
            self._hover_overview.detach()
        self.canvas_overview.draw()

        # ── 2. Accepted & Representative Rejected ─────────────────────────
        self.fig_comparison.clear()
        self.fig_comparison.patch.set_facecolor(get_chart_bg())
        self.canvas_comparison.setStyleSheet(f"background-color: {get_chart_bg()};")
        ax2 = self.fig_comparison.add_subplot(111)
        ax2.plot(spec_wl, spec_int, color=get_chart_text2(), alpha=0.6, linewidth=1.0, label="Processed spectrum")
        if len(df_acc) > 0:
            ax2.scatter(df_acc["Wavelength"], df_acc["Intensity"], color="#4CAF50", edgecolor="black", s=65, zorder=5, label=f"Accepted (all, n={len(df_acc)})")
        if len(df_rej) > 0:
            num_rej_to_plot = min(int(UPRSA_PARAMS["NUMBER_OF_REJECTED_TO_PLOT"]), len(df_rej))
            rej_sorted = df_rej.sort_values("Wavelength").reset_index(drop=True)
            sel_idx = np.linspace(0, len(rej_sorted) - 1, num_rej_to_plot).astype(int)
            rej_sample = rej_sorted.iloc[sel_idx]
            ax2.scatter(rej_sample["Wavelength"], rej_sample["Intensity"], color="#F44336", marker="x", s=80, linewidth=1.8, zorder=6, label=f"Representative rejected (n={len(rej_sample)})")
            for _, r in rej_sample.iterrows():
                ax2.annotate(f"{r['Wavelength']:.2f}", (r["Wavelength"], r["Intensity"]), xytext=(4, -12), textcoords="offset points", fontsize=7, color="#F44336")
        ax2.set_xlabel("Wavelength (nm)")
        ax2.set_ylabel("Intensity (a.u.)")
        ax2.set_title("UPRSA: Accepted vs Representative Rejected Peaks", fontweight="bold")
        ax2.legend(loc="upper right")
        _style_legend(ax2)
        ChartEngine.apply_dark_style(self.fig_comparison, ax2)
        all_wl = []
        all_int = []
        all_extra = []
        if len(df_acc) > 0:
            all_wl.extend(df_acc["Wavelength"].tolist())
            all_int.extend(df_acc["Intensity"].tolist())
            all_extra.extend([f"Decision: Accepted | PQI: {r['PQI']:.3f}" for _, r in df_acc.iterrows()])
        if len(df_rej) > 0:
            all_wl.extend(rej_sample["Wavelength"].tolist())
            all_int.extend(rej_sample["Intensity"].tolist())
            all_extra.extend([f"Decision: Rejected | PQI: {r['PQI']:.3f}" for _, r in rej_sample.iterrows()])
        if all_wl:
            self._hover_comparison.attach(ax2, np.array(all_wl), np.array(all_int), extra_info=all_extra)
        else:
            self._hover_comparison.detach()
        self.canvas_comparison.draw()

        # ── 3. PQI Histogram ──────────────────────────────────────────────
        self.fig_hist.clear()
        self.fig_hist.patch.set_facecolor(get_chart_bg())
        self.canvas_hist.setStyleSheet(f"background-color: {get_chart_bg()};")
        ax3 = self.fig_hist.add_subplot(111)
        if len(df_acc) > 0:
            ax3.hist(df_acc["PQI"], bins=15, color="#4CAF50", alpha=0.65, label=f"Accepted (n={len(df_acc)})")
        if len(df_rej) > 0:
            ax3.hist(df_rej["PQI"], bins=15, color="#F44336", alpha=0.55, label=f"Rejected (n={len(df_rej)})")
        thresh_color = C_ACCENT if is_dark() else L_ACCENT
        ax3.axvline(thresh, color=thresh_color, linestyle="--", linewidth=2.0, label=f"Threshold = {thresh:.2f}")
        ax3.set_xlabel("Peak Quality Index (PQI)")
        ax3.set_ylabel("Number of Peaks")
        ax3.set_title("UPRSA Peak Quality Distribution", fontweight="bold")
        ax3.legend(loc="upper right")
        _style_legend(ax3)
        ChartEngine.apply_dark_style(self.fig_hist, ax3)
        self.canvas_hist.draw()

        # ── 4. Quality Map ────────────────────────────────────────────────
        self.fig_map.clear()
        self.fig_map.patch.set_facecolor(get_chart_bg())
        self.canvas_map.setStyleSheet(f"background-color: {get_chart_bg()};")
        ax4 = self.fig_map.add_subplot(111)
        if len(df_acc) > 0:
            ax4.scatter(df_acc["SNR"], df_acc["Prominence_Normalized"], color="#4CAF50", s=65, alpha=0.8, label=f"Accepted (n={len(df_acc)})")
        if len(df_rej) > 0:
            ax4.scatter(df_rej["SNR"], df_rej["Prominence_Normalized"], color="#F44336", marker="x", s=65, alpha=0.8, label=f"Rejected (n={len(df_rej)})")
        ax4.set_xlabel("Local SNR")
        ax4.set_ylabel("Normalized Prominence")
        ax4.set_title("UPRSA Spectral Quality Separation", fontweight="bold")
        ax4.legend(loc="upper right")
        _style_legend(ax4)
        ChartEngine.apply_dark_style(self.fig_map, ax4)
        map_x = []
        map_y = []
        map_extra = []
        if len(df_acc) > 0:
            map_x.extend(df_acc["SNR"].tolist())
            map_y.extend(df_acc["Prominence_Normalized"].tolist())
            map_extra.extend([f"Status: Accepted | λ: {r['Wavelength']:.2f} nm | PQI: {r['PQI']:.3f}" for _, r in df_acc.iterrows()])
        if len(df_rej) > 0:
            map_x.extend(df_rej["SNR"].tolist())
            map_y.extend(df_rej["Prominence_Normalized"].tolist())
            map_extra.extend([f"Status: Rejected | λ: {r['Wavelength']:.2f} nm | PQI: {r['PQI']:.3f}" for _, r in df_rej.iterrows()])
        if map_x:
            self._hover_map.attach(ax4, np.array(map_x), np.array(map_y), extra_info=map_extra)
        else:
            self._hover_map.detach()
        self.canvas_map.draw()

        # ── 5. Representative Line Profiles ───────────────────────────────
        self.fig_profiles.clear()
        self.fig_profiles.patch.set_facecolor(get_chart_bg())
        self.canvas_profiles.setStyleSheet(f"background-color: {get_chart_bg()};")
        axes = self.fig_profiles.subplots(3, 1)

        sel_accepted = df_acc.iloc[0] if len(df_acc) > 0 else None
        sel_boundary = df_rej.sort_values("PQI", ascending=False).iloc[0] if len(df_rej) > 0 else None
        sel_low = df_rej.sort_values("PQI", ascending=True).iloc[0] if len(df_rej) > 0 else None

        items = [
            (axes[0], sel_accepted, "(a) Highest-PQI Accepted Peak", "Accepted"),
            (axes[1], sel_boundary, "(b) Boundary Rejected Peak (Nearest Threshold)", "Rejected"),
            (axes[2], sel_low, "(c) Low-PQI Rejected Peak", "Rejected"),
        ]

        for ax, row, title, dec in items:
            if row is None:
                ChartEngine._show_placeholder(ax, "No data available")
                ChartEngine.apply_dark_style(self.fig_profiles, ax)
                continue
            wl = float(row["Wavelength"])
            int_val = float(row["Intensity"])
            bg = float(row["Local_Background"])
            noise = float(row["Local_Noise"])
            snr = float(row["SNR"])
            pqi = float(row["PQI"])

            # Local slice
            mask = (spec_wl >= wl - 2.0) & (spec_wl <= wl + 2.0)
            sub_wl = spec_wl[mask]
            sub_int = spec_int[mask]

            ax.plot(sub_wl, sub_int, color=get_chart_text2(), linewidth=1.5, label="Spectrum")
            ax.axhline(bg, color="#2196F3", linestyle="--", linewidth=1.2, label="Background")
            ax.fill_between(sub_wl, bg - noise, bg + noise, color="gray", alpha=0.2, label="Background ± Noise")
            pt_color = "#4CAF50" if dec == "Accepted" else "#F44336"
            ax.scatter([wl], [int_val], color=pt_color, edgecolor="black", s=85, zorder=5, label=dec)
            ax.axvline(wl, color=pt_color, linestyle=":", alpha=0.6)

            param_text = f"λ: {wl:.2f} nm\nSNR: {snr:.1f}\nPQI: {pqi:.3f}\nDecision: {dec}"
            ax.text(0.02, 0.95, param_text, transform=ax.transAxes, va="top", ha="left", fontsize=8, color=get_chart_text(), bbox=dict(boxstyle="round", facecolor=get_chart_axes_bg(), edgecolor=get_chart_border(), alpha=0.85))
            ax.set_title(title, fontsize=10, fontweight="bold")
            ax.legend(loc="upper right", fontsize=8)
            _style_legend(ax)
            ChartEngine.apply_dark_style(self.fig_profiles, ax)

        self.fig_profiles.tight_layout()
        self.canvas_profiles.draw()

    # ──────────────────────────────────────────────────────────────────────
    # Export Actions
    # ──────────────────────────────────────────────────────────────────────

    def _on_export_csv_clicked(self):
        if self.uprsa_result is None:
            return
        directory = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if not directory:
            return
        try:
            paths = export_uprsa_csv(self.uprsa_result, Path(directory))
            show_info("Export Complete", "UPRSA CSV files exported:\n" + "\n".join(str(p) for p in paths))
        except Exception as e:
            show_error("Export Failed", f"Could not save CSV files: {e}")

    def _on_export_png_clicked(self):
        if not self._figures:
            return
        directory = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if not directory:
            return
        try:
            paths = export_uprsa_png(self._figures, Path(directory))
            show_info("Export Complete", "UPRSA figures exported:\n" + "\n".join(str(p) for p in paths))
        except Exception as e:
            show_error("Export Failed", f"Could not save figures: {e}")
