# -*- coding: utf-8 -*-
"""
Step 2 Widget - Automatic Peaks Detection

Provides UI for peak detection with visualization and results table.
"""

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QSplitter, QScrollArea
)
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from src import setup_logger
from src.config import STEP2_PARAMS
from src.core.step2_peaks import PeaksDetector
from src.io.file_reader import CSVReader
from src.io.file_writer import CSVWriter, PlotGenerator
from src.gui.gui_utils import (
    ParameterControl, FileSelector, WorkerThread,
    show_error, show_info
)
from src.gui.theme import (
    primary_button_style, instruction_banner_style, step_title_font,
    C_BG_BASE, C_BG_RAISED, C_BORDER_SUBTLE, C_ACCENT, C_WARN, C_TEXT, C_TEXT2,
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
            "4. Click 'Save Results' to export the detected peaks CSV and plot PNG.\n"
            "   The CSV is required as input for Step 3."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(instruction_banner_style())
        layout.addWidget(instructions)

        # File selection
        file_group = QGroupBox("Input File")
        file_layout = QVBoxLayout()
        self.file_selector = FileSelector(
            "Processed Spectrum:", 
            "CSV Files (*.csv)"
        )
        file_layout.addWidget(self.file_selector)
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
        """Create right visualization panel."""
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Splitter for plot+toolbar and table
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Plot canvas with navigation toolbar (zoom, pan, coordinates)
        self.fig = Figure(figsize=(7, 4), dpi=100)
        self.fig.patch.set_facecolor(C_BG_BASE)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setStyleSheet(f"background-color: {C_BG_BASE};")
        self.axes = self.fig.add_subplot(111)
        self._apply_dark_style()
        self.toolbar = NavigationToolbar2QT(self.canvas)

        chart_container = QWidget()
        chart_layout = QVBoxLayout(chart_container)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.addWidget(self.canvas)
        chart_layout.addWidget(self.toolbar)
        splitter.addWidget(chart_container)

        # Results table
        table_label = QLabel("Detected Peaks Preview")
        table_font = QFont()
        table_font.setBold(True)
        table_label.setFont(table_font)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Wavelength (nm)", "Intensity"])

        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(4, 4, 4, 4)
        table_layout.addWidget(table_label)
        table_layout.addWidget(self.table)
        splitter.addWidget(table_container)

        splitter.setSizes([500, 250])
        layout.addWidget(splitter)

        panel.setLayout(layout)
        return panel

    def _apply_dark_style(self):
        """Apply dark theme to the axes."""
        ax = self.axes
        ax.set_facecolor(C_BG_RAISED)
        ax.tick_params(colors=C_TEXT2, which="both", labelsize=8)
        ax.xaxis.label.set_color(C_TEXT2)
        ax.yaxis.label.set_color(C_TEXT2)
        ax.title.set_color(C_TEXT)
        for spine in ax.spines.values():
            spine.set_edgecolor(C_BORDER_SUBTLE)
            spine.set_linewidth(0.8)
        ax.grid(True, color=C_BORDER_SUBTLE, alpha=0.55, linewidth=0.5, linestyle="--")
    
    def _on_process_clicked(self):
        """Detect peaks when button clicked."""
        if self.file_selector.get_filepath() is None:
            show_error("Error", "Please select an input file")
            return
        
        self.info_label.setText("Loading file...")
        self.process_button.setEnabled(False)
        
        # Try to load as processed spectra (with Corrected column)
        try:
            reader = CSVReader()
            import pandas as pd
            
            df = pd.read_csv(str(self.file_selector.get_filepath()))
            
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
            
            # Extract peak data
            peak_wl = np.array([p.wavelength for p in self.detected_peaks])
            peak_int = np.array([p.intensity for p in self.detected_peaks])
            
            # Update plot
            self.axes.clear()
            self.axes.plot(
                self.processed_data.wavelength,
                self.processed_data.corrected,
                color=C_ACCENT, linewidth=0.9, alpha=0.9,
                label="Spectrum"
            )
            self.axes.scatter(
                peak_wl, peak_int,
                color=C_WARN, s=32, marker="x", linewidths=1.4,
                label=f"Peaks ({len(peak_wl)})", zorder=3
            )
            self.axes.set_xlabel("Wavelength (nm)")
            self.axes.set_ylabel("Intensity")
            self.axes.set_title("Detected Peaks")
            leg = self.axes.legend(loc="upper right", fontsize=8, framealpha=0.6)
            leg.get_frame().set_facecolor(C_BG_RAISED)
            leg.get_frame().set_edgecolor(C_BORDER_SUBTLE)
            for txt in leg.get_texts():
                txt.set_color(C_TEXT2)
            self._apply_dark_style()
            self.fig.tight_layout(pad=1.2)
            self.canvas.draw()
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
    
    def _update_table(self):
        """Update results table with detected peaks."""
        if self.detected_peaks is None:
            return
        
        n_rows = min(10, len(self.detected_peaks))
        self.table.setRowCount(n_rows)
        
        for i in range(n_rows):
            peak = self.detected_peaks[i]
            self.table.setItem(i, 0, QTableWidgetItem(f"{peak.wavelength:.5f}"))
            self.table.setItem(i, 1, QTableWidgetItem(f"{peak.intensity:.6g}"))
    
    def _on_save_clicked(self):
        """Save detected peaks — user picks a directory, filenames get a timestamp."""
        if self.detected_peaks is None:
            show_error("Error", "No peaks to save")
            return

        from PyQt6.QtWidgets import QFileDialog
        from datetime import datetime

        # Ask user where to save
        save_dir = QFileDialog.getExistingDirectory(
            self, "Select Save Directory", str(Path.home())
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
