"""DiskView — l'onglet Disk : le contenu d'UN dossier de `assets/`, à plat.

Lecture seule. Une icône et un nom par entrée, un fil d'ariane (Assets › sfx ›
platformer) pour savoir où l'on est et remonter ; un double-clic sur un dossier
y entre. L'arbre vertical de tout `assets/` est l'affaire du project viewer, pas
de cette zone horizontale.

La vue ne connaît ni le projet ni le disque : `window.py` lui donne l'arbre
calculé par `core.disk_tree`, comme il donne ses messages à la vue Diagnostics.
Chaque fichier porte une marque (asset, source reliée, source sans asset, non
géré), dite par la couleur et par l'infobulle ; la racine s'appelle « Assets »."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QMimeData, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QPushButton, QTabWidget, QToolButton,
    QSlider, QVBoxLayout, QWidget, QWidgetAction,
)

from core import disk_tree
from core.models.audio import MUSIC_FILE_EXTS, SFX_FILE_EXTS
from core.models.font import FONT_FILE_EXTS
from core.models.resource import MIME_CANVAS_ACTOR, MIME_PREFAB_TEMPLATE, MIME_UI_LAYOUT
from core.models.sprite import IMAGE_FILE_EXTS
from ui.common import icons
from ui.common.elide_name import ElidedNameDelegate
from ui.common.disk_folder_colors import COLORS as FOLDER_COLORS, color_for as folder_color_for, set_color as set_folder_color
from ui.common.labels import label
from ui.common.panel_bar import bar_button, panel_bar
from ui.common import shortcut_hints
from ui.common.reveal import reveal_in_file_manager
from ui.common.theme import C, QSS, S, T
from ui.common.tooltip import tooltip
from ui.common.widgets import W

# Une cellule, toujours la même : la surbrillance d'une entrée est un rectangle de taille fixe,
# pas une boîte qui épouse son texte. L'icône est grande, le nom en dessous reste discret.
_CELL = QSize(124, 108)
_ICON = QSize(48, 48)
_GRID_CELL_MIN = 96
_GRID_CELL_MAX = 176
# La vue en liste : une ligne par entrée, l'icône petite, des séparateurs entre les groupes.
_ROW = QSize(10, 26)          # la largeur est celle de la vue : seule la hauteur compte
_ROW_ICON = QSize(18, 18)
_HEADER = QSize(10, 30)

LAYOUT_MODES = ("grid", "list")

_NODE_ROLE = Qt.ItemDataRole.UserRole
_UP_ROLE = Qt.ItemDataRole.UserRole + 1     # l'entrée « ... » qui remonte d'un niveau
_OPEN_ROLE = Qt.ItemDataRole.UserRole + 2   # l'entrée « assets » de la racine, qui ouvre le dossier
_DRAGGING_ROLE = Qt.ItemDataRole.UserRole + 4  # l'entrée qu'on glisse en ce moment : affichée à demi transparente
_HEADER_ROLE = Qt.ItemDataRole.UserRole + 5     # un séparateur de la vue en liste (un groupe de fichiers)
_DROP_ROLE = Qt.ItemDataRole.UserRole + 3   # le dossier (chemin) où un glisser-déposer sur cette entrée range ses fichiers

# Les icônes de l'éditeur (`icons.py`) : une famille d'asset a la sienne partout, ici aussi.
_FAMILY_ICONS = {"sprites": "sprite", "backgrounds": "background", "sfx": "sfx", "music": "music",
                 "jingles": "jingle", "fonts": "font", "palettes": "palette", "scripts": "script_lua",
                 "scenes": "scene", "prefabs": "prefab", "ui_layouts": "ui_layout",
                 "music_boxes": "music", "jingle_boxes": "jingle", "sound_boxes": "sfx",
                 "data_tables": "data_table", "font_assets": "font", "texts": "ui_text",
                 "variables": "data_table"}
# Une source qu'aucun asset ne cite n'a pas de famille : son format dit ce qu'elle PEUT devenir.
# Les listes de formats restent celles des familles (une seule source). Deux formats servent
# à deux familles : `.png` (image ou police) et `.wav` (effet ou musique). Le cas courant
# gagne — l'image, l'effet — parce que les dictionnaires s'écrasent dans l'ordre.
_SUFFIX_ICONS = {**{ext: "font" for ext in FONT_FILE_EXTS},
                 **{ext: "sprite" for ext in IMAGE_FILE_EXTS},
                 **{ext: "music" for ext in MUSIC_FILE_EXTS},
                 **{ext: "sfx" for ext in SFX_FILE_EXTS},
                 ".hex": "palette", ".lua": "script_lua"}


# Ce qui circule quand on glisse des fichiers ou des dossiers de l'onglet Disk : leurs chemins. Un seul format
# pour l'arbre et la vue à plat, de sorte qu'on peut glisser de l'un vers l'autre.
MIME_DISK_PATHS = "application/x-backstage-disk-paths"


# Un prefab ou un layout glissé SEUL depuis le Disk porte en plus le format que le canvas lit déjà
# pour le même geste depuis le project viewer : le canvas ne connaît pas l'onglet Disk.
_CANVAS_MIMES = {"prefabs": MIME_PREFAB_TEMPLATE, "ui_layouts": MIME_UI_LAYOUT}


def disk_mime(paths, nodes=()) -> QMimeData:
    """`nodes` : les DiskNode glissés ; si c'est un unique prefab ou layout, le canvas peut le recevoir."""
    mime = QMimeData()
    mime.setData(MIME_DISK_PATHS, json.dumps([str(p) for p in paths]).encode("utf-8"))
    nodes = list(nodes)
    if len(nodes) == 1 and nodes[0].kind == disk_tree.ASSET and nodes[0].family in _CANVAS_MIMES:
        mime.setData(_CANVAS_MIMES[nodes[0].family], nodes[0].owner.encode("utf-8"))
    return mime


def dropped_paths(mime) -> list[str]:
    """Les chemins portés par un glisser venu d'un onglet Disk, ou rien pour tout autre glisser."""
    if not mime.hasFormat(MIME_DISK_PATHS):
        return []
    try:
        paths = json.loads(bytes(mime.data(MIME_DISK_PATHS)).decode("utf-8"))
    except ValueError:
        return []
    return [p for p in paths if isinstance(p, str)]


DRAGGING_ROLE = _DRAGGING_ROLE


