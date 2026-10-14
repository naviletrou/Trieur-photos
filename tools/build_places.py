"""Fabrique data/lieux.csv.gz, la base des lieux utilisée hors connexion.

Avec les fichiers GeoNames (https://download.geonames.org/export/dump/, licence CC BY 4.0) :
    python tools/build_places.py geonames DOSSIER_GEONAMES
        DOSSIER_GEONAMES contient cities500.txt, FR.txt, admin1CodesASCII.txt, admin2Codes.txt
Pour les essais, à partir du fichier rg_cities1000.csv du paquet reverse_geocoder :
    python tools/build_places.py rg rg_cities1000.csv

Colonnes produites : lat, lon, nom, département ou région, pays (en français).
"""
from __future__ import annotations

import csv
import gzip
import re
import sys
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "lieux.csv.gz"
ARRONDISSEMENT = re.compile(r"^(Paris|Lyon|Marseille) \d{1,2}\b")
DEPT_PREFIX = re.compile(r"^(D[ée]partement|Department)\s+(de la |de l'|de l’|du |des |de |d'|d’)", re.I)


def country_names() -> dict[str, str]:
    try:
        from babel import Locale
        return {code: name for code, name in Locale("fr").territories.items() if len(code) == 2}
    except Exception:
        return {"FR": "France"}


def clean_region(name: str) -> str:
    return DEPT_PREFIX.sub("", name).strip()


def write(rows):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["lat", "lon", "nom", "region", "pays"])
        for row in rows:
            writer.writerow([f"{row[0]:.5f}", f"{row[1]:.5f}", row[2], row[3], row[4]])
    print(f"{len(rows)} lieux écrits dans {OUTPUT}")


def read_geonames(path: Path):
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            yield line.rstrip("\n").split("\t")


def from_geonames(folder: Path):
    countries = country_names()
    admin1 = {}
    for cols in read_geonames(folder / "admin1CodesASCII.txt"):
        admin1[cols[0]] = cols[1]
    admin2 = {}
    for cols in read_geonames(folder / "admin2Codes.txt"):
        admin2[cols[0]] = cols[1]

    rows = []
    # France : toutes les communes (ADM4) et les villes principales
    for c in read_geonames(folder / "FR.txt"):
        fclass, fcode = c[6], c[7]
        name = c[1]
        wanted = (fclass == "A" and fcode == "ADM4") or (fclass == "P" and fcode in ("PPLC", "PPLA", "PPLA2"))
        # arrondissements de Paris, Lyon et Marseille : sinon une photo de la tour Eiffel
        # serait placée à Neuilly, plus proche que le centre de Paris
        arrondissement = ARRONDISSEMENT.match(name)
        if fclass == "P" and fcode == "PPLX" and arrondissement:
            wanted, name = True, arrondissement.group(1)
        if wanted:
            dept = admin2.get(f"FR.{c[10]}.{c[11]}", "")
            rows.append((float(c[4]), float(c[5]), name, clean_region(dept), "France"))
    # reste du monde : villes de plus de 500 habitants
    for c in read_geonames(folder / "cities500.txt"):
        cc = c[8]
        if cc == "FR":
            continue
        region = admin1.get(f"{cc}.{c[10]}", "")
        rows.append((float(c[4]), float(c[5]), c[1], region, countries.get(cc, cc)))
    write(rows)


def from_rg(path: Path):
    countries = country_names()
    rows = []
    with open(path, encoding="utf-8") as handle:
        for r in csv.DictReader(handle):
            region = clean_region(r["admin2"]) if r["cc"] == "FR" and r["admin2"] else r["admin1"]
            rows.append((float(r["lat"]), float(r["lon"]), r["name"], region, countries.get(r["cc"], r["cc"])))
    write(rows)


if __name__ == "__main__":
    mode, source = sys.argv[1], Path(sys.argv[2])
    if mode == "geonames":
        from_geonames(source)
    else:
        from_rg(source)
