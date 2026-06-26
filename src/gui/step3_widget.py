# -*- coding: utf-8 -*-
"""
Step 3 Widget - NIST Element Identification

Provides UI for matching detected peaks against NIST databases.
"""

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QScrollArea
)
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from src import setup_logger
from src.config import STEP3_PARAMS
from src.core.step3_nist_matching import NISTMatcher
from src.io.file_reader import CSVReader
from src.io.file_writer import CSVWriter
from src.gui.gui_utils import (
    ParameterControl, FileSelector, WorkerThread,
    show_error, show_info
)
from src.gui.charts import ChartEngine
from src.gui.theme import primary_button_style, instruction_banner_style, step_title_font

logger = setup_logger(__name__)


class Step3Widget(QWidget):
    """
    UI widget for Step 3: NIST Element Identification.

    Allows users to:
    - Select detected peaks file
    - Select NIST database file(s)
    - Match peaks to elements
    - View element frequency and match-score charts
    - Sort and filter results
    - Save matching results
    """

    def __init__(self, file_history=None, notes_panel=None):
        super().__init__()
        self.detected_peaks = None
        self.nist_db = None
        self.matches = None
        self.matcher = None
        self.worker_thread = None
        self.file_history = file_history
        self.notes_panel = notes_panel

        logger.info("Initializing Step 3 widget")

        # Chart figures
        self.freq_fig = Figure(figsize=(5, 3), dpi=100)
        self.freq_fig.patch.set_facecolor("#141519")
        self.freq_canvas = FigureCanvasQTAgg(self.freq_fig)
        self.freq_canvas.setStyleSheet("background-color: #141519;")
        self.freq_canvas.setMinimumHeight(200)
        self.freq_canvas.setMinimumWidth(260)
        self.freq_toolbar = NavigationToolbar2QT(self.freq_canvas)

        self.score_fig = Figure(figsize=(5, 3), dpi=100)
        self.score_fig.patch.set_facecolor("#141519")
        self.score_canvas = FigureCanvasQTAgg(self.score_fig)
        self.score_canvas.setStyleSheet("background-color: #141519;")
        self.score_canvas.setMinimumHeight(200)
        self.score_canvas.setMinimumWidth(260)
        self.score_toolbar = NavigationToolbar2QT(self.score_canvas)

        # ── Controls (scrollable) ──────────────────────────────────────────
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        self._build_controls(controls_layout)

        scroll = QScrollArea()
        scroll.setWidget(controls_widget)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        # ── Results table ─────────────────────────────────────────────────
        self.table = self._create_results_table()

        # ── Charts panel (side by side) ───────────────────────────────────
        charts_widget = QWidget()
        ch_layout = QHBoxLayout(charts_widget)
        ch_layout.setContentsMargins(4, 4, 4, 4)
        ch_layout.setSpacing(8)

        left_chart = QWidget()
        lc_layout = QVBoxLayout(left_chart)
        lc_layout.setContentsMargins(0, 0, 0, 0)
        lc_layout.addWidget(self.freq_canvas)
        lc_layout.addWidget(self.freq_toolbar)

        right_chart = QWidget()
        rc_layout = QVBoxLayout(right_chart)
        rc_layout.setContentsMargins(0, 0, 0, 0)
        rc_layout.addWidget(self.score_canvas)
        rc_layout.addWidget(self.score_toolbar)

        ch_layout.addWidget(left_chart)
        ch_layout.addWidget(right_chart)

        # ── Table + charts splitter (vertical) ───────────────────────────
        bottom_splitter = QSplitter(Qt.Orientation.Vertical)
        bottom_splitter.addWidget(self.table)
        bottom_splitter.addWidget(charts_widget)
        bottom_splitter.setSizes([350, 250])

        # ── Top (controls scroll) + bottom splitter (horizontal splitter) ─
        top_splitter = QSplitter(Qt.Orientation.Vertical)
        top_splitter.addWidget(scroll)
        top_splitter.addWidget(bottom_splitter)
        top_splitter.setSizes([220, 600])

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(top_splitter)

    # ──────────────────────────────────────────────────────────────────────
    # Control-building helper
    # ──────────────────────────────────────────────────────────────────────

    def _build_controls(self, layout: QVBoxLayout):
        """Populate the controls layout (title, instructions, files, params, buttons)."""
        title = QLabel("Step 3: NIST Element Identification")
        tf = QFont()
        tf.setBold(True)
        tf.setPointSize(12)
        title.setFont(tf)
        title.setStyleSheet(step_title_font(13))
        layout.addWidget(title)

        instructions = QLabel(
            "📋 Instructions:\n"
            "1. 'Detected Peaks': load the peaks CSV from Step 2 (e.g. 'detected_peaks.csv').\n"
            "2. 'NIST Database': load an element reference CSV from the NIST database.\n"
            "3. Set Tolerance (nm): maximum wavelength difference for a match.\n"
            "4. Set Min Score: minimum score to display — leave at 0 for all matches.\n"
            "5. Click 'Match Peaks' to cross-match peaks against the database.\n"
            "6. Results appear in the table; charts update automatically.\n"
            "7. Click 'Save Results' to export 'LIBS_matching_results.csv'.\n"
            "   ⚠ Run for each element — all result files are needed for Step 4."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(instruction_banner_style())
        layout.addWidget(instructions)

        files_group = QGroupBox("Input Files")
        files_layout = QHBoxLayout()
        self.peaks_selector = FileSelector("Detected Peaks:", "CSV Files (*.csv)")
        files_layout.addWidget(self.peaks_selector)
        self.nist_selector = FileSelector("NIST Database:", "CSV Files (*.csv)")
        files_layout.addWidget(self.nist_selector)
        files_group.setLayout(files_layout)
        layout.addWidget(files_group)

        params_group = QGroupBox("Parameters")
        params_layout = QHBoxLayout()
        self.tolerance_control = ParameterControl(
            "Tolerance (nm)", 0.01, 1.0, STEP3_PARAMS['TOLERANCE'],
            step=0.01, decimals=3
        )
        params_layout.addWidget(self.tolerance_control)
        self.threshold_control = ParameterControl(
            "Min Score", 0, 1e10, STEP3_PARAMS['MIN_SCORE_THRESHOLD'],
            step=1e6, decimals=0
        )
        params_layout.addWidget(self.threshold_control)
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        buttons_layout = QHBoxLayout()
        self.match_button = QPushButton("🔬  Match Peaks")
        self.match_button.setStyleSheet(primary_button_style())
        self.match_button.clicked.connect(self._on_match_clicked)
        buttons_layout.addWidget(self.match_button)

        self.save_button = QPushButton("Save Results")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save_clicked)
        buttons_layout.addWidget(self.save_button)

        self.info_label = QLabel("Ready to match peaks")
        self.info_label.setWordWrap(True)
        buttons_layout.addWidget(self.info_label)
        layout.addLayout(buttons_layout)

    def _create_results_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            "Observed (nm)", "Matched (nm)", "Delta (nm)", "Element",
            "Aki", "Rel. Int.", "Score"
        ])
        table.setSortingEnabled(True)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    # ──────────────────────────────────────────────────────────────────────
    # Event handlers
    # ──────────────────────────────────────────────────────────────────────

    def _on_match_clicked(self):
        if self.peaks_selector.get_filepath() is None:
            show_error("Error", "Please select detected peaks file")
            return
        if self.nist_selector.get_filepath() is None:
            show_error("Error", "Please select NIST database file")
            return

        self.info_label.setText("Loading files...")
        self.match_button.setEnabled(False)

        try:
            reader = CSVReader()
            self.detected_peaks = reader.read_detected_peaks(
                str(self.peaks_selector.get_filepath())
            )
            logger.info(f"Loaded {len(self.detected_peaks)} detected peaks")
            self.nist_db = reader.read_nist_database(
                str(self.nist_selector.get_filepath())
            )
            logger.info(f"Loaded NIST database: {len(self.nist_db)} entries")
        except Exception as e:
            logger.error(f"Failed to load files: {e}")
            show_error("Error", f"Failed to load files:\n{e}")
            self.match_button.setEnabled(True)
            self.info_label.setText("Error loading files")
            return

        params = {
            'TOLERANCE': self.tolerance_control.value(),
            'MIN_SCORE_THRESHOLD': self.threshold_control.value()
        }
        self.matcher = NISTMatcher(params)
        self.info_label.setText("Matching peaks… (may take a moment)")

        self.worker_thread = WorkerThread(
            self.matcher.match_peaks,
            self.detected_peaks,
            self.nist_db
        )
        self.worker_thread.finished.connect(self._on_matching_finished)
        self.worker_thread.error.connect(self._on_matching_error)
        self.worker_thread.start()

    def _on_matching_finished(self, result: dict):
        self.matches = result.get('result')

        if self.matches:
            logger.info(f"Matching complete: {len(self.matches)} results")
            self._update_table()
            self._update_charts()

            identified = [m for m in self.matches if m.element]
            self.info_label.setText(
                f"Matched: {len(identified)} peaks identified as elements"
            )
            self.save_button.setEnabled(True)

        self.match_button.setEnabled(True)

    def _on_matching_error(self, error: str):
        logger.error(f"Matching error: {error}")
        show_error("Matching Error", f"Peak matching failed:\n{error}")
        self.info_label.setText("Error during matching")
        self.match_button.setEnabled(True)

    def _update_table(self):
        if self.matches is None:
            return

        self.table.setRowCount(len(self.matches))
        for i, match in enumerate(self.matches):
            self.table.setItem(i, 0, QTableWidgetItem(f"{match.observed_wl:.5f}"))
            self.table.setItem(i, 1, QTableWidgetItem(
                f"{match.matched_wl:.5f}" if match.matched_wl else "—"))
            self.table.setItem(i, 2, QTableWidgetItem(
                f"{match.delta:.4f}" if match.delta is not None else "—"))
            self.table.setItem(i, 3, QTableWidgetItem(
                match.element if match.element else "—"))
            self.table.setItem(i, 4, QTableWidgetItem(
                f"{match.aki:.2e}" if match.aki else "—"))
            self.table.setItem(i, 5, QTableWidgetItem(
                f"{match.relative_intensity:.1f}" if match.relative_intensity else "—"))
            self.table.setItem(i, 6, QTableWidgetItem(
                f"{match.score:.2e}" if match.score else "—"))

    def _update_charts(self):
        """Redraw element-frequency and match-score charts."""
        if not self.matches:
            return

        # Frequency chart
        self.freq_fig.clear()
        ax_freq = self.freq_fig.add_subplot(111)
        ChartEngine.render_element_frequency_chart(ax_freq, self.matches)
        self.freq_canvas.draw()
        self.freq_toolbar.home()

        # Score scatter chart
        self.score_fig.clear()
        ax_score = self.score_fig.add_subplot(111)
        ChartEngine.render_match_score_scatter(ax_score, self.matches)
        self.score_canvas.draw()
        self.score_toolbar.home()

    def _on_save_clicked(self):
        if self.matches is None:
            show_error("Error", "No matches to save")
            return
        try:
            writer = CSVWriter()
            csv_path = writer.write_nist_matches("LIBS_matching_results.csv", self.matches)
            logger.info(f"Saved matching results to {csv_path}")
            show_info("Success", f"Results saved to:\n{csv_path}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            show_error("Error", f"Failed to save results:\n{e}")
