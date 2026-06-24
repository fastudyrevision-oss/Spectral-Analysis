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
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtGui import QFont

from src import setup_logger
from src.config import STEP3_PARAMS
from src.core.step3_nist_matching import NISTMatcher
from src.io.file_reader import CSVReader
from src.io.file_writer import CSVWriter
from src.gui.gui_utils import (
    ParameterControl, FileSelector, WorkerThread,
    show_error, show_info
)
from src.gui.theme import primary_button_style, instruction_banner_style, step_title_font

logger = setup_logger(__name__)


class Step3Widget(QWidget):
    """
    UI widget for Step 3: NIST Element Identification.
    
    Allows users to:
    - Select detected peaks file
    - Select NIST database file(s)
    - Match peaks to elements
    - Sort and filter results
    - Save matching results
    """
    
    def __init__(self, file_history=None, notes_panel=None):
        """
        Initialize Step 3 widget.
        
        Parameters
        ----------
        file_history : FileHistory, optional
            Shared file history object
        notes_panel : NotesPanel, optional
            Shared notes panel widget
        """
        super().__init__()
        self.detected_peaks = None
        self.nist_db = None
        self.matches = None
        self.matcher = None
        self.worker_thread = None
        self.file_history = file_history
        self.notes_panel = notes_panel
        
        logger.info("Initializing Step 3 widget")
        
        main_layout = QVBoxLayout()
        
        # Top section (controls)
        controls_layout = self._create_controls()
        main_layout.addLayout(controls_layout)
        
        # Bottom section (results table)
        self.table = self._create_results_table()
        main_layout.addWidget(self.table, stretch=1)
        
        self.setLayout(main_layout)
    
    def _create_controls(self) -> QVBoxLayout:
        """Create control section."""
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Step 3: NIST Element Identification")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        title.setStyleSheet(step_title_font(13))
        layout.addWidget(title)

        # Instructions
        instructions = QLabel(
            "📋 Instructions:\n"
            "1. 'Detected Peaks': load the peaks CSV from Step 2 (e.g. 'detected_peaks.csv').\n"
            "   • File must have a wavelength column and an intensity column.\n"
            "2. 'NIST Database': load an element reference CSV from the NIST database.\n"
            "   • File must have a wavelength column; Element, Aki, and Relative Intensity columns are used if present.\n"
            "   • Run this step once per element — repeat with a different NIST file to match another element.\n"
            "3. Set Tolerance (nm): maximum allowed wavelength difference for a match (default 0.2 nm).\n"
            "4. Set Min Score: minimum score to display a match — leave at 0 to see all matches.\n"
            "5. Click 'Match Peaks' to cross-match detected peaks against the NIST database.\n"
            "6. Results are listed in the table below, sortable by any column.\n"
            "7. Click 'Save Results' to export 'LIBS_matching_results.csv'.\n"
            "   ⚠ Run this step for each element and save each result file — all result files are required for Step 4."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(instruction_banner_style())
        layout.addWidget(instructions)

        # Files group
        files_group = QGroupBox("Input Files")
        files_layout = QHBoxLayout()
        
        # Peaks file
        self.peaks_selector = FileSelector("Detected Peaks:", "CSV Files (*.csv)")
        files_layout.addWidget(self.peaks_selector)
        
        # NIST file
        self.nist_selector = FileSelector("NIST Database:", "CSV Files (*.csv)")
        files_layout.addWidget(self.nist_selector)
        
        files_group.setLayout(files_layout)
        layout.addWidget(files_group)
        
        # Parameters group
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
        
        # Buttons
        buttons_layout = QHBoxLayout()
        
        self.match_button = QPushButton("🔬  Match Peaks")
        self.match_button.setStyleSheet(primary_button_style())
        self.match_button.clicked.connect(self._on_match_clicked)
        buttons_layout.addWidget(self.match_button)
        
        self.save_button = QPushButton("Save Results")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save_clicked)
        buttons_layout.addWidget(self.save_button)
        
        # Info label
        self.info_label = QLabel("Ready to match peaks")
        self.info_label.setWordWrap(True)
        buttons_layout.addWidget(self.info_label)
        
        layout.addLayout(buttons_layout)
        
        return layout
    
    def _create_results_table(self) -> QTableWidget:
        """Create results display table."""
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            "Observed (nm)", "Matched (nm)", "Delta (nm)", "Element", 
            "Aki", "Rel. Int.", "Score"
        ])
        
        # Make sortable
        table.setSortingEnabled(True)
        
        # Resize columns
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        return table
    
    def _on_match_clicked(self):
        """Match peaks when button clicked."""
        # Validate files
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
            
            # Load detected peaks
            self.detected_peaks = reader.read_detected_peaks(
                str(self.peaks_selector.get_filepath())
            )
            logger.info(f"Loaded {len(self.detected_peaks)} detected peaks")
            
            # Load NIST database
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
        
        # Create matcher
        params = {
            'TOLERANCE': self.tolerance_control.value(),
            'MIN_SCORE_THRESHOLD': self.threshold_control.value()
        }
        self.matcher = NISTMatcher(params)
        
        # Match in worker thread
        self.info_label.setText("Matching peaks... (may take a moment)")
        
        self.worker_thread = WorkerThread(
            self.matcher.match_peaks,
            self.detected_peaks,
            self.nist_db
        )
        
        self.worker_thread.finished.connect(self._on_matching_finished)
        self.worker_thread.error.connect(self._on_matching_error)
        self.worker_thread.start()
    
    def _on_matching_finished(self, result: dict):
        """Handle matching completion."""
        self.matches = result.get('result')
        
        if self.matches:
            logger.info(f"Matching complete: {len(self.matches)} results")
            
            # Update table
            self._update_table()
            
            # Count identified peaks
            identified = [m for m in self.matches if m.element]
            self.info_label.setText(
                f"Matched: {len(identified)} peaks identified as elements"
            )
            
            # Enable save
            self.save_button.setEnabled(True)
        
        self.match_button.setEnabled(True)
    
    def _on_matching_error(self, error: str):
        """Handle matching error."""
        logger.error(f"Matching error: {error}")
        show_error("Matching Error", f"Peak matching failed:\n{error}")
        self.info_label.setText("Error during matching")
        self.match_button.setEnabled(True)
    
    def _update_table(self):
        """Update results table with matches."""
        if self.matches is None:
            return
        
        self.table.setRowCount(len(self.matches))
        
        for i, match in enumerate(self.matches):
            # Observed WL
            self.table.setItem(i, 0, QTableWidgetItem(f"{match.observed_wl:.5f}"))
            
            # Matched WL
            if match.matched_wl:
                self.table.setItem(i, 1, QTableWidgetItem(f"{match.matched_wl:.5f}"))
            else:
                self.table.setItem(i, 1, QTableWidgetItem("—"))
            
            # Delta
            if match.delta is not None:
                self.table.setItem(i, 2, QTableWidgetItem(f"{match.delta:.4f}"))
            else:
                self.table.setItem(i, 2, QTableWidgetItem("—"))
            
            # Element
            element_text = match.element if match.element else "—"
            self.table.setItem(i, 3, QTableWidgetItem(element_text))
            
            # Aki
            if match.aki:
                self.table.setItem(i, 4, QTableWidgetItem(f"{match.aki:.2e}"))
            else:
                self.table.setItem(i, 4, QTableWidgetItem("—"))
            
            # Relative Intensity
            if match.relative_intensity:
                self.table.setItem(i, 5, QTableWidgetItem(f"{match.relative_intensity:.1f}"))
            else:
                self.table.setItem(i, 5, QTableWidgetItem("—"))
            
            # Score
            if match.score:
                self.table.setItem(i, 6, QTableWidgetItem(f"{match.score:.2e}"))
            else:
                self.table.setItem(i, 6, QTableWidgetItem("—"))
    
    def _on_save_clicked(self):
        """Save matching results to file."""
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