@dataclass
class DiskCallbacks:
    """Ce que les vues de l'onglet Disk demandent à la fenêtre pour créer, importer et supprimer. Les vues ne
    connaissent ni le projet ni l'historique : `window.py` donne ces fonctions, comme `set_drop_check`."""
    create_options: Callable[[str], list]               # chemin -> [(famille, mot, nom)] ; vide : pas une source libre
    create_from_sources: Callable[[list, str], None]    # ([chemin], famille) : un seul geste annulable pour tout le lot
    delete_items: Callable[[list], None]                # [DiskNode] : assets, sources, fichiers, dossiers
    deletable: Callable[[object], bool]                 # ce nœud peut-il être supprimé ?
    import_files: Callable[[str], None]                 # dossier de destination
    import_paths: Callable[[list, str], None]           # ([fichier], dossier) : des fichiers déposés depuis l'explorateur
    create_blank: Callable[[str, str], None]            # (type, dossier)
    new_folder: Callable[[str], None]                   # dossier parent
    blank_kinds: list = field(default_factory=list)     # [(type, mot)] dans l'ordre du menu
    edit_externally: Callable[[Path], None] | None = None   # ouvre un .json dans l'éditeur de texte réglé ; sans elle, pas d'entrée
    duplicate_items: Callable[[list], None] | None = None   # [DiskNode] : une copie de chaque asset, en UNE entrée d'historique
    duplicable: Callable[[object], bool] | None = None      # ce nœud (un asset, une source) se duplique-t-il ?


# L'icône de chaque entrée d'un menu de création : la même grammaire que le « + » de l'arbre des scènes
# (une icône par entrée, une séparation avant « Folder »).
_BLANK_ICONS = {"scene": "scene", "prefab": "prefab", "ui_layout": "ui_layout", "music_box": "music",
                "jingle_box": "jingle", "sound_box": "sfx", "data_table": "data_table", "palette": "palette",
                "script": "script_lua", "behavior": "script_lua"}


def bind_delete_key(widget, selected_nodes, callbacks) -> None:
    """Suppr sur `widget` (et non sur son champ de filtre) supprime la sélection, comme l'entrée « Delete » du clic droit.
    `selected_nodes()` rend les nœuds choisis ; `callbacks()` les `DiskCallbacks` du moment (posés après la vue)."""
    def delete_selection():
        cb = callbacks()
        nodes = [n for n in selected_nodes() if cb is not None and cb.deletable(n)]
        if nodes:
            cb.delete_items(nodes)
    shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), widget)
    shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
    shortcut.activated.connect(delete_selection)


def bind_duplicate_key(widget, selected_nodes, callbacks) -> None:
    """Ctrl+D (la touche réglée pour `common.duplicate`) sur `widget` duplique la sélection, comme l'entrée *Duplicate* du
    clic droit. Rien ne se passe si un nœud choisi n'est pas un asset duplicable : le geste est tout ou rien."""
    from core.keybindings import bind

    def duplicate_selection():
        cb = callbacks()
        nodes = selected_nodes()
        if cb is not None and duplicable_nodes(nodes, cb):
            cb.duplicate_items(nodes)
    shortcut = QShortcut(QKeySequence(), widget)
    shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
    shortcut.activated.connect(duplicate_selection)
    bind("common.duplicate", shortcut)


def duplicable_nodes(nodes: list, callbacks: DiskCallbacks) -> bool:
    """Toute la sélection se duplique (assets et sources, que la fenêtre juge). Un dossier ou un fichier inconnu dans le
    lot, et la duplication n'est pas proposée : le geste est tout ou rien, comme *Create*."""
    return bool(nodes) and callbacks.duplicate_items is not None and callbacks.duplicable is not None and all(
        callbacks.duplicable(n) for n in nodes)


def renamable(node: disk_tree.DiskNode) -> bool:
    """Un dossier, une source, un script ou un fichier non géré se renomme depuis le Disk ; le nom d'un autre asset
    se change dans son écran, qui sait tout ce qui le cite."""
    return node.kind != disk_tree.ASSET or node.family == "scripts"


def _icon(name: str):
    return icons.get(name, icons.COLOR_DEFAULT)


# Les .json du projet entier (textes, traductions, variables) : le double-clic ouvre leur écran, le clic droit
# les offre aussi à un éditeur de texte externe.
_TEXT_FILE_FAMILIES = ("texts", "variables")

# Une source, libre ou déjà citée par un asset : on peut en tirer un asset de plus.
_SOURCE_KINDS = (disk_tree.FREE_SOURCE, disk_tree.LINKED_SOURCE)


def shared_create_options(nodes: list, callbacks: DiskCallbacks) -> list:
    """`[(famille, mot, nom)]` : les types que TOUTES les sources choisies peuvent devenir, dans l'ordre de la première
    (le plus courant d'abord) ; vide si un nœud n'est pas une source qui convient, ou si les formats n'ont aucun type commun.
    `nom` est celui de la première source : il ne sert qu'à une sélection d'une seule."""
    if not nodes or any(n.kind not in _SOURCE_KINDS for n in nodes):
        return []
    options = callbacks.create_options(str(nodes[0].path))
    for node in nodes[1:]:
        families = {family for family, _word, _name in callbacks.create_options(str(node.path))}
        options = [option for option in options if option[0] in families]
    return options


def add_asset_actions(menu: QMenu, nodes: list, callbacks: DiskCallbacks,
                      begin_rename: Callable[[disk_tree.DiskNode], None] | None = None) -> None:
    """Les actions du clic droit sur une sélection : *Create* pour des sources qui peuvent devenir un même type, *Rename* et *Reveal* pour UNE entrée, *Delete* pour tout ce qui se supprime (asset, source, fichier, dossier), en dernier.
    Une sélection sans type commun (formats différents, ou autre chose que des sources) garde l'entrée *Create*, grisée, et dit pourquoi."""
    sources = [n for n in nodes if n.kind in _SOURCE_KINDS]
    removable = [n for n in nodes if callbacks.deletable(n)]
    options = shared_create_options(nodes, callbacks)
    paths = [str(n.path) for n in nodes]
    if sources and len(nodes) > 1 and not options:
        entry = menu.addAction(label('disk.create_menu'))
        entry.setEnabled(False)
        entry.setToolTip(label('disk.create_no_common_type' if len(sources) == len(nodes) else 'disk.create_sources_only'))
    elif len(options) == 1:
        family = options[0][0]
        menu.addAction(_icon(_FAMILY_ICONS.get(family, "add")), label('disk.create_menu')).triggered.connect(
            lambda _=False, f=family: callbacks.create_from_sources(paths, f))
    elif options:
        sub = menu.addMenu(_icon("add"), label('disk.create_as'))
        for family, word, _name in options:
            sub.addAction(_icon(_FAMILY_ICONS.get(family, "add")), word).triggered.connect(
                lambda _=False, f=family: callbacks.create_from_sources(paths, f))
    if duplicable_nodes(nodes, callbacks):
        dup = menu.addAction(_icon("copy"), label('disk.duplicate', n=len(nodes)))
        dup.setShortcut(shortcut_hints.bound("common.duplicate"))
        dup.triggered.connect(lambda _=False: callbacks.duplicate_items(list(nodes)))
    if (callbacks.edit_externally is not None and len(nodes) == 1
            and nodes[0].kind == disk_tree.ASSET and nodes[0].family in _TEXT_FILE_FAMILIES):
        path = nodes[0].path
        menu.addAction(_icon("script_file"), label('disk.edit_externally')).triggered.connect(
            lambda _=False: callbacks.edit_externally(path))
    # La fin du menu, comme partout dans l'éditeur : l'emplacement sur le disque, puis *Delete* en dernier.
    if (len(nodes) == 1 or removable) and not menu.isEmpty():
        menu.addSeparator()
    if len(nodes) == 1:
        path = nodes[0].path
        if begin_rename is not None and renamable(nodes[0]):
            menu.addAction(label('disk.rename')).triggered.connect(
                lambda _=False: begin_rename(nodes[0]))
        menu.addAction(_icon("folder"), label('common.reveal')).triggered.connect(
            lambda _=False: reveal_in_file_manager(path))
    if removable:
        menu.addAction(_icon("remove"), label('disk.delete_items', n=len(removable))).triggered.connect(
            lambda _=False: callbacks.delete_items(removable))


