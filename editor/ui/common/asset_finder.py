"""
ui/common/asset_finder.py — LE panneau qui liste les assets d'un projet.

Un seul composant pour toutes les familles (sprites, scènes, prefabs, fonds,
scripts, polices, palettes, sfx, musiques, tables). Les écrans ne décrivent que
ce qui diffère vraiment — où sont les assets, comment on les renomme, comment on
les supprime — via `AssetKind` ; le peuplement, les sous-sections repliables, le
filtre, le renommage en place, le menu contextuel et la sélection sont écrits
ici, une fois.

## L'arbre de nœuds

La source d'une famille n'est pas une liste mais un ARBRE (`AssetNode` : un
dossier, ou un asset). C'est la couture du chantier, et elle est délibérée :
l'utilisateur pourra ranger ses assets dans ses propres dossiers. Aujourd'hui
les scripts rendent déjà un vrai arbre (leur dossier est imbriqué sur disque) et
les familles adossées à un `ResourceStore` n'en rendent qu'un seul niveau —
`ResourceStore` est plat par construction. Le jour où il saura les sous-dossiers,
`store_nodes` rendra un arbre et CE fichier ne bouge pas.

## La source de vérité

`AssetKind.nodes` lit la source de vérité de sa famille, jamais une copie :
- les neuf familles adossées à un `ResourceStore` lisent la COLLECTION EN
  MÉMOIRE (`project.sprites`…), pas le disque — sinon un asset renommé mais pas
  encore sauvé, ou `soft_delete`é mais dont le JSON traîne jusqu'à la fermeture,
  apparaîtrait à côté de la plaque ;
- les scripts lisent le DISQUE, parce que c'est leur vérité à eux : ce sont des
  fichiers `.lua`, sans modèle `Resource` qui les tiendrait en mémoire.

Cf. docs/asset-finder.md pour l'état des lieux et la décision.
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.tooltip import tooltip
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QMenu,
    QAbstractItemView, QMessageBox, QSizePolicy, QScrollArea, QHeaderView,
)
from PyQt6 import sip
from PyQt6.QtGui import QFont, QColor, QDrag
from PyQt6.QtCore import (
    Qt, pyqtSignal, QSize, QTimer, QMimeData, QByteArray, QItemSelectionModel,
)

from ui.common.theme import C, T, S, QSS, ui_font
from ui.common.selection_grammar import RowSelectionDelegate
from ui.common.widgets import W, FinderSection
from ui.common.icons import get as _ico, folder_icon, COLOR_DEFAULT, COLOR_FOLDER
from ui.common.reveal import reveal_in_file_manager
from core.history import get_history, MacroCmd, RefreshAfterCmd

_ROLE_OBJ = Qt.ItemDataRole.UserRole
_ROLE_FOLDER = Qt.ItemDataRole.UserRole + 1   # id d'un dossier d'auteur (obj None)


# ──────────────────────────────────────────────────────────────────
#  Le nœud
# ──────────────────────────────────────────────────────────────────

@dataclass
class AssetNode:
    """Un nœud de l'arbre d'une famille : un dossier, ou un asset.

    `obj` est l'asset lui-même — un `Resource` pour les familles adossées à un
    `ResourceStore`, un `Path` pour les scripts. Il vaut None pour un dossier :
    c'est ce qui distingue les deux, plutôt qu'un drapeau à tenir d'accord avec
    le reste.

    `folder_id`/`color` ne concernent qu'un dossier d'AUTEUR (créé via un
    `FolderScheme`) : son identité durable dans le store et sa couleur de
    repérage. Un dossier deviné (préfixe de sprite, sous-dossier de script) les
    laisse vides — il n'est pas éditable."""
    name: str
    obj: Any = None
    children: list["AssetNode"] = field(default_factory=list)
    folder_id: Optional[str] = None
    color: str = ""

    @property
    def is_folder(self) -> bool:
        return self.obj is None


@dataclass
class FolderScheme:
    """Rend une famille rangeable en dossiers d'auteur, imbricables.

    Le panneau la construit en capturant le store partagé (`AssetFolderStore`) et
    la famille ; le finder ne connaît que ces opérations, jamais le sidecar. Une
    famille sans `FolderScheme` n'a pas de dossiers éditables — c'est l'opt-in qui
    laisse les autres familles inchangées le temps qu'elles l'adoptent."""

    folders: Callable[[], list[Any]]                       # -> [{id,name,parent_id,color}]
    create: Callable[[str, Optional[str]], Any]            # (name, parent_id)
    rename: Callable[[str, str], bool]                     # (id, name)
    delete: Callable[[str], Any]                           # (id)
    set_parent: Callable[[str, Optional[str]], bool]       # (id, parent_id)
    move: Callable[[Any, Optional[str]], Any]              # (asset, folder_id)
    folder_of: Callable[[Any], Optional[str]]              # (asset) -> id
    # Range un lot d'assets dans un NOUVEAU dossier auto-nommé, en un geste
    # (menu « Grouper »). None = la famille ne sait pas grouper d'un clic.
    group: Optional[Callable[[list, Optional[str]], Any]] = None  # (assets, parent) -> folder


def folded_nodes(raw_assets: list[AssetNode], scheme: FolderScheme) -> list[AssetNode]:
    """Range des assets plats sous les dossiers d'auteur (arbre par `parent_id`).

    Les dossiers viennent en tête, dans l'ordre du store ; un asset sans dossier
    (ou de dossier inconnu) retombe à la racine — jamais perdu."""
    infos = list(scheme.folders())
    # Les anciennes données peuvent contenir une couleur ; elle est ignorée afin
    # que tous les dossiers restent neutres sans migration destructive.
    fnodes = {f.id: AssetNode(name=f.name, folder_id=f.id) for f in infos}
    roots: list[AssetNode] = []
    for f in infos:
        node = fnodes[f.id]
        parent = fnodes.get(f.parent_id) if f.parent_id else None
        (parent.children if parent is not None else roots).append(node)
    for asset in raw_assets:
        fid = scheme.folder_of(asset.obj) if asset.obj is not None else None
        host = fnodes.get(fid) if fid else None
        (host.children if host is not None else roots).append(asset)
    return roots


