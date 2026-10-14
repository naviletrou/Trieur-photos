"""Crée un jeu de photos d'essai couvrant les cas à traiter.

    python tools/make_samples.py DOSSIER

Il faut ExifTool (variable TRIEUR_EXIFTOOL ou dans le PATH) et, pour la vidéo, ffmpeg.
"""
from __future__ import annotations

import random
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from trieur.exiftool import find_exiftool  # noqa: E402

CHEVERNY = (47.5008, 1.4595)
BELLEVILLE = (45.3818, 6.5052)
PARIS = (48.8584, 2.2945)


def picture(seed: int, size=(1600, 1200), shift: int = 0) -> Image.Image:
    rnd = random.Random(seed)
    image = Image.new("RGB", size, tuple(rnd.randint(0, 255) for _ in range(3)))
    draw = ImageDraw.Draw(image)
    for _ in range(14):
        x, y = rnd.randint(-200, size[0]), rnd.randint(-200, size[1])
        w, h = rnd.randint(150, 700), rnd.randint(150, 600)
        color = tuple(rnd.randint(0, 255) for _ in range(3))
        if rnd.random() < 0.5:
            draw.ellipse([x + shift, y, x + w + shift, y + h], fill=color)
        else:
            draw.rectangle([x + shift, y, x + w + shift, y + h], fill=color)
    return image.filter(ImageFilter.GaussianBlur(2))


def exif(path: Path, **tags):
    args = []
    for key, value in tags.items():
        args.append(f"-{key}={value}")
    subprocess.run(find_exiftool() + ["-q", "-overwrite_original", *args, str(path)], check=True)


def gps(lat_lon):
    lat, lon = lat_lon
    return dict(GPSLatitude=abs(lat), GPSLatitudeRef="N" if lat >= 0 else "S",
                GPSLongitude=abs(lon), GPSLongitudeRef="E" if lon >= 0 else "W")


def main(root: Path):
    if root.exists():
        shutil.rmtree(root)
    phone = root / "Téléphone"
    camera = root / "Appareil" / "DCIM" / "100CANON"
    scans = root / "Scans"
    copies = root / "Copies"
    for folder in (phone, camera, scans, copies):
        folder.mkdir(parents=True)

    # téléphone : date et GPS
    p = phone / "IMG_20190812_143201.jpg"
    picture(1).save(p, quality=90)
    exif(p, DateTimeOriginal="2019:08:12 14:32:01", Make="Apple", Model="iPhone 8", **gps(CHEVERNY))
    # rafale de 3 photos presque identiques
    for i in range(3):
        p = phone / f"IMG_20190812_1440{i:02d}.jpg"
        picture(2, shift=i * 6).save(p, quality=88)
        exif(p, DateTimeOriginal=f"2019:08:12 14:40:{i:02d}", Make="Apple", Model="iPhone 8", **gps(CHEVERNY))
    # Live Photo : une photo et une courte vidéo de même nom
    p = phone / "IMG_0001.jpg"
    picture(3).save(p, quality=90)
    exif(p, DateTimeOriginal="2019:08:13 09:15:00", Make="Apple", Model="iPhone 8", **gps(PARIS))
    if shutil.which("ffmpeg"):
        for name, when in (("IMG_0001.mov", "2019-08-13T07:15:00Z"), ("VID_20190814_101500.mp4", "2019-08-14T08:15:00Z")):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
                            "-metadata", f"creation_time={when}", str(phone / name)], check=True)

    # appareil photo : date sans GPS, avec un fichier .xmp associé
    p = camera / "IMG_1001.JPG"
    picture(4).save(p, quality=92)
    exif(p, DateTimeOriginal="2001:07:01 11:00:00", Make="Canon", Model="Canon PowerShot A70")
    (camera / "IMG_1001.xmp").write_text("<x:xmpmeta xmlns:x='adobe:ns:meta/'/>", encoding="utf-8")
    p = camera / "IMG_1002.JPG"
    picture(5).save(p, quality=92)
    exif(p, DateTimeOriginal="2001:07:01 15:30:00", Make="Canon", Model="Canon PowerShot A70", **gps(BELLEVILLE))

    # scans sans date : la date vient du nom du dossier
    folder = scans / "2001-07-11 Cheverny"
    folder.mkdir()
    for i in range(3):
        picture(10 + i).save(folder / f"scan{i + 1:03d}.jpg", quality=85)
    folder = scans / "1985 Noël chez Mamie"
    folder.mkdir()
    for i in range(2):
        picture(20 + i).save(folder / f"scan{i + 1:02d}.jpg", quality=85)
    # scan dont l'EXIF contient la date de numérisation (scanner Epson) : la date du dossier doit primer
    folder = scans / "2003-05-01 Mariage Sophie"
    folder.mkdir()
    p = folder / "mariage01.jpg"
    picture(30).save(p, quality=85)
    exif(p, DateTimeOriginal="2024:01:05 10:00:00", Make="EPSON", Model="Perfection V600")
    # dossier sans aucune date
    folder = scans / "Divers"
    folder.mkdir()
    picture(40).save(folder / "inconnue.jpg", quality=85)

    # doublons : copie exacte sous un autre nom et version réduite recompressée sans EXIF
    shutil.copy2(phone / "IMG_20190812_143201.jpg", copies / "Copie de IMG_20190812_143201.jpg")
    small = Image.open(phone / "IMG_20190812_143201.jpg")
    small.resize((800, 600)).save(copies / "envoyée par WhatsApp.jpg", quality=70)

    count = sum(1 for f in root.rglob("*") if f.is_file())
    print(f"{count} fichiers créés dans {root}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
