# -*- coding: utf-8 -*-
"""
GUI Utilities - Common components for PyQt6 GUI

Provides worker threads, plot embedding, and utility functions for the GUI.
"""

import sys
import os
import io
import logging
from pathlib import Path
from typing import Callable, Any

import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QDoubleSpinBox,
    QSlider, QFileDialog, QMessageBox, QProgressDialog, QPushButton, QComboBox,
    QPlainTextEdit, QMenu, QToolButton,
)
from PyQt6.QtGui import QFont, QAction
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as _NavigationToolbar2QT
from matplotlib.figure import Figure

from src import setup_logger
from src.gui.theme import (
    C_BG_BASE, C_BG_RAISED, C_BG_PANEL, C_BORDER_SUBTLE,
    C_ACCENT, C_ACCENT2, C_WARN, C_TEXT, C_TEXT2, C_TEXT_MUTED,
)

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# High-DPI save toolbar
# ---------------------------------------------------------------------------

class HighDpiToolbar(_NavigationToolbar2QT):
    """
    NavigationToolbar2QT subclass that saves PNG/raster at 300 DPI.

    The standard save dialog is used unchanged (all formats, default
    selection). For raster formats (PNG, JPG, TIFF …) the figure is
    re-drawn at 2× its screen size before saving so content is freshly
    rendered at high resolution — not upscaled. Antialiasing is forced
    on for the export. The on-screen figure is completely unaffected.
    Vector formats (SVG, PDF, EPS) are saved as-is.
    """

    EXPORT_DPI   = 300
    EXPORT_SCALE = 2.0

    def save_figure(self, *args):
        import os
        import matplotlib as mpl
        from PyQt6 import QtWidgets

        # ── Standard save dialog (unchanged from base class) ──────────────
        filetypes = self.canvas.get_supported_filetypes_grouped()
        sorted_filetypes = sorted(filetypes.items())
        default_filetype = self.canvas.get_default_filetype()

        startpath = os.path.expanduser(mpl.rcParams['savefig.directory'])
        start = os.path.join(startpath, self.canvas.get_default_filename())

        filters, selected_filter = [], None
        for name, exts in sorted_filetypes:
            exts_list = " ".join([f"*.{ext}" for ext in exts])
            filt = f"{name} ({exts_list})"
            if default_filetype in exts:
                selected_filter = filt
            filters.append(filt)

        fname, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.canvas.parent(), "Choose a filename to save to",
            start, ";;".join(filters), selected_filter)

        if not fname:
            return

        if startpath != "":
            mpl.rcParams['savefig.directory'] = os.path.dirname(fname)

        # ── Save with quality settings ────────────────────────────────────
        fig = self.canvas.figure
        orig_size = fig.get_size_inches().copy()
        orig_dpi  = fig.get_dpi()

        ext = os.path.splitext(fname)[1].lower().lstrip(".")
        is_raster = ext in ("png", "jpg", "jpeg", "tiff", "tif", "bmp")

        try:
            if is_raster:
                fig.set_size_inches(orig_size[0] * self.EXPORT_SCALE,
                                    orig_size[1] * self.EXPORT_SCALE,
                                    forward=False)
                with mpl.rc_context({
                    "lines.antialiased": True,
                    "patch.antialiased": True,
                    "text.antialiased":  True,
                    "path.simplify":     False,
                    "agg.path.chunksize": 0,
                }):
                    fig.savefig(fname, dpi=self.EXPORT_DPI,
                                bbox_inches="tight", pad_inches=0.15)
            else:
                fig.savefig(fname, bbox_inches="tight", pad_inches=0.15)

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error saving file", str(e),
                QtWidgets.QMessageBox.StandardButton.Ok,
                QtWidgets.QMessageBox.StandardButton.NoButton)
        finally:
            fig.set_size_inches(orig_size[0], orig_size[1], forward=False)
            fig.set_dpi(orig_dpi)
            self.canvas.draw_idle()


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
    """
    Manages recent files list with optional disk persistence.

    Files are grouped by a *role* string (e.g. 'peaks', 'spectra', 'nist')
    so each widget shows only its own relevant history.

    Storage: %APPDATA%/LIBS_Analysis/recent_files.json  (Windows)
             ~/.config/LIBS_Analysis/recent_files.json   (Linux / Mac)
    """

    _STORAGE_PATH: Path = None   # resolved once on first use

    def __init__(self, max_items: int = 15, role: str = "general"):
        """
        Parameters
        ----------
        max_items : int
            Maximum recent files to keep per role.
        role : str
            Logical category for this history (e.g. 'peaks', 'spectra').
            Keeps different widgets' histories separate.
        """
        self.max_items = max_items
        self.role      = role
        self._data: dict = {}   # role → [path, ...]
        self._load()

    # ── Persistence helpers ───────────────────────────────────────────────────

    @classmethod
    def _storage_path(cls) -> Path:
        if cls._STORAGE_PATH is None:
            if sys.platform == "win32":
                base = Path(os.environ.get("APPDATA", Path.home()))
            else:
                base = Path.home() / ".config"
            cls._STORAGE_PATH = base / "LIBS_Analysis" / "recent_files.json"
        return cls._STORAGE_PATH

    def _load(self):
        try:
            p = self._storage_path()
            if p.exists():
                import json
                self._data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            self._data = {}

    def _save(self):
        try:
            import json
            p = self._storage_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except Exception:
            pass   # never crash the UI over a history write failure

    # ── Public API ────────────────────────────────────────────────────────────

    def add_file(self, filepath: str):
        """Add a file path to this role's history and persist immediately."""
        if not filepath:
            return
        lst = self._data.setdefault(self.role, [])
        if filepath in lst:
            lst.remove(filepath)
        lst.insert(0, filepath)
        if len(lst) > self.max_items:
            lst.pop()
        self._data[self.role] = lst
        self._save()

    def get_recent(self) -> list:
        """Return recent files for this role (most-recent first, existing only)."""
        raw = self._data.get(self.role, [])
        # Filter out paths that no longer exist on disk
        return [p for p in raw if Path(p).exists()]

    def clear(self):
        """Clear history for this role and persist."""
        self._data[self.role] = []
        self._save()

    def clear_all_roles(self):
        """Wipe the entire history file."""
        self._data = {}
        self._save()




