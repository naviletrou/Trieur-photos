"""Mode « Doublons seuls » sur une photothèque déjà rangée à la main."""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from make_samples import picture  # noqa: E402

from trieur import analyze, executor  # noqa: E402
from trieur.duplicates import HashCache, IDENTICAL, SAME_PHOTO, apply_default_choices, find_duplicates  # noqa: E402
from trieur.settings import TASK_DUPLICATES, Settings  # noqa: E402


def make_library(root: Path):
    cheverny = root / "2001" / "2001-07-11 Cheverny"
    cheverny.mkdir(parents=True)
    picture(1).save(cheverny / "IMG_0001.jpg", quality=90)
    (root / "Divers").mkdir()
    shutil.copy2(cheverny / "IMG_0001.jpg", root / "Divers" / "IMG_0001 (1).jpg")
    (root / "A trier").mkdir()
    shutil.copy2(cheverny / "IMG_0001.jpg", root / "A trier" / "Copie de IMG_0001.jpg")
    noel = root / "2019" / "2019-12-24 Noël"
    noel.mkdir(parents=True)
    picture(2).save(noel / "IMG_0002.jpg", quality=92)
    whatsapp = root / "2019" / "WhatsApp"
    whatsapp.mkdir()
    picture(2).resize((800, 600)).save(whatsapp / "IMG-20191224-WA0001.jpg", quality=70)
    picture(3).save(noel / "IMG_0003.jpg", quality=90)  # photo unique


def analyse(library: Path, preferred: Path | None = None):
    settings = Settings(task=TASK_DUPLICATES, source=str(library), preferred_folder=str(preferred or ""))
    items = analyze.scan(settings)
    cache = HashCache(library.parent / "cache.sqlite")
    groups = find_duplicates(items, None, True, cache=cache, preferred=preferred)
    cache.close()
    apply_default_choices(groups)
    return items, groups


def test_keep_best_placed_copy(tmp_path):
    library = tmp_path / "Photos"
    make_library(library)
    items, groups = analyse(library)
    kinds = {g.kind for g in groups}
    assert kinds == {IDENTICAL, SAME_PHOTO}
    identical = next(g for g in groups if g.kind == IDENTICAL)
    # parmi trois copies identiques, on garde celle du dossier daté et nommé
    assert identical.keep.path.parent.name == "2001-07-11 Cheverny"
    same = next(g for g in groups if g.kind == SAME_PHOTO)
    assert same.keep.name == "IMG_0002.jpg" and same.keep.width == 1600  # la plus grande version
    assert sum(1 for i in items if i.excluded) == 3


def test_preferred_folder(tmp_path):
    library = tmp_path / "Photos"
    make_library(library)
    _, groups = analyse(library, preferred=library / "Divers")
    identical = next(g for g in groups if g.kind == IDENTICAL)
    assert identical.keep.path.parent.name == "Divers"


def test_set_aside_and_undo(tmp_path):
    library = tmp_path / "Photos"
    make_library(library)
    before = sorted(str(p.relative_to(library)) for p in library.rglob("*") if p.is_file())
    items, groups = analyse(library)
    result = executor.execute_duplicates(items, library)
    assert result.duplicates_moved == 3 and not result.errors
    aside = [p for p in (library / "_Doublons").rglob("*") if p.is_file()]
    assert len(aside) == 3
    assert any(p.parent.name == "Divers" for p in aside)  # le chemin d'origine est conservé
    report = tmp_path / "rapport.csv"
    executor.write_report(groups, report)
    assert "écarter" in report.read_text(encoding="utf-8-sig")
    # deuxième recherche : plus de doublons, _Doublons n'est pas parcouru
    _, again = analyse(library)
    assert not [g for g in again if g.kind in (IDENTICAL, SAME_PHOTO)]
    executor.undo(result.journal)
    after = sorted(str(p.relative_to(library)) for p in library.rglob("*")
                   if p.is_file() and "_Journal" not in p.parts and "_Doublons" not in p.parts)
    assert after == before


def test_set_aside_outside_library(tmp_path):
    library = tmp_path / "Photos"
    outside = tmp_path / "Sauvegarde" / "Doublons écartés"
    make_library(library)
    before = sorted(str(p.relative_to(library)) for p in library.rglob("*") if p.is_file())
    items, _ = analyse(library)
    result = executor.execute_duplicates(items, library, aside_base=outside)
    assert result.duplicates_moved == 3 and not result.errors
    assert not (library / "_Doublons").exists()  # rien dans la photothèque
    assert len([p for p in outside.rglob("*") if p.is_file()]) == 3
    assert any(p.parent.name == "Divers" for p in outside.rglob("*.jpg"))
    settings = Settings(task=TASK_DUPLICATES, source=str(library), duplicates_folder=str(outside))
    assert settings.duplicates_location() == outside and settings.duplicates_outside
    executor.undo(result.journal)
    after = sorted(str(p.relative_to(library)) for p in library.rglob("*")
                   if p.is_file() and "_Journal" not in p.parts)
    assert after == before
