"""Réglages de l'utilisateur, conservés d'une séance à l'autre."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .patterns import DEFAULT_PRESET, PRESETS

COPY = "copier"
MOVE = "deplacer"
GROUP_DAY = "jour"
GROUP_DAY_FOLDER = "jour_dossier"


@dataclass
class Settings:
    source: str = ""
    destination: str = ""
    recursive: bool = True
    include_photos: bool = True
    include_videos: bool = True
    mode: str = COPY

    folder_pattern: str = PRESETS[DEFAULT_PRESET][0]
    file_pattern: str = PRESETS[DEFAULT_PRESET][1]
    undated_folder: str = "_Sans date"
    group_by: str = GROUP_DAY_FOLDER

    use_file_date: bool = True          # date du fichier en dernier recours
    write_dates: bool = True            # écrire la date déduite dans les photos qui n'en ont pas
    place_max_km: float = 10.0
    event_from_folder: bool = True      # proposer le nom du dossier d'origine comme événement

    find_duplicates: bool = True
    duplicates_in_destination: bool = True
    similar_photos: bool = True         # chercher aussi les photos presque identiques (rafales)
    remove_empty_folders: bool = True   # après un déplacement

    recent_sources: list[str] = field(default_factory=list)

    @staticmethod
    def file() -> Path:
        base = os.environ.get("APPDATA") or str(Path.home() / ".config")
        return Path(base) / "TrieurPhotos" / "reglages.json"

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(cls.file().read_text(encoding="utf-8"))
            known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            return cls(**known)
        except Exception:
            return cls()

    def save(self):
        try:
            path = self.file()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass


def cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    path = Path(base) / "TrieurPhotos"
    path.mkdir(parents=True, exist_ok=True)
    return path
