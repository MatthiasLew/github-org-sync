import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

DARK_STYLESHEET = """
    /* Main Window Theme */
    QMainWindow {
        background-color: #0f172a; /* Slate 900 */
        color: #f8fafc; /* Slate 50 */
        font-family: "Segoe UI", "Segoe UI Semibold", "Inter", sans-serif;
        font-size: 13px;
    }

    /* Labels */
    QLabel {
        color: #cbd5e1; /* Slate 300 */
        font-weight: 500;
    }

    QLabel#headerTitle {
        color: #ffffff;
        font-size: 18px;
        font-weight: bold;
    }

    /* Buttons */
    QPushButton {
        background-color: #3b82f6; /* Blue 500 */
        color: #ffffff;
        border: none;
        border-radius: 6px;
        padding: 8px 16px;
        font-weight: 600;
    }

    QPushButton:hover {
        background-color: #2563eb; /* Blue 600 */
    }

    QPushButton:pressed {
        background-color: #1d4ed8; /* Blue 700 */
    }

    QPushButton:disabled {
        background-color: #334155; /* Slate 700 */
        color: #64748b; /* Slate 500 */
    }

    QPushButton#btnAction {
        background-color: #8b5cf6; /* Violet 500 */
    }

    QPushButton#btnAction:hover {
        background-color: #7c3aed; /* Violet 600 */
    }

    QPushButton#btnCancel {
        background-color: #ef4444; /* Red 500 */
    }

    QPushButton#btnCancel:hover {
        background-color: #dc2626; /* Red 600 */
    }

    QPushButton#btnOutline {
        background-color: transparent;
        border: 1.5px solid #475569; /* Slate 600 */
        color: #cbd5e1;
    }

    QPushButton#btnOutline:hover {
        background-color: #1e293b; /* Slate 800 */
        border-color: #64748b;
    }

    /* Text Input Fields */
    QLineEdit {
        background-color: #1e293b; /* Slate 800 */
        color: #ffffff;
        border: 1px solid #334155; /* Slate 700 */
        border-radius: 6px;
        padding: 6px 12px;
        selection-background-color: #3b82f6;
    }

    QLineEdit:focus {
        border: 1.5px solid #3b82f6; /* Blue 500 focus ring */
    }

    /* Combo Boxes */
    QComboBox {
        background-color: #1e293b;
        color: #ffffff;
        border: 1px solid #334155;
        border-radius: 6px;
        padding: 6px 12px;
    }

    QComboBox::drop-down {
        border: none;
        width: 20px;
    }

    QComboBox QAbstractItemView {
        background-color: #1e293b;
        color: #ffffff;
        selection-background-color: #3b82f6;
    }

    /* Table View */
    QTableWidget {
        background-color: #1e293b;
        color: #f8fafc;
        gridline-color: #334155;
        border: 1px solid #334155;
        border-radius: 8px;
        selection-background-color: #334155;
        selection-color: #3b82f6;
    }

    QHeaderView::section {
        background-color: #0f172a;
        color: #94a3b8; /* Slate 400 */
        padding: 8px;
        font-weight: 600;
        border: none;
        border-bottom: 2px solid #334155;
    }

    QTableWidget::item {
        padding: 6px;
    }

    QTableWidget::item:selected {
        background-color: #1e293b;
        color: #60a5fa; /* Blue 400 selection text */
    }

    /* Scroll Bar Styling */
    QScrollBar:vertical {
        border: none;
        background: #0f172a;
        width: 10px;
        margin: 0px;
    }

    QScrollBar::handle:vertical {
        background: #475569;
        min-height: 20px;
        border-radius: 5px;
    }

    QScrollBar::handle:vertical:hover {
        background: #64748b;
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        border: none;
        background: none;
    }

    QScrollBar:horizontal {
        border: none;
        background: #0f172a;
        height: 10px;
        margin: 0px;
    }

    QScrollBar::handle:horizontal {
        background: #475569;
        min-width: 20px;
        border-radius: 5px;
    }

    /* Progress Bar */
    QProgressBar {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 6px;
        text-align: center;
        color: #ffffff;
        font-weight: 600;
    }

    QProgressBar::chunk {
        background-color: qlineargradient(
            spread:pad, x1:0, y1:0, x2:1, y2:0,
            stop:0 #3b82f6, stop:1 #8b5cf6
        ); /* Nice Blue to Violet gradient */
        border-radius: 5px;
    }

    /* Text Log Box (Console) */
    QTextEdit#consoleLog {
        background-color: #020617; /* Darkest Slate 950 */
        color: #38bdf8; /* Sky 400 console text */
        font-family: "Consolas", "Courier New", monospace;
        font-size: 12px;
        border: 1px solid #1e293b;
        border-radius: 6px;
        padding: 8px;
    }

    /* Checkbox Styling */
    QCheckBox {
        color: #cbd5e1;
        spacing: 8px;
    }

    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border: 1.5px solid #475569;
        border-radius: 4px;
        background-color: #1e293b;
    }

    QCheckBox::indicator:hover {
        border-color: #64748b;
    }

    QCheckBox::indicator:checked {
        border-color: #3b82f6;
        background-color: #3b82f6;
    }
"""

