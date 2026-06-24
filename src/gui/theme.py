# -*- coding: utf-8 -*-
"""
Application Theme — Spectral Analysis Software

Central stylesheet for the entire application.
All visual styling lives here. No logic is changed anywhere else.

Colour palette (dark professional / scientific):
  Background (deep)  : #0F1117
  Background (panel) : #1A1D27
  Background (card)  : #222536
  Background (input) : #2A2D3E
  Border             : #3A3D52
  Accent blue        : #4A9EFF   (primary actions)
  Accent teal        : #2DD4BF   (success / highlights)
  Accent amber       : #F59E0B   (warnings)
  Accent red         : #EF4444   (errors)
  Text primary       : #E8EAF0
  Text secondary     : #8B90A4
  Text muted         : #555970
"""

# --------------------------------------------------------------------------
# Typography
# --------------------------------------------------------------------------
FONT_FAMILY_UI   = "Segoe UI"      # primary UI font (ships with Windows 10/11)
FONT_FAMILY_MONO = "Consolas"      # monospace (logs, tables)
FONT_SIZE_BASE   = 10              # pt — base body size

# --------------------------------------------------------------------------
# Palette constants (referenced in the stylesheet below)
# --------------------------------------------------------------------------
C_BG_DEEP    = "#0F1117"
C_BG_PANEL   = "#1A1D27"
C_BG_CARD    = "#222536"
C_BG_INPUT   = "#2A2D3E"
C_BORDER     = "#3A3D52"
C_BORDER_FOCUS = "#4A9EFF"
C_ACCENT     = "#4A9EFF"
C_ACCENT2    = "#2DD4BF"
C_WARN       = "#F59E0B"
C_ERROR      = "#EF4444"
C_SUCCESS    = "#22C55E"
C_TEXT       = "#E8EAF0"
C_TEXT2      = "#8B90A4"
C_TEXT_MUTED = "#555970"
C_HOVER      = "#2E3348"
C_PRESSED    = "#1E2135"
C_TAB_ACTIVE = "#222536"
C_TAB_INACTIVE = "#1A1D27"

