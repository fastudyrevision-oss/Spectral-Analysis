# -*- coding: utf-8 -*-
"""
Step 2 Widget - Automatic Peaks Detection

Provides UI for peak detection with visualization and results table.
"""

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QSplitter, QScrollArea, QFileDialog
)
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from src import setup_logger
from src.config import STEP2_PARAMS
from src.core.step2_peaks import PeaksDetector
from src.io.file_reader import CSVReader
from src.io.file_writer import CSVWriter, PlotGenerator
from src.gui.gui_utils import (
    HighDpiToolbar as NavigationToolbar2QT,
    style_toolbar,
    ParameterControl, FileSelector, WorkerThread,
    FileHistory, RecentFilesButton,
    show_error, show_info,
    on_copy_table_clicked,
    PeakHoverAnnotator,
)
from src.gui.theme import (
    primary_button_style, instruction_banner_style, step_title_font,
    C_BG_BASE, C_BG_RAISED, C_BORDER_SUBTLE, C_ACCENT, C_WARN, C_TEXT, C_TEXT2,
    C_TEXT_MUTED, C_ACCENT2,
    get_chart_bg, get_chart_axes_bg, get_chart_text, get_chart_text2, get_chart_border,
)

logger = setup_logger(__name__)


class Step2Widget(QWidget):
    """
    UI widget for Step 2: Automatic Peaks Detection.
    
    Allows users to:
    - Select processed spectrum (from Step 1 or manual input)
    - Adjust peak detection parameters
    - Preview detected peaks
    - Save results
    """
    
    # Emitted after successful detection — carries list[DetectedPeak]
    # so Step 3 can load it directly without a file round-trip.
    result_ready = pyqtSignal(object)
    
    def __init__(self, file_history=None, notes_panel=None):
        """
        Initialize Step 2 widget.
        
        Parameters
        ----------
        file_history : FileHistory, optional
            Shared file history object
        notes_panel : NotesPanel, optional
            Shared notes panel widget
        """
        super().__init__()
        self.processed_data = None
        self.detected_peaks = None
        self.detector = None
        self.worker_thread = None
        self.file_history = file_history
        self.notes_panel = notes_panel
        self._spectrum_path: Path | None = None
        self._spectrum_history = FileHistory(role="step2_spectrum")
        
        logger.info("Initializing Step 2 widget")
        
        # Main layout
        main_layout = QHBoxLayout()
        
        # Left panel (controls) — _create_left_panel already returns a scroll area
        left_scroll = self._create_left_panel()
        main_layout.addWidget(left_scroll, stretch=0)
        
        # Right panel (visualization)
        right_panel = self._create_right_panel()
        main_layout.addWidget(right_panel, stretch=1)
        
        self.setLayout(main_layout)
    
    def _create_left_panel(self) -> QWidget:
        """Create left control panel."""
        panel = QWidget()
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Step 2: Automatic Peaks Detection")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        title.setStyleSheet(step_title_font(13))
        layout.addWidget(title)
        self._title_label = title

        # Instructions
        instructions = QLabel(
            "Instructions:\n"
            "1. Load a spectrum file — either:\n"
            "   • The corrected output from Step 1 ('SG_ALS_LIBS_processed.csv' — Wavelength + Corrected columns), or\n"
            "   • A raw spectrum file (Wavelength + Intensity columns) to run detection directly.\n"
            "2. Adjust detection parameters if needed (click 'Reset to Defaults' to restore originals):\n"
            "   • Height Multiplier: peak must be this many times above local noise.\n"
            "   • Prominence: minimum height a peak stands out from surrounding baseline.\n"
            "   • Baseline Window: window size (points) for local noise estimation.\n"
            "   • Baseline K: noise sensitivity — higher K = fewer peaks detected.\n"
            "3. Click 'Detect Peaks' — results shown on plot and in table.\n"
            "4. Detected peaks are automatically forwarded to Step 3 and UPRSA in-memory.\n"
            "   • Optional: Click 'Save Results' to export detected peaks CSV and plot PNG."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(instruction_banner_style())
        layout.addWidget(instructions)
        self._instructions_label = instructions

        # File selection
        file_group = QGroupBox("Input File")
        file_layout = QVBoxLayout()
        file_layout.setContentsMargins(6, 8, 6, 8)
        file_layout.setSpacing(4)

        file_lbl = QLabel("Processed Spectrum CSV (Step 1 output or raw):")
        file_lbl.setStyleSheet("font-size: 9pt; font-weight: 600;")
        file_layout.addWidget(file_lbl)

        path_row = QHBoxLayout()
        path_row.setSpacing(4)
        self._spec_path_label = QLabel("(No file selected)")
        self._spec_path_label.setStyleSheet(
            f"font-size: 9pt; font-style: italic; color: {C_TEXT_MUTED}; "
            f"border: 1px solid #3A4055; border-radius: 4px; padding: 3px 6px;")
        self._spec_path_label.setWordWrap(False)
        path_row.addWidget(self._spec_path_label, stretch=1)
        browse_btn = QPushButton("Browse")
        browse_btn.setFixedWidth(75)
        browse_btn.setFixedHeight(26)
        browse_btn.clicked.connect(self._on_browse_spectrum)
        path_row.addWidget(browse_btn)
        file_layout.addLayout(path_row)

        recent_row = QHBoxLayout()
        self._spec_recent_btn = RecentFilesButton(self._spectrum_history)
        self._spec_recent_btn.file_selected.connect(self._on_recent_spectrum)
        recent_row.addWidget(self._spec_recent_btn)
        recent_row.addStretch()
        file_layout.addLayout(recent_row)

        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # Parameters group
        params_group = QGroupBox("Parameters")
        params_layout = QVBoxLayout()
        
        self.height_control = ParameterControl(
            "Height Multiplier", 0.5, 5.0, STEP2_PARAMS['HEIGHT_MULTIPLIER'], 
            step=0.1, decimals=1
        )
        params_layout.addWidget(self.height_control)
        
        self.prominence_control = ParameterControl(
            "Prominence", 0.001, 0.5, STEP2_PARAMS['PROMINENCE'], 
            step=0.01, decimals=3
        )
        params_layout.addWidget(self.prominence_control)
        
        self.baseline_window_control = ParameterControl(
            "Baseline Window", 5, 100, STEP2_PARAMS['BASELINE_WINDOW'], 
            step=5, decimals=0
        )
        params_layout.addWidget(self.baseline_window_control)
        
        self.baseline_k_control = ParameterControl(
            "Baseline K", 0.5, 5.0, STEP2_PARAMS['BASELINE_K'], 
            step=0.1, decimals=1
        )
        params_layout.addWidget(self.baseline_k_control)
        
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # Reset defaults button — makes it obvious when params drift
        reset_btn = QPushButton("↺  Reset to Defaults")
        reset_btn.setToolTip(
            f"Reset: Height={STEP2_PARAMS['HEIGHT_MULTIPLIER']}, "
            f"Prominence={STEP2_PARAMS['PROMINENCE']}, "
            f"Window={STEP2_PARAMS['BASELINE_WINDOW']}, "
            f"K={STEP2_PARAMS['BASELINE_K']}"
        )
        reset_btn.clicked.connect(self._on_reset_params)
        layout.addWidget(reset_btn)
        
        # Process button
        self.process_button = QPushButton("🔍  Detect Peaks")
        self.process_button.setStyleSheet(primary_button_style())
        self.process_button.clicked.connect(self._on_process_clicked)
        layout.addWidget(self.process_button)
        
        # Save button
        self.save_button = QPushButton("Save Results")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save_clicked)
        layout.addWidget(self.save_button)
        
        # Info panel
        info_group = QGroupBox("Info")
        info_layout = QVBoxLayout()
        self.info_label = QLabel("Ready to detect peaks")
        self.info_label.setWordWrap(True)
        info_layout.addWidget(self.info_label)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        layout.addStretch()
        panel.setLayout(layout)
        panel.setMaximumWidth(350)

        # Wrap in scroll area for small screens
        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setMaximumWidth(370)
        return scroll
    
    def _create_right_panel(self) -> QWidget:
        """Create right visualization panel (chart tab + data table tab)."""
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Tab widget: one chart tab + one data table tab ─────────────────
        self.view_tabs = QTabWidget()

        # Tab 1: Detected Peaks chart
        self.fig = Figure(figsize=(7, 4), dpi=100)
        chart_bg = get_chart_bg()
        self.fig.patch.set_facecolor(chart_bg)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setStyleSheet(f"background-color: {chart_bg};")
        self.axes = self.fig.add_subplot(111)
        self._style_axes()
        self.toolbar = NavigationToolbar2QT(self.canvas)
        self._hover_annotator = PeakHoverAnnotator(
            self.canvas, radius_px=14.0, x_unit="nm", x_name="Wavelength", y_name="Intensity"
        )

        chart_container = QWidget()
        chart_layout = QVBoxLayout(chart_container)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.addWidget(self.canvas)
        chart_layout.addWidget(self.toolbar)
        self.view_tabs.addTab(chart_container, "Detected Peaks")

        # Tab 2: Data table with pagination
        self._table_page = 0
        self._table_page_size = 100

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Wavelength (nm)", "Intensity"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(4, 4, 4, 4)
        table_layout.setSpacing(4)

        # Header row with pagination controls
        table_header = QHBoxLayout()
        table_title = QLabel("Detected Peaks Preview")
        table_font = QFont()
        table_font.setBold(True)
        table_title.setFont(table_font)
        table_header.addWidget(table_title)
        table_header.addStretch()

        self._table_prev_btn = QPushButton("◀ Prev")
        self._table_prev_btn.setMaximumWidth(70)
        self._table_prev_btn.setEnabled(False)
        self._table_prev_btn.clicked.connect(self._on_table_prev)
        table_header.addWidget(self._table_prev_btn)

        self._table_page_label = QLabel("Page — / —")
        self._table_page_label.setMinimumWidth(90)
        self._table_page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        table_header.addWidget(self._table_page_label)

        self._table_next_btn = QPushButton("Next ▶")
        self._table_next_btn.setMaximumWidth(70)
        self._table_next_btn.setEnabled(False)
        self._table_next_btn.clicked.connect(self._on_table_next)
        table_header.addWidget(self._table_next_btn)

        self._table_count_label = QLabel("")
        self._table_count_label.setMinimumWidth(80)
        self._table_count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table_header.addWidget(self._table_count_label)

        # Copy toggle — appended to the existing pagination row
        self._table_copy_btn = QPushButton("⎘  Copy")
        self._table_copy_btn.setCheckable(True)
        self._table_copy_btn.setFixedHeight(24)
        self._table_copy_btn.setEnabled(False)
        self._table_copy_btn.setToolTip("Copy visible page as TSV to clipboard.\nClick again to deselect.")
        self._table_copy_btn.clicked.connect(
            lambda: on_copy_table_clicked(
                self.table, self._table_copy_btn, self._table_count_label
            )
        )
        table_header.addWidget(self._table_copy_btn)

        table_layout.addLayout(table_header)
        table_layout.addWidget(self.table)
        self.view_tabs.addTab(table_container, "📋 Data Table")

        layout.addWidget(self.view_tabs)
        panel.setLayout(layout)
        return panel

    def _style_axes(self):
        """Apply current theme to the axes."""
        ax = self.axes
        ax.set_facecolor(get_chart_axes_bg())
        ax.tick_params(colors=get_chart_text2(), which="both", labelsize=10)  # was 8
        ax.xaxis.label.set_color(get_chart_text2())
        ax.yaxis.label.set_color(get_chart_text2())
        ax.title.set_color(get_chart_text())
        for spine in ax.spines.values():
            spine.set_edgecolor(get_chart_border())
            spine.set_linewidth(0.8)
        ax.grid(True, color=get_chart_border(), alpha=0.55, linewidth=0.5,
                linestyle="--")

    # Keep old name as alias so any existing call sites don't break
    _apply_dark_style = _style_axes

    def apply_theme(self):
        """Update canvas and axes colours when the global theme changes."""
        from src.gui.theme import step_title_font, instruction_banner_style
        chart_bg = get_chart_bg()
        self.fig.patch.set_facecolor(chart_bg)
        self.canvas.setStyleSheet(f"background-color: {chart_bg};")
        self._style_axes()
        if self.detected_peaks and hasattr(self, 'processed_data') and self.processed_data is not None:
            self._update_chart()
        else:
            self._hover_annotator.update_theme()
            self.canvas.draw()
        # Refresh inline-styled labels
        self._title_label.setStyleSheet(step_title_font(13))
        self._instructions_label.setStyleSheet(instruction_banner_style())
        style_toolbar(self.toolbar)

    # ──────────────────────────────────────────────────────────────────────
    # File selection
    # ──────────────────────────────────────────────────────────────────────

    def _on_browse_spectrum(self):
        recent = self._spectrum_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        fp, _ = QFileDialog.getOpenFileName(
            self, "Select Spectrum File", start_dir, "CSV Files (*.csv)")
        if fp:
            self._set_spectrum_path(Path(fp))

    def _on_recent_spectrum(self, path_str: str):
        self._set_spectrum_path(Path(path_str))

    def _set_spectrum_path(self, path: Path):
        self._spectrum_path = path
        self._spec_path_label.setText(path.name)
        self._spec_path_label.setStyleSheet(
            f"font-size: 9pt; font-weight: 600; color: {C_ACCENT2}; "
            f"border: 1px solid #3A4055; border-radius: 4px; padding: 3px 6px;")
        self._spec_path_label.setToolTip(str(path))
        self._spectrum_history.add_file(str(path))
        self._spec_recent_btn.refresh()
        logger.info(f"Spectrum file selected: {path.name}")

    def _on_process_clicked(self):
        """Detect peaks when button clicked."""
        if self._spectrum_path is None and self.processed_data is None:
            show_error("Error", "Please select an input file")
            return

        self.info_label.setText("Loading file...")
        self.process_button.setEnabled(False)

        # If data was already loaded from Step 1 in-memory, skip file loading
        if self._spectrum_path is None and self.processed_data is not None:
            self._run_detection()
            return

        # Try to load as processed spectra (with Corrected column)
        try:
            reader = CSVReader()
            import pandas as pd
            
            df = pd.read_csv(str(self._spectrum_path))
            
            # Try to find wavelength and corrected/intensity columns
            wl_col = None
            corrected_col = None
            intensity_col = None

            for col in df.columns:
                col_lower = col.lower()
                if 'wavelength' in col_lower or col_lower == 'wl':
                    wl_col = col
                if 'corrected' in col_lower:
                    corrected_col = col
                if ('intensity' in col_lower or 'signal' in col_lower
                        or 'counts' in col_lower):
                    intensity_col = col

            if wl_col is None:
                show_error("Error",
                    "Cannot find a wavelength column in the selected file.\n"
                    "Expected a column named 'Wavelength' or 'wl'.")
                self.process_button.setEnabled(True)
                self.info_label.setText("Error: No wavelength column found")
                return

            # Determine which intensity column to use:
            # Prefer 'Corrected' (Step 1 output); fall back to 'Intensity' (raw file)
            use_col = corrected_col if corrected_col else intensity_col

            if use_col is None:
                show_error("Error",
                    "Cannot find an intensity column in the selected file.\n"
                    "Expected 'Corrected', 'Intensity', 'Signal', or 'Counts'.")
                self.process_button.setEnabled(True)
                self.info_label.setText("Error: No intensity column found")
                return

            class ProcessedSpectra:
                pass

            self.processed_data = ProcessedSpectra()
            self.processed_data.wavelength = df[wl_col].values.astype(float)
            self.processed_data.corrected  = df[use_col].values.astype(float)

            src = "Step 1 corrected" if corrected_col else "raw intensity"
            logger.info(
                f"Loaded spectrum: {len(self.processed_data.wavelength)} points "
                f"using column '{use_col}' ({src})"
            )

        except Exception as e:
            logger.error(f"Failed to load file: {e}")
            show_error("Error", f"Failed to load file:\n{e}")
            self.process_button.setEnabled(True)
            self.info_label.setText("Error loading file")
            return
        
        self._run_detection()

    def _run_detection(self):
        """Launch the peak detection worker (processed_data must already be set)."""
        # Create detector with parameters
        params = {
            'HEIGHT_MULTIPLIER': self.height_control.value(),
            'PROMINENCE': self.prominence_control.value(),
            'BASELINE_WINDOW': int(self.baseline_window_control.value()),
            'BASELINE_K': self.baseline_k_control.value()
        }
        
        self.detector = PeaksDetector(params)
        
        # Process in worker thread
        self.info_label.setText("Detecting peaks... (may take a moment)")
        
        self.worker_thread = WorkerThread(
            self.detector.detect_peaks,
            self.processed_data.wavelength,
            self.processed_data.corrected
        )
        
        self.worker_thread.finished.connect(self._on_detection_finished)
        self.worker_thread.error.connect(self._on_detection_error)
        self.worker_thread.start()
    
    def _on_detection_finished(self, result: dict):
        """Handle detection completion."""
        self.detected_peaks = result.get('result')
        
        if self.detected_peaks:
            logger.info(f"Peaks detection complete: {len(self.detected_peaks)} peaks")
            try:
                from src.gui.session_manager import save_step2
                save_step2(self.detected_peaks)
            except Exception:
                pass
            
            # Extract peak data
            peak_wl = np.array([p.wavelength for p in self.detected_peaks])
            peak_int = np.array([p.intensity for p in self.detected_peaks])
            
            # Update plot
            self._update_chart()
            self.toolbar.home()
            
            # Update table
            self._update_table()
            
            # Update info — show peak count AND the params that produced it
            self.info_label.setText(
                f"Detected: {len(self.detected_peaks)} peaks\n"
                f"Range: {peak_wl.min():.2f} – {peak_wl.max():.2f} nm\n"
                f"Params: Height={self.height_control.value():.1f}  "
                f"K={self.baseline_k_control.value():.1f}  "
                f"Window={int(self.baseline_window_control.value())}"
            )
            
            # Enable save
            self.save_button.setEnabled(True)

            # Notify next step — pass data directly (no file round-trip)
            self.result_ready.emit(self.detected_peaks)
        
        self.process_button.setEnabled(True)
    
    def _on_reset_params(self):
        """Reset all detection parameters to their default values."""
        self.height_control.set_value(STEP2_PARAMS['HEIGHT_MULTIPLIER'])
        self.prominence_control.set_value(STEP2_PARAMS['PROMINENCE'])
        self.baseline_window_control.set_value(STEP2_PARAMS['BASELINE_WINDOW'])
        self.baseline_k_control.set_value(STEP2_PARAMS['BASELINE_K'])
        self.info_label.setText("Parameters reset to defaults. Ready to detect peaks.")
        logger.info("Step 2 parameters reset to defaults")

    def _on_detection_error(self, error: str):
        """Handle detection error."""
        logger.error(f"Detection error: {error}")
        show_error("Detection Error", f"Peak detection failed:\n{error}")
        self.info_label.setText("Error during detection")
        self.process_button.setEnabled(True)
    
    def _on_table_prev(self):
        if self._table_page > 0:
            self._table_page -= 1
            self._update_table()

    def _on_table_next(self):
        if self.detected_peaks is None:
            return
        n_pages = max(1, (len(self.detected_peaks) + self._table_page_size - 1)
                      // self._table_page_size)
        if self._table_page < n_pages - 1:
            self._table_page += 1
            self._update_table()

    def _update_table(self):
        """Update results table with detected peaks (paginated)."""
        if self.detected_peaks is None:
            return
        n_total = len(self.detected_peaks)
        ps = self._table_page_size
        n_pages = max(1, (n_total + ps - 1) // ps)
        self._table_page = max(0, min(self._table_page, n_pages - 1))

        start = self._table_page * ps
        end   = min(start + ps, n_total)

        self.table.setRowCount(end - start)
        for i in range(end - start):
            peak = self.detected_peaks[start + i]
            self.table.setItem(i, 0, QTableWidgetItem(f"{peak.wavelength:.5f}"))
            self.table.setItem(i, 1, QTableWidgetItem(f"{peak.intensity:.3e}"))

        self._table_page_label.setText(f"Page {self._table_page + 1} / {n_pages}")
        self._table_prev_btn.setEnabled(self._table_page > 0)
        self._table_next_btn.setEnabled(self._table_page < n_pages - 1)
        self._table_count_label.setText(f"{n_total:,} peaks total")
        self._table_copy_btn.setEnabled(True)
        self._table_copy_btn.setChecked(False)
        self._table_copy_btn.setText("⎘  Copy")
    
    def load_from_step1(self, processed_data) -> None:
        """
        Auto-load Step 1 output directly into Step 2 (no file picker needed).

        processed_data — a ProcessedSpectra object with .wavelength and .corrected arrays.
        The file path label is updated to indicate the data came from Step 1.
        """
        if processed_data is None:
            return
        self.processed_data = processed_data
        n = len(processed_data.wavelength)

        # Update the UI path label so the user knows where data came from
        self._spectrum_path = None   # no file on disk — data is in memory
        self._spec_path_label.setText("← loaded from Step 1")
        self._spec_path_label.setStyleSheet(
            f"font-size: 9pt; font-weight: 600; color: {C_ACCENT2}; "
            f"border: 1px solid #3A4055; border-radius: 4px; padding: 3px 6px;")
        self._spec_path_label.setToolTip(
            "Spectrum data was passed in-memory from Step 1 — no file needed.")

        self.info_label.setText(
            f"✅ {n:,} points loaded from Step 1.\n"
            "Adjust parameters if needed, then click 'Detect Peaks'."
        )
        logger.info("Step 2: in-memory data loaded from Step 1 (%d points)", n)

    def _on_save_clicked(self):
        """Save detected peaks — user picks a directory, filenames get a timestamp."""
        if self.detected_peaks is None:
            show_error("Error", "No peaks to save")
            return

        from PyQt6.QtWidgets import QFileDialog  # already imported at top — kept for clarity
        from datetime import datetime

        # Open save dialog in the same folder as the loaded spectrum (if known)
        recent = self._spectrum_history.get_recent()
        start_dir = str(Path(recent[0]).parent) if recent else str(Path.home())
        save_dir = QFileDialog.getExistingDirectory(
            self, "Select Save Directory", start_dir
        )
        if not save_dir:
            return  # user cancelled

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_name  = f"detected_peaks_{ts}.csv"
        plot_name = f"detected_peaks_{ts}.png"
        csv_path_str  = str(Path(save_dir) / csv_name)
        plot_path_str = str(Path(save_dir) / plot_name)

        try:
            writer = CSVWriter()
            csv_path = writer.write_detected_peaks(csv_path_str, self.detected_peaks)
            logger.info(f"Saved detected peaks to {csv_path}")

            # Generate plot
            plot_gen = PlotGenerator()
            peak_wl  = np.array([p.wavelength for p in self.detected_peaks])
            peak_int = np.array([p.intensity  for p in self.detected_peaks])
            plot_path = plot_gen.plot_step2_peaks(
                self.processed_data.wavelength,
                self.processed_data.corrected,
                self.detected_peaks,
                plot_path_str,
            )
            logger.info(f"Saved peak plot to {plot_path}")

            show_info(
                "Saved",
                f"Files saved to:\n{save_dir}\n\n"
                f"  {csv_name}\n  {plot_name}"
            )

        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            show_error("Error", f"Failed to save results:\n{e}")
