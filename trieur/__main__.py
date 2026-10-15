"""Point d'entrée : python -m trieur"""
import sys


def main():
    from PySide6.QtCore import QLocale, QTranslator, QLibraryInfo
    from PySide6.QtWidgets import QApplication

    from . import log
    from .ui.main_window import MainWindow
    from .ui.style import STYLE, apply_light_theme

    log.setup()

    app = QApplication(sys.argv)
    app.setApplicationName("Trieur de photos")
    app.setOrganizationName("TrieurPhotos")
    app.setStyle("Fusion")
    apply_light_theme(app)
    QLocale.setDefault(QLocale(QLocale.French, QLocale.France))
    # boutons standard (Oui, Non, Annuler…) en français
    translator = QTranslator(app)
    if translator.load(QLocale(QLocale.French), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)
    app.setStyleSheet(STYLE)
    from PySide6.QtGui import QIcon
    from .exiftool import app_dir
    for base in (app_dir() / "assets", app_dir() / "_internal" / "assets"):
        if (base / "icone.png").exists():
            app.setWindowIcon(QIcon(str(base / "icone.png")))
            break
    window = MainWindow()
    log.install_excepthook(window.show_error)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
