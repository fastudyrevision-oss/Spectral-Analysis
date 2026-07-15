# -*- coding: utf-8 -*-
"""
Step 1 Widget - SG-ALS Baseline Correction

Provides UI for baseline correction with parameter tuning and visualization.
"""

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QScrollArea, QSplitter, QTabWidget,
    QSizePolicy
)
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from src import setup_logger
from src.config import STEP1_PARAMS
from src.core.step1_sg_als import BaselineCorrection
from src.io.file_reader import CSVReader
from src.io.file_writer import CSVWriter, PlotGenerator
from src.gui.gui_utils import (
    ParameterControl, FileSelector, WorkerThread,
    show_error, show_info
)
from src.gui.theme import (
    primary_button_style, instruction_banner_style, step_title_font,
    C_BG_BASE, C_BG_RAISED, C_BORDER_SUBTLE, C_ACCENT, C_ACCENT2,
    C_WARN, C_ERROR, C_TEXT, C_TEXT2,
    get_chart_bg, get_chart_axes_bg, get_chart_text, get_chart_text2, get_chart_border,
)

logger = setup_logger(__name__)

# Colours matching the PlotGenerator export for visual consistency
_C_RAW       = C_WARN      # Raw (offset)  — amber
_C_SG        = C_ACCENT    # SG Smoothed   — blue
_C_BASELINE  = C_ERROR     # ALS Baseline  — red/pink
_C_CORRECTED = C_ACCENT2   # Corrected     — teal


