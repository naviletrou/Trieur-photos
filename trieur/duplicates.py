"""Détection des doublons.

Trois niveaux :
  * « Identiques »   : exactement le même fichier (même empreinte SHA-1), quel que soit son nom ;
  * « Même photo »   : la même image redimensionnée ou recompressée (empreinte visuelle quasi égale) ;
  * « Très proches » : photos presque identiques prises à moins de 2 minutes d'intervalle (rafales).
Les deux premiers niveaux proposent d'écarter les copies ; le troisième est seulement signalé.

Les empreintes sont gardées dans un cache pour que les analyses suivantes soient rapides.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from .model import DATE_EXIF, RAW_EXT, VIDEO_EXT, MediaItem, PHOTO_EXT
from .log import logger
from .settings import cache_dir

IDENTICAL = "Identiques"
SAME_PHOTO = "Même photo"
SIMILAR = "Très proches"

SAME_PHOTO_MAX = 6      # différences tolérées sur 128 bits pour « même photo »
SIMILAR_MAX = 22        # pour « très proches »
SIMILAR_SECONDS = 120   # écart de temps maximal pour « très proches »

Progress = Callable[[str, int, int], None]
Cancelled = Callable[[], bool]

try:
    from PIL import Image, ImageOps
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
except ImportError:  # pragma: no cover
    Image = None


@dataclass
class DuplicateGroup:
    kind: str
    items: list[MediaItem]
    keep: MediaItem
    library_matches: list[Path] = field(default_factory=list)  # déjà présents dans la destination


class HashCache:
    """Empreintes déjà calculées, retrouvées par chemin, taille et date de modification."""

    def __init__(self, path: Path | None = None):
        self.path = path or cache_dir() / "empreintes.sqlite"
        self.lock = threading.Lock()
        # timeout : une autre fenêtre du programme peut utiliser le cache au même moment
        self.db = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30)
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error:
            pass
        self.db.execute("CREATE TABLE IF NOT EXISTS h (path TEXT PRIMARY KEY, size INTEGER, mtime REAL, "
                        "sha1 TEXT, dhash TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS infos (path TEXT PRIMARY KEY, size INTEGER, mtime REAL, "
                        "width INTEGER, height INTEGER, taken TEXT)")

    def get(self, path: Path, size: int, mtime: float) -> tuple[str, int | None] | None:
        with self.lock:
            row = self.db.execute("SELECT size, mtime, sha1, dhash FROM h WHERE path=?", (str(path),)).fetchone()
        if row and row[0] == size and abs(row[1] - mtime) < 0.01:
            return row[2] or "", (int(row[3], 16) if row[3] else None)
        return None

    def put(self, path: Path, size: int, mtime: float, sha1: str, dhash: int | None):
        # le cache ne fait que gagner du temps : une erreur d'écriture ne doit jamais arrêter la recherche
        with self.lock:
            try:
                self.db.execute("INSERT OR REPLACE INTO h VALUES (?,?,?,?,?)",
                                (str(path), size, mtime, sha1, f"{dhash:032x}" if dhash is not None else None))
            except sqlite3.Error as error:
                logger.warning("  cache des empreintes indisponible (%s)", error)

    def get_info(self, path: Path, size: int, mtime: float) -> tuple[int, int, datetime | None] | None:
        with self.lock:
            row = self.db.execute("SELECT size, mtime, width, height, taken FROM infos WHERE path=?",
                                  (str(path),)).fetchone()
        if row and row[0] == size and abs(row[1] - mtime) < 0.01:
            return row[2] or 0, row[3] or 0, datetime.fromisoformat(row[4]) if row[4] else None
        return None

    def put_info(self, path: Path, size: int, mtime: float, width: int, height: int, taken: datetime | None):
        with self.lock:
            try:
                self.db.execute("INSERT OR REPLACE INTO infos VALUES (?,?,?,?,?,?)",
                                (str(path), size, mtime, width, height, taken.isoformat() if taken else None))
            except sqlite3.Error as error:
                logger.warning("  cache des empreintes indisponible (%s)", error)

    def commit(self):
        with self.lock:
            try:
                self.db.commit()
            except sqlite3.Error as error:
                logger.warning("  enregistrement du cache des empreintes impossible (%s)", error)

    def close(self):
        self.commit()
        try:
            self.db.close()
        except sqlite3.Error:
            pass


class Cancelled_(Exception):
    """Lecture interrompue par « Arrêter »."""


def sha1_of(path: Path, cancelled: Cancelled | None = None) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            if cancelled and cancelled():
                # une grosse vidéo sur le NAS peut prendre longtemps : on s'arrête tout de suite
                raise Cancelled_()
            digest.update(chunk)
    return digest.hexdigest()


def dhash_of(path: Path) -> int | None:
    """Empreinte visuelle de 128 bits (différences horizontales et verticales)."""
    return fingerprint(path)[0]


def _exif_date(exif) -> datetime | None:
    from .exiftool import parse_date
    try:
        sub = exif.get_ifd(0x8769)  # sous-répertoire EXIF
        for tag in (36867, 36868):  # DateTimeOriginal, DateTimeDigitized
            when = parse_date(sub.get(tag))
            if when:
                return when
    except Exception:
        pass
    return None


def fingerprint(path: Path) -> tuple[int | None, int, int, datetime | None]:
    """Empreinte visuelle, largeur, hauteur et date de prise de vue, en une seule lecture du fichier."""
    if Image is None or path.suffix.lower() in RAW_EXT or path.suffix.lower() in VIDEO_EXT:
        return None, 0, 0, None
    try:
        with Image.open(path) as image:
            width, height = image.size
            exif = image.getexif()
            taken = _exif_date(exif)
            if exif.get(274) in (5, 6, 7, 8):  # photo tournée d'un quart de tour
                width, height = height, width
            image.draft("L", (128, 128))  # décodage JPEG à taille réduite : bien plus rapide
            image = ImageOps.exif_transpose(image).convert("L")
            horizontal = np.asarray(image.resize((9, 8), Image.LANCZOS), dtype=np.int16)
            vertical = np.asarray(image.resize((8, 9), Image.LANCZOS), dtype=np.int16)
    except Exception:
        return None, 0, 0, None
    bits = np.concatenate([(horizontal[:, 1:] > horizontal[:, :-1]).ravel(),
                           (vertical[1:, :] > vertical[:-1, :]).ravel()])
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value, width, height, taken


def _split(value: int) -> tuple[int, int]:
    return (value >> 64) & 0xFFFFFFFFFFFFFFFF, value & 0xFFFFFFFFFFFFFFFF


COPY_NAME = re.compile(r"^(copie de |copy of )|( - copie| - copy|copie| copy)( \(\d+\))?$|\(\d+\)$", re.I)


def _place_score(item: MediaItem, preferred: Path | None) -> tuple:
    """Pour deux fichiers identiques : le mieux rangé.

    D'abord le dossier préféré choisi par l'utilisateur, puis un dossier daté ou nommé
    (« 2001-07-11 Cheverny ») plutôt qu'un dossier « Divers » ou « À trier », puis un nom
    d'origine plutôt qu'un nom de copie (« Copie de… », « IMG_1 (1).jpg »).
    """
    from .dates import find_date, is_generic_name, text_without_date
    in_preferred = False
    if preferred:
        try:
            item.path.relative_to(preferred)
            in_preferred = True
        except ValueError:
            pass
    folder = item.path.parent.name
    if find_date(folder) and not is_generic_name(text_without_date(folder) or folder):
        folder_quality = 2
    elif find_date(folder) or not is_generic_name(folder):
        folder_quality = 1
    else:
        folder_quality = 0
    original_name = not COPY_NAME.search(item.path.stem)
    return (in_preferred, folder_quality, original_name, -len(str(item.path)))


def _score(item: MediaItem, preferred: Path | None = None) -> tuple:
    """La meilleure version d'une photo : la plus grande, avec sa date d'origine, le plus gros fichier,
    puis la mieux rangée."""
    return (item.pixels, item.date_reliable, item.size) + _place_score(item, preferred)


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, a: int) -> int:
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a: int, b: int):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def library_files(destination: Path, sizes: set[int], cancelled: Cancelled | None = None,
                  progress: Progress | None = None) -> list[tuple[Path, int, float]]:
    """Fichiers déjà présents dans la destination dont la taille correspond à une photo à classer."""
    found = []
    seen = 0
    if not destination or not destination.exists():
        return found
    for root, dirs, files in os.walk(destination):
        if cancelled and cancelled():
            break
        dirs[:] = [d for d in dirs if d.lower() not in ("_doublons", "_journal") and not d.startswith(".")]
        seen += len(files)
        if progress:
            progress("Inventaire de la destination", seen, 0)
        for name in files:
            if os.path.splitext(name)[1].lower() not in PHOTO_EXT | VIDEO_EXT:
                continue
            path = Path(root) / name
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size in sizes:
                found.append((path, stat.st_size, stat.st_mtime))
    return found


def find_duplicates(items: list[MediaItem], destination: Path | None = None, similar: bool = True,
                    progress: Progress | None = None, cancelled: Cancelled | None = None,
                    cache: HashCache | None = None, preferred: Path | None = None,
                    detail: Callable[[str], None] | None = None) -> list[DuplicateGroup]:
    """preferred : dossier dont on garde les photos en priorité (mode « Doublons seuls »).
    detail : reçoit le nom du fichier en cours de lecture."""
    own_cache = cache is None
    cache = cache or HashCache()
    try:
        return _find(items, destination, similar, progress, cancelled, cache, preferred, detail)
    finally:
        if own_cache:
            cache.close()
        else:
            cache.commit()


def _find(items, destination, similar, progress, cancelled, cache, preferred=None, detail=None) -> list[DuplicateGroup]:
    def step(label, done, total):
        if progress:
            progress(label, done, total)

    # 1. empreintes SHA-1 : seulement pour les fichiers de même taille (les autres ne peuvent être identiques)
    by_size: dict[int, list[MediaItem]] = {}
    for item in items:
        by_size.setdefault(item.size, []).append(item)
    library = library_files(destination, set(by_size), cancelled, progress) if destination else []
    library_by_size: dict[int, list[tuple[Path, int, float]]] = {}
    for entry in library:
        library_by_size.setdefault(entry[1], []).append(entry)

    need_sha = [i for i in items if len(by_size[i.size]) > 1 or i.size in library_by_size]
    # 2. empreintes visuelles : toutes les photos
    need_visual = [i for i in items if not i.is_video and i.path.suffix.lower() not in RAW_EXT]
    work = {id(i): i for i in need_sha + need_visual}
    sha_ids = {id(i) for i in need_sha}
    visual_ids = {id(i) for i in need_visual}

    total = len(work)
    done = 0
    read_bytes = 0
    lock = threading.Lock()
    started = time.monotonic()
    logger.info("  %d fichiers à examiner (%d à comparer octet par octet)", total, len(need_sha))
    # tout de suite, sinon l'écran reste sur « Recherche des fichiers » pendant la lecture des premières photos
    step("Recherche des doublons", 0, total)

    def compute(item: MediaItem):
        nonlocal done, read_bytes
        if cancelled and cancelled():
            return
        begin = time.monotonic()
        cached = cache.get(item.path, item.size, item.mtime)
        if detail and not (cached and cached[0] and cached[1] is not None):
            detail(item.path.name)
        sha, dh = (cached if cached else ("", None))
        changed = False
        if id(item) in sha_ids and not sha:
            try:
                sha = sha1_of(item.path, cancelled)
                changed = True
            except OSError:
                sha = ""
        if id(item) in visual_ids:
            info = cache.get_info(item.path, item.size, item.mtime)
            if dh is None or info is None:
                dh, width, height, taken = fingerprint(item.path)
                changed = changed or dh is not None
                cache.put_info(item.path, item.size, item.mtime, width, height, taken)
            else:
                width, height, taken = info
            # dimensions et date de prise de vue, si ExifTool ne les a pas déjà données
            if not item.width and width:
                item.width, item.height = width, height
            if item.date is None and taken:
                item.exif_date = item.date = taken
                item.date_source, item.date_precision = DATE_EXIF, "heure"
        item.sha1, item.dhash = sha, dh
        if changed:
            cache.put(item.path, item.size, item.mtime, sha, dh)
        spent = time.monotonic() - begin
        if spent > 20:
            logger.info("  lecture lente (%.0f s) : %s", spent, item.path)
        with lock:
            done += 1
            if changed:
                read_bytes += item.size
            if done % 200 == 0:
                elapsed = max(time.monotonic() - started, 0.1)
                logger.info("  %d / %d fichiers, %.1f Mo/s", done, total, read_bytes / elapsed / 1e6)
                cache.commit()  # une analyse arrêtée garde ce qui a été calculé
        step("Recherche des doublons", done, total)

    def guarded(item: MediaItem):
        # une photo illisible ne doit jamais arrêter toute la recherche
        try:
            compute(item)
        except Cancelled_:
            pass
        except Exception as error:
            logger.warning("  fichier ignoré (%s) : %s", error, item.path)

    with ThreadPoolExecutor(max_workers=min(8, (os.cpu_count() or 2) + 2)) as pool:
        list(pool.map(guarded, work.values()))
    cache.commit()
    if cancelled and cancelled():
        return []

    groups: list[DuplicateGroup] = []
    grouped: set[int] = set()

    # identiques entre eux
    by_sha: dict[str, list[MediaItem]] = {}
    for item in items:
        if item.sha1:
            by_sha.setdefault(item.sha1, []).append(item)

    # identiques à une photo déjà dans la destination
    library_sha: dict[str, list[Path]] = {}
    for size, entries in library_by_size.items():
        if not any(i.sha1 for i in by_size.get(size, [])):
            continue
        for path, fsize, mtime in entries:
            cached = cache.get(path, fsize, mtime)
            sha = cached[0] if cached and cached[0] else ""
            if not sha:
                try:
                    sha = sha1_of(path)
                    cache.put(path, fsize, mtime, sha, cached[1] if cached else None)
                except OSError:
                    continue
            library_sha.setdefault(sha, []).append(path)
    cache.commit()

    for sha, members in by_sha.items():
        matches = library_sha.get(sha, [])
        # un fichier déjà à sa place dans la destination (dossier source = destination) n'est pas un doublon de lui-même
        matches = [m for m in matches if all(os.path.normcase(str(m)) != os.path.normcase(str(i.path)) for i in members)]
        if len(members) > 1 or matches:
            keep = max(members, key=lambda i: _place_score(i, preferred))
            groups.append(DuplicateGroup(IDENTICAL, sorted(members, key=lambda i: str(i.path)), keep, matches))
            grouped.update(id(i) for i in members)

    # même photo / très proches : comparaison des empreintes visuelles
    candidates = [i for i in items if i.dhash is not None]
    if len(candidates) > 1:
        high = np.array([_split(i.dhash)[0] for i in candidates], dtype=np.uint64)
        low = np.array([_split(i.dhash)[1] for i in candidates], dtype=np.uint64)
        # (date - 1970) plutôt que timestamp() : sous Windows, timestamp() échoue avant 1970
        epoch = datetime(1970, 1, 1)
        stamps = np.array([(i.date - epoch).total_seconds() if i.date and i.date_reliable else np.nan
                           for i in candidates])
        same = _UnionFind(len(candidates))
        close = _UnionFind(len(candidates))
        n = len(candidates)
        for a in range(n - 1):
            if cancelled and cancelled():
                return []
            dist = np.bitwise_count(high[a + 1:] ^ high[a]).astype(np.int32) + \
                np.bitwise_count(low[a + 1:] ^ low[a]).astype(np.int32)
            for b in np.nonzero(dist <= SAME_PHOTO_MAX)[0]:
                same.union(a, a + 1 + int(b))
            if similar and not np.isnan(stamps[a]):
                near = (dist <= SIMILAR_MAX) & (np.abs(stamps[a + 1:] - stamps[a]) <= SIMILAR_SECONDS)
                for b in np.nonzero(near)[0]:
                    close.union(a, a + 1 + int(b))
            if a % 500 == 0:
                step("Comparaison des images", a, n)

        def collect(uf: _UnionFind) -> list[list[MediaItem]]:
            sets: dict[int, list[MediaItem]] = {}
            for idx, item in enumerate(candidates):
                sets.setdefault(uf.find(idx), []).append(item)
            return [members for members in sets.values() if len(members) > 1]

        for members in collect(same):
            # les fichiers identiques sont déjà traités : on ne garde que les groupes qui apportent du nouveau
            distinct = {i.sha1 or id(i) for i in members}
            if len(distinct) < 2:
                continue
            # deux prises de vue d'heures différentes ne sont pas la même photo (rafale) : seulement signalées
            shots = {i.date.replace(microsecond=0) for i in members if i.date and i.date_reliable}
            if len(shots) > 1:
                if similar:
                    keep = max(members, key=lambda i: _score(i, preferred))
                    groups.append(DuplicateGroup(SIMILAR, sorted(members, key=lambda i: i.date or datetime.min), keep))
                    grouped.update(id(i) for i in members)
                continue
            keep = max(members, key=lambda i: _score(i, preferred))
            ids = {id(i) for i in members}
            # un groupe « identiques » entièrement compris dans celui-ci y est fusionné
            library_matches = []
            for other in [g for g in groups if g.kind == IDENTICAL and {id(i) for i in g.items} <= ids]:
                library_matches += other.library_matches
                groups.remove(other)
            groups.append(DuplicateGroup(SAME_PHOTO, sorted(members, key=lambda i: str(i.path)), keep, library_matches))
            grouped.update(ids)
        if similar:
            for members in collect(close):
                if all(id(i) in grouped for i in members):
                    continue
                keep = max(members, key=lambda i: _score(i, preferred))
                groups.append(DuplicateGroup(SIMILAR, sorted(members, key=lambda i: i.date or datetime.min), keep))
        step("Comparaison des images", n, n)

    order = {IDENTICAL: 0, SAME_PHOTO: 1, SIMILAR: 2}
    groups.sort(key=lambda g: (order[g.kind], str(g.keep.path)))
    return groups


def apply_default_choices(groups: list[DuplicateGroup]):
    """Choix proposés : écarter les copies identiques et les versions moins bonnes d'une même photo."""
    for group in groups:
        if group.kind in (IDENTICAL, SAME_PHOTO):
            for item in group.items:
                if item is not group.keep:
                    item.excluded = True
                    item.duplicate_of = group.keep.path
            if group.library_matches:
                # la photo est déjà rangée dans la destination : inutile de la reclasser
                group.keep.already_in_library = group.library_matches[0]


