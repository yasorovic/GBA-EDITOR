"""
GBA Editor — point d'entrée
Usage : python main.py
"""

from ui.common.labels import label
import sys
from pathlib import Path

# La console Windows est en cp1252 par défaut
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# Garantit que `editor/` est toujours le premier élément du path,
# quelle que soit la façon dont le process est lancé (python main.py,
# import depuis un test, lancement via l'IDE…).
# Tous les modules internes importent sans préfixe "editor." — un seul
# nom par module, pas de risque de double-import.
_EDITOR_DIR = str(Path(__file__).resolve().parent)
if _EDITOR_DIR not in sys.path:
    sys.path.insert(0, _EDITOR_DIR)

from PyQt6.QtCore import Qt, QObject, QEvent
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QToolTip
from PyQt6.QtGui import QPalette, QColor, QFont, QHelpEvent
from ui.common.theme import GLOBAL_QSS, QSS, C, T
from ui.common.numeric_drag import install_numeric_drag_behavior
from ui.common import icons
from ui.common import catalog
from ui.home.project_picker import HomeScreen, PROJECTS_DIR
from core.project_paths import PROJECT_EXT, find_manifest, ProjectManifestError
from core.interface_preferences import interface_language


def dark_palette() -> QPalette:
    """Palette Qt du thème actif (sombre ou clair, neutre). Toutes les valeurs dérivent de ui.common.theme.C."""
    p = QPalette()
    bg      = QColor(C.BG_PANEL)
    surface = QColor(C.BG_INPUT)
    border  = QColor(C.BORDER_MID)
    text    = QColor(C.TEXT_BASE)
    muted   = QColor(C.TEXT_DIM)
    accent  = QColor(C.ACCENT)

    p.setColor(QPalette.ColorRole.Window,          bg)
    p.setColor(QPalette.ColorRole.WindowText,      text)
    p.setColor(QPalette.ColorRole.Base,            surface)
    p.setColor(QPalette.ColorRole.AlternateBase,   border)
    p.setColor(QPalette.ColorRole.Text,            text)
    p.setColor(QPalette.ColorRole.PlaceholderText, muted)
    p.setColor(QPalette.ColorRole.Button,          surface)
    p.setColor(QPalette.ColorRole.ButtonText,      text)
    p.setColor(QPalette.ColorRole.Highlight,       accent)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(C.ON_ACCENT))
    # Bulles d'aide : la règle `QToolTip` de la feuille globale ne suit pas une bulle
    # dont le widget porte sa PROPRE feuille (boutons, curseurs…) — Qt retombait alors
    # sur la palette, et le noir par défaut. Même couleurs que la règle, en repli.
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(C.BG_RAISED))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(C.TEXT_NORM))
    return p


