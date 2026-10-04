"""
history.py — Système undo/redo par pattern Command.

Usage :
    from core.history import get_history, SetFieldCmd, MoveActorCmd, ...
    get_history().push(SetFieldCmd(actor, "x", old, new, "Move X"))

Règles :
  - L'historique est par scène : clear() doit être appelé lors d'un
    changement de scène ou d'écran.
  - Les commandes sur un même (objet, champ) consécutives sont fusionnées
    (évite 100 entrées pour un drag de SpinBox).
  - Le stack redo est vidé dès qu'une nouvelle commande est poussée.
  - Max 200 commandes gardées (mémoire bornée).
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal

if TYPE_CHECKING:
    from core.models.scene import Actor, Scene

_MAX_HISTORY = 200


# ── Commande abstraite ─────────────────────────────────────────────

class Command(ABC):
    label: str = ""

    @abstractmethod
    def execute(self): ...

    @abstractmethod
    def undo(self): ...

    def merge(self, newer: "Command") -> bool:
        """Retourne True si `newer` peut être absorbée dans self (fusion)."""
        return False


class MacroCmd(Command):
    """Plusieurs commandes réunies en UNE entrée d'historique.

    Supprimer un LOT d'assets d'un geste doit s'annuler d'un seul Ctrl+Z, pas
    d'un par asset. Les commandes sont DÉJÀ construites : chaque famille sait
    bâtir sa propre suppression (`DeleteResourceCmd`, `DeleteFileCmd`), on ne
    fait que les grouper — aucune logique n'est redite ici.

    `execute` rejoue dans l'ordre, `undo` défait en ordre INVERSE : l'annulation
    d'un lot doit retrouver l'état d'avant exactement comme si les commandes
    s'étaient empilées une à une."""

    def __init__(self, cmds: list, label: str):
        self._cmds = list(cmds)
        self.label = label

    def execute(self):
        for cmd in self._cmds:
            cmd.execute()

    def undo(self):
        for cmd in reversed(self._cmds):
            cmd.undo()


# ── Commandes concrètes ────────────────────────────────────────────

class SetFieldCmd(Command):
    """
    Modification d'un champ d'un objet (actor ou component).
    Les commandes consécutives sur le même (obj, field) sont fusionnées.
    """

    def __init__(self, obj: Any, field: str, old_val: Any, new_val: Any,
                 label: str = "", persist_fn=None):
        self._obj = obj
        self._field = field
        self._old = old_val
        self._new = new_val
        self.label = label or f"Set {field}"
        self._persist = persist_fn   # callable() pour sauvegarder après apply

    def execute(self):
        setattr(self._obj, self._field, self._new)
        if self._persist:
            self._persist()

    def undo(self):
        setattr(self._obj, self._field, self._old)
        if self._persist:
            self._persist()

    def merge(self, newer: "Command") -> bool:
        if not isinstance(newer, SetFieldCmd):
            return False
        if self._obj is newer._obj and self._field == newer._field:
            self._new = newer._new
            self._persist = newer._persist
            return True
        return False


class SwapFieldCmd(Command):
    """
    Échange la valeur d'un même champ entre deux objets (ex: bg_slot de deux
    BackgroundLayer glissés l'un sur l'autre — réordonnance leur priorité
    d'affichage). L'échange est sa propre inverse : undo == execute.
    """

    def __init__(self, obj_a: Any, obj_b: Any, field: str,
                 label: str = "", persist_fn=None):
        self._a = obj_a
        self._b = obj_b
        self._field = field
        self.label = label or f"Swap {field}"
        self._persist = persist_fn

    def _swap(self):
        a_val = getattr(self._a, self._field)
        b_val = getattr(self._b, self._field)
        setattr(self._a, self._field, b_val)
        setattr(self._b, self._field, a_val)
        if self._persist:
            self._persist()

    def execute(self):
        self._swap()

    def undo(self):
        self._swap()


class MoveActorCmd(Command):
    """Déplacement d'un actor dans le canvas (drag souris)."""

    def __init__(self, actor: "Actor", old_x: int, old_y: int,
                 new_x: int, new_y: int, persist_fn=None):
        self._actor = actor
        self._old = (old_x, old_y)
        self._new = (new_x, new_y)
        self.label = f"Déplacer {actor.name}"
        self._persist = persist_fn

    def execute(self):
        self._actor.x, self._actor.y = self._new
        if self._persist:
            self._persist()

    def undo(self):
        self._actor.x, self._actor.y = self._old
        if self._persist:
            self._persist()

    def merge(self, newer: "Command") -> bool:
        if isinstance(newer, MoveActorCmd) and self._actor is newer._actor:
            self._new = newer._new
            self._persist = newer._persist
            return True
        return False


