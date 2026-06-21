# -*- coding: utf-8 -*-
"""
Main Application Window - Spectral Analysis Software

PyQt6 desktop application with tabbed interface for 3-step analysis pipeline.
"""

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStatusBar, QSplitter, QApplication
)
from PyQt6.QtGui import QFont, QIcon

from src import setup_logger
from src.gui.step1_widget import Step1Widget
from src.gui.step2_widget import Step2Widget
from src.gui.step3_widget import Step3Widget

logger = setup_logger(__name__)


class SpectralAnalysisApp(QMainWindow):
    """
    Main application window for Spectral Analysis Software.
    
    Features:
    - 3 tabbed interface for analysis steps
    - Parameter tuning for each step
    - Live visualization of results
    - Results tables with sorting/filtering
    """
    
    def __init__(self):
        """Initialize main application window."""
        super().__init__()
        
        # Window properties
        self.setWindowTitle("Spectral Analysis Software v1.0")
        self.setGeometry(100, 100, 1400, 900)
        
        logger.info("Starting Spectral Analysis Software GUI")
        
        # Create tab widget
        self.tabs = QTabWidget()
        
        # Create tabs for each step
        self.step1_tab = Step1Widget()
        self.step2_tab = Step2Widget()
        self.step3_tab = Step3Widget()
        
        # Add tabs
        self.tabs.addTab(self.step1_tab, "Step 1: Baseline Correction")
        self.tabs.addTab(self.step2_tab, "Step 2: Peak Detection")
        self.tabs.addTab(self.step3_tab, "Step 3: Element Identification")
        
        # Set central widget
        self.setCentralWidget(self.tabs)
        
        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")
        
        # Connect tab changes for logging
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
        logger.info("GUI initialization complete")
    
    def _on_tab_changed(self, index: int):
        """Handle tab change."""
        tab_names = [
            "Step 1: Baseline Correction",
            "Step 2: Peak Detection",
            "Step 3: Element Identification"
        ]
        logger.info(f"Switched to: {tab_names[index]}")
        self.statusBar.showMessage(f"Tab: {tab_names[index]}")


def main():
    """Launch application."""
    app = QApplication(sys.argv)
    
    # Set application font
    font = QFont()
    font.setPointSize(10)
    app.setFont(font)
    
    # Create main window
    window = SpectralAnalysisApp()
    window.show()
    
    logger.info("Application window displayed")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
