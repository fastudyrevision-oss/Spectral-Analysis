# -*- coding: utf-8 -*-
"""
Step 4 Widget - Elemental Preferences & Peak-wise Competition

Two-column layout: scrollable controls on the left, charts + tables on the right.
"""

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QFileDialog, QSplitter, QProgressBar, QScrollArea
)
from PyQt6.QtGui import QFont, QColor
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from src import setup_logger
from src.config import STEP4_PARAMS
from src.core.step4_elemental_preferences import ElementalPreferencesAnalyzer
from src.gui.gui_utils import (
    FileSelector, WorkerThread,
    show_error, show_info
)
from src.gui.theme import (
    primary_button_style, instruction_banner_style, step_title_font,
    summary_banner_style, primary_element_label_style, progress_bar_style
)
from src.gui.charts import ChartEngine
from src.gui.export_engine import export_step4_csv, export_step4_png

logger = setup_logger(__name__)

_CHART_BG = "#141519"


class Step4Widget(QWidget):
    """
    UI widget for Step 4: Elemental Preferences.

    Layout mirrors Step 1/2:
    - Left  (fixed ≤370 px, scrollable): title, instructions, file controls,
      summary banner, action buttons, info label.
    - Right (stretch): vertical splitter → charts side-by-side (top) +
      tabbed result tables (bottom).
    """

    def __init__(self, file_history=None, notes_panel=None):
        super().__init__()
        self.matching_files = []
        self.analyzer = None
        self.analysis_results = None
        self.worker_thread = None
        self.file_history = file_history
        self.notes_panel = notes_panel

        logger.info("Initializing Step 4 widget")

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

        title = QLabel("Step 4: Elemental Preferences & Peak Competition")
        tf = QFont(); tf.setBold(True); tf.setPointSize(12)
        title.setFont(tf)
        title.setStyleSheet(step_title_font(13))
        layout.addWidget(title)

        instructions = QLabel(
            "📋 Instructions: Select NIST matching result files from Step 3.\n"
            "Look for files named 'LIBS_matching_results*.csv'.\n"
            "You can select multiple files to analyse elements from different "
            "NIST databases together."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(instruction_banner_style())
        layout.addWidget(instructions)

        self.summary_banner = QLabel("Run analysis to see summary")
        self.summary_banner.setWordWrap(True)
        self.summary_banner.setStyleSheet(summary_banner_style())
        layout.addWidget(self.summary_banner)

        self.primary_element_label = QLabel("—")
        self.primary_element_label.setStyleSheet(primary_element_label_style())
        layout.addWidget(self.primary_element_label)

        files_group = QGroupBox("Matching Files")
        fl = QHBoxLayout()
        self.files_label = QLabel("No files selected")
        self.files_label.setWordWrap(True)
        fl.addWidget(self.files_label, stretch=1)
        self.add_files_button = QPushButton("Add Files…")
        self.add_files_button.clicked.connect(self._on_add_files)
        fl.addWidget(self.add_files_button)
        self.clear_files_button = QPushButton("Clear")
        self.clear_files_button.clicked.connect(self._on_clear_files)
        fl.addWidget(self.clear_files_button)
        files_group.setLayout(fl)
        layout.addWidget(files_group)

        btn_row = QHBoxLayout()
        self.analyze_button = QPushButton("⚗  Analyze Competition")
        self.analyze_button.setStyleSheet(primary_button_style())
        self.analyze_button.clicked.connect(self._on_analyze_clicked)
        btn_row.addWidget(self.analyze_button)

        self.save_button = QPushButton("Save Results")
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
        layout.addLayout(export_row)

        self.info_label = QLabel("Select matching files to begin analysis")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setStyleSheet(progress_bar_style())
        self.progress_bar.setMaximumHeight(8)
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
        """Right panel: charts side-by-side (top) + tabbed tables (bottom)."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Charts ─────────────────────────────────────────────────────────
        self.ranking_fig = Figure(figsize=(6, 3), dpi=100)
        self.ranking_fig.patch.set_facecolor(_CHART_BG)
        self.ranking_canvas = FigureCanvasQTAgg(self.ranking_fig)
        self.ranking_canvas.setStyleSheet(f"background-color: {_CHART_BG};")
        self.ranking_canvas.setMinimumHeight(160)
        self.ranking_toolbar = NavigationToolbar2QT(self.ranking_canvas)

        self.scatter_fig = Figure(figsize=(6, 3), dpi=100)
        self.scatter_fig.patch.set_facecolor(_CHART_BG)
        self.scatter_canvas = FigureCanvasQTAgg(self.scatter_fig)
        self.scatter_canvas.setStyleSheet(f"background-color: {_CHART_BG};")
        self.scatter_canvas.setMinimumHeight(160)
        self.scatter_toolbar = NavigationToolbar2QT(self.scatter_canvas)

        rank_container = QWidget()
        rcl = QVBoxLayout(rank_container)
        rcl.setContentsMargins(0, 0, 0, 0); rcl.setSpacing(2)
        rcl.addWidget(self.ranking_canvas)
        rcl.addWidget(self.ranking_toolbar)

        scatter_container = QWidget()
        scl = QVBoxLayout(scatter_container)
        scl.setContentsMargins(0, 0, 0, 0); scl.setSpacing(2)
        scl.addWidget(self.scatter_canvas)
        scl.addWidget(self.scatter_toolbar)

        charts_widget = QWidget()
        chl = QHBoxLayout(charts_widget)
        chl.setContentsMargins(4, 4, 4, 4); chl.setSpacing(8)
        chl.addWidget(rank_container)
        chl.addWidget(scatter_container)

        splitter.addWidget(charts_widget)

        # ── Tabbed result tables ───────────────────────────────────────────
        self.results_tabs = QTabWidget()
        self.ranking_table   = self._create_ranking_table()
        self.competition_table = self._create_results_table()
        self.winners_table   = self._create_winners_table()
        self.results_tabs.addTab(self.ranking_table,    "Element Ranking")
        self.results_tabs.addTab(self.competition_table, "Peak Competition")
        self.results_tabs.addTab(self.winners_table,    "Winner Lines")
        splitter.addWidget(self.results_tabs)

        splitter.setSizes([280, 400])
        layout.addWidget(splitter)
        return panel

    # ──────────────────────────────────────────────────────────────────────
    # Table factories
    # ──────────────────────────────────────────────────────────────────────

    def _create_ranking_table(self) -> QTableWidget:
        t = QTableWidget()
        t.setColumnCount(5)
        t.setHorizontalHeaderLabels(["Rank", "Element", "Wins", "Total Score", "Avg Score"])
        t.setSortingEnabled(True)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return t

    def _create_results_table(self) -> QTableWidget:
        t = QTableWidget()
        t.setColumnCount(4)
        t.setHorizontalHeaderLabels(
            ["Wavelength (nm)", "Winner", "Max Score", "Competitors"])
        t.setSortingEnabled(True)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return t

    def _create_winners_table(self) -> QTableWidget:
        t = QTableWidget()
        t.setColumnCount(5)
        t.setHorizontalHeaderLabels(
            ["Element", "Observed (nm)", "NIST (nm)", "Confidence", "Competitors"])
        t.setSortingEnabled(True)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return t

    # ──────────────────────────────────────────────────────────────────────
    # Event handlers
    # ──────────────────────────────────────────────────────────────────────

    def _on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select NIST Matching Files", "", "CSV Files (*.csv)")
        if files:
            self.matching_files.extend(files)
            names = [Path(f).name for f in self.matching_files]
            text = ", ".join(names[:3])
            if len(names) > 3:
                text += f" … and {len(names) - 3} more"
            self.files_label.setText(f"✅ {len(self.matching_files)} file(s): {text}")
            self.info_label.setText(
                f"✅ {len(self.matching_files)} file(s) loaded. "
                "Click 'Analyze Competition' to start.")
            logger.info(f"Added {len(files)} files. Total: {len(self.matching_files)}")

    def _on_clear_files(self):
        self.matching_files = []
        self.files_label.setText("No files selected")
        self.info_label.setText("Select matching files to begin analysis")
        logger.info("Cleared file selection")

    def _on_analyze_clicked(self):
        if not self.matching_files:
            show_error("Error", "Please select at least one matching file")
            return
        self.info_label.setText("Loading files…")
        self.analyze_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.progress_bar.show()
        self.export_csv_button.setEnabled(False)
        self.export_png_button.setEnabled(False)

        self.worker_thread = WorkerThread(self._analyze_worker)
        self.worker_thread.finished.connect(self._on_analysis_finished)
        self.worker_thread.error.connect(self._on_worker_error)
        self.worker_thread.start()

    def _analyze_worker(self):
        try:
            import pandas as pd
            analyzer = ElementalPreferencesAnalyzer(STEP4_PARAMS)
            dataframes = []
            for filepath in self.matching_files:
                logger.info(f"Loading {filepath}")
                df = pd.read_csv(filepath)
                logger.info(f"Loaded {len(df)} rows from {Path(filepath).name}")
                dataframes.append(df)
            if not dataframes:
                return False, "No data loaded from files"
            logger.info(
                f"Analysing {len(dataframes)} file(s) with "
                f"{sum(len(d) for d in dataframes)} total rows")
            self.analysis_results = analyzer.analyze(dataframes)
            return True, "Analysis completed successfully"
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return False, str(e)

    def _on_worker_error(self, error_message: str):
        self.analyze_button.setEnabled(True)
        self.progress_bar.hide()
        show_error("Analysis Error", error_message)
        self.info_label.setText(f"Error: {error_message}")

    def _on_analysis_finished(self, _result: dict = None):
        if self.worker_thread is None:
            return
        result = self.worker_thread.result
        if result is None:
            self.analyze_button.setEnabled(True)
            self.progress_bar.hide()
            show_error("Analysis Failed", "Worker returned no result")
            return

        success, message = result
        self.analyze_button.setEnabled(True)
        if not success:
            self.progress_bar.hide()
            show_error("Analysis Failed", message)
            self.info_label.setText(f"Error: {message}")
            if self.notes_panel:
                self.notes_panel.add_note(f"Step 4 analysis error: {message}", "ERROR")
            return

        self._populate_tables()
        self._update_charts()
        self._update_summary_banner(self.analysis_results)
        self.export_csv_button.setEnabled(True)
        self.export_png_button.setEnabled(True)
        self.progress_bar.hide()
        if self.notes_panel:
            primary = self.analysis_results.get('primary_element', 'Unknown')
            self.notes_panel.add_note(
                f"Step 4 analysis complete: Primary element = {primary}", "SUCCESS")
        self.save_button.setEnabled(True)
        self.info_label.setText(
            f"Analysis complete! Primary element: "
            f"{self.analysis_results['primary_element']}")
        logger.info("Analysis finished successfully")

    # ──────────────────────────────────────────────────────────────────────
    # Data renderers
    # ──────────────────────────────────────────────────────────────────────

    def _populate_tables(self):
        if self.analysis_results is None:
            return

        ranking_df = self.analysis_results['ranking']
        self.ranking_table.setRowCount(len(ranking_df))
        for row, (_, r) in enumerate(ranking_df.iterrows()):
            self.ranking_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.ranking_table.setItem(row, 1, QTableWidgetItem(str(r['Element'])))
            self.ranking_table.setItem(row, 2, QTableWidgetItem(str(int(r['Wins']))))
            self.ranking_table.setItem(row, 3, QTableWidgetItem(f"{r['Total_Score']:.2f}"))
            self.ranking_table.setItem(row, 4, QTableWidgetItem(f"{r['Avg_Score']:.4f}"))

        winners_df = self.analysis_results['winner_lines']
        self.winners_table.setRowCount(len(winners_df))
        for row, (_, w) in enumerate(winners_df.iterrows()):
            self.winners_table.setItem(row, 0, QTableWidgetItem(str(w['Winning_Element'])))
            self.winners_table.setItem(row, 1, QTableWidgetItem(f"{w['Observed_Wavelength']:.2f}"))
            self.winners_table.setItem(row, 2, QTableWidgetItem(f"{w['NIST_Matched_Wavelength']:.2f}"))
            self.winners_table.setItem(row, 3, QTableWidgetItem(f"{w['Confidence_Score']:.4f}"))
            self.winners_table.setItem(row, 4, QTableWidgetItem(str(int(w['Num_Competitors']))))

        comp_df = self.analysis_results['competition'].head(100)
        self.competition_table.setRowCount(len(comp_df))
        for row, (_, c) in enumerate(comp_df.iterrows()):
            self.competition_table.setItem(row, 0, QTableWidgetItem(f"{c['Matched_WL']:.2f}"))
            self.competition_table.setItem(row, 1, QTableWidgetItem(str(c['Winner'])))
            self.competition_table.setItem(row, 2, QTableWidgetItem(f"{c['Max_Score']:.4f}"))
            self.competition_table.setItem(row, 3, QTableWidgetItem(str(int(c['Num_Competitors']))))

        logger.info("Tables populated with analysis results")

    def _update_charts(self):
        if self.analysis_results is None:
            return
        ranking_df = self.analysis_results.get('ranking')
        winner_lines_df = self.analysis_results.get('winner_lines')

        self.ranking_fig.clear()
        ax_r = self.ranking_fig.add_subplot(111)
        ChartEngine.render_ranking_chart(ax_r, ranking_df)
        self.ranking_canvas.draw()
        self.ranking_toolbar.home()

        self.scatter_fig.clear()
        ax_s = self.scatter_fig.add_subplot(111)
        ChartEngine.render_score_scatter(ax_s, winner_lines_df)
        self.scatter_canvas.draw()
        self.scatter_toolbar.home()

    def _update_summary_banner(self, analysis_results):
        if analysis_results is None:
            self.summary_banner.setText("Run analysis to see summary")
            self.primary_element_label.setText("—")
            return
        ranking_df = analysis_results.get('ranking')
        competition_df = analysis_results.get('competition')
        if ranking_df is None or ranking_df.empty:
            self.summary_banner.setText("No ranking data available")
            self.primary_element_label.setText("—")
            return
        top = ranking_df.iloc[0]
        primary = str(top.get('Element', '—'))
        wins = int(top.get('Wins', 0))
        total_peaks = len(competition_df) if competition_df is not None else 0
        self.summary_banner.setText(
            f"Primary element: <b>{primary}</b> ({wins} wins)  |  "
            f"Elements analysed: <b>{len(ranking_df)}</b>  |  "
            f"Peaks analysed: <b>{total_peaks}</b>")
        self.primary_element_label.setText(primary)

    # ──────────────────────────────────────────────────────────────────────
    # Export / save
    # ──────────────────────────────────────────────────────────────────────

    def _on_export_csv_clicked(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Export Directory", "")
        if not directory:
            return
        try:
            paths = export_step4_csv(
                self.analysis_results['ranking'],
                self.analysis_results['winner_lines'],
                self.analysis_results['competition'],
                Path(directory))
            show_info("Export Successful", "CSV files saved:\n" + "\n".join(str(p) for p in paths))
        except Exception as e:
            logger.error(f"CSV export failed: {e}")
            show_error("Export Failed", f"Failed to export CSV:\n{e}")

    def _on_export_png_clicked(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Export Directory", "")
        if not directory:
            return
        try:
            paths = export_step4_png(self.ranking_fig, self.scatter_fig, Path(directory))
            show_info("Export Successful", "PNG files saved:\n" + "\n".join(str(p) for p in paths))
        except Exception as e:
            logger.error(f"PNG export failed: {e}")
            show_error("Export Failed", f"Failed to export PNG:\n{e}")

    def _on_save_clicked(self):
        if self.analysis_results is None:
            show_error("Error", "No results to save")
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Results", "analysis_results", "CSV Files (*.csv)")
        if not filepath:
            return
        try:
            base = str(Path(filepath).with_suffix(''))
            self.analysis_results['ranking'].to_csv(f"{base}_ranking.csv", index=False)
            self.analysis_results['competition'].to_csv(f"{base}_competition.csv", index=False)
            self.analysis_results['winner_lines'].to_csv(f"{base}_winners.csv", index=False)
            show_info("Success",
                      f"Results saved:\n{base}_ranking.csv\n"
                      f"{base}_competition.csv\n{base}_winners.csv")
            logger.info(f"Results saved to {base}_*.csv")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            show_error("Error", f"Failed to save results:\n{e}")
