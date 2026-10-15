"""Étape 5 : lancement du classement, résultat et annulation."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QProgressBar, QPushButton

from .. import analyze
from ..settings import MOVE, TASK_DUPLICATES
from .widgets import Card, Page, label


def open_folder(path: Path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class RunPage(Page):
    run_requested = Signal()
    undo_requested = Signal(object)
    restart_requested = Signal()

    def __init__(self, settings):
        super().__init__("Lancement", "Dernière vérification avant de classer vos photos.")
        self.settings = settings
        self.analysis = None
        self.result = None

        self.recap_card = Card("Ce qui va être fait")
        self.recap = self.recap_card.add(label(""))
        self.layout.addWidget(self.recap_card)

        self.warning = label("", "warningBox")
        self.warning.hide()
        self.layout.addWidget(self.warning)

        self.progress_card = Card("Progression")
        self.step = self.progress_card.add(label(""))
        self.bar = self.progress_card.add(QProgressBar())
        self.progress_card.hide()
        self.layout.addWidget(self.progress_card)

        self.result_card = Card("Terminé")
        self.result_text = self.result_card.add(label(""))
        buttons = QHBoxLayout()
        self.open_dest = QPushButton("Ouvrir la destination")
        self.open_dest.clicked.connect(self.open_target)
        self.open_journal = QPushButton("Voir le journal")
        self.open_journal.clicked.connect(self.show_journal)
        self.undo = QPushButton("Tout remettre en place")
        self.undo.clicked.connect(self.confirm_undo)
        self.again = QPushButton("Nouveau classement")
        self.again.clicked.connect(self.restart_requested)
        for button in (self.open_dest, self.open_journal, self.undo, self.again):
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.result_card.layout.addLayout(buttons)
        self.result_card.hide()
        self.layout.addWidget(self.result_card)
        self.layout.addStretch(1)

        nav = QHBoxLayout()
        nav.addStretch(1)
        self.cancel = QPushButton("Arrêter")
        self.cancel.hide()
        nav.addWidget(self.cancel)
        self.start = QPushButton("Lancer le classement")
        self.start.setObjectName("primary")
        self.start.clicked.connect(self.confirm_run)
        nav.addWidget(self.start)
        self.layout.addLayout(nav)

    def set_analysis(self, analysis):
        self.analysis = analysis
        self.result = None
        self.start.setText("Lancer le classement")
        self.layout.itemAt(1).widget().setText("Dernière vérification avant de classer vos photos.")
        self.result_card.hide()
        self.progress_card.hide()
        self.start.show()
        self.start.setEnabled(True)

    def entered(self):
        if not self.analysis or self.result:
            return
        if self.settings.task == TASK_DUPLICATES:
            self.enter_duplicates()
            return
        analyze.plan(self.analysis.groups, self.settings, check_disk=False)
        stats = analyze.summary(self.analysis.groups)
        move = self.settings.mode == MOVE
        verb = "déplacées" if move else "copiées"
        lines = [
            f"• <b>{stats['actifs']:,}</b> photos et vidéos seront {verb} dans <b>{stats['dossiers']:,}</b> dossiers de "
            f"<b>{self.settings.destination}</b>",
        ]
        if stats["ecartes"]:
            lines.append(f"• {stats['ecartes']} doublons ou photos décochées ne seront pas classés"
                         + (" (mis de côté dans « _Doublons »)" if move else ""))
        if stats["deja_presents"]:
            lines.append(f"• {stats['deja_presents']} photos sont déjà dans la photothèque et seront ignorées")
        without = sum(1 for g in self.analysis.groups if g.effective_date is None for i in g.active_items)
        if without:
            lines.append(f"• {without} photos sans date iront dans « {self.settings.undated_folder} », "
                         "avec leur nom et leur dossier d'origine")
        if self.settings.write_dates and stats["dates_a_ecrire"]:
            lines.append(f"• La date sera écrite dans {stats['dates_a_ecrire']} photos qui n'en avaient pas")
        lines.append("• Un journal permettra d'annuler entièrement ce classement")
        self.recap.setText("<br>".join(lines).replace(",", " "))
        self.recap.adjustSize()
        self.recap_card.adjustSize()
        if move:
            self.warning.setText("Mode « Déplacer » : les photos quittent leur dossier d'origine. "
                                 "Vous pourrez tout remettre en place avec « Annuler ce classement ».")
            self.warning.show()
        else:
            self.warning.hide()

    def enter_duplicates(self):
        aside = [i for i in self.analysis.items if i.excluded and i.duplicate_of]
        size = sum(i.size for i in aside) / 1024 ** 3
        library = Path(self.settings.source)
        lines = [
            f"• <b>{len(aside):,}</b> doublons seront déplacés dans "
            f"<b>{library / '_Doublons'}</b>, en gardant leur chemin d'origine ({size:.1f} Go)".replace(",", " "),
            "• Aucune autre photo n'est déplacée ni renommée",
            "• Un journal permettra de tout remettre en place",
            "• Immich : ajoutez <b>**/_Doublons/**</b> aux motifs d'exclusion de la bibliothèque externe, "
            "puis relancez un scan pour que les doublons disparaissent",
        ]
        self.recap.setText("<br>".join(lines))
        self.warning.hide()
        self.layout.itemAt(1).widget().setText("Dernière vérification avant de mettre les doublons de côté.")
        self.start.setText("Mettre les doublons de côté")
        self.start.setEnabled(bool(aside))

    def confirm_run(self):
        if self.settings.task == TASK_DUPLICATES:
            answer = QMessageBox.question(self, "Doublons", "Déplacer les doublons dans « _Doublons » ?")
            if answer != QMessageBox.Yes:
                return
        elif self.settings.mode == MOVE:
            answer = QMessageBox.question(self, "Déplacer les photos",
                                          "Les photos vont être déplacées. Continuer ?")
            if answer != QMessageBox.Yes:
                return
        self.start.setEnabled(False)
        self.run_requested.emit()

    def show_progress(self, text: str, done: int, total: int):
        self.progress_card.show()
        self.step.setText(text)
        if total:
            self.bar.setRange(0, total)
            self.bar.setValue(done)
            self.bar.setFormat(f"{done} / {total}")
        else:
            self.bar.setRange(0, 0)

    def show_result(self, result, undone: bool = False):
        self.progress_card.hide()
        self.start.hide()
        self.result = result
        lines = []
        if undone:
            self.result_card.layout.itemAt(0).widget().setText("Classement annulé")
            lines.append(f"• {result.moved} fichiers remis à leur place, {result.copied} copies retirées")
            self.undo.hide()
        else:
            dups = self.settings.task == TASK_DUPLICATES
            self.result_card.layout.itemAt(0).widget().setText("Doublons mis de côté" if dups else "Classement terminé")
            self.open_dest.setText("Ouvrir le dossier _Doublons" if dups else "Ouvrir la destination")
            if result.copied:
                lines.append(f"• {result.copied} photos copiées")
            if result.moved:
                lines.append(f"• {result.moved} photos déplacées")
            if result.duplicates_moved:
                lines.append(f"• {result.duplicates_moved} doublons mis de côté dans « _Doublons »")
            if result.dates_written:
                lines.append(f"• {result.dates_written} dates écrites dans les photos")
            if result.folders_removed:
                lines.append(f"• {result.folders_removed} dossiers vides supprimés à l'origine")
            if result.cancelled:
                lines.append("• <b>Classement arrêté avant la fin</b> : vous pouvez l'annuler ou relancer une analyse")
            self.undo.show()
        if result.errors:
            shown = "<br>".join(f"&nbsp;&nbsp;– {e}" for e in result.errors[:8])
            more = f"<br>&nbsp;&nbsp;… et {len(result.errors) - 8} autres" if len(result.errors) > 8 else ""
            lines.append(f"• <span style='color:#C26A00'>{len(result.errors)} problème(s) :</span><br>{shown}{more}")
        self.result_text.setText("<br>".join(lines) or "Rien à faire.")
        self.result_card.show()

    def open_target(self):
        if self.settings.task == TASK_DUPLICATES:
            folder = Path(self.settings.source) / "_Doublons"
            open_folder(folder if folder.exists() else Path(self.settings.source))
        else:
            open_folder(Path(self.settings.destination))

    def show_journal(self):
        if self.result and self.result.journal:
            path = self.result.journal
            if not path.exists():
                path = path.with_name(path.stem + "_annule.csv")
            open_folder(path.parent)

    def confirm_undo(self):
        if not self.result or not self.result.journal:
            return
        answer = QMessageBox.question(self, "Annuler le classement",
                                      "Remettre toutes les photos comme avant ce classement ?\n"
                                      "(les copies sont retirées, les photos déplacées retournent à leur place)")
        if answer == QMessageBox.Yes:
            self.undo_requested.emit(self.result.journal)