def add_folder_actions(menu: QMenu, folder: str, callbacks: DiskCallbacks) -> None:
    """Importer, créer un asset vierge, faire un dossier — dans `folder`. Le « + » de la vue à plat, celui de
    l'arbre et le clic droit sur le vide partagent ce menu : une seule définition de ce qu'on crée sur le disque."""
    menu.addAction(_icon("import"), label('disk.import')).triggered.connect(lambda _=False: callbacks.import_files(folder))
    sub = menu.addMenu(_icon("add"), label('disk.create_menu'))
    for kind, word in callbacks.blank_kinds:
        sub.addAction(_icon(_BLANK_ICONS.get(kind, "add")), word).triggered.connect(
            lambda _=False, k=kind: callbacks.create_blank(k, folder))
    menu.addSeparator()
    menu.addAction(_icon("folder"), label('disk.new_folder')).triggered.connect(lambda _=False: callbacks.new_folder(folder))


# Les critères de tri de l'onglet Disk. Les dossiers passent toujours avant les fichiers ; le critère
# ne départage que les fichiers entre eux (et, à égalité, le nom).
SORT_MODES = ("name", "extension", "status")


def sort_nodes(nodes, mode: str) -> list:
    """`nodes` (les enfants d'un dossier) dans l'ordre `mode` : dossiers d'abord, par nom ; puis les fichiers
    par nom, ou par extension (sans extension en tête) puis par nom."""
    def key(node):
        name = node.name.casefold()
        if node.kind == disk_tree.FOLDER:
            return (0, "", name)
        if mode == "status":
            # Les éléments qui demandent une action montent, mais les dossiers
            # restent toujours devant : la navigation ne change jamais de place.
            urgency = {disk_tree.STATUS_MISSING_SOURCE: 0,
                       disk_tree.STATUS_ORPHAN_SOURCE: 1,
                       disk_tree.STATUS_OK: 2,
                       disk_tree.STATUS_NEUTRAL: 3}.get(node.status, 3)
            return (1, urgency, name)
        return (1, node.path.suffix.casefold() if mode == "extension" else "", name)
    return sorted(nodes, key=key)


def show_sort_menu(parent: QWidget, button, current: str, on_pick: Callable[[str], None]) -> None:
    """Le menu du bouton de tri, déroulé sous `button` : un critère par entrée, celui en vigueur coché."""
    menu = QMenu(parent)
    menu.setStyleSheet(QSS.menu)
    for mode in SORT_MODES:
        action = menu.addAction(label(f'disk.sort_{mode}'))
        action.setCheckable(True)
        action.setChecked(mode == current)
        action.triggered.connect(lambda _=False, m=mode: on_pick(m))
    menu.exec(button.mapToGlobal(button.rect().bottomLeft()))


def show_plus_menu(parent: QWidget, button, folder: str | None, callbacks: DiskCallbacks | None) -> None:
    """Le menu du « + » de l'onglet Disk, déroulé sous `button`, pour créer dans `folder`."""
    if callbacks is None or folder is None:
        return
    menu = QMenu(parent)
    menu.setStyleSheet(QSS.menu)
    add_folder_actions(menu, folder, callbacks)
    menu.exec(button.mapToGlobal(button.rect().bottomLeft()))


_DRAGGING_OPACITY = 0.35


class DragDimDelegate(ElidedNameDelegate):
    """Le nom coupé de `ElidedNameDelegate`, et à demi transparent tant que l'entrée est glissée : on voit
    ce qui voyage, et que l'original est encore là.

    Le `DiskNode` d'une ligne n'est pas rangé sous le même rôle dans les deux vues (la vue à plat l'a à
    `_NODE_ROLE`, l'arbre vertical sous le sien) : chaque vue dit donc le sien à la construction, au lieu
    que le délégué devine — lire le rôle d'une autre vue rend une chaîne, et un `paint` qui lève fait
    mourir le processus."""

    def __init__(self, lines: int = 1, parent=None, node_role=_NODE_ROLE):
        super().__init__(lines, parent)
        self._node_role = node_role

    def paint(self, painter, option, index):
        if index.data(_HEADER_ROLE):
            self._paint_header(painter, option, index)
            return
        if not index.data(DRAGGING_ROLE):
            super().paint(painter, option, index)
        else:
            painter.save()
            painter.setOpacity(_DRAGGING_OPACITY)
            super().paint(painter, option, index)
            painter.restore()
        node = index.data(self._node_role)
        if isinstance(node, disk_tree.DiskNode):       # jamais d'exception dans un paint : une ligne sans nœud n'a pas de pastille
            # La couleur d'un dossier est une convention personnelle. Elle
            # vit sur l'icône elle-même, jamais dans cette pastille réservée
            # au diagnostic des fichiers.
            color = None if node.kind == disk_tree.FOLDER else status_color(node)
            if color:
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(color))
                # Une pastille, jamais un aplat : la forme garde le type,
                # la couleur ne fait que renseigner l'état ou le repère perso.
                painter.drawEllipse(option.rect.right() - 10, option.rect.top() + 6, 5, 5)
                painter.restore()


    @staticmethod
    def _paint_header(painter, option, index) -> None:
        """Un séparateur de la vue en liste : le nom du groupe, puis un filet sur le reste de la ligne."""
        painter.save()
        font = QFont(option.font)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(C.TEXT_MUTED))
        rect = option.rect.adjusted(6, 0, -6, 0)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, text)
        edge = rect.left() + painter.fontMetrics().horizontalAdvance(text) + 8
        y = rect.bottom() - painter.fontMetrics().height() // 2 + 1
        painter.setPen(QPen(QColor(C.BORDER), 1))
        painter.drawLine(edge, y, rect.right(), y)
        painter.restore()