class _TooltipThemeFixer(QObject):
    """Filtre d'événements posé sur `app` : sur Windows, une bulle d'aide déclenchée
    par un widget qui porte sa PROPRE feuille de style (bouton d'icône, curseur…)
    reste noire — ni `GLOBAL_QSS`, ni `app.setPalette()`, ni `QToolTip.setPalette()`
    ne la corrigent, Qt la peint via le thème natif de l'OS.

    On ne laisse plus Qt afficher la bulle : on GÈRE l'événement nous-mêmes
    (`return True`, son traitement par défaut ne s'exécute jamais), et on
    republie la feuille/palette sur le `QLabel` interne (`objectName() ==
    "qtooltip_label"`) tout de suite après l'avoir affiché nous-mêmes — dans le
    même appel synchrone, donc avant que Qt ait pu peindre quoi que ce soit à
    l'écran. Un `QTimer` à 0 ms pour restyler ensuite laissait passer une
    première peinture avec les couleurs natives → un flash noir→thème."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            text = obj.toolTip() if hasattr(obj, "toolTip") else ""
            if text:
                QToolTip.showText(event.globalPos(), text, obj)
                for w in QApplication.topLevelWidgets():
                    if w.objectName() == "qtooltip_label":
                        w.setStyleSheet(QSS.tooltip)
                        w.setPalette(dark_palette())
                        break
            return True
        return False


if __name__ == "__main__":
    # Avant de construire le moindre widget : les écrans lisent `label()` dans
    # leur constructeur, donc les reconstruire après coup serait une seconde
    # mécanique de traduction. Le réglage modifié en session prend effet au
    # redémarrage, comme le dit le panneau Interface.
    catalog.set_language(interface_language())

    # Projet fourni au lancement, deux formes :
    #   --project <dossier>          (le picker, les récents)
    #   <chemin>/<Nom>.gba-project   (double-clic : l'OS passe le fichier associé)
    project_path = None
    if "--project" in sys.argv:
        idx = sys.argv.index("--project")
        if idx + 1 < len(sys.argv):
            project_path = Path(sys.argv[idx + 1])
    else:
        for arg in sys.argv[1:]:
            if arg.endswith(PROJECT_EXT):
                project_path = Path(arg)
                break

    # Le manifeste vit DANS le dossier projet : un .gba-project double-cliqué se
    # ramène à son dossier parent, la racine que MainWindow/Project attendent.
    if project_path is not None and project_path.is_file():
        project_path = project_path.parent

    app = QApplication(sys.argv)
    app.setApplicationName("GBA Editor")
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    install_numeric_drag_behavior(app)
    # Les QSS référencent quelques icônes par chemin de fichier : il faut les
    # rendre maintenant (la QApplication existe) avant d'appliquer la feuille.
    icons.ensure_qss_assets()
    app.setStyleSheet(GLOBAL_QSS)
    # Un widget qui pose sa PROPRE feuille de style (bouton d'icône, curseur…)
    # décroche sa bulle d'aide de la feuille globale ET de app.setPalette() — Qt
    # retombe alors sur le thème natif de l'OS (bulle noire Windows, coins
    # arrondis) au lieu du thème de l'éditeur. `QToolTip.setPalette/setFont` est
    # l'unique réglage que Qt applique à CHAQUE bulle sans dépendre du widget
    # qui la déclenche : seul point qui couvre vraiment tous les cas.
    QToolTip.setPalette(dark_palette())
    QToolTip.setFont(QFont(T.UI, T.MD))
    app._tooltip_theme_fixer = _TooltipThemeFixer()  # garder la référence : sinon PyQt la libère
    app.installEventFilter(app._tooltip_theme_fixer)

    # L'import de la fenêtre entraîne celui de tous les écrans (même ceux qui
    # resteront invisibles au départ). Il est volontairement différé jusqu'à
    # l'exécution, pour ne pas alourdir l'import du module `main`.
    from plugins import load_all_plugins
    loaded, plugin_errors = load_all_plugins()
    from window import MainWindow

    # Refus explicite si le dossier porte plusieurs manifestes (ROADMAP v0.10) :
    # on le dit et on retombe sur l'accueil, plutôt que d'en choisir un au hasard.
    # Après la QApplication : une QMessageBox sans elle planterait.
    if project_path is not None:
        try:
            find_manifest(project_path)
        except ProjectManifestError as exc:
            QMessageBox.critical(None, label('common.open_project'), str(exc))
            project_path = None

    # Si aucun projet fourni en argument, afficher l'écran d'accueil
    if project_path is None:
        picker = HomeScreen(PROJECTS_DIR)
        if picker.exec() != QDialog.DialogCode.Accepted or not picker.result_path:
            sys.exit(0)
        project_path = picker.result_path
        _is_new  = picker.result_is_new
        _name    = picker.result_name
    else:
        _is_new = False
        _name   = ""

    win = MainWindow()
    # Ouvrir le projet AVANT d'afficher la fenêtre : sa construction et son
    # peuplement (Scene Manager, inspecteur, rendu de la scène) sont lourds et
    # se font sur le thread UI. Les faire fenêtre cachée évite d'exposer un
    # éditeur vide (panneaux blancs) puis figé le temps du chargement — la
    # fenêtre n'apparaît qu'une fois prête. Le curseur d'attente signale que le
    # travail est en cours pendant que rien n'est encore visible.
    app.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        if _is_new and _name:
            win._new_project(_name, project_path)
        else:
            win._open_project(project_path)
    finally:
        app.restoreOverrideCursor()

    win.show()

    # Défauts des points d'extension, APRÈS que la fenêtre est visible : un
    # plugin qui n'a pas pu être chargé, et un écran qui ne remplit pas le
    # contrat ProjectScreen (`ui/screens.py`). Les deux se constatent au
    # démarrage et nulle part ailleurs — un écran muet ne se distingue sinon
    # pas d'un écran vide.
    problems = ([f"{name} : {exc}" for name, exc in plugin_errors]
                + list(win.screen_errors))
    if problems:
        box = QMessageBox(win)
        box.setWindowTitle(label('app.extension_errors'))
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(label('app.extension_problems', value=len(problems)))
        box.setDetailedText("\n".join(f"• {p}" for p in problems))
        box.exec()
    sys.exit(app.exec())