class SceneActorOrderCmd(Command):
    """Un changement de pile OAM : ordre de la scène et priorité d'un actor.

    La priorité et l'ordre départageant les OBJ à priorité égale forment un
    seul geste dans la projection Priorité du Scene Tree ; les séparer
    demanderait deux annulations pour un glisser-déposer.
    """

    def __init__(self, scene: "Scene", before: list, after: list,
                 priorities: tuple[list, list], label: str = "Reorder actors", persist_fn=None):
        self._scene = scene
        self._before = list(before)
        self._after = list(after)
        self._priorities = (list(priorities[0]), list(priorities[1]))
        self.label = label
        self._persist = persist_fn

    def _apply(self, order, priority):
        self._scene.actors[:] = order
        for actor, value in priority:
            actor.priority = value
        if self._persist:
            self._persist()

    def execute(self):
        self._apply(self._after, self._priorities[1])

    def undo(self):
        self._apply(self._before, self._priorities[0])


class MoveActorGroupCmd(Command):
    """Déplacement groupé : un actor et son SOUS-ARBRE (`Actor.parent`, ROADMAP
    v0.23) glissés ensemble dans le canvas. Bouger un parent translate ses
    descendants du même delta pour garder leurs positions monde relatives —
    cf. Actor.parent dans core/models/scene.py : l'auteur pose en coordonnées
    monde, ce déplacement groupé est ce qui les garde cohérentes dans
    l'éditeur tant que le canvas ne compose pas encore les transforms
    (rotation/scale du parent, elles, ne sont visibles qu'au runtime).

    Structurellement un `MoveActorCmd` par acteur du groupe, réunis en une
    seule entrée d'historique : annuler doit tout ramener en un geste."""

    def __init__(self, items: list, persist_fn=None):
        # items : [(actor, old_x, old_y, new_x, new_y), ...] — le premier est
        # l'actor réellement saisi par la souris.
        self._items = items
        self.label = f"Déplacer {items[0][0].name}" if items else "Déplacer"
        self._persist = persist_fn

    def execute(self):
        for actor, _ox, _oy, nx, ny in self._items:
            actor.x, actor.y = nx, ny
        if self._persist:
            self._persist()

    def undo(self):
        for actor, ox, oy, _nx, _ny in self._items:
            actor.x, actor.y = ox, oy
        if self._persist:
            self._persist()

    def merge(self, newer: "Command") -> bool:
        if not isinstance(newer, MoveActorGroupCmd):
            return False
        if [a for a, *_ in self._items] != [a for a, *_ in newer._items]:
            return False
        self._items = [
            (a, ox, oy, nx2, ny2)
            for (a, ox, oy, _nx, _ny), (_a2, _ox2, _oy2, nx2, ny2)
            in zip(self._items, newer._items)
        ]
        self._persist = newer._persist
        return True


class MoveCameraCmd(Command):
    """Déplacement du cadre d'une caméra dans le canvas (drag souris).

    Symétrique de `MoveActorCmd` (cf. `SceneEditor.move_camera_item`) : x/y
    d'un seul geste, les frames d'un même drag fusionnent. Un undo rend la
    position, pas l'existence de la caméra, comme déplacer un actor n'annule
    pas sa création."""

    def __init__(self, camera: Any, old_x: int, old_y: int,
                 new_x: int, new_y: int, persist_fn=None):
        self._cam = camera
        self._old = (old_x, old_y)
        self._new = (new_x, new_y)
        self.label = f"Déplacer caméra {getattr(camera, 'name', '')}".rstrip()
        self._persist = persist_fn

    def execute(self):
        self._cam.x, self._cam.y = self._new
        if self._persist:
            self._persist()

    def undo(self):
        self._cam.x, self._cam.y = self._old
        if self._persist:
            self._persist()

    def merge(self, newer: "Command") -> bool:
        if isinstance(newer, MoveCameraCmd) and self._cam is newer._cam:
            self._new = newer._new
            self._persist = newer._persist
            return True
        return False


class MoveUIRegionCmd(Command):
    """Déplacement d'une zone de texte dans le canvas.

    Structurellement identique à `MoveActorCmd` mais distincte à dessein : la
    fusion ne doit PAS confondre les deux (un drag d'actor suivi d'un drag de
    zone sont deux entrées d'historique), et l'étiquette est ce que l'utilisateur
    lit dans Édition → Annuler.

    x/y d'une zone ancrée sur un actor sont un OFFSET : la commande stocke ce
    qu'on lui donne, c'est à l'appelant d'avoir déjà retranché l'origine."""

    def __init__(self, region, old_x: int, old_y: int,
                 new_x: int, new_y: int, persist_fn=None):
        self._region = region
        self._old = (old_x, old_y)
        self._new = (new_x, new_y)
        self.label = f"Déplacer zone {region.name}"
        self._persist = persist_fn

    def execute(self):
        self._region.x, self._region.y = self._new
        if self._persist:
            self._persist()

    def undo(self):
        self._region.x, self._region.y = self._old
        if self._persist:
            self._persist()

    def merge(self, newer: "Command") -> bool:
        if isinstance(newer, MoveUIRegionCmd) and self._region is newer._region:
            self._new = newer._new
            self._persist = newer._persist
            return True
        return False


