# -*- coding: utf-8 -*-
"""
Step 3 Widget - NIST Element Identification

Two-column layout: scrollable controls on the left, charts + table on the right.

NIST database source options:
  1. Built-in  — auto-loaded from the bundled 'NIST database' folder.
     • Separate Neutral Lines (I) and Ionic Lines (II) toggle buttons.
     • Searchable per-element checklist.
  2. Custom    — manual file upload for external / user-supplied CSVs.

Both modes can be active simultaneously; their DataFrames are merged before
matching.
"""

from pathlib import Path
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea,
    QFileDialog, QListWidget, QListWidgetItem, QAbstractItemView, QCheckBox,
    QTabWidget, QLineEdit, QFrame, QSizePolicy, QButtonGroup, QToolButton,
    QSplitter,
)
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from src import setup_logger
from src.config import STEP3_PARAMS
from src.core.step3_nist_matching import NISTMatcher
from src.io.file_reader import CSVReader
from src.io.file_writer import CSVWriter
from src.io.data_models import NISTMatch
from src.gui.gui_utils import (
    HighDpiToolbar as NavigationToolbar2QT,
    style_toolbar,
    ParameterControl, WorkerThread, FileHistory, RecentFilesButton,
    show_error, show_info,
    make_table_toolbar, on_copy_table_clicked,
)
from src.gui.charts import ChartEngine
from src.gui.theme import (
    primary_button_style, secondary_button_style, instruction_banner_style,
    step_title_font, get_chart_bg,
)

logger = setup_logger(__name__)


# ── Lazy loader thread ────────────────────────────────────────────────────────

class _LoaderThread(QThread):
    """Background thread that initialises NISTDatabaseLoader without blocking UI."""
    ready  = pyqtSignal(object)   # emits the loader instance
    failed = pyqtSignal(str)      # emits error message

    def run(self):
        try:
            from src.io.nist_loader import NISTDatabaseLoader
            loader = NISTDatabaseLoader()
            self.ready.emit(loader)
        except Exception as exc:
            self.failed.emit(str(exc))


# ── Element checklist widget ──────────────────────────────────────────────────

class _ElementChecklist(QWidget):
    """
    Searchable, scrollable checklist of element names.
    Supports Select All / Clear All and emits selectionChanged on any toggle.
    """
    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍 Filter elements…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        # Select / Clear row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self._select_all_btn = QPushButton("All")
        self._select_all_btn.setFixedHeight(22)
        self._select_all_btn.clicked.connect(self._select_all)
        self._clear_btn = QPushButton("None")
        self._clear_btn.setFixedHeight(22)
        self._clear_btn.clicked.connect(self._clear_all)
        self._count_label = QLabel("0 selected")
        self._count_label.setStyleSheet("font-size: 10px; color: grey;")
        btn_row.addWidget(self._select_all_btn)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._count_label)
        layout.addLayout(btn_row)

        # List
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._list.setMaximumHeight(160)
        self._list.setMinimumHeight(100)
        layout.addWidget(self._list)

        self._all_elements: List[str] = []

    # ── Public methods ────────────────────────────────────────────────────

    def populate(self, elements: List[str]):
        """Replace the element list (clears any existing selection)."""
        self._all_elements = sorted(elements)
        self._rebuild_list(self._all_elements)

    def selected_elements(self) -> List[str]:
        checked = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked.append(item.text())
        return checked

    # ── Internal helpers ──────────────────────────────────────────────────

    def _rebuild_list(self, elements: List[str]):
        self._list.blockSignals(True)
        self._list.clear()
        for name in elements:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._list.addItem(item)
        self._list.blockSignals(False)
        self._update_count()
        # Connect check-state changes
        self._list.itemChanged.connect(self._on_item_changed)

    def _apply_filter(self, text: str):
        t = text.lower()
        filtered = [e for e in self._all_elements if t in e.lower()] if t else self._all_elements
        # Preserve checked state across filter rebuilds
        prev_checked = set(self.selected_elements())
        self._list.itemChanged.disconnect()
        self._list.blockSignals(True)
        self._list.clear()
        for name in filtered:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            state = Qt.CheckState.Checked if name in prev_checked else Qt.CheckState.Unchecked
            item.setCheckState(state)
            self._list.addItem(item)
        self._list.blockSignals(False)
        self._list.itemChanged.connect(self._on_item_changed)
        self._update_count()

    def _select_all(self):
        self._list.itemChanged.disconnect()
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Checked)
        self._list.blockSignals(False)
        self._list.itemChanged.connect(self._on_item_changed)
        self._update_count()
        self.selectionChanged.emit()

    def _clear_all(self):
        self._list.itemChanged.disconnect()
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._list.blockSignals(False)
        self._list.itemChanged.connect(self._on_item_changed)
        self._update_count()
        self.selectionChanged.emit()

    def _on_item_changed(self, _item):
        self._update_count()
        self.selectionChanged.emit()

    def _update_count(self):
        n = len(self.selected_elements())
        self._count_label.setText(f"{n} selected")


# ── Main widget ───────────────────────────────────────────────────────────────

