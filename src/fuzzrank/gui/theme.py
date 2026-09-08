"""Restrained native-widget palette; no web rendering engine."""

from PySide6.QtGui import QColor, QPalette


def apply(app, dark=True):
    app.setStyle("Fusion")
    palette = QPalette()
    colors = {
        "Window": "#151c26" if dark else "#f1f4f8",
        "WindowText": "#e0e7f0" if dark else "#1b2738",
        "Base": "#111822" if dark else "#ffffff",
        "AlternateBase": "#18222f" if dark else "#f4f6fa",
        "Text": "#e0e7f0" if dark else "#1b2738",
        "Button": "#243143" if dark else "#e3e9f1",
        "ButtonText": "#e0e7f0" if dark else "#1b2738",
        "Highlight": "#345b85" if dark else "#c7def5",
        "HighlightedText": "#ffffff" if dark else "#122d49",
        "ToolTipBase": "#243143" if dark else "#ffffff",
        "ToolTipText": "#e0e7f0" if dark else "#1b2738",
        "PlaceholderText": "#95a6bc" if dark else "#56667a",
    }
    for name, color in colors.items():
        palette.setColor(getattr(QPalette.ColorRole, name), QColor(color))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor("#8491a3" if dark else "#697788"),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor("#8491a3" if dark else "#697788"),
    )
    app.setPalette(palette)
    border = "#344255" if dark else "#c6d0df"
    app.setStyleSheet(f"""
QWidget {{ font-size: 13px; }}
QToolBar {{ spacing: 8px; padding: 4px; border-bottom: 1px solid {border}; }}
QPushButton {{ padding: 5px 12px; border: 1px solid {border}; border-radius: 4px; }}
QPushButton:hover {{ border-color: #7398c4; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ padding: 3px; min-height: 20px; }}
QHeaderView::section {{ padding: 4px; border: none; border-bottom: 1px solid {border}; }}
QTableView {{ gridline-color: {border};
background-color: {"#111822" if dark else "#ffffff"};
alternate-background-color: {"#18222f" if dark else "#f4f6fa"};
selection-background-color: {"#345b85" if dark else "#c7def5"};
selection-color: {"#ffffff" if dark else "#122d49"}; }}
QTableView::item {{ padding: 0 5px; }}
QListWidget#navigation {{ border: none; background: transparent; }}
QListWidget#navigation::item {{ padding: 13px 12px; margin: 2px 4px; border-radius: 4px; }}
QListWidget#navigation::item:selected {{ background: {"#293d56" if dark else "#c7def5"}; }}
QLabel#brand {{ font-size: 22px; font-weight: 700; }}
QLabel#heading {{ font-size: 20px; font-weight: 600; padding: 2px 0; }}
QLabel#subtitle {{ color: {"#a9b8cb" if dark else "#52667d"}; }}
QFrame#metric {{ border: 1px solid {border}; border-radius: 5px; }}
QLabel#metricValue {{ font-size: 27px; font-weight: 600; border: none; }}
QLabel#metricLabel {{ border: none; color: {"#a9b8cb" if dark else "#52667d"}; }}
QSplitter::handle {{ background: {border}; }}
QTabBar::tab {{ padding: 5px 14px; border: 1px solid {border}; }}
QTabBar::tab:selected {{ background: {"#243143" if dark else "#dce7f4"}; }}
QProgressBar {{ max-height: 7px; border: none; }}
QProgressBar::chunk {{ background: #678db9; }}
""")
