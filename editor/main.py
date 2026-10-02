"""
Backstage — point d'entrée
Usage : python main.py
"""

from ui.common.labels import label
import gc
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

from PyQt6.QtCore import Qt, QObject, QEvent, QPoint, QRectF
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QFrame, QLabel, QVBoxLayout
from PyQt6.QtGui import QPalette, QColor, QHelpEvent, QPainter, QPen
from ui.common.theme import GLOBAL_QSS, C, T, ui_font
from ui.common.numeric_drag import install_numeric_drag_behavior
from ui.common import icons
from ui.common import catalog
from ui.home.project_picker import HomeScreen, PROJECTS_DIR
from core.project_paths import (
    PROJECT_EXT, find_manifest, ProjectManifestError, ProjectNotFoundError)
from core import crash_log
from core.app_info import APP_NAME, APP_VERSION
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
    # Ces couleurs restent cohérentes pour les widgets Qt qui utilisent les rôles
    # d'aide de la palette. Les infobulles de l'éditeur sont rendues séparément
    # par `_ThemedTooltip`, sans passer par le composant natif de Qt.
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(C.BG_RAISED))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(C.TEXT_NORM))
    return p


class _ThemedTooltip(QFrame):
    """Bulle d'aide de l'éditeur, sans passage par le widget natif de Qt."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("editor_tooltip")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # La fenêtre elle-même est transparente : le rayon du cadre laisse donc
        # réellement voir les coins, sans le rectangle opaque de Windows/Qt.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._background = QColor(240, 240, 240, 230) if C.IS_LIGHT else QColor(0, 0, 0, 209)
        self._border = QColor(C.BORDER_MID)
        self.setStyleSheet(
            f"QFrame#editor_tooltip{{background:transparent;color:{C.TEXT_NORM};"
            "border:none;padding:0;}"
            "QLabel{background:transparent;border:none;padding:0;}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        self._text = QLabel()
        self._text.setTextFormat(Qt.TextFormat.RichText)
        self._text.setWordWrap(True)
        self._text.setMaximumWidth(420)
        self._text.setFont(ui_font(T.SM))
        self._text.setStyleSheet(f"color:{C.TEXT_NORM};")
        layout.addWidget(self._text)

    def paintEvent(self, event):  # noqa: N802 - API Qt
        """Peint la surface, plutôt que de déléguer son alpha à la feuille Qt.

        Avec `WA_TranslucentBackground`, Windows peut omettre le fond défini en
        QSS pour une fenêtre ToolTip. Un dessin explicite conserve le rayon et
        l'opacité sur toutes les versions de Qt utilisées par l'éditeur.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._background)
        painter.setPen(QPen(self._border))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 7, 7)

    def show_text(self, position: QPoint, text: str):
        self._text.setText(text)
        self._text.adjustSize()
        self.adjustSize()
        screen = QApplication.screenAt(position) or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            x = min(position.x() + 14, area.right() - self.width())
            y = min(position.y() + 20, area.bottom() - self.height())
            position = QPoint(max(area.left(), x), max(area.top(), y))
        else:
            position += QPoint(14, 20)
        self.move(position)
        self.show()


class _TooltipThemeFilter(QObject):
    """Remplace les infobulles natives par une unique bulle thémée."""

    def __init__(self):
        super().__init__()
        self._bubble = _ThemedTooltip()
        self._anchor = None

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            text = obj.toolTip() if hasattr(obj, "toolTip") else ""
            if text:
                self._anchor = obj
                self._bubble.show_text(event.globalPos(), text)
            else:
                self._bubble.hide()
                self._anchor = None
            return True

        if obj is self._anchor and event.type() in (QEvent.Type.Leave, QEvent.Type.Hide):
            self._bubble.hide()
            self._anchor = None
        elif event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.ApplicationDeactivate):
            self._bubble.hide()
            self._anchor = None
        return False


