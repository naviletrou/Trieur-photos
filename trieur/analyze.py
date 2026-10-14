"""Analyse des fichiers : recherche, métadonnées, date, lieu, regroupement et plan de classement."""
from __future__ import annotations

import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import dates as dt
from .exiftool import ExifTool, parse_date
from .model import (DATE_EXIF, DATE_FILE, DATE_FILENAME, DATE_FOLDER, DATE_MANUAL, DATE_VIDEO, PHOTO_EXT,
                    PLACE_GPS, RAW_EXT, SIDECAR_EXT, VIDEO_EXT, Group, MediaItem)
from .patterns import render_dirs, render_name, token_values
from .places import PlaceIndex
from .settings import GROUP_DAY, Settings

Progress = Callable[[str, int, int], None]  # (étape, fait, total)
Cancelled = Callable[[], bool]

# dossiers jamais parcourus
SKIP_DIRS = {"_doublons", "_journal", "@eadir", "$recycle.bin", "system volume information",
             ".thumbnails", ".trash", ".picasaoriginals", "#recycle"}
# appareils qui enregistrent la date de numérisation et non celle de la photo
SCANNER_RE = re.compile(r"scan|perfection|plustek|reflecta|coolscan|opticfilm|wolverine|kodak scanza|"
                        r"veho smartfix|imagelock|filmscan", re.I)


def _norm(path: Path | str) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


# ---------------------------------------------------------------------------------------------
# Recherche des fichiers
# ---------------------------------------------------------------------------------------------

def scan(settings: Settings, progress: Progress | None = None, cancelled: Cancelled | None = None) -> list[MediaItem]:
    source = Path(settings.source)
    destination = _norm(settings.destination) if settings.destination else None
    wanted = set()
    if settings.include_photos:
        wanted |= PHOTO_EXT
    if settings.include_videos:
        wanted |= VIDEO_EXT

    items: list[MediaItem] = []
    walker = os.walk(source) if settings.recursive else [(str(source), [], os.listdir(source))]
    for root, dirs, files in walker:
        if cancelled and cancelled():
            break
        # ne pas descendre dans les dossiers techniques ni dans la destination
        dirs[:] = sorted(d for d in dirs
                         if d.lower() not in SKIP_DIRS and not d.startswith(".")
                         and not (destination and _norm(Path(root) / d) == destination))
        if not settings.recursive:
            files = [f for f in files if (Path(root) / f).is_file()]
        items.extend(_items_in_folder(Path(root), sorted(files), source, wanted))
        if progress:
            progress("Recherche des fichiers", len(items), 0)
    return items


def _media_stem(name: str) -> str:
    """« IMG_1.JPG.xmp » → « img_1 » ; « IMG_1.xmp » → « img_1 »."""
    stem, ext = os.path.splitext(name)
    if ext.lower() in SIDECAR_EXT:
        inner, inner_ext = os.path.splitext(stem)
        if inner_ext.lower() in PHOTO_EXT | VIDEO_EXT:
            stem = inner
    return stem.casefold()


def _items_in_folder(folder: Path, files: list[str], source: Path, wanted: set[str]) -> list[MediaItem]:
    by_stem: dict[str, list[str]] = {}
    for name in files:
        if name.startswith("."):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in wanted or ext in SIDECAR_EXT or ext in PHOTO_EXT | VIDEO_EXT:
            by_stem.setdefault(_media_stem(name), []).append(name)

    items = []
    for names in by_stem.values():
        exts = {n: os.path.splitext(n)[1].lower() for n in names}
        photos = [n for n in names if exts[n] in PHOTO_EXT - RAW_EXT and exts[n] in wanted]
        raws = [n for n in names if exts[n] in RAW_EXT and exts[n] in wanted]
        videos = [n for n in names if exts[n] in VIDEO_EXT and exts[n] in wanted]
        sidecars = [n for n in names if exts[n] in SIDECAR_EXT]

        primaries: list[str]
        companions: list[str] = []
        if photos:
            # JPEG + RAW ou HEIC + vidéo d'une Live Photo : un seul élément, les autres suivent
            primaries = photos[:1]
            companions = photos[1:] + raws + videos
        elif raws:
            primaries, companions = raws[:1], raws[1:] + videos
        else:
            primaries = videos
        if not primaries:
            continue
        companions += sidecars
        for i, name in enumerate(primaries):
            path = folder / name
            try:
                stat = path.stat()
            except OSError:
                continue
            items.append(MediaItem(
                path=path,
                source_root=source,
                size=stat.st_size,
                mtime=stat.st_mtime,
                is_video=exts[name] in VIDEO_EXT,
                companions=[folder / c for c in companions] if i == 0 else [],
            ))
    return items


# ---------------------------------------------------------------------------------------------
# Métadonnées, date et lieu
# ---------------------------------------------------------------------------------------------

