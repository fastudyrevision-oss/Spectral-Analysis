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
    QScrollArea, QTabWidget, QProgressBar, QFileDialog, QApplication,
    QStyledItemDelegate, QStyleOptionViewItem, QComboBox,
)
from PyQt6.QtGui import QFont, QColor, QPainter, QPalette
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from src import setup_logger
from src.core.step6_performance import PerformanceCalculator
from src.gui.charts import ChartEngine
from src.gui.export_engine import export_step6_csv, export_step6_png, generate_pdf_report
from src.gui.gui_utils import HighDpiToolbar as NavigationToolbar2QT, style_toolbar, WorkerThread, show_error, show_info
from src.gui.theme import (
    primary_button_style, secondary_button_style, step_title_font, summary_banner_style,
    progress_bar_style, instruction_banner_style,
    C_BG_BASE, C_BG_RAISED, C_BG_INPUT, C_BORDER, C_ACCENT,
    C_SUCCESS, C_WARN, C_ERROR, C_TEXT, C_TEXT2, C_TEXT_MUTED,
    get_chart_bg, is_dark,
    L_SUCCESS, L_WARN, L_ERROR, L_BG_RAISED, L_TEXT2,
)

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# Item delegate — ensures per-cell foreground colours are always honoured
# even when the global QSS sets a colour on QTableWidget or its items.
# ---------------------------------------------------------------------------