class RecentFilesButton(QToolButton):
    """
    A compact "🕐 Recent" drop-down button that shows the last N files
    for a given role.  When the user picks an entry the *file_selected*
    signal is emitted with the absolute path string.

    When ``show_add_all=True`` an "Add All Recent" action appears at the
    top of the menu — emits *all_selected* with the full list of paths.

    Designed to sit beside a QListWidget + Add/Remove/Clear row so the
    user can re-add previously used files in one click instead of
    navigating the file-system every time.

    Usage
    -----
    btn = RecentFilesButton(history)          # history is a FileHistory instance
    btn.file_selected.connect(my_callback)    # callback receives str path
    btn.all_selected.connect(my_all_callback) # callback receives list[str]
    btn.refresh()                             # call after history changes
    """

    file_selected = pyqtSignal(str)
    all_selected  = pyqtSignal(list)   # emits list[str] of all recent paths

    def __init__(self, history: "FileHistory", parent=None,
                 show_add_all: bool = False):
        super().__init__(parent)
        self._history     = history
        self._show_add_all = show_add_all
        self.setText("🕐 Recent ▾")
        self.setToolTip(
            "Pick a recently used file.\n"
            "Only files that still exist on disk are shown."
        )
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setFixedHeight(24)
        self.setStyleSheet(
            "QToolButton { font-size: 9pt; padding: 2px 8px; }"
            "QToolButton::menu-indicator { image: none; }"   # hide default arrow
        )
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self.refresh()

    def refresh(self):
        """Rebuild the dropdown from the current history."""
        self._menu.clear()
        recent = self._history.get_recent()
        if not recent:
            no_action = QAction("(no recent files)", self)
            no_action.setEnabled(False)
            self._menu.addAction(no_action)
            self.setEnabled(False)
            return

        self.setEnabled(True)

        # ── "Add All Recent" shortcut ─────────────────────────────────────
        if self._show_add_all and len(recent) > 1:
            add_all_action = QAction(f"➕  Add All Recent  ({len(recent)} files)", self)
            add_all_action.setToolTip(
                "Add every file in the recent list to the queue at once."
            )
            add_all_action.triggered.connect(
                lambda checked, r=list(recent): self.all_selected.emit(r)
            )
            self._menu.addAction(add_all_action)
            self._menu.addSeparator()

        for path_str in recent:
            p = Path(path_str)
            # Show filename as label, full path as tooltip
            action = QAction(p.name, self)
            action.setToolTip(path_str)
            action.setData(path_str)
            action.triggered.connect(
                lambda checked, ps=path_str: self.file_selected.emit(ps)
            )
            self._menu.addAction(action)

        self._menu.addSeparator()
        clear_action = QAction("Clear history", self)
        clear_action.triggered.connect(self._on_clear)
        self._menu.addAction(clear_action)

    def _on_clear(self):
        self._history.clear()
        self.refresh()