def _shutdown_qt(app, *widgets) -> None:
    """Détruit les fenêtres PENDANT que la QApplication existe encore.

    Sans cela, `win` (une globale du script) n'est détruite qu'à la toute fin de
    l'interpréteur, APRÈS la QApplication : sous Windows le processus plantait
    alors à la sortie (violation d'accès, « aucun frame Python » dans
    `crash_native.log`) — mesuré le 2026-10-02 : 4 sorties sur 6 plantaient, contre
    0 sur 6 avec cette fermeture explicite. Le plantage survient après la
    fermeture de la fenêtre et l'enregistrement du projet : aucune donnée perdue,
    mais un code de sortie non nul, un rapport d'erreur Windows possible, et une
    CI qui ne peut pas se fier au code de sortie du binaire."""
    for widget in widgets:
        if widget is not None:
            widget.close()
            widget.deleteLater()
    app.processEvents()
    gc.collect()


if __name__ == "__main__":
    # Avant tout : une exception dans un slot tuerait le processus sans trace.
    crash_log.install()
    # Avant de construire le moindre widget : les écrans lisent `label()` dans
    # leur constructeur, donc les reconstruire après coup serait une seconde
    # mécanique de traduction. Le réglage modifié en session prend effet au
    # redémarrage, comme le dit le panneau Interface.
    catalog.set_language(interface_language())

    # Projet fourni au lancement, deux formes :
    #   --project <dossier>          (le picker, les récents)
    #   <chemin>/<Nom>.project   (double-clic : l'OS passe le fichier associé)
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

    # Le manifeste vit DANS le dossier projet : un .project double-cliqué se
    # ramène à son dossier parent, la racine que MainWindow/Project attendent.
    if project_path is not None and project_path.is_file():
        project_path = project_path.parent

    app = QApplication(sys.argv)
    # La trace s'écrit déjà (crash_log.install) ; la fenêtre, elle, a besoin de
    # la QApplication.
    from ui.common.crash_dialog import show_crash_dialog
    crash_log.set_reporter(show_crash_dialog)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    install_numeric_drag_behavior(app)
    # Les QSS référencent quelques icônes par chemin de fichier : il faut les
    # rendre maintenant (la QApplication existe) avant d'appliquer la feuille.
    icons.ensure_qss_assets()
    app.setStyleSheet(GLOBAL_QSS)
    app._tooltip_theme_filter = _TooltipThemeFilter()
    app.installEventFilter(app._tooltip_theme_filter)

    # L'import de la fenêtre entraîne celui de tous les écrans (même ceux qui
    # resteront invisibles au départ). Il est volontairement différé jusqu'à
    # l'exécution, pour ne pas alourdir l'import du module `main`.
    from plugins import load_all_plugins
    loaded, plugin_errors = load_all_plugins()
    from window import MainWindow

    # `--smoke-test[=rapport]` : la CI de release l'exécute sur le binaire LIVRÉ,
    # avant de publier. Aucune fenêtre d'accueil, aucune interaction.
    if any(a == "--smoke-test" or a.startswith("--smoke-test=") for a in sys.argv[1:]):
        import smoke_test
        smoke_code = smoke_test.run(app, plugin_errors)
        _shutdown_qt(app)
        sys.exit(smoke_code)

    # Refus explicite si le dossier porte plusieurs manifestes (ROADMAP v0.10) :
    # on le dit et on retombe sur l'accueil, plutôt que d'en choisir un au hasard.
    # Après la QApplication : une QMessageBox sans elle planterait.
    if project_path is not None:
        try:
            if find_manifest(project_path) is None:
                raise ProjectNotFoundError(
                    f"« {project_path.name} » n'est pas un projet : aucun "
                    f"fichier {PROJECT_EXT} dans ce dossier.")
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
        _starter = picker.result_starter
    else:
        _starter = "Basic"
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
            win._new_project(_name, project_path, _starter)
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
    exit_code = app.exec()
    _shutdown_qt(app, win, globals().get("picker"))
    sys.exit(exit_code)
