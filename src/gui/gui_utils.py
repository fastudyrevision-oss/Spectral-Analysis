# -*- coding: utf-8 -*-
"""
GUI Utilities - Common components for PyQt6 GUI

Provides worker threads, plot embedding, and utility functions for the GUI.
"""

import sys
import io
import logging
from pathlib import Path
from typing import Callable, Any

import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QDoubleSpinBox,
    QSlider, QFileDialog, QMessageBox, QProgressDialog, QPushButton, QComboBox,
    QPlainTextEdit
)
from PyQt6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from src import setup_logger
from src.gui.theme import (
    C_BG_BASE, C_BG_RAISED, C_BG_PANEL, C_BORDER_SUBTLE,
    C_ACCENT, C_ACCENT2, C_WARN, C_TEXT, C_TEXT2, C_TEXT_MUTED,
)

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
    """Matplotlib canvas with dark theme — consistent with the application palette."""

    def __init__(self, width: float = 5, height: float = 4, dpi: int = 100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111)

        super().__init__(self.fig)

        # Dark background — no white flash
        self.setStyleSheet(f"background-color: {C_BG_BASE};")
        self._apply_dark_style()

    def _apply_dark_style(self):
        """Apply dark theme to figure and current axes."""
        self.fig.patch.set_facecolor(C_BG_BASE)
        ax = self.axes
        ax.set_facecolor(C_BG_RAISED)
        ax.tick_params(colors=C_TEXT2, which="both", labelsize=8)
        ax.xaxis.label.set_color(C_TEXT2)
        ax.yaxis.label.set_color(C_TEXT2)
        ax.title.set_color(C_TEXT)
        for spine in ax.spines.values():
            spine.set_edgecolor(C_BORDER_SUBTLE)
            spine.set_linewidth(0.8)
        ax.grid(True, color=C_BORDER_SUBTLE, alpha=0.55, linewidth=0.5,
                linestyle="--")

    def plot_spectrum(self, wavelength, intensity,
                     title: str = "Spectrum", ylabel: str = "Intensity"):
        """Plot corrected spectrum with dark theme."""
        self.axes.clear()
        self.axes.plot(wavelength, intensity,
                       color=C_ACCENT, linewidth=0.9, alpha=0.95)
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel(ylabel)
        self.axes.set_title(title)
        self._apply_dark_style()
        self.fig.tight_layout(pad=1.2)
        self.draw()

    def plot_peaks(self, wavelength, intensity,
                   peak_wl, peak_int, title: str = "Detected Peaks"):
        """Plot spectrum with detected peaks, dark theme."""
        self.axes.clear()
        self.axes.plot(wavelength, intensity,
                       color=C_ACCENT, linewidth=0.9, alpha=0.9,
                       label="Spectrum")
        self.axes.scatter(peak_wl, peak_int,
                          color=C_WARN, s=32, marker="x", linewidths=1.4,
                          label=f"Peaks ({len(peak_wl)})", zorder=3)
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel("Intensity")
        self.axes.set_title(title)
        leg = self.axes.legend(loc="upper right", fontsize=8, framealpha=0.6)
        leg.get_frame().set_facecolor(C_BG_RAISED)
        leg.get_frame().set_edgecolor(C_BORDER_SUBTLE)
        for txt in leg.get_texts():
            txt.set_color(C_TEXT2)
        self._apply_dark_style()
        self.fig.tight_layout(pad=1.2)
        self.draw()

    def clear(self):
        """Clear plot and restore dark style."""
        self.axes.clear()
        self._apply_dark_style()
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
        self.path_label.setStyleSheet(
            f"color: {C_TEXT_MUTED}; font-style: italic;"
        )
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
            self.path_label.setStyleSheet(
                f"color: {C_ACCENT2}; font-style: normal; font-weight: 600;"
            )
    
    def get_filepath(self) -> Path:
        """Get selected file path."""
        return self.filepath
    
    def set_filepath(self, filepath: Path):
        """Set file path."""
        if filepath and filepath.exists():
            self.filepath = filepath
            self.path_label.setText(str(filepath.name))
            self.path_label.setStyleSheet(
                f"color: {C_ACCENT2}; font-style: normal; font-weight: 600;"
            )


