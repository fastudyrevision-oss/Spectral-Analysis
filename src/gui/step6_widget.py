# -*- coding: utf-8 -*-
"""
Step 6 Widget - Model Performance Metrics

Two-column layout mirroring Step 5:
  Left  (scrollable, ≤370 px): title, status banner, action buttons,
                                 export buttons, info label, progress bar.
  Right (stretch): QTabWidget with four chart tabs (Fig 7, 11, 12, 14)
                   above a QSplitter-mounted summary QTableWidget.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QScrollArea, QTabWidget, QProgressBar, QFileDialog,
)
from PyQt6.QtGui import QFont, QColor
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from src import setup_logger
from src.core.step6_performance import PerformanceCalculator
from src.gui.charts import ChartEngine
from src.gui.export_engine import export_step6_csv, export_step6_png, generate_pdf_report
from src.gui.gui_utils import WorkerThread, show_error, show_info
from src.gui.theme import (
    primary_button_style, secondary_button_style, step_title_font, summary_banner_style,
    progress_bar_style, instruction_banner_style,
    C_SUCCESS, C_WARN, C_ERROR, C_TEXT, C_TEXT2,
    get_chart_bg,
)

logger = setup_logger(__name__)


class Step6Widget(QWidget):
    """
    UI widget for Step 6: Model Performance Metrics.

    Reads results from Steps 1–5, computes performance metrics via
    :class:`PerformanceCalculator`, and displays four scientific charts
    plus a summary table.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        step2_tab,
        step3_tab,
        step4_tab,
        step5_tab,
        step1_tab=None,
        file_history=None,
        notes_panel=None,
    ):
        super().__init__()

        # Store upstream tab references
        self.step2_tab = step2_tab
        self.step3_tab = step3_tab
        self.step4_tab = step4_tab
        self.step5_tab = step5_tab
        self.step1_tab = step1_tab
        self.file_history = file_history
        self.notes_panel = notes_panel

        # Computation state
        self.performance_results = None
        self.worker_thread = None

        logger.info("Initialising Step 6 widget")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._create_left_panel(), stretch=0)
        main_layout.addWidget(self._create_right_panel(), stretch=1)

    # ------------------------------------------------------------------
    # Panel builders
    # ------------------------------------------------------------------

    def _create_left_panel(self) -> QWidget:
        """Scrollable control / summary panel (max width 370 px)."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # ── Title ──────────────────────────────────────────────────────
        title = QLabel("Step 6: Model Performance")
        tf = QFont()
        tf.setBold(True)
        tf.setPointSize(12)
        title.setFont(tf)
        title.setStyleSheet(step_title_font(13))
        layout.addWidget(title)
        self._title_label = title

        # ── Status / summary banner ────────────────────────────────────
        self.summary_banner = QLabel("Run Steps 2–5 then click Compute Metrics.")
        self.summary_banner.setStyleSheet(summary_banner_style())
        self.summary_banner.setWordWrap(True)
        layout.addWidget(self.summary_banner)

        # ── Primary action button ──────────────────────────────────────
        self.compute_button = QPushButton("⚙  Compute Metrics")
        self.compute_button.setStyleSheet(primary_button_style())
        self.compute_button.clicked.connect(self._on_compute_clicked)
        layout.addWidget(self.compute_button)

        # ── Secondary action row: Reload + Clear ───────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(6)

        self.reload_button = QPushButton("↻  Reload Data")
        self.reload_button.setToolTip(
            "Re-read all upstream step results and recompute metrics"
        )
        self.reload_button.setStyleSheet(secondary_button_style())
        self.reload_button.clicked.connect(self._on_reload_clicked)
        action_row.addWidget(self.reload_button)

        self.clear_button = QPushButton("✕  Clear")
        self.clear_button.setToolTip(
            "Clear all computed results and reset charts to placeholder state"
        )
        self.clear_button.setStyleSheet(secondary_button_style())
        self.clear_button.clicked.connect(self._on_clear_clicked)
        action_row.addWidget(self.clear_button)

        layout.addLayout(action_row)

        # ── Export buttons ─────────────────────────────────────────────
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

        # ── Info label ─────────────────────────────────────────────────
        self.info_label = QLabel(
            "Complete Steps 2–5 to enable performance metrics computation."
        )
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet(instruction_banner_style())
        layout.addWidget(self.info_label)

        # ── Progress bar (hidden until computation starts) ─────────────
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
        """Right panel: chart tab widget + summary table in a vertical splitter."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Chart tab widget ───────────────────────────────────────────
        self.chart_tabs = QTabWidget()

        chart_bg = get_chart_bg()

        # Fig 7: Elemental Preference Ranking
        self.fig7 = Figure(figsize=(8, 3.5), dpi=100)
        self.fig7.patch.set_facecolor(chart_bg)
        self.ax7 = self.fig7.add_subplot(111)
        self.canvas7 = FigureCanvasQTAgg(self.fig7)
        self.canvas7.setStyleSheet(f"background-color: {chart_bg};")
        self.toolbar7 = NavigationToolbar2QT(self.canvas7)
        tab7 = self._wrap_canvas(self.canvas7, self.toolbar7)
        self.chart_tabs.addTab(tab7, " Ranking")

        # Fig 11: Pipeline Funnel
        self.fig11 = Figure(figsize=(8, 3.5), dpi=100)
        self.fig11.patch.set_facecolor(chart_bg)
        self.ax11 = self.fig11.add_subplot(111)
        self.canvas11 = FigureCanvasQTAgg(self.fig11)
        self.canvas11.setStyleSheet(f"background-color: {chart_bg};")
        self.toolbar11 = NavigationToolbar2QT(self.canvas11)
        tab11 = self._wrap_canvas(self.canvas11, self.toolbar11)
        self.chart_tabs.addTab(tab11, " Pipeline")

        # Fig 12: Correlation Heatmap
        self.fig12 = Figure(figsize=(8, 3.5), dpi=100)
        self.fig12.patch.set_facecolor(chart_bg)
        self.ax12 = self.fig12.add_subplot(111)
        self.canvas12 = FigureCanvasQTAgg(self.fig12)
        self.canvas12.setStyleSheet(f"background-color: {chart_bg};")
        self.toolbar12 = NavigationToolbar2QT(self.canvas12)
        tab12 = self._wrap_canvas(self.canvas12, self.toolbar12)
        self.chart_tabs.addTab(tab12, "Heatmap")

        # Fig 14: Performance Metrics (dual Y-axis)
        self.fig14 = Figure(figsize=(8, 3.5), dpi=100)
        self.fig14.patch.set_facecolor(chart_bg)
        self.ax14 = self.fig14.add_subplot(111)
        self.ax14_2 = self.ax14.twinx()   # secondary axis for SBR
        self.canvas14 = FigureCanvasQTAgg(self.fig14)
        self.canvas14.setStyleSheet(f"background-color: {chart_bg};")
        self.toolbar14 = NavigationToolbar2QT(self.canvas14)
        tab14 = self._wrap_canvas(self.canvas14, self.toolbar14)
        self.chart_tabs.addTab(tab14, " Metrics")

        chart_wrapper = QWidget()
        cwl = QVBoxLayout(chart_wrapper)
        cwl.setContentsMargins(0, 0, 0, 0)
        cwl.addWidget(self.chart_tabs)
        chart_wrapper.setMinimumHeight(280)
        splitter.addWidget(chart_wrapper)

        # ── Summary table ──────────────────────────────────────────────
        self.summary_table = self._create_summary_table()
        splitter.addWidget(self.summary_table)

        splitter.setSizes([400, 200])
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

    def _create_summary_table(self) -> QTableWidget:
        """Create the per-element summary QTableWidget."""
        t = QTableWidget()
        t.setColumnCount(5)
        t.setHorizontalHeaderLabels(
            ["Element", "Confidence Tier", "Matched Lines", "Mean VC", "Status"]
        )
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.setAlternatingRowColors(True)
        t.setSortingEnabled(False)
        # Populate placeholder row
        self._set_table_placeholder(t)
        return t

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Pull latest data from upstream tabs and trigger a (re)computation."""
        self._on_compute_clicked()

    # ------------------------------------------------------------------
    # Compute logic
    # ------------------------------------------------------------------

    def _on_compute_clicked(self) -> None:
        """Disable exports, show progress, launch background worker."""
        # Reset export buttons every cycle (Requirement 10.4)
        self.export_csv_button.setEnabled(False)
        self.export_png_button.setEnabled(False)
        self.export_pdf_button.setEnabled(False)

        self.compute_button.setEnabled(False)
        self.progress_bar.show()
        self.summary_banner.setText("Computing performance metrics…")
        self.info_label.setText("Running analysis — please wait.")

        self.worker_thread = WorkerThread(self._compute_worker)
        self.worker_thread.finished.connect(self._on_compute_finished)
        self.worker_thread.error.connect(self._on_worker_error)
        self.worker_thread.start()

    def _on_reload_clicked(self) -> None:
        """Re-read all upstream step data and recompute metrics from scratch."""
        logger.info("Step 6: Reload Data triggered")
        self.summary_banner.setText("Reloading data from Steps 2–5…")
        self.info_label.setText("Fetching latest upstream results and recomputing.")
        # Delegate to the normal compute path — it always pulls live references
        self._on_compute_clicked()

    def _on_clear_clicked(self) -> None:
        """Clear all results, reset charts to placeholder, disable exports."""
        logger.info("Step 6: Clear triggered")
        self.performance_results = None

        # Disable exports
        self.export_csv_button.setEnabled(False)
        self.export_png_button.setEnabled(False)
        self.export_pdf_button.setEnabled(False)

        # Reset status labels
        self.summary_banner.setText("Results cleared. Run Steps 2–5 then click Compute Metrics.")
        self.info_label.setText("Complete Steps 2–5 to enable performance metrics computation.")

        # Reset all four charts to placeholder state
        for ax, canvas in [
            (self.ax7,  self.canvas7),
            (self.ax11, self.canvas11),
            (self.ax12, self.canvas12),
            (self.ax14, self.canvas14),
        ]:
            ax.clear()
            ChartEngine._show_placeholder(ax, "No data — click Compute Metrics")
            ChartEngine.apply_dark_style(ax.get_figure(), ax)
            canvas.draw()

        # Also clear the secondary axis on fig14
        self.ax14_2.clear()
        self.canvas14.draw()

        # Reset summary table
        self._set_table_placeholder(self.summary_table)

    def _compute_worker(self):
        """Worker function: read upstream data, call PerformanceCalculator."""
        detected_peaks = getattr(self.step2_tab, "detected_peaks", None)
        matches = getattr(self.step3_tab, "matches", None)
        analysis_results = getattr(self.step4_tab, "analysis_results", None)
        validation_results = getattr(self.step5_tab, "validation_results", None)

        # processed_data lives on step1_tab when Step 1 baseline correction was
        # used, but also on step2_tab (loaded directly for peak detection).
        # Try step1 first, then fall back to step2.
        processed_data = None
        if self.step1_tab is not None:
            processed_data = getattr(self.step1_tab, "processed_data", None)
        if processed_data is None:
            processed_data = getattr(self.step2_tab, "processed_data", None)

        calculator = PerformanceCalculator()
        result = calculator.compute(
            detected_peaks=detected_peaks,
            matches=matches,
            analysis_results=analysis_results,
            validation_results=validation_results,
            processed_data=processed_data,
        )
        return result

    def _on_compute_finished(self, _signal_dict: dict = None) -> None:
        """Called by WorkerThread.finished — update UI with computed results."""
        self.compute_button.setEnabled(True)
        self.progress_bar.hide()

        if self.worker_thread is None:
            return

        results = self.worker_thread.result
        if results is None:
            self.summary_banner.setText("Computation returned no results.")
            self.info_label.setText("No results available.")
            return

        self.performance_results = results

        # ── Status banner ──────────────────────────────────────────────
        missing = results.get("missing_steps", [])
        if missing:
            banner_text = f"Partial results — missing: {', '.join(missing)}."
        else:
            acc = results.get("accuracy")
            f1 = results.get("f1_score")
            acc_str = f"{acc * 100:.1f}%" if acc is not None else "N/A"
            f1_str = f"{f1 * 100:.1f}%" if f1 is not None else "N/A"
            n_elem = len(results.get("element_rows", []))
            banner_text = (
                f"Accuracy: {acc_str}  |  F1-Score: {f1_str}  |  Elements: {n_elem}"
            )
        self.summary_banner.setText(banner_text)
        self.info_label.setText("Metrics computed successfully.")

        # ── Update all four charts ─────────────────────────────────────
        self._update_chart_fig7()
        self._update_chart_fig11()
        self._update_chart_fig12()
        self._update_chart_fig14()

        # ── Populate summary table ─────────────────────────────────────
        self._populate_summary_table()

        # ── Re-enable export buttons ───────────────────────────────────
        self.export_csv_button.setEnabled(True)
        self.export_png_button.setEnabled(True)
        self.export_pdf_button.setEnabled(True)

        logger.info("Step 6 compute finished: %s", banner_text)

    def _on_worker_error(self, error_message: str) -> None:
        """Handle worker thread error."""
        self.compute_button.setEnabled(True)
        self.progress_bar.hide()
        self.summary_banner.setText(f"Error: {error_message}")
        self.info_label.setText(f"Computation failed: {error_message}")
        logger.error("Step 6 worker error: %s", error_message)
        show_error("Step 6 Error", f"Failed to compute metrics:\n{error_message}")

    # ------------------------------------------------------------------
    # Chart update helpers (Task 5.3)
    # ------------------------------------------------------------------

    def _update_chart_fig7(self) -> None:
        """Render Fig 7: Elemental Preference Ranking bar chart."""
        self.ax7.clear()
        ranking_df = None
        if self.performance_results is not None:
            ranking_df = self.performance_results.get("ranking_df")
        ChartEngine.render_element_ranking_fig7(self.ax7, ranking_df)
        self.canvas7.draw()

    def _update_chart_fig11(self) -> None:
        """Render Fig 11: Pipeline Funnel chart."""
        self.ax11.clear()
        stage_counts = None
        if self.performance_results is not None:
            pipeline = self.performance_results.get("pipeline_stages")
            if pipeline is not None:
                stage_counts = {
                    "stage1_detected": pipeline.get("stage1_detected", 0),
                    "stage2_nist_matched": pipeline.get("stage2_nist_matched", 0),
                    "stage3_ranked": pipeline.get("stage3_ranked", 0),
                    "stage4_validated": pipeline.get("stage4_validated", 0),
                    "stage5_confirmed": pipeline.get("stage5_confirmed", 0),
                }
        ChartEngine.render_pipeline_funnel(self.ax11, stage_counts)
        self.canvas11.draw()

    def _update_chart_fig12(self) -> None:
        """Render Fig 12: Correlation Heatmap."""
        self.ax12.clear()
        matrix = None
        peak_labels = []
        element_labels = []
        if self.performance_results is not None:
            matrix = self.performance_results.get("heatmap_matrix")
            peak_labels = self.performance_results.get("peak_labels", [])
            element_labels = self.performance_results.get("element_labels", [])
        ChartEngine.render_correlation_heatmap(
            self.ax12, matrix, peak_labels, element_labels
        )
        self.canvas12.draw()

    def _update_chart_fig14(self) -> None:
        """Render Fig 14: Performance Metrics bar chart (dual Y-axis)."""
        # Clear both axes before re-rendering
        self.ax14.clear()
        self.ax14_2.clear()

        metrics_dict = {
            "accuracy": None,
            "precision": None,
            "recall": None,
            "f1_score": None,
            "sbr_improvement": None,
        }
        if self.performance_results is not None:
            metrics_dict = {
                "accuracy": self.performance_results.get("accuracy"),
                "precision": self.performance_results.get("precision"),
                "recall": self.performance_results.get("recall"),
                "f1_score": self.performance_results.get("f1_score"),
                "sbr_improvement": self.performance_results.get("sbr_improvement"),
            }

        ChartEngine.render_performance_metrics(self.ax14, metrics_dict, self.ax14_2)
        self.canvas14.draw()

    # ------------------------------------------------------------------
    # Summary table (Task 5.4)
    # ------------------------------------------------------------------

    def _populate_summary_table(self) -> None:
        """Fill the summary table with per-element rows from performance_results."""
        if self.performance_results is None:
            self._set_table_placeholder(self.summary_table)
            return

        element_rows = self.performance_results.get("element_rows", [])
        if not element_rows:
            self._set_table_placeholder(self.summary_table)
            return

        self.summary_table.setSortingEnabled(False)
        self.summary_table.setRowCount(len(element_rows))

        for row_idx, er in enumerate(element_rows):
            element = str(er.get("element", ""))
            tier = str(er.get("confidence_tier", ""))
            matched = er.get("matched_lines", 0)
            mean_vc = er.get("mean_vc")

            # Determine status from tier
            if tier == "High":
                status = "Confirmed"
                tier_bg = C_SUCCESS
            elif tier == "Medium":
                status = "Probable"
                tier_bg = C_WARN
            else:
                status = "Uncertain"
                tier_bg = C_ERROR

            # Column 0: Element
            self.summary_table.setItem(row_idx, 0, QTableWidgetItem(element))

            # Column 1: Confidence Tier — colour-coded background
            tier_item = QTableWidgetItem(tier)
            try:
                tier_item.setBackground(QColor(tier_bg))
                tier_item.setForeground(QColor("#FFFFFF"))
            except Exception:
                logger.warning("Step 6: could not set tier cell colour for %s", element)
                tier_item.setBackground(QColor(C_ERROR))
            self.summary_table.setItem(row_idx, 1, tier_item)

            # Column 2: Matched Lines
            self.summary_table.setItem(
                row_idx, 2, QTableWidgetItem(str(int(matched)))
            )

            # Column 3: Mean VC
            mean_vc_str = f"{mean_vc:.4f}" if mean_vc is not None else "N/A"
            self.summary_table.setItem(row_idx, 3, QTableWidgetItem(mean_vc_str))

            # Column 4: Status
            self.summary_table.setItem(row_idx, 4, QTableWidgetItem(status))

        self.summary_table.setSortingEnabled(True)

    @staticmethod
    def _set_table_placeholder(table: QTableWidget) -> None:
        """Display a single 'Run Steps 2–5 first' placeholder row."""
        table.setSortingEnabled(False)
        table.setRowCount(1)
        placeholder = QTableWidgetItem("Run Steps 2–5 first")
        placeholder.setForeground(QColor(C_TEXT2))
        table.setItem(0, 0, placeholder)
        for col in range(1, 5):
            table.setItem(0, col, QTableWidgetItem(""))

    # ------------------------------------------------------------------
    # apply_theme() (Task 5.6)
    # ------------------------------------------------------------------

    def apply_theme(self) -> None:
        """Refresh all chart canvas backgrounds for the active theme."""
        chart_bg = get_chart_bg()
        for fig, canvas in [
            (self.fig7,  self.canvas7),
            (self.fig11, self.canvas11),
            (self.fig12, self.canvas12),
            (self.fig14, self.canvas14),
        ]:
            fig.patch.set_facecolor(chart_bg)
            canvas.setStyleSheet(f"background-color: {chart_bg};")
            canvas.draw()

        # Refresh label styles for the new theme
        self._title_label.setStyleSheet(step_title_font(13))
        self.summary_banner.setStyleSheet(summary_banner_style())
        self.info_label.setStyleSheet(instruction_banner_style())
        self.reload_button.setStyleSheet(secondary_button_style())
        self.clear_button.setStyleSheet(secondary_button_style())

    # ------------------------------------------------------------------
    # Export handlers (Task 5.7)
    # ------------------------------------------------------------------

    def _on_export_csv_clicked(self) -> None:
        """Export Step 6 summary as CSV."""
        if self.performance_results is None:
            show_error("Export Error", "No results to export. Run Compute Metrics first.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "step6_performance", "CSV Files (*.csv)"
        )
        if not filepath:
            return  # Silently cancel (Requirement 10.5)

        try:
            export_step6_csv(self.performance_results, Path(filepath))
            show_info("Export Successful", f"CSV saved to:\n{filepath}")
        except Exception as e:
            logger.error("Step 6 CSV export failed: %s", e)
            show_error("Export Failed", f"Failed to export CSV:\n{e}")

    def _on_export_png_clicked(self) -> None:
        """Export all four Step 6 charts as a composite PNG."""
        if self.performance_results is None:
            show_error("Export Error", "No results to export. Run Compute Metrics first.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", "step6_charts", "PNG Files (*.png)"
        )
        if not filepath:
            return  # Silently cancel (Requirement 10.5)

        try:
            figures = [self.fig7, self.fig11, self.fig12, self.fig14]
            export_step6_png(figures, Path(filepath), dpi=150)
            show_info("Export Successful", f"PNG saved to:\n{filepath}")
        except Exception as e:
            logger.error("Step 6 PNG export failed: %s", e)
            show_error("Export Failed", f"Failed to export PNG:\n{e}")

    def _on_export_pdf_clicked(self) -> None:
        """Export Step 6 PDF report (reuses generate_pdf_report from step5)."""
        if self.performance_results is None:
            show_error("Export Error", "No results to export. Run Compute Metrics first.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Report", "step6_performance_report", "PDF Files (*.pdf)"
        )
        if not filepath:
            return  # Silently cancel (Requirement 10.5)

        # Gather validation_results_df from step5 if available
        validation_results_df = getattr(self.step5_tab, "validation_results", None)
        if validation_results_df is None:
            import pandas as pd
            validation_results_df = pd.DataFrame()

        # Pull target wavelengths and filenames from Step 5
        target_wavelengths = getattr(self.step5_tab, "target_wavelengths", []) or []
        processed_path = getattr(
            getattr(self.step5_tab, "processed_selector", None),
            "get_filepath", lambda: ""
        )()
        reference_path = getattr(
            getattr(self.step5_tab, "reference_selector", None),
            "get_filepath", lambda: ""
        )()

        # Retrieve vc_fig from step5 if available (best-effort)
        vc_fig = getattr(self.step5_tab, "vc_fig", None)
        if vc_fig is None:
            # Fall back to an empty Figure so the PDF generator always has one
            vc_fig = Figure(figsize=(6, 3), dpi=100)

        # Build step6 metrics dict to pass into the PDF
        step6_metrics = None
        if self.performance_results is not None:
            step6_metrics = {
                "accuracy": self.performance_results.get("accuracy"),
                "precision": self.performance_results.get("precision"),
                "recall": self.performance_results.get("recall"),
                "f1_score": self.performance_results.get("f1_score"),
                "sbr_improvement": self.performance_results.get("sbr_improvement"),
                "element_rows": self.performance_results.get("element_rows", []),
                "pipeline_stages": self.performance_results.get("pipeline_stages"),
            }

        try:
            generate_pdf_report(
                validation_results_df=validation_results_df,
                params={},
                vc_fig=vc_fig,
                processed_filename=Path(processed_path).name if processed_path else "(Step 6 export)",
                reference_filename=Path(reference_path).name if reference_path else "",
                target_wavelengths=target_wavelengths,
                filepath=Path(filepath),
                step6_metrics=step6_metrics,
            )
            show_info("Export Successful", f"PDF report saved to:\n{filepath}")
        except ImportError:
            show_error(
                "Missing Dependency",
                "reportlab is not installed.\nRun: pip install reportlab",
            )
        except Exception as e:
            logger.error("Step 6 PDF export failed: %s", e)
            show_error("Export Failed", f"Failed to generate PDF:\n{e}")
