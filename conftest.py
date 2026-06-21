# -*- coding: utf-8 -*-
"""
Root Conftest - Pytest Fixtures for Root-level Tests

Provides QApplication fixture for GUI tests.
"""

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for GUI tests (session-scoped)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(scope="function")
def app(qapp):
    """Provide QApplication instance for each test (function-scoped)."""
    yield qapp
