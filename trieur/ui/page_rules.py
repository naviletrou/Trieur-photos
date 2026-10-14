"""Étape 2 : règles de classement (modèles de dossiers et de noms)."""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLineEdit,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..patterns import PRESETS, TOKENS, check_pattern, render_dirs, render_name, token_values
from ..settings import GROUP_DAY, GROUP_DAY_FOLDER, Settings
from .widgets import Card, FlowRow, Page, label

CUSTOM = "Personnalisé"


class RulesPage(Page):
    rules_changed = Signal(bool)  # True si l'analyse des dates et lieux doit être refaite
    next_requested = Signal()

    def __init__(self, settings: Settings):
        super().__init__("Classement",
                         "Choisissez comment nommer les dossiers et les fichiers. "
                         "L'exemple se met à jour avec vos propres photos.")
        self.settings = settings
        self.analysis = None
        self.last_field: QLineEdit | None = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("content")
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 8, 0)
        column.setSpacing(14)
        scroll.setWidget(body)
        self.layout.addWidget(scroll, 1)

        rules = Card("Modèle de classement")
        top = QHBoxLayout()
        top.addWidget(label("Modèle prêt à l'emploi :", wrap=False))
        self.preset = QComboBox()
        self.preset.addItems(list(PRESETS) + [CUSTOM])
        self.preset.currentTextChanged.connect(self.apply_preset)
        top.addWidget(self.preset, 1)
        rules.layout.addLayout(top)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.addWidget(label("Dossiers :", wrap=False), 0, 0)
        self.folders = QLineEdit()
        grid.addWidget(self.folders, 0, 1)
        grid.addWidget(label("Le signe « / » crée un sous-dossier.", "hint"), 1, 1)
        grid.addWidget(label("Noms des fichiers :", wrap=False), 2, 0)
        self.files = QLineEdit()
        grid.addWidget(self.files, 2, 1)
        grid.addWidget(label("L'extension (.jpg, .mp4…) est ajoutée automatiquement. "
                             "Si deux photos ont le même nom, « _2 », « _3 »… sont ajoutés.", "hint"), 3, 1)
        rules.layout.addLayout(grid)
        rules.add(label("Cliquez sur une étiquette pour l'insérer dans le champ sélectionné :", "hint"))
        buttons = []
        for token in TOKENS:
            button = QPushButton(token.label)
            button.setObjectName("token")
            button.setToolTip(f"{{{token.key}}}  —  exemple : {token.example}")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, key=token.key: self.insert_token(key))
            buttons.append(button)
        rules.add(FlowRow(buttons, per_row=8))
        self.pattern_error = label("", "warningBox")
        self.pattern_error.hide()
        rules.add(self.pattern_error)
        column.addWidget(rules)

        example = Card("Exemple avec vos photos")
        self.example = example.add(label("", "example"))
        self.example.setTextFormat(Qt.RichText)
        self.example.setTextInteractionFlags(Qt.TextSelectableByMouse)
        column.addWidget(example)

        options = Card("Options")
        self.group_by = QComboBox()
        self.group_by.addItem("par jour et par dossier d'origine (conseillé pour une archive déjà rangée)", GROUP_DAY_FOLDER)
        self.group_by.addItem("par jour seulement (photos du téléphone et de l'appareil réunies)", GROUP_DAY)
        row = QHBoxLayout()
        row.addWidget(label("Regrouper les photos :", wrap=False))
        row.addWidget(self.group_by, 1)
        options.layout.addLayout(row)
        self.event_from_folder = options.add(QCheckBox(
            "Proposer le nom des dossiers datés comme événement  (« 2001-07-11 Cheverny » → « Cheverny »)"))
        self.use_file_date = options.add(QCheckBox(
            "Sans date de prise de vue, utiliser la date du fichier  (souvent la date de copie : à vérifier)"))
        self.write_dates = options.add(QCheckBox(
            "Écrire la date trouvée dans les photos qui n'en ont pas  (scans… : Immich les classera au bon endroit)"))
        row = QHBoxLayout()
        row.addWidget(label("Lieu : commune la plus proche, à moins de", wrap=False))
        self.max_km = QDoubleSpinBox()
        self.max_km.setRange(0.5, 100)
        self.max_km.setDecimals(1)
        self.max_km.setSuffix(" km")
        row.addWidget(self.max_km)
        row.addWidget(label("de l'endroit de la photo", wrap=False))
        row.addStretch(1)
        options.layout.addLayout(row)
        column.addWidget(options)
        column.addStretch(1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.next = QPushButton("Vérifier le résultat  →")
        self.next.setObjectName("primary")
        self.next.clicked.connect(self.next_requested)
        bottom.addWidget(self.next)
        self.layout.addLayout(bottom)

        self.load()
        self.folders.installEventFilter(self)
        self.files.installEventFilter(self)
        self.last_field = self.folders
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.update_example)
        self.folders.textChanged.connect(self.pattern_edited)
        self.files.textChanged.connect(self.pattern_edited)
        self.group_by.currentIndexChanged.connect(lambda: self.options_changed(False))
        self.write_dates.toggled.connect(lambda: self.options_changed(False))
        for widget in (self.event_from_folder, self.use_file_date):
            widget.toggled.connect(lambda: self.options_changed(True))
        self.max_km.valueChanged.connect(lambda: self.options_changed(True))
        self.update_example()

    # -- réglages ----------------------------------------------------------------------------

    def load(self):
        s = self.settings
        self.folders.setText(s.folder_pattern)
        self.files.setText(s.file_pattern)
        self.sync_preset()
        self.group_by.setCurrentIndex(max(0, self.group_by.findData(s.group_by)))
        self.event_from_folder.setChecked(s.event_from_folder)
        self.use_file_date.setChecked(s.use_file_date)
        self.write_dates.setChecked(s.write_dates)
        self.max_km.setValue(s.place_max_km)

    def store(self):
        s = self.settings
        s.folder_pattern = self.folders.text().strip() or PRESETS[next(iter(PRESETS))][0]
        s.file_pattern = self.files.text().strip() or "{annee}-{mois}-{jour}_{heure}h{minute}"
        s.group_by = self.group_by.currentData()
        s.event_from_folder = self.event_from_folder.isChecked()
        s.use_file_date = self.use_file_date.isChecked()
        s.write_dates = self.write_dates.isChecked()
        s.place_max_km = self.max_km.value()
        s.save()

    def sync_preset(self):
        current = (self.folders.text().strip(), self.files.text().strip())
        name = next((n for n, p in PRESETS.items() if p == current), CUSTOM)
        self.preset.blockSignals(True)
        self.preset.setCurrentText(name)
        self.preset.blockSignals(False)

    def apply_preset(self, name: str):
        if name in PRESETS:
            folders, files = PRESETS[name]
            self.folders.setText(folders)
            self.files.setText(files)

    def eventFilter(self, obj, event):
        if event.type() == event.Type.FocusIn and obj in (self.folders, self.files):
            self.last_field = obj
        return super().eventFilter(obj, event)

    def insert_token(self, key: str):
        field = self.last_field or self.folders
        field.insert(f"{{{key}}}")
        field.setFocus()

    def pattern_edited(self):
        self.sync_preset()
        unknown = check_pattern(self.folders.text()) + check_pattern(self.files.text())
        self.pattern_error.setText("Étiquette inconnue : " + ", ".join("{" + u + "}" for u in unknown)
                                   if unknown else "")
        self.pattern_error.setVisible(bool(unknown))
        self.timer.start()

    def options_changed(self, needs_resolve: bool):
        self.store()
        self.rules_changed.emit(needs_resolve)
        self.timer.start()

    def set_analysis(self, analysis):
        self.analysis = analysis
        self.update_example()

    # -- exemple -----------------------------------------------------------------------------

    def sample_groups(self):
        if not self.analysis:
            return []
        dated = [g for g in self.analysis.groups if g.effective_date and g.active_items]
        picks = []
        for test in (lambda g: g.effective_place and g.effective_event,
                     lambda g: g.effective_place,
                     lambda g: g.effective_event,
                     lambda g: True):
            found = next((g for g in dated if test(g) and g not in picks), None)
            if found:
                picks.append(found)
            if len(picks) == 2:
                break
        return picks

    def update_example(self):
        self.store()
        s = self.settings
        lines = []
        groups = self.sample_groups()
        if not groups:
            from datetime import datetime
            values = token_values(datetime(2001, 7, 11, 14, 32, 5), "heure", place="Cheverny",
                                  region="Loir-et-Cher", country="France", event="Visite du château",
                                  camera="Canon PowerShot A70", original="IMG_1234", counter=1)
            samples = [(render_dirs(s.folder_pattern, values), [(render_name(s.file_pattern, values) + ".jpg", "IMG_1234.jpg")])]
        else:
            samples = []
            for group in groups:
                precision = "jour" if group.manual_date else group.date_precision
                values = token_values(group.effective_date, precision, place=group.effective_place,
                                      region=group.region, country=group.country, event=group.effective_event)
                files = []
                for counter, item in enumerate(group.active_items[:2], start=1):
                    v = token_values(item.date, item.date_precision, place=item.place or group.effective_place,
                                     region=item.region or group.region, country=item.country or group.country,
                                     event=group.effective_event, camera=item.camera, original=item.path.stem,
                                     counter=counter)
                    files.append(((render_name(s.file_pattern, v) or item.path.stem) + item.path.suffix.lower(),
                                  str(item.relative)))
                samples.append((render_dirs(s.folder_pattern, values), files))
        shown_dirs: list[str] = []
        for dirs, files in samples:
            # même règle que le classement : « _2 », « _3 »… pour les noms identiques
            seen: dict[str, int] = {}
            unique = []
            for name, original in files:
                stem, dot, ext = name.rpartition(".")
                count = seen.get(name.lower(), 0) + 1
                seen[name.lower()] = count
                unique.append((f"{stem}_{count}.{ext}" if count > 1 else name, original))
            files = unique
            for depth, name in enumerate(dirs):
                key = "/".join(dirs[:depth + 1])
                if key not in shown_dirs:
                    shown_dirs.append(key)
                    lines.append("&nbsp;" * (depth * 4) + "📁 " + html.escape(name))
            for name, original in files:
                lines.append("&nbsp;" * (len(dirs) * 4) + "🖼 " + html.escape(name) +
                             f"   <span style='color:#5F6B7A'>← {html.escape(original)}</span>")
        self.example.setText("<br>".join(lines) if lines else "—")