class DropCheckMixin:
    """Ce que le survol demande au projet : ce glisser pourrait-il être déposé sur ce dossier ? La réponse vient
    d'une fonction que `window.py` donne à la vue (la vue ne connaît pas le projet) ; elle est gardée le temps
    d'un glisser, car le survol la repose à chaque mouvement de la souris. Un refus est dit une seule fois."""

    _drop_check = None

    @staticmethod
    def _canvas_actor(mime) -> str | None:
        """Le nom de l'acteur qu'un glisser venu du canvas porte (il se range dans un dossier : prefab), ou `None`."""
        if not mime.hasFormat(MIME_CANVAS_ACTOR):
            return None
        return bytes(mime.data(MIME_CANVAS_ACTOR)).decode("utf-8") or None

    @staticmethod
    def _external_files(mime) -> list[str]:
        """Les fichiers et dossiers qu'un glisser venu de l'explorateur du système porte (un glisser interne n'a pas d'URL)."""
        if mime.hasFormat(MIME_DISK_PATHS) or not mime.hasUrls():
            return []
        return [p for p in (u.toLocalFile() for u in mime.urls() if u.isLocalFile()) if Path(p).exists()]

    def set_drop_check(self, check) -> None:
        """`check(chemins, dossier) -> (possible, refus)` ; sans elle, tout dossier reçoit."""
        self._drop_check = check
        self._verdicts = {}

    def _forget_verdicts(self) -> None:
        self._verdicts = {}

    def _allowed(self, paths, target) -> bool:
        if self._drop_check is None:
            return True
        key = (tuple(paths), target)
        if key not in self._verdicts:
            possible, refusal = self._drop_check(paths, target)
            self._verdicts[key] = possible
            if not possible and refusal is not None:
                self.drop_blocked.emit(refusal)
        return self._verdicts[key]


def paint_drop_target(viewport: QWidget, rect) -> None:
    """La surimpression du dossier qui recevrait ce qu'on glisse : un voile et un cadre de la couleur d'accent
    froide, distincts du gris de la sélection. Partagée par l'arbre et la vue à plat."""
    painter = QPainter(viewport)
    color = QColor(C.ACCENT_COOL)
    fill = QColor(color)
    fill.setAlpha(60)
    painter.fillRect(rect, fill)
    painter.setPen(QPen(color, 2))
    painter.drawRect(rect.adjusted(1, 1, -1, -1))
    painter.end()


def add_disk_tab(tabs: QTabWidget, page: QWidget) -> None:
    """Pose l'onglet Disk TOUT À GAUCHE de `tabs`, avec son icône de disque — le seul onglet à en avoir une.
    L'icône suit l'état de l'onglet : atténuée, elle s'éclaire quand il est actif, comme son texte.
    L'onglet courant ne change pas : insérer à gauche ne déplace pas la sélection."""
    tabs.insertTab(0, page, label('build.disk'))

    def refresh_icon(*_ignored) -> None:
        active = tabs.currentWidget() is page
        tabs.setTabIcon(tabs.indexOf(page), icons.get("disk", C.TEXT_HI if active else C.TEXT_DIM))

    tabs.currentChanged.connect(refresh_icon)
    refresh_icon()


def icon_key(node: disk_tree.DiskNode) -> str:
    """La clé d'icône (`icons.py`) d'un fichier : celle de sa famille, sinon celle de son
    format, sinon un fichier générique."""
    return (_FAMILY_ICONS.get(node.family)
            or _SUFFIX_ICONS.get(node.path.suffix.lower(), "script_file"))


def file_icon(node: disk_tree.DiskNode):
    """L'icône d'un fichier ; sa couleur dit la marque (asset, source reliée, source sans
    asset, non géré)."""
    return icons.get(icon_key(node), mark_color(node.kind))


def mark_text(node: disk_tree.DiskNode) -> str:
    """Ce que dit la marque d'un fichier — l'infobulle de l'onglet Disk, ici comme dans l'arbre."""
    if node.status == disk_tree.STATUS_MISSING_SOURCE:
        return label('disk.source_missing')
    if node.kind == disk_tree.ASSET:
        return label('disk.asset')
    if node.kind == disk_tree.LINKED_SOURCE:
        return label('disk.source_of', name=node.owner)
    if node.kind == disk_tree.FREE_SOURCE:
        return label('disk.free_source')
    return label('disk.unsupported')


def mark_color(kind: str) -> str:
    return {disk_tree.ASSET: C.TEXT_HI,
            disk_tree.LINKED_SOURCE: C.TEXT_NORM,
            disk_tree.FREE_SOURCE: C.ACCENT_YLW}.get(kind, C.TEXT_DIM)


def status_color(node: disk_tree.DiskNode) -> str | None:
    """Couleur réservée aux états qui réclament une action.

    Un asset sain n'a pas besoin de signal : l'absence de pastille garde la
    mosaïque calme et laisse ressortir les exceptions.
    """
    return {disk_tree.STATUS_ORPHAN_SOURCE: C.ACCENT_YLW,
            disk_tree.STATUS_MISSING_SOURCE: C.ACCENT_RED}.get(node.status)


def add_folder_color_actions(menu: QMenu, node: disk_tree.DiskNode, changed: Callable[[], None]) -> None:
    """Six pastilles de couleur directement dans le menu d'un vrai dossier."""
    if node.kind != disk_tree.FOLDER:
        return
    if not menu.isEmpty():
        menu.addSeparator()
    current = folder_color_for(node.path)
    row = QWidget(menu)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(10, 4, 10, 4)
    layout.setSpacing(5)
    title = QLabel(label('disk.folder_color'))
    title.setStyleSheet(f"color:{C.TEXT_NORM};")
    layout.addWidget(title)

    def add_dot(name: str, color: str | None) -> None:
        selected = current == color
        dot = QToolButton(row)
        dot.setFixedSize(18, 18)
        dot.setCursor(Qt.CursorShape.PointingHandCursor)
        dot.setToolTip(label(name))
        dot.setText("×" if color is None else "")
        fill = color or "transparent"
        border = C.TEXT_HI if selected else (C.BORDER_MID if color is None else color)
        text = C.TEXT_DIM if color is None else C.BG_DEEP
        dot.setStyleSheet(
            f"QToolButton{{background:{fill};color:{text};border:2px solid {border};border-radius:9px;"
            f"padding:0;font-size:12px;font-weight:700;}}"
            f"QToolButton:hover{{border-color:{C.TEXT_HI};}}")
        dot.clicked.connect(lambda _=False, c=color: (set_folder_color(node.path, c), changed(), menu.close()))
        layout.addWidget(dot)

    add_dot('disk.folder_color_none', None)
    for key, color in FOLDER_COLORS.items():
        add_dot(f'disk.folder_color_{key}', color)
    action = QWidgetAction(menu)
    action.setDefaultWidget(row)
    menu.addAction(action)


