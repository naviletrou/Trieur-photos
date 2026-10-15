"""Un lien symbolique vers un dossier parent (fréquent sur un NAS) ne doit pas faire tourner la recherche en rond."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from make_samples import picture  # noqa: E402

from trieur import analyze  # noqa: E402
from trieur.settings import TASK_DUPLICATES, Settings  # noqa: E402


@pytest.mark.skipif(os.name == "nt", reason="liens symboliques réservés aux administrateurs sous Windows")
def test_symlink_loop(tmp_path):
    library = tmp_path / "Photos"
    folder = library / "2025" / "Noël"
    folder.mkdir(parents=True)
    picture(1).save(folder / "IMG_0001.jpg")
    os.symlink(library, folder / "retour", target_is_directory=True)
    details = []
    items = analyze.scan(Settings(task=TASK_DUPLICATES, source=str(library)), detail=details.append)
    assert len(items) == 1
    assert details