class ResizeUIRegionCmd(Command):
    """Redimensionnement d'une zone de texte par les poignées du canvas.

    Distincte de `MoveUIRegionCmd` parce qu'elle réécrit les QUATRE champs
    géométriques d'un coup : tirer une poignée haut/gauche déplace l'origine ET
    change la taille, un déplacement pur n'y touche pas. Les tuples sont
    (x, y, w, h) ; comme pour le move, x/y sont un OFFSET quand la zone est
    ancrée sur un actor, et c'est à l'appelant d'avoir déjà retranché l'origine
    de l'acteur."""

    def __init__(self, region, old, new, persist_fn=None):
        self._region = region
        self._old = tuple(old)   # (x, y, w, h)
        self._new = tuple(new)
        self.label = f"Redimensionner zone {region.name}"
        self._persist = persist_fn

    def _apply(self, g):
        self._region.x, self._region.y, self._region.w, self._region.h = g
        if self._persist:
            self._persist()

    def execute(self):
        self._apply(self._new)

    def undo(self):
        self._apply(self._old)

    def merge(self, newer: "Command") -> bool:
        if isinstance(newer, ResizeUIRegionCmd) and self._region is newer._region:
            self._new = newer._new
            self._persist = newer._persist
            return True
        return False


class UILayoutOrderCmd(Command):
    """Mutation undoable de l'ORDRE et de la HIÉRARCHIE des éléments d'une
    `UILayout` — réordonnancement de frères (z-order) OU reparentage avec
    position, deux gestes qui touchent l'un l'ordre de `elements`, l'autre une
    ref `parent`, souvent les deux à la fois (drop dans l'arbre). Remplace
    l'ancien `ReparentUIRegionCmd` (parent seul) : le drop porte désormais aussi
    la position, et un snapshot couvre les deux uniformément.

    Snapshot COMPLET (liste `elements` + `parent` de chaque élément), même
    patron que `_ScenePaletteCmd` : le `mutate_fn` applique la nouvelle
    configuration (via `UILayout.move_sibling`/`place_child`), et l'avant (pris à
    la construction) et l'après (pris au 1er execute) suffisent à rejouer sans
    ré-exécuter la logique — un `move_sibling` n'est pas idempotent, le rejouer
    en boucle dériverait."""

    def __init__(self, layout, mutate_fn, label: str, persist_fn=None):
        self._layout = layout
        self._mutate = mutate_fn
        self.label = label
        self._persist = persist_fn
        self._before = self._snapshot()
        self._after = None

    def _snapshot(self):
        return (list(self._layout.elements),
                {e.name: e.parent for e in self._layout.elements})

    def _restore(self, snap):
        elems, parents = snap
        self._layout.elements[:] = elems
        for e in self._layout.elements:
            if e.name in parents:
                e.parent = parents[e.name]

    def execute(self):
        if self._after is None:
            self._mutate()
            self._after = self._snapshot()
        else:
            self._restore(self._after)   # redo
        if self._persist:
            self._persist()

    def undo(self):
        self._restore(self._before)
        if self._persist:
            self._persist()


class AddActorCmd(Command):
    def __init__(self, scene: "Scene", actor: "Actor", persist_fn=None):
        self._scene = scene
        self._actor = actor
        self.label = f"Ajouter {actor.name}"
        self._persist = persist_fn

    def execute(self):
        if self._actor not in self._scene.actors:
            self._scene.actors.append(self._actor)
        if self._persist:
            self._persist()

    def undo(self):
        if self._actor in self._scene.actors:
            self._scene.actors.remove(self._actor)
        if self._persist:
            self._persist()


class PaintFrameCmd(Command):
    """
    Peinture / effacement de tuiles sur un AnimFrame (canvas sprite editor).
    Coups de pinceau consécutifs sur la même frame fusionnés en un seul undo.
    Utiliser avec record() (action déjà appliquée avant l'enregistrement).
    """

    def __init__(self, frame: Any, old_tiles: list, new_tiles: list, persist_fn=None):
        self._frame   = frame
        self._old     = old_tiles
        self._new     = new_tiles
        self.label    = "Peindre frame"
        self._persist = persist_fn

    def execute(self):
        self._frame.tiles = list(self._new)
        if self._persist: self._persist()

    def undo(self):
        self._frame.tiles = list(self._old)
        if self._persist: self._persist()

    def merge(self, newer: "Command") -> bool:
        if isinstance(newer, PaintFrameCmd) and self._frame is newer._frame:
            self._new     = newer._new
            self._persist = newer._persist
            return True
        return False