class _DiskList(DropCheckMixin, QListWidget):
    """La liste à plat : on y glisse ses entrées vers un dossier (une entrée dossier ou « ... »)."""

    move_requested = pyqtSignal(list, str)           # (chemins, dossier de destination)
    drop_blocked = pyqtSignal(object)                # (chemin, motif) du premier élément qu'un survol refuse
    actor_dropped = pyqtSignal(str, str)             # (acteur du canvas, dossier de destination)
    files_dropped = pyqtSignal(list, str)            # (fichiers de l'explorateur, dossier survolé ou « » : le dossier affiché)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._verdicts: dict = {}
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)      # plusieurs entrées se glissent d'un coup
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)       # jamais Move : un dépôt accepté AILLEURS (canvas) ferait retirer la ligne par Qt
        self._pressed_item: QListWidgetItem | None = None     # l'entrée sous la souris quand le bouton est pressé
        self._drop_hover: QListWidgetItem | None = None       # l'entrée survolée par un glisser qui pourrait la recevoir
        self._pressed_at = None

    # Dans une liste en icônes à sélection multiple, Qt tire un rectangle d'élastique dès que la souris bouge
    # bouton enfoncé — même quand on a pressé SUR une entrée. Presser sur une entrée et bouger, c'est glisser
    # cette entrée (ou la sélection, si elle en fait partie) ; le rectangle ne part que d'un fond vide.
    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint()) if event.button() == Qt.MouseButton.LeftButton else None
        self._pressed_item = item
        self._pressed_at = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pressed_item is None or not event.buttons() & Qt.MouseButton.LeftButton:
            super().mouseMoveEvent(event)
            return
        if (event.position().toPoint() - self._pressed_at).manhattanLength() < QApplication.startDragDistance():
            return                                          # pas encore un glisser : et surtout pas un rectangle
        item, self._pressed_item = self._pressed_item, None
        if not item.isSelected():
            self.clearSelection()
            item.setSelected(True)
        self.startDrag(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, event):
        self._pressed_item = None
        super().mouseReleaseEvent(event)

    def mimeTypes(self):
        return [MIME_DISK_PATHS]

    def mimeData(self, items):
        nodes = [i.data(_NODE_ROLE) for i in items if i.data(_NODE_ROLE) is not None]
        return disk_mime((n.path for n in nodes), nodes)

    def _target(self, event) -> str | None:
        item = self.itemAt(event.position().toPoint())
        return item.data(_DROP_ROLE) if item is not None else None

    def startDrag(self, actions):
        """Les entrées glissées passent à demi transparentes jusqu'au dépôt (ou à l'abandon)."""
        items = self.selectedItems()
        for item in items:
            item.setData(DRAGGING_ROLE, True)
        try:
            super().startDrag(Qt.DropAction.CopyAction)
        finally:
            for item in items:
                try:
                    item.setData(DRAGGING_ROLE, False)
                except RuntimeError:                      # la vue a été reconstruite par le déplacement
                    pass
            self.viewport().update()

    def dragEnterEvent(self, event):
        self._forget_verdicts()
        mime = event.mimeData()
        if dropped_paths(mime) or self._canvas_actor(mime) or self._external_files(mime):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        paths, target = dropped_paths(event.mimeData()), self._target(event)
        if self._external_files(event.mimeData()):        # l'explorateur : le dossier survolé, sinon le dossier affiché
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self._set_drop_hover(self.itemAt(event.position().toPoint()) if target else None)
        elif self._canvas_actor(event.mimeData()):          # un acteur du canvas : tout dossier le reçoit
            event.setDropAction(Qt.DropAction.CopyAction)
            if target:
                event.accept()
                self._set_drop_hover(self.itemAt(event.position().toPoint()))
            else:
                event.ignore()
                self._set_drop_hover(None)
        elif paths and target and self._allowed(paths, target):
            event.acceptProposedAction()
            self._set_drop_hover(self.itemAt(event.position().toPoint()))
        else:
            event.ignore()                                # le curseur « interdit » : pas de surimpression non plus
            self._set_drop_hover(None)

    def dragLeaveEvent(self, event):
        self._set_drop_hover(None)
        self._forget_verdicts()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        target = self._target(event)
        paths = dropped_paths(event.mimeData())
        actor = self._canvas_actor(event.mimeData())
        files = self._external_files(event.mimeData())
        self._set_drop_hover(None)
        self._forget_verdicts()
        if files:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.files_dropped.emit(files, target or "")
            return
        if target and actor:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.actor_dropped.emit(actor, target)
            return
        if not (target and paths):
            event.ignore()
            return
        event.acceptProposedAction()
        self.clearSelection()                             # sinon Qt retirerait lui-même les lignes « déplacées »
        self.move_requested.emit(paths, target)

    def _set_drop_hover(self, item: QListWidgetItem | None) -> None:
        """L'entrée qui recevrait le dépôt, surlignée tant que la souris la survole."""
        if item is not self._drop_hover:
            self._drop_hover = item
            self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drop_hover is not None:
            paint_drop_target(self.viewport(), self.visualItemRect(self._drop_hover))


def openable(node: disk_tree.DiskNode) -> tuple[str, str, str] | None:
    """`(famille, nom, chemin)` de l'asset qu'un double-clic ouvre dans son écran, ou `None`. Un fichier d'asset s'ouvre ;
    une source ne s'ouvre que si UN seul asset la cite (sinon, lequel ?). Partagée par l'arbre et la vue à plat."""
    if not node.family or not node.owner:
        return None
    if node.kind == disk_tree.ASSET or (node.kind == disk_tree.LINKED_SOURCE and ", " not in node.owner):
        return node.family, node.owner, str(node.path)
    return None


