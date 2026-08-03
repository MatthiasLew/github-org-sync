from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QMessageBox

from github_org_sync.ui.repository_table import RepositoryTable


@pytest.mark.gui
def test_open_terminal_success(qtbot) -> None:
    table = RepositoryTable()
    qtbot.addWidget(table)

    with patch("github_org_sync.ui.repository_table.open_terminal") as mock_open:
        mock_open.return_value = True
        table._open_terminal(Path("/dummy/path"))
        mock_open.assert_called_once_with(Path("/dummy/path"))


@pytest.mark.gui
def test_open_terminal_failure(qtbot) -> None:
    table = RepositoryTable()
    qtbot.addWidget(table)

    with (
        patch("github_org_sync.ui.repository_table.open_terminal") as mock_open,
        patch.object(QMessageBox, "warning") as mock_warning,
    ):
        mock_open.return_value = False
        table._open_terminal(Path("/dummy/path"))
        mock_open.assert_called_once_with(Path("/dummy/path"))
        mock_warning.assert_called_once()