def read_metadata(items: list[MediaItem], exiftool: ExifTool, progress: Progress | None = None,
                  cancelled: Cancelled | None = None):
    total = len(items)
    meta = exiftool.read([i.path for i in items],
                         progress=(lambda done: progress("Lecture des dates et des lieux", done, total)) if progress else None,
                         cancelled=cancelled)
    for item in items:
        entry = meta.get(_norm(item.path))
        if entry:
            apply_metadata(item, entry)


def apply_metadata(item: MediaItem, entry: dict):
    make = str(entry.get("Make") or "").strip()
    model = str(entry.get("Model") or "").strip()
    item.camera = model if make and model.lower().startswith(make.split()[0].lower()) else f"{make} {model}".strip()
    scanner = bool(SCANNER_RE.search(f"{make} {model}"))
    if item.is_video:
        keys = ("CreateDate", "MediaCreateDate", "TrackCreateDate", "DateTimeOriginal")
    else:
        keys = ("DateTimeOriginal", "CreateDate")
    if not scanner:
        for key in keys:
            when = parse_date(entry.get(key))
            if when:
                item.exif_date = when
                break
    try:
        lat, lon = entry.get("GPSLatitude"), entry.get("GPSLongitude")
        if lat is not None and lon is not None:
            item.lat, item.lon = float(lat), float(lon)
    except (TypeError, ValueError):
        pass
    for attr, key in (("width", "ImageWidth"), ("height", "ImageHeight")):
        try:
            setattr(item, attr, int(entry.get(key) or 0))
        except (TypeError, ValueError):
            pass
    if entry.get("Orientation") in (5, 6, 7, 8):
        item.width, item.height = item.height, item.width


def _parent_folders(item: MediaItem) -> list[Path]:
    """Dossiers d'origine, du plus proche au plus lointain, jusqu'au dossier source compris."""
    folders = []
    folder = item.path.parent
    root = _norm(item.source_root)
    while True:
        folders.append(folder)
        if _norm(folder) == root or folder.parent == folder:
            break
        folder = folder.parent
    return folders


def resolve(items: list[MediaItem], settings: Settings, index: PlaceIndex | None):
    for item in items:
        resolve_item(item, settings, index)


def resolve_item(item: MediaItem, settings: Settings, index: PlaceIndex | None):
    parents = _parent_folders(item)
    # date
    item.date, item.date_source, item.date_precision = None, "", ""
    if item.exif_date:
        item.date, item.date_source, item.date_precision = item.exif_date, DATE_VIDEO if item.is_video else DATE_EXIF, "heure"
    else:
        found = dt.find_date(item.path.stem, year_only=False)
        if found:
            item.date, item.date_source, item.date_precision = found.when, DATE_FILENAME, found.precision
        else:
            for folder in parents:
                found = dt.find_date(folder.name)
                if found:
                    item.date, item.date_source, item.date_precision = found.when, DATE_FOLDER, found.precision
                    break
        if item.date is None and settings.use_file_date:
            item.date, item.date_source, item.date_precision = datetime.fromtimestamp(item.mtime), DATE_FILE, "jour"
    if item.date is None:
        item.date_source = "Aucune"

    # événement proposé : texte d'un dossier d'origine daté (« 2001-07-11 Cheverny » → « Cheverny »).
    # Les dossiers sans date (« Téléphone », « DCIM »...) sont des rangements, pas des événements.
    item.folder_text = ""
    if settings.event_from_folder:
        for folder in parents:
            if not dt.find_date(folder.name):
                continue
            text = dt.text_without_date(folder.name)
            if text and not dt.is_generic_name(text) and text.casefold() not in MONTH_NAMES:
                item.folder_text = text
            break

    # lieu d'après le GPS
    item.place = item.region = item.country = item.place_source = ""
    if index and item.lat is not None:
        place = index.nearest(item.lat, item.lon, settings.place_max_km)
        if place:
            item.place, item.region, item.country, item.place_source = place.name, place.region, place.country, PLACE_GPS


MONTH_NAMES = {m.casefold() for m in dt.MONTHS_FR} | {dt.strip_accents(m).casefold() for m in dt.MONTHS_FR}


# ---------------------------------------------------------------------------------------------
# Regroupement
# ---------------------------------------------------------------------------------------------

_PRECISION_ORDER = {"heure": 0, "jour": 1, "mois": 2, "année": 3}


