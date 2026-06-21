# -*- coding: utf-8 -*-
"""
GUI Utilities - Common components for PyQt6 GUI

Provides worker threads, plot embedding, and utility functions for the GUI.
"""

import sys
import io
from pathlib import Path
from typing import Callable, Any

import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QDoubleSpinBox,
    QSlider, QFileDialog, QMessageBox, QProgressDialog
)
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

from src import setup_logger

logger = setup_logger(__name__)


class WorkerThread(QThread):
    """
    Worker thread for long-running operations.
    
    Emits signals to keep UI responsive during processing.
    """
    
    # Signals
    started = pyqtSignal()
    progress = pyqtSignal(str)  # Progress message
    finished = pyqtSignal(dict)  # Results dict
    error = pyqtSignal(str)  # Error message
    
    def __init__(self, func: Callable, *args, **kwargs):
        """
        Initialize worker thread.
        
        Parameters
        ----------
        func : Callable
            Function to execute in thread
        *args, **kwargs
            Arguments to pass to function
        """
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.result = None
        
    def run(self):
        """Execute function in thread."""
        try:
            self.started.emit()
            self.progress.emit("Processing...")
            
            # Execute function with args/kwargs
            self.result = self.func(*self.args, **self.kwargs)
            
            # Emit result
            if isinstance(self.result, dict):
                self.finished.emit(self.result)
            else:
                self.finished.emit({"result": self.result})
                
        except Exception as e:
            logger.error(f"Worker thread error: {e}", exc_info=True)
            self.error.emit(str(e))


class ParameterControl(QWidget):
    """
    Reusable parameter control widget (slider + spinbox).
    
    Allows user to adjust numeric parameters with visual feedback.
    """
    
    def __init__(self, name: str, min_val: float, max_val: float, 
                 initial: float, step: float = 1.0, decimals: int = 2):
        """
        Initialize parameter control.
        
        Parameters
        ----------
        name : str
            Parameter name
        min_val : float
            Minimum value
        max_val : float
            Maximum value
        initial : float
            Initial value
        step : float
            Step size
        decimals : int
            Decimal places to display
        """
        super().__init__()
        self.name = name
        self.min_val = min_val
        self.max_val = max_val
        self.decimals = decimals
        self.step = step
        
        layout = QHBoxLayout()
        
        # Label
        label = QLabel(f"{name}:")
        label.setMinimumWidth(120)
        layout.addWidget(label)
        
        # Spinbox (for precise input)
        self.spinbox = QDoubleSpinBox()
        self.spinbox.setMinimum(min_val)
        self.spinbox.setMaximum(max_val)
        self.spinbox.setValue(initial)
        self.spinbox.setSingleStep(step)
        self.spinbox.setDecimals(decimals)
        self.spinbox.setMaximumWidth(100)
        layout.addWidget(self.spinbox)
        
        # Slider (for quick adjustment)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        # Convert float range to integer range for slider (0-1000 steps)
        self.slider_steps = 1000
        self.slider.setMinimum(0)
        self.slider.setMaximum(self.slider_steps)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.setTickInterval(self.slider_steps // 10)
        
        # Set slider to initial position
        normalized = (initial - min_val) / (max_val - min_val) if max_val != min_val else 0
        self.slider.setValue(int(normalized * self.slider_steps))
        layout.addWidget(self.slider, stretch=1)
        
        # Connect signals
        self.spinbox.valueChanged.connect(self._on_spinbox_changed)
        self.slider.sliderMoved.connect(self._on_slider_changed)
        
        self.setLayout(layout)
        
    def _on_spinbox_changed(self, value):
        """Update slider when spinbox changes."""
        if abs(self.max_val - self.min_val) > 0:
            normalized = (value - self.min_val) / (self.max_val - self.min_val)
            self.slider.blockSignals(True)
            self.slider.setValue(int(normalized * self.slider_steps))
            self.slider.blockSignals(False)
    
    def _on_slider_changed(self, position):
        """Update spinbox when slider changes."""
        normalized = position / self.slider_steps
        value = self.min_val + normalized * (self.max_val - self.min_val)
        self.spinbox.blockSignals(True)
        self.spinbox.setValue(value)
        self.spinbox.blockSignals(False)
    
    def value(self) -> float:
        """Get current parameter value."""
        return self.spinbox.value()
    
    def set_value(self, value: float):
        """Set parameter value."""
        self.spinbox.setValue(value)


class MatplotlibCanvas(FigureCanvas):
    """
    Matplotlib canvas for embedding plots in PyQt6.
    
    Allows display of publication-quality plots within GUI.
    """
    
    def __init__(self, width: float = 5, height: float = 4, dpi: int = 100):
        """
        Initialize canvas.
        
        Parameters
        ----------
        width : float
            Figure width in inches
        height : float
            Figure height in inches
        dpi : int
            Dots per inch (screen display)
        """
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111)
        
        super().__init__(self.fig)
        self.setStyleSheet("background-color: white")
    
    def plot_spectrum(self, wavelength: np.ndarray, intensity: np.ndarray, 
                      title: str = "Spectrum", ylabel: str = "Intensity"):
        """
        Plot spectrum.
        
        Parameters
        ----------
        wavelength : np.ndarray
            Wavelength array (nm)
        intensity : np.ndarray
            Intensity array
        title : str
            Plot title
        ylabel : str
            Y-axis label
        """
        self.axes.clear()
        self.axes.plot(wavelength, intensity, 'b-', linewidth=0.8)
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel(ylabel)
        self.axes.set_title(title)
        self.axes.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.draw()
    
    def plot_peaks(self, wavelength: np.ndarray, intensity: np.ndarray, 
                   peak_wl: np.ndarray, peak_int: np.ndarray, title: str = "Detected Peaks"):
        """
        Plot spectrum with detected peaks.
        
        Parameters
        ----------
        wavelength : np.ndarray
            Wavelength array (nm)
        intensity : np.ndarray
            Intensity array
        peak_wl : np.ndarray
            Peak wavelengths (nm)
        peak_int : np.ndarray
            Peak intensities
        title : str
            Plot title
        """
        self.axes.clear()
        self.axes.plot(wavelength, intensity, 'b-', linewidth=0.8, label="Spectrum")
        self.axes.scatter(peak_wl, peak_int, color='red', s=30, marker='x', 
                         label=f"Peaks ({len(peak_wl)})")
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel("Intensity")
        self.axes.set_title(title)
        self.axes.legend()
        self.axes.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.draw()
    
    def clear(self):
        """Clear all plots."""
        self.axes.clear()
        self.draw()