class Step3Widget(QWidget):
    """
    UI widget for Step 3: NIST Element Identification.

    Left panel (scrollable, ≤370 px):
      - Instructions
      - Detected Peaks file selector
      - Built-in NIST Database group (Neutral / Ionic toggles + element lists)
      - Custom Database group (manual file upload, collapsible)
      - Parameters
      - Action buttons + status label

    Right panel (stretches):
      - Tabs: Element Frequency chart | Match Score Scatter | Results Table
    """

    # Emitted after successful matching — carries list[NISTMatch]
    # so Step 4 can receive results directly without a file round-trip.
    result_ready = pyqtSignal(object)

    def __init__(self, file_history=None, notes_panel=None):
        super().__init__()
        self.detected_peaks   = None
        self.matches: Optional[List[NISTMatch]] = None
        self.matcher          = None
        self.worker_thread    = None
        self.file_history     = file_history
        self.notes_panel      = notes_panel

        # NIST loader (populated by background thread)
        self._nist_loader     = None
        self._loader_thread   = None

        # Manual-upload paths (custom DB, kept for power users)
        self._custom_paths: List[str] = []
        # Detected peaks files (multi-file)
        self._peaks_paths: List[str] = []

        # Persistent recent-file histories (role-scoped, survive app restarts)
        # We always create our own role-scoped instances so histories are
        # separated by use-case regardless of what file_history is passed in.
        self._peaks_history  = FileHistory(role="peaks")
        self._custom_history = FileHistory(role="nist_custom")

        logger.info("Initialising Step 3 widget")
        self._build_ui()

        # Start loading the built-in databases in the background
        self._start_loader()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._create_left_panel(), stretch=0)
        main_layout.addWidget(self._create_right_panel(), stretch=1)

    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Title
        title = QLabel("Step 3: NIST Element Identification")
        title.setStyleSheet(step_title_font(13))
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        self._title_label = title

        # Instructions
        instructions = QLabel(
            "📋 Instructions:\n"
            "1. Add one or more detected peaks CSVs from Step 2.\n"
            "   Peaks from all files are merged before matching.\n"
            "2. Choose Built-in database lines:\n"
            "   • Toggle Neutral (I) and/or Ionic (II).\n"
            "   • Select specific elements, or leave all checked.\n"
            "3. Optionally add custom CSV/XLSX files.\n"
            "4. Set Tolerance and Min Score.\n"
            "5. Click 'Match Peaks'.\n"
            "6. Matches are automatically forwarded to Step 4 in-memory (exporting CSV is optional)."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(instruction_banner_style())
        layout.addWidget(instructions)
        self._instructions_label = instructions

        # Detected peaks files (multi)
        peaks_group = QGroupBox("Detected Peaks Files")
        pg = QVBoxLayout()
        pg.setContentsMargins(6, 6, 6, 6)
        pg.setSpacing(4)

        self._peaks_list_widget = QListWidget()
        self._peaks_list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._peaks_list_widget.setMaximumHeight(75)
        self._peaks_list_widget.setToolTip(
            "Each file's peaks are combined before matching.\n"
            "Select items then click Remove to delete.")
        pg.addWidget(self._peaks_list_widget)

        peaks_btn_row = QHBoxLayout()
        peaks_btn_row.setSpacing(4)
        add_peaks_btn = QPushButton("Add File(s)…")
        add_peaks_btn.clicked.connect(self._on_add_peaks_files)
        peaks_btn_row.addWidget(add_peaks_btn)
        rem_peaks_btn = QPushButton("Remove")
        rem_peaks_btn.clicked.connect(self._on_remove_peaks_files)
        peaks_btn_row.addWidget(rem_peaks_btn)
        clr_peaks_btn = QPushButton("Clear")
        clr_peaks_btn.clicked.connect(self._on_clear_peaks_files)
        peaks_btn_row.addWidget(clr_peaks_btn)
        pg.addLayout(peaks_btn_row)

        # Recent files row — shows previously used peaks files
        recent_peaks_row = QHBoxLayout()
        recent_peaks_row.setSpacing(4)
        self._peaks_recent_btn = RecentFilesButton(self._peaks_history)
        self._peaks_recent_btn.file_selected.connect(self._on_recent_peaks_selected)
        recent_peaks_row.addWidget(self._peaks_recent_btn)
        recent_peaks_row.addStretch()
        pg.addLayout(recent_peaks_row)

        self._peaks_count_label = QLabel("No peaks files loaded")
        self._peaks_count_label.setStyleSheet("font-size: 10px; color: grey;")
        pg.addWidget(self._peaks_count_label)

        peaks_group.setLayout(pg)
        layout.addWidget(peaks_group)

        # Built-in database group
        layout.addWidget(self._create_builtin_group())

        # Custom database group (collapsible)
        layout.addWidget(self._create_custom_group())

        # Parameters
        params_group = QGroupBox("Parameters")
        pl = QVBoxLayout()
        pl.setContentsMargins(6, 6, 6, 6)
        self.tolerance_control = ParameterControl(
            "Tolerance (nm)", 0.01, 1.0, STEP3_PARAMS["TOLERANCE"],
            step=0.01, decimals=3)
        pl.addWidget(self.tolerance_control)
        self.threshold_control = ParameterControl(
            "Min Score", 0, 1e10, STEP3_PARAMS["MIN_SCORE_THRESHOLD"],
            step=1e6, decimals=0)
        pl.addWidget(self.threshold_control)
        params_group.setLayout(pl)
        layout.addWidget(params_group)

        # ── Selected Elements summary ─────────────────────────────────────
        self._sel_group = QGroupBox("Selected Elements")
        sel_layout = QVBoxLayout(self._sel_group)
        sel_layout.setContentsMargins(6, 6, 6, 6)
        sel_layout.setSpacing(4)

        # Counter row
        sel_header = QHBoxLayout()
        self._sel_count_label = QLabel("No elements selected")
        self._sel_count_label.setStyleSheet("font-size: 10px; font-weight: bold;")
        sel_header.addWidget(self._sel_count_label)
        sel_header.addStretch()

        # Toggle to expand/collapse the list
        self._sel_toggle_btn = QPushButton("▶ Show")
        self._sel_toggle_btn.setFixedHeight(20)
        self._sel_toggle_btn.setFixedWidth(60)
        self._sel_toggle_btn.setStyleSheet(
            "QPushButton { font-size: 9px; padding: 0 4px; }"
        )
        self._sel_toggle_btn.clicked.connect(self._on_toggle_sel_list)
        sel_header.addWidget(self._sel_toggle_btn)
        sel_layout.addLayout(sel_header)

        # Scrollable tag area (collapsed by default)
        self._sel_list_frame = QFrame()
        self._sel_list_frame.setVisible(False)
        tags_layout = QVBoxLayout(self._sel_list_frame)
        tags_layout.setContentsMargins(0, 2, 0, 0)
        tags_layout.setSpacing(2)

        self._sel_list_widget = QListWidget()
        self._sel_list_widget.setMaximumHeight(120)
        self._sel_list_widget.setMinimumHeight(60)
        self._sel_list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self._sel_list_widget.setStyleSheet("font-size: 9pt;")
        tags_layout.addWidget(self._sel_list_widget)

        sel_layout.addWidget(self._sel_list_frame)
        layout.addWidget(self._sel_group)

        # Action buttons
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

        # Reset button on its own row so it's visually distinct
        reset_row = QHBoxLayout()
        self.reset_button = QPushButton("✕  Reset")
        self.reset_button.setStyleSheet(secondary_button_style())
        self.reset_button.setToolTip(
            "Clear all selections, results, and charts.\n"
            "Database elements stay loaded — just untoggled."
        )
        self.reset_button.clicked.connect(self._on_reset_clicked)
        reset_row.addWidget(self.reset_button)
        reset_row.addStretch()
        layout.addLayout(reset_row)

        self.info_label = QLabel("Loading built-in NIST database…")
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

    def _create_builtin_group(self) -> QGroupBox:
        """Built-in NIST database selector with Neutral/Ionic toggles."""
        group = QGroupBox("Built-in NIST Database")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(6)

        # ── Loading status banner ─────────────────────────────────────────
        self._db_status_label = QLabel("⏳ Loading database…")
        self._db_status_label.setWordWrap(True)
        self._db_status_label.setStyleSheet(
            "font-size: 10px; color: #888; padding: 2px;")
        layout.addWidget(self._db_status_label)

        # ── Open folder + Refresh row ─────────────────────────────────────
        folder_row = QHBoxLayout()
        folder_row.setSpacing(4)

        self._open_folder_btn = QPushButton("📂 Open Database Folder")
        self._open_folder_btn.setToolTip(
            "Open the NIST database folder in File Explorer.\n"
            "Drop new CSV or XLSX files into 'Neutral lines' or 'Ionic lines'\n"
            "and click Refresh — the software will pick them up automatically."
        )
        self._open_folder_btn.setFixedHeight(24)
        self._open_folder_btn.clicked.connect(self._on_open_db_folder)
        folder_row.addWidget(self._open_folder_btn)

        self._refresh_btn = QPushButton("🔄 Refresh DB")
        self._refresh_btn.setToolTip(
            "Rescan the database folder and rebuild the cache.\n"
            "Use after adding or removing element files."
        )
        self._refresh_btn.setFixedHeight(24)
        self._refresh_btn.clicked.connect(self._on_refresh_db)
        folder_row.addWidget(self._refresh_btn)

        layout.addLayout(folder_row)

        # ── Line-type toggle buttons ──────────────────────────────────────
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(4)

        self._neutral_btn = QPushButton("Neutral Lines (I)")
        self._neutral_btn.setCheckable(True)
        self._neutral_btn.setChecked(False)
        self._neutral_btn.setToolTip("Load neutral atomic lines from the built-in database")
        self._neutral_btn.toggled.connect(self._on_neutral_toggled)
        toggle_row.addWidget(self._neutral_btn)

        self._ionic_btn = QPushButton("Ionic Lines (II)")
        self._ionic_btn.setCheckable(True)
        self._ionic_btn.setChecked(False)
        self._ionic_btn.setToolTip("Load singly-ionised lines from the built-in database")
        self._ionic_btn.toggled.connect(self._on_ionic_toggled)
        toggle_row.addWidget(self._ionic_btn)

        layout.addLayout(toggle_row)

        # ── Neutral element checklist ─────────────────────────────────────
        self._neutral_frame = QFrame()
        nf_layout = QVBoxLayout(self._neutral_frame)
        nf_layout.setContentsMargins(0, 2, 0, 0)
        nf_layout.setSpacing(2)
        neutral_lbl = QLabel("Neutral elements:")
        neutral_lbl.setStyleSheet("font-size: 10px; font-weight: bold;")
        nf_layout.addWidget(neutral_lbl)
        self._neutral_list = _ElementChecklist()
        self._neutral_list.selectionChanged.connect(self._update_db_status)
        self._neutral_list.selectionChanged.connect(self._update_selected_elements)
        nf_layout.addWidget(self._neutral_list)
        self._neutral_frame.setVisible(False)
        layout.addWidget(self._neutral_frame)

        # ── Ionic element checklist ───────────────────────────────────────
        self._ionic_frame = QFrame()
        if_layout = QVBoxLayout(self._ionic_frame)
        if_layout.setContentsMargins(0, 2, 0, 0)
        if_layout.setSpacing(2)
        ionic_lbl = QLabel("Ionic elements:")
        ionic_lbl.setStyleSheet("font-size: 10px; font-weight: bold;")
        if_layout.addWidget(ionic_lbl)
        self._ionic_list = _ElementChecklist()
        self._ionic_list.selectionChanged.connect(self._update_db_status)
        self._ionic_list.selectionChanged.connect(self._update_selected_elements)
        if_layout.addWidget(self._ionic_list)
        self._ionic_frame.setVisible(False)
        layout.addWidget(self._ionic_frame)

        return group

    def _create_custom_group(self) -> QGroupBox:
        """Collapsible group for manual file uploads."""
        group = QGroupBox("Custom Database Files  (optional)")
        group.setCheckable(True)
        group.setChecked(False)
        group.setToolTip(
            "Upload your own CSV / XLSX files to supplement or replace "
            "the built-in database."
        )
        layout = QVBoxLayout(group)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._custom_list_widget = QListWidget()
        self._custom_list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._custom_list_widget.setMaximumHeight(70)
        layout.addWidget(self._custom_list_widget)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add File(s)…")
        add_btn.clicked.connect(self._on_add_custom_files)
        btn_row.addWidget(add_btn)
        rem_btn = QPushButton("Remove")
        rem_btn.clicked.connect(self._on_remove_custom_files)
        btn_row.addWidget(rem_btn)
        clr_btn = QPushButton("Clear")
        clr_btn.clicked.connect(self._on_clear_custom_files)
        btn_row.addWidget(clr_btn)
        layout.addLayout(btn_row)

        # Recent files row for custom database files
        recent_custom_row = QHBoxLayout()
        self._custom_recent_btn = RecentFilesButton(self._custom_history)
        self._custom_recent_btn.file_selected.connect(self._on_recent_custom_selected)
        recent_custom_row.addWidget(self._custom_recent_btn)
        recent_custom_row.addStretch()
        layout.addLayout(recent_custom_row)

        return group

    def _create_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        chart_bg = get_chart_bg()
        self.chart_tabs = QTabWidget()

        # Tab 1 — Element Frequency
        self.freq_fig = Figure(figsize=(5, 3), dpi=100)
        self.freq_fig.patch.set_facecolor(chart_bg)
        self.freq_canvas = FigureCanvasQTAgg(self.freq_fig)
        self.freq_canvas.setStyleSheet(f"background-color: {chart_bg};")
        self.freq_toolbar = NavigationToolbar2QT(self.freq_canvas)
        freq_w = QWidget()
        fl = QVBoxLayout(freq_w)
        fl.setContentsMargins(0, 0, 0, 0); fl.setSpacing(2)
        fl.addWidget(self.freq_canvas); fl.addWidget(self.freq_toolbar)
        self.chart_tabs.addTab(freq_w, "Element Frequency")

        # Tab 2 — Match Score Scatter
        self.score_fig = Figure(figsize=(5, 3), dpi=100)
        self.score_fig.patch.set_facecolor(chart_bg)
        self.score_canvas = FigureCanvasQTAgg(self.score_fig)
        self.score_canvas.setStyleSheet(f"background-color: {chart_bg};")
        self.score_toolbar = NavigationToolbar2QT(self.score_canvas)
        score_w = QWidget()
        sl = QVBoxLayout(score_w)
        sl.setContentsMargins(0, 0, 0, 0); sl.setSpacing(2)
        sl.addWidget(self.score_canvas); sl.addWidget(self.score_toolbar)
        self.chart_tabs.addTab(score_w, "Match Score Scatter")

        self._show_placeholders()

        # Tab 3 — Results Table
        table_tab = QWidget()
        ttl = QVBoxLayout(table_tab)
        ttl.setContentsMargins(4, 2, 4, 4); ttl.setSpacing(4)

        # Filter checkbox row
        filter_row = QHBoxLayout()
        self.matched_only_cb = QCheckBox("Show matched peaks only")
        self.matched_only_cb.setChecked(False)
        self.matched_only_cb.toggled.connect(self._on_filter_toggled)
        filter_row.addWidget(self.matched_only_cb)
        filter_row.addStretch()
        ttl.addLayout(filter_row)

        # Table with copy toolbar
        self.table = self._create_results_table()
        _tbl_container, self._table_copy_btn, self._table_row_label = \
            make_table_toolbar(self.table, row_label_text="— rows")
        self._table_copy_btn.clicked.connect(
            lambda: on_copy_table_clicked(
                self.table, self._table_copy_btn, self._table_row_label
            )
        )
        ttl.addWidget(_tbl_container)
        self.chart_tabs.addTab(table_tab, "📋 Results Table")

        layout.addWidget(self.chart_tabs)
        return panel

    def _create_results_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            "Observed (nm)", "Matched (nm)", "Delta (nm)", "Element",
            "Aki", "Rel. Int.", "Score",
        ])
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    # ── Built-in loader lifecycle ─────────────────────────────────────────────

    def _start_loader(self):
        """Kick off background loading of the built-in NIST databases."""
        self._loader_thread = _LoaderThread()
        self._loader_thread.ready.connect(self._on_loader_ready)
        self._loader_thread.failed.connect(self._on_loader_failed)
        self._loader_thread.start()

    def _on_loader_ready(self, loader):
        """Called on the GUI thread once the loader is ready."""
        self._nist_loader = loader
        n_elem = loader.element_count("neutral")
        i_elem = loader.element_count("ionic")
        n_rows = loader.row_count("neutral")
        i_rows = loader.row_count("ionic")

        # Populate checklists
        self._neutral_list.populate(loader.list_elements("neutral"))
        self._ionic_list.populate(loader.list_elements("ionic"))

        self._db_status_label.setText(
            f"✅ Ready — {n_elem} neutral elements ({n_rows:,} lines)\n"
            f"   {i_elem} ionic elements ({i_rows:,} lines)\n"
            f"Toggle buttons above to activate."
        )
        self._db_status_label.setStyleSheet(
            "font-size: 10px; color: #4CAF50; padding: 2px;")
        self.info_label.setText("Ready — select elements and match peaks.")
        logger.info(
            f"Built-in NIST DB ready: neutral={n_elem} elements / {n_rows} rows, "
            f"ionic={i_elem} elements / {i_rows} rows"
        )

    def _on_loader_failed(self, err: str):
        self._db_status_label.setText(f"⚠ Database load failed: {err}")
        self._db_status_label.setStyleSheet(
            "font-size: 10px; color: #F44336; padding: 2px;")
        self.info_label.setText(
            "Built-in database unavailable. Use Custom Database files.")
        logger.error(f"NISTDatabaseLoader failed: {err}")

    # ── Open folder / Refresh handlers ───────────────────────────────────────

    def _on_open_db_folder(self):
        """Open the NIST database folder in the system file explorer."""
        import subprocess
        if self._nist_loader is not None:
            folder = self._nist_loader.db_folder()
        else:
            # Loader not ready yet — open best-guess path
            from src.io.nist_loader import _NIST_ROOT
            folder = _NIST_ROOT

        if not folder.exists():
            show_error(
                "Folder Not Found",
                f"Database folder does not exist:\n{folder}\n\n"
                "This should not happen. Check the installation."
            )
            return

        try:
            # Windows: explorer opens the folder and selects nothing
            subprocess.Popen(f'explorer "{folder}"')
        except Exception as exc:
            logger.warning(f"Could not open folder: {exc}")
            show_info("Database Folder", str(folder))

    def _on_refresh_db(self):
        """Force-rebuild the cache and repopulate element checklists."""
        if self._nist_loader is None:
            # Loader hasn't finished initial load yet — restart it
            self._start_loader()
            return

        self._db_status_label.setText("⏳ Rebuilding database cache…")
        self._db_status_label.setStyleSheet(
            "font-size: 10px; color: #888; padding: 2px;")
        self._refresh_btn.setEnabled(False)
        self._open_folder_btn.setEnabled(False)

        # Run rebuild in background so the UI stays responsive
        class _RebuildThread(QThread):
            done   = pyqtSignal(object)
            failed = pyqtSignal(str)
            def __init__(self, loader):
                super().__init__()
                self._loader = loader
            def run(self):
                try:
                    self._loader.force_rebuild()
                    self.done.emit(self._loader)
                except Exception as exc:
                    self.failed.emit(str(exc))

        self._rebuild_thread = _RebuildThread(self._nist_loader)
        self._rebuild_thread.done.connect(self._on_loader_ready)
        self._rebuild_thread.done.connect(
            lambda _: self._refresh_btn.setEnabled(True))
        self._rebuild_thread.done.connect(
            lambda _: self._open_folder_btn.setEnabled(True))
        self._rebuild_thread.failed.connect(self._on_loader_failed)
        self._rebuild_thread.failed.connect(
            lambda _: self._refresh_btn.setEnabled(True))
        self._rebuild_thread.start()

    # ── Toggle handlers ───────────────────────────────────────────────────────

    def _on_neutral_toggled(self, checked: bool):
        self._neutral_frame.setVisible(checked)
        self._update_db_status()
        self._update_selected_elements()

    def _on_ionic_toggled(self, checked: bool):
        self._ionic_frame.setVisible(checked)
        self._update_db_status()
        self._update_selected_elements()

    def _update_db_status(self):
        """Refresh the status label to reflect current selection counts."""
        if self._nist_loader is None:
            return
        n_total = self._nist_loader.element_count("neutral")
        i_total = self._nist_loader.element_count("ionic")
        n_rows  = self._nist_loader.row_count("neutral")
        i_rows  = self._nist_loader.row_count("ionic")

        neutral_on = self._neutral_btn.isChecked()
        ionic_on   = self._ionic_btn.isChecked()

        if not neutral_on and not ionic_on:
            self._db_status_label.setText(
                f"ℹ Toggle Neutral / Ionic to activate.\n"
                f"Available: {n_total} neutral elements ({n_rows:,} lines), "
                f"{i_total} ionic elements ({i_rows:,} lines)"
            )
            self._db_status_label.setStyleSheet(
                "font-size: 10px; color: #888; padding: 2px;")
            return

        parts = []
        if neutral_on:
            n_sel = len(self._neutral_list.selected_elements())
            label = f"{n_sel}/{n_total} neutral" if n_sel else f"all {n_total} neutral"
            parts.append(f"{label} ({n_rows:,} lines)")
        if ionic_on:
            i_sel = len(self._ionic_list.selected_elements())
            label = f"{i_sel}/{i_total} ionic" if i_sel else f"all {i_total} ionic"
            parts.append(f"{label} ({i_rows:,} lines)")

        self._db_status_label.setText("✅ Active: " + "\n         ".join(parts))
        self._db_status_label.setStyleSheet(
            "font-size: 10px; color: #4CAF50; padding: 2px;")

    def _update_selected_elements(self):
        """Refresh the Selected Elements summary panel."""
        entries: List[tuple[str, str]] = []  # (element, type_tag)

        if self._neutral_btn.isChecked():
            for el in self._neutral_list.selected_elements():
                entries.append((el, "I"))

        if self._ionic_btn.isChecked():
            for el in self._ionic_list.selected_elements():
                # Avoid duplicating elements already listed as neutral
                if not any(e == el and t == "I" for e, t in entries):
                    entries.append((el, "II"))
                else:
                    # Element has both neutral and ionic selected — mark it
                    entries = [(e, "I+II") if e == el and t == "I" else (e, t)
                               for e, t in entries]

        n = len(entries)
        if n == 0:
            self._sel_count_label.setText("No elements selected")
            self._sel_count_label.setStyleSheet("font-size: 10px; font-weight: bold; color: grey;")
        else:
            self._sel_count_label.setText(f"{n} element{'s' if n != 1 else ''} selected")
            self._sel_count_label.setStyleSheet(
                "font-size: 10px; font-weight: bold; color: #4CAF50;")

        # Rebuild the list widget
        self._sel_list_widget.clear()
        for el, tag in sorted(entries, key=lambda x: x[0]):
            tag_colour = {
                "I":    "#3FA9F5",   # blue  — neutral
                "II":   "#3DDC97",   # teal  — ionic
                "I+II": "#F4B942",   # amber — both
            }.get(tag, "#AEB7C4")
            item = QListWidgetItem(f"  {el}  ({tag})")
            item.setForeground(__import__('PyQt6.QtGui', fromlist=['QColor']).QColor(tag_colour))
            self._sel_list_widget.addItem(item)

    def _on_toggle_sel_list(self):
        """Expand / collapse the selected-elements list."""
        visible = not self._sel_list_frame.isVisible()
        self._sel_list_frame.setVisible(visible)
        self._sel_toggle_btn.setText("▼ Hide" if visible else "▶ Show")

    # ── Peaks file management ─────────────────────────────────────────────────

    def _on_add_peaks_files(self):
        recent = self._peaks_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Detected Peaks File(s)", start_dir,
            "CSV Files (*.csv)"
        )
        for fp in files:
            if fp not in self._peaks_paths:
                self._peaks_paths.append(fp)
                self._peaks_list_widget.addItem(QListWidgetItem(Path(fp).name))
                self._peaks_history.add_file(fp)
        self._peaks_recent_btn.refresh()
        self._refresh_peaks_label()

    def _on_recent_peaks_selected(self, path_str: str):
        """Add a recently-used peaks file from the dropdown."""
        if path_str not in self._peaks_paths:
            self._peaks_paths.append(path_str)
            self._peaks_list_widget.addItem(QListWidgetItem(Path(path_str).name))
            self._peaks_history.add_file(path_str)
        self._peaks_recent_btn.refresh()
        self._refresh_peaks_label()

    def _on_remove_peaks_files(self):
        rows = sorted(
            [self._peaks_list_widget.row(i)
             for i in self._peaks_list_widget.selectedItems()],
            reverse=True,
        )
        for r in rows:
            self._peaks_list_widget.takeItem(r)
            self._peaks_paths.pop(r)
        self._refresh_peaks_label()

    def _on_clear_peaks_files(self):
        self._peaks_paths.clear()
        self._peaks_list_widget.clear()
        self._refresh_peaks_label()

    def _refresh_peaks_label(self):
        n = len(self._peaks_paths)
        if n == 0:
            self._peaks_count_label.setText("No peaks files loaded")
            self._peaks_count_label.setStyleSheet("font-size: 10px; color: grey;")
        else:
            self._peaks_count_label.setText(f"✅ {n} file{'s' if n > 1 else ''} queued")
            self._peaks_count_label.setStyleSheet("font-size: 10px; color: #4CAF50;")

    # ── Custom file management ────────────────────────────────────────────────

    def _on_add_custom_files(self):
        recent = self._custom_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select NIST Database File(s)", start_dir,
            "Database Files (*.csv *.xlsx *.csv.xlsx)"
        )
        for fp in files:
            if fp not in self._custom_paths:
                self._custom_paths.append(fp)
                self._custom_list_widget.addItem(QListWidgetItem(Path(fp).name))
                self._custom_history.add_file(fp)
        self._custom_recent_btn.refresh()

    def _on_recent_custom_selected(self, path_str: str):
        """Add a recently-used custom DB file from the dropdown."""
        if path_str not in self._custom_paths:
            self._custom_paths.append(path_str)
            self._custom_list_widget.addItem(QListWidgetItem(Path(path_str).name))
            self._custom_history.add_file(path_str)
        self._custom_recent_btn.refresh()

    def _on_remove_custom_files(self):
        rows = sorted(
            [self._custom_list_widget.row(i)
             for i in self._custom_list_widget.selectedItems()],
            reverse=True,
        )
        for r in rows:
            self._custom_list_widget.takeItem(r)
            self._custom_paths.pop(r)

    def _on_clear_custom_files(self):
        self._custom_paths.clear()
        self._custom_list_widget.clear()

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _show_placeholders(self):
        chart_bg = get_chart_bg()
        for fig, canvas, msg in [
            (self.freq_fig, self.freq_canvas, "No data — run Element Identification"),
            (self.score_fig, self.score_canvas, "No data — run Element Identification"),
        ]:
            fig.clear()
            fig.patch.set_facecolor(chart_bg)
            canvas.setStyleSheet(f"background-color: {chart_bg};")
            ax = fig.add_subplot(111)
            ChartEngine._show_placeholder(ax, msg)
            ChartEngine.apply_dark_style(fig, ax)
            canvas.draw()

    def apply_theme(self):
        from src.gui.theme import step_title_font, instruction_banner_style
        chart_bg = get_chart_bg()
        for fig, canvas in [(self.freq_fig, self.freq_canvas),
                             (self.score_fig, self.score_canvas)]:
            fig.patch.set_facecolor(chart_bg)
            canvas.setStyleSheet(f"background-color: {chart_bg};")
        if self.matches:
            self._update_charts()
        else:
            self._show_placeholders()
        self._title_label.setStyleSheet(step_title_font(13))
        self._instructions_label.setStyleSheet(instruction_banner_style())
        style_toolbar(self.freq_toolbar)
        style_toolbar(self.score_toolbar)

    # ── Matching ──────────────────────────────────────────────────────────────

    def _on_reset_clicked(self):
        """Reset the entire Step 3 panel to its initial state."""
        # ── Input files ───────────────────────────────────────────────────
        self._on_clear_peaks_files()
        self.detected_peaks = None

        # ── Built-in database toggles + checklists ────────────────────────
        self._neutral_btn.setChecked(False)   # triggers _on_neutral_toggled → hides frame
        self._ionic_btn.setChecked(False)     # triggers _on_ionic_toggled   → hides frame
        self._neutral_list._clear_all()
        self._ionic_list._clear_all()

        # ── Custom files ──────────────────────────────────────────────────
        self._on_clear_custom_files()

        # ── Results ───────────────────────────────────────────────────────
        self.matches = None
        self.matcher = None
        self.table.setRowCount(0)
        self._table_row_label.setText("— rows")
        self._table_copy_btn.setEnabled(False)
        self._table_copy_btn.setChecked(False)
        self._table_copy_btn.setText("⎘  Copy")
        self.matched_only_cb.setChecked(False)
        self.save_button.setEnabled(False)

        # ── Selected elements panel ───────────────────────────────────────
        self._update_selected_elements()

        # ── Charts ────────────────────────────────────────────────────────
        self._show_placeholders()

        # ── Status ────────────────────────────────────────────────────────
        self.info_label.setText("Reset complete — select elements and match peaks.")
        self._update_db_status()
        logger.info("Step 3 reset to initial state.")

    def _collect_nist_dataframes(self) -> List[pd.DataFrame]:
        """
        Assemble the list of DataFrames to match against.

        Order: built-in neutral → built-in ionic → custom files.
        Returns an empty list if nothing is selected.
        """
        frames: List[pd.DataFrame] = []

        # Built-in databases
        if self._nist_loader is not None:
            if self._neutral_btn.isChecked():
                sel = self._neutral_list.selected_elements()
                df = (self._nist_loader.get_dataframe("neutral", sel if sel else None))
                if not df.empty:
                    frames.append(df)
                    logger.info(
                        f"Built-in neutral: {len(df):,} rows "
                        f"({'all' if not sel else len(sel)} elements)"
                    )

            if self._ionic_btn.isChecked():
                sel = self._ionic_list.selected_elements()
                df = self._nist_loader.get_dataframe("ionic", sel if sel else None)
                if not df.empty:
                    frames.append(df)
                    logger.info(
                        f"Built-in ionic: {len(df):,} rows "
                        f"({'all' if not sel else len(sel)} elements)"
                    )

        # Custom files
        if self._custom_paths:
            reader = CSVReader()
            for fp in self._custom_paths:
                try:
                    db = reader.read_nist_database(fp)
                    frames.append(db)
                    logger.info(f"Custom DB '{Path(fp).name}': {len(db):,} rows")
                except Exception as exc:
                    logger.warning(f"Skipping custom file {fp}: {exc}")

        return frames

    def _on_match_clicked(self):
        # Allow proceeding if peaks were loaded in-memory from Step 2
        if not self._peaks_paths and not self.detected_peaks:
            show_error("Error", "Please add at least one detected peaks file.")
            return

        # Validate that at least one NIST source is active
        builtin_active = (
            self._neutral_btn.isChecked() or self._ionic_btn.isChecked()
        )
        custom_active = bool(self._custom_paths)
        if not builtin_active and not custom_active:
            show_error(
                "No Database Selected",
                "Please toggle Neutral Lines, Ionic Lines, "
                "or add a Custom file before matching.",
            )
            return

        self.info_label.setText("Loading files…")
        self.match_button.setEnabled(False)

        # Load and merge detected peaks from all selected files
        # (skipped when peaks were already loaded in-memory from Step 2)
        if self._peaks_paths:
            try:
                reader = CSVReader()
                all_peaks = []
                for fp in self._peaks_paths:
                    peaks = reader.read_detected_peaks(fp)
                    all_peaks.extend(peaks)
                    logger.info(f"Loaded {len(peaks)} peaks from '{Path(fp).name}'")
                self.detected_peaks = all_peaks
                logger.info(f"Total detected peaks: {len(self.detected_peaks)}")
            except Exception as exc:
                logger.error(f"Failed to load peaks: {exc}")
                show_error("Error", f"Failed to load peaks file:\n{exc}")
                self.match_button.setEnabled(True)
                self.info_label.setText("Error loading peaks file.")
                return

        # Collect NIST DataFrames
        nist_dfs = self._collect_nist_dataframes()
        if not nist_dfs:
            show_error("Error", "No NIST data loaded. Check your selection.")
            self.match_button.setEnabled(True)
            self.info_label.setText("No NIST data available.")
            return

        # Merge all selected DataFrames into one for matching
        combined_df = pd.concat(nist_dfs, ignore_index=True)
        logger.info(f"Combined NIST DB: {len(combined_df):,} rows total")

        params = {
            "TOLERANCE": self.tolerance_control.value(),
            "MIN_SCORE_THRESHOLD": self.threshold_control.value(),
        }
        self.matcher = NISTMatcher(params)
        self.info_label.setText(
            f"Matching {len(self.detected_peaks)} peaks against "
            f"{len(combined_df):,} NIST lines…"
        )

        self.worker_thread = WorkerThread(
            self.matcher.match_peaks, self.detected_peaks, combined_df)
        self.worker_thread.finished.connect(self._on_match_finished)
        self.worker_thread.error.connect(self._on_matching_error)
        self.worker_thread.start()

    def _on_match_finished(self, result: dict):
        self.matches = result.get("result")
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
                f"Done: {len(identified)} of {len(self.matches)} peaks identified."
            )
            self.save_button.setEnabled(True)

            # Notify next step — pass data directly (no file round-trip)
            self.result_ready.emit(self.matches)
        else:
            self.info_label.setText("No matches found.")
        self.match_button.setEnabled(True)

    def load_from_step2(self, detected_peaks) -> None:
        """
        Auto-load Step 2 output directly into Step 3 (no file picker needed).

        detected_peaks — list[DetectedPeak] from Step 2.
        The peaks list widget is updated to show the in-memory source label.
        """
        if not detected_peaks:
            return
        # Store the peaks internally
        self.detected_peaks = detected_peaks
        n = len(detected_peaks)

        # Reflect in the UI: replace any existing file entries with an
        # in-memory sentinel so the user sees what happened.
        self._peaks_paths = []   # clear file-based paths — using in-memory data
        self._peaks_list_widget.clear()
        from PyQt6.QtWidgets import QListWidgetItem as _LWI
        sentinel = _LWI(f"← {n} peaks loaded from Step 2 (in-memory)")
        self._peaks_list_widget.addItem(sentinel)
        self._peaks_count_label.setText(f"✅ {n} peaks from Step 2")
        self._peaks_count_label.setStyleSheet("font-size: 10px; color: #4CAF50;")
        self.info_label.setText(
            f"✅ {n:,} peaks loaded from Step 2.\n"
            "Select NIST elements and click 'Match Peaks'."
        )
        logger.info("Step 3: in-memory peaks loaded from Step 2 (%d peaks)", n)

    def _on_matching_error(self, error: str):
        logger.error(f"Matching error: {error}")
        show_error("Matching Error", f"Peak matching failed:\n{error}")
        self.info_label.setText("Error during matching.")
        self.match_button.setEnabled(True)

    # ── Table & Charts ────────────────────────────────────────────────────────

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

        n = len(rows)
        self._table_row_label.setText(f"{n} row{'s' if n != 1 else ''}")
        self._table_copy_btn.setEnabled(n > 0)
        self._table_copy_btn.setChecked(False)
        self._table_copy_btn.setText("⎘  Copy")

    def _on_filter_toggled(self):
        self._update_table()

    def _update_charts(self):
        if not self.matches:
            return
        self.freq_fig.clear()
        ChartEngine.render_element_frequency_chart(
            self.freq_fig.add_subplot(111), self.matches)
        self.freq_canvas.draw()
        self.freq_toolbar.home()

        self.score_fig.clear()
        ChartEngine.render_match_score_scatter(
            self.score_fig.add_subplot(111), self.matches)
        self.score_canvas.draw()
        self.score_toolbar.home()

    # ── Save ──────────────────────────────────────────────────────────────────

    def _on_save_clicked(self):
        if self.matches is None:
            show_error("Error", "No matches to save.")
            return

        recent = self._peaks_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        save_dir = QFileDialog.getExistingDirectory(
            self, "Select Save Directory", start_dir)
        if not save_dir:
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"LIBS_matching_results_{ts}.csv"
        filepath = str(Path(save_dir) / filename)

        # Respect the "Show matched peaks only" toggle when exporting
        matched_only = self.matched_only_cb.isChecked()
        data_to_save = [m for m in self.matches if not matched_only or m.element]

        try:
            writer = CSVWriter()
            writer.write_nist_matches(filepath, data_to_save)
            logger.info(f"Saved matching results to {filepath}")
            show_info("Saved", f"Results saved to:\n{save_dir}\n\n  {filename}")
        except Exception as exc:
            logger.error(f"Failed to save results: {exc}")
            show_error("Error", f"Failed to save results:\n{exc}")
