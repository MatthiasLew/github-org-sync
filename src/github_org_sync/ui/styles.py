def get_stylesheet() -> str:
    return """
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
            background-color: qlineargradradient(
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
            image: url(icons/check.png); /* Fallback */
        }
    """
