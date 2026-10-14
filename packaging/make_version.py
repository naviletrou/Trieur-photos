"""Écrit packaging/version.txt (informations de version de l'exécutable Windows)."""
import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent
version = re.search(r'__version__ = "([^"]+)"', (root / "trieur" / "__init__.py").read_text()).group(1)
parts = (version.split(".") + ["0"] * 4)[:4]
numbers = ", ".join(parts)
(root / "packaging" / "version.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({numbers}), prodvers=({numbers})),
  kids=[StringFileInfo([StringTable('040C04B0', [
    StringStruct('FileDescription', 'Trieur de photos'),
    StringStruct('ProductName', 'Trieur de photos'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('ProductVersion', '{version}'),
    StringStruct('LegalCopyright', 'Licence MIT')])]),
    VarFileInfo([VarStruct('Translation', [1036, 1200])])]
)
""", encoding="utf-8")
print(version)
