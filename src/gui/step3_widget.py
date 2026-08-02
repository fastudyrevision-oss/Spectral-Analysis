# -*- coding: utf-8 -*-
"""
Step 3 Widget - NIST Element Identification

Two-column layout: scrollable controls on the left, charts + table on the right.

Multiple NIST database files are supported. Each is matched against the same
detected-peaks file; the best score across all databases wins each peak.
"""

from pathlib import Path
from datetime import datetime

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QScrollArea,
    QFileDialog, QListWidget, QListWidgetItem, QAbstractItemView, QCheckBox,
    QTabWidget,
)
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from src import setup_logger
from src.config import STEP3_PARAMS
from src.core.step3_nist_matching import NISTMatcher
from src.io.file_reader import CSVReader
from src.io.file_writer import CSVWriter
from src.gui.gui_utils import (
    HighDpiToolbar as NavigationToolbar2QT,
    ParameterControl, FileSelector, WorkerThread,
    show_error, show_info
)
from src.gui.charts import ChartEngine
from src.gui.theme import (
    primary_button_style, instruction_banner_style, step_title_font,
    C_BG_BASE,
    get_chart_bg, get_chart_axes_bg, get_chart_text, get_chart_text2, get_chart_border,
)

logger = setup_logger(__name__)


class Step3Widget(QWidget):
    """
    UI widget for Step 3: NIST Element Identification.

    Layout:
    - Left  (fixed ≤370 px, scrollable): title, instructions, detected-peaks
      file selector, NIST database file list (multi-file), parameters,
      action buttons, info label.
    - Right (stretch): vertical splitter → charts side-by-side (top) +
      results table (bottom).
    """

    def __init__(self, file_history=None, notes_panel=None):
        super().__init__()
        self.detected_peaks = None
        self.nist_dbs = []          # list of loaded pd.DataFrames
        self.nist_paths: list[str] = []   # parallel list of file paths
        self.matches = None
        self.matcher = None
        self.worker_thread = None
        self.file_history = file_history
        self.notes_panel = notes_panel

        logger.info("Initializing Step 3 widget")

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

        title = QLabel("Step 3: NIST Element Identification")
        tf = QFont(); tf.setBold(True); tf.setPointSize(12)
        title.setFont(tf)
        title.setStyleSheet(step_title_font(13))
        layout.addWidget(title)

        instructions = QLabel(
            "📋 Instructions:\n"
            "1. 'Detected Peaks': load the peaks CSV from Step 2.\n"
            "2. 'NIST Databases': add one or more element reference CSVs.\n"
            "   • Each file is typically one element (e.g. NIST-Ca.csv).\n"
            "   • The merged view lets you preview all matches at once.\n"
            "3. Set Tolerance (nm): max wavelength difference for a match.\n"
            "4. Set Min Score: minimum score to display (0 = all matches).\n"
            "5. Click 'Match Peaks' to run matching across all databases.\n"
            "6. Results appear in the table; charts update automatically.\n"
            "7. Click 'Save Results' to export CSVs:\n"
            "   • 1 NIST file → 1 combined results CSV.\n"
            "   • Multiple NIST files → 1 CSV per element database.\n"
            "   ⚠ Step 4 needs one CSV file per element."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(instruction_banner_style())
        layout.addWidget(instructions)

        # ── Detected peaks file (single) ───────────────────────────────────
        peaks_group = QGroupBox("Detected Peaks File")
        pg = QVBoxLayout()
        self.peaks_selector = FileSelector("Peaks CSV:", "CSV Files (*.csv)")
        pg.addWidget(self.peaks_selector)
        peaks_group.setLayout(pg)
        layout.addWidget(peaks_group)

        # ── NIST database files (multi) ────────────────────────────────────
        nist_group = QGroupBox("NIST Database Files")
        ng = QVBoxLayout()
        ng.setSpacing(4)

        # File list display
        self.nist_list = QListWidget()
        self.nist_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.nist_list.setMaximumHeight(90)
        self.nist_list.setToolTip("Select items then click Remove to delete them")
        ng.addWidget(self.nist_list)

        nist_btn_row = QHBoxLayout()
        add_nist_btn = QPushButton("Add File(s)…")
        add_nist_btn.clicked.connect(self._on_add_nist_files)
        nist_btn_row.addWidget(add_nist_btn)

        remove_nist_btn = QPushButton("Remove Selected")
        remove_nist_btn.clicked.connect(self._on_remove_nist_files)
        nist_btn_row.addWidget(remove_nist_btn)

        clear_nist_btn = QPushButton("Clear All")
        clear_nist_btn.clicked.connect(self._on_clear_nist_files)
        nist_btn_row.addWidget(clear_nist_btn)
        ng.addLayout(nist_btn_row)

        self.nist_count_label = QLabel("No NIST files loaded")
        self.nist_count_label.setWordWrap(True)
        ng.addWidget(self.nist_count_label)

        nist_group.setLayout(ng)
        layout.addWidget(nist_group)

        # ── Parameters ─────────────────────────────────────────────────────
        params_group = QGroupBox("Parameters")
        pl = QVBoxLayout()
        self.tolerance_control = ParameterControl(
            "Tolerance (nm)", 0.01, 1.0, STEP3_PARAMS['TOLERANCE'],
            step=0.01, decimals=3)
        pl.addWidget(self.tolerance_control)
        self.threshold_control = ParameterControl(
            "Min Score", 0, 1e10, STEP3_PARAMS['MIN_SCORE_THRESHOLD'],
            step=1e6, decimals=0)
        pl.addWidget(self.threshold_control)
        params_group.setLayout(pl)
        layout.addWidget(params_group)

        # ── Buttons ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.match_button = QPushButton("🔬  Match Peaks")
        self.match_button.setStyleSheet(primary_button_style())
        self.match_button.clicked.connect(self._on_match_clicked)
        btn_row.addWidget(self.match_button)

        self.save_button = QPushButton("Save Results")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save_clicked)
        btn_row.addWidget(self.save_button)
        layout.addLayout(btn_row)

        self.info_label = QLabel("Ready to match peaks")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

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
        """Right panel: tab widget (charts + results table as tabs)."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Tab widget ─────────────────────────────────────────────────────
        self.chart_tabs = QTabWidget()

        chart_bg = get_chart_bg()

        # Tab 1: Element Frequency chart
        self.freq_fig = Figure(figsize=(5, 3), dpi=100)
        self.freq_fig.patch.set_facecolor(chart_bg)
        self.freq_canvas = FigureCanvasQTAgg(self.freq_fig)
        self.freq_canvas.setStyleSheet(f"background-color: {chart_bg};")
        self.freq_toolbar = NavigationToolbar2QT(self.freq_canvas)

        freq_container = QWidget()
        fcl = QVBoxLayout(freq_container)
        fcl.setContentsMargins(0, 0, 0, 0); fcl.setSpacing(2)
        fcl.addWidget(self.freq_canvas)
        fcl.addWidget(self.freq_toolbar)
        self.chart_tabs.addTab(freq_container, "Element Frequency")

        # Tab 2: Match Score Scatter chart
        self.score_fig = Figure(figsize=(5, 3), dpi=100)
        self.score_fig.patch.set_facecolor(chart_bg)
        self.score_canvas = FigureCanvasQTAgg(self.score_fig)
        self.score_canvas.setStyleSheet(f"background-color: {chart_bg};")
        self.score_toolbar = NavigationToolbar2QT(self.score_canvas)

        score_container = QWidget()
        scl = QVBoxLayout(score_container)
        scl.setContentsMargins(0, 0, 0, 0); scl.setSpacing(2)
        scl.addWidget(self.score_canvas)
        scl.addWidget(self.score_toolbar)
        self.chart_tabs.addTab(score_container, "Match Score Scatter")

        # Tab 3: Results table
        table_tab = QWidget()
        ttl = QVBoxLayout(table_tab)
        ttl.setContentsMargins(4, 2, 4, 4)
        ttl.setSpacing(4)

        self.matched_only_cb = QCheckBox("Show matched peaks only")
        self.matched_only_cb.setChecked(False)
        self.matched_only_cb.toggled.connect(self._on_filter_toggled)
        ttl.addWidget(self.matched_only_cb)

        self.table = self._create_results_table()
        ttl.addWidget(self.table)
        self.chart_tabs.addTab(table_tab, "📋 Results Table")

        layout.addWidget(self.chart_tabs)
        return panel

    def _create_results_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            "Observed (nm)", "Matched (nm)", "Delta (nm)", "Element",
            "Aki", "Rel. Int.", "Score"
        ])
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    # ──────────────────────────────────────────────────────────────────────
    # NIST file management
    # ──────────────────────────────────────────────────────────────────────

    def _on_add_nist_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select NIST Database File(s)", str(Path.home()),
            "CSV Files (*.csv)")
        if not files:
            return
        for fp in files:
            if fp not in self.nist_paths:
                self.nist_paths.append(fp)
                self.nist_list.addItem(QListWidgetItem(Path(fp).name))
        self._refresh_nist_label()

    def _on_remove_nist_files(self):
        """Remove whichever rows are selected in the list."""
        selected_rows = sorted(
            [self.nist_list.row(item) for item in self.nist_list.selectedItems()],
            reverse=True)
        for row in selected_rows:
            self.nist_list.takeItem(row)
            self.nist_paths.pop(row)
        self._refresh_nist_label()

    def _on_clear_nist_files(self):
        self.nist_paths.clear()
        self.nist_dbs.clear()
        self.nist_list.clear()
        self._refresh_nist_label()

    def _refresh_nist_label(self):
        n = len(self.nist_paths)
        if n == 0:
            self.nist_count_label.setText("No NIST files loaded")
        else:
            self.nist_count_label.setText(
                f"✅ {n} file{'s' if n > 1 else ''} queued")

    # ──────────────────────────────────────────────────────────────────────
    # Theme
    # ──────────────────────────────────────────────────────────────────────

    def apply_theme(self):
        """Update chart backgrounds when the global theme changes."""
        chart_bg = get_chart_bg()
        for fig, canvas in [(self.freq_fig, self.freq_canvas),
                             (self.score_fig, self.score_canvas)]:
            fig.patch.set_facecolor(chart_bg)
            canvas.setStyleSheet(f"background-color: {chart_bg};")
            canvas.draw()

    # ──────────────────────────────────────────────────────────────────────
    # Matching
    # ──────────────────────────────────────────────────────────────────────

    def _on_match_clicked(self):
        if self.peaks_selector.get_filepath() is None:
            show_error("Error", "Please select the detected peaks file")
            return
        if not self.nist_paths:
            show_error("Error", "Please add at least one NIST database file")
            return

        self.info_label.setText("Loading files…")
        self.match_button.setEnabled(False)

        try:
            reader = CSVReader()
            self.detected_peaks = reader.read_detected_peaks(
                str(self.peaks_selector.get_filepath()))
            logger.info(f"Loaded {len(self.detected_peaks)} detected peaks")

            self.nist_dbs = []
            for fp in self.nist_paths:
                db = reader.read_nist_database(fp)
                self.nist_dbs.append(db)
                logger.info(f"Loaded NIST DB '{Path(fp).name}': {len(db)} entries")

        except Exception as e:
            logger.error(f"Failed to load files: {e}")
            show_error("Error", f"Failed to load files:\n{e}")
            self.match_button.setEnabled(True)
            self.info_label.setText("Error loading files")
            return

        params = {
            'TOLERANCE': self.tolerance_control.value(),
            'MIN_SCORE_THRESHOLD': self.threshold_control.value(),
        }
        self.matcher = NISTMatcher(params)

        if len(self.nist_dbs) == 1:
            # Single DB — use the straightforward path
            self.info_label.setText("Matching peaks against 1 database…")
            self.worker_thread = WorkerThread(
                self.matcher.match_peaks, self.detected_peaks, self.nist_dbs[0])
            self.worker_thread.finished.connect(self._on_single_match_finished)
        else:
            # Multiple DBs — use match_multiple_databases
            self.info_label.setText(
                f"Matching peaks against {len(self.nist_dbs)} databases…")
            self.worker_thread = WorkerThread(
                self.matcher.match_multiple_databases,
                self.detected_peaks, self.nist_dbs)
            self.worker_thread.finished.connect(self._on_multi_match_finished)

        self.worker_thread.error.connect(self._on_matching_error)
        self.worker_thread.start()

    def _on_single_match_finished(self, result: dict):
        """Handle result from match_peaks (returns list of NISTMatch)."""
        self.matches = result.get('result')
        if self.matches:
            logger.info(f"Matching complete: {len(self.matches)} results")
            try:
                from src.gui.session_manager import save_step3
                save_step3(self.matches)
            except Exception:
                pass
            self._update_table()
            self._update_charts()
            identified = [m for m in self.matches if m.element]
            self.info_label.setText(
                f"Matched: {len(identified)} of {len(self.matches)} peaks identified")
            self.save_button.setEnabled(True)
        else:
            self.info_label.setText("No matches found")
        self.match_button.setEnabled(True)

    def _on_multi_match_finished(self, result: dict):
        """
        Handle result from match_multiple_databases (returns a DataFrame).
        Convert it back to a list of NISTMatch objects so the rest of the
        widget (table, charts, save) stays unchanged.
        """
        from src.io.data_models import NISTMatch
        import pandas as pd

        df = result.get('result')
        if df is None or (hasattr(df, 'empty') and df.empty):
            self.info_label.setText("No matches found")
            self.match_button.setEnabled(True)
            return

        self.matches = []
        for _, row in df.iterrows():
            self.matches.append(NISTMatch(
                observed_wl=row.get('Observed_WL', 0.0),
                matched_wl=row.get('Matched_WL') if pd.notna(row.get('Matched_WL')) else None,
                delta=row.get('Delta') if pd.notna(row.get('Delta')) else None,
                aki=row.get('Aki', 0.0) or 0.0,
                relative_intensity=row.get('relative_intensity', 0.0) or 0.0,
                score=row.get('Score', 0.0) or 0.0,
                element=row.get('Element') if pd.notna(row.get('Element')) else None,
            ))

        logger.info(f"Multi-DB matching complete: {len(self.matches)} results")
        try:
            from src.gui.session_manager import save_step3
            save_step3(self.matches)
        except Exception:
            pass
        self._update_table()
        self._update_charts()
        identified = [m for m in self.matches if m.element]
        self.info_label.setText(
            f"Matched across {len(self.nist_dbs)} databases: "
            f"{len(identified)} of {len(self.matches)} peaks identified")
        self.save_button.setEnabled(True)
        self.match_button.setEnabled(True)

    def _on_matching_error(self, error: str):
        logger.error(f"Matching error: {error}")
        show_error("Matching Error", f"Peak matching failed:\n{error}")
        self.info_label.setText("Error during matching")
        self.match_button.setEnabled(True)

    # ──────────────────────────────────────────────────────────────────────
    # Table & charts
    # ──────────────────────────────────────────────────────────────────────

    def _update_table(self):
        if self.matches is None:
            return
        matched_only = self.matched_only_cb.isChecked()
        rows = [m for m in self.matches if not matched_only or m.element]
        self.table.setRowCount(len(rows))
        for i, m in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(f"{m.observed_wl:.5f}"))
            self.table.setItem(i, 1, QTableWidgetItem(
                f"{m.matched_wl:.5f}" if m.matched_wl else "—"))
            self.table.setItem(i, 2, QTableWidgetItem(
                f"{m.delta:.4f}" if m.delta is not None else "—"))
            self.table.setItem(i, 3, QTableWidgetItem(
                m.element if m.element else "—"))
            self.table.setItem(i, 4, QTableWidgetItem(
                f"{m.aki:.2e}" if m.aki else "—"))
            self.table.setItem(i, 5, QTableWidgetItem(
                f"{m.relative_intensity:.1f}" if m.relative_intensity else "—"))
            self.table.setItem(i, 6, QTableWidgetItem(
                f"{m.score:.2e}" if m.score else "—"))

    def _on_filter_toggled(self):
        """Re-render the table when the matched-only checkbox is toggled."""
        self._update_table()

    def _update_charts(self):
        if not self.matches:
            return
        self.freq_fig.clear()
        ax_freq = self.freq_fig.add_subplot(111)
        ChartEngine.render_element_frequency_chart(ax_freq, self.matches)
        self.freq_canvas.draw()
        self.freq_toolbar.home()

        self.score_fig.clear()
        ax_score = self.score_fig.add_subplot(111)
        ChartEngine.render_match_score_scatter(ax_score, self.matches)
        self.score_canvas.draw()
        self.score_toolbar.home()

    # ──────────────────────────────────────────────────────────────────────
    # Save
    # ──────────────────────────────────────────────────────────────────────

    def _on_save_clicked(self):
        if self.matches is None:
            show_error("Error", "No matches to save")
            return

        save_dir = QFileDialog.getExistingDirectory(
            self, "Select Save Directory", str(Path.home()))
        if not save_dir:
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # ── Single DB: save one combined file ──────────────────────────────
        if len(self.nist_paths) <= 1:
            filename = f"LIBS_matching_results_{ts}.csv"
            filepath = str(Path(save_dir) / filename)
            try:
                writer = CSVWriter()
                writer.write_nist_matches(filepath, self.matches)
                logger.info(f"Saved matching results to {filepath}")
                show_info("Saved", f"Results saved to:\n{save_dir}\n\n  {filename}")
            except Exception as e:
                logger.error(f"Failed to save results: {e}")
                show_error("Error", f"Failed to save results:\n{e}")
            return

        # ── Multiple DBs: save one file per database ───────────────────────
        # Re-run the match per-DB so we can write separate files.
        # (self.matches is the merged preview; we need per-element splits.)
        try:
            reader = CSVReader()
            params = {
                'TOLERANCE': self.tolerance_control.value(),
                'MIN_SCORE_THRESHOLD': self.threshold_control.value(),
            }
            matcher = NISTMatcher(params)
            saved_files = []

            for fp in self.nist_paths:
                db = reader.read_nist_database(fp)
                per_db_matches = matcher.match_peaks(self.detected_peaks, db)

                # Derive a clean stem from the DB filename
                stem = Path(fp).stem  # e.g. "NIST-Ca"
                filename = f"LIBS_matching_results_{stem}_{ts}.csv"
                out_path = str(Path(save_dir) / filename)

                writer = CSVWriter()
                writer.write_nist_matches(out_path, per_db_matches)
                saved_files.append(filename)
                logger.info(f"Saved per-DB results: {out_path}")

            files_list = "\n  ".join(saved_files)
            show_info(
                "Saved",
                f"One file saved per NIST database in:\n{save_dir}\n\n  {files_list}\n\n"
                "ℹ Load all of these files together in Step 4."
            )

        except Exception as e:
            logger.error(f"Failed to save per-DB results: {e}")
            show_error("Error", f"Failed to save results:\n{e}")
