"""Étape 3 : vérification des groupes de photos avant le classement."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QMessageBox, QPushButton, QSplitter, QTableView, QVBoxLayout, QWidget)

from .. import analyze
from ..dates import find_date
from ..model import DATE_FILE, Group, MediaItem
from .style import WARNING
from .thumbs import thumbnail
from .widgets import Chip, Page, label

FILTERS = ["Tous les groupes", "À vérifier", "Sans date", "Sans lieu", "Avec photos écartées"]


def format_date(when, precision: str) -> str:
    if when is None:
        return "Sans date"
    if precision == "année":
        return f"{when.year}"
    if precision == "mois":
        return when.strftime("%m/%Y")
    return when.strftime("%d/%m/%Y")


def relative_to(path: Path | None, base: str) -> str:
    if not path:
        return ""
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


class GroupsModel(QAbstractTableModel):
    HEADERS = ["", "Date", "Lieu", "Événement", "Photos", "Dossier de destination"]
    edited = Signal()

    def __init__(self):
        super().__init__()
        self.groups: list[Group] = []
        self.destination = ""

    def set_groups(self, groups: list[Group], destination: str):
        self.beginResetModel()
        self.groups = groups
        self.destination = destination
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.groups)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def flags(self, index):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() in (1, 2, 3):
            base |= Qt.ItemIsEditable
        return base

    def data(self, index, role=Qt.DisplayRole):
        group = self.groups[index.row()]
        col = index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            if col == 0:
                return "⚠" if group.to_check else ""
            if col == 1:
                precision = "jour" if group.manual_date else group.date_precision
                text = format_date(group.effective_date, precision)
                if role == Qt.DisplayRole and group.manual_date:
                    text += "  ✎"
                return text
            if col == 2:
                return group.effective_place
            if col == 3:
                return group.effective_event
            if col == 4:
                active = len(group.active_items)
                return f"{active}" if active == len(group.items) else f"{active} / {len(group.items)}"
            if col == 5:
                return relative_to(group.target_dir, self.destination) if group.target_dir else "— (rien à classer)"
        if role == Qt.ForegroundRole:
            if col == 0:
                return QColor(WARNING)
            if col == 1 and group.effective_date is None:
                return QColor(WARNING)
            if col == 5 and not group.target_dir:
                return QColor("#8A94A0")
        if role == Qt.ToolTipRole:
            if col == 0 and group.to_check:
                return "Date à vérifier : absente, approximative ou tirée de la date du fichier."
            if col == 1:
                return "Double-cliquez pour saisir une date (JJ/MM/AAAA). Laissez vide pour revenir à la date trouvée."
            if col in (2, 3):
                return "Double-cliquez pour modifier."
        if role == Qt.TextAlignmentRole and col in (0, 4):
            return Qt.AlignCenter
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False
        group = self.groups[index.row()]
        text = str(value).strip()
        col = index.column()
        if col == 1:
            if not text or text == format_date(group.date, group.date_precision):
                group.manual_date = None
            else:
                found = find_date(text)
                if not found or found.precision not in ("jour", "heure"):
                    QMessageBox.warning(None, "Date", "Saisissez une date complète, par exemple 11/07/2001.")
                    return False
                group.manual_date = found.when.replace(hour=12, minute=0, second=0)
        elif col == 2:
            group.manual_place = None if text == group.place else text
        elif col == 3:
            group.manual_event = None if text == group.event else text
        else:
            return False
        self.edited.emit()
        return True

    def refresh(self):
        if self.groups:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.groups) - 1, len(self.HEADERS) - 1))


class FilesModel(QAbstractTableModel):
    HEADERS = ["Garder", "Fichier d'origine", "Date trouvée", "Lieu", "Nouveau nom"]
    toggled = Signal()

    def __init__(self):
        super().__init__()
        self.items: list[MediaItem] = []

    def set_items(self, items: list[MediaItem]):
        self.beginResetModel()
        self.items = items
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def flags(self, index):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            base |= Qt.ItemIsUserCheckable
        return base

    def data(self, index, role=Qt.DisplayRole):
        item = self.items[index.row()]
        col = index.column()
        if role == Qt.CheckStateRole and col == 0:
            return Qt.Unchecked if item.excluded else Qt.Checked
        if role == Qt.DisplayRole:
            if col == 1:
                extra = f"  (+{len(item.companions)})" if item.companions else ""
                return str(item.relative) + extra
            if col == 2:
                if item.date is None:
                    return "aucune"
                when = item.date.strftime("%d/%m/%Y %H:%M") if item.date_precision == "heure" \
                    else format_date(item.date, item.date_precision)
                return f"{when}  · {item.date_source}"
            if col == 3:
                return item.place
            if col == 4:
                if item.already_in_library:
                    return "déjà dans la photothèque"
                if item.excluded:
                    return "écarté (doublon)" if item.duplicate_of else "écarté"
                return item.target.name if item.target else ""
        if role == Qt.ForegroundRole:
            if col == 4 and (item.excluded or item.already_in_library):
                return QColor("#8A94A0")
            if col == 2 and (item.date is None or item.date_source == DATE_FILE):
                return QColor(WARNING)
        if role == Qt.FontRole and col == 4 and (item.excluded or item.already_in_library):
            font = QFont()
            font.setItalic(True)
            return font
        if role == Qt.ToolTipRole:
            if col == 1:
                lines = [str(item.path)] + [f"+ {c.name}" for c in item.companions]
                return "\n".join(lines)
            if col == 4 and item.duplicate_of:
                return f"Copie de {item.duplicate_of}"
            if col == 4 and item.already_in_library:
                return f"Déjà présent : {item.already_in_library}"
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole and index.column() == 0:
            item = self.items[index.row()]
            item.excluded = Qt.CheckState(value) != Qt.Checked
            if not item.excluded:
                item.duplicate_of = None
            self.toggled.emit()
            return True
        return False


class ReviewPage(Page):
    next_requested = Signal()
    changed = Signal()

    def __init__(self, settings):
        super().__init__("Vérification",
                         "Chaque ligne est un groupe de photos du même jour. Double-cliquez sur la date, le lieu "
                         "ou l'événement pour les modifier ; les lignes marquées ⚠ méritent un coup d'œil.")
        self.settings = settings
        self.analysis = None

        chips = QHBoxLayout()
        self.chips = [Chip(), Chip(), Chip(warning=True), Chip(warning=True)]
        for chip in self.chips:
            chips.addWidget(chip)
        chips.addStretch(1)
        chips.addWidget(QLabel("Afficher :"))
        self.filter = QComboBox()
        self.filter.addItems(FILTERS)
        self.filter.currentIndexChanged.connect(self.apply_filter)
        chips.addWidget(self.filter)
        self.layout.addLayout(chips)

        self.groups_model = GroupsModel()
        self.groups_model.edited.connect(self.on_edit)
        self.groups_view = QTableView()
        self.groups_view.setModel(self.groups_model)
        self.groups_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.groups_view.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.groups_view.verticalHeader().hide()
        self.groups_view.setAlternatingRowColors(False)
        header = self.groups_view.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.groups_view.setColumnWidth(0, 30)
        for col, width in ((1, 110), (2, 200), (3, 230), (4, 70)):
            self.groups_view.setColumnWidth(col, width)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.groups_view.selectionModel().selectionChanged.connect(self.show_group)

        actions = QHBoxLayout()
        self.set_event = QPushButton("Événement pour la sélection…")
        self.set_event.clicked.connect(self.bulk_event)
        self.set_date = QPushButton("Date pour la sélection…")
        self.set_date.clicked.connect(self.bulk_date)
        actions.addWidget(self.set_event)
        actions.addWidget(self.set_date)
        actions.addWidget(label("Astuce : Ctrl + clic ou Maj + clic pour sélectionner plusieurs groupes.", "hint"))
        actions.addStretch(1)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(self.groups_view)
        top_layout.addLayout(actions)

        self.files_model = FilesModel()
        self.files_model.toggled.connect(self.on_toggle)
        self.files_view = QTableView()
        self.files_view.setModel(self.files_model)
        self.files_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.files_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.files_view.verticalHeader().hide()
        fh = self.files_view.horizontalHeader()
        for col, width in ((0, 60), (1, 280), (2, 220), (3, 160)):
            self.files_view.setColumnWidth(col, width)
        fh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.files_view.selectionModel().selectionChanged.connect(self.show_file)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumWidth(300)
        self.preview.setStyleSheet("background: white; border: 1px solid #D9DEE5; border-radius: 6px;")
        self.preview_info = label("", "hint")
        preview_box = QWidget()
        pv = QVBoxLayout(preview_box)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.addWidget(self.preview, 1)
        pv.addWidget(self.preview_info)

        bottom = QSplitter(Qt.Horizontal)
        bottom.addWidget(self.files_view)
        bottom.addWidget(preview_box)
        bottom.setStretchFactor(0, 3)
        bottom.setStretchFactor(1, 1)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(top)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.layout.addWidget(splitter, 1)

        nav = QHBoxLayout()
        nav.addStretch(1)
        self.next = QPushButton("Continuer  →")
        self.next.setObjectName("primary")
        self.next.clicked.connect(self.next_requested)
        nav.addWidget(self.next)
        self.layout.addLayout(nav)

    # -- données -----------------------------------------------------------------------------

    def set_analysis(self, analysis):
        self.analysis = analysis
        self.replan()
        self.apply_filter()

    def entered(self):
        if self.analysis:
            self.replan()
            self.groups_model.refresh()
            self.update_chips()
            self.show_group()

    def replan(self):
        analyze.plan(self.analysis.groups, self.settings, check_disk=False)

    def update_chips(self):
        if not self.analysis:
            return
        stats = analyze.summary(self.analysis.groups)
        self.chips[0].setText(f"{stats['actifs']:,} photos à classer".replace(",", " "))
        self.chips[1].setText(f"{stats['groupes']:,} groupes · {stats['dossiers']:,} dossiers".replace(",", " "))
        self.chips[2].setText(f"⚠ {stats['a_verifier']} groupes à vérifier")
        self.chips[3].setText(f"{stats['sans_date']} sans date")
        self.chips[2].setVisible(stats["a_verifier"] > 0)
        self.chips[3].setVisible(stats["sans_date"] > 0)

    def apply_filter(self):
        if not self.analysis:
            return
        mode = self.filter.currentIndex()
        groups = self.analysis.groups
        if mode == 1:
            groups = [g for g in groups if g.to_check]
        elif mode == 2:
            groups = [g for g in groups if g.effective_date is None]
        elif mode == 3:
            groups = [g for g in groups if not g.effective_place]
        elif mode == 4:
            groups = [g for g in groups if any(i.excluded or i.already_in_library for i in g.items)]
        self.groups_model.set_groups(groups, self.settings.destination)
        self.update_chips()
        if groups:
            self.groups_view.selectRow(0)
        else:
            self.files_model.set_items([])
            self.preview.clear()

    def selected_groups(self) -> list[Group]:
        rows = sorted({i.row() for i in self.groups_view.selectionModel().selectedRows()})
        return [self.groups_model.groups[r] for r in rows]

    def show_group(self, *args):
        groups = self.selected_groups()
        self.files_model.set_items(groups[0].items if len(groups) == 1 else [i for g in groups for i in g.items])
        if self.files_model.items:
            self.files_view.selectRow(0)
        else:
            self.preview.clear()
            self.preview_info.setText("")

    def show_file(self, *args):
        rows = self.files_view.selectionModel().selectedRows()
        if not rows:
            return
        item = self.files_model.items[rows[0].row()]
        pixmap = thumbnail(item.path, 360)
        self.preview.setPixmap(pixmap)
        info = [item.name]
        if item.camera:
            info.append(item.camera)
        if item.width:
            info.append(f"{item.width} × {item.height}")
        if item.lat is not None:
            info.append(f"GPS {item.lat:.4f}, {item.lon:.4f}")
        self.preview_info.setText(" · ".join(info))

    # -- modifications -----------------------------------------------------------------------

    def on_edit(self):
        self.replan()
        self.groups_model.refresh()
        self.files_model.layoutChanged.emit()
        self.update_chips()
        self.changed.emit()

    def on_toggle(self):
        self.on_edit()

    def bulk_event(self):
        groups = self.selected_groups()
        if not groups:
            return
        text, ok = QInputDialog.getText(self, "Événement", f"Événement pour les {len(groups)} groupes sélectionnés :",
                                        text=groups[0].effective_event)
        if ok:
            for group in groups:
                group.manual_event = text.strip()
            self.on_edit()

    def bulk_date(self):
        groups = self.selected_groups()
        if not groups:
            return
        text, ok = QInputDialog.getText(self, "Date", f"Date pour les {len(groups)} groupes sélectionnés "
                                                      "(JJ/MM/AAAA, vide pour annuler la saisie) :")
        if not ok:
            return
        found = find_date(text) if text.strip() else None
        if text.strip() and (not found or found.precision not in ("jour", "heure")):
            QMessageBox.warning(self, "Date", "Saisissez une date complète, par exemple 11/07/2001.")
            return
        for group in groups:
            group.manual_date = found.when.replace(hour=12, minute=0, second=0) if found else None
        self.on_edit()
