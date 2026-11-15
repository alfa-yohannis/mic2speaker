"""Fixtures shared by all tests."""

import os

import pytest
from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qt_application() -> QApplication:
    """Create the one QApplication that every Qt test shares.

    The tests run without a screen, so Qt is told to draw offscreen.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application
