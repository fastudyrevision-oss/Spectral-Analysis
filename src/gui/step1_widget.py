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
    QTableWidget, QTableWidgetItem, QScrollArea, QSplitter, QMessageBox
)
from PyQt6.QtGui import QFont

from src import setup_logger
from src.config import STEP1_PARAMS
from src.core.step1_sg_als import BaselineCorrection
from src.io.file_reader import CSVReader
from src.io.file_writer import CSVWriter, PlotGenerator
from src.gui.gui_utils import (
    ParameterControl, MatplotlibCanvas, FileSelector, WorkerThread,
    show_error, show_info
)

logger = setup_logger(__name__)


class Step1Widget(QWidget):
    """
    UI widget for Step 1: SG-ALS Baseline Correction.
    
    Allows users to:
    - Select input spectrum file
    - Adjust baseline correction parameters
    - Preview results with plots
    - Save processed spectra
    """
    
    # Signals
    processing_started = pyqtSignal()
    processing_finished = pyqtSignal(dict)
    
    def __init__(self):
        """Initialize Step 1 widget."""
        super().__init__()
        self.processed_data = None
        self.raw_data = None
        self.corrector = None
        self.worker_thread = None
        
        logger.info("Initializing Step 1 widget")
        
        # Main layout
        main_layout = QHBoxLayout()
        
        # Left panel (controls)
        left_panel = self._create_left_panel()
        main_layout.addWidget(left_panel, stretch=0)
        
        # Right panel (visualization)
        right_panel = self._create_right_panel()
        main_layout.addWidget(right_panel, stretch=1)
        
        self.setLayout(main_layout)
    
    def _create_left_panel(self) -> QWidget:
        """Create left control panel."""
        panel = QWidget()
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Step 1: SG-ALS Baseline Correction")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # File selection
        file_group = QGroupBox("Input File")
        file_layout = QVBoxLayout()
        self.file_selector = FileSelector("Spectrum File:", "CSV Files (*.csv)")
        file_layout.addWidget(self.file_selector)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # Parameters group
        params_group = QGroupBox("Parameters")
        params_layout = QVBoxLayout()
        
        # Get default values
        self.lambda_control = ParameterControl(
            "Lambda (λ)", 1e3, 1e6, STEP1_PARAMS['LAMBDA'], step=1e4, decimals=0
        )
        params_layout.addWidget(self.lambda_control)
        
        self.p_control = ParameterControl(
            "Asymmetry (p)", 0.001, 0.1, STEP1_PARAMS['P'], step=0.001, decimals=4
        )
        params_layout.addWidget(self.p_control)
        
        self.niter_control = ParameterControl(
            "Iterations", 1, 50, STEP1_PARAMS['NITER'], step=1, decimals=0
        )
        params_layout.addWidget(self.niter_control)
        
        self.window_control = ParameterControl(
            "SG Window", 3, 21, STEP1_PARAMS['WINDOW'], step=2, decimals=0
        )
        params_layout.addWidget(self.window_control)
        
        self.poly_control = ParameterControl(
            "SG Poly Order", 1, 5, STEP1_PARAMS['POLY'], step=1, decimals=0
        )
        params_layout.addWidget(self.poly_control)
        
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)
        
        # Process button
        self.process_button = QPushButton("Process")
        self.process_button.setStyleSheet(
            "QPushButton { background-color: #2E86AB; color: white; "
            "padding: 8px; font-weight: bold; border-radius: 4px; }"
        )
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
        self.info_label = QLabel("Ready to process")
        self.info_label.setWordWrap(True)
        info_layout.addWidget(self.info_label)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Stretch at bottom
        layout.addStretch()
        
        panel.setLayout(layout)
        panel.setMaximumWidth(350)
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """Create right visualization panel."""
        panel = QWidget()
        layout = QVBoxLayout()
        
        # Splitter for plot and table
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Plot canvas
        self.canvas = MatplotlibCanvas(width=7, height=4, dpi=100)
        splitter.addWidget(self.canvas)
        
        # Results table
        table_label = QLabel("Processed Data Preview")
        table_font = QFont()
        table_font.setBold(True)
        table_label.setFont(table_font)
        layout.addWidget(table_label)
        
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Wavelength (nm)", "Raw", "Smoothed_SG", "Baseline_ALS", "Corrected"
        ])
        self.table.setMaximumHeight(200)
        splitter.addWidget(self.table)
        
        splitter.setSizes([600, 200])
        layout.addWidget(splitter)
        
        panel.setLayout(layout)
        return panel
    
    def _on_process_clicked(self):
        """Process spectrum when button clicked."""
        # Validate input
        if self.file_selector.get_filepath() is None:
            show_error("Error", "Please select an input file")
            return
        
        # Update info
        self.info_label.setText("Loading file...")
        self.process_button.setEnabled(False)
        
        # Read file
        try:
            reader = CSVReader()
            self.raw_data = reader.read_raw_spectra(str(self.file_selector.get_filepath()))
            logger.info(f"Loaded spectrum: {len(self.raw_data.wavelength)} points")
        except Exception as e:
            logger.error(f"Failed to load file: {e}")
            show_error("Error", f"Failed to load file:\n{e}")
            self.process_button.setEnabled(True)
            self.info_label.setText("Error loading file")
            return
        
        # Create corrector with parameters
        params = {
            'LAMBDA': self.lambda_control.value(),
            'P': self.p_control.value(),
            'NITER': int(self.niter_control.value()),
            'WINDOW': int(self.window_control.value()),
            'POLY': int(self.poly_control.value())
        }
        
        self.corrector = BaselineCorrection(params)
        
        # Process in worker thread
        self.info_label.setText("Processing... (may take a moment)")
        
        self.worker_thread = WorkerThread(
            self.corrector.process,
            self.raw_data.wavelength,
            self.raw_data.intensity
        )
        
        self.worker_thread.finished.connect(self._on_processing_finished)
        self.worker_thread.error.connect(self._on_processing_error)
        self.worker_thread.start()
    
    def _on_processing_finished(self, result: dict):
        """Handle processing completion."""
        self.processed_data = result.get('result')
        
        if self.processed_data:
            logger.info("Baseline correction complete")
            
            # Update plot
            self.canvas.plot_spectrum(
                self.processed_data.wavelength,
                self.processed_data.corrected,
                title="Corrected Spectrum",
                ylabel="Intensity (baseline subtracted)"
            )
            
            # Update table with first 10 rows
            self._update_table()
            
            # Update info
            self.info_label.setText(
                f"Processed: {len(self.processed_data.wavelength)} points\n"
                f"Corrected range: {np.min(self.processed_data.corrected):.2e} "
                f"to {np.max(self.processed_data.corrected):.2e}"
            )
            
            # Enable save button
            self.save_button.setEnabled(True)
        
        self.process_button.setEnabled(True)
    
    def _on_processing_error(self, error: str):
        """Handle processing error."""
        logger.error(f"Processing error: {error}")
        show_error("Processing Error", f"Baseline correction failed:\n{error}")
        self.info_label.setText("Error during processing")
        self.process_button.setEnabled(True)
    
    def _update_table(self):
        """Update results table with processed data."""
        if self.processed_data is None:
            return
        
        # Show first 10 rows
        n_rows = min(10, len(self.processed_data.wavelength))
        self.table.setRowCount(n_rows)
        
        for i in range(n_rows):
            wl = self.processed_data.wavelength[i]
            raw = self.processed_data.raw[i]
            sg = self.processed_data.smoothed_sg[i]
            baseline = self.processed_data.baseline_als[i]
            corrected = self.processed_data.corrected[i]
            
            # Wavelength
            self.table.setItem(i, 0, QTableWidgetItem(f"{wl:.5f}"))
            # Raw
            self.table.setItem(i, 1, QTableWidgetItem(f"{raw:.6g}"))
            # Smoothed_SG
            self.table.setItem(i, 2, QTableWidgetItem(f"{sg:.6g}"))
            # Baseline_ALS
            self.table.setItem(i, 3, QTableWidgetItem(f"{baseline:.6g}"))
            # Corrected
            self.table.setItem(i, 4, QTableWidgetItem(f"{corrected:.6g}"))
    
    def _on_save_clicked(self):
        """Save processed results to file."""
        if self.processed_data is None:
            show_error("Error", "No processed data to save")
            return
        
        try:
            writer = CSVWriter()
            csv_path = writer.write_processed_spectra("SG_ALS_LIBS_processed.csv", self.processed_data)
            logger.info(f"Saved processed spectra to {csv_path}")
            
            # Generate plot
            plot_gen = PlotGenerator()
            plot_path = plot_gen.plot_step1_baseline(self.processed_data, "SG_ALS_LIBS_processed.png")
            logger.info(f"Saved baseline plot to {plot_path}")
            
            show_info("Success", f"Results saved:\n- {csv_path}\n- {plot_path}")
            
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            show_error("Error", f"Failed to save results:\n{e}")