class NotesPanel(QWidget):
    """
    Collapsible application log panel.

    Starts collapsed — only the title bar is visible.  Clicking the title bar
    (or the ▲/▼ toggle button) expands / collapses the text area.

    A Qt-safe logging handler is attached to the root logger so every
    logger.info/warning/error call appears here in real time.
    """

    # Height of the text area when expanded (pixels)
    _EXPANDED_HEIGHT = 160

    def __init__(self, max_lines: int = 200):
        super().__init__()
        self.max_lines = max_lines
        self.notes: list[str] = []
        self._expanded = False          # start collapsed

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Title / toggle bar ────────────────────────────────────────────
        self._header = QWidget()
        self._header.setFixedHeight(26)
        self._header.setStyleSheet(
            f"background: {C_BG_RAISED}; border-top: 1px solid {C_BORDER_SUBTLE};"
        )
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)

        header_row = QHBoxLayout(self._header)
        header_row.setContentsMargins(8, 0, 6, 0)
        header_row.setSpacing(6)

        self._toggle_icon = QLabel("▶")
        self._toggle_icon.setStyleSheet(f"color: {C_TEXT_MUTED}; font-size: 8pt;")
        header_row.addWidget(self._toggle_icon)

        title_lbl = QLabel("Application Log")
        title_font = title_lbl.font()
        title_font.setBold(True)
        title_font.setPointSize(9)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet(f"color: {C_TEXT};")
        header_row.addWidget(title_lbl)

        # Live "last message" preview shown while collapsed
        self._preview_lbl = QLabel("")
        self._preview_lbl.setStyleSheet(f"color: {C_TEXT_MUTED}; font-size: 8pt;")
        self._preview_lbl.setMaximumWidth(600)
        from PyQt6.QtCore import Qt as _Qt
        self._preview_lbl.setAlignment(_Qt.AlignmentFlag.AlignLeft | _Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self._preview_lbl, stretch=1)

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(18)
        clear_btn.setMaximumWidth(55)
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {C_BORDER_SUBTLE}; "
            f"border-radius: 3px; color: {C_TEXT_MUTED}; font-size: 8pt; padding: 0 6px; }}"
            f"QPushButton:hover {{ border-color: {C_ACCENT}; color: {C_ACCENT}; }}"
        )
        clear_btn.clicked.connect(self.clear)
        header_row.addWidget(clear_btn)

        copy_btn = QPushButton("Copy")
        copy_btn.setFixedHeight(18)
        copy_btn.setMaximumWidth(55)
        copy_btn.setStyleSheet(clear_btn.styleSheet())
        copy_btn.clicked.connect(self._on_copy)
        header_row.addWidget(copy_btn)

        outer.addWidget(self._header)

        # ── Log text area (hidden when collapsed) ─────────────────────────
        self._body = QWidget()
        self._body.setMaximumHeight(0)       # collapsed by default
        self._body.setVisible(False)

        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(4, 2, 4, 4)
        body_layout.setSpacing(0)

        self.text_display = QPlainTextEdit()
        self.text_display.setReadOnly(True)
        body_layout.addWidget(self.text_display)

        outer.addWidget(self._body)

        # Make the header clickable
        self._header.mousePressEvent = self._on_header_clicked

        # ── Logging handler ───────────────────────────────────────────────
        self._log_handler = _QtLogHandler()
        self._log_handler.log_record.connect(self._append_log)
        self._log_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                              datefmt="%H:%M:%S"))
        logging.getLogger().addHandler(self._log_handler)

    # ------------------------------------------------------------------
    # Toggle
    # ------------------------------------------------------------------

    def _on_header_clicked(self, _event=None):
        self._expanded = not self._expanded
        if self._expanded:
            self._toggle_icon.setText("▼")
            self._preview_lbl.setText("")
            self._body.setVisible(True)
            self._body.setMaximumHeight(self._EXPANDED_HEIGHT)
            self.setMaximumHeight(26 + self._EXPANDED_HEIGHT)
        else:
            self._toggle_icon.setText("▶")
            self._body.setMaximumHeight(0)
            self._body.setVisible(False)
            self.setMaximumHeight(26)
            # Show last log line as preview
            if self.notes:
                self._preview_lbl.setText(self.notes[-1][:120])

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
        # Keep preview label current when collapsed
        if not self._expanded:
            self._preview_lbl.setText(message[:120])

    def clear(self):
        self.notes.clear()
        self.text_display.clear()
        self._preview_lbl.setText("")

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
