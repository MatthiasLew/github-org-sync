import sys
import urllib.parse
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from github_org_sync import __version__
from github_org_sync.i18n import _t
from github_org_sync.services.report_service import _scrub_secrets


def sanitize_error_text(text: str) -> str:
    """Redacts secrets and replaces the local user home directory to preserve privacy."""
    text = _scrub_secrets(text)
    try:
        home_path = str(Path.home())
        if home_path:
            # Replace backslashes and forward slashes to ensure both formats are sanitized
            text = text.replace(home_path, "[USER_HOME]")
            text = text.replace(home_path.replace("\\", "/"), "[USER_HOME]")
    except Exception:
        pass
    return text


class CrashReportDialog(QDialog):
    def __init__(self, error_type: str, error_msg: str, traceback_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.error_type = error_type
        self.error_msg = sanitize_error_text(error_msg)
        self.traceback_text = sanitize_error_text(traceback_text)

        self.setWindowTitle(_t("crash_title"))
        self.setMinimumSize(650, 450)
        self.resize(700, 500)

        # Remove help button from title bar
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header Section with Icon
        header_layout = QHBoxLayout()
        header_layout.setSpacing(15)

        # Critical Icon
        icon_label = QLabel()
        error_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical)
        icon_label.setPixmap(error_icon.pixmap(48, 48))
        header_layout.addWidget(icon_label)

        # Titles
        title_layout = QVBoxLayout()
        title_label = QLabel(_t("crash_header"))
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #d32f2f;")  # Danger red

        desc_label = QLabel(_t("crash_desc"))
        desc_label.setWordWrap(True)

        title_layout.addWidget(title_label)
        title_layout.addWidget(desc_label)
        header_layout.addLayout(title_layout, stretch=1)

        layout.addLayout(header_layout)

        # Traceback display
        self.trace_edit = QTextEdit()
        self.trace_edit.setReadOnly(True)
        self.trace_edit.setFont(QFont("Consolas", 9) if sys.platform == "win32" else QFont("Courier", 9))
        self.trace_edit.setStyleSheet(
            """
            QTextEdit {
                background-color: #f5f5f5;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 10px;
                color: #333333;
            }
        """
        )

        full_error_details = (
            f"Application Version: {__version__}\n"
            f"Platform: {sys.platform}\n"
            f"Python: {sys.version}\n\n"
            f"Error Type: {self.error_type}\n"
            f"Message: {self.error_msg}\n\n"
            f"Traceback:\n{self.traceback_text}"
        )
        self.trace_edit.setText(full_error_details)
        layout.addWidget(self.trace_edit)

        # Temporary clipboard notification label
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.status_label)

        # Actions Layout
        buttons_layout = QHBoxLayout()

        self.btn_copy = QPushButton(_t("btn_copy_traceback"))
        self.btn_copy.clicked.connect(self.copy_to_clipboard)
        buttons_layout.addWidget(self.btn_copy)

        self.btn_report = QPushButton(_t("btn_report_github"))
        self.btn_report.clicked.connect(self.report_on_github)
        self.btn_report.setStyleSheet(
            """
            QPushButton {
                background-color: #0066cc;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #0052a3;
            }
            QPushButton:pressed {
                background-color: #003d7a;
            }
        """
        )
        buttons_layout.addWidget(self.btn_report)

        buttons_layout.addStretch()

        self.btn_close = QPushButton(_t("no_remote_skip") if sys.platform == "win32" else "Close")
        self.btn_close.clicked.connect(self.reject)
        buttons_layout.addWidget(self.btn_close)

        layout.addLayout(buttons_layout)

    def copy_to_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.trace_edit.toPlainText())
            self.status_label.setText(_t("copied_to_clipboard"))

    def report_on_github(self) -> None:
        # Build issue template body
        body_template = (
            "### Describe the bug\n"
            "A clear and concise description of what the bug is.\n\n"
            "### To Reproduce\n"
            "Steps to reproduce the behavior:\n"
            "1. Go to '...'\n"
            "2. Click on '...'\n"
            "3. Scroll down to '...'\n"
            "4. See error\n\n"
            "### Error Details & Traceback\n"
            "```text\n"
            f"{self.trace_edit.toPlainText()}\n"
            "```"
        )

        title = f"Bug: {self.error_type} - {self.error_msg[:60]}"
        encoded_title = urllib.parse.quote(title)
        encoded_body = urllib.parse.quote(body_template)

        github_url = (
            f"https://github.com/MatthiasLew/github-org-sync/issues/new?title={encoded_title}&body={encoded_body}"
        )
        webbrowser.open(github_url)
