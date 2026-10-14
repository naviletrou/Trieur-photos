"""Éléments d'interface communs."""
from __future__ import annotations

from PySide6.QtCore import QDir, Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)


def label(text: str, name: str | None = None, wrap: bool = True) -> QLabel:
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


class Card(QFrame):
    """Cadre blanc à bords arrondis, avec un titre facultatif."""

    def __init__(self, title: str = "", hint: str = ""):
        super().__init__()
        self.setObjectName("card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(18, 16, 18, 16)
        self.layout.setSpacing(10)
        if title:
            self.layout.addWidget(label(title, "cardTitle"))
        if hint:
            self.layout.addWidget(label(hint, "hint"))

    def add(self, widget):
        self.layout.addWidget(widget)
        return widget


class Page(QWidget):
    """Page de l'assistant avec un titre et une introduction."""

    def __init__(self, title: str, intro: str = ""):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(32, 26, 32, 22)
        self.layout.setSpacing(14)
        self.layout.addWidget(label(title, "pageTitle"))
        if intro:
            self.layout.addWidget(label(intro, "pageIntro"))

    def entered(self):
        """Appelée quand la page devient visible."""


class PathPicker(QWidget):
    changed = Signal(str)

    def __init__(self, placeholder: str, dialog_title: str):
        super().__init__()
        self.dialog_title = dialog_title
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self.changed)
        button = QPushButton("Parcourir…")
        button.clicked.connect(self.browse)
        row.addWidget(self.edit, 1)
        row.addWidget(button)

    def browse(self):
        folder = QFileDialog.getExistingDirectory(self, self.dialog_title, self.edit.text())
        if folder:
            self.edit.setText(QDir.toNativeSeparators(folder))

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, text: str):
        self.edit.setText(text)


class Chip(QLabel):
    def __init__(self, text: str = "", warning: bool = False):
        super().__init__(text)
        self.setObjectName("chipWarning" if warning else "chip")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


class FlowRow(QWidget):
    """Rangée de boutons qui passe à la ligne si la place manque."""

    def __init__(self, widgets: list[QWidget], per_row: int = 8):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        for start in range(0, len(widgets), per_row):
            row = QHBoxLayout()
            row.setSpacing(6)
            for widget in widgets[start:start + per_row]:
                row.addWidget(widget)
            row.addStretch(1)
            outer.addLayout(row)