# --------------------------------------------------------------------------
# Full application stylesheet
# --------------------------------------------------------------------------
APP_STYLESHEET = f"""

/* ===================================================================
   GLOBAL
=================================================================== */

QWidget {{
    background-color: {C_BG_PANEL};
    color: {C_TEXT};
    font-family: "{FONT_FAMILY_UI}", "Segoe UI", Arial, sans-serif;
    font-size: {FONT_SIZE_BASE}pt;
    selection-background-color: {C_ACCENT};
    selection-color: #ffffff;
}}

QMainWindow {{
    background-color: {C_BG_DEEP};
}}

/* ===================================================================
   TABS
=================================================================== */

QTabWidget::pane {{
    background-color: {C_BG_PANEL};
    border: 1px solid {C_BORDER};
    border-top: 2px solid {C_ACCENT};
    border-radius: 0px 4px 4px 4px;
}}

QTabBar {{
    background-color: transparent;
    qproperty-drawBase: 0;
}}

QTabBar::tab {{
    background-color: {C_TAB_INACTIVE};
    color: {C_TEXT2};
    border: 1px solid {C_BORDER};
    border-bottom: none;
    padding: 8px 18px;
    margin-right: 2px;
    border-radius: 4px 4px 0px 0px;
    font-weight: 500;
    font-size: 9pt;
    min-width: 140px;
}}

QTabBar::tab:selected {{
    background-color: {C_TAB_ACTIVE};
    color: {C_ACCENT};
    border-top: 2px solid {C_ACCENT};
    font-weight: 700;
}}

QTabBar::tab:hover:!selected {{
    background-color: {C_HOVER};
    color: {C_TEXT};
}}

/* ===================================================================
   GROUP BOXES
=================================================================== */

QGroupBox {{
    background-color: {C_BG_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    margin-top: 14px;
    padding: 10px 8px 8px 8px;
    font-weight: 600;
    font-size: 9pt;
    color: {C_TEXT2};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    left: 12px;
    color: {C_ACCENT2};
    font-weight: 700;
    font-size: 9pt;
    letter-spacing: 0.5px;
}}

/* ===================================================================
   BUTTONS
=================================================================== */

QPushButton {{
    background-color: {C_BG_INPUT};
    color: {C_TEXT};
    border: 1px solid {C_BORDER};
    border-radius: 5px;
    padding: 6px 16px;
    font-weight: 600;
    font-size: 9pt;
    outline: none;
}}

QPushButton:hover {{
    background-color: {C_HOVER};
    border-color: {C_ACCENT};
    color: {C_ACCENT};
}}

QPushButton:pressed {{
    background-color: {C_PRESSED};
    border-color: {C_ACCENT};
}}

QPushButton:disabled {{
    background-color: {C_BG_CARD};
    color: {C_TEXT_MUTED};
    border-color: {C_BORDER};
}}

/* Primary action button — keep the per-widget inline style as override */

/* ===================================================================
   LABELS
=================================================================== */

QLabel {{
    background-color: transparent;
    color: {C_TEXT};
    font-size: {FONT_SIZE_BASE}pt;
}}

/* ===================================================================
   LINE EDIT / SPIN BOX / COMBO BOX
=================================================================== */

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {C_BG_INPUT};
    color: {C_TEXT};
    border: 1px solid {C_BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 9pt;
    selection-background-color: {C_ACCENT};
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {C_BORDER_FOCUS};
    background-color: {C_BG_INPUT};
}}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background-color: {C_BG_CARD};
    border: none;
    width: 16px;
}}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {C_HOVER};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background-color: {C_BG_CARD};
    color: {C_TEXT};
    border: 1px solid {C_BORDER};
    selection-background-color: {C_ACCENT};
    selection-color: #ffffff;
    outline: none;
}}

/* ===================================================================
   SLIDERS
=================================================================== */

QSlider::groove:horizontal {{
    background-color: {C_BG_INPUT};
    height: 4px;
    border-radius: 2px;
    border: 1px solid {C_BORDER};
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
    background-color: #6AB4FF;
}}

QSlider::sub-page:horizontal {{
    background-color: {C_ACCENT};
    height: 4px;
    border-radius: 2px;
}}

/* ===================================================================
   TABLES
=================================================================== */

QTableWidget {{
    background-color: {C_BG_CARD};
    color: {C_TEXT};
    gridline-color: {C_BORDER};
    border: 1px solid {C_BORDER};
    border-radius: 4px;
    font-size: 9pt;
    alternate-background-color: {C_BG_INPUT};
}}

QTableWidget::item {{
    padding: 4px 8px;
    border: none;
}}

QTableWidget::item:selected {{
    background-color: {C_ACCENT};
    color: #ffffff;
}}

QTableWidget::item:hover {{
    background-color: {C_HOVER};
}}

QHeaderView::section {{
    background-color: {C_BG_DEEP};
    color: {C_ACCENT2};
    padding: 6px 10px;
    border: none;
    border-right: 1px solid {C_BORDER};
    border-bottom: 2px solid {C_ACCENT};
    font-weight: 700;
    font-size: 9pt;
    letter-spacing: 0.3px;
}}

QHeaderView::section:first {{
    border-left: none;
}}

/* ===================================================================
   PLAIN TEXT EDIT (Notes panel)
=================================================================== */

QPlainTextEdit {{
    background-color: {C_BG_DEEP};
    color: {C_TEXT2};
    border: 1px solid {C_BORDER};
    border-radius: 4px;
    font-family: "{FONT_FAMILY_MONO}", "Courier New", monospace;
    font-size: 9pt;
    padding: 6px;
    selection-background-color: {C_ACCENT};
}}

/* ===================================================================
   SCROLL BARS
=================================================================== */

QScrollBar:vertical {{
    background-color: {C_BG_PANEL};
    width: 8px;
    margin: 0;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background-color: {C_BORDER};
    border-radius: 4px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {C_TEXT_MUTED};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: {C_BG_PANEL};
    height: 8px;
    margin: 0;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background-color: {C_BORDER};
    border-radius: 4px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {C_TEXT_MUTED};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ===================================================================
   SPLITTER
=================================================================== */

QSplitter::handle {{
    background-color: {C_BORDER};
}}

QSplitter::handle:horizontal {{
    width: 2px;
}}

QSplitter::handle:vertical {{
    height: 2px;
}}

/* ===================================================================
   STATUS BAR
=================================================================== */

QStatusBar {{
    background-color: {C_BG_DEEP};
    color: {C_TEXT_MUTED};
    border-top: 1px solid {C_BORDER};
    font-size: 8pt;
    padding: 2px 8px;
}}

/* ===================================================================
   TOOL TIP
=================================================================== */

QToolTip {{
    background-color: {C_BG_CARD};
    color: {C_TEXT};
    border: 1px solid {C_ACCENT};
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 9pt;
}}

/* ===================================================================
   MESSAGE BOX
=================================================================== */

QMessageBox {{
    background-color: {C_BG_PANEL};
    color: {C_TEXT};
}}

QMessageBox QLabel {{
    color: {C_TEXT};
    font-size: {FONT_SIZE_BASE}pt;
}}

QMessageBox QPushButton {{
    min-width: 80px;
    padding: 6px 20px;
}}

"""

# --------------------------------------------------------------------------
# Per-widget inline style helpers — used by individual widgets
# so they stay consistent even if a widget overrides the stylesheet.
# --------------------------------------------------------------------------

def primary_button_style(color: str = C_ACCENT) -> str:
    """Return inline style for a primary action button."""
    return (
        f"QPushButton {{"
        f"  background-color: {color};"
        f"  color: #ffffff;"
        f"  border: none;"
        f"  border-radius: 5px;"
        f"  padding: 8px 20px;"
        f"  font-weight: 700;"
        f"  font-size: 9pt;"
        f"  letter-spacing: 0.3px;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background-color: #6AB4FF;"
        f"}}"
        f"QPushButton:pressed {{"
        f"  background-color: #2E74CC;"
        f"}}"
        f"QPushButton:disabled {{"
        f"  background-color: {C_BG_INPUT};"
        f"  color: {C_TEXT_MUTED};"
        f"}}"
    )


def instruction_banner_style() -> str:
    """Return inline style for the instruction banner QLabel."""
    return (
        f"QLabel {{"
        f"  background-color: #151B2E;"
        f"  color: {C_TEXT2};"
        f"  border: 1px solid {C_ACCENT};"
        f"  border-left: 4px solid {C_ACCENT2};"
        f"  border-radius: 6px;"
        f"  padding: 10px 14px;"
        f"  font-size: 9pt;"
        f"  line-height: 1.5;"
        f"}}"
    )


def step_title_font(size: int = 13) -> str:
    """Return stylesheet fragment for step title labels."""
    return (
        f"QLabel {{"
        f"  color: {C_TEXT};"
        f"  font-size: {size}pt;"
        f"  font-weight: 700;"
        f"  letter-spacing: 0.5px;"
        f"}}"
    )
