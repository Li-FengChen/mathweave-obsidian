"""A quiet editorial workspace with indigo and teal accents."""
STYLE = """
QWidget { font-family:'Microsoft YaHei','Segoe UI'; font-size:13px; color:#343d54; }
QMainWindow, QDialog { background:#f2f3f9; }
QWidget#workspace { background:#f2f3f9; }
QFrame#card { background:white; border:1px solid #e6e9f2; border-radius:14px; }
QFrame#header { background:transparent; }
QLabel#brand { font-size:24px; font-weight:700; color:#222943; }
QLabel#subtitle, QLabel#muted { color:#8891a8; font-size:12px; }
QLabel#section { font-size:15px; font-weight:700; color:#3a425d; }
QLabel#number { color:#9992d4; font-size:11px; font-weight:700; letter-spacing:2px; }
QLabel#pill { background:#e8f5f0; color:#458f7a; padding:7px 12px; border-radius:12px; font-size:11px; }
QLabel#summary { color:#778199; font-size:12px; }
QPushButton { background:#fff; border:1px solid #e1e4ef; border-radius:8px; padding:8px 13px; color:#626b84; }
QPushButton:hover { border-color:#b1a9df; background:#f5f3fc; color:#554ba9; }
QPushButton:pressed { background:#eae6f7; }
QPushButton:disabled { color:#b3bac9; background:#f4f5f8; border-color:#ecedf3; }
QPushButton#primary { background:#665acb; color:white; border:0; padding:12px 18px; font-weight:600; }
QPushButton#primary:hover { background:#786bdc; }
QPushButton#primary:disabled { background:#d0cce9; }
QPushButton#save { background:#237f72; color:white; border:0; padding:11px 18px; font-weight:600; }
QPushButton#save:hover { background:#329889; }
QPushButton#save:disabled { background:#c4d8d2; }
QPushButton#quiet { border:0; background:transparent; color:#8475c5; padding:4px; }
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox { background:white; border:1px solid #dde1ee; border-radius:7px; padding:7px; selection-background-color:#e6e1fa; }
QPlainTextEdit { background:#fbfbfe; border:1px solid #e6e8f1; border-radius:9px; padding:11px; selection-background-color:#e2ddf8; }
QPlainTextEdit:focus { border-color:#ada2df; }
QListWidget { background:white; border:0; outline:0; padding:3px; }
QListWidget::item { padding:13px 7px; margin:3px 0; border-radius:9px; color:#5d6781; }
QListWidget::item:selected { background:#eeebfa; color:#574ba9; }
QListWidget::item:hover { background:#f6f4fc; }
QCheckBox { spacing:7px; color:#818aa0; }
QTabWidget::pane { background:white; border:0; }
QTabBar::tab { background:transparent; color:#9097a9; border-bottom:2px solid transparent; padding:10px 15px; }
QTabBar::tab:selected { color:#6556b8; border-bottom:2px solid #8d7de0; }
QTabBar::tab:hover { color:#6556b8; }
QProgressBar { border:0; background:#ece9f8; border-radius:3px; height:5px; max-height:5px; }
QProgressBar::chunk { background:#9b8edb; border-radius:3px; }
QSplitter::handle { background:transparent; width:12px; }
QScrollBar:vertical { background:transparent; width:8px; margin:0; }
QScrollBar::handle:vertical { background:#d7dbea; border-radius:4px; min-height:24px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QStatusBar { color:#939ab0; background:transparent; }
QMenuBar { background:#f2f3f9; color:#717a93; }
QMenu { background:white; border:1px solid #e3e5ef; padding:5px; }
QMenu::item { padding:8px 22px; }
QMenu::item:selected { background:#efecfa; }
QToolTip { background:#2f3550; color:white; border:0; padding:6px; }
"""
