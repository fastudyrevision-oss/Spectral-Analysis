# -*- coding: utf-8 -*-
"""
Main Application Window - Spectral Analysis Software

PyQt6 desktop application with tabbed interface for 5-step analysis pipeline.
"""

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStatusBar, QSplitter, QApplication
)
from PyQt6.QtGui import QFont, QIcon, QFontDatabase

from src import setup_logger
from src.gui.step1_widget import Step1Widget
from src.gui.step2_widget import Step2Widget
from src.gui.step3_widget import Step3Widget
from src.gui.step4_widget import Step4Widget
from src.gui.step5_widget import Step5Widget
from src.gui.step6_widget import Step6Widget
from src.gui.summary_widget import SummaryWidget
from src.gui.gui_utils import NotesPanel, FileHistory
from src.gui.theme import APP_STYLESHEET, LIGHT_STYLESHEET, FONT_FAMILY_UI, FONT_SIZE_BASE
import src.gui.theme as _theme_module

logger = setup_logger(__name__)


class SpectralAnalysisApp(QMainWindow):
    """
    Main application window for Spectral Analysis Software.

    Features:
    - 6-tab interface: 5 analysis steps + Analysis Summary dashboard
    - Parameter tuning for each step
    - Live visualization of results
    - Results tables with sorting/filtering
    """

    def __init__(self):
        """Initialize main application window."""
        super().__init__()

        self.setWindowTitle("Spectral Analysis Software  |  5-Step LIBS Pipeline")
        self.setGeometry(100, 100, 1440, 900)
        self._dark_mode = True   # start in dark mode

        logger.info("Starting Spectral Analysis Software GUI")

        self.file_history = FileHistory(max_items=15)
        self.notes_panel = NotesPanel(max_lines=100)

        self.tabs = QTabWidget()

        # Create step widgets
        self.step1_tab = Step1Widget(file_history=self.file_history, notes_panel=self.notes_panel)
        self.step2_tab = Step2Widget(file_history=self.file_history, notes_panel=self.notes_panel)
        self.step3_tab = Step3Widget(file_history=self.file_history, notes_panel=self.notes_panel)
        self.step4_tab = Step4Widget(file_history=self.file_history, notes_panel=self.notes_panel)
        self.step5_tab = Step5Widget(file_history=self.file_history, notes_panel=self.notes_panel)
        self.step6_tab = Step6Widget(
            step2_tab=self.step2_tab,
            step3_tab=self.step3_tab,
            step4_tab=self.step4_tab,
            step5_tab=self.step5_tab,
            step1_tab=self.step1_tab,
            file_history=self.file_history,
            notes_panel=self.notes_panel,
        )

        # Create summary dashboard (read-only, fed by step widgets)
        self.summary_tab = SummaryWidget(
            step1=self.step1_tab,
            step2=self.step2_tab,
            step3=self.step3_tab,
            step4=self.step4_tab,
            step5=self.step5_tab,
        )

        # Add tabs with Unicode-prefixed labels
        self.tabs.addTab(self.step1_tab, "① Step 1: Baseline Correction")
        self.tabs.addTab(self.step2_tab, "② Step 2: Peak Detection")
        self.tabs.addTab(self.step3_tab, "③ Step 3: Element Identification")
        self.tabs.addTab(self.step4_tab, "④ Step 4: Elemental Preferences")
        self.tabs.addTab(self.step5_tab, "⑤ Step 5: Validation")
        self.tabs.insertTab(5, self.step6_tab, "⑥ Step 6: Model Performance")
        self.tabs.addTab(self.summary_tab, "📊 Analysis Summary")

        central_widget = QWidget()
        central_layout = QVBoxLayout()
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        central_layout.addWidget(self.tabs, stretch=1)
        central_layout.addWidget(self.notes_panel, stretch=0)
        self.notes_panel.setMaximumHeight(26)   # collapsed height; expands on click

        central_widget.setLayout(central_layout)
        self.setCentralWidget(central_widget)

        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")

        # Theme toggle button — lives in the right corner of the status bar
        self._theme_btn = QPushButton("☀  Light Mode")
        self._theme_btn.setFixedHeight(22)
        self._theme_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #3A4055; "
            "border-radius: 4px; color: #AEB7C4; font-size: 8pt; padding: 0 10px; }"
            "QPushButton:hover { border-color: #3FA9F5; color: #3FA9F5; }"
        )
        self._theme_btn.clicked.connect(self._on_toggle_theme)
        self.statusBar.addPermanentWidget(self._theme_btn)

        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.notes_panel.add_note("Application started", "INFO")

        # Restore last session silently
        self._restore_session()

        logger.info("GUI initialization complete")

    def _restore_session(self) -> None:
        """Silently restore step results from the last session on startup."""
        try:
            from src.gui.session_manager import (
                load_step2, load_step3, load_step4, load_step5,
            )
            peaks = load_step2()
            if peaks:
                self.step2_tab.detected_peaks = peaks
                logger.info("Session restored: %d detected peaks (Step 2)", len(peaks))

            matches = load_step3()
            if matches:
                self.step3_tab.matches = matches
                logger.info("Session restored: %d NIST matches (Step 3)", len(matches))

            analysis = load_step4()
            if analysis:
                self.step4_tab.analysis_results = analysis
                logger.info("Session restored: Step 4 analysis results")

            validation = load_step5()
            if validation is not None:
                self.step5_tab.validation_results = validation
                logger.info(
                    "Session restored: %d validation rows (Step 5)", len(validation)
                )
        except Exception:
            logger.exception("Session restore failed — starting with clean state")

    def _on_toggle_theme(self):
        """Switch between dark and light application themes."""
        self._dark_mode = not self._dark_mode
        app = QApplication.instance()
        if self._dark_mode:
            _theme_module.set_theme("dark")
            app.setStyleSheet(APP_STYLESHEET)
            self._theme_btn.setText("☀  Light Mode")
            self.statusBar.showMessage("Theme: Dark")
            logger.info("Switched to dark theme")
        else:
            _theme_module.set_theme("light")
            app.setStyleSheet(LIGHT_STYLESHEET)
            self._theme_btn.setText("🌙  Dark Mode")
            self.statusBar.showMessage("Theme: Light")
            logger.info("Switched to light theme")
        # Propagate to all widgets that have inline styles or matplotlib canvases
        for widget in [self.step1_tab, self.step2_tab, self.step3_tab,
                       self.step4_tab, self.step5_tab, self.step6_tab, self.summary_tab]:
            if hasattr(widget, 'apply_theme'):
                widget.apply_theme()

    def _on_tab_changed(self, index: int):
        """Refresh summary dashboard when its tab is activated."""
        # ASCII-safe names for logging (console may be CP-1252)
        tab_names = [
            "Step 1: Baseline Correction",
            "Step 2: Peak Detection",
            "Step 3: Element Identification",
            "Step 4: Elemental Preferences",
            "Step 5: Validation",
            "Step 6: Model Performance",
            "Analysis Summary",
        ]
        if index < len(tab_names):
            logger.info(f"Switched to: {tab_names[index]}")
            self.statusBar.showMessage(f"Tab: {tab_names[index]}")

        if index == 5:
            self.step6_tab.refresh_if_not_cleared()
        elif index == 6:
            self.summary_tab.refresh_if_not_cleared()


def main():
    """Launch application."""
    app = QApplication(sys.argv)

    app.setStyleSheet(APP_STYLESHEET)

    font = QFont(FONT_FAMILY_UI)
    font.setPointSize(FONT_SIZE_BASE)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(font)

    window = SpectralAnalysisApp()
    window.show()

    logger.info("Application window displayed")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
