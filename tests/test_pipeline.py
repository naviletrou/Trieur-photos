"""Classement complet d'un jeu de photos d'essai (nécessite ExifTool)."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from trieur import analyze, executor  # noqa: E402
from trieur.duplicates import HashCache, apply_default_choices, find_already_sorted, find_duplicates  # noqa: E402
from trieur.exiftool import ExifTool, ExifToolError, find_exiftool  # noqa: E402
from trieur.places import PlaceIndex  # noqa: E402
from trieur.settings import COPY, MOVE, Settings  # noqa: E402

try:
    find_exiftool()
    HAS_EXIFTOOL = True
except ExifToolError:
    HAS_EXIFTOOL = False

pytestmark = pytest.mark.skipif(not HAS_EXIFTOOL, reason="ExifTool absent")


@pytest.fixture()
def samples(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "cache"))
    import make_samples
    source = tmp_path / "source"
    make_samples.main(source)
    return source, tmp_path / "destination"


def classify(source, destination, mode):
    settings = Settings(source=str(source), destination=str(destination), mode=mode, use_file_date=False)
    items = analyze.scan(settings)
    with ExifTool() as et:
        analyze.read_metadata(items, et)
        analyze.resolve(items, settings, PlaceIndex.load(ROOT / "data" / "lieux.csv.gz"))
        cache = HashCache(Path(str(destination) + ".sqlite"))
        apply_default_choices(find_duplicates(items, destination, cache=cache))
        groups = analyze.build_groups(items, settings)
        analyze.plan(groups, settings)
        find_already_sorted(groups, et, cache=cache)
        analyze.plan(groups, settings)
        cache.close()
        return groups, executor.execute(groups, settings, et)


def files(folder: Path) -> set[str]:
    return {str(p.relative_to(folder)).replace("\\", "/") for p in folder.rglob("*")
            if p.is_file() and "_Journal" not in p.parts}


def test_copy_classification(samples):
    source, destination = samples
    before = files(source)
    groups, result = classify(source, destination, COPY)
    assert not result.errors
    assert files(source) == before  # en copie, la source n'est pas touchée
    out = files(destination)
    assert "2001/07 - Juillet/2001-07-11 - Cheverny/2001-07-11.jpg" in out           # date du dossier
    assert "2003/05 - Mai/2003-05-01 - Mariage Sophie/2003-05-01.jpg" in out          # date du scanner ignorée
    assert "1985/1985 - Noël chez Mamie/1985.jpg" in out                              # année seule
    assert "2019/08 - Août/2019-08-12 Cheverny/2019-08-12_14h32_Cheverny.jpg" in out  # EXIF + GPS
    assert any(p.endswith("Saint-Martin-de-Belleville.xmp") for p in out)            # fichier associé
    assert "_Sans date/Scans/Divers/inconnue.jpg" in out
    # les copies de la même photo ne sont pas recopiées
    assert not any("WhatsApp" in p or "Copie de" in p for p in out)
    # deuxième passage : tout est déjà rangé
    _, again = classify(source, destination, COPY)
    assert again.copied == 0


def test_move_and_undo(samples):
    source, destination = samples
    before = files(source)
    _, result = classify(source, destination, MOVE)
    assert not result.errors and result.moved > 0 and result.duplicates_moved == 2
    assert not files(source)  # tout est parti, les dossiers vides sont supprimés
    assert any(p.startswith("_Doublons/") for p in files(destination))
    undone = executor.undo(result.journal)
    assert not undone.errors
    assert files(source) == before
    assert not [p for p in files(destination)]
