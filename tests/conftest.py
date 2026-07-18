from collections.abc import Generator
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QMessageBox


@pytest.fixture(autouse=True)
def prevent_dialog_hangs() -> Generator[None, None, None]:
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
    ):
        yield
