"""Recherche d'une date dans un nom de fichier ou de dossier.

Reconnaît par exemple : « IMG_20190812_143201.jpg », « 2001-07-11 Cheverny »,
« 2001 05 10 - Levignen », « 20010711 », « 1985 » ou « Juillet 2001 ».
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre"]
MONTHS_FR_TITLE = [m.capitalize() for m in MONTHS_FR]


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


# année, mois, jour séparés ou non (« 2001-07-11 », « 2001 07 11 », « 20010711 »)
# et heure facultative (« _143201 », « 14h32 », « 14.32.01 »)
_FULL = re.compile(
    r"(?<!\d)(?P<y>19\d{2}|20\d{2})(?P<s1>[-_. ]?)(?P<m>0[1-9]|1[0-2])(?P=s1)(?P<d>0[1-9]|[12]\d|3[01])(?!\d)"
    r"(?:[-_ T.]{0,3}(?P<H>[01]\d|2[0-3])[h:._-]?(?P<M>[0-5]\d)(?:[m:._-]?(?P<S>[0-5]\d)(?:\d{3})?)?(?!\d))?"
)
# jour, mois, année à la française (« 11-07-2001 », « 11.07.2001 »)
_FULL_FR = re.compile(
    r"(?<!\d)(?P<d>0[1-9]|[12]\d|3[01])(?P<s1>[-_. ])(?P<m>0[1-9]|1[0-2])(?P=s1)(?P<y>19\d{2}|20\d{2})(?!\d)"
)
# année et mois seulement (« 2001-07 », « 2001 07 »)
_YEAR_MONTH = re.compile(r"(?<!\d)(?P<y>19\d{2}|20\d{2})[-_. ](?P<m>0[1-9]|1[0-2])(?!\d)")
# mois en toutes lettres (« juillet 2001 »)
_MONTH_NAME = re.compile(
    r"(?<![a-z])(?P<mn>" + "|".join(strip_accents(m) for m in MONTHS_FR) + r")\s+(?P<y>19\d{2}|20\d{2})(?!\d)"
)
# année seule (« 1985 », « Noël 1985 »)
_YEAR = re.compile(r"(?<![0-9a-z])(?P<y>19\d{2}|20\d{2})(?![0-9a-z])")


@dataclass
class FoundDate:
    when: datetime
    precision: str  # « heure », « jour », « mois » ou « année »
    start: int      # position du texte de la date dans le nom
    end: int


def _valid(y: int, m: int, d: int) -> bool:
    try:
        datetime(y, m, d)
    except ValueError:
        return False
    return 1826 <= y <= datetime.now().year + 1


def find_date(name: str, year_only: bool = True) -> FoundDate | None:
    """Cherche la date la plus précise contenue dans un nom.

    year_only : accepter une année seule (« 1985 Noël »). À éviter pour les noms de fichiers,
    où « IMG_2005.jpg » est un numéro de photo et non l'année 2005.
    """
    plain = strip_accents(unicodedata.normalize("NFC", name)).lower()
    for match in _FULL.finditer(plain):
        y, m, d = int(match["y"]), int(match["m"]), int(match["d"])
        if not _valid(y, m, d):
            continue
        if match["H"] is not None:
            when = datetime(y, m, d, int(match["H"]), int(match["M"]), int(match["S"] or 0))
            return FoundDate(when, "heure", match.start(), match.end())
        return FoundDate(datetime(y, m, d, 12, 0, 0), "jour", match.start(), match.end())
    for match in _FULL_FR.finditer(plain):
        y, m, d = int(match["y"]), int(match["m"]), int(match["d"])
        if _valid(y, m, d):
            return FoundDate(datetime(y, m, d, 12, 0, 0), "jour", match.start(), match.end())
    for match in _YEAR_MONTH.finditer(plain):
        y, m = int(match["y"]), int(match["m"])
        if _valid(y, m, 1):
            return FoundDate(datetime(y, m, 1, 12, 0, 0), "mois", match.start(), match.end())
    for match in _MONTH_NAME.finditer(plain):
        y = int(match["y"])
        m = [strip_accents(x) for x in MONTHS_FR].index(match["mn"]) + 1
        if _valid(y, m, 1):
            return FoundDate(datetime(y, m, 1, 12, 0, 0), "mois", match.start(), match.end())
    for match in _YEAR.finditer(plain) if year_only else []:
        y = int(match["y"])
        if _valid(y, 1, 1):
            return FoundDate(datetime(y, 1, 1, 12, 0, 0), "année", match.start(), match.end())
    return None


def text_without_date(name: str) -> str:
    """Le texte d'un nom de dossier sans sa date : « 2001-07-11 Cheverny » → « Cheverny »."""
    name = unicodedata.normalize("NFC", name)
    found = find_date(name)
    text = name
    if found:
        text = name[:found.start] + " " + name[found.end:]
    text = re.sub(r"[_]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -_.,;+")


def is_generic_name(text: str) -> bool:
    """Noms de dossiers sans intérêt comme événement (« DCIM », « 100CANON », « Photos »...)."""
    plain = strip_accents(text).lower().strip()
    if not plain or len(plain) < 2:
        return True
    if re.fullmatch(r"\d+[a-z_]*|[a-z_]*\d+|img|dcim|camera|photos?|images?|videos?|scans?|"
                    r"divers|nouveau dossier|new folder|export|download|downloads|telechargements|"
                    r"whatsapp.*|screenshots?|captures? d'ecran|sans titre|untitled|import.*|a trier|tri|nouveau tri|"
                    r"vrac|temp|tmp|backup|sauvegardes?|copies?|doublons?|recuperation|recup|old|ancien", plain):
        return True
    return False
