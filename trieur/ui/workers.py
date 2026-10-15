"""Travaux longs exécutés en arrière-plan pour ne pas figer la fenêtre."""
from __future__ import annotations

import time
import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .. import analyze, executor
from ..duplicates import HashCache, apply_default_choices, find_already_sorted, find_duplicates
from ..exiftool import ExifTool
from ..log import error_text, logger
from ..places import get_index
from ..settings import TASK_DUPLICATES, Settings


class Worker(QThread):
    progress = Signal(str, int, int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._cancel = False
        self._step = ""
        self._step_start = 0.0

    def cancel(self):
        if not self._cancel:
            logger.info("Arrêt demandé par l'utilisateur")
        self._cancel = True

    def cancelled(self) -> bool:
        return self._cancel

    def report(self, label: str, done: int, total: int):
        if label != self._step:
            now = time.monotonic()
            if self._step:
                logger.info("  fin de « %s » en %.1f s", self._step, now - self._step_start)
            logger.info("Étape : %s", label)
            self._step, self._step_start = label, now
        self.progress.emit(label, done, total)

    def run(self):
        start = time.monotonic()
        logger.info("Début : %s", self.__class__.__name__)
        try:
            result = self.work()
            self.report("Terminé", 0, 0)
            logger.info("Fin : %s en %.1f s%s", self.__class__.__name__, time.monotonic() - start,
                        " (arrêté)" if self._cancel else "")
            self.done.emit(result)
        except Exception as error:  # affiché à l'utilisateur
            logger.error("Erreur pendant %s :\n%s", self.__class__.__name__, error_text(error))
            traceback.print_exc()
            self.failed.emit(f"{error.__class__.__name__} : {error}")

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
        logger.info("Source : %s · destination : %s · mode : %s · doublons : %s (destination : %s)",
                    s.source, s.destination, s.mode, s.find_duplicates, s.duplicates_in_destination)
        self.report("Recherche des fichiers", 0, 0)
        items = analyze.scan(s, self.report, self.cancelled)
        logger.info("  %d fichiers trouvés", len(items))
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
                self.report("Préparation du classement", 0, 0)
                groups = analyze.build_groups(items, s)
                analyze.plan(groups, s, check_disk=False)
                logger.info("  %d groupes, %d groupes de doublons", len(groups), len(duplicates))
                if s.duplicates_in_destination:
                    self.report("Recherche des photos déjà rangées", 0, 0)
                    found = find_already_sorted(groups, et, cache, self.cancelled, self.report)
                    logger.info("  %d photos déjà rangées", found)
            finally:
                cache.close()
        return Analysis(s, items, groups, duplicates)


class DuplicatesOnlyWorker(Worker):
    """Mode « Doublons seuls » : aucune lecture ExifTool, une seule lecture de chaque photo."""

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

    def work(self) -> Analysis | None:
        s = self.settings
        logger.info("Doublons seuls : %s · dossier préféré : %s", s.source, s.preferred_folder or "-")
        self.report("Recherche des fichiers", 0, 0)
        items = analyze.scan(s, self.report, self.cancelled)
        logger.info("  %d fichiers trouvés", len(items))
        if self.cancelled():
            return None
        preferred = Path(s.preferred_folder) if s.preferred_folder else None
        cache = HashCache()
        try:
            duplicates = find_duplicates(items, None, s.similar_photos, self.report, self.cancelled, cache,
                                         preferred=preferred)
        finally:
            cache.close()
        if self.cancelled():
            return None
        apply_default_choices(duplicates)
        logger.info("  %d groupes de doublons", len(duplicates))
        return Analysis(s, items, [], duplicates)


class ExecuteWorker(Worker):
    def __init__(self, analysis: Analysis):
        super().__init__()
        self.analysis = analysis

    def work(self):
        s = self.analysis.settings
        if s.task == TASK_DUPLICATES:
            return executor.execute_duplicates(self.analysis.items, Path(s.source), self.report, self.cancelled)
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
