from unittest.mock import MagicMock, patch

import pytest

from github_org_sync.i18n import _t
from github_org_sync.services.diagnostics_service import DiagnosticsService
from github_org_sync.ui.diagnostics_dialog import DiagnosticsDialog


@pytest.mark.unit
def test_diagnostics_service_all_success() -> None:
    def fake_run_process(args, **kwargs):
        mock_res = MagicMock()
        if args[0] == "git":
            mock_res.stdout = "git version 2.40.1.windows.1\n"
        elif args[0] == "gh" and args[1] == "--version":
            mock_res.stdout = "gh version 2.29.0 (2023-05-18)\n"
        elif args[0] == "gh" and args[1] == "auth" and args[2] == "status":
            mock_res.stdout = "Logged in to github.com as subactor"
            mock_res.stderr = ""
        elif args[0] == "ssh":
            mock_res.stdout = ""
            mock_res.stderr = (
                "Hi subactor! You've successfully authenticated, but GitHub does not provide shell access."
            )
        return mock_res

    with patch("github_org_sync.services.diagnostics_service.run_process", side_effect=fake_run_process):
        results = DiagnosticsService.run_all_checks()
        assert len(results) == 4
        assert all(r.success for r in results)
        assert results[0].message == "git version 2.40.1.windows.1"
        assert results[1].message == "gh version 2.29.0 (2023-05-18)"
        assert "subactor" in results[3].message


@pytest.mark.unit
def test_diagnostics_service_all_failure() -> None:
    def fake_run_process(args, **kwargs):
        raise RuntimeError("Command failed")

    with patch("github_org_sync.services.diagnostics_service.run_process", side_effect=fake_run_process):
        results = DiagnosticsService.run_all_checks()
        assert len(results) == 4
        assert not any(r.success for r in results)


@pytest.mark.gui
def test_diagnostics_dialog_ui(qtbot) -> None:
    from github_org_sync.services.diagnostics_service import DiagnosticsResult

    fake_results = [
        DiagnosticsResult("git", "Git Check", True, "Git version OK"),
        DiagnosticsResult("gh", "GH Check", False, "GH CLI is missing"),
    ]

    with patch.object(DiagnosticsService, "run_all_checks", return_value=fake_results):
        dialog = DiagnosticsDialog()
        qtbot.addWidget(dialog)

        # Assert table counts
        assert dialog.table.rowCount() == 2
        assert dialog.table.item(0, 0).text() == "Git Check"
        assert _t("diagnostics_status_success") in dialog.table.item(0, 1).text()
        assert dialog.table.item(1, 0).text() == "GH Check"
        assert _t("diagnostics_status_fail") in dialog.table.item(1, 1).text()

        # Select first row, check details text
        dialog.table.selectRow(0)
        assert dialog.details_box.toPlainText() == "Git version OK"

        # Select second row, check details text
        dialog.table.selectRow(1)
        assert dialog.details_box.toPlainText() == "GH CLI is missing"