class DeleteResourceCmd(Command):
    """
    Suppression d'une Resource (scène, prefab…) depuis l'UI.
    execute : soft_delete (retire de la liste, JSON différé)
    undo    : restore (remet dans la liste et resauvegarde le JSON)
    """

    def __init__(self, manager: Any, item: Any, refresh_fn=None):
        self._mgr     = manager
        self._item    = item
        self.label    = f"Supprimer {getattr(item, 'name', str(item))}"
        self._refresh = refresh_fn

    def execute(self):
        self._mgr.soft_delete(self._item)
        if self._refresh:
            self._refresh()

    def undo(self):
        self._mgr.restore(self._item)
        if self._refresh:
            self._refresh()


class DeleteFontSourceCmd(DeleteResourceCmd):
    """Supprime une source de police en gardant ses familles cohérentes.

    Une ``Font`` vectorielle peut être la face d'un ou plusieurs ``FontAsset``.
    Un simple ``DeleteResourceCmd`` enlève correctement la source, mais laisse
    ces fiches afficher une face qui n'existe plus. La photographie est prise
    avant la première exécution afin que Ctrl+Z remette *exactement* les faces
    et les chaînes de repli que l'auteur avait configurées.
    """

    def __init__(self, project: Any, item: Any):
        super().__init__(project.fonts, item)
        self._project = project
        self._asset_state = [
            (asset, list(asset.faces),
             {variant: list(sources) for variant, sources in asset.sources.items()})
            for asset in project.font_assets
        ]

    def execute(self):
        super().execute()
        # Import local : history reste générique et n'introduit pas de cycle
        # module avec la couche d'encodage au chargement de l'application.
        from core.resources.asset_reconciliation import reconcile_font_assets
        reconcile_font_assets(self._project)

    def undo(self):
        super().undo()
        for asset, faces, sources in self._asset_state:
            asset.faces = list(faces)
            asset.sources = {variant: list(names) for variant, names in sources.items()}
            self._project.font_assets.save(asset)


class AddResourceCmd(Command):
    """
    Ajout d'une Resource au catalogue depuis l'UI (ex. dupliquer une palette).
    Strictement symétrique de DeleteResourceCmd — même paire de méthodes du
    ResourceStore, dans l'autre sens :
    execute : restore (ajoute à la liste et écrit le JSON)
    undo    : soft_delete (retire de la liste, JSON effacé à la fermeture)
    """

    def __init__(self, manager: Any, item: Any, refresh_fn=None):
        self._mgr     = manager
        self._item    = item
        self.label    = f"Ajouter {getattr(item, 'name', str(item))}"
        self._refresh = refresh_fn

    def execute(self):
        self._mgr.restore(self._item)
        if self._refresh:
            self._refresh()

    def undo(self):
        self._mgr.soft_delete(self._item)
        if self._refresh:
            self._refresh()


class DeleteInterfaceCmd(Command):
    """Retire un nœud `Interface` d'une scène (v0.25).

    Sa référence quitte `Scene.ui_layouts` ; et SI plus aucune scène ne le
    référence (`delete_asset`), l'asset lui-même part — `soft_delete`, donc le
    JSON n'est effacé qu'à la fermeture et `restore` le ramène à l'annulation.
    Un nœud PARTAGÉ ne perd que sa référence dans CETTE scène, jamais l'asset :
    le supprimer casserait les autres scènes. Deux gestes, une seule annulation —
    l'historique n'a pas de macro, d'où cette commande dédiée."""

    def __init__(self, store, layout, ref_list: list, delete_asset: bool,
                 persist_fn=None, refresh_fn=None):
        self._store = store
        # `layout` peut être l'asset `UILayout` ou une vue liée `BoundInterface` :
        # le store d'assets veut l'asset (`.layout`), la liste de scène veut le
        # NŒUD `InterfaceNode` qui le cite (repéré par `layout_name`).
        self._asset = getattr(layout, "layout", layout)
        self._name = self._asset.name
        self._refs = ref_list
        self._delete_asset = delete_asset
        self._node = next((n for n in ref_list if n.layout_name == self._name), None)
        self._index = (ref_list.index(self._node)
                       if self._node in ref_list else len(ref_list))
        self.label = f"Supprimer l'interface {self._name}"
        self._persist = persist_fn
        self._refresh = refresh_fn

    def _after(self):
        if self._persist:
            self._persist()
        if self._refresh:
            self._refresh()

    def execute(self):
        if self._node in self._refs:
            self._refs.remove(self._node)
        if self._delete_asset:
            self._store.soft_delete(self._asset)
        self._after()

    def undo(self):
        if self._delete_asset:
            self._store.restore(self._asset)
        if self._node is not None and self._node not in self._refs:
            self._refs.insert(min(self._index, len(self._refs)), self._node)
        self._after()


