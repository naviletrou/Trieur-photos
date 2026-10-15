"""Fenêtre principale : barre des étapes et pages de l'assistant."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QMainWindow, QMessageBox, QProgressDialog, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import __version__, analyze
from ..log import error_text, log_file, logger
from ..exiftool import ExifToolError, find_exiftool
from ..places import get_index
from ..settings import TASK_DUPLICATES, Settings
from .page_duplicates import DuplicatesPage
from .page_folders import FoldersPage
from .page_review import ReviewPage
from .page_rules import RulesPage
from .page_run import RunPage
from .widgets import label
from .workers import AnalysisWorker, DuplicatesOnlyWorker, ExecuteWorker, UndoWorker

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
        self.folders.task_sort.toggled.connect(self.task_switched)
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
        dups = self.settings.task == TASK_DUPLICATES
        for index, button in enumerate(self.step_buttons):
            button.setEnabled(index == 0 or self.analysis is not None)
            button.setChecked(index == current)
            # mode « Doublons seuls » : ni classement ni vérification, étapes renumérotées
            button.setVisible(not (dups and index in (1, 2)))
            number = {3: 2, 4: 3}.get(index, index + 1) if dups else index + 1
            button.setText(f"{number}   {STEPS[index].split('   ', 1)[1]}")
        self.stack.setCurrentIndex(current)

    def go(self, index: int):
        if index > 0 and not self.analysis:
            index = 0
        if self.settings.task == TASK_DUPLICATES and index in (1, 2):
            index = 3
        self.update_steps(index)
        page = self.stack.widget(index)
        page.entered()

    def invalidate_run(self):
        self.run.set_analysis(self.analysis)

    def restart(self):
        self.analysis = None
        self.update_steps(0)

    def task_switched(self):
        self.folders.store()
        self.analysis = None
        self.update_steps(0)

    # -- travaux en arrière-plan -------------------------------------------------------------

    def previous_work_finished(self) -> bool:
        """Attend la fin d'un travail précédent : deux recherches en même temps saturent le NAS."""
        previous = self.worker
        if previous is None or not previous.isRunning():
            return True
        previous.cancel()
        waiting = QProgressDialog("Arrêt du travail précédent en cours…\n(fin de la lecture des fichiers ouverts)",
                                  None, 0, 0, self)
        waiting.setWindowTitle("Trieur de photos")
        waiting.setWindowModality(Qt.WindowModal)
        waiting.setMinimumWidth(460)
        waiting.setMinimumDuration(0)
        waiting.show()
        while previous.isRunning():
            QApplication.processEvents()
            previous.wait(100)
        waiting.hide()
        waiting.deleteLater()
        return True

    def closeEvent(self, event):
        # ne pas laisser une recherche tourner sans fenêtre (elle continuerait à lire le NAS)
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(15000)
        super().closeEvent(event)

    def run_worker(self, worker, title: str, on_done, modal: bool = True):
        self.previous_work_finished()
        self.worker = worker
        dialog = None
        if modal:
            dialog = QProgressDialog(title, "Arrêter", 0, 0, self)
            dialog.setWindowTitle("Trieur de photos")
            dialog.setWindowModality(Qt.WindowModal)
            dialog.setMinimumWidth(460)
            dialog.setMinimumDuration(0)
            # sinon la fenêtre disparaît dès qu'une étape atteint 100 %, alors que l'analyse continue
            dialog.setAutoReset(False)
            dialog.setAutoClose(False)

            def stop():
                # la fenêtre reste affichée jusqu'à l'arrêt réel : on ne peut pas relancer entre-temps
                worker.cancel()
                state["stopping"] = True
                dialog.setCancelButtonText("Arrêt en cours…")
                cancel_button = dialog.findChild(QPushButton)
                if cancel_button:
                    cancel_button.setEnabled(False)
                dialog.setLabelText("Arrêt en cours…\n(fin de la lecture des fichiers ouverts)")
                dialog.show()
            dialog.canceled.connect(stop)

            state = {"text": "", "count": "", "detail": "", "stopping": False}

            def refresh_label():
                if state["stopping"]:
                    return
                lines = [f"{state['text']}…"]
                if state["count"]:
                    lines.append(state["count"])
                if state["detail"]:
                    lines.append(state["detail"])
                dialog.setLabelText("\n".join(lines))

            def detail(text):
                # nom du fichier ou du dossier en cours : montre que le travail avance
                state["detail"] = text if len(text) <= 70 else "…" + text[-69:]
                refresh_label()

            def progress(text, done, total):
                count = (f"{done:,} / {total:,}" if total else (f"{done:,}" if done else "")).replace(",", " ")
                if text != state["text"]:
                    state["detail"] = ""
                state["text"], state["count"] = text, count
                refresh_label()
                if total:
                    dialog.setRange(0, total)
                    dialog.setValue(min(done, total))
                else:
                    dialog.setRange(0, 0)  # durée inconnue : barre animée
                if not dialog.isVisible():
                    dialog.show()
            worker.progress.connect(progress)
            worker.detail.connect(detail)
        else:
            worker.progress.connect(self.run.show_progress)

        def close_dialog():
            if dialog:
                try:
                    dialog.canceled.disconnect()
                except (RuntimeError, TypeError):
                    pass
                dialog.hide()
                dialog.deleteLater()

        def finished(result):
            close_dialog()
            try:
                on_done(result)
            except Exception as error:
                logger.error("Erreur après « %s » :\n%s", title, error_text(error))
                self.show_error(f"{error.__class__.__name__} : {error}", error_text(error))

        def failed(message):
            close_dialog()
            self.show_error(message)

        worker.done.connect(finished)
        worker.failed.connect(failed)
        worker.start()
        if dialog:
            dialog.show()

    def start_analysis(self):
        self.analysis = None
        if self.settings.task == TASK_DUPLICATES:
            self.run_worker(DuplicatesOnlyWorker(self.settings), "Recherche des doublons", self.analysis_done)
        else:
            self.run_worker(AnalysisWorker(self.settings), "Analyse des photos", self.analysis_done)

    def analysis_done(self, analysis):
        if analysis is None:
            QMessageBox.information(self, "Analyse", "Analyse arrêtée.")
            return
        if not analysis.items:
            QMessageBox.information(self, "Analyse", "Aucune photo ni vidéo trouvée dans ce dossier.")
            return
        self.analysis = analysis
        self.duplicates.set_analysis(analysis)
        self.run.set_analysis(analysis)
        if self.settings.task == TASK_DUPLICATES:
            self.go(3)
            return
        self.rules.set_analysis(analysis)
        self.review.set_analysis(analysis)
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

    def show_error(self, message: str, details: str = ""):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("Erreur")
        box.setText(message)
        box.setInformativeText(f"Le détail est enregistré dans le journal technique :\n{log_file()}")
        if details:
            box.setDetailedText(details)
        box.exec()

    def open_log(self):
        from .page_run import open_folder
        open_folder(log_file().parent)

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
                          "Interface : Qt for Python (PySide6), licence LGPL.<br><br>"
                          f"Journal technique : {log_file()}")

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
