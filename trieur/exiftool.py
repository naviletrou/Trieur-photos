"""Communication avec ExifTool (lecture et écriture des métadonnées).

ExifTool est lancé une seule fois en mode « -stay_open » : les commandes lui sont
envoyées les unes après les autres, ce qui évite de relancer le programme pour
chaque fichier (très lent sous Windows).
"""
from __future__ import annotations

import json
import re
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

# Format des dates renvoyées par ExifTool
DATE_FORMAT = "%Y:%m:%d %H:%M:%S"

# Balises lues pour chaque fichier. Le suffixe « # » donne la valeur numérique brute.
READ_TAGS = [
    "-DateTimeOriginal",
    "-CreateDate",
    "-QuickTime:CreateDate",
    "-MediaCreateDate",
    "-TrackCreateDate",
    "-GPSLatitude#",
    "-GPSLongitude#",
    "-Make",
    "-Model",
    "-ImageWidth",
    "-ImageHeight",
    "-Orientation#",
]


class ExifToolError(RuntimeError):
    pass


def app_dir() -> Path:
    """Dossier du programme (à côté de l'exécutable une fois installé)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def find_exiftool() -> list[str]:
    """Commande permettant de lancer ExifTool."""
    env = os.environ.get("TRIEUR_EXIFTOOL")
    if env:
        return ["perl", env] if env.endswith(".pl") else [env]
    base = app_dir()
    candidates = [
        base / "exiftool" / "exiftool.exe",
        base / "_internal" / "exiftool" / "exiftool.exe",
        base / "exiftool.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return [str(candidate)]
    found = shutil.which("exiftool")
    if found:
        return [found]
    raise ExifToolError(
        "ExifTool est introuvable. Réinstallez le Trieur de photos ou placez exiftool.exe "
        "dans le dossier du programme."
    )


def parse_date(value) -> datetime | None:
    """Convertit une date ExifTool en datetime ; None si absente ou invalide (0000:00:00)."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    # retire le fuseau horaire éventuel (« +02:00 », « Z ») et les fractions de seconde
    for sep in ("+", "Z"):
        if sep in text[10:]:
            text = text[: 10 + text[10:].index(sep)]
    text = text.split(".")[0].strip()
    if len(text) == 10:
        text += " 00:00:00"
    try:
        parsed = datetime.strptime(text[:19], DATE_FORMAT)
    except ValueError:
        return None
    if parsed.year < 1826:  # première photographie connue : tout ce qui précède est faux
        return None
    return parsed


class ExifTool:
    """Processus ExifTool persistant. À utiliser avec « with ExifTool() as et: ... »."""

    SENTINEL = "{ready}"

    def __init__(self, command: list[str] | None = None):
        self.command = command or find_exiftool()
        self.process: subprocess.Popen | None = None
        self.lock = threading.Lock()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    def start(self):
        if self.process:
            return
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NO_WINDOW  # pas de fenêtre noire sous Windows
        self.process = subprocess.Popen(
            self.command + ["-stay_open", "True", "-@", "-", "-common_args",
                            "-charset", "filename=utf8", "-charset", "utf8"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )

    def stop(self):
        if not self.process:
            return
        try:
            self.process.stdin.write(b"-stay_open\nFalse\n")
            self.process.stdin.flush()
            self.process.wait(timeout=10)
        except Exception:
            self.process.kill()
        self.process = None

    def execute(self, *args: str) -> str:
        """Envoie une commande et renvoie la sortie texte."""
        if not self.process:
            self.start()
        with self.lock:
            payload = "\n".join(args) + "\n-execute\n"
            self.process.stdin.write(payload.encode("utf-8"))
            self.process.stdin.flush()
            output = bytearray()
            stdout = self.process.stdout
            while True:
                line = stdout.readline()
                if not line:
                    raise ExifToolError("ExifTool s'est arrêté de façon inattendue.")
                if line.strip() == self.SENTINEL.encode():
                    break
                output += line
            return output.decode("utf-8", errors="replace")

    def read(self, paths: Iterable[Path], chunk: int = 200,
             progress: Callable[[int], None] | None = None,
             cancelled: Callable[[], bool] | None = None) -> dict[str, dict]:
        """Lit les métadonnées de nombreux fichiers. Renvoie {chemin: {balise: valeur}}."""
        paths = [str(p) for p in paths]
        result: dict[str, dict] = {}
        for start in range(0, len(paths), chunk):
            if cancelled and cancelled():
                break
            batch = paths[start:start + chunk]
            raw = self.execute("-json", "-api", "QuickTimeUTC", "-api", "LargeFileSupport=1",
                               "-d", DATE_FORMAT, *READ_TAGS, *batch)
            if raw.strip():
                try:
                    for entry in json.loads(raw):
                        result[os.path.normcase(os.path.normpath(entry.get("SourceFile", "")))] = entry
                except json.JSONDecodeError:
                    pass
            if progress:
                progress(min(start + chunk, len(paths)))
        return result

    def write_date(self, path: Path, when: datetime, is_video: bool) -> bool:
        """Écrit la date de prise de vue dans le fichier. Renvoie True si réussi."""
        value = when.strftime(DATE_FORMAT)
        if is_video:
            # les dates QuickTime sont en temps universel : ExifTool convertit avec QuickTimeUTC
            args = ["-api", "QuickTimeUTC", f"-QuickTime:CreateDate={value}",
                    f"-QuickTime:ModifyDate={value}", f"-MediaCreateDate={value}",
                    f"-TrackCreateDate={value}"]
        else:
            args = [f"-DateTimeOriginal={value}", f"-CreateDate={value}", f"-ModifyDate={value}"]
        output = self.execute("-overwrite_original", "-P", *args, str(path))
        match = re.search(r"(\d+) image files updated", output)
        return bool(match and int(match.group(1)) > 0)