LIGHT_STYLESHEET = """
    /* Main Window Theme */
    QMainWindow {
        background-color: #f8fafc; /* Slate 50 */
        color: #0f172a; /* Slate 900 */
        font-family: "Segoe UI", "Segoe UI Semibold", "Inter", sans-serif;
        font-size: 13px;
    }

    /* Labels */
    QLabel {
        color: #475569; /* Slate 600 */
        font-weight: 500;
    }

    QLabel#headerTitle {
        color: #0f172a;
        font-size: 18px;
        font-weight: bold;
    }

    /* Buttons */
    QPushButton {
        background-color: #3b82f6; /* Blue 500 */
        color: #ffffff;
        border: none;
        border-radius: 6px;
        padding: 8px 16px;
        font-weight: 600;
    }

    QPushButton:hover {
        background-color: #2563eb; /* Blue 600 */
    }

    QPushButton:pressed {
        background-color: #1d4ed8; /* Blue 700 */
    }

    QPushButton:disabled {
        background-color: #e2e8f0; /* Slate 200 */
        color: #94a3b8; /* Slate 400 */
    }

    QPushButton#btnAction {
        background-color: #8b5cf6; /* Violet 500 */
    }

    QPushButton#btnAction:hover {
        background-color: #7c3aed; /* Violet 600 */
    }

    QPushButton#btnCancel {
        background-color: #ef4444; /* Red 500 */
    }

    QPushButton#btnCancel:hover {
        background-color: #dc2626; /* Red 600 */
    }

    QPushButton#btnOutline {
        background-color: transparent;
        border: 1.5px solid #cbd5e1; /* Slate 200 */
        color: #475569;
    }

    QPushButton#btnOutline:hover {
        background-color: #f1f5f9; /* Slate 100 */
        border-color: #94a3b8;
    }

    /* Text Input Fields */
    QLineEdit {
        background-color: #ffffff;
        color: #0f172a;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 6px 12px;
        selection-background-color: #3b82f6;
    }

    QLineEdit:focus {
        border: 1.5px solid #3b82f6;
    }

    /* Combo Boxes */
    QComboBox {
        background-color: #ffffff;
        color: #0f172a;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 6px 12px;
    }

    QComboBox::drop-down {
        border: none;
        width: 20px;
    }

    QComboBox QAbstractItemView {
        background-color: #ffffff;
        color: #0f172a;
        selection-background-color: #f1f5f9;
        selection-color: #0f172a;
    }

    /* Table View */
    QTableWidget {
        background-color: #ffffff;
        color: #0f172a;
        gridline-color: #e2e8f0;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        selection-background-color: #f1f5f9;
        selection-color: #3b82f6;
    }

    QHeaderView::section {
        background-color: #f1f5f9;
        color: #475569; /* Slate 600 */
        padding: 8px;
        font-weight: 600;
        border: none;
        border-bottom: 2px solid #cbd5e1;
    }

    QTableWidget::item {
        padding: 6px;
    }

    QTableWidget::item:selected {
        background-color: #f1f5f9;
        color: #2563eb;
    }

    /* Scroll Bar Styling */
    QScrollBar:vertical {
        border: none;
        background: #f8fafc;
        width: 10px;
        margin: 0px;
    }

    QScrollBar::handle:vertical {
        background: #cbd5e1;
        min-height: 20px;
        border-radius: 5px;
    }

    QScrollBar::handle:vertical:hover {
        background: #94a3b8;
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        border: none;
        background: none;
    }

    QScrollBar:horizontal {
        border: none;
        background: #f8fafc;
        height: 10px;
        margin: 0px;
    }

    QScrollBar::handle:horizontal {
        background: #cbd5e1;
        min-width: 20px;
        border-radius: 5px;
    }

    /* Progress Bar */
    QProgressBar {
        background-color: #e2e8f0;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        text-align: center;
        color: #0f172a;
        font-weight: 600;
    }

    QProgressBar::chunk {
        background-color: qlineargradient(
            spread:pad, x1:0, y1:0, x2:1, y2:0,
            stop:0 #3b82f6, stop:1 #8b5cf6
        );
        border-radius: 5px;
    }

    /* Text Log Box (Console) */
    QTextEdit#consoleLog {
        background-color: #f1f5f9; /* Slate 100 */
        color: #0369a1; /* Sky 700 console text */
        font-family: "Consolas", "Courier New", monospace;
        font-size: 12px;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 8px;
    }

    /* Checkbox Styling */
    QCheckBox {
        color: #475569;
        spacing: 8px;
    }

    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border: 1.5px solid #cbd5e1;
        border-radius: 4px;
        background-color: #ffffff;
    }

    QCheckBox::indicator:hover {
        border-color: #94a3b8;
    }

    QCheckBox::indicator:checked {
        border-color: #3b82f6;
        background-color: #3b82f6;
    }
"""


def is_system_dark() -> bool:
    """Detects if system settings are set to dark mode."""
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return scheme == Qt.ColorScheme.Dark
    except Exception:
        if sys.platform == "win32":
            try:
                import winreg

                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                )
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return bool(val == 0)
            except Exception:
                pass
        return True  # Fallback to dark theme


def get_stylesheet(theme_name: str) -> str:
    """Returns the CSS stylesheet for the specified theme."""
    name = theme_name.lower()
    if name == "dark" or name == "ciemny":
        return DARK_STYLESHEET
    if name == "light" or name == "jasny":
        return LIGHT_STYLESHEET

    # System theme fallback
    if is_system_dark():
        return DARK_STYLESHEET
    return LIGHT_STYLESHEET
