"""Exécution du classement, journal des opérations et annulation.

Chaque opération est inscrite immédiatement dans un journal CSV (dossier _Journal de la
destination). Le journal permet d'annuler le classement, même après une coupure.
"""
from __future__ import annotations

import csv
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .analyze import companion_target
from .exiftool import ExifTool
from .model import DATE_FILENAME, DATE_FOLDER, Group, MediaItem
from .settings import MOVE, Settings

Progress = Callable[[str, int, int], None]
Cancelled = Callable[[], bool]

COPY_OP = "copie"
MOVE_OP = "deplacement"
DUPLICATE_OP = "doublon"
DATE_OP = "date"
DIR_CREATED = "dossier_cree"
DIR_REMOVED = "dossier_supprime"
JOURNAL_DIR = "_Journal"
DUPLICATES_DIR = "_Doublons"
# formats dans lesquels ExifTool sait écrire une date
WRITABLE = {".jpg", ".jpeg", ".jpe", ".tif", ".tiff", ".png", ".heic", ".heif", ".webp", ".dng",
            ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".pef", ".mp4", ".mov", ".m4v", ".3gp"}


@dataclass
class Result:
    copied: int = 0
    moved: int = 0
    duplicates_moved: int = 0
    dates_written: int = 0
    folders_removed: int = 0
    errors: list[str] = field(default_factory=list)
    journal: Path | None = None
    cancelled: bool = False


class Journal:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        self.handle = open(path, "a", encoding="utf-8-sig" if new else "utf-8", newline="")
        self.writer = csv.writer(self.handle, delimiter=";")
        if new:
            self.writer.writerow(["action", "origine", "destination", "taille", "detail"])

    def write(self, action: str, source: Path | str = "", target: Path | str = "", size: int | str = "", detail: str = ""):
        self.writer.writerow([action, str(source), str(target), size, detail])
        self.handle.flush()

    def close(self):
        self.handle.close()


def date_to_write(item: MediaItem, group: Group) -> datetime | None:
    """Date à écrire dans le fichier : déduite du nom ou saisie à la main, jamais celle du fichier."""
    if item.date_reliable:
        return None
    if group.manual_date:
        return group.manual_date.replace(hour=12, minute=0, second=0)
    # seulement les dates connues au jour près : écrire « 1er janvier 1985 » pour une photo
    # dont on ne connaît que l'année la ferait passer, plus tard, pour une date sûre
    if item.date_source in (DATE_FILENAME, DATE_FOLDER) and item.date and item.date_precision in ("jour", "heure"):
        return item.date
    return None


def _free_path(path: Path) -> Path:
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def execute(groups: list[Group], settings: Settings, exiftool: ExifTool | None = None,
            progress: Progress | None = None, cancelled: Cancelled | None = None) -> Result:
    destination = Path(settings.destination)
    stamp = datetime.now().strftime("%Y-%m-%d_%Hh%M")
    result = Result(journal=destination / JOURNAL_DIR / f"classement_{stamp}.csv")
    journal = Journal(result.journal)
    journal.write("debut", settings.source, settings.destination, "", f"mode={settings.mode}")
    move = settings.mode == MOVE
    created_dirs: set[str] = set()

    def ensure_dir(folder: Path):
        missing = []
        current = folder
        while not current.exists():
            missing.append(current)
            current = current.parent
        for d in reversed(missing):
            d.mkdir(exist_ok=True)
            if str(d) not in created_dirs:
                created_dirs.add(str(d))
                journal.write(DIR_CREATED, "", d)

    def transfer(source: Path, target: Path) -> Path:
        ensure_dir(target.parent)
        target = _free_path(target)
        size = source.stat().st_size
        if move:
            shutil.move(str(source), str(target))
            journal.write(MOVE_OP, source, target, size)
        else:
            shutil.copy2(str(source), str(target))
            if target.stat().st_size != size:
                raise OSError(f"copie incomplète de {source}")
            journal.write(COPY_OP, source, target, size)
        return target

    work = [(g, i) for g in groups for i in g.items]
    total = len(work)
    try:
        for done, (group, item) in enumerate(work, start=1):
            if cancelled and cancelled():
                result.cancelled = True
                break
            if progress and (done % 10 == 0 or done == total):
                progress("Classement des photos", done, total)
            try:
                if item.target and not item.excluded and not item.already_in_library:
                    item.target = transfer(item.path, item.target)  # nom réel, en cas de conflit de dernière minute
                    target = item.target
                    for companion in item.companions:
                        if companion.exists():
                            transfer(companion, companion_target(item, companion))
                    if move:
                        result.moved += 1
                    else:
                        result.copied += 1
                    when = date_to_write(item, group) if settings.write_dates else None
                    if when and exiftool and target.suffix.lower() in WRITABLE:
                        if exiftool.write_date(target, when, item.is_video):
                            result.dates_written += 1
                            journal.write(DATE_OP, "", target, "", when.strftime("%Y-%m-%d %H:%M:%S"))
                        else:
                            result.errors.append(f"Date non écrite dans {target.name}")
                elif move and (item.duplicate_of or item.already_in_library):
                    # en déplacement, les doublons écartés sont mis de côté, jamais supprimés
                    aside_base = Path(settings.duplicates_folder) if settings.duplicates_folder \
                        else destination / DUPLICATES_DIR
                    aside = aside_base / stamp / item.relative
                    ensure_dir(aside.parent)
                    aside = _free_path(aside)
                    shutil.move(str(item.path), str(aside))
                    journal.write(DUPLICATE_OP, item.path, aside, item.size,
                                  f"doublon de {item.duplicate_of or item.already_in_library}")
                    for companion in item.companions:
                        if companion.exists():
                            c_aside = _free_path(aside.parent / companion.name)
                            shutil.move(str(companion), str(c_aside))
                            journal.write(DUPLICATE_OP, companion, c_aside, "", "fichier associé")
                    result.duplicates_moved += 1
            except Exception as error:  # une erreur sur un fichier n'arrête pas le classement
                result.errors.append(f"{item.path} : {error}")
                journal.write("erreur", item.path, item.target or "", "", str(error))

        if move and settings.remove_empty_folders and not result.cancelled:
            result.folders_removed = remove_empty_dirs(Path(settings.source), journal)
    finally:
        journal.write("fin", "", "", "", f"erreurs={len(result.errors)}")
        journal.close()
    return result