# ──────────────────────────────────────────────────────────────────
#  La description d'une famille
# ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AssetKind:
    """Ce qu'un écran déclare pour qu'une famille s'affiche dans un finder.

    Tout est optionnel sauf `label`, `icon` et `nodes` : une famille sans
    `rename` n'est simplement pas renommable depuis le finder, et son entrée de
    menu n'apparaît pas. On ne grise pas une action impossible, on ne la propose
    pas — l'éditeur rend le matériel fidèlement, il ne le commente pas.
    """

    label: str                                   # titre de section — « Tables »
    icon: str                                    # clé ui/common/icons.py
    nodes: Callable[[Any], list[AssetNode]]      # projet -> arbre (LA vérité)

    # Icône neutre par défaut : dans un finder, un type se lit à la FORME de
    # l'icône, pas à sa couleur (cf. project_theme_gba_redesign). `icon_of`
    # n'existe que pour les familles dont l'icône dépend de l'asset lui-même —
    # l'extension d'un script, les couleurs d'une palette.
    color: str = COLOR_DEFAULT
    icon_of: Optional[Callable[[Any], Any]] = None
    # Affiché à la place de la liste quand la famille est vide. Dit d'où vient
    # un asset quand ce n'est pas d'un « + » — une police naît d'un PNG déposé
    # dans assets/fonts/, pas d'un bouton.
    empty_text: str = ""
    # Suffixe affiché à droite du nom, en italique, jamais édité — « 12 × 3 », « 16 ».
    # Le nom NU reste l'identité : c'est lui qu'on édite et qu'on cherche.
    suffix_of: Optional[Callable[[Any], str]] = None
    tooltip_of: Optional[Callable[[Any], str]] = None

    # (projet, asset, nouveau_nom) -> nom RÉELLEMENT appliqué ("" si refusé).
    rename: Optional[Callable[[Any, Any, str], str]] = None
    # (projet, asset) -> Command de suppression, PAS encore poussée. Le finder
    # la pousse (une seule ligne), ou groupe tout un lot dans un `MacroCmd` pour
    # un unique Ctrl+Z. La bâtir sans l'exécuter est ce qui rend le lot possible.
    delete: Optional[Callable[[Any, Any], Any]] = None
    delete_prompt: Optional[Callable[[Any], str]] = None
    # Le « + » de la section. Une famille sait se créer elle-même (`add`), ou
    # délègue à l'écran (`add_tooltip` seul -> signal `add_requested`) quand
    # naître demande plus que le projet — importer un PNG, par exemple.
    # Ni l'un ni l'autre : pas de bouton.
    add: Optional[Callable[[Any], Any]] = None
    add_tooltip: str = ""
    # Entrées de menu propres à la famille : [(libellé, (projet, asset) -> None)]
    actions: tuple = ()

    # Glisser-déposer vers le canvas : (type MIME, asset -> charge utile texte).
    # Une famille sans `mime` n'est pas glissable.
    mime: Optional[tuple] = None

    # projet -> dossier RÉEL de la famille sur le disque, pour le bouton
    # « Open in file manager » (standardisé, cf. widgets.FinderSection). Une
    # famille sans `dir_of` n'affiche pas le bouton — cf. `dir_of()` ci-dessous.
    dir_of: Optional[Callable[[Any], Any]] = None

    # Keep these after the original fields: positional plugin constructors
    # retain their argument order. Empty keys preserve plugin-provided text.
    label_key: str = ""
    add_tooltip_key: str = ""
    add_tip_key: str = ""
    empty_text_key: str = ""
    # L'état initial est une propriété de la famille, non du finder qui la
    # montre : une source encombrante peut démarrer repliée partout.
    section_expanded: bool = True


# ──────────────────────────────────────────────────────────────────
#  Constructeurs d'arbres — les deux sources de vérité qui existent
# ──────────────────────────────────────────────────────────────────

def store_nodes(attr: str,
                group_by: Optional[Callable[[Any], str]] = None,
                where: Optional[Callable[[Any], bool]] = None,
                collapse_singletons: bool = False,
                ) -> Callable[[Any], list[AssetNode]]:
    """Arbre d'une famille adossée à un `ResourceStore` (`project.<attr>`).

    Lit la collection EN MÉMOIRE, qui est la source de vérité (cf. en-tête).
    `ResourceStore` étant plat, l'arbre n'a aujourd'hui qu'un seul niveau —
    sauf si `group_by` donne un axe de regroupement déjà porté par le modèle
    (le `kind` d'un fond : scene / ui / animated).

    `where` restreint à une partie du store, pour les écrans qui donnent à
    chaque sous-famille sa propre section — le Background Editor a un bouton
    d'import par `kind`, ce qu'une section unique ne saurait pas offrir.

    `collapse_singletons` remonte au premier niveau un groupe qui n'a qu'un
    membre. Réservé aux regroupements DEVINÉS (les sprites se rangent par
    préfixe de nom) : un dossier pour un seul asset y est du bruit, alors qu'un
    vrai dossier — celui que l'utilisateur a créé — existe même vide.

    Le jour où `ResourceStore` saura les sous-dossiers, c'est ICI que l'arbre
    prendra sa profondeur ; le panneau, lui, sait déjà l'afficher."""
    def build(project) -> list[AssetNode]:
        items = list(getattr(project, attr, []) or [])
        if where is not None:
            items = [it for it in items if where(it)]
        if group_by is None:
            return [AssetNode(name=it.name, obj=it) for it in items]
        folders: dict[str, AssetNode] = {}
        roots: list[AssetNode] = []
        for it in items:
            group = group_by(it) or ""
            leaf = AssetNode(name=it.name, obj=it)
            if not group:
                roots.append(leaf)
                continue
            folder = folders.get(group)
            if folder is None:
                folder = folders[group] = AssetNode(name=group)
                roots.append(folder)
            folder.children.append(leaf)
        if collapse_singletons:
            roots = [n.children[0] if n.is_folder and len(n.children) == 1 else n
                     for n in roots]
        return roots
    return build


def dir_nodes(attr: str, suffixes: tuple[str, ...]
              ) -> Callable[[Any], list[AssetNode]]:
    """Arbre d'une famille dont la vérité est le DISQUE — les scripts.

    Parcourt `project.<attr>` récursivement : les dossiers deviennent des nœuds
    dossier, les fichiers dont l'extension figure dans `suffixes` des feuilles
    portant leur `Path`."""
    def walk(directory: Path) -> list[AssetNode]:
        try:
            entries = sorted(directory.iterdir(),
                             key=lambda p: (not p.is_dir(), p.name.lower()))
        except (OSError, PermissionError):
            return []
        out: list[AssetNode] = []
        for entry in entries:
            if entry.is_dir():
                out.append(AssetNode(name=entry.name, children=walk(entry)))
            elif entry.suffix in suffixes:
                out.append(AssetNode(name=entry.name, obj=entry))
        return out

    def build(project) -> list[AssetNode]:
        directory = getattr(project, attr, None)
        if not directory or not Path(directory).exists():
            return []
        return walk(Path(directory))
    return build


def resource_dir(attr: str) -> Callable[[Any], Optional[Path]]:
    """Dossier physique d'une famille, pour `AssetKind.dir_of` — même contrat
    que `store_nodes`/`dir_nodes` (un nom de propriété de `Project`), vers UN
    chemin plutôt qu'un arbre. `attr` est déjà la source nommée dans le
    `store_nodes`/`dir_nodes` de la même famille — jamais une copie."""
    def get(project) -> Optional[Path]:
        directory = getattr(project, attr, None)
        return Path(directory) if directory else None
    return get


