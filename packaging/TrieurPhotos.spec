# Fabrication de l'exécutable : pyinstaller packaging/TrieurPhotos.spec
from pathlib import Path

root = Path(SPECPATH).parent

a = Analysis(
    [str(root / "packaging" / "lancer.py")],
    pathex=[str(root)],
    datas=[
        (str(root / "data" / "lieux.csv.gz"), "data"),
        (str(root / "assets" / "icone.png"), "assets"),
        (str(root / "assets" / "coche.svg"), "assets"),
        (str(root / "assets" / "point.svg"), "assets"),
        (str(root / "vendor" / "exiftool"), "exiftool"),
    ],
    hiddenimports=["pillow_heif", "PySide6.QtSvg"],  # QtSvg : coches des cases (images SVG)
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtTest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TrieurPhotos",
    console=False,
    icon=str(root / "assets" / "icone.ico"),
    version=str(root / "packaging" / "version.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="TrieurPhotos")
