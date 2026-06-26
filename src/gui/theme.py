# -*- coding: utf-8 -*-
"""
Application Theme — Spectral Analysis Software
Professional Scientific Dark Theme

Design language: clean, high-information-density, precision-focused.
Comparable to OriginPro / MATLAB dark mode.

Palette
-------
  Background (base)    : #1E1F26
  Background (panel)   : #262A36
  Background (raised)  : #2F3443
  Background (input)   : #323849
  Border (subtle)      : #3A4055
  Border (focus)       : #3FA9F5
  Accent blue          : #3FA9F5
  Accent teal          : #3DDC97
  Warning amber        : #F4B942
  Danger red           : #E85D75
  Text primary         : #F0F2F5
  Text secondary       : #AEB7C4
  Text muted           : #6B7589
  Hover overlay        : rgba(63,169,245,0.08)
  Pressed overlay      : rgba(63,169,245,0.18)
  Tab active bg        : #2F3443
  Tab inactive bg      : #1E1F26
"""

# ──────────────────────────────────────────────────────────────────────────────
# Typography
# ──────────────────────────────────────────────────────────────────────────────
FONT_FAMILY_UI   = "Segoe UI"
FONT_FAMILY_MONO = "Consolas"
FONT_SIZE_BASE   = 10

# ──────────────────────────────────────────────────────────────────────────────
# Palette constants
# ──────────────────────────────────────────────────────────────────────────────
C_BG_BASE    = "#1E1F26"
C_BG_PANEL   = "#262A36"
C_BG_RAISED  = "#2F3443"
C_BG_INPUT   = "#323849"
C_BG_DEEP    = "#141519"   # deepest — used for chart backgrounds, status bar
C_BG_CARD    = "#2F3443"   # alias for raised panels

C_BORDER     = "#3A4055"
C_BORDER_FOCUS = "#3FA9F5"
C_BORDER_SUBTLE = "#2E3348"

C_ACCENT     = "#3FA9F5"   # primary blue
C_ACCENT2    = "#3DDC97"   # teal / success
C_WARN       = "#F4B942"
C_ERROR      = "#E85D75"
C_SUCCESS    = "#3DDC97"

C_TEXT       = "#F0F2F5"
C_TEXT2      = "#AEB7C4"
C_TEXT_MUTED = "#6B7589"

C_HOVER      = "rgba(63,169,245,0.08)"
C_PRESSED    = "rgba(63,169,245,0.18)"
C_ROW_ALT    = "#2A2F3E"
C_ROW_HOVER  = "#374060"
C_SELECTION  = "#3FA9F5"

C_TAB_ACTIVE   = "#2F3443"
C_TAB_INACTIVE = "#1E1F26"

