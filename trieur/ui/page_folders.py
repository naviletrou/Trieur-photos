"""Étape 1 : dossiers à traiter et destination."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QCheckBox, QHBoxLayout, QPushButton, QRadioButton

from ..settings import COPY, MOVE, Settings
from .widgets import Card, Page, PathPicker, label


class FoldersPage(Page):
    analyse_requested = Signal()

    def __init__(self, settings: Settings):
        super().__init__("Dossiers",
                         "Choisissez les photos à ranger et l'endroit où les classer. "
                         "Rien n'est modifié avant la dernière étape : vous verrez d'abord le résultat.")
        self.settings = settings

        source = Card("Photos à ranger", "Le dossier contenant les photos (une carte mémoire, un dossier "
                                         "« À trier », une ancienne archive…).")
        self.source = source.add(PathPicker("Dossier à traiter", "Choisir le dossier des photos à ranger"))
        self.recursive = source.add(QCheckBox("Inclure les sous-dossiers"))
        types = QHBoxLayout()
        self.photos = QCheckBox("Photos")
        self.videos = QCheckBox("Vidéos")
        types.addWidget(self.photos)
        types.addWidget(self.videos)
        types.addStretch(1)
        source.layout.addLayout(types)
        self.layout.addWidget(source)

        dest = Card("Destination", "Le dossier de votre photothèque, où les photos seront classées.")
        self.destination = dest.add(PathPicker("Dossier de destination", "Choisir le dossier de destination"))
        modes = QHBoxLayout()
        self.copy = QRadioButton("Copier les photos  (les originaux restent intacts — conseillé)")
        self.move = QRadioButton("Déplacer les photos")
        group = QButtonGroup(self)
        group.addButton(self.copy)
        group.addButton(self.move)
        modes.addWidget(self.copy)
        modes.addWidget(self.move)
        modes.addStretch(1)
        dest.layout.addLayout(modes)
        self.layout.addWidget(dest)

        dup = Card("Doublons")
        self.find_dups = dup.add(QCheckBox("Rechercher les doublons"))
        self.dups_dest = dup.add(QCheckBox("Comparer aussi avec les photos déjà présentes dans la destination"))
        self.similar = dup.add(QCheckBox("Signaler les photos presque identiques (rafales)"))
        self.find_dups.toggled.connect(lambda on: (self.dups_dest.setEnabled(on), self.similar.setEnabled(on)))
        self.layout.addWidget(dup)

        self.message = label("", "warningBox")
        self.message.hide()
        self.layout.addWidget(self.message)
        self.layout.addStretch(1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.analyse = QPushButton("Analyser les photos  →")
        self.analyse.setObjectName("primary")
        self.analyse.clicked.connect(self.request_analysis)
        bottom.addWidget(self.analyse)
        self.layout.addLayout(bottom)

        self.load()
        for widget in (self.source, self.destination):
            widget.changed.connect(self.validate)
        self.validate()

    def load(self):
        s = self.settings
        self.source.setText(s.source)
        self.destination.setText(s.destination)
        self.recursive.setChecked(s.recursive)
        self.photos.setChecked(s.include_photos)
        self.videos.setChecked(s.include_videos)
        (self.move if s.mode == MOVE else self.copy).setChecked(True)
        self.find_dups.setChecked(s.find_duplicates)
        self.dups_dest.setChecked(s.duplicates_in_destination)
        self.similar.setChecked(s.similar_photos)
        self.dups_dest.setEnabled(s.find_duplicates)
        self.similar.setEnabled(s.find_duplicates)

    def store(self):
        s = self.settings
        s.source = self.source.text()
        s.destination = self.destination.text()
        s.recursive = self.recursive.isChecked()
        s.include_photos = self.photos.isChecked()
        s.include_videos = self.videos.isChecked()
        s.mode = MOVE if self.move.isChecked() else COPY
        s.find_duplicates = self.find_dups.isChecked()
        s.duplicates_in_destination = self.dups_dest.isChecked()
        s.similar_photos = self.similar.isChecked()

    def problem(self) -> str:
        source, destination = self.source.text(), self.destination.text()
        if not source:
            return ""
        if not Path(source).is_dir():
            return "Le dossier des photos à ranger est introuvable."
        if not destination:
            return ""
        src = os.path.normcase(os.path.abspath(source))
        dst = os.path.normcase(os.path.abspath(destination))
        if src == dst:
            return "La destination doit être différente du dossier à traiter."
        if src.startswith(dst + os.sep):
            return ("Le dossier à traiter se trouve dans la destination. Choisissez plutôt un dossier "
                    "« À trier » placé à côté de votre photothèque.")
        return ""

    def validate(self):
        problem = self.problem()
        self.message.setText(problem)
        self.message.setVisible(bool(problem))
        self.analyse.setEnabled(bool(self.source.text() and self.destination.text() and not problem))

    def request_analysis(self):
        if not (self.photos.isChecked() or self.videos.isChecked()):
            self.message.setText("Cochez au moins « Photos » ou « Vidéos ».")
            self.message.show()
            return
        self.store()
        self.settings.save()
        self.analyse_requested.emit()
