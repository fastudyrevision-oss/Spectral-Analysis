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
from src.gui.summary_widget import SummaryWidget
from src.gui.gui_utils import NotesPanel, FileHistory
from src.gui.theme import APP_STYLESHEET, FONT_FAMILY_UI, FONT_SIZE_BASE

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
        self.tabs.addTab(self.summary_tab, "📊 Analysis Summary")

        central_widget = QWidget()
        central_layout = QVBoxLayout()
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        central_layout.addWidget(self.tabs, stretch=3)
        central_layout.addWidget(self.notes_panel, stretch=1)

        central_widget.setLayout(central_layout)
        self.setCentralWidget(central_widget)

        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.notes_panel.add_note("Application started", "INFO")

        logger.info("GUI initialization complete")

    def _on_tab_changed(self, index: int):
        """Refresh summary dashboard when its tab is activated."""
        tab_names = [
            "① Step 1: Baseline Correction",
            "② Step 2: Peak Detection",
            "③ Step 3: Element Identification",
            "④ Step 4: Elemental Preferences",
            "⑤ Step 5: Validation",
            "📊 Analysis Summary",
        ]
        if index < len(tab_names):
            logger.info(f"Switched to: {tab_names[index]}")
            self.statusBar.showMessage(f"Tab: {tab_names[index]}")

        # Refresh summary dashboard whenever user navigates to it
        if index == 5:
            self.summary_tab.refresh()


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