def remove_empty_dirs(root: Path, journal: Journal | None = None) -> int:
    removed = 0
    for current, dirs, files in os.walk(root, topdown=False):
        path = Path(current)
        if path == root:
            continue
        try:
            if not any(path.iterdir()):
                path.rmdir()
                removed += 1
                if journal:
                    journal.write(DIR_REMOVED, path, "")
        except OSError:
            pass
    return removed


def read_journal(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def undo(journal_path: Path, progress: Progress | None = None) -> Result:
    """Remet les fichiers à leur place d'origine d'après le journal."""
    rows = read_journal(journal_path)
    result = Result(journal=journal_path)
    # fichiers dont nous avons nous-mêmes modifié la date : leur taille a changé depuis la copie
    dated = {row["destination"] for row in rows if row["action"] == DATE_OP}
    total = len(rows)
    for done, row in enumerate(reversed(rows), start=1):
        if progress and (done % 10 == 0 or done == total):
            progress("Annulation du classement", done, total)
        action = row["action"]
        source = Path(row["origine"]) if row["origine"] else None
        target = Path(row["destination"]) if row["destination"] else None
        try:
            if action == COPY_OP and target and target.exists():
                size = row.get("taille") or ""
                if not size or row["destination"] in dated or target.stat().st_size == int(size):
                    target.unlink()
                    result.copied += 1
                else:
                    result.errors.append(f"{target} a été modifié depuis le classement : il est conservé")
            elif action in (MOVE_OP, DUPLICATE_OP) and target and target.exists() and source:
                source.parent.mkdir(parents=True, exist_ok=True)
                back = _free_path(source)
                shutil.move(str(target), str(back))
                result.moved += 1
            elif action == DIR_CREATED and target and target.exists():
                try:
                    target.rmdir()  # seulement s'il est vide
                except OSError:
                    pass
            elif action == DIR_REMOVED and source:
                source.mkdir(parents=True, exist_ok=True)
        except Exception as error:
            result.errors.append(f"{target or source} : {error}")
    try:
        journal_path.rename(journal_path.with_name(journal_path.stem + "_annule.csv"))
    except OSError:
        pass
    return result


def execute_duplicates(items: list[MediaItem], library: Path, progress: Progress | None = None,
                       cancelled: Cancelled | None = None, aside_base: Path | None = None) -> Result:
    """Mode « Doublons seuls » : met de côté les doublons écartés dans « _Doublons » de la photothèque.

    Le chemin d'origine est conservé sous _Doublons/<date>/ pour savoir d'où vient chaque fichier.
    Rien n'est supprimé, et le journal permet de tout remettre en place.
    aside_base : dossier choisi par l'utilisateur, par exemple en dehors de la photothèque pour
    qu'Immich ne voie jamais les doublons (par défaut : « _Doublons » dans la photothèque).
    """
    stamp = datetime.now().strftime("%Y-%m-%d_%Hh%M")
    result = Result(journal=library / JOURNAL_DIR / f"doublons_{stamp}.csv")
    journal = Journal(result.journal)
    journal.write("debut", library, "", "", "mode=doublons")
    aside_root = (aside_base or library / DUPLICATES_DIR) / stamp
    work = [i for i in items if i.excluded and i.duplicate_of]
    try:
        for done, item in enumerate(work, start=1):
            if cancelled and cancelled():
                result.cancelled = True
                break
            if progress and (done % 10 == 0 or done == len(work)):
                progress("Mise de côté des doublons", done, len(work))
            try:
                aside = _free_path(aside_root / item.relative)
                aside.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item.path), str(aside))
                journal.write(DUPLICATE_OP, item.path, aside, item.size, f"doublon de {item.duplicate_of}")
                for companion in item.companions:
                    if companion.exists():
                        c_aside = _free_path(aside.parent / companion.name)
                        shutil.move(str(companion), str(c_aside))
                        journal.write(DUPLICATE_OP, companion, c_aside, "", "fichier associé")
                result.duplicates_moved += 1
            except Exception as error:
                result.errors.append(f"{item.path} : {error}")
                journal.write("erreur", item.path, "", "", str(error))
    finally:
        journal.write("fin", "", "", "", f"erreurs={len(result.errors)}")
        journal.close()
    return result


def write_report(groups, path: Path):
    """Liste des doublons au format CSV (s'ouvre dans Excel)."""
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["groupe", "type", "décision", "fichier", "dossier", "taille (octets)",
                         "largeur", "hauteur", "date de prise de vue"])
        for number, group in enumerate(groups, start=1):
            for item in group.items:
                decision = "garder" if not item.excluded else "écarter"
                if item is group.keep:
                    decision += " (meilleure version)"
                writer.writerow([number, group.kind, decision, item.name, str(item.path.parent), item.size,
                                 item.width or "", item.height or "",
                                 item.date.strftime("%d/%m/%Y %H:%M") if item.date and item.date_reliable else ""])