# ──────────────────────────────────────────────────────────────────
#  L'arbre Qt d'une famille
# ──────────────────────────────────────────────────────────────────

class _KindTree(QTreeWidget):
    """L'arbre d'UNE famille. Ne connaît que son `AssetKind` et son panneau."""

    def __init__(self, panel: "AssetFinder", kind: AssetKind):
        super().__init__()
        self._panel = panel
        self._kind = kind
        # Asset ACTIF (chargé dans le canvas) — distinct de la sélection, peint
        # en barre gauche par la grammaire de sélection partagée
        # (`RowSelectionDelegate`, via `active_item()`). Retenu par IDENTITÉ
        # (comme la sélection restaurée) ; None si la famille n'a pas d'actif.
        self._active_obj = None
        self.setItemDelegate(RowSelectionDelegate(self))
        self.setHeaderHidden(True)
        # Deux colonnes : le nom (qui s'étire et s'édite) et, ferré à droite,
        # le suffixe informatif — « 16 » pour une palette, « 12 × 3 » pour une table.
        self.setColumnCount(2)
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.setIndentation(14)
        self.setUniformRowHeights(True)
        self.setIconSize(QSize(14, 14))
        self.setStyleSheet(QSS.tree_widget)
        # Sélection multiple pour agir sur un LOT (supprimer plusieurs assets
        # d'un geste). `ExtendedSelection` est le mode NATIF de Qt pour Maj/Ctrl
        # (cf. QAbstractItemView::SelectionMode) : clic simple = remplace, Maj-clic
        # = plage depuis l'item courant, Ctrl-clic = bascule cet item sans toucher
        # au reste. On ne réécrit PAS ce geste à la main — Qt le fait déjà
        # correctement ; notre seul travail est de décider QUAND réagir à la
        # sélection qui en résulte (cf. `_on_selection_set_changed`).
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Renommage en place, jamais de dialogue modal : clic sur un item déjà
        # sélectionné, ou F2. Même geste que partout ailleurs dans l'éditeur.
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        # Hauteur RÉGLÉE SUR LE CONTENU (cf. `_fit`), jamais extensible : c'est
        # ce qui ferre les sections en haut du panneau. Une liste extensible se
        # partagerait la colonne avec ses voisines, et une section courte
        # flotterait au milieu du vide qu'on lui a donné.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._configure_dnd()
        self.itemSelectionChanged.connect(self._on_selection_set_changed)
        self.itemDoubleClicked.connect(self._on_double_clicked)
        self.customContextMenuRequested.connect(self._on_ctx_menu)
        self.itemChanged.connect(self._on_item_changed)
        self.model().rowsInserted.connect(self._fit)
        self.model().rowsRemoved.connect(self._fit)
        self.itemExpanded.connect(self._fit)
        self.itemCollapsed.connect(self._fit)
        self.itemExpanded.connect(lambda it: self._refresh_folder_icon(it, True))
        self.itemCollapsed.connect(lambda it: self._refresh_folder_icon(it, False))

    def _refresh_folder_icon(self, item: QTreeWidgetItem, expanded: bool) -> None:
        """Alterne plein/filet au dépli — seuls les dossiers portent `_ROLE_OBJ`
        à None (les items d'asset le renseignent toujours, cf. `_fill`).
        `setIcon` émet `itemChanged` comme un renommage utilisateur : sans
        `blockSignals`, `_on_item_changed` relirait ce non-événement comme un
        renommage de dossier et repeuplerait l'arbre en boucle."""
        if item.data(0, _ROLE_OBJ) is None:
            self.blockSignals(True)
            item.setIcon(0, folder_icon(expanded, COLOR_FOLDER))
            self.blockSignals(False)

    def _configure_dnd(self):
        """Glisser vers le canvas si la famille déclare un `mime` ; sinon aucun
        glisser-déposer Qt. Le rangement en dossiers d'auteur NE passe PAS par le
        drag Qt : dans un `QTreeWidget`, activer le drag (InternalMove/acceptDrops)
        désactive la sélection au rectangle — la multi-sélection prime. Les dossiers
        se pilotent au menu contextuel (« Déplacer vers », « Nouveau dossier »)."""
        if self._kind.mime is not None:
            self.setDragEnabled(True)
            self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        else:
            self.setDragEnabled(False)
            self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)

    # ── Peuplement ────────────────────────────────────────────────

    def populate(self, project):
        # La sélection/l'item courant visent des `QTreeWidgetItem` que `clear()`
        # va détruire : on retient les ASSETS (identité stable), pas les items,
        # pour les re-sélectionner une fois l'arbre reconstruit. Sans ça, tout
        # repeuplement (un renommage, un ajout, l'activation d'une scène...)
        # effaçait la surbrillance — rien ne disait plus où on en était.
        prev_selected = [it.data(0, _ROLE_OBJ) for it in self.selectedItems()]
        cur = self.currentItem()
        prev_current = cur.data(0, _ROLE_OBJ) if cur else None
        self.blockSignals(True)
        self.clear()
        if project is not None:
            nodes = self._kind.nodes(project)
            scheme = self._panel.folder_scheme(self._kind.label)
            if scheme is not None:
                nodes = folded_nodes(nodes, scheme)
            self._fill(self.invisibleRootItem(), nodes)
            if prev_selected:
                self._restore_selection(prev_selected, prev_current)
        # `clear()` a détruit l'ancienne ligne active : on la retrouve par
        # identité sur l'arbre reconstruit (le liseré survit à un repeuplement,
        # comme la sélection juste au-dessus).
        self._refresh_active_item()
        self.blockSignals(False)
        self._fit()
        return self.topLevelItemCount() > 0

    # ── Asset actif (liseré, distinct de la sélection) ────────────

    def set_active(self, obj) -> None:
        """Marque `obj` comme l'asset ACTIF de la famille (liseré gauche), ou
        efface le marqueur si `obj` est None. N'affecte NI la sélection NI ce que
        l'écran édite — c'est un pur repère visuel de « ce qui est ouvert »."""
        self._active_obj = obj
        self._refresh_active_item()
        self.viewport().update()

    def _refresh_active_item(self) -> None:
        self._active_item = (self._locate(self._active_obj)
                             if self._active_obj is not None else None)

    def active_item(self) -> Optional[QTreeWidgetItem]:
        it = getattr(self, "_active_item", None)
        return it if it is not None and not sip.isdeleted(it) else None

    def _restore_selection(self, prev_objs: list, prev_current) -> None:
        """Ré-applique une sélection par IDENTITÉ après un repeuplement. Reste
        muette (appelée sous `blockSignals`) : un repeuplement ne doit pas
        réémettre comme si l'utilisateur venait de re-cliquer."""
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        current_item = None
        while stack:
            it = stack.pop()
            obj = it.data(0, _ROLE_OBJ)
            if obj is not None:
                if any(self._same(obj, o) for o in prev_objs):
                    it.setSelected(True)
                if prev_current is not None and self._same(obj, prev_current):
                    current_item = it
            stack.extend(it.child(k) for k in range(it.childCount()))
        if current_item is not None:
            # `setCurrentItem(item)` seul vaut `ClearAndSelect` côté Qt — ça
            # effacerait la sélection qu'on vient tout juste de poser (même
            # piège que le Ctrl-clic, cf. `_on_selection_set_changed`).
            # `NoUpdate` ne fait bouger que l'item courant.
            self.setCurrentItem(current_item, 0, QItemSelectionModel.SelectionFlag.NoUpdate)

    def _fill(self, parent, nodes: list[AssetNode]):
        editable_folders = self._panel.folder_scheme(self._kind.label) is not None
        for node in nodes:
            item = QTreeWidgetItem(parent)
            item.setFont(0, ui_font(T.LG))
            if node.is_folder:
                item.setIcon(0, folder_icon(True, node.color or COLOR_FOLDER))
                item.setText(0, node.name)
                item.setForeground(0, QColor(C.TEXT_DIM))
                # Un dossier d'AUTEUR (folder_id) est renommable et accueille un
                # drop ; un dossier deviné n'a ni l'un ni l'autre.
                if node.folder_id is not None:
                    item.setData(0, _ROLE_FOLDER, node.folder_id)
                    if editable_folders:
                        item.setFlags((item.flags() | Qt.ItemFlag.ItemIsEditable
                                       | Qt.ItemFlag.ItemIsDropEnabled)
                                      & ~Qt.ItemFlag.ItemIsDragEnabled)
                self._fill(item, node.children)
                item.setExpanded(True)
            else:
                item.setIcon(0, self._kind.icon_of(node.obj) if self._kind.icon_of
                                else _ico(self._kind.icon, self._kind.color))
                item.setData(0, _ROLE_OBJ, node.obj)
                item.setForeground(0, QColor(C.TEXT_NORM))
                self._set_label(item, node.obj)
                if self._kind.rename is not None:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                if editable_folders:
                    # Un asset se glisse (dans un dossier) mais n'accueille aucun
                    # drop : on ne s'imbrique pas SOUS un asset.
                    item.setFlags((item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
                                  & ~Qt.ItemFlag.ItemIsDropEnabled)
                if self._kind.tooltip_of is not None:
                    item.setToolTip(0, self._kind.tooltip_of(node.obj))
                if node.children:
                    self._fill(item, node.children)

    def _set_label(self, item: QTreeWidgetItem, obj):
        """Nom + suffixe informatif. Le suffixe n'est QUE de l'affichage : le nom
        nu vit dans l'objet, et c'est lui que l'édition en place reprend."""
        name = self._name_of(obj)
        suffix = self._kind.suffix_of(obj) if self._kind.suffix_of else ""
        item.setText(0, name)
        item.setText(1, suffix)
        if suffix:
            font = ui_font(T.SM)
            font.setItalic(True)
            item.setFont(1, font)
            item.setForeground(1, QColor(C.TEXT_DIM))
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    @staticmethod
    def _name_of(obj) -> str:
        return obj.name if isinstance(obj, Path) else getattr(obj, "name", str(obj))

    def _fit(self):
        rows, stack = 0, [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            it = stack.pop()
            rows += 1
            if it.isExpanded():
                stack.extend(it.child(n) for n in range(it.childCount()))
        # S.ROW = hauteur d'une ligne dans QSS.tree_widget : les deux doivent
        # rester d'accord, sinon l'arbre se coupe ou traîne du vide.
        self.setFixedHeight(max(rows * S.ROW, 4))

    # ── Sélection ─────────────────────────────────────────────────

    def _on_selection_set_changed(self):
        """Sélection STABILISÉE de l'arbre. C'est le SEUL point où l'on décide
        d'activer, et à dessein : Qt émet ce signal APRÈS avoir posé la plage d'un
        Shift/Ctrl-clic, alors que `currentItemChanged` est émis AVANT — la
        sélection y est encore celle d'avant le geste, si bien qu'on ne peut pas
        y distinguer un clic simple d'un lot.

        Un asset UNIQUE s'active — il devient ce que l'écran édite, et pour une
        scène cela la CHARGE. Un LOT ne sert qu'aux opérations du menu contextuel
        (suppression groupée) : on le publie pour la sélection croisée, mais on
        ne l'active pas.

        L'émission proprement dite est DIFFÉRÉE (`QTimer.singleShot(0, ...)`) :
        activer une scène rafraîchit ce panneau (`window._on_scene_selected` ->
        `assets_finder_panel.refresh()` -> `populate()`), qui reconstruit CET
        arbre — CELUI-LÀ MÊME qui est en train de traiter le clic qui a causé
        cette activation. Le faire dans le même appel, c'est reconstruire
        l'arbre PENDANT que Qt peint/termine l'évènement souris dessus : c'est ce
        qui produisait les « QPainter: Unbalanced save/restore » observés en test
        manuel. Un tour de boucle d'attente suffit à laisser le clic se terminer
        avant que le rebuild n'ait lieu — même parade que `select_obj`/`edit_obj`
        plus bas pour la même classe de réentrance."""
        objs = self._selected_objs()
        QTimer.singleShot(0, lambda k=self._kind.label, os=objs: self._emit_selection(k, os))

    def _emit_selection(self, kind_label: str, objs: list) -> None:
        # L'ENSEMBLE, pour la sélection croisée d'un écran (project viewer ↔ graphe).
        self._panel.selection_changed.emit(kind_label, objs)
        if not objs:
            return
        # Une seule section surlignée dans TOUT le panneau : deux sections
        # surlignées à la fois, et le surlignage ne dirait plus ce que l'écran
        # montre. Vrai aussi pour un lot.
        self._panel.clear_selection(except_label=kind_label)
        if len(objs) == 1:
            self._panel.selected.emit(kind_label, objs[0])

    def highlight_objs(self, objs, fold_to_folder: bool = False) -> None:
        """Sélectionne ces assets SANS rien activer ni réémettre — la sélection
        vient d'ailleurs (l'autre vue du même écran) ; le critère est l'identité
        de l'asset.

        `fold_to_folder` : si un asset est CACHÉ sous un dossier replié, on
        surligne À SA PLACE le dossier replié visible le plus haut. Sans ça,
        sélectionner dans le graphe une scène rangée dans un groupe replié côté
        project viewer ne donnerait aucun retour — la ligne de la scène n'y est
        pas dépliée. On garde ainsi toujours un repère dans le panneau."""
        wanted = {id(o) for o in objs}
        targets: list[QTreeWidgetItem] = []
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            it = stack.pop()
            o = it.data(0, _ROLE_OBJ)
            if o is not None and id(o) in wanted:
                targets.append(self._visible_representative(it) if fold_to_folder else it)
            stack.extend(it.child(k) for k in range(it.childCount()))
        # Muet (comme highlight_matching) : un écho de sélection ne doit pas
        # repartir en boucle vers la vue qui l'a émis.
        self.blockSignals(True)
        self.clearSelection()
        for it in targets:
            it.setSelected(True)
        self.blockSignals(False)

    @staticmethod
    def _visible_representative(item: QTreeWidgetItem) -> QTreeWidgetItem:
        """L'item lui-même s'il est visible, sinon le dossier replié VISIBLE le
        plus haut au-dessus de lui. On remonte jusqu'à la racine en retenant le
        dernier ancêtre replié croisé : c'est le plus proche de la racine, donc
        le seul dont tous les ancêtres sont dépliés — celui qu'on voit."""
        rep = item
        parent = item.parent()
        while parent is not None:
            if not parent.isExpanded():
                rep = parent
            parent = parent.parent()
        return rep

    def _on_double_clicked(self, item: QTreeWidgetItem, _col: int):
        obj = item.data(0, _ROLE_OBJ)
        if obj is not None:
            self._panel.activated.emit(self._kind.label, obj)

    # ── Glisser vers le canvas ────────────────────────────────────

    def startDrag(self, _actions):
        """Le finder ne sait pas ce qu'on fait d'un asset lâché sur un canvas ;
        il ne fait qu'annoncer lequel, dans le type MIME que la famille déclare.
        C'est le canvas qui décide (instancier un prefab, poser un fond animé…)."""
        item = self.currentItem()
        obj = item.data(0, _ROLE_OBJ) if item else None
        if obj is None or self._kind.mime is None:
            return
        mime_type, payload = self._kind.mime
        project = self._panel.project
        data = QMimeData()
        data.setData(mime_type, QByteArray(str(payload(project, obj)).encode()))
        drag = QDrag(self)
        drag.setMimeData(data)
        drag.exec(Qt.DropAction.MoveAction)

    # ── Rangement en dossiers d'auteur (menu contextuel) ──────────

    def _folder_menu(self, scheme, folder_id, pos):
        """Menu d'un dossier d'auteur (ou de la zone vide) : nouveau (sous-)dossier,
        et — sur un dossier — renommer ou supprimer."""
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        menu.setFont(QFont(T.UI, T.MD))
        new_label = (label('assetfind.new_subfolder') if folder_id
                     else label('assetfind.new_folder'))
        menu.addAction(new_label).triggered.connect(
            lambda _=False, p=folder_id: self._create_folder(scheme, p))
        if folder_id is not None:
            menu.addSeparator()
            menu.addAction(label('assetfind.rename')).triggered.connect(
                lambda _=False, f=folder_id: self._edit_folder(f))
            menu.addSeparator()
            menu.addAction(label('scttree.delete_folder')).triggered.connect(
                lambda _=False, f=folder_id: self._delete_folder(scheme, f))
        menu.exec(self.viewport().mapToGlobal(pos))

    def _create_folder(self, scheme, parent_id):
        folder = scheme.create(label('assetfind.folder_default_name'), parent_id)
        self._panel.refresh()
        self._panel.folders_changed.emit()
        if folder is not None:
            self._edit_folder(folder.id)

    def _delete_folder(self, scheme, folder_id):
        scheme.delete(folder_id)
        self._panel.refresh()
        self._panel.folders_changed.emit()

    def _group(self, objs):
        """« Grouper » : range le lot (ou l'item seul) dans un nouveau dossier
        auto-nommé, puis l'ouvre en renommage. Le geste opère sur la sélection
        courante — un seul point d'entrée pour le simple et le multiple."""
        scheme = self._panel.folder_scheme(self._kind.label)
        if scheme is None or scheme.group is None or not objs:
            return
        folder = scheme.group(objs, None)
        self._panel.refresh()
        self._panel.folders_changed.emit()
        if folder is not None:
            self._edit_folder(folder.id)

    def _locate_folder(self, folder_id) -> Optional[QTreeWidgetItem]:
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            it = stack.pop()
            if it.data(0, _ROLE_FOLDER) == folder_id:
                return it
            stack.extend(it.child(n) for n in range(it.childCount()))
        return None

    def _edit_folder(self, folder_id):
        def go():
            it = self._locate_folder(folder_id)
            if it is not None:
                self.setCurrentItem(it)
                self.editItem(it, 0)
        QTimer.singleShot(0, go)

    @staticmethod
    def _same(a, b) -> bool:
        """Identité pour un asset en mémoire — deux `Resource` de mêmes champs
        restent deux assets distincts. Égalité pour un `Path`, qui est reconstruit
        à chaque parcours du disque et ne survivrait pas à un test d'identité."""
        return a is b or (isinstance(a, Path) and isinstance(b, Path) and a == b)

    def _locate(self, obj) -> Optional[QTreeWidgetItem]:
        """Retrouve la ligne d'`obj` par IDENTITÉ, sans y toucher — pure lecture."""
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            it = stack.pop()
            if self._same(it.data(0, _ROLE_OBJ), obj):
                return it
            stack.extend(it.child(n) for n in range(it.childCount()))
        return None

    def select_obj(self, obj) -> bool:
        it = self._locate(obj)
        if it is None:
            return False
        self.setCurrentItem(it)
        # `setCurrentItem` sélectionne l'item : le signal de sélection stabilisée
        # (`itemSelectionChanged`) remonte SYNCHRONE jusqu'à
        # `window._on_scene_selected`, qui rafraîchit ce panneau
        # (`assets_finder_panel.refresh()`) avant de rendre la main — `it` est
        # alors déjà détruit. Même mise en garde que `_on_item_changed` plus bas.
        if not sip.isdeleted(it):
            self.scrollToItem(it)
        return True

    def edit_obj(self, obj):
        """Ouvre l'édition en place sur `obj` — appelé après une création, pour
        que l'asset naisse nommé et renommable d'un geste, sans pop-up."""
        def go():
            if not self.select_obj(obj):
                return
            # `select_obj` a pu déclencher le rebuild réentrant décrit
            # au-dessus : `currentItem()` n'y survit pas forcément — on
            # retrouve la ligne à froid, sur l'arbre tel qu'il est retombé.
            it = self._locate(obj)
            if it is not None:
                self.editItem(it, 0)
        QTimer.singleShot(0, go)

    # ── Renommage en place ────────────────────────────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, col: int):
        if col != 0:            # le suffixe n'est qu'affichage, jamais une édition
            return
        obj = item.data(0, _ROLE_OBJ)
        folder_id = item.data(0, _ROLE_FOLDER)
        scheme = self._panel.folder_scheme(self._kind.label)
        if obj is None:
            # Renommage d'un dossier d'auteur (le seul item sans obj éditable).
            if folder_id is not None and scheme is not None:
                typed = item.text(0).strip()
                if typed:
                    scheme.rename(folder_id, typed)
                self._panel.refresh()
                self._panel.folders_changed.emit()
            return
        if self._kind.rename is None:
            return
        typed = item.text(0).strip()
        if not typed or typed == self._name_of(obj):
            self.blockSignals(True)
            self._set_label(item, obj)          # remet nom + suffixe
            self.blockSignals(False)
            return
        project = self._panel.project
        if project is None:
            return
        # Un renommage réécrit les références et peut faire repeupler l'arbre
        # DANS l'appel (project.events "renamed" -> "project_tree_changed" est
        # synchrone) : `item` est alors déjà détruit. On ne le retouche donc pas
        # après — on repeuple et on re-cible l'objet par IDENTITÉ, qui survit.
        applied = self._kind.rename(project, obj, typed)
        self._panel.refresh()
        if applied:
            self.select_obj(obj)

    # ── Menu contextuel ───────────────────────────────────────────

    def _selected_objs(self) -> list:
        """Les assets sélectionnés — les dossiers (obj None) sont ignorés : un
        lot n'opère que sur de vrais assets."""
        out = []
        for it in self.selectedItems():
            obj = it.data(0, _ROLE_OBJ)
            if obj is not None:
                out.append(obj)
        return out

    def _on_ctx_menu(self, pos):
        item = self.itemAt(pos)
        scheme = self._panel.folder_scheme(self._kind.label)
        if scheme is not None:
            # Zone vide ou dossier d'auteur : menu de dossiers (créer/renommer…).
            folder_id = item.data(0, _ROLE_FOLDER) if item else None
            if item is None or folder_id is not None:
                self._folder_menu(scheme, folder_id, pos)
                return
        if not item or item.data(0, _ROLE_OBJ) is None:
            return                      # rien, ou un dossier deviné : rien à proposer
        # Clic HORS sélection : la sélection retombe sur cette seule ligne, comme
        # dans un gestionnaire de fichiers. Clic DEDANS : on garde le lot, pour
        # agir dessus. `setCurrentItem` en mode Extended remplace la sélection.
        if item not in self.selectedItems():
            self.setCurrentItem(item)
        # Le lot ne sert qu'à décider simple/multiple ; la cible du menu simple
        # est l'item CLIQUÉ (obj garanti non nul ici), jamais `objs[0]` — un
        # dossier sélectionné (obj None) rendrait `objs` vide et planterait.
        objs = self._selected_objs()
        if len(objs) > 1 and item.data(0, _ROLE_OBJ) in objs:
            self._multi_menu(objs, pos)
        else:
            self._single_menu(item.data(0, _ROLE_OBJ), pos)

    def _single_menu(self, obj, pos):
        kind, project = self._kind, self._panel.project
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        menu.setFont(QFont(T.UI, T.MD))

        # Actions de la famille (les mêmes partout), puis celles que l'écran a
        # ajoutées — « Voir les instances » n'a de sens que là où un inspecteur
        # peut les montrer.
        for lbl_key, fn in kind.actions:
            menu.addAction(label(lbl_key)).triggered.connect(
                lambda _=False, f=fn, o=obj: f(project, o))
        for lbl, fn in self._panel.extra_actions(kind.label):
            menu.addAction(lbl).triggered.connect(
                lambda _=False, f=fn, o=obj: f(o))

        if kind.rename is not None:
            if not menu.isEmpty():
                menu.addSeparator()
            act = menu.addAction(label('assetfind.rename'))
            act.setShortcut("F2")       # affiché ; géré par EditKeyPressed
            # Pas `item` capturé : le menu ouvert laisse tourner la boucle
            # d'évènements, un refresh de l'arbre peut le détruire avant le
            # clic. On retrouve la ligne par identité au moment de l'action.
            act.triggered.connect(lambda _=False, o=obj: self.edit_obj(o))

        scheme = self._panel.folder_scheme(kind.label)
        if scheme is not None:
            if scheme.group is not None:
                if not menu.isEmpty():
                    menu.addSeparator()
                menu.addAction(label('assetfind.group')).triggered.connect(
                    lambda _=False, o=obj: self._group([o]))
            self._add_move_to_folder(menu, scheme, obj)

        if kind.delete is not None:
            menu.addSeparator()
            menu.addAction(label('common.delete')).triggered.connect(
                lambda _=False, o=obj: self._delete(o))

        if not menu.isEmpty():
            menu.exec(self.viewport().mapToGlobal(pos))

    def _add_move_to_folder(self, menu, scheme, obj):
        """Rangement sans glisser : « Déplacer vers » chaque dossier, et un retour
        à la racine si l'asset est déjà rangé."""
        current = scheme.folder_of(obj)
        folders = scheme.folders()
        if not menu.isEmpty():
            menu.addSeparator()
        sub = menu.addMenu(label('assetfind.move_to_folder'))
        sub.setFont(QFont(T.UI, T.MD))
        sub.setEnabled(bool(folders))
        for folder in folders:
            act = sub.addAction(folder.name)
            act.setEnabled(folder.id != current)
            act.triggered.connect(
                lambda _=False, fid=folder.id, o=obj: self._move_to_folder(scheme, o, fid))
        if current is not None:
            menu.addAction(label('assetfind.remove_from_folder')).triggered.connect(
                lambda _=False, o=obj: self._move_to_folder(scheme, o, None))

    def _move_to_folder(self, scheme, obj, folder_id):
        scheme.move(obj, folder_id)
        self._panel.refresh()
        self._panel.folders_changed.emit()

    def _move_many_to_folder(self, scheme, objs, folder_id):
        for obj in objs:
            scheme.move(obj, folder_id)
        self._panel.refresh()
        self._panel.folders_changed.emit()

    def _multi_menu(self, objs, pos):
        """Menu d'un LOT : les actions qui ont un sens sur plusieurs assets à la
        fois. Le renommage reste mono-ligne (édition en place) et les actions par
        asset ne sont pas pensées pour le lot ; restent grouper, ranger et
        supprimer — ce que la multi-sélection sert d'abord."""
        kind = self._kind
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        menu.setFont(QFont(T.UI, T.MD))
        scheme = self._panel.folder_scheme(kind.label)
        if scheme is not None:
            if scheme.group is not None:
                menu.addAction(label('assetfind.group')).triggered.connect(
                    lambda _=False, os=list(objs): self._group(os))
            self._add_move_many_to_folder(menu, scheme, objs)
        if kind.delete is not None:
            if not menu.isEmpty():
                menu.addSeparator()
            menu.addAction(label('assetfind.delete_selection', n=len(objs))).triggered.connect(
                lambda _=False, os=list(objs): self._delete_many(os))
        if not menu.isEmpty():
            menu.exec(self.viewport().mapToGlobal(pos))

    def _add_move_many_to_folder(self, menu, scheme, objs):
        """« Déplacer vers le dossier » pour un lot : chaque dossier existant, et
        un retour à la racine — le lot entier suit la cible choisie."""
        if not menu.isEmpty():
            menu.addSeparator()
        sub = menu.addMenu(label('assetfind.move_to_folder'))
        sub.setFont(QFont(T.UI, T.MD))
        folders = scheme.folders()
        sub.setEnabled(bool(folders))
        for folder in folders:
            sub.addAction(folder.name).triggered.connect(
                lambda _=False, fid=folder.id, os=list(objs): self._move_many_to_folder(scheme, os, fid))
        menu.addAction(label('assetfind.remove_from_folder')).triggered.connect(
            lambda _=False, os=list(objs): self._move_many_to_folder(scheme, os, None))

    def _delete(self, obj):
        kind, project = self._kind, self._panel.project
        if project is None:
            return
        name = self._name_of(obj)
        prompt = (kind.delete_prompt(obj) if kind.delete_prompt
                  else label('assetfind.delete_name_ctrl_z_to_undo', name=name))
        if QMessageBox.question(
            self, label('common.delete'), prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        get_history().push(RefreshAfterCmd(kind.delete(project, obj), self._panel.refresh))
        self._panel.refresh()
        self._panel.emptied.emit(kind.label)

    def _delete_many(self, objs):
        """Supprime un lot en UNE entrée d'historique (`MacroCmd`) : un seul
        Ctrl+Z ramène tout. Chaque famille bâtit sa propre commande — on ne fait
        que les grouper."""
        kind, project = self._kind, self._panel.project
        if project is None or not objs:
            return
        n = len(objs)
        if QMessageBox.question(
            self, label('common.delete'),
            label('assetfind.delete_confirm', n=n),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        cmds = [kind.delete(project, o) for o in objs]
        get_history().push(RefreshAfterCmd(
            MacroCmd(cmds, f"Delete {n} {kind.label.lower()}"), self._panel.refresh))
        self._panel.refresh()
        self._panel.emptied.emit(kind.label)


# ──────────────────────────────────────────────────────────────────
#  Le panneau
# ──────────────────────────────────────────────────────────────────

class AssetFinder(QWidget):
    """Colonne « finder » d'un écran : une section repliable par famille.

        finder = AssetFinder("Data finder", [DATA_TABLES])
        finder.load_project(project)
        finder.selected.connect(...)
    """

    selected      = pyqtSignal(str, object)   # (AssetKind.label, asset)
    activated     = pyqtSignal(str, object)   # double-clic
    emptied       = pyqtSignal(str)           # une suppression a eu lieu
    add_requested = pyqtSignal(str)           # « + » d'une famille qui délègue
    selection_changed = pyqtSignal(str, list)  # (label, assets sélectionnés) — sync
    folders_changed = pyqtSignal()            # un dossier a été créé/déplacé/supprimé

    def __init__(self, title: str, kinds: list[AssetKind],
                 min_width: int = 220, max_width: int = 420, parent=None):
        super().__init__(parent)
        self._project = None
        self._kinds = list(kinds)
        self._trees: dict[str, _KindTree] = {}
        self._sections: dict[str, QWidget] = {}
        self._empties: dict[str, QLabel] = {}
        self._extra_actions: dict[str, list] = {}
        # Rangement en dossiers d'auteur, par famille — injecté au chargement
        # projet (le store n'existe pas avant). Une famille absente n'a pas de
        # dossiers éditables : l'opt-in laisse les autres inchangées.
        self._folder_schemes: dict[str, FolderScheme] = {}
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self.setMinimumWidth(min_width)
        self.setMaximumWidth(max_width)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._title = W.finder_bar(title)
        self._title_label = self._title.findChild(QLabel)
        root.addWidget(self._title)

        # Toutes les sections dans UNE zone défilante, calées en haut. Chacune
        # vaut sa hauteur de contenu ; le ressort de queue prend le reste, sinon
        # QVBoxLayout répartirait le rab entre les sections et une liste courte
        # flotterait au milieu du vide. Une liste plus haute que la colonne fait
        # défiler tout le panneau — et non elle seule, ce qui remettrait un
        # ascenseur par famille.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background:{C.BG_BASE}; border:none;")
        container = QWidget()
        container.setStyleSheet(f"background:{C.BG_BASE};")
        self._column = QVBoxLayout(container)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(0)

        for kind in self._kinds:
            # Titre en tons de thème : les finders n'ont plus de code couleur
            # par famille, la distinction se fait à la forme de l'icône.
            section = FinderSection(label(kind.label_key) if kind.label_key else kind.label)
            section.set_expanded(kind.section_expanded)
            tree = _KindTree(self, kind)
            self._trees[kind.label] = tree
            self._sections[kind.label] = section
            section.set_widget(self._wrap(tree, kind))
            if kind.add is None and not (kind.add_tooltip or kind.add_tooltip_key):
                section.set_add_visible(False)
            else:
                section.set_add_tooltip(
                    tooltip(title=label(kind.add_tooltip_key),
                            body=label(kind.add_tip_key) if kind.add_tip_key else "")
                    if kind.add_tooltip_key
                    else kind.add_tooltip or label('assetfind.add_an_item'))
                section.add_clicked.connect(lambda k=kind: self._add(k))
            if kind.dir_of is not None:
                section.set_reveal_visible(True)
                section.reveal_clicked.connect(lambda k=kind: self._reveal(k))
            self._column.addWidget(section)

        self._column.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

    def show_only(self, labels):
        """N'affiche que ces familles — le finder suit ce qu'on édite.

        Une banque d'effets n'a rien à faire à côté d'un graphe musical : elle
        ne s'y glisse pas et ne s'y référence pas. Masquer plutôt que griser,
        comme partout ailleurs : on ne propose pas une action impossible.
        `None` remet tout.
        """
        for label, section in self._sections.items():
            section.setVisible(labels is None or label in labels)

    def set_title(self, title: str) -> None:
        """Nomme le contexte actuellement parcouru par ce finder."""
        if self._title_label is not None:
            self._title_label.setText(title)

    def add_section(self, section: QWidget):
        """Ajoute une section À LA SUITE des familles, dans la même colonne
        défilante — pour ce qu'un écran affiche sous ses assets sans que ce
        soient des assets : les états d'animation d'un sprite, les constantes
        et globales du Script Editor. Sans quoi ces sections vivraient hors de
        la zone défilante et flotteraient en bas du panneau."""
        self._column.insertWidget(self._column.count() - 1, section)

    def _wrap(self, tree: _KindTree, kind: AssetKind) -> QWidget:
        """Liste + message d'état vide, l'un ou l'autre. Une famille sans
        `empty_text` n'affiche rien : une liste vide se voit toute seule."""
        if not (kind.empty_text or kind.empty_text_key):
            return tree
        box = QWidget()
        box.setStyleSheet(f"background:{C.BG_BASE};")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        empty = QLabel(label(kind.empty_text_key) if kind.empty_text_key else kind.empty_text)
        empty.setFont(QFont(T.UI, T.SM))
        empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:{S.CONTENT}px;")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setWordWrap(True)
        lay.addWidget(tree)
        lay.addWidget(empty)
        self._empties[kind.label] = empty
        return box

    # ── Chargement ────────────────────────────────────────────────

    @property
    def project(self):
        return self._project

    def load_project(self, project):
        self._project = project
        self.refresh()

    def refresh(self):
        for label, tree in self._trees.items():
            filled = tree.populate(self._project)
            empty = self._empties.get(label)
            if empty is not None:
                tree.setVisible(filled)
                empty.setVisible(not filled)

    def activate_current(self):
        """Émet `activated` pour l'asset sélectionné dans l'arbre qui a le focus
        — de quoi câbler un raccourci (Espace = écouter, dans le Sound Mixer)
        sans que le composant ait à savoir ce qu'« activer » veut dire."""
        for label, tree in self._trees.items():
            if tree.hasFocus():
                item = tree.currentItem()
                obj = item.data(0, _ROLE_OBJ) if item else None
                if obj is not None:
                    self.activated.emit(label, obj)
                return

    def clear_selection(self, except_label: str = ""):
        """Désélectionne sans réémettre — quand un autre panneau prend la main
        sur le contexte de l'écran (le Text Editor bascule Police ↔ Texte), ou
        qu'une autre famille du même panneau vient d'être choisie."""
        for label, tree in self._trees.items():
            if label == except_label:
                continue
            tree.blockSignals(True)
            tree.clearSelection()
            tree.setCurrentItem(None)
            tree.blockSignals(False)

    # ── Sélection pilotée de l'extérieur ──────────────────────────

    def select(self, kind_label: str, obj) -> bool:
        """Sélectionne `obj` — navigation venue d'un autre écran ou d'un undo."""
        tree = self._trees.get(kind_label)
        return tree.select_obj(obj) if tree is not None else False

    def current(self, kind_label: str):
        tree = self._trees.get(kind_label)
        item = tree.currentItem() if tree is not None else None
        return item.data(0, _ROLE_OBJ) if item is not None else None

    def highlight_selection(self, kind_label: str, objs,
                            fold_to_folder: bool = False) -> None:
        """Surligne un lot d'assets sans l'activer ni réémettre — sélection venue
        d'une autre vue du même écran (project viewer ↔ graphe).

        `fold_to_folder` reporte le surlignage d'un asset caché sur son dossier
        replié (retour visuel garanti même groupe fermé, cf. `highlight_objs`)."""
        tree = self._trees.get(kind_label)
        if tree is not None:
            tree.highlight_objs(objs, fold_to_folder=fold_to_folder)

    def set_active(self, kind_label: str, obj) -> None:
        """Marque l'asset ACTIF d'une famille (liseré gauche), ou l'efface si
        `obj` est None. Distinct de la sélection : dit « ce qui est ouvert dans
        le canvas », pas « ce que l'inspecteur montre » (cf. la règle
        active/sélectionnée, project_ui_conventions)."""
        tree = self._trees.get(kind_label)
        if tree is not None:
            tree.set_active(obj)

    def begin_rename(self, kind_label: str, obj):
        """Ouvre l'édition en place sur `obj` — après une création faite ailleurs
        que par le « + » du finder (le menu Fichier, un import)."""
        tree = self._trees.get(kind_label)
        if tree is not None:
            tree.edit_obj(obj)

    def begin_rename_folder(self, kind_label: str, folder_id: str):
        """Ouvre l'édition en place sur un dossier d'auteur fraîchement créé
        ailleurs que par le menu contextuel de l'arbre (« + » de l'en-tête,
        Ctrl+G) — même geste que la création d'un asset : il naît renommable."""
        tree = self._trees.get(kind_label)
        if tree is not None:
            tree._edit_folder(folder_id)

    def selected_objs(self, kind_label: str) -> list:
        """Le LOT sélectionné d'une famille (dossiers exclus) — pour un geste qui
        opère sur la sélection courante sans attendre un signal (Ctrl+G)."""
        tree = self._trees.get(kind_label)
        return tree._selected_objs() if tree is not None else []

    # ── Actions ajoutées par l'écran ──────────────────────────────

    def folder_scheme(self, kind_label: str) -> Optional["FolderScheme"]:
        return self._folder_schemes.get(kind_label)

    def set_folder_scheme(self, kind_label: str, scheme: Optional["FolderScheme"]) -> None:
        """Active (ou retire) le rangement en dossiers d'une famille. Rappelle la
        config DnD de l'arbre — le scheme arrive après sa construction — puis
        repeuple pour montrer les dossiers."""
        if scheme is None:
            self._folder_schemes.pop(kind_label, None)
        else:
            self._folder_schemes[kind_label] = scheme
        tree = self._trees.get(kind_label)
        if tree is not None:
            tree._configure_dnd()
            tree.populate(self._project)

    def add_action(self, kind_label: str, text: str, fn: Callable[[Any], None]):
        """Ajoute une entrée au menu contextuel d'une famille, DANS CET ÉCRAN.

        Ce qu'une famille sait faire d'elle-même vit dans `AssetKind.actions`
        (dupliquer une palette : vrai partout). Ce qui dépend de l'écran passe
        par ici — « Voir les instances » suppose un inspecteur pour les
        afficher, que seul le Scene Manager possède."""
        self._extra_actions.setdefault(kind_label, []).append((text, fn))

    def extra_actions(self, kind_label: str) -> list:
        return self._extra_actions.get(kind_label, [])

    # ── Ouvrir dans l'explorateur du système ─────────────────────────

    def _reveal(self, kind: AssetKind):
        if self._project is None:
            return
        reveal_in_file_manager(kind.dir_of(self._project))

    # ── Ajout ─────────────────────────────────────────────────────

    def _add(self, kind: AssetKind):
        if self._project is None:
            return
        if kind.add is None:
            self.add_requested.emit(kind.label)   # l'écran prend la main
            return
        obj = kind.add(self._project)
        self.refresh()
        if obj is not None:
            # Créé nommé d'office puis renommable en place : pas de dialogue qui
            # réclame un nom avant que la chose existe.
            self._trees[kind.label].edit_obj(obj)
