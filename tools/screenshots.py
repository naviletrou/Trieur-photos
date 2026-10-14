"""Captures des écrans avec le jeu d'essai (sans écran : QT_QPA_PLATFORM=offscreen)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PySide6.QtWidgets import QApplication  # noqa: E402

from trieur.ui.main_window import MainWindow  # noqa: E402
from trieur.ui.style import STYLE  # noqa: E402
from trieur.ui.workers import AnalysisWorker  # noqa: E402

source, destination, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
window = MainWindow()
window.resize(1280, 820)
window.folders.source.setText(str(source))
window.folders.destination.setText(str(destination))
window.show()
app.processEvents()
window.grab().save(str(out / "1_dossiers.png"))
window.folders.store()
analysis = AnalysisWorker(window.settings).work()
window.analysis_done(analysis)
for index, name in enumerate(["1_dossiers", "2_classement", "3_verification", "4_doublons", "5_lancement"]):
    if index == 0:
        continue
    window.go(index)
    if index == 2:
        window.review.groups_view.selectRow(1)
    app.processEvents()
    window.grab().save(str(out / f"{name}.png"))
print("captures dans", out)
from trieur.ui.workers import ExecuteWorker  # noqa: E402
result = ExecuteWorker(window.analysis).work()
window.run_done(result)
app.processEvents()
window.grab().save(str(out / "6_termine.png"))
