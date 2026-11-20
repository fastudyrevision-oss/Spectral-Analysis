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
from typing import Callable, Any, Optional, List

import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QTimer, QRectF
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QDoubleSpinBox,
    QSlider, QFileDialog, QMessageBox, QProgressDialog, QPushButton, QComboBox,
    QPlainTextEdit, QMenu, QToolButton, QStyledItemDelegate, QStyle,
    QAbstractItemView, QApplication,
)
from PyQt6.QtGui import QFont, QAction, QIcon, QPixmap, QPalette, QColor, QPainter, QPen, QConicalGradient
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as _NavigationToolbar2QT
from matplotlib.figure import Figure

from src import setup_logger
from src.gui.theme import (
    C_BG_BASE, C_BG_RAISED, C_BG_PANEL, C_BORDER_SUBTLE,
    C_ACCENT, C_ACCENT2, C_WARN, C_TEXT, C_TEXT2, C_TEXT_MUTED,
    L_BG_RAISED, L_BG_INPUT, L_BORDER_SUBTLE, L_BORDER, L_TEXT, L_ACCENT,
    L_ROW_HOVER,
)

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# Asset & Icon helpers
# ---------------------------------------------------------------------------

def get_asset_path(filename: str = "icon.png") -> Path:
    """
    Locate an asset file in both development and PyInstaller frozen modes.
    """
    candidates = []

    # 1. PyInstaller extraction directory (_MEIPASS)
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "assets" / filename)
        candidates.append(Path(sys._MEIPASS) / "src" / "assets" / filename)
        candidates.append(Path(sys._MEIPASS) / filename)

    # 2. Executable directory (for one-folder PyInstaller)
    exe_dir = Path(sys.executable).parent
    candidates.append(exe_dir / "_internal" / "assets" / filename)
    candidates.append(exe_dir / "_internal" / "src" / "assets" / filename)
    candidates.append(exe_dir / "assets" / filename)
    candidates.append(exe_dir / filename)

    # 3. Development tree (relative to source file)
    current_file = Path(__file__).resolve()
    # src/gui/gui_utils.py -> src/assets/filename
    candidates.append(current_file.parent.parent / "assets" / filename)
    # src/gui/gui_utils.py -> project_root/assets/filename
    candidates.append(current_file.parent.parent.parent / "assets" / filename)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Default fallback
    return current_file.parent.parent / "assets" / filename


def get_app_icon() -> QIcon:
    """Return the application QIcon loaded from bundled assets."""
    ico_path = get_asset_path("icon.ico")
    png_path = get_asset_path("icon.png")

    icon = QIcon()
    if ico_path.exists():
        icon = QIcon(str(ico_path))
    
    if png_path.exists():
        pix = QPixmap(str(png_path))
        if not pix.isNull():
            for sz in [16, 24, 32, 48, 64, 128, 256]:
                icon.addPixmap(pix.scaled(
                    sz, sz,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))

    return icon


