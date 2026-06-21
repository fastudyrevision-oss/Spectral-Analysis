# -*- coding: utf-8 -*-
"""
GUI Launcher - Start the Spectral Analysis Software GUI

Run this script to launch the PyQt6 desktop application.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.gui.main_window import main

if __name__ == "__main__":
    main()
