# -*- coding: utf-8 -*-
"""
Step 5 Widget - Validation with Reference Spectra

Provides UI for validating processed spectra against reference spectra.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QDoubleSpinBox,
    QFileDialog, QSpinBox
)
from PyQt6.QtGui import QFont

from src import setup_logger
from src.config import STEP5_PARAMS
from src.core.step5_validation import ValidationAnalyzer
from src.io.file_reader import CSVReader
from src.gui.gui_utils import (
    FileSelector, WorkerThread,
    show_error, show_info
)
from src.gui.theme import primary_button_style, instruction_banner_style, step_title_font

logger = setup_logger(__name__)


class Step5Widget(QWidget):
    """
    UI widget for Step 5: Validation with Reference Spectra.
    
    Allows users to:
    - Load processed and reference spectra
    - Specify target wavelengths for validation
    - Calculate validation coefficients
    - View correlation results
    - Save validation report
    """
    
    def __init__(self, file_history=None, notes_panel=None):
        """
        Initialize Step 5 widget.
        
        Parameters
        ----------
        file_history : FileHistory, optional
            Shared file history object
        notes_panel : NotesPanel, optional
            Shared notes panel widget
        """
        super().__init__()
        self.processed_spectrum = None
        self.reference_spectrum = None
        self.validation_results = None
        self.analyzer = None
        self.worker_thread = None
        self.file_history = file_history
        self.notes_panel = notes_panel
        
        logger.info("Initializing Step 5 widget")
        
        main_layout = QVBoxLayout()
        
        # Top section (controls)
        controls_layout = self._create_controls()
        main_layout.addLayout(controls_layout)
        
        # Results table
        self.results_table = self._create_results_table()
        main_layout.addWidget(self.results_table, stretch=1)
        
        self.setLayout(main_layout)
    
    def _create_controls(self) -> QVBoxLayout:
        """Create control section."""
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Step 5: Validation with Reference Spectra")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        title.setStyleSheet(step_title_font(13))
        layout.addWidget(title)

        # Instructions
        instructions = QLabel(
            "📋 Instructions:\n"
            "1. 'Processed Spectrum': load your baseline-corrected spectrum CSV from Step 1\n"
            "   ('SG_ALS_LIBS_processed.csv'). Must have wavelength and intensity columns.\n"
            "2. 'Reference Spectrum': load a pure-element reference spectrum CSV for comparison.\n"
            "   Must have wavelength and intensity (or 'signal'/'counts') columns.\n"
            "3. Specify target wavelengths — the emission lines to validate:\n"
            "   • 'Load from File': CSV (first column = wavelengths) or plain text (one wavelength per line).\n"
            "   • 'Enter Manually': type wavelengths directly, one per line.\n"
            "4. Adjust parameters if needed:\n"
            "   • Window (nm): spectral region ± window around each target line used for correlation.\n"
            "   • Min Points: minimum data points required in each region (increase if validation fails).\n"
            "   • VC Threshold: validation coefficient ≥ this value is rated 'Good' (0–1 scale).\n"
            "5. Click 'Validate Spectrum' to compute Pearson correlation at each target line.\n"
            "6. Results show the Validation Coefficient (VC) per line: Good ≥ 0.8, Fair ≥ 0.6, Poor < 0.6.\n"
            "7. Click 'Save Report' to export the validation results as CSV."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(instruction_banner_style())
        layout.addWidget(instructions)

        # Files section
        files_group = QGroupBox("Input Spectra")
        files_layout = QHBoxLayout()
        
        self.processed_selector = FileSelector(
            "Processed Spectrum:", "CSV Files (*.csv)"
        )
        files_layout.addWidget(self.processed_selector)
        
        self.reference_selector = FileSelector(
            "Reference Spectrum:", "CSV Files (*.csv)"
        )
        files_layout.addWidget(self.reference_selector)
        
        files_group.setLayout(files_layout)
        layout.addWidget(files_group)
        
        # Parameters section
        params_group = QGroupBox("Parameters")
        params_layout = QHBoxLayout()
        
        # Window size
        window_layout = QVBoxLayout()
        window_label = QLabel("Window (nm):")
        self.window_spinbox = QDoubleSpinBox()
        self.window_spinbox.setMinimum(0.01)
        self.window_spinbox.setMaximum(10.0)
        self.window_spinbox.setValue(STEP5_PARAMS['WINDOW'])
        self.window_spinbox.setSingleStep(0.1)
        self.window_spinbox.setDecimals(2)
        window_layout.addWidget(window_label)
        window_layout.addWidget(self.window_spinbox)
        params_layout.addLayout(window_layout)
        
        # Min points
        points_layout = QVBoxLayout()
        points_label = QLabel("Min Points:")
        self.min_points_spinbox = QSpinBox()
        self.min_points_spinbox.setMinimum(2)
        self.min_points_spinbox.setMaximum(100)
        self.min_points_spinbox.setValue(STEP5_PARAMS['MIN_POINTS'])
        points_layout.addWidget(points_label)
        points_layout.addWidget(self.min_points_spinbox)
        params_layout.addLayout(points_layout)
        
        # VC Threshold
        threshold_layout = QVBoxLayout()
        threshold_label = QLabel("VC Threshold:")
        self.threshold_spinbox = QDoubleSpinBox()
        self.threshold_spinbox.setMinimum(0.0)
        self.threshold_spinbox.setMaximum(1.0)
        self.threshold_spinbox.setValue(STEP5_PARAMS['VC_THRESHOLD'])
        self.threshold_spinbox.setSingleStep(0.1)
        self.threshold_spinbox.setDecimals(2)
        threshold_layout.addWidget(threshold_label)
        threshold_layout.addWidget(self.threshold_spinbox)
        params_layout.addLayout(threshold_layout)
        
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)
        
        # Target wavelengths section
        lines_group = QGroupBox("Target Wavelengths (nm)")
        lines_layout = QHBoxLayout()
        
        self.wavelengths_label = QLabel("No wavelengths specified")
        lines_layout.addWidget(self.wavelengths_label)
        
        self.load_lines_button = QPushButton("Load from File...")
        self.load_lines_button.clicked.connect(self._on_load_wavelengths)
        lines_layout.addWidget(self.load_lines_button)
        
        self.manual_lines_button = QPushButton("Enter Manually...")
        self.manual_lines_button.clicked.connect(self._on_manual_wavelengths)
        lines_layout.addWidget(self.manual_lines_button)
        
        lines_group.setLayout(lines_layout)
        layout.addWidget(lines_group)
        
        # Action buttons
        buttons_layout = QHBoxLayout()
        
        self.validate_button = QPushButton("✔  Validate Spectrum")
        self.validate_button.setStyleSheet(primary_button_style())
        self.validate_button.clicked.connect(self._on_validate_clicked)
        buttons_layout.addWidget(self.validate_button)
        
        self.save_button = QPushButton("Save Report")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save_clicked)
        buttons_layout.addWidget(self.save_button)
        
        # Info label
        self.info_label = QLabel("Ready to validate spectrum")
        self.info_label.setWordWrap(True)
        buttons_layout.addWidget(self.info_label)
        
        layout.addLayout(buttons_layout)
        
        return layout
    
    def _create_results_table(self) -> QTableWidget:
        """Create results display table."""
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels([
            "Wavelength (nm)", "Validation Coefficient", "Status", "Quality"
        ])
        
        table.setSortingEnabled(True)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        return table
    
    def _on_load_wavelengths(self):
        """Load wavelengths from file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Wavelengths File", "",
            "CSV Files (*.csv);;Text Files (*.txt)"
        )
        
        if not filepath:
            return
        
        try:
            # Try to read as CSV
            if filepath.endswith('.csv'):
                df = pd.read_csv(filepath)
                # Get first column as wavelengths
                wavelengths = df.iloc[:, 0].values
            else:
                # Read as text file
                with open(filepath, 'r') as f:
                    wavelengths = [float(line.strip()) for line in f if line.strip()]
            
            self.target_wavelengths = list(wavelengths)
            self.wavelengths_label.setText(
                f"{len(self.target_wavelengths)} wavelengths loaded"
            )
            logger.info(f"Loaded {len(self.target_wavelengths)} wavelengths")
        
        except Exception as e:
            logger.error(f"Failed to load wavelengths: {e}")
            show_error("Error", f"Failed to load wavelengths:\n{e}")
    
    def _on_manual_wavelengths(self):
        """Enter wavelengths manually."""
        from PyQt6.QtWidgets import QInputDialog
        
        text, ok = QInputDialog.getMultiLineText(
            self, "Enter Target Wavelengths",
            "Enter wavelengths (nm), one per line:"
        )
        
        if ok and text:
            try:
                wavelengths = [float(line.strip()) for line in text.split('\n') if line.strip()]
                self.target_wavelengths = wavelengths
                self.wavelengths_label.setText(
                    f"{len(self.target_wavelengths)} wavelengths entered"
                )
                logger.info(f"Entered {len(self.target_wavelengths)} wavelengths manually")
            except ValueError as e:
                show_error("Error", f"Invalid wavelength format:\n{e}")
    
    def _on_validate_clicked(self):
        """Validate spectrum."""
        # Check inputs
        if self.processed_selector.get_filepath() is None:
            show_error("Error", "Please select processed spectrum file")
            return
        if self.reference_selector.get_filepath() is None:
            show_error("Error", "Please select reference spectrum file")
            return
        if not hasattr(self, 'target_wavelengths') or not self.target_wavelengths:
            show_error("Error", "Please specify target wavelengths")
            return
        
        self.info_label.setText("Validating spectrum...")
        self.validate_button.setEnabled(False)
        self.save_button.setEnabled(False)
        
        # Run validation in worker thread
        self.worker_thread = WorkerThread(
            self._validate_worker
        )
        self.worker_thread.finished.connect(self._on_validation_finished)
        self.worker_thread.error.connect(self._on_worker_error)
        self.worker_thread.start()
    
    def _validate_worker(self):
        """Worker thread for validation."""
        try:
            # Load spectra
            processed = pd.read_csv(str(self.processed_selector.get_filepath()))
            reference = pd.read_csv(str(self.reference_selector.get_filepath()))
            
            # Create analyzer
            params = {
                'WINDOW': self.window_spinbox.value(),
                'MIN_POINTS': self.min_points_spinbox.value(),
                'INTERPOLATION_KIND': STEP5_PARAMS['INTERPOLATION_KIND'],
                'VC_THRESHOLD': self.threshold_spinbox.value()
            }
            analyzer = ValidationAnalyzer(params)
            
            # Validate
            results = analyzer.validate_spectrum(
                processed, reference, self.target_wavelengths
            )
            
            self.validation_results = results
            
            return True, "Validation completed successfully"
        
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return False, str(e)
    
    def _on_worker_error(self, error_message: str):
        """Handle worker thread unhandled exception."""
        self.validate_button.setEnabled(True)
        show_error("Validation Error", error_message)
        self.info_label.setText(f"Error: {error_message}")

    def _on_validation_finished(self, _result: dict = None):
        """Handle validation completion."""
        if self.worker_thread is None:
            return

        result = self.worker_thread.result
        if result is None:
            self.validate_button.setEnabled(True)
            show_error("Validation Failed", "Worker returned no result")
            return

        success, message = result
        self.validate_button.setEnabled(True)
        
        if not success:
            show_error("Validation Failed", message)
            self.info_label.setText(f"Error: {message}")
            return
        
        # Update table
        self._populate_results_table()
        
        self.save_button.setEnabled(True)
        
        # Calculate statistics
        valid_vc = self.validation_results[
            self.validation_results['Validation_Coefficient'].notna()
        ]['Validation_Coefficient']
        
        if not valid_vc.empty:
            mean_vc = valid_vc.mean()
            self.info_label.setText(
                f"Validation complete! Mean VC: {mean_vc:.4f} "
                f"({len(valid_vc)} lines validated)"
            )
        
        logger.info("Validation finished successfully")
    
    def _populate_results_table(self):
        """Populate results table."""
        if self.validation_results is None:
            return
        
        df = self.validation_results
        self.results_table.setRowCount(len(df))
        
        for row, (_, r_data) in enumerate(df.iterrows()):
            wl = f"{r_data['Wavelength_nm']:.2f}"
            self.results_table.setItem(row, 0, QTableWidgetItem(wl))
            
            vc_val = r_data['Validation_Coefficient']
            if pd.isna(vc_val):
                vc_str = "N/A"
                quality = "Failed"
            else:
                vc_str = f"{vc_val:.4f}"
                quality = "Good" if vc_val > 0.8 else "Fair" if vc_val > 0.6 else "Poor"
            
            self.results_table.setItem(row, 1, QTableWidgetItem(vc_str))
            self.results_table.setItem(row, 2, QTableWidgetItem(r_data['Status']))
            self.results_table.setItem(row, 3, QTableWidgetItem(quality))
        
        logger.info("Results table populated")
    
    def _on_save_clicked(self):
        """Save validation report."""
        if self.validation_results is None:
            show_error("Error", "No results to save")
            return
        
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Validation Report", "validation_results",
            "CSV Files (*.csv)"
        )
        
        if filepath:
            try:
                self.validation_results.to_csv(filepath, index=False)
                show_info("Success", f"Report saved to:\n{filepath}")
                logger.info(f"Report saved to {filepath}")
            except Exception as e:
                logger.error(f"Failed to save report: {e}")
                show_error("Error", f"Failed to save report:\n{e}")
