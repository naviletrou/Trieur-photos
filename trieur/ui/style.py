"""Apparence de l'application."""

ACCENT = "#1E5A8C"        # bleu marine
ACCENT_DARK = "#174872"
ACCENT_LIGHT = "#E6EFF7"
WARNING = "#C26A00"
WARNING_LIGHT = "#FFF3E0"
OK = "#2E7D4F"
TEXT = "#1F2933"
MUTED = "#5F6B7A"
BORDER = "#D9DEE5"
BACKGROUND = "#F4F6F8"
SIDEBAR = "#1D2B3A"

def _assets_dir() -> str:
    """Dossier des images de l'interface (coche…), écrit avec des « / » comme le veut Qt."""
    from ..exiftool import app_dir
    for base in (app_dir() / "assets", app_dir() / "_internal" / "assets"):
        if (base / "coche.svg").exists():
            return base.as_posix()
    return (app_dir() / "assets").as_posix()


ASSETS = _assets_dir()

STYLE = f"""
QWidget {{
    color: {TEXT};
    font-size: 10pt;
}}
QMainWindow, #content {{
    background: {BACKGROUND};
}}
#sidebar {{
    background: {SIDEBAR};
}}
#appTitle {{
    color: white;
    font-size: 15pt;
    font-weight: 600;
}}
#appSubtitle {{
    color: #9FB0C3;
    font-size: 9pt;
}}
QPushButton#step {{
    color: #C9D4E0;
    background: transparent;
    border: none;
    border-radius: 6px;
    text-align: left;
    padding: 10px 12px;
    font-size: 10.5pt;
}}
QPushButton#step:hover:enabled {{
    background: #26384B;
}}
QPushButton#step:checked {{
    color: white;
    background: {ACCENT};
    font-weight: 600;
}}
QPushButton#step:disabled {{
    color: #5D6E80;
}}
#pageTitle {{
    font-size: 17pt;
    font-weight: 600;
}}
#pageIntro {{
    color: {MUTED};
    font-size: 10.5pt;
}}
QFrame#card {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
#cardTitle {{
    font-size: 11pt;
    font-weight: 600;
}}
#hint {{
    color: {MUTED};
    font-size: 9pt;
}}
#example {{
    background: {ACCENT_LIGHT};
    border-radius: 6px;
    padding: 10px 12px;
    font-family: "Consolas", "DejaVu Sans Mono", monospace;
    font-size: 9.5pt;
}}
#warningBox {{
    background: {WARNING_LIGHT};
    border: 1px solid #F3C98B;
    border-radius: 6px;
    padding: 8px 10px;
    color: #7A4300;
}}
#chip {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 3px 10px;
    color: {MUTED};
}}
#chipWarning {{
    background: {WARNING_LIGHT};
    border: 1px solid #F3C98B;
    border-radius: 12px;
    padding: 3px 10px;
    color: #7A4300;
}}
QPushButton {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 14px;
}}
QPushButton:hover:enabled {{
    border-color: {ACCENT};
    color: {ACCENT};
}}
QPushButton:disabled {{
    color: #A0A9B4;
}}
QPushButton#primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: white;
    font-weight: 600;
    padding: 9px 20px;
}}
QPushButton#primary:hover:enabled {{
    background: {ACCENT_DARK};
    color: white;
}}
QPushButton#primary:disabled {{
    background: #9DB4CA;
    border-color: #9DB4CA;
}}
QPushButton#token {{
    background: {ACCENT_LIGHT};
    border: 1px solid #C7D9EA;
    border-radius: 11px;
    padding: 3px 10px;
    color: {ACCENT_DARK};
    font-size: 9pt;
}}
QPushButton#token:hover {{
    background: #D3E3F2;
}}
QLineEdit, QComboBox, QDoubleSpinBox, QDateEdit {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
}}
QLineEdit:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QTableView, QListWidget {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: #EEF1F4;
    selection-background-color: {ACCENT_LIGHT};
    selection-color: {TEXT};
}}
QListWidget::item {{
    padding: 8px 10px;
    border-bottom: 1px solid #EEF1F4;
}}
QListWidget::item:selected {{
    background: {ACCENT_LIGHT};
    color: {TEXT};
}}
/* listes déroulantes, bulles d'aide et boîtes de dialogue : toujours claires,
   même quand Windows est en mode sombre */
QComboBox QAbstractItemView {{
    background: white;
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_LIGHT};
    selection-color: {TEXT};
    outline: 0;
}}
QToolTip {{
    background: white;
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 6px;
}}
QDialog, QMessageBox, QInputDialog, QProgressDialog {{
    background: {BACKGROUND};
}}
QMenu {{
    background: white;
    color: {TEXT};
    border: 1px solid {BORDER};
}}
QMenu::item:selected {{
    background: {ACCENT_LIGHT};
}}
QHeaderView::section {{
    background: #F0F3F6;
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 8px;
    font-weight: 600;
    color: {MUTED};
}}
QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: white;
    text-align: center;
    height: 20px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 5px;
}}
QRadioButton, QCheckBox {{
    spacing: 10px;
}}
/* cases à cocher et boutons radio bien visibles : bord foncé, et une fois choisis,
   fond plein bleu marine avec une coche (ou un point) blanc */
QCheckBox::indicator, QRadioButton::indicator, QTableView::indicator {{
    width: 18px;
    height: 18px;
    background: white;
    border: 2px solid #7D8A99;
}}
QCheckBox::indicator, QTableView::indicator {{
    border-radius: 4px;
}}
QRadioButton::indicator {{
    border-radius: 11px;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked, QTableView::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: url("{ASSETS}/coche.svg");
}}
QRadioButton::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: url("{ASSETS}/point.svg");
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background: #E6EAEE;
    border-color: #C2CAD3;
}}
QCheckBox::indicator:checked:disabled, QRadioButton::indicator:checked:disabled {{
    background: #A9B5C2;
    border-color: #A9B5C2;
}}
QCheckBox:disabled, QRadioButton:disabled {{
    color: #8A94A0;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
"""


def apply_light_theme(app):
    """Thème clair imposé : sans cela, en mode sombre, Windows assombrit une partie des éléments
    (listes déroulantes, boîtes de dialogue) et le texte devient illisible."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPalette
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:  # Qt plus ancien que 6.8
        pass
    palette = QPalette()
    roles = {
        QPalette.Window: BACKGROUND, QPalette.WindowText: TEXT,
        QPalette.Base: "#FFFFFF", QPalette.AlternateBase: "#F6F8FA",
        QPalette.Text: TEXT, QPalette.PlaceholderText: "#8A94A0",
        QPalette.Button: "#FFFFFF", QPalette.ButtonText: TEXT,
        QPalette.ToolTipBase: "#FFFFFF", QPalette.ToolTipText: TEXT,
        QPalette.Highlight: ACCENT_LIGHT, QPalette.HighlightedText: TEXT,
        QPalette.Link: ACCENT, QPalette.BrightText: "#FFFFFF",
        QPalette.Light: "#FFFFFF", QPalette.Midlight: "#EEF1F4", QPalette.Mid: BORDER,
        QPalette.Dark: "#9AA5B1", QPalette.Shadow: "#5F6B7A",
    }
    for role, color in roles.items():
        palette.setColor(QPalette.All, role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor("#A0A9B4"))
    app.setPalette(palette)