class SetPaletteColorCmd(Command):
    """
    Édition d'une couleur d'une PaletteBank à un index donné (Palette Editor).
    Les éditions consécutives sur le même (bank, index) sont fusionnées — un
    drag de slider / roue = une seule entrée d'undo (comme SetFieldCmd).

    apply_fn(index) est fournie par l'écran : elle persiste la banque et
    resynchronise l'UI (swatch, inspecteur, finder). C'est ce callback qui
    garantit le rafraîchissement du Palette Editor sur undo/redo, comme
    DeleteResourceCmd.refresh_fn.
    """

    def __init__(self, bank: Any, index: int, old_val: int, new_val: int, apply_fn):
        self._bank = bank
        self._index = index
        self._old = old_val
        self._new = new_val
        self.label = f"Couleur index {index}"
        self._apply = apply_fn

    def _set(self, value: int):
        if 0 <= self._index < len(self._bank.colors):
            self._bank.colors[self._index] = value
        self._apply(self._bank, self._index)

    def execute(self):
        self._set(self._new)

    def undo(self):
        self._set(self._old)

    def merge(self, newer: "Command") -> bool:
        if (isinstance(newer, SetPaletteColorCmd)
                and self._bank is newer._bank and self._index == newer._index):
            self._new = newer._new
            self._apply = newer._apply
            return True
        return False


class SetPaletteColorsCmd(Command):
    """
    Édition groupée de plusieurs slots d'une PaletteBank en UNE seule entrée
    d'undo (ex: vider une sélection). delta = {index: (old_val, new_val)}.
    apply_fn(bank) re-render la banque et persiste (voir SetPaletteColorCmd).
    """

    def __init__(self, bank: Any, delta: dict, apply_fn, label: str = "Modifier palette"):
        self._bank = bank
        self._delta = delta
        self.label = label
        self._apply = apply_fn

    def _set(self, pick: int):
        for i, pair in self._delta.items():
            if 0 <= i < len(self._bank.colors):
                self._bank.colors[i] = pair[pick]
        self._apply(self._bank)

    def execute(self):
        self._set(1)

    def undo(self):
        self._set(0)


class CollisionPaintCmd(Command):
    """
    Stroke de peinture collision (pinceau ou slope). Un stroke = press → release.
    delta : {(col, row): (old_tile, new_tile)}
    Les tiles sont déjà appliquées au moment du push — on bypasse execute().
    """

    def __init__(self, overlay, delta: dict, persist_fn=None):
        self._overlay = overlay
        self._delta   = delta
        self.label    = "Peinture collision"
        self._persist = persist_fn

    def execute(self):
        for (col, row), (_, new) in self._delta.items():
            self._overlay.set_tile(col, row, new)
        if self._persist:
            self._persist()

    def undo(self):
        for (col, row), (old, _) in self._delta.items():
            self._overlay.set_tile(col, row, old)
        if self._persist:
            self._persist()


def _collision_tag_owners(project):
    """Tous les acteurs/prefabs porteurs d'un CollisionBoxComponent — la même
    liste que la matrice de collision parcourt pour découvrir ses tags
    (cf. project_settings_dialog.CollisionsPanel)."""
    return [a for sc in project.scenes for a in sc.actors] + list(project.prefabs) + [
        ch for pf in project.prefabs for ch in (getattr(pf, "children", []) or [])]


class RenameCollisionTagCmd(Command):
    """Renomme un tag de collision PARTOUT en une seule étape d'annulation :
    chaque CollisionBoxComponent qui le portait (tag explicite OU vide,
    donc « body » par défaut), et la clé de chaque paire de la matrice qui
    le citait (cf. pair_key, models/settings.py). Un tag simplement déclaré
    (`ProjectSettings.collision_tags`, aucun composant) suit lui aussi."""

    def __init__(self, project, old_name: str, new_name: str, persist_fn=None, label: str = ""):
        from core.models.components import CollisionBoxComponent
        self._project = project
        self._old = old_name
        self._new = new_name
        self.label = label or f"Renommer le tag {old_name}"
        self._persist = persist_fn
        self._components = [
            c for o in _collision_tag_owners(project) for c in getattr(o, "components", [])
            if isinstance(c, CollisionBoxComponent) and (c.tag or "body") == old_name]

    def _apply(self, old: str, new: str):
        from core.models.settings import pair_key
        from scripting.api import DOMAIN_BOX_TAG
        # Les scripts citent le tag en chaîne (`self:collision_box("hitbox")`, `hb.tag == "hitbox"`) : ils
        # suivent le renommage, dans un sens comme dans l'autre (annulation).
        self._project.rename_lua_refs(DOMAIN_BOX_TAG, old, new)
        for c in self._components:
            c.tag = new
        s = self._project.settings
        remapped = set()
        for key in s.collision_disabled_pairs:
            a, b = key.split("|", 1)
            remapped.add(pair_key(new if a == old else a, new if b == old else b))
        s.collision_disabled_pairs = sorted(remapped)
        if old in s.collision_tags:
            s.collision_tags = [new if t == old else t for t in s.collision_tags]

    def execute(self):
        self._apply(self._old, self._new)
        if self._persist:
            self._persist()

    def undo(self):
        self._apply(self._new, self._old)
        if self._persist:
            self._persist()