def build_groups(items: list[MediaItem], settings: Settings, previous: dict[tuple, Group] | None = None) -> list[Group]:
    """Regroupe les photos par jour (et par dossier d'origine selon le réglage).

    previous : groupes d'une analyse précédente, pour conserver les saisies de l'utilisateur.
    """
    groups: dict[tuple, Group] = {}
    for item in items:
        folder = _norm(item.path.parent)
        if item.date is None:
            key = ("sans_date", folder)
        else:
            precision = item.date_precision if item.date_precision in ("mois", "année") else "jour"
            day = {"jour": item.date.strftime("%Y-%m-%d"), "mois": item.date.strftime("%Y-%m"),
                   "année": item.date.strftime("%Y")}[precision]
            key = (day, None if settings.group_by == GROUP_DAY else folder)
        item.group_key = key
        groups.setdefault(key, Group(key=key)).items.append(item)

    for key, group in groups.items():
        group.items.sort(key=lambda i: (i.date or datetime.min, i.path.name.casefold()))
        dated = [i for i in group.items if i.date]
        if dated:
            group.date = min(i.date for i in dated)
            group.date_precision = max((i.date_precision for i in dated), key=lambda p: _PRECISION_ORDER.get(p, 1))
            if group.date_precision == "heure":
                group.date_precision = "jour"
        places = Counter(i.place for i in group.items if i.place)
        if places:
            group.place = places.most_common(1)[0][0]
            first = next(i for i in group.items if i.place == group.place)
            group.region, group.country = first.region, first.country
        texts = Counter(i.folder_text for i in group.items if i.folder_text)
        group.event = texts.most_common(1)[0][0] if texts else ""
        if previous and key in previous:
            old = previous[key]
            group.manual_date, group.manual_place, group.manual_event = old.manual_date, old.manual_place, old.manual_event

    return sorted(groups.values(), key=lambda g: (g.effective_date is None, g.effective_date or datetime.min,
                                                  str(g.key[1] or "")))


# ---------------------------------------------------------------------------------------------
# Plan de classement : chemin de destination de chaque photo
# ---------------------------------------------------------------------------------------------

def plan(groups: list[Group], settings: Settings, check_disk: bool = True):
    """Calcule le chemin de destination de chaque photo (item.target)."""
    destination = Path(settings.destination)
    taken: set[str] = set()
    sources = {_norm(i.path) for g in groups for i in g.items}

    def free(path: Path) -> bool:
        key = _norm(path)
        if key in taken:
            return False
        if check_disk and key not in sources and path.exists():
            return False
        return True

    for group in groups:
        group.target_dir = None
        active = [i for i in group.items if not i.excluded and not i.already_in_library]
        for item in group.items:
            item.target = None
        if not active:
            continue
        when = group.effective_date
        if when is None:
            # sans date : on garde le dossier et le nom d'origine, rangés à part
            relative_dir = active[0].relative.parent
            target_dir = destination / settings.undated_folder / relative_dir
        else:
            precision = "jour" if group.manual_date else group.date_precision
            values = token_values(when, precision, place=group.effective_place, region=group.region,
                                  country=group.country, event=group.effective_event)
            target_dir = destination.joinpath(*render_dirs(settings.folder_pattern, values))
        group.target_dir = target_dir

        for counter, item in enumerate(active, start=1):
            if when is None:
                stem = item.path.stem
            else:
                item_when, item_precision = item.date, item.date_precision
                if group.manual_date and not item.date_reliable:
                    item_when, item_precision = group.manual_date, "jour"
                if item_precision == "jour" and item.date_source == DATE_FILE:
                    item_precision = "jour"
                values = token_values(item_when, item_precision,
                                      place=item.place or group.effective_place,
                                      region=item.region or group.region,
                                      country=item.country or group.country,
                                      event=group.effective_event, camera=item.camera,
                                      original=item.path.stem, counter=counter)
                stem = render_name(settings.file_pattern, values) or item.path.stem
            ext = item.path.suffix.lower()
            candidate = target_dir / f"{stem}{ext}"
            n = 2
            while not free(candidate):
                candidate = target_dir / f"{stem}_{n}{ext}"
                n += 1
            taken.add(_norm(candidate))
            item.target = candidate


def companion_target(item: MediaItem, companion: Path) -> Path:
    """Nouveau nom d'un fichier associé : même nom que la photo, avec sa propre extension."""
    target_stem = item.target.stem
    name = companion.name
    lower = name.lower()
    for ext in SIDECAR_EXT:
        if lower.endswith(ext):
            inner = name[: -len(ext)]
            inner_ext = os.path.splitext(inner)[1]
            if inner_ext.lower() in PHOTO_EXT | VIDEO_EXT:
                # « IMG_1.JPG.xmp » → « nouveau.jpg.xmp »
                return item.target.with_name(f"{target_stem}{item.target.suffix}{ext}")
            return item.target.with_name(f"{target_stem}{ext}")
    return item.target.with_name(f"{target_stem}{companion.suffix.lower()}")


def summary(groups: list[Group]) -> dict:
    items = [i for g in groups for i in g.items]
    active = [i for i in items if not i.excluded and not i.already_in_library]
    return {
        "total": len(items),
        "actifs": len(active),
        "sans_date": sum(1 for i in items if i.date is None),
        "a_verifier": sum(1 for g in groups if g.to_check),
        "sans_lieu": sum(1 for i in items if not i.place),
        "groupes": len(groups),
        "dossiers": len({_norm(g.target_dir) for g in groups if g.target_dir}),
        "ecartes": sum(1 for i in items if i.excluded),
        "deja_presents": sum(1 for i in items if i.already_in_library),
        "dates_a_ecrire": sum(1 for i in active if i.date and not i.date_reliable and i.date_source != DATE_FILE),
    }
