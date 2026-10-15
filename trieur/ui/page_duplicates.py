"""Étape 4 : doublons."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSplitter, QVBoxLayout, QWidget)

from ..duplicates import IDENTICAL, SAME_PHOTO, SIMILAR, DuplicateGroup
from ..settings import MOVE, TASK_DUPLICATES
from .style import OK
from .thumbs import thumbnail
from .widgets import Page, label

EXPLANATIONS = {
    IDENTICAL: "Fichiers exactement identiques, sous des noms ou dans des dossiers différents.",
    SAME_PHOTO: "La même photo en plusieurs versions (réduite, recompressée, envoyée par messagerie…). "
                "La meilleure version est proposée.",
    SIMILAR: "Photos presque identiques prises à quelques secondes d'intervalle (rafale). "
             "Elles sont toutes gardées sauf si vous en écartez.",
}


def human_size(size: int) -> str:
    for unit in ("octets", "Ko", "Mo", "Go"):
        if size < 1024 or unit == "Go":
            return f"{size:.0f} {unit}" if unit == "octets" else f"{size:.1f} {unit}".replace(".", ",")
        size /= 1024
    return ""


class PhotoCard(QFrame):
    toggled = Signal()

    def __init__(self, item, keep_path, best: bool):
        super().__init__()
        self.item = item
        self.keep_path = keep_path
        self.setObjectName("card")
        self.setFixedWidth(250)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        image = QLabel()
        image.setAlignment(Qt.AlignCenter)
        image.setFixedHeight(180)
        image.setPixmap(thumbnail(item.path, 230))
        layout.addWidget(image)
        if best:
            badge = QLabel("★ Meilleure version")
            badge.setStyleSheet(f"color: {OK}; font-weight: 600;")
            layout.addWidget(badge)
        name = label(f"<b>{item.name}</b>")
        name.setToolTip(str(item.path))
        layout.addWidget(name)
        details = [str(item.relative.parent) if str(item.relative.parent) != "." else "(dossier principal)"]
        if item.width:
            details.append(f"{item.width} × {item.height} pixels")
        details.append(human_size(item.size))
        if item.date:
            details.append(item.date.strftime("%d/%m/%Y %H:%M") + f" · {item.date_source}")
        layout.addWidget(label("<br>".join(details), "hint"))
        self.keep = QCheckBox("Garder cette photo")
        self.keep.setChecked(not item.excluded)
        self.keep.toggled.connect(self.on_toggle)
        layout.addWidget(self.keep)
        layout.addStretch(1)

    def on_toggle(self, keep: bool):
        self.item.excluded = not keep
        # une photo écartée ici est un doublon : en déplacement, elle est mise de côté dans _Doublons
        self.item.duplicate_of = None if keep or self.item.path == self.keep_path else self.keep_path
        self.toggled.emit()


class DuplicatesPage(Page):
    next_requested = Signal()
    changed = Signal()

    def __init__(self, settings):
        super().__init__("Doublons",
                         "Les photos décochées ne sont pas classées. En mode « Déplacer », elles sont mises de côté "
                         "dans le dossier « _Doublons » de la destination : rien n'est jamais supprimé.")
        self.settings = settings
        self.groups: list[DuplicateGroup] = []

        self.intro = self.layout.itemAt(1).widget()
        self.empty = label("Aucun doublon trouvé. 👍", "pageIntro")
        self.empty.hide()
        self.layout.addWidget(self.empty)

        self.splitter = QSplitter(Qt.Horizontal)
        self.listing = QListWidget()
        self.listing.setMinimumWidth(280)
        self.listing.currentRowChanged.connect(self.show_group)
        self.splitter.addWidget(self.listing)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(12, 0, 0, 0)
        self.kind = label("", "cardTitle")
        self.explanation = label("", "hint")
        rl.addWidget(self.kind)
        rl.addWidget(self.explanation)
        self.cards_area = QScrollArea()
        self.cards_area.setWidgetResizable(True)
        self.cards_host = QWidget()
        self.cards_layout = QHBoxLayout(self.cards_host)
        self.cards_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.cards_area.setWidget(self.cards_host)
        rl.addWidget(self.cards_area, 1)
        self.library = label("", "warningBox")
        self.library.hide()
        rl.addWidget(self.library)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(1, 1)
        self.layout.addWidget(self.splitter, 1)

        nav = QHBoxLayout()
        keep_best = QPushButton("Garder seulement la meilleure version partout")
        keep_best.clicked.connect(lambda: self.choose_all(best_only=True))
        keep_all = QPushButton("Tout garder")
        keep_all.clicked.connect(lambda: self.choose_all(best_only=False))
        nav.addWidget(keep_best)
        nav.addWidget(keep_all)
        self.export = QPushButton("Exporter la liste (Excel)…")
        self.export.clicked.connect(self.export_report)
        nav.addWidget(self.export)
        nav.addStretch(1)
        self.next = QPushButton("Continuer  →")
        self.next.setObjectName("primary")
        self.next.clicked.connect(self.next_requested)
        nav.addWidget(self.next)
        self.layout.addLayout(nav)

    def set_analysis(self, analysis):
        self.groups = analysis.duplicates if analysis else []
        if self.settings.task == TASK_DUPLICATES:
            found = sum(1 for g in self.groups for i in g.items if i.excluded)
            total = len(analysis.items) if analysis else 0
            self.intro.setText(
                f"{total:,} photos et vidéos analysées, {len(self.groups):,} groupes de doublons. ".replace(",", " ") +
                "Les photos décochées seront déplacées dans le dossier « _Doublons » de la photothèque, "
                "avec leur chemin d'origine. Rien n'est supprimé.")
        else:
            self.intro.setText("Les photos décochées ne sont pas classées. En mode « Déplacer », elles sont mises de "
                               "côté dans le dossier « _Doublons » de la destination : rien n'est jamais supprimé.")
        self.export.setEnabled(bool(self.groups))
        self.listing.clear()
        for group in self.groups:
            entry = QListWidgetItem()
            self.listing.addItem(entry)
            self.update_entry(self.listing.count() - 1)
        has = bool(self.groups)
        self.empty.setVisible(not has)
        self.splitter.setVisible(has)
        if has:
            self.listing.setCurrentRow(0)

    def update_entry(self, row: int):
        group = self.groups[row]
        kept = sum(1 for i in group.items if not i.excluded)
        name = group.keep.name
        text = f"{group.kind} · {len(group.items)} fichiers\n{name}\n{kept} gardée(s)"
        if group.library_matches:
            text += " · déjà dans la photothèque"
        self.listing.item(row).setText(text)

    def show_group(self, row: int):
        while self.cards_layout.count():
            widget = self.cards_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        if row < 0 or row >= len(self.groups):
            return
        group = self.groups[row]
        self.kind.setText(group.kind)
        self.explanation.setText(EXPLANATIONS[group.kind])
        for item in group.items:
            card = PhotoCard(item, group.keep.path, item is group.keep)
            card.toggled.connect(lambda r=row: self.on_toggle(r))
            self.cards_layout.addWidget(card)
        if group.library_matches:
            self.library.setText("Cette photo est déjà présente dans la destination : "
                                 f"{group.library_matches[0]}. Elle ne sera pas classée une seconde fois.")
            self.library.show()
        else:
            self.library.hide()

    def on_toggle(self, row: int):
        self.update_entry(row)
        self.changed.emit()

    def export_report(self):
        from datetime import datetime
        from pathlib import Path
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from ..executor import write_report
        default = Path.home() / "Documents" / f"doublons_{datetime.now():%Y-%m-%d_%Hh%M}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer la liste des doublons", str(default),
                                              "Fichier CSV pour Excel (*.csv)")
        if not path:
            return
        try:
            write_report(self.groups, Path(path))
        except OSError as error:
            QMessageBox.warning(self, "Liste des doublons", f"Enregistrement impossible : {error}")
            return
        from .page_run import open_folder
        open_folder(Path(path).parent)

    def choose_all(self, best_only: bool):
        for group in self.groups:
            for item in group.items:
                exclude = best_only and item is not group.keep
                item.excluded = exclude
                item.duplicate_of = group.keep.path if exclude else None
        for row in range(len(self.groups)):
            self.update_entry(row)
        self.show_group(self.listing.currentRow())
        self.changed.emit()