def find_already_sorted(groups, exiftool=None, cache: HashCache | None = None,
                        cancelled: Cancelled | None = None, progress: Progress | None = None) -> int:
    """Photos déjà rangées par un classement précédent dans leur dossier de destination.

    Après un premier classement, la date écrite dans les scans change leur empreinte SHA-1 :
    on les reconnaît alors à leur empreinte visuelle, dans le dossier où elles doivent aller,
    à condition que la date de prise de vue soit la même.
    Renvoie le nombre de photos reconnues (marquées already_in_library).
    """
    from .exiftool import parse_date
    own_cache = cache is None
    cache = cache or HashCache()
    found = 0
    try:
        for number, group in enumerate(groups, start=1):
            if cancelled and cancelled():
                break
            if progress and (number % 20 == 0 or number == len(groups)):
                progress("Recherche des photos déjà rangées", number, len(groups))
            folder = group.target_dir
            if not folder or not folder.is_dir():
                continue
            candidates = [i for i in group.items if not i.excluded and not i.already_in_library and i.dhash is not None]
            if not candidates:
                continue
            existing = []
            for path in folder.iterdir():
                if path.suffix.lower() not in PHOTO_EXT or path.suffix.lower() in RAW_EXT or not path.is_file():
                    continue
                stat = path.stat()
                cached = cache.get(path, stat.st_size, stat.st_mtime)
                dh = cached[1] if cached and cached[1] is not None else dhash_of(path)
                if dh is not None and not (cached and cached[1] is not None):
                    cache.put(path, stat.st_size, stat.st_mtime, cached[0] if cached else "", dh)
                if dh is not None:
                    existing.append((path, dh))
            if not existing:
                continue
            dates = {}
            if exiftool:
                meta = exiftool.read([p for p, _ in existing])
                for p, _ in existing:
                    entry = meta.get(os.path.normcase(os.path.normpath(str(p)))) or {}
                    dates[str(p)] = parse_date(entry.get("DateTimeOriginal")) or parse_date(entry.get("CreateDate"))
            for item in candidates:
                for path, dh in existing:
                    distance = bin(item.dhash ^ dh).count("1")
                    if distance > SAME_PHOTO_MAX:
                        continue
                    other = dates.get(str(path))
                    if item.date and other and item.date.replace(microsecond=0) != other and item.date_reliable:
                        continue  # autre prise de vue d'une rafale
                    item.already_in_library = path
                    found += 1
                    break
    finally:
        if own_cache:
            cache.close()
        else:
            cache.commit()
    return found
