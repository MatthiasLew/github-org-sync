import sys
import traceback
from pathlib import Path
from types import TracebackType

from PySide6.QtWidgets import QApplication

from github_org_sync.ui.main_window import MainWindow


def handle_exception(exctype: type[BaseException], value: BaseException, tb: TracebackType | None) -> None:
    # Do not intercept exceptions if running inside pytest or smoke test
    if "pytest" in sys.modules or "--smoke-test" in sys.argv:
        sys.__excepthook__(exctype, value, tb)
        return

    # Print to stderr
    sys.__excepthook__(exctype, value, tb)

    # Spawn crash report dialog only if QApplication instance exists
    if QApplication.instance():
        try:
            from github_org_sync.ui.crash_dialog import CrashReportDialog

            tb_lines = traceback.format_exception(exctype, value, tb)
            tb_text = "".join(tb_lines)

            dialog = CrashReportDialog(exctype.__name__, str(value), tb_text)
            dialog.exec()
        except Exception as e:
            print(f"Failed to show crash report dialog: {e}", file=sys.stderr)


# Register global exception handler
sys.excepthook = handle_exception


def setup_logging(app_data_dir: Path | None = None) -> None:
    import logging
    from logging.handlers import RotatingFileHandler

    from github_org_sync.services.report_service import ReportService

    # Skip actual file logging in tests unless a custom directory is specified
    if "pytest" in sys.modules and app_data_dir is None:
        return

    try:
        app_dir = app_data_dir or ReportService.get_app_data_dir()
        log_dir = app_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.log"

        handler = RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)

        logging.info("Persistent file logging initialized.")
    except Exception as e:
        print(f"Failed to initialize file logging: {e}", file=sys.stderr)


def main() -> None:
    setup_logging()

    if "--smoke-test" in sys.argv:
        # Prevent showing GUI dialogs
        app = QApplication(sys.argv)
        try:
            window = MainWindow()
            # Verify UI title
            title = window.windowTitle()
            if not title:
                raise ValueError("MainWindow title is empty")

            # Verify crucial widgets exist
            widgets = ["org_input", "table", "btn_sync", "btn_load", "search_input", "status_filter_cb"]
            for widget_name in widgets:
                widget = getattr(window, widget_name, None)
                if widget is None:
                    raise ValueError(f"Widget '{widget_name}' was not loaded or is missing in MainWindow")

            # Verify basic translations loaded
            from github_org_sync.i18n import _t

            sample_trans = _t("menu_settings")
            if not sample_trans or sample_trans == "menu_settings":
                raise ValueError("Translations failed to load or fallback key returned")

            # Verify window icon is set
            icon = window.windowIcon()
            if icon.isNull():
                raise ValueError("MainWindow icon was not loaded or is null")

            print("Smoke test passed successfully!")
            sys.exit(0)
        except Exception as e:
            print(f"Smoke test failed: {e}", file=sys.stderr)
            sys.exit(1)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