# ──────────────────────────────────────────────────────────────────────────────
# Full application stylesheet
# ──────────────────────────────────────────────────────────────────────────────
APP_STYLESHEET = f"""

/* ═══════════════════════════════════════════════════════════════════════
   GLOBAL RESET
═══════════════════════════════════════════════════════════════════════ */

* {{
    outline: none;
}}

QWidget {{
    background-color: {C_BG_PANEL};
    color: {C_TEXT};
    font-family: "{FONT_FAMILY_UI}", "Segoe UI", Arial, sans-serif;
    font-size: {FONT_SIZE_BASE}pt;
    selection-background-color: {C_ACCENT};
    selection-color: #ffffff;
}}

QMainWindow {{
    background-color: {C_BG_BASE};
}}

/* ═══════════════════════════════════════════════════════════════════════
   TABS  —  active step must be immediately obvious
═══════════════════════════════════════════════════════════════════════ */

QTabWidget::pane {{
    background-color: {C_BG_PANEL};
    border: none;
    border-top: 2px solid {C_BORDER};
}}

QTabBar {{
    background-color: {C_BG_BASE};
    qproperty-drawBase: 0;
}}

QTabBar::tab {{
    background-color: {C_TAB_INACTIVE};
    color: {C_TEXT_MUTED};
    border: none;
    border-bottom: 3px solid transparent;
    padding: 9px 20px 8px 20px;
    margin-right: 1px;
    font-weight: 500;
    font-size: 9pt;
    min-width: 130px;
}}

QTabBar::tab:selected {{
    background-color: {C_TAB_ACTIVE};
    color: {C_ACCENT};
    border-bottom: 3px solid {C_ACCENT};
    font-weight: 700;
    font-size: 9pt;
}}

QTabBar::tab:hover:!selected {{
    background-color: {C_BG_RAISED};
    color: {C_TEXT2};
    border-bottom: 3px solid {C_BORDER};
}}

/* ═══════════════════════════════════════════════════════════════════════
   GROUP BOXES  —  reduced borders, elevated background
═══════════════════════════════════════════════════════════════════════ */

QGroupBox {{
    background-color: {C_BG_RAISED};
    border: 1px solid {C_BORDER_SUBTLE};
    border-radius: 7px;
    margin-top: 16px;
    padding: 10px 10px 10px 10px;
    font-weight: 600;
    font-size: 8pt;
    color: {C_TEXT2};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    left: 14px;
    top: -1px;
    color: {C_ACCENT2};
    font-weight: 700;
    font-size: 8pt;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    background-color: transparent;
}}

/* ═══════════════════════════════════════════════════════════════════════
   BUTTONS
═══════════════════════════════════════════════════════════════════════ */

QPushButton {{
    background-color: {C_BG_INPUT};
    color: {C_TEXT2};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 6px 18px;
    font-weight: 600;
    font-size: 9pt;
    min-height: 28px;
}}

QPushButton:hover {{
    background-color: {C_BG_RAISED};
    border-color: {C_ACCENT};
    color: {C_TEXT};
}}

QPushButton:pressed {{
    background-color: {C_BG_BASE};
    border-color: {C_ACCENT};
    color: {C_ACCENT};
}}

QPushButton:disabled {{
    background-color: {C_BG_RAISED};
    color: {C_TEXT_MUTED};
    border-color: {C_BORDER_SUBTLE};
}}

/* ═══════════════════════════════════════════════════════════════════════
   LABELS
═══════════════════════════════════════════════════════════════════════ */

QLabel {{
    background-color: transparent;
    color: {C_TEXT};
    font-size: {FONT_SIZE_BASE}pt;
}}

/* ═══════════════════════════════════════════════════════════════════════
   INPUTS — line edit, spinbox, combo
═══════════════════════════════════════════════════════════════════════ */

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {C_BG_INPUT};
    color: {C_TEXT};
    border: 1px solid {C_BORDER};
    border-radius: 5px;
    padding: 4px 10px;
    font-size: 9pt;
    min-height: 26px;
    selection-background-color: {C_ACCENT};
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {C_BORDER_FOCUS};
    background-color: {C_BG_RAISED};
}}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background-color: transparent;
    border: none;
    width: 18px;
    subcontrol-origin: border;
}}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {C_BG_RAISED};
    border-radius: 3px;
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
    padding-right: 4px;
}}

QComboBox QAbstractItemView {{
    background-color: {C_BG_RAISED};
    color: {C_TEXT};
    border: 1px solid {C_BORDER};
    border-radius: 5px;
    selection-background-color: {C_ACCENT};
    selection-color: #ffffff;
    padding: 2px;
    outline: none;
}}

/* ═══════════════════════════════════════════════════════════════════════
   SLIDERS
═══════════════════════════════════════════════════════════════════════ */

QSlider::groove:horizontal {{
    background-color: {C_BG_INPUT};
    height: 4px;
    border-radius: 2px;
    border: none;
}}

QSlider::handle:horizontal {{
    background-color: {C_ACCENT};
    border: 2px solid {C_BG_PANEL};
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}

QSlider::handle:horizontal:hover {{
    background-color: #6FC4FB;
    border-color: {C_BG_PANEL};
}}

QSlider::sub-page:horizontal {{
    background-color: {C_ACCENT};
    height: 4px;
    border-radius: 2px;
}}

/* ═══════════════════════════════════════════════════════════════════════
   TABLES  —  taller rows, alternating colors, strong headers
═══════════════════════════════════════════════════════════════════════ */

QTableWidget {{
    background-color: {C_BG_RAISED};
    color: {C_TEXT};
    gridline-color: {C_BORDER_SUBTLE};
    border: none;
    border-radius: 6px;
    font-size: 9pt;
    alternate-background-color: {C_ROW_ALT};
    show-decoration-selected: 1;
}}

QTableWidget::item {{
    padding: 6px 10px;
    border: none;
    min-height: 28px;
}}

QTableWidget::item:selected {{
    background-color: {C_ACCENT};
    color: #ffffff;
}}

QTableWidget::item:hover {{
    background-color: {C_ROW_HOVER};
}}

QHeaderView {{
    background-color: transparent;
}}

QHeaderView::section {{
    background-color: {C_BG_BASE};
    color: {C_ACCENT};
    padding: 7px 12px;
    border: none;
    border-right: 1px solid {C_BORDER_SUBTLE};
    border-bottom: 2px solid {C_ACCENT};
    font-weight: 700;
    font-size: 8pt;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}

QHeaderView::section:first {{
    border-left: none;
}}

QHeaderView::section:hover {{
    background-color: {C_BG_RAISED};
    color: {C_TEXT};
}}

/* ═══════════════════════════════════════════════════════════════════════
   PLAIN TEXT EDIT  (Notes & History panel)
═══════════════════════════════════════════════════════════════════════ */

QPlainTextEdit {{
    background-color: {C_BG_BASE};
    color: {C_TEXT2};
    border: none;
    border-top: 1px solid {C_BORDER_SUBTLE};
    border-radius: 0px;
    font-family: "{FONT_FAMILY_MONO}", "Courier New", monospace;
    font-size: 8pt;
    padding: 6px;
    selection-background-color: {C_ACCENT};
}}

/* ═══════════════════════════════════════════════════════════════════════
   SCROLL BARS  — high-contrast, clearly interactive
═══════════════════════════════════════════════════════════════════════ */

QScrollBar:vertical {{
    background-color: {C_BG_BASE};
    width: 12px;
    margin: 0;
    border-radius: 6px;
    border: 1px solid {C_BORDER_SUBTLE};
}}

QScrollBar::handle:vertical {{
    background-color: #5A6485;
    border-radius: 5px;
    min-height: 40px;
    margin: 2px;
    border: 1px solid #7080AA;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {C_ACCENT};
    border: 1px solid #7EC0FF;
}}

QScrollBar::handle:vertical:pressed {{
    background-color: #2A7FCC;
    border: 1px solid {C_ACCENT};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: {C_BG_BASE};
}}

QScrollBar:horizontal {{
    background-color: {C_BG_BASE};
    height: 12px;
    margin: 0;
    border-radius: 6px;
    border: 1px solid {C_BORDER_SUBTLE};
}}

QScrollBar::handle:horizontal {{
    background-color: #5A6485;
    border-radius: 5px;
    min-width: 40px;
    margin: 2px;
    border: 1px solid #7080AA;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {C_ACCENT};
    border: 1px solid #7EC0FF;
}}

QScrollBar::handle:horizontal:pressed {{
    background-color: #2A7FCC;
    border: 1px solid {C_ACCENT};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: {C_BG_BASE};
}}

/* ═══════════════════════════════════════════════════════════════════════
   SPLITTER HANDLES  — clearly draggable accent lines
═══════════════════════════════════════════════════════════════════════ */

QSplitter::handle {{
    background-color: {C_BORDER};
}}

QSplitter::handle:horizontal {{
    width: 5px;
    background-color: {C_BG_BASE};
    border-left: 2px solid {C_ACCENT};
    border-right: 1px solid {C_BORDER_SUBTLE};
}}

QSplitter::handle:horizontal:hover {{
    background-color: {C_ACCENT};
    border-left: 2px solid #7EC0FF;
    border-right: 2px solid #7EC0FF;
}}

QSplitter::handle:vertical {{
    height: 5px;
    background-color: {C_BG_BASE};
    border-top: 2px solid {C_ACCENT};
    border-bottom: 1px solid {C_BORDER_SUBTLE};
}}

QSplitter::handle:vertical:hover {{
    background-color: {C_ACCENT};
    border-top: 2px solid #7EC0FF;
    border-bottom: 2px solid #7EC0FF;
}}

/* ═══════════════════════════════════════════════════════════════════════
   STATUS BAR
═══════════════════════════════════════════════════════════════════════ */

QStatusBar {{
    background-color: {C_BG_BASE};
    color: {C_TEXT_MUTED};
    border-top: 1px solid {C_BORDER_SUBTLE};
    font-size: 8pt;
    padding: 2px 10px;
}}

/* ═══════════════════════════════════════════════════════════════════════
   TOOLTIPS
═══════════════════════════════════════════════════════════════════════ */

QToolTip {{
    background-color: {C_BG_RAISED};
    color: {C_TEXT};
    border: 1px solid {C_ACCENT};
    padding: 5px 10px;
    border-radius: 5px;
    font-size: 9pt;
}}

/* ═══════════════════════════════════════════════════════════════════════
   MESSAGE BOXES
═══════════════════════════════════════════════════════════════════════ */

QMessageBox {{
    background-color: {C_BG_PANEL};
    color: {C_TEXT};
}}

QMessageBox QLabel {{
    color: {C_TEXT};
    font-size: {FONT_SIZE_BASE}pt;
    min-width: 300px;
}}

QMessageBox QPushButton {{
    min-width: 90px;
    padding: 7px 22px;
}}

/* ═══════════════════════════════════════════════════════════════════════
   PROGRESS BAR
═══════════════════════════════════════════════════════════════════════ */

QProgressBar {{
    background-color: {C_BG_INPUT};
    border: none;
    border-radius: 3px;
    height: 5px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background-color: {C_ACCENT};
    border-radius: 3px;
}}

/* ═══════════════════════════════════════════════════════════════════════
   FRAME  (used in summary cards, etc.)
═══════════════════════════════════════════════════════════════════════ */

QFrame[frameShape="5"] {{
    color: {C_BORDER};
}}

"""

