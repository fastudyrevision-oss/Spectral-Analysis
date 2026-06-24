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
from src.gui.gui_utils import NotesPanel, FileHistory
from src.gui.theme import APP_STYLESHEET, FONT_FAMILY_UI, FONT_SIZE_BASE

logger = setup_logger(__name__)


class SpectralAnalysisApp(QMainWindow):
    """
    Main application window for Spectral Analysis Software.
    
    Features:
    - 5 tabbed interface for complete analysis pipeline
    - Parameter tuning for each step
    - Live visualization of results
    - Results tables with sorting/filtering
    """
    
    def __init__(self):
        """Initialize main application window."""
        super().__init__()
        
        # Window properties
        self.setWindowTitle("Spectral Analysis Software  |  5-Step LIBS Pipeline")
        self.setGeometry(100, 100, 1440, 900)
        
        logger.info("Starting Spectral Analysis Software GUI")
        
        # Create global file history and notes panel
        self.file_history = FileHistory(max_items=15)
        self.notes_panel = NotesPanel(max_lines=100)
        
        # Create tab widget
        self.tabs = QTabWidget()
        
        # Create tabs for each step
        self.step1_tab = Step1Widget(file_history=self.file_history, notes_panel=self.notes_panel)
        self.step2_tab = Step2Widget(file_history=self.file_history, notes_panel=self.notes_panel)
        self.step3_tab = Step3Widget(file_history=self.file_history, notes_panel=self.notes_panel)
        self.step4_tab = Step4Widget(file_history=self.file_history, notes_panel=self.notes_panel)
        self.step5_tab = Step5Widget(file_history=self.file_history, notes_panel=self.notes_panel)
        
        # Add tabs
        self.tabs.addTab(self.step1_tab, "Step 1: Baseline Correction")
        self.tabs.addTab(self.step2_tab, "Step 2: Peak Detection")
        self.tabs.addTab(self.step3_tab, "Step 3: Element Identification")
        self.tabs.addTab(self.step4_tab, "Step 4: Elemental Preferences")
        self.tabs.addTab(self.step5_tab, "Step 5: Validation")
        
        # Create central widget with tabs and notes panel
        from PyQt6.QtWidgets import QWidget, QVBoxLayout
        central_widget = QWidget()
        central_layout = QVBoxLayout()
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        
        central_layout.addWidget(self.tabs, stretch=3)
        central_layout.addWidget(self.notes_panel, stretch=1)
        
        central_widget.setLayout(central_layout)
        self.setCentralWidget(central_widget)
        
        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")
        
        # Connect tab changes for logging
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
        # Add initial note
        self.notes_panel.add_note("Application started", "INFO")
        
        logger.info("GUI initialization complete")
    
    def _on_tab_changed(self, index: int):
        """Handle tab change."""
        tab_names = [
            "Step 1: Baseline Correction",
            "Step 2: Peak Detection",
            "Step 3: Element Identification",
            "Step 4: Elemental Preferences",
            "Step 5: Validation"
        ]
        if index < len(tab_names):
            logger.info(f"Switched to: {tab_names[index]}")
            self.statusBar.showMessage(f"Tab: {tab_names[index]}")


def main():
    """Launch application."""
    app = QApplication(sys.argv)

    # Apply global dark theme stylesheet
    app.setStyleSheet(APP_STYLESHEET)

    # Set application font — prefer Segoe UI, fall back gracefully
    font = QFont(FONT_FAMILY_UI)
    font.setPointSize(FONT_SIZE_BASE)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(font)

    # Create main window
    window = SpectralAnalysisApp()
    window.show()

    logger.info("Application window displayed")
    sys.exit(app.exec())



if __name__ == "__main__":
    main()
