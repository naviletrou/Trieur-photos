"""Données manipulées par le programme."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PHOTO_EXT = {".jpg", ".jpeg", ".jpe", ".heic", ".heif", ".png", ".tif", ".tiff", ".bmp", ".gif",
             ".webp", ".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".raf", ".pef", ".srw"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mts", ".m2ts", ".3gp", ".mkv", ".wmv", ".mpg", ".mpeg"}
RAW_EXT = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".raf", ".pef", ".srw"}
# fichiers qui accompagnent une photo et doivent suivre son nouveau nom
SIDECAR_EXT = {".xmp", ".aae", ".thm"}

# origine de la date retenue pour le classement
DATE_EXIF = "EXIF"
DATE_VIDEO = "Vidéo"
DATE_FILENAME = "Nom du fichier"
DATE_FOLDER = "Nom du dossier"
DATE_FILE = "Date du fichier"
DATE_MANUAL = "Manuelle"
DATE_NONE = "Aucune"
# dates jugées sûres : celles enregistrées par l'appareil
RELIABLE_DATES = {DATE_EXIF, DATE_VIDEO, DATE_MANUAL}

PLACE_GPS = "GPS"
PLACE_MANUAL = "Manuel"


@dataclass
class MediaItem:
    path: Path                       # fichier d'origine
    source_root: Path                # dossier choisi comme source
    size: int
    mtime: float                     # date de modification du fichier
    is_video: bool
    companions: list[Path] = field(default_factory=list)  # .xmp, .aae, vidéo d'une Live Photo
    ctime: float | None = None       # date de création du fichier (souvent la date de copie)

    # métadonnées lues
    exif_date: datetime | None = None
    lat: float | None = None
    lon: float | None = None
    camera: str = ""
    width: int = 0
    height: int = 0

    # date retenue
    date: datetime | None = None
    date_source: str = DATE_NONE
    date_precision: str = ""         # « heure », « jour », « mois », « année »

    # lieu retenu
    place: str = ""
    region: str = ""
    country: str = ""
    place_source: str = ""

    # texte du dossier d'origine (« Cheverny » dans « 2001-07-11 Cheverny »)
    folder_text: str = ""

    # empreintes pour les doublons
    sha1: str = ""
    dhash: int | None = None

    # résultat du classement
    group_key: tuple = ()
    target: Path | None = None
    excluded: bool = False           # décoché par l'utilisateur ou écarté comme doublon
    duplicate_of: Path | None = None  # doublon écarté au profit de ce fichier
    already_in_library: Path | None = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def relative(self) -> Path:
        try:
            return self.path.relative_to(self.source_root)
        except ValueError:
            return Path(self.path.name)

    @property
    def pixels(self) -> int:
        return (self.width or 0) * (self.height or 0)

    @property
    def date_reliable(self) -> bool:
        return self.date_source in RELIABLE_DATES

    @property
    def to_check(self) -> bool:
        """À vérifier : pas de date, date approximative ou date tirée de la date du fichier."""
        return self.date is None or self.date_source == DATE_FILE or self.date_precision in ("mois", "année")


@dataclass
class Group:
    """Ensemble de photos classées ensemble (même jour, même dossier d'origine)."""
    key: tuple
    items: list[MediaItem] = field(default_factory=list)
    date: datetime | None = None      # jour du groupe
    date_precision: str = "jour"
    place: str = ""
    region: str = ""
    country: str = ""
    event: str = ""
    # modifications faites par l'utilisateur dans l'écran de vérification
    manual_date: datetime | None = None
    manual_place: str | None = None
    manual_event: str | None = None
    target_dir: Path | None = None

    @property
    def effective_date(self) -> datetime | None:
        return self.manual_date or self.date

    @property
    def effective_place(self) -> str:
        return self.manual_place if self.manual_place is not None else self.place

    @property
    def effective_event(self) -> str:
        return self.manual_event if self.manual_event is not None else self.event

    @property
    def active_items(self) -> list[MediaItem]:
        return [i for i in self.items if not i.excluded]

    @property
    def to_check(self) -> bool:
        return self.manual_date is None and any(i.to_check for i in self.items)