class FileSelector(QWidget):
    """
    File selection widget with label.
    
    Allows user to select input/output files.
    """
    
    def __init__(self, label: str, file_filter: str = "CSV Files (*.csv)"):
        """
        Initialize file selector.
        
        Parameters
        ----------
        label : str
            Widget label
        file_filter : str
            File type filter for dialog
        """
        super().__init__()
        self.file_filter = file_filter
        self.filepath = None
        
        layout = QHBoxLayout()
        
        # Label
        label_widget = QLabel(label)
        label_widget.setMinimumWidth(120)
        layout.addWidget(label_widget)
        
        # File path display
        self.path_label = QLabel("(No file selected)")
        self.path_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.path_label, stretch=1)
        
        self.setLayout(layout)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
    def mousePressEvent(self, event):
        """Open file dialog when clicked."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, 
            "Select File",
            str(Path.home()),
            self.file_filter
        )
        
        if filepath:
            self.filepath = Path(filepath)
            self.path_label.setText(str(self.filepath.name))
            self.path_label.setStyleSheet("color: black; font-style: normal;")
    
    def get_filepath(self) -> Path:
        """Get selected file path."""
        return self.filepath
    
    def set_filepath(self, filepath: Path):
        """Set file path."""
        if filepath and filepath.exists():
            self.filepath = filepath
            self.path_label.setText(str(filepath.name))
            self.path_label.setStyleSheet("color: black; font-style: normal;")


def show_error(title: str, message: str):
    """Show error dialog."""
    QMessageBox.critical(None, title, message)


def show_info(title: str, message: str):
    """Show info dialog."""
    QMessageBox.information(None, title, message)


def show_warning(title: str, message: str):
    """Show warning dialog."""
    QMessageBox.warning(None, title, message)
