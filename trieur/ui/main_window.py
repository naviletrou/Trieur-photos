"""Fenêtre principale : barre des étapes et pages de l'assistant."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QMainWindow, QMessageBox, QProgressDialog, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import __version__, analyze
from ..exiftool import ExifToolError, find_exiftool
from ..places import get_index
from ..settings import Settings
from .page_duplicates import DuplicatesPage
from .page_folders import FoldersPage
from .page_review import ReviewPage
from .page_rules import RulesPage
from .page_run import RunPage
from .widgets import label
from .workers import AnalysisWorker, ExecuteWorker, UndoWorker

STEPS = ["1   Dossiers", "2   Classement", "3   Vérification", "4   Doublons", "5   Lancement"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trieur de photos")
        self.resize(1280, 820)
        self.settings = Settings.load()
        self.analysis = None
        self.worker = None

        root = QWidget()
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 22, 16, 16)
        side.setSpacing(4)
        side.addWidget(label("Trieur de photos", "appTitle"))
        side.addWidget(label("Ranger, nommer, dédoublonner", "appSubtitle"))
        side.addSpacing(22)
        self.step_buttons: list[QPushButton] = []
        for index, title in enumerate(STEPS):
            button = QPushButton(title)
            button.setObjectName("step")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, i=index: self.go(i))
            side.addWidget(button)
            self.step_buttons.append(button)
        side.addStretch(1)
        undo = QPushButton("Annuler un classement…")
        undo.setObjectName("step")
        undo.setStyleSheet("font-size: 9pt;")
        undo.clicked.connect(self.undo_previous)
        side.addWidget(undo)
        about = QPushButton("À propos")
        about.setObjectName("step")
        about.setStyleSheet("font-size: 9pt;")
        about.clicked.connect(self.about)
        side.addWidget(about)
        row.addWidget(sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        self.folders = FoldersPage(self.settings)
        self.rules = RulesPage(self.settings)
        self.review = ReviewPage(self.settings)
        self.duplicates = DuplicatesPage(self.settings)
        self.run = RunPage(self.settings)
        for page in (self.folders, self.rules, self.review, self.duplicates, self.run):
            page.setObjectName("content")
            self.stack.addWidget(page)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.folders.analyse_requested.connect(self.start_analysis)
        self.rules.rules_changed.connect(self.rules_changed)
        self.rules.next_requested.connect(lambda: self.go(2))
        self.review.next_requested.connect(lambda: self.go(3 if self.analysis and self.analysis.duplicates else 4))
        self.review.changed.connect(self.invalidate_run)
        self.duplicates.next_requested.connect(lambda: self.go(4))
        self.duplicates.changed.connect(self.invalidate_run)
        self.run.run_requested.connect(self.start_run)
        self.run.undo_requested.connect(self.start_undo)
        self.run.restart_requested.connect(self.restart)
        self.run.cancel.clicked.connect(lambda: self.worker and self.worker.cancel())

        self.update_steps(0)
        self.check_tools()

    # -- navigation --------------------------------------------------------------------------

    def update_steps(self, current: int):
        for index, button in enumerate(self.step_buttons):
            button.setEnabled(index == 0 or self.analysis is not None)
            button.setChecked(index == current)
        self.stack.setCurrentIndex(current)

    def go(self, index: int):
        if index > 0 and not self.analysis:
            index = 0
        self.update_steps(index)
        page = self.stack.widget(index)
        page.entered()

    def invalidate_run(self):
        self.run.set_analysis(self.analysis)

    def restart(self):
        self.analysis = None
        self.update_steps(0)

    # -- travaux en arrière-plan -------------------------------------------------------------

    def run_worker(self, worker, title: str, on_done, modal: bool = True):
        self.worker = worker
        dialog = None
        if modal:
            dialog = QProgressDialog(title, "Arrêter", 0, 0, self)
            dialog.setWindowTitle("Trieur de photos")
            dialog.setWindowModality(Qt.WindowModal)
            dialog.setMinimumWidth(460)
            dialog.setMinimumDuration(0)
            dialog.canceled.connect(worker.cancel)

            def progress(text, done, total):
                dialog.setLabelText(f"{text}…" + (f"  {done:,} / {total:,}".replace(",", " ") if total else
                                                   (f"  {done:,}".replace(",", " ") if done else "")))
                dialog.setMaximum(total or 0)
                if total:
                    dialog.setValue(min(done, total))
            worker.progress.connect(progress)
        else:
            worker.progress.connect(self.run.show_progress)

        def finished(result):
            if dialog:
                dialog.reset()
                dialog.close()
            on_done(result)

        def failed(message):
            if dialog:
                dialog.close()
            QMessageBox.critical(self, "Erreur", message)

        worker.done.connect(finished)
        worker.failed.connect(failed)
        worker.start()
        if dialog:
            dialog.show()

    def start_analysis(self):
        self.run_worker(AnalysisWorker(self.settings), "Analyse des photos", self.analysis_done)

    def analysis_done(self, analysis):
        if analysis is None:
            return  # arrêtée par l'utilisateur
        if not analysis.items:
            QMessageBox.information(self, "Analyse", "Aucune photo ni vidéo trouvée dans ce dossier.")
            return
        self.analysis = analysis
        self.rules.set_analysis(analysis)
        self.review.set_analysis(analysis)
        self.duplicates.set_analysis(analysis)
        self.run.set_analysis(analysis)
        self.go(1)

    def rules_changed(self, needs_resolve: bool):
        if not self.analysis:
            return
        self.setCursor(Qt.WaitCursor)
        try:
            if needs_resolve:
                analyze.resolve(self.analysis.items, self.settings, get_index())
            previous = {g.key: g for g in self.analysis.groups}
            self.analysis.groups = analyze.build_groups(self.analysis.items, self.settings, previous)
            analyze.plan(self.analysis.groups, self.settings, check_disk=False)
            self.review.set_analysis(self.analysis)
            self.run.set_analysis(self.analysis)
        finally:
            self.unsetCursor()

    def start_run(self):
        self.run.cancel.show()
        self.run_worker(ExecuteWorker(self.analysis), "Classement", self.run_done, modal=False)

    def run_done(self, result):
        self.run.cancel.hide()
        self.run.show_result(result)
        for button in self.step_buttons[1:4]:
            button.setEnabled(False)

    def start_undo(self, journal: Path):
        self.run_worker(UndoWorker(journal), "Annulation du classement", lambda r: self.run.show_result(r, True),
                        modal=True)

    def undo_previous(self):
        start = str(Path(self.settings.destination) / "_Journal") if self.settings.destination else ""
        path, _ = QFileDialog.getOpenFileName(self, "Choisir le journal du classement à annuler", start,
                                              "Journal (*.csv)")
        if not path:
            return
        answer = QMessageBox.question(self, "Annuler un classement",
                                      "Remettre les photos comme avant ce classement ?")
        if answer == QMessageBox.Yes:
            self.update_steps(4)
            self.run.set_analysis(None)
            self.run.recap_card.hide()
            self.run_worker(UndoWorker(Path(path)), "Annulation du classement",
                            lambda r: self.run.show_result(r, True))

    # -- divers ------------------------------------------------------------------------------

    def check_tools(self):
        try:
            find_exiftool()
        except ExifToolError as error:
            QMessageBox.critical(self, "ExifTool manquant", str(error))

    def about(self):
        places = "disponible" if get_index() else "absente (les lieux ne seront pas trouvés)"
        QMessageBox.about(self, "À propos",
                          f"<b>Trieur de photos</b> version {__version__}<br><br>"
                          "Range les photos par date et par lieu, les renomme et repère les doublons.<br><br>"
                          f"Base des lieux : {places}.<br>"
                          "Lieux : © GeoNames (geonames.org), licence CC BY 4.0.<br>"
                          "Métadonnées : ExifTool de Phil Harvey (exiftool.org).<br>"
                          "Interface : Qt for Python (PySide6), licence LGPL.")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            answer = QMessageBox.question(self, "Quitter", "Un traitement est en cours. Quitter quand même ?")
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait(5000)
        self.settings.save()
        event.accept()