class RemoveCollisionTagCmd(Command):
    """Retire un tag de collision : les composants qui le portaient
    EXPLICITEMENT retombent au défaut (tag vide → « body »), ses paires
    disparaissent de la matrice, et il quitte la liste des tags déclarés
    s'il y était. Un composant dont le tag était déjà vide (donc « body »
    par héritage, pas par choix) n'est pas touché — il n'a rien à perdre.
    Tout revient à l'identique par l'annulation."""

    def __init__(self, project, tag_name: str, persist_fn=None, label: str = ""):
        from core.models.components import CollisionBoxComponent
        self._project = project
        self._tag = tag_name
        self.label = label or f"Retirer le tag {tag_name}"
        self._persist = persist_fn
        self._components = [
            c for o in _collision_tag_owners(project) for c in getattr(o, "components", [])
            if isinstance(c, CollisionBoxComponent) and c.tag == tag_name]
        self._removed_pairs = {k for k in project.settings.collision_disabled_pairs
                               if tag_name in k.split("|", 1)}
        self._was_declared = tag_name in project.settings.collision_tags

    def execute(self):
        for c in self._components:
            c.tag = ""
        s = self._project.settings
        s.collision_disabled_pairs = [k for k in s.collision_disabled_pairs
                                      if k not in self._removed_pairs]
        if self._was_declared:
            s.collision_tags = [t for t in s.collision_tags if t != self._tag]
        if self._persist:
            self._persist()

    def undo(self):
        for c in self._components:
            c.tag = self._tag
        s = self._project.settings
        s.collision_disabled_pairs = sorted(set(s.collision_disabled_pairs) | self._removed_pairs)
        if self._was_declared and self._tag not in s.collision_tags:
            s.collision_tags = sorted(set(s.collision_tags) | {self._tag})
        if self._persist:
            self._persist()


class SceneInpaintingCmd(Command):
    """Stroke d'inpainting de scène (réassignation SE_PALBANK par tuile).
    delta : {(col, row): (old_slot|None, new_slot|None)}.
    Les tuiles sont déjà appliquées au moment du push — execute() n'est appelé
    que lors d'un redo. Délègue au SceneInpaintingController pour rebâtir le pixmap."""

    def __init__(self, controller, layer, bg_slot: int, delta: dict, persist_fn=None):
        self._ctrl = controller
        self._layer = layer
        self._bg_slot = bg_slot
        self._delta = delta
        self.label = "Inpainting de scène"

    def execute(self):
        self._ctrl.apply_override_delta(self._layer, self._bg_slot, self._delta, True)

    def undo(self):
        self._ctrl.apply_override_delta(self._layer, self._bg_slot, self._delta, False)


class BackgroundInpaintingCmd(Command):
    """Stroke d'inpainting de fond au niveau ÉDITEUR : réassignation de la palette
    (pal_bank local) par tuile dans `BackgroundAsset.tile_palette_overrides`,
    partagé entre toutes les scènes. delta : {(col,row): (old_idx|None, new_idx|None)}.
    Les tuiles sont déjà appliquées au moment du push — execute() ne sert qu'au redo.
    Délègue au BgInpaintController pour rebâtir le pixmap + persister."""

    def __init__(self, controller, ba, delta: dict):
        self._ctrl = controller
        self._ba = ba
        self._delta = delta
        self.label = "Inpainting de fond"

    def execute(self):
        self._ctrl.apply_override_delta(self._ba, self._delta, True)

    def undo(self):
        self._ctrl.apply_override_delta(self._ba, self._delta, False)


class SetSceneModeCmd(Command):
    """Change le mode vidéo d'une scène (0-5). Le changement élague les calques/
    palettes BG incompatibles → on snapshot (render_mode, background_layers,
    active_bg_palettes) pour un undo fidèle."""

    def __init__(self, scene, new_mode, new_layers, new_bg_palettes,
                 persist_fn=None, refresh_fn=None):
        self._scene = scene
        self._old = (scene.render_mode, list(scene.background_layers),
                     list(scene.active_bg_palettes))
        self._new = (new_mode, list(new_layers), list(new_bg_palettes))
        self.label = f"Mode de scène → Mode {new_mode}"
        self._persist = persist_fn
        self._refresh = refresh_fn

    def _apply(self, state):
        mode, layers, pals = state
        self._scene.render_mode = mode
        self._scene.background_layers[:] = layers
        self._scene.active_bg_palettes[:] = pals
        if self._persist:
            self._persist()
        if self._refresh:
            self._refresh()

    def execute(self):
        self._apply(self._new)

    def undo(self):
        self._apply(self._old)