def show_about_dialog(parent: QWidget = None) -> None:
    """Display the modern About dialog with app logo and info."""
    from PyQt6.QtWidgets import QDialog, QFrame

    dialog = QDialog(parent)
    dialog.setWindowTitle("About LIBS Spectral Analysis")
    dialog.setFixedSize(500, 380)
    dialog.setWindowIcon(get_app_icon())

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(24, 24, 24, 20)
    layout.setSpacing(14)

    # Header with logo
    header_layout = QHBoxLayout()
    header_layout.setSpacing(16)

    logo_path = get_asset_path("logo.png")
    if logo_path.exists():
        logo_lbl = QLabel()
        pixmap = QPixmap(str(logo_path)).scaled(
            75, 75, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        logo_lbl.setPixmap(pixmap)
        header_layout.addWidget(logo_lbl)

    title_layout = QVBoxLayout()
    title_layout.setSpacing(4)
    title_lbl = QLabel("LIBS Spectral Analysis")
    title_lbl.setStyleSheet("font-size: 14pt; font-weight: bold; color: #3FA9F5;")
    version_lbl = QLabel("Version 1.1.1  •  Laser-Induced Breakdown Spectroscopy")
    version_lbl.setStyleSheet("font-size: 9pt; color: #8F9CAE;")
    publisher_lbl = QLabel("JFD Tech  |  https://www.jfdtech.info")
    publisher_lbl.setStyleSheet("font-size: 8.5pt; color: #5C6577;")

    title_layout.addWidget(title_lbl)
    title_layout.addWidget(version_lbl)
    title_layout.addWidget(publisher_lbl)
    header_layout.addLayout(title_layout)
    header_layout.addStretch()

    layout.addLayout(header_layout)

    # Separator
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: #2D3344;")
    layout.addWidget(line)

    # Description
    desc_lbl = QLabel(
        "Complete 6-step desktop analytical pipeline for LIBS spectra:\n\n"
        "• ① Baseline Correction (Savitzky-Golay & Asymmetric Least Squares)\n"
        "• ② Peak Detection (Prominence, Wavelengths, SNR)\n"
        "• ③ NIST Atomic Spectra Database Matching\n"
        "• ④ Elemental Preferences & Winner Assignment\n"
        "• ⑤ Reference Spectra Validation & Correlation\n"
        "• ⑥ Model Performance Metrics & Multi-Format Reporting"
    )
    desc_lbl.setWordWrap(True)
    desc_lbl.setStyleSheet("font-size: 9pt; line-height: 1.4; color: #C2C9D6;")
    layout.addWidget(desc_lbl)

    layout.addStretch()

    # Close button
    btn_layout = QHBoxLayout()
    btn_layout.addStretch()
    close_btn = QPushButton("Close")
    close_btn.setFixedWidth(90)
    close_btn.setStyleSheet(
        "QPushButton { background: #1E2333; border: 1px solid #3FA9F5; border-radius: 4px; "
        "color: #3FA9F5; padding: 6px; font-weight: bold; }"
        "QPushButton:hover { background: #3FA9F5; color: #0E121E; }"
    )
    close_btn.clicked.connect(dialog.accept)
    btn_layout.addWidget(close_btn)
    layout.addLayout(btn_layout)

    dialog.exec()

# ---------------------------------------------------------------------------
# Toolbar theme helper
# ---------------------------------------------------------------------------

def style_toolbar(toolbar: "_NavigationToolbar2QT") -> None:
    """Apply a theme-aware style to a matplotlib NavigationToolbar2QT instance.

    Matplotlib's NavigationToolbar2QT renders its icons by colorizing SVG/PNG
    images using the QPalette ButtonText role.  Setting only a stylesheet
    color is not enough — we must also set the palette so Qt uses a dark ink
    color for the icons.  Without this the icons are nearly invisible in light
    mode (light-grey on light-grey).
    """
    from src.gui.theme import is_dark

    if is_dark():
        # Dark theme — keep existing dark look
        bg_hex      = C_BG_RAISED
        icon_hex    = C_TEXT2        # mid-grey — works on dark bg
        hover_hex   = "rgba(63,169,245,0.15)"
        pressed_hex = "rgba(63,169,245,0.30)"
        checked_hex = "rgba(63,169,245,0.25)"
        border_hex  = C_BORDER_SUBTLE
        accent_hex  = C_ACCENT
    else:
        
        # Light theme — use a noticeably grey background and very dark icons
        bg_hex      = "#12141A"
        icon_hex    = "#E6EAF2"
        hover_hex   = "#20242D"
        pressed_hex = "#2A303B"
        checked_hex = "#303846"
        border_hex  = "#363C48"
        accent_hex  = L_ACCENT

    # ── Stylesheet — background, hover, pressed, checked ──────────────────
    toolbar.setStyleSheet(
        f"QToolBar, QWidget {{"
        f"  background-color: {bg_hex};"
        f"  border-top: 1px solid {border_hex};"
        f"}}"
        f"QToolButton {{"
        f"  background-color: transparent;"
        f"  border: 1px solid transparent;"
        f"  border-radius: 4px;"
        f"  padding: 3px;"
        f"  margin: 1px;"
        f"}}"
        f"QToolButton:hover {{"
        f"  background-color: {hover_hex};"
        f"  border-color: {border_hex};"
        f"}}"
        f"QToolButton:pressed {{"
        f"  background-color: {pressed_hex};"
        f"  border-color: {accent_hex};"
        f"}}"
        f"QToolButton:checked {{"
        f"  background-color: {checked_hex};"
        f"  border-color: {accent_hex};"
        f"}}"
    )

    # ── Palette — controls how Qt colorizes the actual icon pixels ─────────
    pal = toolbar.palette()
    icon_color = QColor(icon_hex)
    bg_color   = QColor(bg_hex)
    pal.setColor(QPalette.ColorRole.ButtonText,   icon_color)
    pal.setColor(QPalette.ColorRole.WindowText,   icon_color)
    pal.setColor(QPalette.ColorRole.Text,         icon_color)
    pal.setColor(QPalette.ColorRole.Button,       bg_color)
    pal.setColor(QPalette.ColorRole.Window,       bg_color)
    toolbar.setPalette(pal)
    toolbar.setAutoFillBackground(True)

    # Force all child QToolButtons to inherit the same palette so their
    # icons also pick up the dark ink color
    for btn in toolbar.findChildren(QToolButton):
        btn.setPalette(pal)
        btn.setAutoFillBackground(False)


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

    def __init__(self, canvas, parent=None):
        super().__init__(canvas, parent)
        style_toolbar(self)

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
                    "lines.antialiased":  True,
                    "patch.antialiased":  True,
                    "text.antialiased":   True,
                    "path.simplify":      False,
                    "agg.path.chunksize": 0,
                    # Larger labels for saved images (was: label=13, tick=11, title=14, legend=10)
                    "axes.labelsize":     15,
                    "xtick.labelsize":    13,
                    "ytick.labelsize":    13,
                    "axes.titlesize":     16,
                    "legend.fontsize":    12,
                }):
                    fig.savefig(fname, dpi=self.EXPORT_DPI,
                                bbox_inches="tight", pad_inches=0.2)
            else:
                # Vector formats: boost label sizes for readability too
                with mpl.rc_context({
                    # Larger labels for saved images (was: label=13, tick=11, title=14, legend=10)
                    "axes.labelsize":  15,
                    "xtick.labelsize": 13,
                    "ytick.labelsize": 13,
                    "axes.titlesize":  16,
                    "legend.fontsize": 12,
                }):
                    fig.savefig(fname, bbox_inches="tight", pad_inches=0.2)

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error saving file", str(e),
                QtWidgets.QMessageBox.StandardButton.Ok,
                QtWidgets.QMessageBox.StandardButton.NoButton)
        finally:
            fig.set_size_inches(orig_size[0], orig_size[1], forward=False)
            fig.set_dpi(orig_dpi)
            self.canvas.draw_idle()