def show_error(title: str, message: str):
    """Show error dialog."""
    QMessageBox.critical(None, title, message)


def show_info(title: str, message: str):
    """Show info dialog."""
    QMessageBox.information(None, title, message)


def show_warning(title: str, message: str):
    """Show warning dialog."""
    QMessageBox.warning(None, title, message)


# ==========================================
# FILE HISTORY & NOTES COMPONENTS
# ==========================================

class FileHistory:
    """Manages file history and recent files list."""
    
    def __init__(self, max_items: int = 10):
        """
        Initialize file history.
        
        Parameters
        ----------
        max_items : int
            Maximum number of recent files to keep
        """
        self.max_items = max_items
        self.history = []
    
    def add_file(self, filepath: str):
        """Add file to history."""
        if filepath in self.history:
            self.history.remove(filepath)
        self.history.insert(0, filepath)
        if len(self.history) > self.max_items:
            self.history.pop()
    
    def get_recent(self) -> list:
        """Get recent files list."""
        return self.history.copy()
    
    def clear(self):
        """Clear history."""
        self.history.clear()


class NotesPanel(QWidget):
    """
    Notes/status panel — shows live application log output.

    A Qt-safe logging handler (QtLogHandler) is attached to the root logger
    during __init__ so that every logger.info/warning/error call across all
    modules automatically appears here in real time.
    """

    def __init__(self, max_lines: int = 200):
        super().__init__()
        self.max_lines = max_lines
        self.notes = []

        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        # Header row
        header_row = QHBoxLayout()
        title = QLabel("Application Log")
        title_font = title.font()
        title_font.setBold(True)
        title_font.setPointSize(9)
        title.setFont(title_font)
        header_row.addWidget(title)
        header_row.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setMaximumWidth(70)
        clear_btn.clicked.connect(self.clear)
        header_row.addWidget(clear_btn)

        copy_btn = QPushButton("Copy All")
        copy_btn.setMaximumWidth(80)
        copy_btn.clicked.connect(self._on_copy)
        header_row.addWidget(copy_btn)

        layout.addLayout(header_row)

        self.text_display = QPlainTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setMaximumHeight(150)
        layout.addWidget(self.text_display)

        self.setLayout(layout)

        # Attach a Qt-safe log handler to the root logger.
        # The handler emits a signal so widget updates always happen on the
        # GUI thread, even when log calls come from worker threads.
        self._log_handler = _QtLogHandler()
        self._log_handler.log_record.connect(self._append_log)
        self._log_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                              datefmt="%H:%M:%S"))
        logging.getLogger().addHandler(self._log_handler)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_note(self, note: str, note_type: str = "INFO"):
        """Append a hand-crafted note (legacy callers keep working)."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        icons = {'INFO': 'ℹ', 'SUCCESS': '✔', 'WARNING': '⚠', 'ERROR': '✘'}
        icon = icons.get(note_type, 'ℹ')
        self._append_log(f"[{timestamp}] {icon} {note}", note_type)

    @pyqtSlot(str, str)
    def _append_log(self, message: str, note_type: str):
        """Append one line to the display (always called on the GUI thread)."""
        self.notes.append(message)
        if len(self.notes) > self.max_lines:
            self.notes.pop(0)
        self.text_display.setPlainText('\n'.join(self.notes))
        self.text_display.verticalScrollBar().setValue(
            self.text_display.verticalScrollBar().maximum())

    def clear(self):
        self.notes.clear()
        self.text_display.clear()

    def _on_copy(self):
        from PyQt6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(self.text_display.toPlainText())


from PyQt6.QtCore import QObject as _QObject


class _LogBridge(_QObject):
    """QObject bridge that carries the log signal on the GUI thread."""
    log_record = pyqtSignal(str, str)


class _QtLogHandler(logging.Handler):
    """
    Logging handler that forwards formatted log records to a Qt signal,
    ensuring GUI updates happen on the main thread even from worker threads.
    """
    def __init__(self):
        logging.Handler.__init__(self)
        self._bridge = _LogBridge()

    @property
    def log_record(self):
        return self._bridge.log_record

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            note_type = {
                logging.DEBUG:    "INFO",
                logging.INFO:     "INFO",
                logging.WARNING:  "WARNING",
                logging.ERROR:    "ERROR",
                logging.CRITICAL: "ERROR",
            }.get(record.levelno, "INFO")
            self._bridge.log_record.emit(msg, note_type)
        except Exception:
            self.handleError(record)


class FileSelectorWithHistory(QWidget):
    """
    Enhanced file selector with recent files dropdown.
    
    Combines file selection with quick access to recent files.
    """
    
    def __init__(self, label: str, file_filter: str = "CSV Files (*.csv)", 
                 history: FileHistory = None):
        """
        Initialize file selector with history.
        
        Parameters
        ----------
        label : str
            Widget label
        file_filter : str
            File type filter for dialog
        history : FileHistory
            File history object (optional)
        """
        super().__init__()
        self.label_text = label
        self.file_filter = file_filter
        self.filepath = None
        self.history = history or FileHistory()
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # Top row: Label and file path
        top_layout = QHBoxLayout()
        
        label_widget = QLabel(label)
        label_widget.setMinimumWidth(120)
        top_layout.addWidget(label_widget)
        
        # File path display (clickable)
        self.path_label = QLabel("(No file selected)")
        self.path_label.setStyleSheet(
            "color: gray; font-style: italic; padding: 5px; "
            "border: 1px solid #ddd; border-radius: 3px; background-color: #f9f9f9;"
        )
        self.path_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.path_label.mousePressEvent = self._open_file_dialog
        top_layout.addWidget(self.path_label, stretch=1)
        
        # Browse button
        browse_btn = QPushButton("Browse...")
        browse_btn.setMaximumWidth(100)
        browse_btn.clicked.connect(self._open_file_dialog)
        top_layout.addWidget(browse_btn)
        
        layout.addLayout(top_layout)
        
        # Recent files row
        if self.history.get_recent():
            recent_layout = QHBoxLayout()
            recent_label = QLabel("Recent:")
            recent_label.setMinimumWidth(120)
            recent_label.setStyleSheet("color: #666; font-size: 9pt;")
            recent_layout.addWidget(recent_label)
            
            self.recent_combo = QComboBox()
            self.recent_combo.setMaximumWidth(300)
            self.recent_combo.addItems(self.history.get_recent())
            self.recent_combo.currentTextChanged.connect(self._on_recent_selected)
            recent_layout.addWidget(self.recent_combo)
            recent_layout.addStretch()
            
            layout.addLayout(recent_layout)
        
        self.setLayout(layout)
    
    def _open_file_dialog(self, event=None):
        """Open file dialog when clicked."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, 
            f"Select {self.label_text}",
            str(Path.home()),
            self.file_filter
        )
        
        if filepath:
            self.set_filepath(Path(filepath))
    
    def _on_recent_selected(self, filepath_str: str):
        """Handle selection from recent files."""
        if filepath_str:
            self.set_filepath(Path(filepath_str))
    
    def set_filepath(self, filepath: Path):
        """Set file path and update history."""
        self.filepath = filepath
        self.path_label.setText(str(self.filepath.name))
        self.path_label.setStyleSheet(
            "color: green; font-style: normal; padding: 5px; "
            "border: 2px solid #4CAF50; border-radius: 3px; background-color: #f0f8f0; font-weight: bold;"
        )
        self.history.add_file(str(filepath))
    
    def get_filepath(self) -> Path:
        """Get selected file path."""
        return self.filepath
