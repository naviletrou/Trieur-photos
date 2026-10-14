"""Modèles de noms de dossiers et de fichiers.

Un modèle mélange du texte et des étiquettes entre accolades, par exemple
« {annee}/{mois} - {mois_nom}/{annee}-{mois}-{jour} {lieu} - {evenement} ».
Le « / » sépare les niveaux de dossiers.

Quand une étiquette est vide (pas de lieu, pas d'événement...), le texte qui la
sépare des autres disparaît avec elle : « 2001-07-11 {lieu} - {evenement} » donne
« 2001-07-11 - Anniversaire » sans lieu, et « 2001-07-11 Cheverny » sans événement.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

from .dates import MONTHS_FR_TITLE, strip_accents

DAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


@dataclass(frozen=True)
class Token:
    key: str
    label: str
    example: str


TOKENS = [
    Token("annee", "Année", "2001"),
    Token("mois", "Mois", "07"),
    Token("mois_nom", "Nom du mois", "Juillet"),
    Token("jour", "Jour", "11"),
    Token("jour_nom", "Jour de la semaine", "Mercredi"),
    Token("heure", "Heure", "14"),
    Token("minute", "Minute", "32"),
    Token("seconde", "Seconde", "05"),
    Token("lieu", "Lieu", "Cheverny"),
    Token("departement", "Département / région", "Loir-et-Cher"),
    Token("pays", "Pays", "France"),
    Token("evenement", "Événement", "Visite du château"),
    Token("appareil", "Appareil photo", "Canon EOS 450D"),
    Token("nom_origine", "Nom d'origine", "IMG_1234"),
    Token("compteur", "Numéro", "001"),
]
TOKEN_KEYS = {t.key for t in TOKENS}

PRESETS = {
    "Année / Mois / Jour Lieu - Événement": (
        "{annee}/{mois} - {mois_nom}/{annee}-{mois}-{jour} {lieu} - {evenement}",
        "{annee}-{mois}-{jour}_{heure}h{minute}_{lieu}",
    ),
    "Année / Jour Lieu - Événement": (
        "{annee}/{annee}-{mois}-{jour} {lieu} - {evenement}",
        "{annee}-{mois}-{jour}_{heure}h{minute}_{lieu}",
    ),
    "Année / Mois / Jour": (
        "{annee}/{mois} - {mois_nom}/{jour}",
        "{annee}-{mois}-{jour}_{heure}h{minute}m{seconde}",
    ),
    "Année / Mois (sans sous-dossier)": (
        "{annee}/{mois} - {mois_nom}",
        "{annee}-{mois}-{jour}_{heure}h{minute}_{lieu}",
    ),
}
DEFAULT_PRESET = "Année / Mois / Jour Lieu - Événement"

_TOKEN_RE = re.compile(r"\{([a-z_]+)\}")
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
MAX_COMPONENT = 120


def normalize_for_compare(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", strip_accents(text).lower()).strip()


def token_values(when: datetime | None, precision: str, place: str = "", region: str = "",
                 country: str = "", event: str = "", camera: str = "", original: str = "",
                 counter: int | None = None) -> dict[str, str]:
    """Valeurs des étiquettes pour une photo. Les parties de date inconnues restent vides."""
    values = {k: "" for k in TOKEN_KEYS}
    if when:
        values["annee"] = f"{when.year:04d}"
        if precision in ("mois", "jour", "heure"):
            values["mois"] = f"{when.month:02d}"
            values["mois_nom"] = MONTHS_FR_TITLE[when.month - 1]
        if precision in ("jour", "heure"):
            values["jour"] = f"{when.day:02d}"
            values["jour_nom"] = DAYS_FR[when.weekday()]
        if precision == "heure":
            values["heure"] = f"{when.hour:02d}"
            values["minute"] = f"{when.minute:02d}"
            values["seconde"] = f"{when.second:02d}"
    values.update(lieu=place, departement=region, pays=country, evenement=event,
                  appareil=camera, nom_origine=original)
    if counter is not None:
        values["compteur"] = f"{counter:03d}"
    return values


def _render_component(component: str, values: dict[str, str]) -> str:
    # pas de lieu en double quand l'événement le contient déjà (« Cheverny » / « Château de Cheverny »)
    if "{lieu}" in component and "{evenement}" in component and values.get("lieu") and values.get("evenement") \
            and normalize_for_compare(values["lieu"]) in normalize_for_compare(values["evenement"]):
        values = {**values, "lieu": ""}
    parts: list[tuple[bool, str]] = []  # (est une étiquette, texte)
    pos = 0
    for match in _TOKEN_RE.finditer(component):
        if match.start() > pos:
            parts.append((False, component[pos:match.start()]))
        key = match.group(1)
        parts.append((True, values.get(key, "") if key in TOKEN_KEYS else match.group(0)))
        pos = match.end()
    if pos < len(component):
        parts.append((False, component[pos:]))

    tokens_present = [text for is_token, text in parts if is_token]
    if not tokens_present:
        return component
    if not any(tokens_present):
        return ""

    token_indexes = [i for i, (is_token, _) in enumerate(parts) if is_token]
    first_token, last_token = token_indexes[0], token_indexes[-1]
    result = ""
    pending = ""
    for i, (is_token, text) in enumerate(parts):
        if not is_token:
            if i < first_token:
                result += text  # texte avant la première étiquette : toujours gardé
            elif i > last_token:
                if parts[last_token][1]:
                    result += text  # texte après la dernière étiquette, si elle est remplie
            else:
                pending = text  # séparateur : seul le dernier avant une étiquette remplie compte
            continue
        if text:
            if result and pending:
                result += pending
            result += text
            pending = ""
    return result


def sanitize(component: str) -> str:
    """Nom de dossier ou de fichier valable sous Windows."""
    text = unicodedata.normalize("NFC", component)
    text = _FORBIDDEN.sub("-", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.rstrip(". ")
    if len(text) > MAX_COMPONENT:
        text = text[:MAX_COMPONENT].rstrip(" .-_")
    if text.upper().split(".")[0] in _RESERVED:
        text = "_" + text
    return text


def render_dirs(pattern: str, values: dict[str, str]) -> list[str]:
    """Niveaux de dossiers produits par un modèle (les niveaux vides sont supprimés)."""
    dirs = []
    for component in pattern.replace("\\", "/").split("/"):
        rendered = sanitize(_render_component(component, values))
        if rendered:
            dirs.append(rendered)
    return dirs


def render_name(pattern: str, values: dict[str, str]) -> str:
    """Nom de fichier sans extension. Vide si le modèle ne donne rien."""
    return sanitize(_render_component(pattern.replace("/", "-").replace("\\", "-"), values))


def check_pattern(pattern: str) -> list[str]:
    """Étiquettes inconnues dans un modèle (fautes de frappe)."""
    return [m.group(1) for m in _TOKEN_RE.finditer(pattern) if m.group(1) not in TOKEN_KEYS]
