# -*- coding: utf-8 -*-
"""
Step 4 Widget - Elemental Preferences & Peak-wise Competition

Provides UI for analyzing element preferences through competitive scoring.
"""

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QFileDialog, QMessageBox, QSplitter, QProgressBar, QScrollArea
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


class Step4Widget(QWidget):
    """
    UI widget for Step 4: Elemental Preferences.
    
    Allows users to:
    - Load multiple NIST matching files
    - Analyze peak-wise element competition
    - View element rankings
    - Identify primary element
    - Save detailed results
    """
    
    def __init__(self, file_history=None, notes_panel=None):
        """
        Initialize Step 4 widget.
        
        Parameters
        ----------
        file_history : FileHistory, optional
            Shared file history object
        notes_panel : NotesPanel, optional
            Shared notes panel widget
        """
        super().__init__()
        self.matching_files = []
        self.analyzer = None
        self.analysis_results = None
        self.worker_thread = None
        self.file_history = file_history
        self.notes_panel = notes_panel
        
        logger.info("Initializing Step 4 widget")

        # --- Chart figures and canvases ------------------------------------
        self.ranking_fig = Figure(figsize=(6, 3), dpi=100)
        self.ranking_fig.patch.set_facecolor("#141519")
        self.ranking_canvas = FigureCanvasQTAgg(self.ranking_fig)
        self.ranking_canvas.setStyleSheet("background-color: #141519;")
        self.ranking_toolbar = NavigationToolbar2QT(self.ranking_canvas)
        self.ranking_canvas.setMinimumHeight(180)
        self.ranking_canvas.setMinimumWidth(260)

        self.scatter_fig = Figure(figsize=(6, 3), dpi=100)
        self.scatter_fig.patch.set_facecolor("#141519")
        self.scatter_canvas = FigureCanvasQTAgg(self.scatter_fig)
        self.scatter_canvas.setStyleSheet("background-color: #141519;")
        self.scatter_toolbar = NavigationToolbar2QT(self.scatter_canvas)
        self.scatter_canvas.setMinimumHeight(180)
        self.scatter_canvas.setMinimumWidth(260)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(0)

        # Controls in a scroll area
        controls_container = QWidget()
        controls_layout = self._create_controls()
        controls_container.setLayout(controls_layout)

        controls_scroll = QScrollArea()
        controls_scroll.setWidget(controls_container)
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        controls_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        # No fixed max-height — splitter handles it

        # Results tabs
        self.results_tabs = QTabWidget()
        self.competition_table = self._create_results_table()
        self.ranking_table = self._create_ranking_table()
        self.winners_table = self._create_winners_table()

        self.results_tabs.addTab(self.ranking_table, "Element Ranking")
        self.results_tabs.addTab(self.competition_table, "Peak Competition")
        self.results_tabs.addTab(self.winners_table, "Winner Lines")

        # Charts panel (side-by-side)
        charts_widget = QWidget()
        charts_h_layout = QHBoxLayout()
        charts_h_layout.setContentsMargins(4, 4, 4, 4)
        charts_h_layout.setSpacing(8)

        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)
        left_layout.addWidget(self.ranking_canvas)
        left_layout.addWidget(self.ranking_toolbar)
        left_panel.setLayout(left_layout)

        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)
        right_layout.addWidget(self.scatter_canvas)
        right_layout.addWidget(self.scatter_toolbar)
        right_panel.setLayout(right_layout)

        charts_h_layout.addWidget(left_panel)
        charts_h_layout.addWidget(right_panel)
        charts_widget.setLayout(charts_h_layout)

        # 3-pane vertical splitter: controls (small) | tables (large) | charts (medium)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(controls_scroll)
        splitter.addWidget(self.results_tabs)
        splitter.addWidget(charts_widget)
        # ~180px controls, ~380px tables, ~220px charts out of ~780px total
        splitter.setSizes([180, 380, 220])
        splitter.setStretchFactor(0, 0)   # controls: don't grow
        splitter.setStretchFactor(1, 3)   # tables:   grow most
        splitter.setStretchFactor(2, 1)   # charts:   grow some

        main_layout.addWidget(splitter, stretch=1)
        self.setLayout(main_layout)
    
    def _create_controls(self) -> QVBoxLayout:
        """Create control section."""
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Step 4: Elemental Preferences & Peak Competition")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        title.setStyleSheet(step_title_font(13))
        layout.addWidget(title)

        # Instructions
        instructions = QLabel(
            "📋 Instructions: Select NIST matching result files from Step 3.\n"
            "Look for files named 'LIBS_matching_results*.csv' in the 'NIST matching (3rd step)' folder.\n"
            "You can select multiple files to analyze elements from different NIST databases together."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(instruction_banner_style())
        layout.addWidget(instructions)

        # Summary banner
        self.summary_banner = QLabel("Run analysis to see summary")
        self.summary_banner.setWordWrap(True)
        self.summary_banner.setStyleSheet(summary_banner_style())
        layout.addWidget(self.summary_banner)

        # Primary element label
        self.primary_element_label = QLabel("—")
        self.primary_element_label.setStyleSheet(primary_element_label_style())
        layout.addWidget(self.primary_element_label)

        # Files section
        files_group = QGroupBox("Matching Files")
        files_layout = QHBoxLayout()
        
        self.files_label = QLabel("No files selected")
        files_layout.addWidget(self.files_label)
        
        self.add_files_button = QPushButton("Add Files...")
        self.add_files_button.clicked.connect(self._on_add_files)
        files_layout.addWidget(self.add_files_button)
        
        self.clear_files_button = QPushButton("Clear")
        self.clear_files_button.clicked.connect(self._on_clear_files)
        files_layout.addWidget(self.clear_files_button)
        
        files_group.setLayout(files_layout)
        layout.addWidget(files_group)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        
        self.analyze_button = QPushButton("⚗  Analyze Competition")
        self.analyze_button.setStyleSheet(primary_button_style())
        self.analyze_button.clicked.connect(self._on_analyze_clicked)
        buttons_layout.addWidget(self.analyze_button)
        
        self.save_button = QPushButton("Save Results")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save_clicked)
        buttons_layout.addWidget(self.save_button)

        self.export_csv_button = QPushButton("Export CSV")
        self.export_csv_button.setEnabled(False)
        self.export_csv_button.setToolTip("No data — run analysis first")
        self.export_csv_button.clicked.connect(self._on_export_csv_clicked)
        buttons_layout.addWidget(self.export_csv_button)

        self.export_png_button = QPushButton("Export PNG")
        self.export_png_button.setEnabled(False)
        self.export_png_button.setToolTip("No data — run analysis first")
        self.export_png_button.clicked.connect(self._on_export_png_clicked)
        buttons_layout.addWidget(self.export_png_button)

        # Info label
        self.info_label = QLabel("Select matching files to begin analysis")
        self.info_label.setWordWrap(True)
        buttons_layout.addWidget(self.info_label)
        
        layout.addLayout(buttons_layout)

        # Progress bar (indeterminate, hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setStyleSheet(progress_bar_style())
        self.progress_bar.setMaximumHeight(8)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        
        return layout
    
    def _create_ranking_table(self) -> QTableWidget:
        """Create element ranking table."""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels([
            "Rank", "Element", "Wins", "Total Score", "Avg Score"
        ])
        
        table.setSortingEnabled(True)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        return table
    
    def _create_results_table(self) -> QTableWidget:
        """Create competition results table."""
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "Wavelength (nm)", "Winner", "Max Score", 
            "Competitors", "Ca", "Fe"
        ])
        
        table.setSortingEnabled(True)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        return table
    
    def _create_winners_table(self) -> QTableWidget:
        """Create winner lines table."""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels([
            "Element", "Observed (nm)", "NIST (nm)", 
            "Confidence", "Competitors"
        ])
        
        table.setSortingEnabled(True)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        return table
    
    def _on_add_files(self):
        """Add NIST matching files."""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select NIST Matching Files", "",
            "CSV Files (*.csv)"
        )
        
        if files:
            self.matching_files.extend(files)
            # Show file names in label
            file_names = [Path(f).name for f in self.matching_files]
            files_text = ", ".join(file_names[:3])  # Show first 3 file names
            if len(file_names) > 3:
                files_text += f" ... and {len(file_names) - 3} more"
            self.files_label.setText(f"✅ {len(self.matching_files)} file(s): {files_text}")
            self.info_label.setText(
                f"✅ Loaded {len(self.matching_files)} file(s). "
                f"Click 'Analyze Competition' to start analysis."
            )
            logger.info(f"Added {len(files)} files. Total: {len(self.matching_files)}")
    
    def _on_clear_files(self):
        """Clear selected files."""
        self.matching_files = []
        self.files_label.setText("No files selected")
        self.info_label.setText("Select matching files to begin analysis")
        logger.info("Cleared file selection")
    
    def _on_analyze_clicked(self):
        """Analyze element competition."""
        if not self.matching_files:
            show_error("Error", "Please select at least one matching file")
            return
        
        self.info_label.setText("Loading files...")
        self.analyze_button.setEnabled(False)
        self.save_button.setEnabled(False)

        # Show progress bar and disable export buttons while running
        self.progress_bar.show()
        self.export_csv_button.setEnabled(False)
        self.export_png_button.setEnabled(False)
        
        # Run analysis in worker thread
        self.worker_thread = WorkerThread(
            self._analyze_worker
        )
        self.worker_thread.finished.connect(self._on_analysis_finished)
        self.worker_thread.error.connect(self._on_worker_error)
        self.worker_thread.start()
    
    def _analyze_worker(self):
        """Worker thread for analysis."""
        try:
            import pandas as pd
            analyzer = ElementalPreferencesAnalyzer(STEP4_PARAMS)
            
            # Load all matching files
            dataframes = []
            for filepath in self.matching_files:
                logger.info(f"Loading {filepath}")
                # Read CSV file directly using pandas
                df = pd.read_csv(filepath)
                logger.info(f"Loaded {len(df)} rows from {Path(filepath).name}")
                dataframes.append(df)
            
            # Validate that we have data
            if not dataframes:
                return False, "No data loaded from files"
            
            logger.info(f"Analyzing {len(dataframes)} file(s) with {sum(len(df) for df in dataframes)} total rows")
            
            # Perform analysis
            self.analysis_results = analyzer.analyze(dataframes)

            return True, "Analysis completed successfully"

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return False, str(e)
    
    def _on_worker_error(self, error_message: str):
        """Handle worker thread unhandled exception."""
        self.analyze_button.setEnabled(True)
        self.progress_bar.hide()
        show_error("Analysis Error", error_message)
        self.info_label.setText(f"Error: {error_message}")

    def _on_analysis_finished(self, _result: dict = None):
        """Handle analysis completion."""
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
        
        # Update tables
        self._populate_tables()

        # Update charts and summary banner
        self._update_charts()
        self._update_summary_banner(self.analysis_results)

        # Enable export buttons
        self.export_csv_button.setEnabled(True)
        self.export_png_button.setEnabled(True)

        # Hide progress bar
        self.progress_bar.hide()

        # Update notes panel (GUI thread — safe)
        if self.notes_panel:
            primary = self.analysis_results.get('primary_element', 'Unknown')
            self.notes_panel.add_note(
                f"Step 4 analysis complete: Primary element = {primary}",
                "SUCCESS"
            )

        self.save_button.setEnabled(True)
        self.info_label.setText(
            f"Analysis complete! Primary element: {self.analysis_results['primary_element']}"
        )
        logger.info("Analysis finished successfully")
    
    def _populate_tables(self):
        """Populate result tables."""
        if self.analysis_results is None:
            return
        
        # Ranking table
        ranking_df = self.analysis_results['ranking']
        self.ranking_table.setRowCount(len(ranking_df))
        
        for row, (_, r_data) in enumerate(ranking_df.iterrows()):
            self.ranking_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.ranking_table.setItem(row, 1, QTableWidgetItem(str(r_data['Element'])))
            self.ranking_table.setItem(row, 2, QTableWidgetItem(str(int(r_data['Wins']))))
            self.ranking_table.setItem(row, 3, QTableWidgetItem(f"{r_data['Total_Score']:.2f}"))
            self.ranking_table.setItem(row, 4, QTableWidgetItem(f"{r_data['Avg_Score']:.4f}"))
        
        # Winner lines table
        winners_df = self.analysis_results['winner_lines']
        self.winners_table.setRowCount(len(winners_df))
        
        for row, (_, w_data) in enumerate(winners_df.iterrows()):
            self.winners_table.setItem(row, 0, QTableWidgetItem(str(w_data['Winning_Element'])))
            self.winners_table.setItem(row, 1, QTableWidgetItem(f"{w_data['Observed_Wavelength']:.2f}"))
            self.winners_table.setItem(row, 2, QTableWidgetItem(f"{w_data['NIST_Matched_Wavelength']:.2f}"))
            self.winners_table.setItem(row, 3, QTableWidgetItem(f"{w_data['Confidence_Score']:.4f}"))
            self.winners_table.setItem(row, 4, QTableWidgetItem(str(int(w_data['Num_Competitors']))))
        
        # Competition table (limited to first 100 rows for performance)
        comp_df = self.analysis_results['competition'].head(100)
        self.competition_table.setRowCount(len(comp_df))
        
        for row, (_, c_data) in enumerate(comp_df.iterrows()):
            self.competition_table.setItem(row, 0, QTableWidgetItem(f"{c_data['Matched_WL']:.2f}"))
            self.competition_table.setItem(row, 1, QTableWidgetItem(str(c_data['Winner'])))
            self.competition_table.setItem(row, 2, QTableWidgetItem(f"{c_data['Max_Score']:.4f}"))
            self.competition_table.setItem(row, 3, QTableWidgetItem(str(int(c_data['Num_Competitors']))))
        
        logger.info("Tables populated with analysis results")

    def _update_charts(self):
        """Clear and redraw ranking and scatter charts from current analysis_results."""
        if self.analysis_results is None:
            return

        ranking_df = self.analysis_results.get('ranking')
        winner_lines_df = self.analysis_results.get('winner_lines')

        # Ranking chart
        self.ranking_fig.clear()
        ax_ranking = self.ranking_fig.add_subplot(111)
        ChartEngine.render_ranking_chart(ax_ranking, ranking_df)
        self.ranking_canvas.draw()
        self.ranking_toolbar.home()

        # Scatter chart
        self.scatter_fig.clear()
        ax_scatter = self.scatter_fig.add_subplot(111)
        ChartEngine.render_score_scatter(ax_scatter, winner_lines_df)
        self.scatter_canvas.draw()
        self.scatter_toolbar.home()

    def _update_summary_banner(self, analysis_results):
        """Update the summary banner and primary element label from analysis_results."""
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

        # Extract primary element info from the top-ranked row
        top_row = ranking_df.iloc[0]
        primary_element = str(top_row.get('Element', '—'))
        wins = int(top_row.get('Wins', 0))
        total_elements = len(ranking_df)
        total_peaks = len(competition_df) if competition_df is not None else 0

        banner_text = (
            f"Primary element: <b>{primary_element}</b> "
            f"({wins} wins)  |  "
            f"Elements analysed: <b>{total_elements}</b>  |  "
            f"Peaks analysed: <b>{total_peaks}</b>"
        )
        self.summary_banner.setText(banner_text)
        self.primary_element_label.setText(primary_element)

    def _on_export_csv_clicked(self):
        """Export Step 4 results to CSV files in a selected directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Export Directory", ""
        )
        if not directory:
            return

        try:
            ranking_df = self.analysis_results['ranking']
            winner_lines_df = self.analysis_results['winner_lines']
            competition_df = self.analysis_results['competition']

            written_paths = export_step4_csv(
                ranking_df, winner_lines_df, competition_df, Path(directory)
            )
            paths_text = "\n".join(str(p) for p in written_paths)
            show_info("Export Successful", f"CSV files saved:\n{paths_text}")
            logger.info(f"Step 4 CSV exported to {directory}")

        except Exception as e:
            logger.error(f"CSV export failed: {e}")
            show_error("Export Failed", f"Failed to export CSV:\n{e}")

    def _on_export_png_clicked(self):
        """Export Step 4 charts to PNG files in a selected directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Export Directory", ""
        )
        if not directory:
            return

        try:
            written_paths = export_step4_png(
                self.ranking_fig, self.scatter_fig, Path(directory)
            )
            paths_text = "\n".join(str(p) for p in written_paths)
            show_info("Export Successful", f"PNG files saved:\n{paths_text}")
            logger.info(f"Step 4 PNG exported to {directory}")

        except Exception as e:
            logger.error(f"PNG export failed: {e}")
            show_error("Export Failed", f"Failed to export PNG:\n{e}")

    def _on_save_clicked(self):
        """Save analysis results."""
        if self.analysis_results is None:
            show_error("Error", "No results to save")
            return
        
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Results", "analysis_results",
            "CSV Files (*.csv)"
        )
        
        if not filepath:
            return
        
        try:
            base_path = str(Path(filepath).with_suffix(''))
            
            # Save each result
            ranking_file = f"{base_path}_ranking.csv"
            competition_file = f"{base_path}_competition.csv"
            winners_file = f"{base_path}_winners.csv"
            
            self.analysis_results['ranking'].to_csv(ranking_file, index=False)
            self.analysis_results['competition'].to_csv(competition_file, index=False)
            self.analysis_results['winner_lines'].to_csv(winners_file, index=False)
            
            show_info(
                "Success",
                f"Results saved:\n{ranking_file}\n{competition_file}\n{winners_file}"
            )
            logger.info(f"Results saved to {base_path}_*.csv")
        
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            show_error("Error", f"Failed to save results:\n{e}")
