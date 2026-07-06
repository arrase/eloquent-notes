"""Stylesheets for Eloquent Notes configuration GUI."""

QSS_STYLESHEET = """
    QDialog {
        background-color: #1e1e2e;
        color: #cdd6f4;
    }
    QWidget {
        background-color: #1e1e2e;
        color: #cdd6f4;
        font-family: 'Segoe UI', 'Ubuntu', sans-serif;
        font-size: 13px;
    }
    QTabWidget::pane {
        border: 1px solid #313244;
        background-color: #181825;
        border-radius: 8px;
    }
    QTabBar::tab {
        background-color: #1e1e2e;
        color: #a6adc8;
        border: 1px solid #313244;
        border-bottom-color: transparent;
        padding: 10px 16px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        margin-right: 4px;
    }
    QTabBar::tab:selected {
        background-color: #181825;
        color: #89b4fa;
        font-weight: bold;
        border-bottom-color: #181825;
    }
    QTabBar::tab:hover:not(:selected) {
        background-color: #313244;
        color: #cdd6f4;
    }
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QListWidget {
        background-color: #181825;
        border: 1px solid #313244;
        border-radius: 6px;
        padding: 6px 10px;
        color: #cdd6f4;
    }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus {
        border: 1px solid #89b4fa;
    }
    QComboBox::drop-down {
        border: 0px;
    }
    QListWidget::item {
        padding: 8px;
        border-radius: 4px;
    }
    QListWidget::item:selected {
        background-color: #89b4fa;
        color: #11111b;
        font-weight: bold;
    }
    QListWidget::item:hover:not(:selected) {
        background-color: #313244;
    }
    QPushButton {
        background-color: #313244;
        border: 1px solid #45475a;
        border-radius: 6px;
        padding: 8px 16px;
        color: #cdd6f4;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #45475a;
    }
    QPushButton:pressed {
        background-color: #585b70;
    }
    QPushButton#btnSave {
        background-color: #89b4fa;
        color: #11111b;
        border: 1px solid #89b4fa;
    }
    QPushButton#btnSave:hover {
        background-color: #b4befe;
    }
    QGroupBox {
        border: 1px solid #313244;
        border-radius: 8px;
        margin-top: 16px;
        padding-top: 16px;
        font-weight: bold;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 0 6px;
        color: #89b4fa;
    }
    QCheckBox {
        spacing: 8px;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border: 1px solid #45475a;
        background-color: #181825;
        border-radius: 4px;
    }
    QCheckBox::indicator:checked {
        background-color: #89b4fa;
        border-color: #89b4fa;
    }
    QScrollBar:vertical {
        border: none;
        background: #181825;
        width: 10px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #313244;
        min-height: 20px;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical:hover {
        background: #45475a;
    }
"""