class _CellColourDelegate(QStyledItemDelegate):
    """Paint table cells using the item's own Background/Foreground roles.

    Qt's stylesheet engine overrides QTableWidgetItem.setForeground() for
    normal (non-hovered, non-selected) cells because the global
    ``QWidget { color: … }`` rule cascades into table items.

    This delegate intercepts ``initStyleOption`` — which runs *after* the
    stylesheet is resolved but *before* painting — and writes the item's
    stored ForegroundRole / BackgroundRole colours directly into the
    QStyleOption palette, so they are always respected.

    Note: Qt stores colours set via setBackground/setForeground as QBrush,
    not QColor, so we call .color() to extract the QColor from the brush.
    """

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)

        bg_brush = index.data(Qt.ItemDataRole.BackgroundRole)
        fg_brush = index.data(Qt.ItemDataRole.ForegroundRole)

        if bg_brush is not None:
            colour = bg_brush.color() if hasattr(bg_brush, "color") else QColor(bg_brush)
            if colour.isValid():
                option.palette.setColor(QPalette.ColorRole.Base, colour)
                option.palette.setColor(QPalette.ColorRole.AlternateBase, colour)

        if fg_brush is not None:
            colour = fg_brush.color() if hasattr(fg_brush, "color") else QColor(fg_brush)
            if colour.isValid():
                option.palette.setColor(QPalette.ColorRole.Text, colour)
                # Keep white text on the accent-coloured selection background
                option.palette.setColor(
                    QPalette.ColorRole.HighlightedText, QColor("#FFFFFF")
                )


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
        self._cleared = False  # True after Clear is clicked; suppresses auto-refresh

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
        """Right panel: chart tab widget + summary table as a tab."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

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

        # Fig 11: Pipeline Funnel — taller figure to accommodate 5 stages
        self.fig11 = Figure(figsize=(8, 7), dpi=100)
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
        tab12 = self._create_heatmap_tab(chart_bg)
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

        # Summary table tab — _create_summary_table returns the container
        # widget (toolbar + table) and also sets self.summary_table.
        summary_tab = self._create_summary_table()
        self.chart_tabs.addTab(summary_tab, "📋 Summary Table")

        layout.addWidget(self.chart_tabs)
        self._reset_chart_placeholders()
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

    def _create_heatmap_tab(self, chart_bg: str) -> QWidget:
        """Create the Heatmap tab with view filter controls (Ambiguous / Matched / All)."""
        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setContentsMargins(6, 6, 6, 4)
        cl.setSpacing(4)

        ctrl_bar = QHBoxLayout()
        ctrl_bar.setContentsMargins(4, 2, 4, 4)
        ctrl_bar.setSpacing(8)

        lbl = QLabel("Filter:")
        lbl.setStyleSheet(f"color: {C_TEXT2}; font-size: 11px; font-weight: bold;")
        ctrl_bar.addWidget(lbl)

        self.heatmap_filter_combo = QComboBox()
        self.heatmap_filter_combo.addItem("⚡ Ambiguous Peaks Only", "ambiguous")
        self.heatmap_filter_combo.addItem("✓ Matched Peaks Only", "matched")
        self.heatmap_filter_combo.addItem("🔍 All Peaks", "all")
        self.heatmap_filter_combo.setToolTip("Filter heatmap: focus on conflicting peaks, non-zero matches, or full matrix")
        self.heatmap_filter_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {C_BG_RAISED};
                color: {C_TEXT};
                border: 1px solid {C_BORDER};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                min-width: 170px;
            }}
            QComboBox:hover {{
                border-color: {C_ACCENT};
            }}
        """)
        self.heatmap_filter_combo.currentIndexChanged.connect(self._on_heatmap_filter_changed)
        ctrl_bar.addWidget(self.heatmap_filter_combo)

        self.heatmap_info_label = QLabel("")
        self.heatmap_info_label.setStyleSheet(f"color: {C_TEXT_MUTED}; font-size: 11px;")
        ctrl_bar.addWidget(self.heatmap_info_label)

        ctrl_bar.addStretch()
        cl.addLayout(ctrl_bar)
        cl.addWidget(self.canvas12)
        cl.addWidget(self.toolbar12)
        return container

    def _on_heatmap_filter_changed(self) -> None:
        """Slot called when user changes heatmap view filter."""
        self._update_chart_fig12()

    def _create_summary_table(self) -> QWidget:
        """Create the summary table tab content: toolbar + themed QTableWidget.

        Returns a QWidget container (not the table itself) so the tab holds
        the toolbar+table pair.  The table is stored as ``self.summary_table``.
        """
        # ── Scrollbar stylesheet — themed to match the app dark palette ──
        _SCROLLBAR_CSS = f"""
QTableWidget {{
    gridline-color: {C_BORDER};
    border: none;
}}
QScrollBar:horizontal {{
    background: {C_BG_BASE};
    height: 10px;
    margin: 0px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background: {C_BORDER};
    min-width: 28px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {C_ACCENT};
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QScrollBar:vertical {{
    background: {C_BG_BASE};
    width: 10px;
    margin: 0px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {C_BORDER};
    min-height: 28px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background: {C_ACCENT};
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""
        # ── Table widget ───────────────────────────────────────────────
        t = QTableWidget()
        t.setColumnCount(8)
        t.setHorizontalHeaderLabels([
            "Element",
            "Confidence Tier",
            "Status",
            "Matched Lines",
            "Mean VC",
            "Avg Δλ (nm)",
            "Avg Score",
            "Best Lines (nm)",
        ])
        hdr = t.horizontalHeader()
        # All columns size to their content — horizontal scroll reveals overflow
        for col in range(8):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        # Allow the user to manually resize if desired
        hdr.setStretchLastSection(False)
        t.setAlternatingRowColors(True)
        t.setSortingEnabled(False)
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # NOTE: do NOT call t.setStyleSheet() here — any QSS on the table
        # widget itself re-introduces the cascade that overrides the delegate's
        # palette colours, making foreground text invisible in the normal state.
        # Delegate ensures per-cell foreground is always painted correctly
        # even when the global stylesheet sets a colour on QTableWidget::item
        t.setItemDelegate(_CellColourDelegate(t))
        self._set_table_placeholder(t)
        self.summary_table = t

        # ── Toolbar row above the table ────────────────────────────────
        toolbar = QWidget()
        toolbar.setFixedHeight(34)
        toolbar.setStyleSheet(f"background-color: {C_BG_RAISED}; border-bottom: 1px solid {C_BORDER};")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 0, 8, 0)
        tb_layout.setSpacing(8)

        self._table_row_label = QLabel("— rows")
        self._table_row_label.setStyleSheet(f"color: {C_TEXT2}; font-size: 9pt; background: transparent; border: none;")
        tb_layout.addWidget(self._table_row_label)

        tb_layout.addStretch()

        # Copy toggle button
        self._copy_btn = QPushButton("⎘  Copy Table")
        self._copy_btn.setCheckable(True)
        self._copy_btn.setFixedHeight(24)
        self._copy_btn.setToolTip("Copy all rows as tab-separated values to clipboard.\nClick again to deselect.")
        self._copy_btn.setStyleSheet(f"""