class AddComponentCmd(Command):
    def __init__(self, actor: "Actor", comp: Any, persist_fn=None):
        self._actor = actor
        self._comp = comp
        self.label = f"Ajouter component {getattr(comp, 'id', '')}"
        self._persist = persist_fn

    def execute(self):
        if self._comp not in self._actor.components:
            self._actor.components.append(self._comp)
        if self._persist:
            self._persist()

    def undo(self):
        if self._comp in self._actor.components:
            self._actor.components.remove(self._comp)
        if self._persist:
            self._persist()


class RenameSpriteIdCmd(Command):
    """Renomme l'`id` d'un composant sprite ET les références du script de son
    propriétaire (`self:activate_sprite("id")`, `self.active_sprite == "id"`).

    Une commande à part, pas un `SetFieldCmd` : annuler doit défaire les DEUX —
    rendre l'ancien `id` sans réécrire le script laisserait des références mortes,
    que seul le build dénoncerait."""

    def __init__(self, project, owner: Any, comp: Any, old: str, new: str, persist_fn=None):
        self._project = project
        self._owner = owner
        self._comp = comp
        self._old = old
        self._new = new
        self.label = f"Renommer sprite {old} → {new}"
        self._persist = persist_fn

    def _apply(self, frm: str, to: str):
        with self._project._renaming():
            refs = self._project.rename_sprite_id_refs(self._owner, frm, to)
            self._comp.id = to
        self._project._notify_renamed("Sprite id", frm, to, refs)
        if self._persist:
            self._persist()

    def execute(self):
        self._apply(self._old, self._new)

    def undo(self):
        self._apply(self._new, self._old)


class RemoveComponentCmd(Command):
    def __init__(self, actor: "Actor", comp: Any, index: int, persist_fn=None):
        self._actor = actor
        self._comp = comp
        self._index = index
        self.label = f"Supprimer component {getattr(comp, 'id', '')}"
        self._persist = persist_fn

    def execute(self):
        if self._comp in self._actor.components:
            self._actor.components.remove(self._comp)
        if self._persist:
            self._persist()

    def undo(self):
        idx = min(self._index, len(self._actor.components))
        self._actor.components.insert(idx, self._comp)
        if self._persist:
            self._persist()


class RemoveListItemCmd(Command):
    """
    Suppression d'un élément d'une liste arbitraire (ex: AnimState d'un
    sprite). Générique pour éviter une Command dédiée par type de liste.
    """

    def __init__(self, container: list, item: Any, persist_fn=None, label: str = "Supprimer"):
        self._container = container
        self._item = item
        self._index = container.index(item)
        self.label = label
        self._persist = persist_fn

    def execute(self):
        if self._item in self._container:
            self._container.remove(self._item)
        if self._persist:
            self._persist()

    def undo(self):
        idx = min(self._index, len(self._container))
        self._container.insert(idx, self._item)
        if self._persist:
            self._persist()


class AddListItemCmd(Command):
    """
    Ajout d'un élément à une liste arbitraire (ex: BackgroundLayer d'un
    BackgroundAsset). Symétrique de RemoveListItemCmd — construire l'item
    AVANT de le pousser (contrairement à AddComponentCmd, pas besoin de le
    retirer manuellement pour laisser execute() faire son travail).
    """

    def __init__(self, container: list, item: Any, persist_fn=None, label: str = "Ajouter"):
        self._container = container
        self._item = item
        self.label = label
        self._persist = persist_fn

    def execute(self):
        if self._item not in self._container:
            self._container.append(self._item)
        if self._persist:
            self._persist()

    def undo(self):
        if self._item in self._container:
            self._container.remove(self._item)
        if self._persist:
            self._persist()


class RemoveListItemsCmd(Command):
    """
    Suppression d'un LOT d'éléments d'une liste arbitraire, en UNE entrée
    d'historique. Symétrique d'AddListItemsCmd, mêmes raisons.

    Les positions sont mémorisées et l'annulation réinsère en ordre croissant :
    la disposition d'origine est restituée à l'identique, et pas seulement le
    contenu — pour une mise en page d'interface, l'ordre de la liste EST le
    z-order et l'ordre des frères.
    """

    def __init__(self, container: list, items: list, persist_fn=None,
                 label: str = "Supprimer"):
        self._container = container
        at = {id(x): i for i, x in enumerate(container)}
        self._removed = sorted((at[id(it)], it) for it in items if id(it) in at)
        self.label = label
        self._persist = persist_fn

    def execute(self):
        for _i, item in self._removed:
            for i, x in enumerate(self._container):
                if x is item:
                    del self._container[i]
                    break
        if self._persist:
            self._persist()

    def undo(self):
        for i, item in self._removed:          # indices croissants
            self._container.insert(min(i, len(self._container)), item)
        if self._persist:
            self._persist()


