"""Nom du lieu à partir des coordonnées GPS, sans connexion internet.

La base des lieux (communes françaises et villes du monde, d'après GeoNames,
licence CC BY 4.0) est fournie avec le programme dans data/lieux.csv.gz.
"""
from __future__ import annotations

import csv
import gzip
import io
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .exiftool import app_dir

EARTH_RADIUS_KM = 6371.0
CELL = 0.5  # taille des cases de la grille de recherche, en degrés


@dataclass(frozen=True)
class Place:
    name: str        # commune ou ville
    region: str      # département (France) ou région
    country: str     # pays, en français
    distance_km: float


def data_file() -> Path | None:
    for base in (app_dir() / "data", app_dir() / "_internal" / "data"):
        candidate = base / "lieux.csv.gz"
        if candidate.exists():
            return candidate
    return None


class PlaceIndex:
    """Recherche du lieu le plus proche dans une grille de cases de 0,5°."""

    def __init__(self, rows: list[tuple[float, float, str, str, str]]):
        self.names = [r[2] for r in rows]
        self.regions = [r[3] for r in rows]
        self.countries = [r[4] for r in rows]
        self.lat = np.radians(np.array([r[0] for r in rows], dtype=np.float64))
        self.lon = np.radians(np.array([r[1] for r in rows], dtype=np.float64))
        cells: dict[tuple[int, int], list[int]] = {}
        for i, r in enumerate(rows):
            cells.setdefault(self._cell(r[0], r[1]), []).append(i)
        self.cells = {k: np.array(v, dtype=np.int64) for k, v in cells.items()}

    @staticmethod
    def _cell(lat: float, lon: float) -> tuple[int, int]:
        return int(math.floor(lat / CELL)), int(math.floor(lon / CELL))

    @classmethod
    def load(cls, path: Path | None = None) -> "PlaceIndex | None":
        path = path or data_file()
        if not path or not path.exists():
            return None
        rows = []
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            for row in csv.reader(handle):
                if not row or row[0] == "lat":
                    continue
                rows.append((float(row[0]), float(row[1]), row[2], row[3], row[4]))
        return cls(rows)

    def nearest(self, lat: float, lon: float, max_km: float = 10.0) -> Place | None:
        if lat is None or lon is None or (lat == 0 and lon == 0):
            return None
        cy, cx = self._cell(lat, lon)
        # nombre de cases à parcourir autour du point pour couvrir max_km
        span_lat = int(math.ceil(max_km / 111.0 / CELL))
        span_lon = int(math.ceil(max_km / (111.0 * max(math.cos(math.radians(lat)), 0.05)) / CELL))
        candidates = [self.cells[(y, x)]
                      for y in range(cy - span_lat, cy + span_lat + 1)
                      for x in range(cx - span_lon, cx + span_lon + 1)
                      if (y, x) in self.cells]
        if not candidates:
            return None
        idx = np.concatenate(candidates)
        plat, plon = math.radians(lat), math.radians(lon)
        dlat = self.lat[idx] - plat
        dlon = self.lon[idx] - plon
        a = np.sin(dlat / 2) ** 2 + math.cos(plat) * np.cos(self.lat[idx]) * np.sin(dlon / 2) ** 2
        dist = 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.minimum(a, 1.0)))
        best = int(np.argmin(dist))
        if dist[best] > max_km:
            return None
        i = int(idx[best])
        return Place(self.names[i], self.regions[i], self.countries[i], float(dist[best]))


_index: PlaceIndex | None = None
_loaded = False


def get_index() -> PlaceIndex | None:
    """Base des lieux, chargée une seule fois."""
    global _index, _loaded
    if not _loaded:
        _loaded = True
        _index = PlaceIndex.load()
    return _index
