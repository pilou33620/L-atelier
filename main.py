# ==========================================
# VERSIONING DU CODE
# Voir CHANGELOG.md pour l'historique des versions.
# ==========================================

import sys
import logging
try:
    import onnxruntime
except ImportError:
    pass

from PyQt6.QtWidgets import QApplication, QDialog

from ui import DARK_QSS, ProjectLauncherDialog, MainWindow

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("[LOG - SYSTEM] Lancement de 'L'Atelier V4.5.0'")
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)

    dialog = ProjectLauncherDialog()
    if dialog.exec() == QDialog.DialogCode.Accepted:
        app_mode, target_directory = dialog.get_selection()
        
        window = MainWindow(app_mode=app_mode)
        window.show()

        if target_directory:
            # open_folder() propose lui-même l'import des datasheets en mode
            # hardware. L'appel supplémentaire à import_datasheets() qui se
            # trouvait ici ouvrait une SECONDE fois le sélecteur de fichiers.
            window.open_folder(path=target_directory)

        app.exec()

    sys.exit(0)