class DiskView(QWidget):
    refresh_requested = pyqtSignal()
    asset_open_requested = pyqtSignal(str, str, str)  # (famille, nom, chemin) : double-clic sur un asset
    actor_dropped = pyqtSignal(str, str)             # (acteur du canvas, dossier) : un acteur glissé du canvas
    move_requested = pyqtSignal(list, str)           # (chemins, dossier de destination)
    drop_blocked = pyqtSignal(object)                # (chemin, motif) : un survol que le projet refuse
    rename_requested = pyqtSignal(str, str)          # (chemin de l'entrée, nouveau nom)
    folder_color_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout_mode = LAYOUT_MODES[0]
        self._grid_cell_width = _CELL.width()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        bar, row = panel_bar()
        refresh = bar_button(label('build.refresh'))
        refresh.setToolTip(tooltip(title=label('disk.refresh_title'), body=label('disk.refresh_tip')))
        refresh.clicked.connect(lambda: self.refresh_requested.emit())
        row.addWidget(refresh)
        self._callbacks: DiskCallbacks | None = None
        # « Create <nom> » : n'existe que pour UNE source libre sélectionnée. Le clic prend le type le plus courant ;
        # la flèche, quand le fichier peut devenir autre chose (un PNG : sprite, fond ou police), propose les autres.
        self._btn_create = bar_button("")
        self._btn_create.setToolTip(tooltip(title=label('disk.create_menu'), body=label('disk.create_named_tip')))
        self._btn_create.clicked.connect(self._create_default)
        self._btn_create.hide()
        row.addWidget(self._btn_create)
        self._btn_create_more = bar_button("▾")
        self._btn_create_more.setToolTip(tooltip(title=label('disk.create_menu'), body=label('disk.create_other_tip')))
        self._btn_create_more.clicked.connect(self._show_create_types)
        self._btn_create_more.hide()
        row.addWidget(self._btn_create_more)
        self._create_options: list = []
        self._create_paths: list[str] = []
        self._breadcrumb = QHBoxLayout()
        self._breadcrumb.setSpacing(0)
        row.addLayout(self._breadcrumb)
        row.addStretch()
        self._summary = QLabel("—")
        self._summary.setFont(QFont(T.UI, T.SM))
        self._summary.setStyleSheet(f"color:{C.TEXT_MUTED};")
        row.addWidget(self._summary)
        self._btn_plus = W.btn_add_menu(label('disk.plus_tip'))
        self._btn_plus.clicked.connect(self._show_plus_menu)
        row.addWidget(self._btn_plus)
        self._sort = SORT_MODES[0]
        self._btn_sort = W.btn_sort(label('disk.sort_tip'))
        self._btn_sort.clicked.connect(
            lambda: show_sort_menu(self, self._btn_sort, self._sort, self._set_sort))
        row.addWidget(self._btn_sort)
        self._btn_layout = W.btn_list_view(label('disk.list_view_tip'))
        self._btn_layout.toggled.connect(lambda on: self.set_layout_mode("list" if on else "grid"))
        row.addWidget(self._btn_layout)
        self._btn_grid_size = W.btn_grid_size(label('disk.grid_size_tip'))
        self._btn_grid_size.toggled.connect(self._on_grid_size_toggled)
        row.addWidget(self._btn_grid_size)
        self._grid_size_slider = QSlider(Qt.Orientation.Horizontal)
        self._grid_size_slider.setRange(_GRID_CELL_MIN, _GRID_CELL_MAX)
        self._grid_size_slider.setValue(self._grid_cell_width)
        self._grid_size_slider.setFixedWidth(112)
        self._grid_size_slider.setToolTip(label('disk.grid_size_tip'))
        self._grid_size_slider.setStyleSheet(
            f"QSlider::groove:horizontal{{height:4px;background:{C.BORDER_MID};border-radius:2px;}}"
            f"QSlider::handle:horizontal{{width:12px;margin:-4px 0;background:{C.ACCENT};border-radius:6px;}}"
            f"QSlider::handle:horizontal:hover{{background:{C.ACCENT_HOVER};}}")
        self._grid_size_slider.valueChanged.connect(self.set_grid_cell_width)
        self._grid_size_slider.hide()
        row.addWidget(self._grid_size_slider)
        self._btn_search = W.btn_search(label('wdg.filter_by_name'))
        self._btn_search.setCheckable(True)
        self._btn_search.toggled.connect(self._on_search_toggled)
        row.addWidget(self._btn_search)
        v.addWidget(bar)

        # Champ de filtre : masqué tant que la loupe n'est pas enfoncée ; Échap le referme (comme dans l'arbre).
        self._search_box = W.search_box()
        self._search_box.textChanged.connect(self._apply_filter)
        close_on_escape = self._search_box.keyPressEvent
        self._search_box.keyPressEvent = lambda e: (
            self._btn_search.setChecked(False) if e.key() == Qt.Key.Key_Escape else close_on_escape(e))
        self._search_row = QWidget()
        self._search_row.setStyleSheet(f"background:{C.BG_BASE};")
        search_layout = QHBoxLayout(self._search_row)
        search_layout.setContentsMargins(S.GUTTER, S.SM, S.MD, S.SM)
        search_layout.addWidget(self._search_box)
        self._search_row.hide()
        v.addWidget(self._search_row)

        self._list = _DiskList()
        self._list.move_requested.connect(self.move_requested)
        self._list.drop_blocked.connect(self.drop_blocked)
        self._list.actor_dropped.connect(self.actor_dropped)
        self._list.files_dropped.connect(self._on_files_dropped)
        self._list.setSpacing(0)
        self._list.setFont(QFont(T.UI, T.SM))
        # Un clic sur une entrée déjà choisie (ou F2) en édite le nom ; seules les entrées `renamable` portent le drapeau d'édition.
        self._list.setEditTriggers(QListWidget.EditTrigger.SelectedClicked | QListWidget.EditTrigger.EditKeyPressed)
        self._list.setStyleSheet(
            f"QListWidget{{background:{C.BG_DEEP};border:none;padding:6px;outline:none;}}"
            f"QListWidget::item{{padding:4px;border:1px solid transparent;border-radius:4px;}}"
            f"QListWidget::item:hover{{background:{C.BG_HOVER};}}"
            f"QListWidget::item:selected{{background:{C.BG_SEL};border-color:{C.BORDER_MID};}}"
            f"QListWidget::item:selected:active{{border-color:{C.ACCENT};}}"
            f"QListWidget::item:focus{{outline:none;}}")
        self._list.itemDoubleClicked.connect(self._enter)
        self._list.itemSelectionChanged.connect(self._sync_create_button)
        bind_delete_key(self._list, self._selected_nodes, lambda: self._callbacks)
        bind_duplicate_key(self._list, self._selected_nodes, lambda: self._callbacks)
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        v.addWidget(self._list, 1)

        self._root: disk_tree.DiskNode | None = None
        self._trail: list[str] = []   # noms des dossiers qu'on a descendus sous la racine
        self._apply_layout()

    # ── Mosaïque ou liste ─────────────────────────────────────────

    def layout_mode(self) -> str:
        return self._layout_mode

    def grid_cell_width(self) -> int:
        return self._grid_cell_width

    def set_grid_cell_width(self, width) -> None:
        """Largeur d'une tuile de mosaïque ; la hauteur et l'icône suivent.

        Les cellules restent légèrement plus larges que hautes, afin de garder
        deux lignes de nom sans donner une impression de cartes massives.
        """
        width = max(_GRID_CELL_MIN, min(_GRID_CELL_MAX, int(width)))
        if width == self._grid_cell_width:
            return
        self._grid_cell_width = width
        self._grid_size_slider.blockSignals(True)
        self._grid_size_slider.setValue(width)
        self._grid_size_slider.blockSignals(False)
        self._apply_layout()
        self._show()

    def set_layout_mode(self, mode: str) -> None:
        """`grid` (mosaïque d'icônes) ou `list` (une ligne par entrée ; séparée en groupes par extension
        quand le tri est par extension)."""
        if mode not in LAYOUT_MODES:
            return
        self._layout_mode = mode
        self._btn_layout.blockSignals(True)
        self._btn_layout.setChecked(mode == "list")
        self._btn_layout.blockSignals(False)
        self._btn_grid_size.setVisible(mode == "grid")
        if mode != "grid":
            self._btn_grid_size.setChecked(False)
        self._grid_size_slider.setVisible(mode == "grid" and self._btn_grid_size.isChecked())
        self._apply_layout()
        self._show()

    def _on_grid_size_toggled(self, shown: bool) -> None:
        self._grid_size_slider.setVisible(self._layout_mode == "grid" and shown)

    def _apply_layout(self) -> None:
        """Règle la liste Qt pour le mode courant ; les entrées sont reconstruites par `_show`. Changer de
        `viewMode` remet le mouvement et les dépôts à leur défaut : tout est donc reposé ici."""
        grid = self._layout_mode == "grid"
        lst = self._list
        lst.setViewMode(QListWidget.ViewMode.IconMode if grid else QListWidget.ViewMode.ListMode)
        lst.setResizeMode(QListWidget.ResizeMode.Adjust)
        lst.setMovement(QListWidget.Movement.Static)
        # `setMovement(Static)` coupe les dépôts sur le viewport : sans cette ligne, les événements de glisser
        # n'atteignent jamais la liste (et un dépôt direct, lui, passerait quand même dans un test).
        lst.viewport().setAcceptDrops(True)
        lst.setWordWrap(grid)
        lst.setItemDelegate(DragDimDelegate(lines=2 if grid else 1, parent=lst))   # nom coupé, extension gardée
        cell = QSize(self._grid_cell_width, max(86, round(self._grid_cell_width * _CELL.height() / _CELL.width())))
        icon = QSize(max(36, min(64, round(self._grid_cell_width * _ICON.width() / _CELL.width()))),
                     max(36, min(64, round(self._grid_cell_width * _ICON.height() / _CELL.width()))))
        lst.setIconSize(icon if grid else _ROW_ICON)
        lst.setGridSize(cell if grid else QSize())
        lst.setUniformItemSizes(grid)

    def _set_sort(self, mode: str) -> None:
        self._sort = mode
        self._show()

    def _on_search_toggled(self, shown: bool) -> None:
        self._search_row.setVisible(shown)
        if shown:
            self._search_box.setFocus()
        else:
            self._search_box.clear()

    def _apply_filter(self, text: str = "") -> None:
        """Ne montre que les entrées dont le nom contient `text` ; « ... » et le disque `assets` restent."""
        needle = text.strip().casefold()
        for i in range(self._list.count()):
            item = self._list.item(i)
            fixed = item.data(_UP_ROLE) or item.data(_OPEN_ROLE)
            item.setHidden(bool(needle) and not fixed and needle not in item.text().casefold())

    def set_drop_check(self, check) -> None:
        self._list.set_drop_check(check)

    def set_callbacks(self, callbacks: DiskCallbacks) -> None:
        self._callbacks = callbacks

    # ── Création, import, suppression ─────────────────────────────

    def _selected_nodes(self) -> list:
        return [n for n in (i.data(_NODE_ROLE) for i in self._list.selectedItems()) if n is not None]

    def _shown_folder(self) -> str | None:
        folder = self._current() if self._root is not None else None
        return str(folder.path) if folder is not None else None

    def _on_files_dropped(self, files: list, folder: str) -> None:
        """Des fichiers de l'explorateur : dans le dossier survolé, sinon dans celui qu'on affiche."""
        folder = folder or self._shown_folder()
        if folder and self._callbacks is not None:
            self._callbacks.import_paths(files, folder)

    def _show_plus_menu(self) -> None:
        """Le « + » : importer un fichier, créer un asset vierge, faire un dossier — dans le dossier affiché."""
        show_plus_menu(self, self._btn_plus, self._shown_folder(), self._callbacks)

    def _sync_create_button(self) -> None:
        """« Create » suit la sélection : des sources qui peuvent devenir un même type, sinon rien."""
        nodes = self._selected_nodes()
        options = shared_create_options(nodes, self._callbacks) if self._callbacks is not None else []
        self._create_options = options
        self._create_paths = [str(n.path) for n in nodes] if options else []
        self._btn_create.setVisible(bool(options))
        self._btn_create_more.setVisible(len(options) > 1)
        if options:
            self._btn_create.setText(label('disk.create_menu'))

    def _create_default(self) -> None:
        if self._callbacks is not None and self._create_options:
            self._callbacks.create_from_sources(self._create_paths, self._create_options[0][0])

    def _show_create_types(self) -> None:
        if self._callbacks is None or not self._create_options:
            return
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        for family, word, _name in self._create_options:
            menu.addAction(_icon(_FAMILY_ICONS.get(family, "add")), word).triggered.connect(
                lambda _=False, f=family: self._callbacks.create_from_sources(self._create_paths, f))
        menu.exec(self._btn_create_more.mapToGlobal(self._btn_create_more.rect().bottomLeft()))

    def _on_context_menu(self, position) -> None:
        """Le clic droit : l'entrée sous la souris rejoint la sélection si elle n'en fait pas partie."""
        if self._callbacks is None:
            return
        item = self._list.itemAt(position)
        if item is not None and not item.isSelected():
            self._list.clearSelection()
            item.setSelected(True)
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        nodes = self._selected_nodes()
        if item is None:                      # le vide : les actions du « + », dans le dossier affiché
            folder = self._shown_folder()
            if folder is not None:
                add_folder_actions(menu, folder, self._callbacks)
        else:
            add_asset_actions(menu, nodes, self._callbacks, self.begin_rename)
            if len(nodes) == 1:
                add_folder_color_actions(menu, nodes[0], self.folder_color_changed.emit)
        if not menu.isEmpty():
            menu.exec(self._list.viewport().mapToGlobal(position))

    # ── Renommer en place ─────────────────────────────────────────

    def begin_rename(self, node: disk_tree.DiskNode) -> None:
        """L'entrée de `node` devient une ligne éditable ; le nouveau nom part en `rename_requested` à la validation."""
        item = next((self._list.item(row) for row in range(self._list.count())
                     if getattr(self._list.item(row).data(_NODE_ROLE), "path", None) == node.path), None)
        if item is not None and item.flags() & Qt.ItemFlag.ItemIsEditable:
            self._list.setCurrentItem(item)
            self._list.editItem(item)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """Le nom validé dans l'éditeur ; un nom inchangé (ou Échap) ne demande rien."""
        node = item.data(_NODE_ROLE)
        if node is not None and item.text() != node.name:
            self.rename_requested.emit(str(node.path), item.text())

    # ── Contenu ───────────────────────────────────────────────────

    def set_tree(self, root: disk_tree.DiskNode | None) -> None:
        """Remplace l'arbre. On reste dans le dossier où l'on était, s'il existe encore."""
        self._root = root
        self._trail = self._surviving_trail()
        self._show()

    def _surviving_trail(self) -> list[str]:
        node, kept = self._root, []
        for name in self._trail:
            node = next((c for c in (node.children if node else ())
                         if c.kind == disk_tree.FOLDER and c.name == name), None)
            if node is None:
                break
            kept.append(name)
        return kept

    def _current(self) -> disk_tree.DiskNode | None:
        node = self._root
        for name in self._trail:
            node = next(c for c in node.children if c.kind == disk_tree.FOLDER and c.name == name)
        return node

    def show_folder(self, path) -> None:
        """Affiche le dossier `path` (un chemin sous la racine de l'arbre courant) ;
        ignoré s'il n'en fait pas partie."""
        if self._root is None:
            return
        try:
            parts = Path(path).relative_to(self._root.path).parts
        except ValueError:
            return
        self._trail = list(parts)
        self._trail = self._surviving_trail()
        self._show()

    def select_file(self, path) -> None:
        """Montre le dossier de `path` et sélectionne son fichier. Le filtre est levé : il pourrait le cacher."""
        if self._root is None:
            return
        self._btn_search.setChecked(False)
        self.show_folder(Path(path).parent)
        for row in range(self._list.count()):
            node = self._list.item(row).data(_NODE_ROLE)
            if node is not None and node.path == Path(path):
                self._list.setCurrentRow(row)
                self._list.scrollToItem(self._list.item(row))
                return

    def _go_to(self, depth: int) -> None:
        """Remonte au dossier du fil d'ariane de profondeur `depth` (0 = Assets)."""
        self._trail = self._trail[:depth]
        self._show()

    def _enter(self, item: QListWidgetItem) -> None:
        if item.data(_UP_ROLE):
            self._go_to(len(self._trail) - 1)
            return
        if item.data(_OPEN_ROLE):
            reveal_in_file_manager(self._root.path)
            return
        node = item.data(_NODE_ROLE)
        if node is not None and node.kind == disk_tree.FOLDER:
            self._trail.append(node.name)
            self._show()
        elif node is not None and (target := openable(node)) is not None:
            self.asset_open_requested.emit(*target)

    def _show(self) -> None:
        self._rebuild_breadcrumb()
        self._list.clear()
        folder = self._current() if self._root is not None else None
        if folder is None:
            self._summary.setText("—")
            return
        # Toujours une première entrée : hors de la racine « ... » (dossier en filet) remonte ;
        # à la racine il n'y a rien au-dessus, le disque `assets` ouvre le dossier lui-même.
        self._list.addItem(self._up_item() if self._trail else self._assets_item())
        group = None
        for child in sort_nodes(folder.children, self._sort):
            if self._layout_mode == "list" and self._sort == "extension" and self._group_of(child) != group:
                group = self._group_of(child)
                self._list.addItem(self._header_item(group))
            self._list.addItem(self._item(child))
        assets = sum(1 for c in folder.children if c.kind == disk_tree.ASSET)
        sources = sum(1 for c in folder.children if c.kind == disk_tree.FREE_SOURCE)
        self._summary.setText(label('disk.counts', assets=assets, sources=sources))
        self._apply_filter(self._search_box.text())

    @staticmethod
    def _group_of(node: disk_tree.DiskNode) -> str:
        """Le groupe d'un séparateur de la vue en liste : les dossiers, puis une extension par groupe."""
        if node.kind == disk_tree.FOLDER:
            return label('disk.group_folders')
        return node.path.suffix.lower() or label('disk.group_no_extension')

    def _header_item(self, text: str) -> QListWidgetItem:
        """Un séparateur de la vue en liste : ni sélectionnable, ni glissable, ni cible de dépôt."""
        item = QListWidgetItem(text)
        item.setSizeHint(_HEADER)
        item.setData(_HEADER_ROLE, True)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        return item

    def _place(self, item: QListWidgetItem) -> None:
        """La taille et l'alignement d'une entrée selon le mode : cellule centrée en mosaïque, ligne à gauche en liste."""
        if self._layout_mode == "grid":
            item.setSizeHint(QSize(self._grid_cell_width,
                                   max(86, round(self._grid_cell_width * _CELL.height() / _CELL.width()))))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        else:
            item.setSizeHint(_ROW)
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def _up_item(self) -> QListWidgetItem:
        """« ... », toujours en tête hors de la racine : un double-clic remonte d'un niveau.
        Le dossier en filet est réservé à cette entrée ; les vrais dossiers sont pleins."""
        item = QListWidgetItem("...")
        self._place(item)
        item.setData(_UP_ROLE, True)
        item.setFlags((item.flags() | Qt.ItemFlag.ItemIsDropEnabled) & ~Qt.ItemFlag.ItemIsDragEnabled)
        parent = self._current().path.parent
        item.setData(_DROP_ROLE, str(parent))           # déposer sur « ... », c'est ranger dans le dossier du dessus
        item.setIcon(icons.folder_icon(True))
        item.setForeground(QColor(C.TEXT_HI))
        item.setToolTip(label('disk.up_tip'))
        return item

    def _assets_item(self) -> QListWidgetItem:
        """À la racine, un disque nommé comme le dossier lui-même (`assets`) : un double-clic
        l'ouvre dans l'explorateur de fichiers du système."""
        item = QListWidgetItem(self._root.name)
        self._place(item)
        item.setData(_OPEN_ROLE, True)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
        item.setIcon(icons.get("disk", icons.COLOR_FOLDER))
        item.setForeground(QColor(C.TEXT_HI))
        item.setToolTip(label('disk.open_assets_tip'))
        return item

    def _item(self, node: disk_tree.DiskNode) -> QListWidgetItem:
        item = QListWidgetItem(node.name)
        self._place(item)
        item.setData(_NODE_ROLE, node)
        if renamable(node):
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        if node.kind == disk_tree.FOLDER:
            item.setIcon(icons.folder_icon(False, folder_color_for(node.path) or icons.COLOR_FOLDER))
            item.setData(_DROP_ROLE, str(node.path))
            item.setForeground(QColor(C.TEXT_HI))
            return item
        item.setIcon(file_icon(node))
        item.setForeground(QColor(mark_color(node.kind)))
        item.setToolTip(mark_text(node))
        return item

    # ── Fil d'ariane ──────────────────────────────────────────────

    def _rebuild_breadcrumb(self) -> None:
        while self._breadcrumb.count():
            widget = self._breadcrumb.takeAt(0).widget()
            if widget is not None:
                # `hide()` tout de suite : deleteLater seul le laisse affiché un instant. Jamais `setParent(None)` pour
                # cela : un widget sans parent devient une FENÊTRE de premier niveau, et le maillon « Assets » clignotait
                # comme une petite fenêtre à chaque rafraîchissement de l'onglet Disk.
                widget.hide()
                widget.deleteLater()
        if self._root is None:
            return
        names = [label('disk.root')] + self._trail
        for depth, name in enumerate(names):
            if depth:
                separator = QLabel("›")
                separator.setStyleSheet(f"color:{C.TEXT_DIM};")
                self._breadcrumb.addWidget(separator)
            last = depth == len(names) - 1
            button = QPushButton(name)
            button.setFlat(True)
            button.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold if last else QFont.Weight.Normal))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton{{border:none;padding:0 5px;color:{C.TEXT_HI if last else C.TEXT_NORM};}}"
                f"QPushButton:hover{{color:{C.TEXT_HI};}}")
            button.clicked.connect(lambda _=False, d=depth: self._go_to(d))
            self._breadcrumb.addWidget(button)