QPushButton {{
    background-color: {C_BG_INPUT};
    color: {C_TEXT2};
    border: 1px solid {C_BORDER};
    border-radius: 4px;
    padding: 0 10px;
    font-size: 9pt;
}}
QPushButton:hover {{
    background-color: {C_BG_RAISED};
    color: {C_TEXT};
    border-color: {C_ACCENT};
}}
QPushButton:checked {{
    background-color: {C_ACCENT};
    color: #ffffff;
    border-color: {C_ACCENT};
}}
QPushButton:disabled {{
    color: {C_TEXT_MUTED};
    border-color: {C_BORDER};
    background-color: {C_BG_BASE};
}}
""")
        self._copy_btn.setEnabled(False)
        self._copy_btn.clicked.connect(self._on_copy_table_clicked)
        tb_layout.addWidget(self._copy_btn)

        # ── Container ──────────────────────────────────────────────────
        container = QWidget()
        # Apply the scrollbar CSS on the container, not on the table itself,
        # so the table's stylesheet context stays clean for the delegate.
        container.setStyleSheet(_SCROLLBAR_CSS)
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(toolbar)
        cl.addWidget(t, stretch=1)   # stretch=1 fills all remaining vertical space
        return container

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Pull latest data from upstream tabs and trigger a (re)computation."""
        self._on_compute_clicked()

    def refresh_if_not_cleared(self) -> None:
        """Called on tab-switch. Skips refresh when user has explicitly cleared."""
        if not self._cleared:
            self._on_compute_clicked()

    # ------------------------------------------------------------------
    # Compute logic
    # ------------------------------------------------------------------

    def _on_compute_clicked(self) -> None:
        """Disable exports, show progress, launch background worker."""
        self._cleared = False  # any explicit compute rearms auto-refresh
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
        self._cleared = False  # rearm auto-refresh going forward
        self.summary_banner.setText("Reloading data from Steps 2–5…")
        self.info_label.setText("Fetching latest upstream results and recomputing.")
        self._on_compute_clicked()

    def _on_clear_clicked(self) -> None:
        """Clear all results, reset charts to placeholder, disable exports."""
        logger.info("Step 6: Clear triggered")
        self._cleared = True  # suppress auto-refresh on next tab-switch
        self.performance_results = None

        # Disable exports
        self.export_csv_button.setEnabled(False)
        self.export_png_button.setEnabled(False)
        self.export_pdf_button.setEnabled(False)

        # Reset status labels
        self.summary_banner.setText("Results cleared. Run Steps 2–5 then click Compute Metrics.")
        self.info_label.setText("Complete Steps 2–5 to enable performance metrics computation.")

        # Reset all four charts to placeholder state
        self._reset_chart_placeholders()

        # Reset summary table
        self._set_table_placeholder(self.summary_table)

    def _reset_chart_placeholders(self) -> None:
        """Reset all four charts to theme-aware placeholder state."""
        chart_bg = get_chart_bg()
        for fig, canvas in [
            (self.fig7,  self.canvas7),
            (self.fig11, self.canvas11),
            (self.fig14, self.canvas14),
        ]:
            fig.patch.set_facecolor(chart_bg)
            canvas.setStyleSheet(f"background-color: {chart_bg};")
            ax = fig.axes[0] if fig.axes else fig.add_subplot(111)
            ax.clear()
            ChartEngine._show_placeholder(ax, "No data — click Compute Metrics")
            ChartEngine.apply_dark_style(fig, ax)
            canvas.draw()

        # Fig 12 needs full figure clear to remove any orphaned colorbar axes
        self.fig12.clf()
        self.fig12.patch.set_facecolor(chart_bg)
        self.canvas12.setStyleSheet(f"background-color: {chart_bg};")
        self.ax12 = self.fig12.add_subplot(111)
        ChartEngine._show_placeholder(self.ax12, "No data — click Compute Metrics")
        ChartEngine.apply_dark_style(self.fig12, self.ax12)
        self.canvas12.draw()
        if hasattr(self, "heatmap_info_label"):
            self.heatmap_info_label.setText("")

        # Also clear the secondary axis on fig14
        self.ax14_2.clear()
        self.canvas14.draw()

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

        # Persist immediately so the next launch can restore without recomputing
        try:
            from src.gui.session_manager import save_step6
            save_step6(self.performance_results)
        except Exception:
            pass

        # ── Status banner ──────────────────────────────────────────────
        missing = results.get("missing_steps", [])
        if missing:
            banner_text = f"Partial results — missing: {', '.join(missing)}."
        else:
            acc  = results.get("accuracy")
            prec = results.get("precision")
            rec  = results.get("recall")
            f1   = results.get("f1_score")
            acc_str  = f"{acc  * 100:.1f}%" if acc  is not None else "N/A"
            prec_str = f"{prec * 100:.1f}%" if prec is not None else "N/A"
            rec_str  = f"{rec  * 100:.1f}%" if rec  is not None else "N/A"
            f1_str   = f"{f1   * 100:.1f}%" if f1   is not None else "N/A"
            n_elem = len(results.get("element_rows", []))
            banner_text = (
                f"Acc: {acc_str}  Prec: {prec_str}  "
                f"Rec: {rec_str}  F1: {f1_str}  |  Elements: {n_elem}"
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
        """Render Fig 12: Correlation Heatmap.

        Uses fig.clf() + add_subplot() instead of ax.clear() so that any
        orphaned colorbar axes from the previous render are fully removed.
        """
        # Full figure clear — removes the main axes AND any colorbar axes
        # that fig.colorbar() added on the previous render.
        self.fig12.clf()
        self.ax12 = self.fig12.add_subplot(111)

        matrix = None
        peak_labels = []
        element_labels = []
        if self.performance_results is not None:
            matrix = self.performance_results.get("heatmap_matrix")
            peak_labels = self.performance_results.get("peak_labels", [])
            element_labels = self.performance_results.get("element_labels", [])

        filter_mode = "ambiguous"
        if hasattr(self, "heatmap_filter_combo"):
            filter_mode = self.heatmap_filter_combo.currentData() or "ambiguous"

        meta = ChartEngine.render_correlation_heatmap(
            self.ax12, matrix, peak_labels, element_labels, filter_mode=filter_mode
        )

        if hasattr(self, "heatmap_info_label") and meta:
            n_amb = meta.get("n_ambiguous", 0)
            n_matched = meta.get("n_matched", 0)
            n_total = meta.get("n_total", 0)
            if n_total > 0:
                self.heatmap_info_label.setText(
                    f"Ambiguous: {n_amb}  |  Matched: {n_matched}  |  Total Detected: {n_total}"
                )
            else:
                self.heatmap_info_label.setText("")

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

    def _update_charts(self) -> None:
        """Update and redraw all 4 Step 6 charts with the current theme."""
        chart_bg = get_chart_bg()
        for fig, canvas in [
            (self.fig7,  self.canvas7),
            (self.fig11, self.canvas11),
            (self.fig12, self.canvas12),
            (self.fig14, self.canvas14),
        ]:
            fig.patch.set_facecolor(chart_bg)
            canvas.setStyleSheet(f"background-color: {chart_bg};")

        self._update_chart_fig7()
        self._update_chart_fig11()
        self._update_chart_fig12()
        self._update_chart_fig14()

    # ------------------------------------------------------------------
    # Summary table (Task 5.4)
    # ------------------------------------------------------------------

    def _populate_summary_table(self) -> None:
        """Fill the 8-column summary table with colour-coded per-element rows."""
        if self.performance_results is None:
            self._set_table_placeholder(self.summary_table)
            self._table_row_label.setText("— rows")
            self._copy_btn.setEnabled(False)
            self._copy_btn.setChecked(False)
            return

        element_rows = self.performance_results.get("element_rows", [])
        if not element_rows:
            self._set_table_placeholder(self.summary_table)
            self._table_row_label.setText("0 elements")
            self._copy_btn.setEnabled(False)
            self._copy_btn.setChecked(False)
            return

        # ── Colour palette ─────────────────────────────────────────────
        # All colours are theme-aware: dark theme uses vivid saturated
        # backgrounds with white/dark-base text; light theme uses pastel
        # tinted backgrounds with dark, readable foreground text.
        if is_dark():
            TIER_COLOURS = {
                "High":   (C_SUCCESS, "#FFFFFF"),
                "Medium": (C_WARN,    "#FFFFFF"),   # white on amber — was dark brown #1A1C10
                "Low":    (C_ERROR,   "#FFFFFF"),
            }
            STATUS_COLOURS = {
                "Confirmed": (C_SUCCESS, "#FFFFFF"),
                "Probable":  (C_WARN,    "#FFFFFF"),  # white on amber — was dark brown
                "Uncertain": (C_ERROR,   "#FFFFFF"),
            }
            # NA cells: no coloured background — just use the standard table
            # text colour so they don't vanish into the dark table background.
            _NA_CELL = ("", C_TEXT2)
            _NA_VC   = ("", C_TEXT2)

            def _vc_colour(vc):
                if vc is None:         return _NA_VC
                v = float(vc)
                if v >= 0.70:          return (C_SUCCESS, "#FFFFFF")
                if v >= 0.50:          return (C_WARN,    "#FFFFFF")  # was #1A1C10
                if v >= 0.0:           return _NA_VC
                return                        (C_ERROR,   "#FFFFFF")

            def _delta_colour(d):
                if d is None:          return _NA_CELL
                if d <= 0.05:          return (C_SUCCESS, "#FFFFFF")
                if d <= 0.15:          return (C_WARN,    "#FFFFFF")  # was #1A1C10
                return                        (C_ERROR,   "#FFFFFF")

            def _score_colour(s, max_s):
                if s is None or max_s == 0: return _NA_CELL
                r = s / max_s
                if r >= 0.67:          return (C_SUCCESS, "#FFFFFF")
                if r >= 0.33:          return (C_WARN,    "#FFFFFF")  # was #1A1C10
                return                        (C_ERROR,   "#FFFFFF")

            def _matched_colour(n):
                if n >= 10:            return (C_SUCCESS, "#FFFFFF")
                if n >= 3:             return (C_WARN,    "#FFFFFF")  # was #1A1C10
                return                        (C_ERROR,   "#FFFFFF")
        else:
            # Light theme — pastel tinted backgrounds, dark text
            TIER_COLOURS = {
                "High":   ("#C6F4DE", "#0D6B3A"),
                "Medium": ("#FDF0C2", "#7A4F00"),
                "Low":    ("#FAD4DA", "#8B001A"),
            }
            STATUS_COLOURS = {
                "Confirmed": ("#C6F4DE", "#0D6B3A"),
                "Probable":  ("#FDF0C2", "#7A4F00"),
                "Uncertain": ("#FAD4DA", "#8B001A"),
            }
            _NA_CELL = (L_BG_RAISED, L_TEXT2)

            def _vc_colour(vc):
                if vc is None:         return _NA_CELL
                v = float(vc)
                if v >= 0.70:          return ("#C6F4DE", "#0D6B3A")
                if v >= 0.50:          return ("#FDF0C2", "#7A4F00")
                if v >= 0.0:           return _NA_CELL
                return                        ("#FAD4DA", "#8B001A")

            def _delta_colour(d):
                if d is None:          return _NA_CELL
                if d <= 0.05:          return ("#C6F4DE", "#0D6B3A")
                if d <= 0.15:          return ("#FDF0C2", "#7A4F00")
                return                        ("#FAD4DA", "#8B001A")

            def _score_colour(s, max_s):
                if s is None or max_s == 0: return _NA_CELL
                r = s / max_s
                if r >= 0.67:          return ("#C6F4DE", "#0D6B3A")
                if r >= 0.33:          return ("#FDF0C2", "#7A4F00")
                return                        ("#FAD4DA", "#8B001A")

            def _matched_colour(n):
                if n >= 10:            return ("#C6F4DE", "#0D6B3A")
                if n >= 3:             return ("#FDF0C2", "#7A4F00")
                return                        ("#FAD4DA", "#8B001A")

        def _coloured_item(text: str, bg: str, fg: str) -> QTableWidgetItem:
            item = QTableWidgetItem(text)
            if bg:
                item.setBackground(QColor(bg))
            item.setForeground(QColor(fg))
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )
            return item

        # Pre-compute max score for relative colouring
        all_scores = [
            er.get("avg_score") for er in element_rows
            if er.get("avg_score") is not None
        ]
        max_score = max(all_scores) if all_scores else 1.0

        self.summary_table.setSortingEnabled(False)
        self.summary_table.setRowCount(len(element_rows))
        self.summary_table.setRowHeight(0, 28)   # set default row height

        for row_idx, er in enumerate(element_rows):
            element  = str(er.get("element", ""))
            tier     = str(er.get("confidence_tier", "Low"))
            matched  = er.get("matched_lines", 0)
            mean_vc  = er.get("mean_vc")
            avg_d    = er.get("avg_delta")
            avg_s    = er.get("avg_score")
            best_wls = er.get("best_lines") or []

            # Status from tier
            status = {"High": "Confirmed", "Medium": "Probable"}.get(tier, "Uncertain")

            tier_bg,   tier_fg   = TIER_COLOURS.get(tier, ("#2A2D3A", C_TEXT2))
            stat_bg,   stat_fg   = STATUS_COLOURS.get(status, ("#2A2D3A", C_TEXT2))
            vc_bg,     vc_fg     = _vc_colour(mean_vc)
            d_bg,      d_fg      = _delta_colour(avg_d)
            s_bg,      s_fg      = _score_colour(avg_s, max_score)
            m_bg,      m_fg      = _matched_colour(matched)

            # Format display strings
            vc_str   = f"{mean_vc:.3f}"  if mean_vc  is not None else "N/A"
            d_str    = f"{avg_d:.4f}"    if avg_d    is not None else "N/A"
            # Score: always use scientific notation for consistency
            s_str    = f"{avg_s:.3e}"    if avg_s    is not None else "N/A"
            best_str = ",  ".join(f"{w:.2f}" for w in best_wls) if best_wls else "—"

            # Col 0: Element name — plain, no colour
            elem_item = QTableWidgetItem(element)
            elem_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.summary_table.setItem(row_idx, 0, elem_item)

            # Col 1: Confidence Tier
            self.summary_table.setItem(
                row_idx, 1, _coloured_item(tier, tier_bg, tier_fg)
            )
            # Col 2: Status
            self.summary_table.setItem(
                row_idx, 2, _coloured_item(status, stat_bg, stat_fg)
            )
            # Col 3: Matched Lines
            self.summary_table.setItem(
                row_idx, 3, _coloured_item(str(int(matched)), m_bg, m_fg)
            )
            # Col 4: Mean VC
            self.summary_table.setItem(
                row_idx, 4, _coloured_item(vc_str, vc_bg, vc_fg)
            )
            # Col 5: Avg Δλ
            self.summary_table.setItem(
                row_idx, 5, _coloured_item(d_str, d_bg, d_fg)
            )
            # Col 6: Avg Score
            self.summary_table.setItem(
                row_idx, 6, _coloured_item(s_str, s_bg, s_fg)
            )
            # Col 7: Best Lines — left-aligned, plain text (can be long)
            best_item = QTableWidgetItem(best_str)
            best_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            best_item.setToolTip(best_str)   # full text on hover
            self.summary_table.setItem(row_idx, 7, best_item)

        self.summary_table.setSortingEnabled(True)
        self.summary_table.resizeRowsToContents()

        # Update toolbar
        n = len(element_rows)
        self._table_row_label.setText(f"{n} element{'s' if n != 1 else ''}")
        self._copy_btn.setEnabled(True)
        self._copy_btn.setChecked(False)

    @staticmethod
    def _set_table_placeholder(table: QTableWidget) -> None:
        """Display a single 'Run Steps 2–5 first' placeholder row."""
        table.setSortingEnabled(False)
        table.setRowCount(1)
        placeholder = QTableWidgetItem("Run Steps 2–5 first")
        placeholder.setForeground(QColor(C_TEXT2))
        table.setItem(0, 0, placeholder)
        for col in range(1, 8):
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
        # Restyle all navigation toolbars so icons are visible in light theme
        for tb in [self.toolbar7, self.toolbar11, self.toolbar12, self.toolbar14]:
            style_toolbar(tb)

        # Re-populate the summary table and refresh charts for the active theme
        if self.performance_results is not None:
            self._update_charts()
            self._populate_summary_table()
        else:
            self._reset_chart_placeholders()
            self.summary_table.viewport().update()

    # ------------------------------------------------------------------
    # Export handlers (Task 5.7)
    # ------------------------------------------------------------------

    def _on_copy_table_clicked(self) -> None:
        """Copy all visible table rows to the clipboard as TSV.

        The button is checkable: pressing once copies and highlights the
        action (checked state); pressing again clears the selection and
        resets to unchecked.
        """
        t = self.summary_table
        rows = t.rowCount()
        cols = t.columnCount()

        if not self._copy_btn.isChecked():
            # Second press — just deselect everything and reset label
            t.clearSelection()
            self._copy_btn.setText("⎘  Copy Table")
            return

        if rows == 0:
            self._copy_btn.setChecked(False)
            return

        # Build header row
        headers = [
            t.horizontalHeaderItem(c).text() if t.horizontalHeaderItem(c) else ""
            for c in range(cols)
        ]
        lines = ["\t".join(headers)]

        # Build data rows (plain text, no colour info)
        for r in range(rows):
            row_cells = []
            for c in range(cols):
                item = t.item(r, c)
                row_cells.append(item.text() if item else "")
            lines.append("\t".join(row_cells))

        tsv = "\n".join(lines)
        QApplication.clipboard().setText(tsv)

        # Visual feedback — briefly update button label
        self._copy_btn.setText("✓  Copied!")
        self._table_row_label.setText(
            f"{rows} element{'s' if rows != 1 else ''}  ·  copied to clipboard"
        )


    def _on_export_csv_clicked(self) -> None:
        """Export Step 6 summary as CSV."""
        if self.performance_results is None:
            show_error("Export Error", "No results to export. Run Compute Metrics first.")
            return

        # Open dialog in step5's last-used folder (most relevant context)
        proc_history = getattr(
            getattr(self.step5_tab, "_processed_history", None),
            "get_recent", lambda: []
        )()
        start_dir = str(Path(proc_history[0]).parent) if proc_history else str(Path.home())

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export CSV",
            str(Path(start_dir) / "step6_performance"),
            "CSV Files (*.csv)"
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

        proc_history = getattr(
            getattr(self.step5_tab, "_processed_history", None),
            "get_recent", lambda: []
        )()
        start_dir = str(Path(proc_history[0]).parent) if proc_history else str(Path.home())

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export PNG",
            str(Path(start_dir) / "step6_charts"),
            "PNG Files (*.png)"
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

        proc_history = getattr(
            getattr(self.step5_tab, "_processed_history", None),
            "get_recent", lambda: []
        )()
        start_dir = str(Path(proc_history[0]).parent) if proc_history else str(Path.home())

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Report",
            str(Path(start_dir) / "step6_performance_report"),
            "PDF Files (*.pdf)"
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
