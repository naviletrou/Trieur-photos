"""Étape 1 : dossiers à traiter et destination."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QCheckBox, QHBoxLayout, QPushButton, QRadioButton

from ..settings import COPY, MOVE, TASK_DUPLICATES, TASK_SORT, Settings
from .widgets import Card, Page, PathPicker, label


class FoldersPage(Page):
    analyse_requested = Signal()

    def __init__(self, settings: Settings):
        super().__init__("Dossiers",
                         "Choisissez les photos à ranger et l'endroit où les classer. "
                         "Rien n'est modifié avant la dernière étape : vous verrez d'abord le résultat.")
        self.settings = settings

        task = Card("Que voulez-vous faire ?")
        tasks = QHBoxLayout()
        self.task_sort = QRadioButton("Classer des photos  (ranger, renommer, dédoublonner)")
        self.task_dups = QRadioButton("Rechercher les doublons dans ma photothèque  (sans rien reclasser)")
        task_group = QButtonGroup(self)
        task_group.addButton(self.task_sort)
        task_group.addButton(self.task_dups)
        tasks.addWidget(self.task_sort)
        tasks.addWidget(self.task_dups)
        tasks.addStretch(1)
        task.layout.addLayout(tasks)
        self.layout.addWidget(task)

        source = Card("Photos à ranger", "Le dossier contenant les photos (une carte mémoire, un dossier "
                                         "« À trier », une ancienne archive…).")
        self.source_card = source
        self.source_title = source.layout.itemAt(0).widget()
        self.source_hint = source.layout.itemAt(1).widget()
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
        self.dest_card = dest
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
        self.preferred_hint = dup.add(label(
            "Facultatif : un dossier dont les photos sont gardées en priorité quand il existe des copies identiques "
            "ailleurs. Sinon, le programme garde la copie la mieux rangée (dossier daté ou nommé plutôt que "
            "« Divers » ou « À trier », nom d'origine plutôt que « Copie de… »).", "hint"))
        self.preferred = dup.add(PathPicker("Dossier préféré (facultatif)", "Choisir le dossier à privilégier"))
        self.aside_hint = dup.add(label(
            "Où mettre les doublons écartés ? Laissez vide pour un dossier « _Doublons » dans la photothèque, ou "
            "choisissez un dossier en dehors (un autre dossier du disque, un disque de sauvegarde, ce PC) : "
            "Immich ne les verra jamais.", "hint"))
        self.aside = dup.add(PathPicker("Dossier des doublons (facultatif)", "Choisir où mettre les doublons écartés"))
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
        for widget in (self.source, self.destination, self.preferred, self.aside):
            widget.changed.connect(self.validate)
        self.task_sort.toggled.connect(self.task_changed)
        self.task_changed()

    @property
    def duplicates_only(self) -> bool:
        return self.task_dups.isChecked()

    def task_changed(self):
        dups = self.duplicates_only
        self.source_title.setText("Photothèque à vérifier" if dups else "Photos à ranger")
        self.source_hint.setText(
            "Le dossier de votre photothèque, sur ce PC ou sur le réseau (par exemple \\\\openmediavault\\Photos). "
            "Seuls les doublons que vous écarterez seront déplacés, dans le dossier des doublons choisi plus bas." if dups else
            "Le dossier contenant les photos (une carte mémoire, un dossier « À trier », une ancienne archive…).")
        self.dest_card.setVisible(not dups)
        self.find_dups.setVisible(not dups)
        self.dups_dest.setVisible(not dups)
        self.preferred.setVisible(dups)
        self.preferred_hint.setVisible(dups)
        self.analyse.setText("Rechercher les doublons  →" if dups else "Analyser les photos  →")
        self.layout.itemAt(1).widget().setText(
            "Choisissez la photothèque à vérifier. Rien n'est modifié avant la dernière étape : vous verrez d'abord "
            "les doublons trouvés." if dups else
            "Choisissez les photos à ranger et l'endroit où les classer. Rien n'est modifié avant la dernière étape : "
            "vous verrez d'abord le résultat.")
        self.validate()

    def load(self):
        s = self.settings
        (self.task_dups if s.task == TASK_DUPLICATES else self.task_sort).setChecked(True)
        self.preferred.setText(s.preferred_folder)
        self.aside.setText(s.duplicates_folder)
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
        s.task = TASK_DUPLICATES if self.duplicates_only else TASK_SORT
        s.preferred_folder = self.preferred.text() if self.duplicates_only else ""
        s.duplicates_folder = self.aside.text()
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
            return "Le dossier des photos est introuvable."
        aside = self.aside.text()
        if aside:
            folder = os.path.normcase(os.path.abspath(aside))
            libraries = [source] if self.duplicates_only else [source, destination]
            for library in filter(None, libraries):
                lib = os.path.normcase(os.path.abspath(library))
                if folder == lib or folder.startswith(lib + os.sep):
                    return ("Le dossier des doublons doit être en dehors des photos analysées "
                            "(ou laissez-le vide pour « _Doublons »).")
        if self.duplicates_only:
            preferred = self.preferred.text()
            if preferred:
                pref = os.path.normcase(os.path.abspath(preferred))
                src = os.path.normcase(os.path.abspath(source))
                if pref != src and not pref.startswith(src + os.sep):
                    return "Le dossier préféré doit se trouver dans la photothèque."
            return ""
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
        ready = self.source.text() and (self.duplicates_only or self.destination.text())
        self.analyse.setEnabled(bool(ready and not problem))

    def request_analysis(self):
        if not (self.photos.isChecked() or self.videos.isChecked()):
            self.message.setText("Cochez au moins « Photos » ou « Vidéos ».")
            self.message.show()
            return
        self.store()
        if self.duplicates_only:
            self.settings.find_duplicates = True
        self.settings.save()
        self.analyse_requested.emit()