class AddListItemsCmd(Command):
    """
    Ajout d'un LOT d'éléments à une liste arbitraire, en UNE entrée d'historique
    (ex: les copies d'un Ctrl+V, d'un Ctrl+D ou d'un Alt+glisser).

    Pluriel d'AddListItemCmd, et pas une boucle dessus : coller trois éléments
    est un seul geste, l'annuler doit l'être aussi — sinon il faudrait trois
    Ctrl+Z pour défaire un Ctrl+V, et la sauvegarde s'exécuterait trois fois.

    Appartenance testée par IDENTITÉ (`is`) et non par `in` : les items sont des
    dataclasses, deux copies aux champs identiques seraient confondues par `==`.
    """

    def __init__(self, container: list, items: list, persist_fn=None,
                 label: str = "Ajouter"):
        self._container = container
        self._items = list(items)
        self.label = label
        self._persist = persist_fn

    def _holds(self, item) -> bool:
        return any(x is item for x in self._container)

    def execute(self):
        for item in self._items:
            if not self._holds(item):
                self._container.append(item)
        if self._persist:
            self._persist()

    def undo(self):
        for item in self._items:
            for i, x in enumerate(self._container):
                if x is item:
                    del self._container[i]
                    break
        if self._persist:
            self._persist()


class RenameFileCmd(Command):
    """
    Renommage d'un fichier arbitraire sur disque (scripts assets/ — pas un
    Resource géré par ResourceStore, donc pas de rename() disponible).
    execute/undo renomment réellement le fichier dans les deux sens.
    """

    def __init__(self, old_path: Path, new_path: Path, refresh_fn=None):
        self._old = old_path
        self._new = new_path
        self.label = f"Renommer {old_path.name} → {new_path.name}"
        self._refresh = refresh_fn

    def execute(self):
        if self._old.exists():
            self._old.rename(self._new)
        if self._refresh:
            self._refresh()

    def undo(self):
        if self._new.exists():
            self._new.rename(self._old)
        if self._refresh:
            self._refresh()


class DeleteFileCmd(Command):
    """
    Suppression d'un fichier arbitraire sur disque (scripts assets/). Le
    contenu est gardé en mémoire le temps de la commande pour permettre un
    undo réel (contrairement à DeleteResourceCmd, il n'y a pas de
    soft_delete/restore disponible pour un fichier hors ResourceStore).
    """

    def __init__(self, path: Path, refresh_fn=None):
        self._path = path
        self._bytes: Optional[bytes] = None
        self.label = f"Supprimer {path.name}"
        self._refresh = refresh_fn

    def execute(self):
        if self._path.exists():
            self._bytes = self._path.read_bytes()
            self._path.unlink()
        if self._refresh:
            self._refresh()

    def undo(self):
        if self._bytes is not None:
            self._path.write_bytes(self._bytes)
        if self._refresh:
            self._refresh()


# ── Historique ────────────────────────────────────────────────────

class CommandHistory(QObject):
    """
    Stack undo/redo avec fusion de commandes consécutives identiques.
    Émis changed() à chaque mutation du stack pour mettre à jour l'UI.
    """

    changed = pyqtSignal()   # undo/redo dispo a changé

    def __init__(self, parent=None):
        super().__init__(parent)
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    # ── API ──────────────────────────────────────────────────────

    def record(self, cmd: Command):
        """Enregistre une commande SANS l'exécuter (déjà exécutée par l'appelant)."""
        if self._undo and self._undo[-1].merge(cmd):
            self.changed.emit()
            return
        self._undo.append(cmd)
        self._redo.clear()
        if len(self._undo) > _MAX_HISTORY:
            self._undo = self._undo[-_MAX_HISTORY:]
        self.changed.emit()

    def push(self, cmd: Command):
        """Exécute la commande et l'enregistre dans le stack undo."""
        # Tenter la fusion avec la dernière commande
        if self._undo and self._undo[-1].merge(cmd):
            # Fusion réussie : on réexécute la commande mergée (nouvelle valeur)
            cmd.execute()
            self.changed.emit()
            return

        cmd.execute()
        self._undo.append(cmd)
        self._redo.clear()

        # Borner la mémoire
        if len(self._undo) > _MAX_HISTORY:
            self._undo = self._undo[-_MAX_HISTORY:]

        self.changed.emit()

    def undo(self) -> Optional[str]:
        """Annule la dernière commande. Retourne son label ou None."""
        if not self._undo:
            return None
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)
        self.changed.emit()
        return cmd.label

    def redo(self) -> Optional[str]:
        """Rejoue la dernière commande annulée. Retourne son label ou None."""
        if not self._redo:
            return None
        cmd = self._redo.pop()
        cmd.execute()
        self._undo.append(cmd)
        self.changed.emit()
        return cmd.label

    def clear(self):
        """Vide l'historique (changement de scène / d'écran)."""
        self._undo.clear()
        self._redo.clear()
        self.changed.emit()

    # ── État ─────────────────────────────────────────────────────

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    @property
    def redo_label(self) -> str:
        return self._redo[-1].label if self._redo else ""


# ── Singleton global ──────────────────────────────────────────────
# Accessible par tous les modules sans passer de référence.

_history = CommandHistory()


def get_history() -> CommandHistory:
    return _history
