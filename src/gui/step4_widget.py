# -*- coding: utf-8 -*-
"""
Step 4 Widget - Elemental Preferences & Peak-wise Competition

Two-column layout: scrollable controls on the left, charts + tables on the right.
"""

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QFileDialog, QSplitter, QProgressBar, QScrollArea,
    QListWidget, QListWidgetItem, QAbstractItemView,
)
from PyQt6.QtGui import QFont, QColor
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from src import setup_logger
from src.config import STEP4_PARAMS
from src.core.step4_elemental_preferences import ElementalPreferencesAnalyzer
from src.gui.gui_utils import (
    HighDpiToolbar as NavigationToolbar2QT,
    style_toolbar,
    FileSelector, WorkerThread, FileHistory, RecentFilesButton,
    show_error, show_info,
    make_table_toolbar, on_copy_table_clicked,
)
from src.gui.theme import (
    primary_button_style, instruction_banner_style, step_title_font,
    summary_banner_style, primary_element_label_style, progress_bar_style,
    get_chart_bg,
)
from src.gui.charts import ChartEngine
from src.gui.export_engine import export_step4_csv, export_step4_png

logger = setup_logger(__name__)


class Step4Widget(QWidget):
    """
    UI widget for Step 4: Elemental Preferences.

    Layout mirrors Step 1/2:
    - Left  (fixed ≤370 px, scrollable): title, instructions, file controls,
      summary banner, action buttons, info label.
    - Right (stretch): vertical splitter → charts side-by-side (top) +
      tabbed result tables (bottom).
    """

    # Emitted after successful analysis — carries the analysis_results dict
    # so Step 5 can receive it directly without a file round-trip.
    result_ready = pyqtSignal(object)

    def __init__(self, file_history=None, notes_panel=None):
        super().__init__()
        self.matching_files = []
        self.analyzer = None
        self.analysis_results = None
        self.worker_thread = None
        self.file_history = file_history
        self.notes_panel = notes_panel

        # Role-scoped recent-file history for Step 4 matching files
        self._matching_history = FileHistory(role="step4_matching")

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
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("Step 4: Elemental Preferences & Peak Competition")
        tf = QFont(); tf.setBold(True); tf.setPointSize(12)
        title.setFont(tf)
        title.setStyleSheet(step_title_font(13))
        title.setWordWrap(True)
        layout.addWidget(title)
        self._title_label = title

        instructions = QLabel(
            "📋 Instructions: Select NIST matching result files from Step 3.\n"
            "Look for files named 'LIBS_matching_results*.csv'.\n"
            "You can select multiple files to analyse elements from different "
            "NIST databases together."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(instruction_banner_style())
        layout.addWidget(instructions)
        self._instructions_label = instructions

        self.summary_banner = QLabel("Run analysis to see summary")
        self.summary_banner.setWordWrap(True)
        self.summary_banner.setStyleSheet(summary_banner_style())
        layout.addWidget(self.summary_banner)

        self.primary_element_label = QLabel("—")
        self.primary_element_label.setStyleSheet(primary_element_label_style())
        layout.addWidget(self.primary_element_label)

        files_group = QGroupBox("Matching Files")
        fl = QVBoxLayout()
        fl.setContentsMargins(6, 6, 6, 6)
        fl.setSpacing(4)

        # List of queued files
        self._files_list_widget = QListWidget()
        self._files_list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._files_list_widget.setMaximumHeight(80)
        self._files_list_widget.setToolTip(
            "NIST matching result CSVs from Step 3.\n"
            "All files are merged before analysis.\n"
            "Select items then click Remove to delete.")
        fl.addWidget(self._files_list_widget)

        # Add / Remove / Clear row
        file_btn_row = QHBoxLayout()
        file_btn_row.setSpacing(4)
        self.add_files_button = QPushButton("Add Files…")
        self.add_files_button.clicked.connect(self._on_add_files)
        file_btn_row.addWidget(self.add_files_button)
        self._remove_files_btn = QPushButton("Remove")
        self._remove_files_btn.clicked.connect(self._on_remove_files)
        file_btn_row.addWidget(self._remove_files_btn)
        self.clear_files_button = QPushButton("Clear")
        self.clear_files_button.clicked.connect(self._on_clear_files)
        file_btn_row.addWidget(self.clear_files_button)
        fl.addLayout(file_btn_row)

        # Recent files dropdown
        recent_row = QHBoxLayout()
        recent_row.setSpacing(4)
        self._matching_recent_btn = RecentFilesButton(
            self._matching_history, show_add_all=True)
        self._matching_recent_btn.file_selected.connect(self._on_recent_file_selected)
        self._matching_recent_btn.all_selected.connect(self._on_add_all_recent)
        recent_row.addWidget(self._matching_recent_btn)
        recent_row.addStretch()
        fl.addLayout(recent_row)

        # Status label
        self.files_label = QLabel("No files selected")
        self.files_label.setWordWrap(True)
        self.files_label.setStyleSheet("font-size: 10px; color: grey;")
        fl.addWidget(self.files_label)

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
        """Right panel: single tab widget with charts + tabbed result tables."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Single tab widget: charts + tables all as tabs ─────────────────
        self.chart_tabs = QTabWidget()

        chart_bg = get_chart_bg()

        # Tab 1: Ranking Chart
        self.ranking_fig = Figure(figsize=(6, 3), dpi=100)
        self.ranking_fig.patch.set_facecolor(chart_bg)
        self.ranking_canvas = FigureCanvasQTAgg(self.ranking_fig)
        self.ranking_canvas.setStyleSheet(f"background-color: {chart_bg};")
        self.ranking_toolbar = NavigationToolbar2QT(self.ranking_canvas)

        rank_container = QWidget()
        rcl = QVBoxLayout(rank_container)
        rcl.setContentsMargins(0, 0, 0, 0); rcl.setSpacing(2)
        rcl.addWidget(self.ranking_canvas)
        rcl.addWidget(self.ranking_toolbar)
        self.chart_tabs.addTab(rank_container, "Ranking Chart")

        # Tab 2: Score Scatter Chart
        self.scatter_fig = Figure(figsize=(6, 3), dpi=100)
        self.scatter_fig.patch.set_facecolor(chart_bg)
        self.scatter_canvas = FigureCanvasQTAgg(self.scatter_fig)
        self.scatter_canvas.setStyleSheet(f"background-color: {chart_bg};")
        self.scatter_toolbar = NavigationToolbar2QT(self.scatter_canvas)

        scatter_container = QWidget()
        scl = QVBoxLayout(scatter_container)
        scl.setContentsMargins(0, 0, 0, 0); scl.setSpacing(2)
        scl.addWidget(self.scatter_canvas)
        scl.addWidget(self.scatter_toolbar)
        self.chart_tabs.addTab(scatter_container, "Score Scatter")

        self._show_placeholders()

        # Tab 3: Element Ranking table
        self.ranking_table = self._create_ranking_table()
        _rank_container, self._ranking_copy_btn, self._ranking_row_label = \
            make_table_toolbar(self.ranking_table, row_label_text="— rows")
        self._ranking_copy_btn.clicked.connect(
            lambda: on_copy_table_clicked(
                self.ranking_table, self._ranking_copy_btn, self._ranking_row_label
            )
        )
        self.chart_tabs.addTab(_rank_container, "📋 Element Ranking")

        # Tab 4: Peak Competition table
        self.competition_table = self._create_results_table()
        _comp_container, self._competition_copy_btn, self._competition_row_label = \
            make_table_toolbar(self.competition_table, row_label_text="— rows")
        self._competition_copy_btn.clicked.connect(
            lambda: on_copy_table_clicked(
                self.competition_table, self._competition_copy_btn, self._competition_row_label
            )
        )
        self.chart_tabs.addTab(_comp_container, "📋 Peak Competition")

        # Tab 5: Winner Lines table
        self.winners_table = self._create_winners_table()
        _win_container, self._winners_copy_btn, self._winners_row_label = \
            make_table_toolbar(self.winners_table, row_label_text="— rows")
        self._winners_copy_btn.clicked.connect(
            lambda: on_copy_table_clicked(
                self.winners_table, self._winners_copy_btn, self._winners_row_label
            )
        )
        self.chart_tabs.addTab(_win_container, "📋 Winner Lines")

        # Keep results_tabs as an alias so existing code that references it still works
        self.results_tabs = self.chart_tabs

        layout.addWidget(self.chart_tabs)
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
    # Theme
    # ──────────────────────────────────────────────────────────────────────

    def _show_placeholders(self):
        chart_bg = get_chart_bg()
        for fig, canvas, msg in [
            (self.ranking_fig, self.ranking_canvas, "No data — run Elemental Preferences"),
            (self.scatter_fig, self.scatter_canvas, "No data — run Elemental Preferences"),
        ]:
            fig.clear()
            fig.patch.set_facecolor(chart_bg)
            canvas.setStyleSheet(f"background-color: {chart_bg};")
            ax = fig.add_subplot(111)
            ChartEngine._show_placeholder(ax, msg)
            ChartEngine.apply_dark_style(fig, ax)
            canvas.draw()

    def apply_theme(self):
        """Update chart backgrounds when the global theme changes."""
        from src.gui.theme import step_title_font, instruction_banner_style, summary_banner_style
        chart_bg = get_chart_bg()
        for fig, canvas in [(self.ranking_fig, self.ranking_canvas),
                             (self.scatter_fig, self.scatter_canvas)]:
            fig.patch.set_facecolor(chart_bg)
            canvas.setStyleSheet(f"background-color: {chart_bg};")

        if self.analysis_results is not None:
            self._update_charts()
        else:
            self._show_placeholders()

        self._title_label.setStyleSheet(step_title_font(13))
        self._instructions_label.setStyleSheet(instruction_banner_style())
        self.summary_banner.setStyleSheet(summary_banner_style())
        style_toolbar(self.ranking_toolbar)
        style_toolbar(self.scatter_toolbar)

    # ──────────────────────────────────────────────────────────────────────
    # Event handlers
    # ──────────────────────────────────────────────────────────────────────

    def _on_add_files(self):
        recent = self._matching_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select NIST Matching Files", start_dir, "CSV Files (*.csv)")
        if files:
            for fp in files:
                if fp not in self.matching_files:
                    self.matching_files.append(fp)
                    self._files_list_widget.addItem(
                        QListWidgetItem(Path(fp).name))
                    self._matching_history.add_file(fp)
            self._matching_recent_btn.refresh()
            self._refresh_files_label()
            self.info_label.setText(
                f"✅ {len(self.matching_files)} file(s) loaded. "
                "Click 'Analyze Competition' to start.")
            logger.info(f"Added {len(files)} files. Total: {len(self.matching_files)}")

    def _on_remove_files(self):
        """Remove selected items from the list."""
        rows = sorted(
            [self._files_list_widget.row(i)
             for i in self._files_list_widget.selectedItems()],
            reverse=True,
        )
        for r in rows:
            self._files_list_widget.takeItem(r)
            self.matching_files.pop(r)
        self._refresh_files_label()

    def _on_clear_files(self):
        self.matching_files = []
        self._files_list_widget.clear()
        self._refresh_files_label()
        self.info_label.setText("Select matching files to begin analysis")
        logger.info("Cleared file selection")

    def _on_recent_file_selected(self, path_str: str):
        """Add a recently-used file from the dropdown."""
        if path_str not in self.matching_files:
            self.matching_files.append(path_str)
            self._files_list_widget.addItem(
                QListWidgetItem(Path(path_str).name))
            self._matching_history.add_file(path_str)
        self._matching_recent_btn.refresh()
        self._refresh_files_label()

    def _on_add_all_recent(self, paths: list):
        """Add every file in the recent list that isn't already queued."""
        added = 0
        for path_str in paths:
            if path_str not in self.matching_files:
                self.matching_files.append(path_str)
                self._files_list_widget.addItem(
                    QListWidgetItem(Path(path_str).name))
                added += 1
        if added:
            self._matching_recent_btn.refresh()
            self._refresh_files_label()
            logger.info(f"Added all recent: {added} file(s) queued")

    def _refresh_files_label(self):
        n = len(self.matching_files)
        if n == 0:
            self.files_label.setText("No files selected")
            self.files_label.setStyleSheet("font-size: 10px; color: grey;")
        else:
            self.files_label.setText(f"✅ {n} file{'s' if n > 1 else ''} queued")
            self.files_label.setStyleSheet("font-size: 10px; color: #4CAF50;")

    def _on_analyze_clicked(self):
        has_inmemory = getattr(self, '_step3_inmemory_df', None) is not None
        if not self.matching_files and not has_inmemory:
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

            # Use in-memory DataFrame from Step 3 if available
            inmemory_df = getattr(self, '_step3_inmemory_df', None)
            if inmemory_df is not None and not inmemory_df.empty:
                dataframes.append(inmemory_df)
                logger.info(
                    f"Using in-memory Step 3 data: {len(inmemory_df)} rows"
                )
            else:
                for filepath in self.matching_files:
                    logger.info(f"Loading {filepath}")
                    df = pd.read_csv(filepath)
                    logger.info(f"Loaded {len(df)} rows from {Path(filepath).name}")
                    dataframes.append(df)

            if not dataframes:
                return False, "No data loaded from files"
            logger.info(
                f"Analysing {len(dataframes)} source(s) with "
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
        try:
            from src.gui.session_manager import save_step4
            save_step4(self.analysis_results)
        except Exception:
            pass
        if self.notes_panel:
            primary = self.analysis_results.get('primary_element', 'Unknown')
            self.notes_panel.add_note(
                f"Step 4 analysis complete: Primary element = {primary}", "SUCCESS")
        self.save_button.setEnabled(True)
        self.info_label.setText(
            f"Analysis complete! Primary element: "
            f"{self.analysis_results['primary_element']}")
        logger.info("Analysis finished successfully")

        # Notify next step — pass results directly (no file round-trip)
        self.result_ready.emit(self.analysis_results)

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
            self.ranking_table.setItem(row, 3, QTableWidgetItem(f"{r['Total_Score']:.3e}"))
            self.ranking_table.setItem(row, 4, QTableWidgetItem(f"{r['Avg_Score']:.3e}"))
        n_rank = len(ranking_df)
        self._ranking_row_label.setText(f"{n_rank} row{'s' if n_rank != 1 else ''}")
        self._ranking_copy_btn.setEnabled(n_rank > 0)
        self._ranking_copy_btn.setChecked(False)
        self._ranking_copy_btn.setText("⎘  Copy")

        winners_df = self.analysis_results['winner_lines']
        self.winners_table.setRowCount(len(winners_df))
        for row, (_, w) in enumerate(winners_df.iterrows()):
            self.winners_table.setItem(row, 0, QTableWidgetItem(str(w['Winning_Element'])))
            self.winners_table.setItem(row, 1, QTableWidgetItem(f"{w['Observed_Wavelength']:.2f}"))
            self.winners_table.setItem(row, 2, QTableWidgetItem(f"{w['NIST_Matched_Wavelength']:.2f}"))
            self.winners_table.setItem(row, 3, QTableWidgetItem(f"{w['Confidence_Score']:.3e}"))
            self.winners_table.setItem(row, 4, QTableWidgetItem(str(int(w['Num_Competitors']))))
        n_win = len(winners_df)
        self._winners_row_label.setText(f"{n_win} row{'s' if n_win != 1 else ''}")
        self._winners_copy_btn.setEnabled(n_win > 0)
        self._winners_copy_btn.setChecked(False)
        self._winners_copy_btn.setText("⎘  Copy")

        comp_df = self.analysis_results['competition'].head(100)
        self.competition_table.setRowCount(len(comp_df))
        for row, (_, c) in enumerate(comp_df.iterrows()):
            self.competition_table.setItem(row, 0, QTableWidgetItem(f"{c['Matched_WL']:.2f}"))
            self.competition_table.setItem(row, 1, QTableWidgetItem(str(c['Winner'])))
            self.competition_table.setItem(row, 2, QTableWidgetItem(f"{c['Max_Score']:.3e}"))
            self.competition_table.setItem(row, 3, QTableWidgetItem(str(int(c['Num_Competitors']))))
        n_comp = len(comp_df)
        self._competition_row_label.setText(f"{n_comp} row{'s' if n_comp != 1 else ''}")
        self._competition_copy_btn.setEnabled(n_comp > 0)
        self._competition_copy_btn.setChecked(False)
        self._competition_copy_btn.setText("⎘  Copy")

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
        recent = self._matching_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Select Export Directory", start_dir)
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
        recent = self._matching_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Select Export Directory", start_dir)
        if not directory:
            return
        try:
            paths = export_step4_png(self.ranking_fig, self.scatter_fig, Path(directory))
            show_info("Export Successful", "PNG files saved:\n" + "\n".join(str(p) for p in paths))
        except Exception as e:
            logger.error(f"PNG export failed: {e}")
            show_error("Export Failed", f"Failed to export PNG:\n{e}")

    def load_from_step3(self, matches) -> None:
        """
        Auto-load Step 3 NIST match results directly into Step 4.

        matches — list[NISTMatch] from Step 3.
        Converts to a DataFrame (same schema as the CSV the analyzer expects)
        and registers it as the single in-memory matching file.
        """
        if not matches:
            return
        import pandas as pd
        rows = [{
            "Observed_WL":         m.observed_wl,
            "Matched_WL":          m.matched_wl if m.matched_wl is not None else "",
            "Delta":               m.delta if m.delta is not None else "",
            "Aki":                 m.aki,
            "Relative_Intensity":  m.relative_intensity,
            "Score":               m.score,
            "Element":             m.element if m.element is not None else "",
        } for m in matches]
        df = pd.DataFrame(rows)

        # Store the DataFrame where the analyzer worker can find it
        self._step3_inmemory_df = df

        n = len(matches)
        self.matching_files = []   # clear file paths — using in-memory data
        self._files_list_widget.clear()
        self._files_list_widget.addItem(
            QListWidgetItem(f"← {n} matches loaded from Step 3 (in-memory)"))
        self._refresh_files_label()
        self.info_label.setText(
            f"✅ {n:,} NIST matches loaded from Step 3.\n"
            "Click 'Analyze Competition' to proceed."
        )
        logger.info("Step 4: in-memory matches loaded from Step 3 (%d rows)", n)

    def _on_save_clicked(self):
        if self.analysis_results is None:
            show_error("Error", "No results to save")
            return
        recent = self._matching_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Results", str(Path(start_dir) / "analysis_results"),
            "CSV Files (*.csv)")
        if not filepath:
            return
        try:
            base = str(Path(filepath).with_suffix(''))
            self.analysis_results['ranking'].to_csv(
                f"{base}_ranking.csv", index=False, lineterminator='\n')
            self.analysis_results['competition'].to_csv(
                f"{base}_competition.csv", index=False, lineterminator='\n')
            self.analysis_results['winner_lines'].to_csv(
                f"{base}_winners.csv", index=False, lineterminator='\n')
            show_info("Success",
                      f"Results saved:\n{base}_ranking.csv\n"
                      f"{base}_competition.csv\n{base}_winners.csv")
            logger.info(f"Results saved to {base}_*.csv")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            show_error("Error", f"Failed to save results:\n{e}")
