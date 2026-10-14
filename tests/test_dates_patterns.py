from datetime import datetime

from trieur.dates import find_date, is_generic_name, text_without_date
from trieur.patterns import PRESETS, DEFAULT_PRESET, render_dirs, render_name, sanitize, token_values


def test_dates_in_names():
    cases = {
        "IMG_20190812_143201.jpg": (datetime(2019, 8, 12, 14, 32, 1), "heure"),
        "2001-07-11 Cheverny": (datetime(2001, 7, 11, 12), "jour"),
        "2001 05 10 - Levignen": (datetime(2001, 5, 10, 12), "jour"),
        "20010711": (datetime(2001, 7, 11, 12), "jour"),
        "11.07.2001 anniversaire": (datetime(2001, 7, 11, 12), "jour"),
        "Juillet 2001": (datetime(2001, 7, 1, 12), "mois"),
        "2001-07": (datetime(2001, 7, 1, 12), "mois"),
        "1985 Noël chez Mamie": (datetime(1985, 1, 1, 12), "année"),
        "PXL_20231224_201510123.jpg": (datetime(2023, 12, 24, 20, 15, 10), "heure"),
    }
    for name, (when, precision) in cases.items():
        found = find_date(name)
        assert found, name
        assert (found.when, found.precision) == (when, precision), name


def test_no_false_dates():
    for name in ("IMG_1234.jpg", "DSC01999", "photo 3000x2000", "Divers", "IMG_2005.jpg"):
        assert find_date(name, year_only=False) is None, name
    assert find_date("DSC01999") is None


def test_text_without_date():
    assert text_without_date("2001-07-11 Cheverny") == "Cheverny"
    assert text_without_date("2001 05 10 - Levignen Anniv") == "Levignen Anniv"
    assert text_without_date("1985_Noël_chez_Mamie") == "Noël chez Mamie"
    assert is_generic_name("100CANON") and is_generic_name("DCIM") and not is_generic_name("Cheverny")


def test_patterns():
    folders, files = PRESETS[DEFAULT_PRESET]
    when = datetime(2001, 7, 11, 14, 32, 5)
    full = token_values(when, "heure", place="Cheverny", event="Visite du château")
    assert render_dirs(folders, full) == ["2001", "07 - Juillet", "2001-07-11 Cheverny - Visite du château"]
    assert render_name(files, full) == "2001-07-11_14h32_Cheverny"
    no_place = token_values(when, "heure", event="Anniversaire")
    assert render_dirs(folders, no_place)[-1] == "2001-07-11 - Anniversaire"
    assert render_name(files, no_place) == "2001-07-11_14h32"
    # le lieu n'est pas répété quand l'événement le contient
    dup = token_values(when, "heure", place="Cheverny", event="Château de Cheverny")
    assert render_dirs(folders, dup)[-1] == "2001-07-11 - Château de Cheverny"
    assert render_name(files, dup) == "2001-07-11_14h32_Cheverny"
    # année seule : pas de dossier de mois
    year = token_values(datetime(1985, 1, 1, 12), "année", event="Noël")
    assert render_dirs(folders, year) == ["1985", "1985 - Noël"]


def test_sanitize():
    assert sanitize('a:b?c. ') == "a-b-c"
    assert sanitize("CON") == "_CON"
    assert len(sanitize("x" * 300)) <= 120
