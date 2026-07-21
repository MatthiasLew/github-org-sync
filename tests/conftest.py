from collections.abc import Generator
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def prevent_dialog_hangs() -> Generator[None, None, None]:
    try:
        from PySide6.QtWidgets import QMessageBox
    except ImportError:
        yield
        return

    with (
        patch(
            "PySide6.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ),
        patch(
            "PySide6.QtWidgets.QMessageBox.warning",
            return_value=QMessageBox.StandardButton.Ok,
        ),
        patch(
            "PySide6.QtWidgets.QMessageBox.information",
            return_value=QMessageBox.StandardButton.Ok,
        ),
        patch(
            "PySide6.QtWidgets.QMessageBox.critical",
            return_value=QMessageBox.StandardButton.Ok,
        ),
    ):
        yield
