# -*- coding: utf-8 -*-
"""
Spectral Analysis Software - Main Application Entry Point

This is the main entry point for the application.
Run this file to launch the software.
"""

from src.logger import setup_logger

logger = setup_logger(__name__)


def main():
    """Main application entry point."""
    logger.info("Starting Spectral Analysis Software")
    print("Spectral Analysis Software v1.0.0")
    print("Ready for Phase 1 foundation setup complete!")


if __name__ == "__main__":
    main()