# ──────────────────────────────────────────────────────────────────────────────
# Per-widget inline style helpers
# ──────────────────────────────────────────────────────────────────────────────

def primary_button_style(color: str = C_ACCENT) -> str:
    """Primary action button — filled accent colour."""
    return (
        f"QPushButton {{"
        f"  background-color: {color};"
        f"  color: #ffffff;"
        f"  border: none;"
        f"  border-radius: 6px;"
        f"  padding: 7px 22px;"
        f"  font-weight: 700;"
        f"  font-size: 9pt;"
        f"  letter-spacing: 0.3px;"
        f"  min-height: 30px;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background-color: #6FC4FB;"
        f"}}"
        f"QPushButton:pressed {{"
        f"  background-color: #2A7FCC;"
        f"}}"
        f"QPushButton:disabled {{"
        f"  background-color: {C_BG_INPUT};"
        f"  color: {C_TEXT_MUTED};"
        f"  border: 1px solid {C_BORDER_SUBTLE};"
        f"}}"
    )


def instruction_banner_style() -> str:
    """Instruction banner — low-contrast info block."""
    return (
        f"QLabel {{"
        f"  background-color: #1A2030;"
        f"  color: {C_TEXT2};"
        f"  border: none;"
        f"  border-left: 3px solid {C_ACCENT2};"
        f"  border-radius: 5px;"
        f"  padding: 8px 14px;"
        f"  font-size: 8pt;"
        f"  line-height: 1.6;"
        f"}}"
    )


