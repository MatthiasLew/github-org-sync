import sys

from PySide6.QtWidgets import QApplication

from github_org_sync.ui.main_window import MainWindow


def main() -> None:
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
