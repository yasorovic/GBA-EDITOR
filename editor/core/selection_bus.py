"""
selection_bus.py — Point central de sélection pour tous les panels.

Règle absolue :
  - Les panels appellent bus.select(obj) quand l'utilisateur interagit.
  - Les panels écoutent bus.changed pour se mettre à jour (on_selection).
  - Les panels ne se parlent JAMAIS directement.
  - on_selection() ne rappelle JAMAIS bus.select() — sens unique.

Usage :
    from core.selection_bus import get_bus
    bus = get_bus()
    bus.select(actor)          # émet changed(actor)
    bus.changed.connect(panel.on_selection)
"""

from __future__ import annotations
from PyQt6.QtCore import QObject, pyqtSignal


class CameraSelection:
    """Marqueur de sélection : l'ICÔNE caméra a été cliquée dans le canvas (ou
    une caméra choisie dans le scene tree) — distinct d'une sélection de Scene
    « nue » (qui affiche le SceneInspector, comme Actor/Prefab affichent leur
    propre inspecteur). Le rectangle de vue 240×160 de la caméra n'est qu'un
    retour visuel, non cliquable ; seule l'icône déclenche ce marqueur (cf.
    CameraItem.shape() dans scene_canvas.py). Sans lui, impossible de
    distinguer les deux intentions une fois passées par le bus.

    `camera` désigne PRÉCISÉMENT la caméra visée (la scène peut en posséder
    plusieurs) : toujours une caméra réelle, une scène sans caméra n'en offre
    aucune à sélectionner."""
    __slots__ = ("scene", "camera")

    def __init__(self, scene, camera=None):
        self.scene = scene
        self.camera = camera


class ActorSelection:
    """Sélection multiple d'acteurs, avec un acteur actif pour l'inspecteur."""
    __slots__ = ("actors", "active")

    def __init__(self, actors, active=None):
        self.actors = tuple(actors)
        # Les acteurs sont mutables et peuvent être structurellement égaux :
        # l'éditeur les sélectionne toujours par identité, jamais par ``==``.
        self.active = next((actor for actor in self.actors if actor is active),
                           self.actors[0] if self.actors else None)


class BackgroundLayerSelection:
    """Marqueur de sélection d'un slot BG de la scène.

    Un slot est une partie du matériel, même lorsqu'il ne contient encore
    aucun fond. Le marqueur conserve donc le slot plutôt qu'un BackgroundLayer
    éventuellement absent, et laisse l'inspecteur ouvrir la bonne ligne.
    """
    __slots__ = ("scene", "bg_slot")

    def __init__(self, scene, bg_slot: int):
        self.scene = scene
        self.bg_slot = int(bg_slot)


class UIElementSelection:
    """Marqueur de sélection : un ÉLÉMENT d'UI (zone, panel, texte…) a été
    sélectionné dans le canvas ou l'arbre.

    Porte la mise en page en plus de l'élément, parce qu'un élément ne connaît
    pas son `UILayout` — et que l'inspecteur en a besoin pour dire « partagée
    par N scènes » comme pour le supprimer de la bonne liste. Même raison d'être
    que `CameraSelection` : le bus transporte une intention, pas seulement un
    objet.

    `region` est un alias rétro-compat de `element` : le bus portait autrefois
    des zones seules, et de nombreux sites lisent encore `.region`."""
    __slots__ = ("layout", "element")

    def __init__(self, layout, element):
        self.layout = layout
        self.element = element

    @property
    def region(self):
        return self.element


# Alias historique : `UIRegionSelection(layout, region)` construit toujours, et
# `isinstance(obj, UIRegionSelection)` reste vrai pour tout élément.
UIRegionSelection = UIElementSelection


class UILayoutSelection:
    """Marqueur de sélection : le NŒUD `Interface` lui-même (la racine de la
    branche dans l'arbre de scène), distinct d'un de ses éléments.

    C'est lui qui porte le chemin matériel du sous-arbre — ancrage + cible
    (v0.25) — d'où un inspecteur propre, là où le clic sur le nœud ne faisait
    rien. Porte la `scene` en plus du `layout` : le badge « partagée — N scènes »
    et l'acteur suivi (ancrage actor) se lisent dans le contexte de la scène,
    exactement comme `CameraSelection` porte la sienne."""
    __slots__ = ("layout", "scene")

    def __init__(self, layout, scene):
        self.layout = layout
        self.scene = scene


class SelectionBus(QObject):
    """
    Singleton de sélection. Émet changed(obj) à chaque changement.
    obj : Actor | Scene | Prefab | CameraSelection | UIRegionSelection | None
    """

    changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = None

    def select(self, obj):
        """Sélectionner un objet. No-op si déjà sélectionné (évite les boucles)."""
        if obj is self._current:
            return
        self._current = obj
        self.changed.emit(obj)

    def clear(self):
        self.select(None)

    @property
    def current(self):
        return self._current


_bus = SelectionBus()


def get_bus() -> SelectionBus:
    return _bus