def step_title_font(size: int = 13) -> str:
    """Step title label style."""
    return (
        f"QLabel {{"
        f"  color: {C_TEXT};"
        f"  font-size: {size}pt;"
        f"  font-weight: 700;"
        f"  letter-spacing: 0.8px;"
        f"  background: transparent;"
        f"  padding-bottom: 4px;"
        f"}}"
    )


def summary_banner_style() -> str:
    """Summary statistics banner."""
    return (
        f"QLabel {{"
        f"  background-color: #1C2535;"
        f"  color: {C_TEXT2};"
        f"  border: none;"
        f"  border-left: 3px solid {C_ACCENT};"
        f"  border-radius: 5px;"
        f"  padding: 8px 14px;"
        f"  font-size: 9pt;"
        f"}}"
    )


def primary_element_label_style() -> str:
    """Primary element name label — prominent, teal."""
    return (
        f"QLabel {{"
        f"  background-color: transparent;"
        f"  color: {C_ACCENT2};"
        f"  font-size: 15pt;"
        f"  font-weight: 700;"
        f"  letter-spacing: 0.5px;"
        f"}}"
    )


def mean_vc_label_style(colour: str) -> str:
    """Mean VC label — tier-coloured, bold."""
    return (
        f"QLabel {{"
        f"  background-color: transparent;"
        f"  color: {colour};"
        f"  font-size: 15pt;"
        f"  font-weight: 700;"
        f"}}"
    )


def progress_bar_style() -> str:
    """Thin indeterminate progress bar."""
    return (
        f"QProgressBar {{"
        f"  background-color: {C_BG_INPUT};"
        f"  border: none;"
        f"  border-radius: 3px;"
        f"  max-height: 5px;"
        f"  text-align: center;"
        f"  color: transparent;"
        f"}}"
        f"QProgressBar::chunk {{"
        f"  background-color: {C_ACCENT};"
        f"  border-radius: 3px;"
        f"}}"
    )
