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
    QFileDialog, QSpinBox, QSplitter, QProgressBar, QScrollArea
)
from PyQt6.QtGui import QFont, QColor

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from src import setup_logger
from src.config import STEP5_PARAMS
from src.core.step5_validation import ValidationAnalyzer
from src.io.file_reader import CSVReader
from src.gui.gui_utils import (
    FileSelector, WorkerThread,
    show_error, show_info
)
from src.gui.charts import ChartEngine
from src.gui.export_engine import export_step5_csv, export_step5_png, generate_pdf_report
from src.gui.theme import (
    primary_button_style, instruction_banner_style, step_title_font,
    summary_banner_style, mean_vc_label_style, progress_bar_style
)

logger = setup_logger(__name__)


class Step5Widget(QWidget):
    """
    UI widget for Step 5: Validation with Reference Spectra.
    
    Allows users to:
    - Load processed and reference spectra
    - Specify target wavelengths for validation
    - Calculate validation coefficients
    - View correlation results with colour-coded quality badges
    - View VC histogram chart
    - Export results as CSV, PNG, or PDF
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
        
        # Create the VC histogram figure, canvas, and toolbar
        self.vc_fig = Figure(figsize=(8, 3), dpi=100)
        self.vc_canvas = FigureCanvasQTAgg(self.vc_fig)
        self.vc_canvas.setMinimumHeight(180)
        self.vc_canvas.setMinimumWidth(280)
        self.vc_toolbar = NavigationToolbar2QT(self.vc_canvas)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(0)

        # ── Controls pane (scrollable) ────────────────────────────────────
        controls_container = QWidget()
        controls_layout = self._create_controls()
        controls_container.setLayout(controls_layout)

        controls_scroll = QScrollArea()
        controls_scroll.setWidget(controls_container)
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        controls_scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        # ── Results table pane ────────────────────────────────────────────
        self.results_table = self._create_results_table()

        # ── Chart pane ────────────────────────────────────────────────────
        chart_widget = QWidget()
        chart_layout = QVBoxLayout()
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.setSpacing(2)
        chart_layout.addWidget(self.vc_canvas)
        chart_layout.addWidget(self.vc_toolbar)
        chart_widget.setLayout(chart_layout)

        # ── 3-pane vertical splitter: controls | table | chart ────────────
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(controls_scroll)
        splitter.addWidget(self.results_table)
        splitter.addWidget(chart_widget)
        # ~220px controls, ~360px table, ~200px chart (out of ~780px total)
        splitter.setSizes([220, 360, 200])
        splitter.setStretchFactor(0, 0)   # controls: stay compact
        splitter.setStretchFactor(1, 3)   # table:    grows most
        splitter.setStretchFactor(2, 1)   # chart:    grows some

        main_layout.addWidget(splitter, stretch=1)

        # ── Progress bar (hidden by default, sits below splitter) ─────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setStyleSheet(progress_bar_style())
        self.progress_bar.setMaximumHeight(6)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

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

        # Summary banner (after title, before instructions)
        self.summary_banner = QLabel("Run validation to see summary")
        self.summary_banner.setStyleSheet(summary_banner_style())
        self.summary_banner.setWordWrap(True)
        layout.addWidget(self.summary_banner)
        
        self.mean_vc_label = QLabel("—")
        layout.addWidget(self.mean_vc_label)

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
            "6. Results show the Validation Coefficient (VC) per line: colour-coded by quality tier.\n"
            "7. Use the export buttons to save results as CSV, PNG, or PDF."
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
        
        # Export buttons (disabled until data is available)
        self.export_csv_button = QPushButton("Export CSV")
        self.export_csv_button.setEnabled(False)
        self.export_csv_button.setToolTip("No data — run analysis first")
        self.export_csv_button.clicked.connect(self._on_export_csv_clicked)
        buttons_layout.addWidget(self.export_csv_button)
        
        self.export_png_button = QPushButton("Export PNG")
        self.export_png_button.setEnabled(False)
        self.export_png_button.setToolTip("No data — run analysis first")
        self.export_png_button.clicked.connect(self._on_export_png_clicked)
        buttons_layout.addWidget(self.export_png_button)
        
        self.export_pdf_button = QPushButton("Export PDF Report")
        self.export_pdf_button.setEnabled(False)
        self.export_pdf_button.setToolTip("No data — run analysis first")
        self.export_pdf_button.clicked.connect(self._on_export_pdf_clicked)
        buttons_layout.addWidget(self.export_pdf_button)
        
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
        
        # Show progress bar and disable export buttons
        self.progress_bar.show()
        self.export_csv_button.setEnabled(False)
        self.export_png_button.setEnabled(False)
        self.export_pdf_button.setEnabled(False)
        
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
        self.progress_bar.hide()
        show_error("Validation Error", error_message)
        self.info_label.setText(f"Error: {error_message}")

    def _on_validation_finished(self, _result: dict = None):
        """Handle validation completion."""
        if self.worker_thread is None:
            return

        result = self.worker_thread.result
        if result is None:
            self.validate_button.setEnabled(True)
            self.progress_bar.hide()
            show_error("Validation Failed", "Worker returned no result")
            return

        success, message = result
        self.validate_button.setEnabled(True)
        
        if not success:
            self.progress_bar.hide()
            show_error("Validation Failed", message)
            self.info_label.setText(f"Error: {message}")
            return
        
        # Update table
        self._populate_results_table()
        
        # Update chart and summary banner
        self._update_chart()
        self._update_summary_banner(self.validation_results)
        
        # Enable export buttons and hide progress bar
        self.export_csv_button.setEnabled(True)
        self.export_png_button.setEnabled(True)
        self.export_pdf_button.setEnabled(True)
        self.progress_bar.hide()
        
        self.save_button.setEnabled(True)
        
        # Calculate statistics for info label
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
        """Populate results table with colour-coded quality badges."""
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
            else:
                vc_str = f"{vc_val:.4f}"
            
            self.results_table.setItem(row, 1, QTableWidgetItem(vc_str))
            self.results_table.setItem(row, 2, QTableWidgetItem(r_data['Status']))
            
            # Use ChartEngine to classify the VC and colour the quality cell
            tier_label, bg_hex, fg_hex = ChartEngine.classify_vc(vc_val)
            quality_item = QTableWidgetItem(tier_label)
            quality_item.setBackground(QColor(bg_hex))
            quality_item.setForeground(QColor(fg_hex))
            self.results_table.setItem(row, 3, quality_item)
        
        logger.info("Results table populated")
    
    def _update_chart(self):
        """Clear and redraw the VC histogram on the existing canvas."""
        self.vc_fig.clear()
        ax = self.vc_fig.add_subplot(111)
        ChartEngine.render_vc_histogram(ax, self.validation_results)
        self.vc_canvas.draw()
        self.vc_toolbar.home()
    
    def _update_summary_banner(self, validation_results: pd.DataFrame):
        """Update the summary banner and mean VC label with current results.
        
        Parameters
        ----------
        validation_results : pd.DataFrame
            The validation results DataFrame with Validation_Coefficient column.
        """
        if validation_results is None or validation_results.empty:
            self.summary_banner.setText("No results to summarise.")
            self.mean_vc_label.setText("—")
            return
        
        # Extract non-null VC values
        valid_vc = validation_results['Validation_Coefficient'].dropna()
        total_count = len(validation_results)
        
        if valid_vc.empty:
            self.summary_banner.setText(
                f"Total wavelengths: {total_count} | All validations failed (no VC values)"
            )
            self.mean_vc_label.setText("—")
            return
        
        mean_vc = valid_vc.mean()
        
        # Count per tier
        tier_counts: dict[str, int] = {}
        for vc_val in validation_results['Validation_Coefficient']:
            tier_label, _, _ = ChartEngine.classify_vc(vc_val)
            tier_counts[tier_label] = tier_counts.get(tier_label, 0) + 1
        
        # Build summary text
        tier_parts = []
        for label in ["Excellent", "Good", "Moderate", "Weak", "Failed"]:
            count = tier_counts.get(label, 0)
            if count > 0:
                tier_parts.append(f"{label}: {count}")
        
        tier_str = " | ".join(tier_parts)
        banner_text = (
            f"Mean VC: {mean_vc:.4f}  |  Total wavelengths: {total_count}  |  {tier_str}"
        )
        self.summary_banner.setText(banner_text)
        
        # Update mean VC label with tier colour
        _, colour, _ = ChartEngine.classify_vc(mean_vc)
        self.mean_vc_label.setStyleSheet(mean_vc_label_style(colour))
        self.mean_vc_label.setText(f"{mean_vc:.4f}")
    
    def _on_export_csv_clicked(self):
        """Export validation results to CSV."""
        if self.validation_results is None:
            show_error("Error", "No data to export")
            return
        
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "validation_results",
            "CSV Files (*.csv)"
        )
        
        if not filepath:
            return
        
        try:
            export_step5_csv(self.validation_results, Path(filepath))
            show_info("Export Successful", f"CSV saved to:\n{filepath}")
            logger.info(f"CSV exported to {filepath}")
        except Exception as e:
            logger.error(f"CSV export failed: {e}")
            show_error("Export Failed", f"Failed to export CSV:\n{e}")
    
    def _on_export_png_clicked(self):
        """Export the VC histogram chart as PNG."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", "vc_histogram",
            "PNG Files (*.png)"
        )
        
        if not filepath:
            return
        
        try:
            export_step5_png(self.vc_fig, Path(filepath))
            show_info("Export Successful", f"PNG saved to:\n{filepath}")
            logger.info(f"PNG exported to {filepath}")
        except Exception as e:
            logger.error(f"PNG export failed: {e}")
            show_error("Export Failed", f"Failed to export PNG:\n{e}")
    
    def _on_export_pdf_clicked(self):
        """Generate and save a comprehensive PDF validation report."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Report", "LIBS_Validation_Report",
            "PDF Files (*.pdf)"
        )
        
        if not filepath:
            return
        
        # Gather parameters
        params = {
            'WINDOW': self.window_spinbox.value(),
            'MIN_POINTS': self.min_points_spinbox.value(),
            'VC_THRESHOLD': self.threshold_spinbox.value(),
        }
        
        # Get filenames from selectors
        processed_path = self.processed_selector.get_filepath()
        reference_path = self.reference_selector.get_filepath()
        processed_filename = Path(processed_path).name if processed_path else "Unknown"
        reference_filename = Path(reference_path).name if reference_path else "Unknown"
        
        target_wavelengths = getattr(self, 'target_wavelengths', [])
        
        try:
            generate_pdf_report(
                validation_results_df=self.validation_results,
                params=params,
                vc_fig=self.vc_fig,
                processed_filename=processed_filename,
                reference_filename=reference_filename,
                target_wavelengths=target_wavelengths,
                filepath=Path(filepath),
            )
            show_info("Export Successful", f"PDF report saved to:\n{filepath}")
            logger.info(f"PDF report exported to {filepath}")
        except ImportError:
            show_error(
                "Missing Dependency",
                "reportlab is not installed.\nRun: pip install reportlab"
            )
        except Exception as e:
            logger.error(f"PDF export failed: {e}")
            show_error("Export Failed", f"Failed to generate PDF report:\n{e}")
    
    def _on_save_clicked(self):
        """Save validation report (legacy CSV save)."""
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
