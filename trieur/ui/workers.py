"""Travaux longs exécutés en arrière-plan pour ne pas figer la fenêtre."""
from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .. import analyze, executor
from ..duplicates import HashCache, apply_default_choices, find_already_sorted, find_duplicates
from ..exiftool import ExifTool
from ..places import get_index
from ..settings import Settings


class Worker(QThread):
    progress = Signal(str, int, int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def cancelled(self) -> bool:
        return self._cancel

    def report(self, label: str, done: int, total: int):
        self.progress.emit(label, done, total)

    def run(self):
        try:
            self.done.emit(self.work())
        except Exception as error:  # affiché à l'utilisateur
            traceback.print_exc()
            self.failed.emit(str(error) or error.__class__.__name__)

    def work(self):
        raise NotImplementedError


class Analysis:
    """Résultat d'une analyse."""

    def __init__(self, settings: Settings, items, groups, duplicates):
        self.settings = settings
        self.items = items
        self.groups = groups
        self.duplicates = duplicates


class AnalysisWorker(Worker):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

    def work(self) -> Analysis | None:
        s = self.settings
        self.report("Recherche des fichiers", 0, 0)
        items = analyze.scan(s, self.report, self.cancelled)
        if self.cancelled():
            return None
        with ExifTool() as et:
            self.report("Lecture des dates et des lieux", 0, len(items))
            analyze.read_metadata(items, et, self.report, self.cancelled)
            if self.cancelled():
                return None
            self.report("Recherche des lieux", 0, 0)
            analyze.resolve(items, s, get_index())
            duplicates = []
            cache = HashCache()
            try:
                if s.find_duplicates:
                    duplicates = find_duplicates(items, Path(s.destination) if s.duplicates_in_destination else None,
                                                 s.similar_photos, self.report, self.cancelled, cache)
                    apply_default_choices(duplicates)
                if self.cancelled():
                    return None
                groups = analyze.build_groups(items, s)
                analyze.plan(groups, s, check_disk=False)
                if s.duplicates_in_destination:
                    self.report("Recherche des photos déjà rangées", 0, 0)
                    find_already_sorted(groups, et, cache, self.cancelled)
            finally:
                cache.close()
        return Analysis(s, items, groups, duplicates)


class ExecuteWorker(Worker):
    def __init__(self, analysis: Analysis):
        super().__init__()
        self.analysis = analysis

    def work(self):
        s = self.analysis.settings
        self.report("Préparation", 0, 0)
        analyze.plan(self.analysis.groups, s, check_disk=True)
        with ExifTool() as et:
            return executor.execute(self.analysis.groups, s, et, self.report, self.cancelled)


class UndoWorker(Worker):
    def __init__(self, journal: Path):
        super().__init__()
        self.journal = journal

    def work(self):
        return executor.undo(self.journal, self.report)