class Step1Widget(QWidget):
    """
    UI widget for Step 1: SG-ALS Baseline Correction.

    Allows users to:
    - Select input spectrum file
    - Adjust baseline correction parameters
    - Preview results across multiple chart tabs:
        Tab 1 — Corrected Spectrum
        Tab 2 — Baseline Separation (Raw + SG + ALS Baseline + Corrected)
        Tab 3 — ALS Iterative Convergence
    - Save processed spectra
    """

    # Signals
    processing_started = pyqtSignal()
    processing_finished = pyqtSignal(dict)

    def __init__(self, file_history=None, notes_panel=None):
        super().__init__()
        self.processed_data = None
        self.raw_data = None
        self.corrector = None
        self.worker_thread = None
        self.file_history = file_history
        self.notes_panel = notes_panel

        logger.info("Initializing Step 1 widget")

        main_layout = QHBoxLayout()
        main_layout.addWidget(self._create_left_panel(), stretch=0)
        main_layout.addWidget(self._create_right_panel(), stretch=1)
        self.setLayout(main_layout)

    # ──────────────────────────────────────────────────────────────────────
    # Panel builders
    # ──────────────────────────────────────────────────────────────────────

    def _create_left_panel(self) -> QWidget:
        """Create left control panel (scrollable)."""
        panel = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Step 1: SG-ALS Baseline Correction")
        tf = QFont(); tf.setBold(True); tf.setPointSize(12)
        title.setFont(tf)
        title.setStyleSheet(step_title_font(13))
        layout.addWidget(title)
        self._title_label = title

        instructions = QLabel(
            "📋 Instructions:\n"
            "1. Click 'Spectrum File' to select your raw LIBS spectrum CSV.\n"
            "   • File must have a 'Wavelength' column and an 'Intensity' (or 'Signal'/'Counts') column.\n"
            "2. Adjust parameters if needed (defaults work for most spectra):\n"
            "   • Lambda (λ): smoothness of the baseline — higher = smoother.\n"
            "   • Asymmetry (p): lower values push the baseline below peaks.\n"
            "   • Iterations: more iterations = more precise baseline.\n"
            "   • SG Window / Poly: Savitzky-Golay smoothing settings (window must be odd).\n"
            "3. Click 'Process' to run SG smoothing + ALS baseline correction.\n"
            "4. Use the chart tabs on the right to inspect the results.\n"
            "5. Click 'Save Results' to export the processed CSV and baseline plot.\n"
            "   ⚠ The saved CSV is required as input for Step 2."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(instruction_banner_style())
        layout.addWidget(instructions)
        self._instructions_label = instructions

        file_group = QGroupBox("Input File")
        fl = QVBoxLayout()
        self.file_selector = FileSelector("Spectrum File:", "CSV Files (*.csv)")
        fl.addWidget(self.file_selector)
        file_group.setLayout(fl)
        layout.addWidget(file_group)

        params_group = QGroupBox("Parameters")
        pl = QVBoxLayout()
        self.lambda_control = ParameterControl(
            "Lambda (λ)", 1e3, 1e6, STEP1_PARAMS['LAMBDA'], step=1e4, decimals=0)
        pl.addWidget(self.lambda_control)
        self.p_control = ParameterControl(
            "Asymmetry (p)", 0.001, 0.1, STEP1_PARAMS['P'], step=0.001, decimals=4)
        pl.addWidget(self.p_control)
        self.niter_control = ParameterControl(
            "Iterations", 1, 50, STEP1_PARAMS['NITER'], step=1, decimals=0)
        pl.addWidget(self.niter_control)
        self.window_control = ParameterControl(
            "SG Window", 3, 21, STEP1_PARAMS['WINDOW'], step=2, decimals=0)
        pl.addWidget(self.window_control)
        self.poly_control = ParameterControl(
            "SG Poly Order", 1, 5, STEP1_PARAMS['POLY'], step=1, decimals=0)
        pl.addWidget(self.poly_control)
        params_group.setLayout(pl)
        layout.addWidget(params_group)

        self.process_button = QPushButton("⚙  Process")
        self.process_button.setStyleSheet(primary_button_style())
        self.process_button.clicked.connect(self._on_process_clicked)
        layout.addWidget(self.process_button)

        self.save_button = QPushButton("Save Results")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save_clicked)
        layout.addWidget(self.save_button)

        info_group = QGroupBox("Info")
        il = QVBoxLayout()
        self.info_label = QLabel("Ready to process")
        self.info_label.setWordWrap(True)
        il.addWidget(self.info_label)
        info_group.setLayout(il)
        layout.addWidget(info_group)

        layout.addStretch()
        panel.setLayout(layout)
        panel.setMaximumWidth(350)

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setMaximumWidth(370)
        return scroll

    def _create_right_panel(self) -> QWidget:
        """Create right visualization panel (tabs + table)."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Tab widget with 5 chart tabs ──────────────────────────────────
        self.tab_widget = QTabWidget()

        # Tab 1: Raw Spectrum
        self.fig_raw, self.ax_raw, self.canvas_raw, self.toolbar_raw = \
            self._make_chart_tab("Raw Spectrum")

        # Tab 2: SG Smoothed
        self.fig_sg, self.ax_sg, self.canvas_sg, self.toolbar_sg = \
            self._make_chart_tab("SG Smoothed")

        # Tab 3: Corrected Spectrum
        self.fig_corr, self.ax_corr, self.canvas_corr, self.toolbar_corr = \
            self._make_chart_tab("Corrected Spectrum")

        # Tab 4: Baseline Separation
        self.fig_sep, self.ax_sep, self.canvas_sep, self.toolbar_sep = \
            self._make_chart_tab("Baseline Separation")

        # Tab 5: ALS Convergence
        self.fig_conv, self.ax_conv, self.canvas_conv, self.toolbar_conv = \
            self._make_chart_tab("ALS Convergence")

        splitter.addWidget(self.tab_widget)

        # ── Results table ─────────────────────────────────────────────────
        table_label = QLabel("Processed Data Preview")
        tlf = QFont(); tlf.setBold(True)
        table_label.setFont(tlf)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Wavelength (nm)", "Raw", "Smoothed_SG", "Baseline_ALS", "Corrected"
        ])

        table_container = QWidget()
        tcl = QVBoxLayout(table_container)
        tcl.setContentsMargins(4, 4, 4, 4)
        tcl.addWidget(table_label)
        tcl.addWidget(self.table)
        splitter.addWidget(table_container)

        splitter.setSizes([500, 220])
        layout.addWidget(splitter)
        return panel

    def _make_chart_tab(self, title: str):
        """
        Create one tab containing a Figure + canvas + NavigationToolbar2QT.

        Returns (fig, ax, canvas, toolbar) for later use.
        """
        chart_bg = get_chart_bg()
        fig = Figure(figsize=(7, 4), dpi=100)
        fig.patch.set_facecolor(chart_bg)
        canvas = FigureCanvasQTAgg(fig)
        canvas.setStyleSheet(f"background-color: {chart_bg};")
        ax = fig.add_subplot(111)
        self._style_ax(fig, ax)
        toolbar = NavigationToolbar2QT(canvas)

        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(canvas)
        cl.addWidget(toolbar)

        self.tab_widget.addTab(container, title)
        return fig, ax, canvas, toolbar

    # ──────────────────────────────────────────────────────────────────────
    # Theme helper
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _style_ax(fig: Figure, ax) -> None:
        """Apply current theme to a figure/axes pair."""
        chart_bg = get_chart_bg()
        axes_bg = get_chart_axes_bg()
        text = get_chart_text()
        text2 = get_chart_text2()
        border = get_chart_border()
        fig.patch.set_facecolor(chart_bg)
        ax.set_facecolor(axes_bg)
        ax.tick_params(colors=text2, which="both", labelsize=8)
        ax.xaxis.label.set_color(text2)
        ax.yaxis.label.set_color(text2)
        ax.title.set_color(text)
        for spine in ax.spines.values():
            spine.set_edgecolor(border)
            spine.set_linewidth(0.8)
        ax.grid(True, color=border, alpha=0.55, linewidth=0.5,
                linestyle="--")

    @staticmethod
    def _style_legend(ax) -> None:
        """Style an existing legend for the current theme."""
        leg = ax.get_legend()
        if leg is None:
            return
        leg.get_frame().set_facecolor(get_chart_axes_bg())
        leg.get_frame().set_edgecolor(get_chart_border())
        leg.get_frame().set_alpha(0.85)
        for txt in leg.get_texts():
            txt.set_color(get_chart_text2())
            txt.set_fontsize(8)

    def apply_theme(self) -> None:
        """Update inline styles and chart colours when theme changes."""
        from src.gui import theme as _theme
        # Refresh inline-styled labels
        self._title_label.setStyleSheet(step_title_font(13))
        self._instructions_label.setStyleSheet(instruction_banner_style())
        # Update all 5 chart canvases
        chart_bg = _theme.get_chart_bg()
        for fig, canvas, ax in [
            (self.fig_raw,  self.canvas_raw,  self.ax_raw),
            (self.fig_sg,   self.canvas_sg,   self.ax_sg),
            (self.fig_corr, self.canvas_corr, self.ax_corr),
            (self.fig_sep,  self.canvas_sep,  self.ax_sep),
            (self.fig_conv, self.canvas_conv, self.ax_conv),
        ]:
            canvas.setStyleSheet(f"background-color: {chart_bg};")
            self._style_ax(fig, ax)
            self._style_legend(ax)
            canvas.draw()

    # ──────────────────────────────────────────────────────────────────────
    # Event handlers
    # ──────────────────────────────────────────────────────────────────────

    def _on_process_clicked(self):
        if self.file_selector.get_filepath() is None:
            show_error("Error", "Please select an input file")
            return

        self.info_label.setText("Loading file...")
        self.process_button.setEnabled(False)

        if self.notes_panel:
            self.notes_panel.add_note("Starting baseline correction (Step 1)", "INFO")

        try:
            reader = CSVReader()
            self.raw_data = reader.read_raw_spectra(
                str(self.file_selector.get_filepath()))
            logger.info(f"Loaded spectrum: {len(self.raw_data.wavelength)} points")
            if self.notes_panel:
                self.notes_panel.add_note(
                    f"File loaded: {self.file_selector.get_filepath().name} "
                    f"({len(self.raw_data.wavelength)} points)", "SUCCESS")
        except Exception as e:
            logger.error(f"Failed to load file: {e}")
            show_error("Error", f"Failed to load file:\n{e}")
            self.process_button.setEnabled(True)
            self.info_label.setText("Error loading file")
            if self.notes_panel:
                self.notes_panel.add_note(f"File loading failed: {e}", "ERROR")
            return

        params = {
            'LAMBDA': self.lambda_control.value(),
            'P': self.p_control.value(),
            'NITER': int(self.niter_control.value()),
            'WINDOW': int(self.window_control.value()),
            'POLY': int(self.poly_control.value()),
        }
        self.corrector = BaselineCorrection(params)
        self.info_label.setText("Processing... (may take a moment)")

        self.worker_thread = WorkerThread(
            self.corrector.process,
            self.raw_data.wavelength,
            self.raw_data.intensity,
        )
        self.worker_thread.finished.connect(self._on_processing_finished)
        self.worker_thread.error.connect(self._on_processing_error)
        self.worker_thread.start()

    def _on_processing_finished(self, result: dict):
        self.processed_data = result.get('result')

        if self.processed_data:
            logger.info("Baseline correction complete")
            if self.notes_panel:
                self.notes_panel.add_note(
                    "Baseline correction completed successfully", "SUCCESS")

            self._draw_raw_tab()
            self._draw_sg_tab()
            self._draw_corrected_tab()
            self._draw_separation_tab()
            self._draw_convergence_tab()
            self._update_table()

            self.info_label.setText(
                f"Processed: {len(self.processed_data.wavelength)} points\n"
                f"Corrected range: {np.min(self.processed_data.corrected):.2e} "
                f"to {np.max(self.processed_data.corrected):.2e}"
            )
            self.save_button.setEnabled(True)

        self.process_button.setEnabled(True)

    def _on_processing_error(self, error: str):
        logger.error(f"Processing error: {error}")
        show_error("Processing Error", f"Baseline correction failed:\n{error}")
        self.info_label.setText("Error during processing")
        if self.notes_panel:
            self.notes_panel.add_note(f"Processing error: {error}", "ERROR")
        self.process_button.setEnabled(True)

    # ──────────────────────────────────────────────────────────────────────
    # Chart renderers (one per tab)
    # ──────────────────────────────────────────────────────────────────────

    def _draw_raw_tab(self):
        """Tab 1 — Raw spectrum as loaded from file."""
        d = self.processed_data
        ax = self.ax_raw
        ax.clear()
        ax.plot(d.wavelength, d.raw,
                color=_C_RAW, linewidth=0.9, alpha=0.85,
                label="Raw")
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Intensity (counts)")
        ax.set_title("Raw Spectrum")
        ax.legend(loc="upper right", fontsize=8)
        self._style_ax(self.fig_raw, ax)
        self._style_legend(ax)
        self.fig_raw.tight_layout(pad=1.2)
        self.canvas_raw.draw()
        self.toolbar_raw.home()

    def _draw_sg_tab(self):
        """Tab 2 — SG-smoothed spectrum overlaid on raw."""
        d = self.processed_data
        ax = self.ax_sg
        ax.clear()
        ax.plot(d.wavelength, d.raw,
                color=_C_RAW, linewidth=0.8, alpha=0.45,
                label="Raw")
        ax.plot(d.wavelength, d.smoothed_sg,
                color=_C_SG, linewidth=1.0, alpha=0.95,
                label="SG Smoothed")
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Intensity")
        ax.set_title("Savitzky-Golay Smoothed Spectrum")
        ax.legend(loc="upper right", fontsize=8)
        self._style_ax(self.fig_sg, ax)
        self._style_legend(ax)
        self.fig_sg.tight_layout(pad=1.2)
        self.canvas_sg.draw()
        self.toolbar_sg.home()

    def _draw_corrected_tab(self):
        """Tab 3 — Corrected spectrum only."""
        d = self.processed_data
        ax = self.ax_corr
        ax.clear()
        ax.plot(d.wavelength, d.corrected,
                color=_C_CORRECTED, linewidth=0.9, alpha=0.95,
                label="Corrected")
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Intensity (baseline subtracted)")
        ax.set_title("Corrected Spectrum")
        ax.legend(loc="upper right", fontsize=8)
        self._style_ax(self.fig_corr, ax)
        self._style_legend(ax)
        self.fig_corr.tight_layout(pad=1.2)
        self.canvas_corr.draw()
        self.toolbar_corr.home()

    def _draw_separation_tab(self):
        """Tab 4 — Raw (offset) + SG Smoothed + ALS Baseline + Corrected."""
        d = self.processed_data
        ax = self.ax_sep

        # Auto-compute a visible vertical offset so Raw doesn't collide
        signal_range = float(np.ptp(d.smoothed_sg))
        offset = signal_range * 0.6 if signal_range > 0 else 4000.0

        ax.clear()
        ax.plot(d.wavelength, d.raw + offset,
                color=_C_RAW, linewidth=0.9, alpha=0.75,
                label=f"Raw (+ offset {offset:.0f})")
        ax.plot(d.wavelength, d.smoothed_sg,
                color=_C_SG, linewidth=0.9, alpha=0.90,
                label="SG Smoothed")
        ax.plot(d.wavelength, d.baseline_als,
                color=_C_BASELINE, linewidth=1.3, linestyle="--",
                label="ALS Baseline")
        ax.plot(d.wavelength, d.corrected - offset,
                color=_C_CORRECTED, linewidth=0.9,
                label=f"Corrected (− offset {offset:.0f})")

        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Intensity (offset)")
        ax.set_title("SG + ALS Baseline Separation")
        ax.legend(loc="upper right", fontsize=8)
        self._style_ax(self.fig_sep, ax)
        self._style_legend(ax)
        self.fig_sep.tight_layout(pad=1.2)
        self.canvas_sep.draw()
        self.toolbar_sep.home()

    def _draw_convergence_tab(self):
        """Tab 5 — ALS iterative baseline convergence (imshow + overlays)."""
        d = self.processed_data
        ax = self.ax_conv
        ax.clear()

        has_iters = (hasattr(d, "baseline_iterations")
                     and d.baseline_iterations
                     and len(d.baseline_iterations) > 0)

        if not has_iters:
            # Fallback: just show final baseline vs SG smoothed
            ax.plot(d.wavelength, d.smoothed_sg,
                    color=_C_SG, linewidth=0.9, alpha=0.75, label="SG Smoothed")
            ax.plot(d.wavelength, d.baseline_als,
                    color=_C_BASELINE, linewidth=1.3, linestyle="--",
                    label="ALS Baseline (final)")
            ax.set_xlabel("Wavelength (nm)")
            ax.set_ylabel("Intensity")
            ax.set_title("ALS Baseline (convergence data unavailable)")
            ax.legend(loc="upper right", fontsize=8)
            self._style_ax(self.fig_conv, ax)
            self._style_legend(ax)
            self.fig_conv.tight_layout(pad=1.2)
            self.canvas_conv.draw()
            self.toolbar_conv.home()
            return

        baseline_matrix = np.array(d.baseline_iterations)
        n_iters = len(d.baseline_iterations)

        im = ax.imshow(
            baseline_matrix,
            aspect="auto",
            extent=[d.wavelength.min(), d.wavelength.max(), 1, n_iters],
            origin="lower",
            cmap="plasma",
        )

        # Overlay 4 representative iteration curves
        snap_indices = [
            0,
            n_iters // 3,
            2 * n_iters // 3,
            n_iters - 1,
        ]
        snap_colours = ["white", "yellow", "cyan", "red"]
        for idx, colour in zip(snap_indices, snap_colours):
            if idx < n_iters:
                iter_data = d.baseline_iterations[idx]
                norm_y = (iter_data / np.max(iter_data)) * n_iters
                ax.plot(d.wavelength, norm_y,
                        linestyle="--", linewidth=1.2,
                        color=colour, label=f"Iter {idx + 1}")

        # Colourbar
        cb = self.fig_conv.colorbar(im, ax=ax)
        cb.ax.tick_params(colors=C_TEXT2, labelsize=8)
        cb.set_label("Baseline Intensity", color=C_TEXT2, fontsize=9)

        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Iteration")
        ax.set_title("ALS Iterative Baseline Convergence")
        ax.legend(loc="upper right", fontsize=8, title="Iterations")
        self._style_ax(self.fig_conv, ax)
        self._style_legend(ax)
        self.fig_conv.tight_layout(pad=1.2)
        self.canvas_conv.draw()
        self.toolbar_conv.home()

    # ──────────────────────────────────────────────────────────────────────
    # Table & save
    # ──────────────────────────────────────────────────────────────────────

    def _update_table(self):
        if self.processed_data is None:
            return
        n_rows = min(10, len(self.processed_data.wavelength))
        self.table.setRowCount(n_rows)
        for i in range(n_rows):
            d = self.processed_data
            self.table.setItem(i, 0, QTableWidgetItem(f"{d.wavelength[i]:.5f}"))
            self.table.setItem(i, 1, QTableWidgetItem(f"{d.raw[i]:.6g}"))
            self.table.setItem(i, 2, QTableWidgetItem(f"{d.smoothed_sg[i]:.6g}"))
            self.table.setItem(i, 3, QTableWidgetItem(f"{d.baseline_als[i]:.6g}"))
            self.table.setItem(i, 4, QTableWidgetItem(f"{d.corrected[i]:.6g}"))

    def _on_save_clicked(self):
        if self.processed_data is None:
            show_error("Error", "No processed data to save")
            return

        from PyQt6.QtWidgets import QFileDialog
        from datetime import datetime

        save_dir = QFileDialog.getExistingDirectory(
            self, "Select Save Directory", str(Path.home()))
        if not save_dir:
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_name  = f"SG_ALS_LIBS_processed_{ts}.csv"
        plot_name = f"SG_ALS_LIBS_processed_{ts}.png"
        csv_path_str  = str(Path(save_dir) / csv_name)
        plot_path_str = str(Path(save_dir) / plot_name)

        try:
            writer = CSVWriter()
            csv_path = writer.write_processed_spectra(csv_path_str, self.processed_data)
            logger.info(f"Saved processed spectra to {csv_path}")

            plot_gen = PlotGenerator()
            plot_path = plot_gen.plot_step1_baseline(self.processed_data, plot_path_str)
            logger.info(f"Saved baseline plot to {plot_path}")

            show_info(
                "Saved",
                f"Files saved to:\n{save_dir}\n\n"
                f"  {csv_name}\n  {plot_name}"
            )
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            show_error("Error", f"Failed to save results:\n{e}")