# ---------------------------------------------------------------------------
# Theme-switch overlay
# ---------------------------------------------------------------------------

class ThemeSwitchOverlay(QWidget):
    """Full-window semi-transparent overlay shown while the theme is switching.

    Displays a spinning arc progress indicator and a short status message so
    the user gets immediate feedback that the UI is responding rather than
    frozen.  Call :meth:`show_over` to attach it to a parent window, and
    :meth:`finish` to dismiss it once the switch is complete.

    Usage (inside the main window)::

        self._theme_overlay = ThemeSwitchOverlay(self)
        self._theme_overlay.show_over(self, "Switching to Light Theme…")
        QApplication.processEvents()          # let Qt paint the overlay
        # … do the heavy theme work …
        self._theme_overlay.finish()
    """

    _ARC_SIZE   = 56     # diameter of the spinner ring (px)
    _ARC_WIDTH  =  5     # pen width of the ring
    _SPIN_STEP  = 12     # degrees advanced per timer tick
    _TICK_MS    = 30     # timer interval in milliseconds

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        self._angle   = 0      # current start angle of the arc (degrees × 16 for Qt)
        self._label   = ""

        self._timer = QTimer(self)
        self._timer.setInterval(self._TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_over(self, window: QWidget, message: str = "Switching theme…") -> None:
        """Resize to cover *window* and make visible."""
        self._label = message
        self._angle = 0
        self.setParent(window)
        self.resize(window.size())
        self.raise_()
        self.show()
        self._timer.start()

    def finish(self) -> None:
        """Stop the spinner and hide the overlay."""
        self._timer.stop()
        self.hide()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        self._angle = (self._angle + self._SPIN_STEP) % 360
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        from src.gui.theme import is_dark
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── Background scrim ──────────────────────────────────────────
        scrim = QColor(15, 16, 22, 210) if is_dark() else QColor(240, 242, 248, 210)
        painter.fillRect(self.rect(), scrim)

        cx = self.width()  // 2
        cy = self.height() // 2
        r  = self._ARC_SIZE // 2

        # ── Spinner ring (track) ──────────────────────────────────────
        track_col = QColor(80, 90, 120, 100) if is_dark() else QColor(180, 190, 210, 140)
        pen = QPen(track_col, self._ARC_WIDTH, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        rect = QRectF(cx - r, cy - r, self._ARC_SIZE, self._ARC_SIZE)
        painter.drawEllipse(rect)

        # ── Spinner arc (progress) ────────────────────────────────────
        arc_col = QColor("#3FA9F5") if is_dark() else QColor("#2A7FCC")
        pen.setColor(arc_col)
        painter.setPen(pen)
        # Qt angles: 0° = 3 o'clock, positive = counter-clockwise
        # We want clockwise rotation so negate the angle.
        start_angle = (90 - self._angle) * 16   # 12 o'clock start, rotating CW
        span_angle  = -120 * 16                  # 120° arc sweep
        painter.drawArc(rect, start_angle, span_angle)

        # ── Label ─────────────────────────────────────────────────────
        text_col = QColor("#F0F2F5") if is_dark() else QColor("#1A1C24")
        painter.setPen(QPen(text_col))
        font = painter.font()
        font.setFamily("Segoe UI")
        font.setPointSize(10)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(
            0, cy + r + 18, self.width(), 28,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self._label,
        )

        painter.end()

    def resizeEvent(self, event) -> None:  # noqa: N802
        """Keep overlay covering the full parent window if it resizes."""
        if self.parent():
            self.resize(self.parent().size())
        super().resizeEvent(event)


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


class PeakHoverAnnotator:
    """
    Attaches an interactive hover tooltip and highlight ring to scatter peaks on a Matplotlib Axes.

    Shows exact (x, y) coordinates and physical labels (e.g. wavelength in nm and intensity)
    when the mouse cursor hovers within a configurable pixel radius of any peak marker.
    """

    def __init__(
        self,
        canvas: FigureCanvas,
        radius_px: float = 14.0,
        x_unit: str = "nm",
        y_unit: str = "",
        x_name: str = "Wavelength",
        y_name: str = "Intensity",
    ):
        self.canvas = canvas
        self.radius_px = radius_px
        self.x_unit = x_unit
        self.y_unit = y_unit
        self.x_name = x_name
        self.y_name = y_name

        self.ax: Optional[Any] = None
        self._peak_x: Optional[np.ndarray] = None
        self._peak_y: Optional[np.ndarray] = None
        self._extra_info: Optional[List[str]] = None
        self._current_idx: Optional[int] = None

        self._annot = None
        self._highlight = None

        # Connect canvas events
        self._cid_motion = self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self._cid_leave = self.canvas.mpl_connect("figure_leave_event", self._on_leave)

    def attach(
        self,
        ax: Any,
        peak_x: np.ndarray | list[float],
        peak_y: np.ndarray | list[float],
        extra_info: Optional[List[str]] = None,
    ) -> None:
        """Attach peak coordinates and initialize artists on the given axes."""
        self.ax = ax
        self._peak_x = np.asarray(peak_x, dtype=float) if peak_x is not None else None
        self._peak_y = np.asarray(peak_y, dtype=float) if peak_y is not None else None
        self._extra_info = extra_info
        self._current_idx = None

        from src.gui.theme import (
            get_chart_axes_bg, get_chart_text, is_dark, C_ACCENT, L_ACCENT
        )
        accent = C_ACCENT if is_dark() else L_ACCENT

        self._annot = self.ax.annotate(
            "",
            xy=(0, 0),
            xytext=(14, 14),
            textcoords="offset points",
            bbox=dict(
                boxstyle="round,pad=0.5",
                facecolor=get_chart_axes_bg(),
                edgecolor=accent,
                linewidth=1.2,
                alpha=0.95,
            ),
            arrowprops=dict(
                arrowstyle="->",
                connectionstyle="arc3,rad=0",
                color=accent,
                linewidth=1.2,
            ),
            fontsize=9,
            fontweight="bold",
            color=get_chart_text(),
            zorder=25,
        )
        self._annot.set_visible(False)

        self._highlight, = self.ax.plot(
            [], [],
            marker="o",
            markersize=10,
            markeredgecolor=accent,
            markerfacecolor="none",
            markeredgewidth=2.0,
            linestyle="none",
            zorder=24,
        )
        self._highlight.set_visible(False)

    def update_theme(self) -> None:
        """Update colors of the annotation and highlight ring to match active theme."""
        if self._annot is None or self._highlight is None:
            return
        from src.gui.theme import (
            get_chart_axes_bg, get_chart_text, is_dark, C_ACCENT, L_ACCENT
        )
        accent = C_ACCENT if is_dark() else L_ACCENT
        try:
            self._annot.get_bbox_patch().set_facecolor(get_chart_axes_bg())
            self._annot.get_bbox_patch().set_edgecolor(accent)
            self._annot.arrowprops['color'] = accent
            self._annot.set_color(get_chart_text())
            self._highlight.set_markeredgecolor(accent)
        except Exception:
            pass

    def clear(self) -> None:
        """Clear data and hide annotations."""
        self._peak_x = None
        self._peak_y = None
        self._extra_info = None
        self._current_idx = None
        if self._annot is not None:
            try:
                self._annot.set_visible(False)
            except Exception:
                pass
        if self._highlight is not None:
            try:
                self._highlight.set_visible(False)
            except Exception:
                pass

    def detach(self) -> None:
        """Alias for clear()."""
        self.clear()

    def _on_motion(self, event) -> None:
        if (
            self.ax is None
            or event.inaxes != self.ax
            or self._peak_x is None
            or len(self._peak_x) == 0
            or self._annot is None
            or self._highlight is None
        ):
            self._hide()
            return

        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        mask = (
            (self._peak_x >= xlim[0]) & (self._peak_x <= xlim[1]) &
            (self._peak_y >= ylim[0]) & (self._peak_y <= ylim[1])
        )
        if not np.any(mask):
            self._hide()
            return

        vis_indices = np.where(mask)[0]
        pts = self.ax.transData.transform(
            np.column_stack([self._peak_x[mask], self._peak_y[mask]])
        )
        dists = np.hypot(pts[:, 0] - event.x, pts[:, 1] - event.y)
        min_sub = int(np.argmin(dists))

        if dists[min_sub] <= self.radius_px:
            target_idx = int(vis_indices[min_sub])
            self._show_peak(target_idx, pts[min_sub])
        else:
            self._hide()

    def _show_peak(self, idx: int, disp_pt: np.ndarray) -> None:
        if self._current_idx == idx:
            return  # already showing this peak, avoid redraw

        self._current_idx = idx
        x_val = float(self._peak_x[idx])
        y_val = float(self._peak_y[idx])

        # Dynamic flip if near canvas edges
        bbox = self.ax.bbox
        offset_x = -135 if disp_pt[0] > (bbox.xmax - 120) else 14
        offset_y = -55 if disp_pt[1] > (bbox.ymax - 60) else 14

        extra = f"\n{self._extra_info[idx]}" if self._extra_info and idx < len(self._extra_info) else ""
        unit_str = f" {self.x_unit}" if self.x_unit else ""
        y_unit_str = f" {self.y_unit}" if self.y_unit else ""
        text = (
            f"({x_val:.2f}, {y_val:.2f})\n"
            f"{self.x_name}: {x_val:.2f}{unit_str}\n"
            f"{self.y_name}: {y_val:.2f}{y_unit_str}{extra}"
        )

        self._annot.xy = (x_val, y_val)
        self._annot.xyann = (offset_x, offset_y)
        self._annot.set_text(text)
        self._annot.set_visible(True)

        self._highlight.set_data([x_val], [y_val])
        self._highlight.set_visible(True)
        self.canvas.draw_idle()

    def _hide(self) -> None:
        if self._current_idx is not None:
            self._current_idx = None
            if self._annot is not None:
                self._annot.set_visible(False)
            if self._highlight is not None:
                self._highlight.set_visible(False)
            self.canvas.draw_idle()

    def _on_leave(self, event) -> None:
        self._hide()


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


# ---------------------------------------------------------------------------
# Foreground-respecting item delegate
# ---------------------------------------------------------------------------

class ForegroundDelegate(QStyledItemDelegate):
    """Item delegate that always honours the item's ForegroundRole colour.

    Qt's global stylesheet (``QWidget { color: … }``) cascades into table
    cells and silently overrides ``setForeground()`` for the normal (not
    hovered, not selected) state.  This delegate reads the ForegroundRole
    directly from the model and paints the text with that colour, so coloured
    cells (e.g. Quality tier badges) are always legible regardless of the
    active stylesheet theme.
    """

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        fg = index.data(Qt.ItemDataRole.ForegroundRole)
        if fg is not None:
            # fg is a QBrush; extract the colour and override the palette entry
            # that the style uses to draw the display text.
            colour = fg.color() if hasattr(fg, "color") else QColor(fg)
            option.palette.setColor(option.palette.ColorRole.Text, colour)
            # Also override the highlighted-text colour so selected rows keep
            # a readable foreground (white on accent background).
            option.palette.setColor(
                option.palette.ColorRole.HighlightedText, QColor("#FFFFFF")
            )


# ---------------------------------------------------------------------------
# Copy-table toolbar utility
# ---------------------------------------------------------------------------

def make_table_toolbar(
    table: "QTableWidget",  # noqa: F821  (forward ref, QTableWidget imported at call site)
    *,
    row_label_text: str = "— rows",
) -> "tuple[QWidget, QPushButton, QLabel]":
    """Create a slim toolbar bar for a table with a row-count label and copy toggle.

    Returns
    -------
    container : QWidget
        A ``QWidget`` with a ``QVBoxLayout`` containing *toolbar* (fixed 34 px
        height) above *table*.  Add this container wherever the raw table used
        to be placed.
    copy_btn : QPushButton
        The checkable copy button.  Connect to :func:`on_copy_table_clicked`
        or your own handler.
    row_label : QLabel
        The label showing row count.  Update its text after populating the table.

    The caller is responsible for:
    * Updating ``row_label.setText(...)`` after data is loaded.
    * Enabling/disabling ``copy_btn`` as appropriate.
    * Connecting ``copy_btn.clicked`` to :func:`on_copy_table_clicked` or a custom slot.
    """
    from src.gui.theme import (
        C_BG_BASE, C_BG_RAISED, C_BG_INPUT, C_BORDER, C_ACCENT,
        C_TEXT, C_TEXT2, C_TEXT_MUTED,
    )

    # ── Toolbar strip ──────────────────────────────────────────────────
    toolbar = QWidget()
    toolbar.setFixedHeight(34)
    toolbar.setStyleSheet(
        f"background-color: {C_BG_RAISED}; border-bottom: 1px solid {C_BORDER};"
    )
    tb_layout = QHBoxLayout(toolbar)
    tb_layout.setContentsMargins(8, 0, 8, 0)
    tb_layout.setSpacing(8)

    row_label = QLabel(row_label_text)
    row_label.setStyleSheet(
        f"color: {C_TEXT2}; font-size: 9pt; background: transparent; border: none;"
    )
    tb_layout.addWidget(row_label)
    tb_layout.addStretch()

    copy_btn = QPushButton("⎘  Copy")
    copy_btn.setCheckable(True)
    copy_btn.setFixedHeight(24)
    copy_btn.setToolTip(
        "Copy all rows as tab-separated values to clipboard.\n"
        "Click again to deselect."
    )
    copy_btn.setStyleSheet(f"""
QPushButton {{
    background-color: {C_BG_INPUT};
    color: {C_TEXT2};
    border: 1px solid {C_BORDER};
    border-radius: 4px;
    padding: 0 10px;
    font-size: 9pt;
}}
QPushButton:hover {{
    background-color: {C_BG_RAISED};
    color: {C_TEXT};
    border-color: {C_ACCENT};
}}
QPushButton:checked {{
    background-color: {C_ACCENT};
    color: #ffffff;
    border-color: {C_ACCENT};
}}
QPushButton:disabled {{
    color: {C_TEXT_MUTED};
    border-color: {C_BORDER};
    background-color: {C_BG_BASE};
}}
""")
    copy_btn.setEnabled(False)
    tb_layout.addWidget(copy_btn)

    # ── Container ──────────────────────────────────────────────────────
    container = QWidget()
    cl = QVBoxLayout(container)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)
    cl.addWidget(toolbar)
    cl.addWidget(table)

    return container, copy_btn, row_label


def on_copy_table_clicked(
    table: "QTableWidget",  # noqa: F821
    copy_btn: QPushButton,
    row_label: QLabel,
    *,
    base_label: str = "",
) -> None:
    """Handle the copy toggle button click for any table.

    Pass this as the ``clicked`` slot (via ``lambda``) from any widget.

    Parameters
    ----------
    table      : the QTableWidget whose data should be copied.
    copy_btn   : the checkable QPushButton that triggered the click.
    row_label  : the row-count QLabel in the toolbar (updated on copy).
    base_label : base text for row_label (e.g. "12 rows").  When empty the
                 current label text up to " ·" is kept.
    """
    from PyQt6.QtWidgets import QApplication

    rows = table.rowCount()
    cols = table.columnCount()

    if not copy_btn.isChecked():
        # Second press — deselect and reset
        table.clearSelection()
        copy_btn.setText("⎘  Copy")
        if base_label:
            row_label.setText(base_label)
        else:
            # Trim the "· copied" suffix if present
            current = row_label.text()
            row_label.setText(current.split(" ·")[0])
        return

    if rows == 0:
        copy_btn.setChecked(False)
        return

    # Build TSV
    headers = [
        (table.horizontalHeaderItem(c).text()
         if table.horizontalHeaderItem(c) else "")
        for c in range(cols)
    ]
    lines = ["\t".join(headers)]
    for r in range(rows):
        row_cells = []
        for c in range(cols):
            item = table.item(r, c)
            row_cells.append(item.text() if item else "")
        lines.append("\t".join(row_cells))

    QApplication.clipboard().setText("\n".join(lines))

    copy_btn.setText("✓  Copied!")
    # Update label
    current_base = base_label or row_label.text().split(" ·")[0]
    row_label.setText(f"{current_base}  ·  copied to clipboard")
