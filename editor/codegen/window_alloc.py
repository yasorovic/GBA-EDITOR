"""editor/codegen/window_alloc.py — allocation de WIN0/WIN1 par scène.

Source de vérité UNIQUE pour « quelle INTENTION (cadre de caméra, panneau UI
nommé) reçoit quel rang matériel (`WINR_0`/`WINR_1`) ». Même famille que
`palette_alloc.py`/`vram_alloc.py` (cf. ARCHITECTURE.md, « Ressources
matérielles — l'auteur ne les nomme jamais » et « Deux allocateurs, pas un ») :
résolu au BUILD, en Python, pas à l'exécution — le nombre d'intentions d'une
scène ne change pas en cours de partie.

Ce que cet allocateur NE couvre PAS, par construction (cf. ARCHITECTURE.md) :
`WINR_OBJ` (pas de géométrie, pilotée par `Actor.obj_mode`, jamais disputée)
et `WINR_OUT` (le complément automatique — personne ne peut le demander). Le
pool réellement adressable ne contient que DEUX places.

Déterministe, pas optimal : l'intention caméra (si elle existe) prend
TOUJOURS la première place (`WINR_0`), puis chaque `WindowSlot` nommé prend ce
qui reste, dans l'ordre de `Scene.windows`. Pas de champ de priorité
authorable — cf. ROADMAP.md, chantier « l'allocateur de ressources
matérielles », décision verrouillée « déterminisme avant optimalité »."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.models.scene import Scene
from core.project import Project

# Les deux seuls rangs matériels disputables (WINR_OBJ=2/WINR_OUT=3 ne le sont
# jamais, cf. docstring de module).
_MAX_SLOTS = 2


@dataclass
class WindowLayout:
    """Résultat de l'allocation pour UNE scène."""
    slots: dict = field(default_factory=dict)          # nom de WindowSlot -> 0 ou 1
    camera_slot: Optional[int] = None                   # 0 ou 1 si une caméra de la scène a un frame réduit
    overflow: list = field(default_factory=list)        # noms d'intentions qui n'ont PAS pu être placées

    def slot_for(self, window_name: str) -> Optional[int]:
        return self.slots.get(window_name)


def scene_needs_camera_slot(scene: Scene, project=None) -> bool:
    """Une des caméras de la scène a-t-elle un cadre plus petit que l'écran ?
    Une seule réservation même si plusieurs le font — une seule caméra est
    active à la fois (cf. camera.py)."""
    return any(c.px('frame_w', project) < 240 or c.px('frame_h', project) < 160 for c in scene.cameras)


def scene_window_names(scene: Scene) -> list:
    """Noms des `WindowSlot` rectangle (non-OBJ) de la scène, dans l'ordre
    d'auteur — ce sont les intentions candidates à WIN0/WIN1."""
    return [ws.name for ws in scene.windows if not ws.is_obj]


def scene_window_layout(project: Project, scene: Scene) -> WindowLayout:
    """Assigne WINR_0/WINR_1 aux intentions de `scene` : le cadre de la
    caméra active (s'il existe) en premier, puis les `WindowSlot` nommés dans
    l'ordre. Au-delà de deux intentions, le reste va dans `overflow` — pas de
    repli silencieux possible pour une window (une région non allouée
    s'affiche partout au lieu d'être découpée, un bug visuel sans signal)."""
    layout = WindowLayout()
    next_slot = 0

    if scene_needs_camera_slot(scene, project):
        layout.camera_slot = next_slot
        next_slot += 1

    for name in scene_window_names(scene):
        if next_slot < _MAX_SLOTS:
            layout.slots[name] = next_slot
            next_slot += 1
        else:
            layout.overflow.append(name)

    return layout


def scene_window_budget(scene: Scene, project=None) -> tuple:
    """(intentions utilisées, 2) — même collecte que `scene_window_layout`
    sans construire l'assignation, pour l'affichage budget des inspecteurs
    (Scene « Windows », Camera « Transform »). `utilisées` peut dépasser 2 :
    montrer le dépassement plutôt que le masquer est le but de ce chiffre."""
    used = (1 if scene_needs_camera_slot(scene, project) else 0) + len(scene_window_names(scene))
    return (used, _MAX_SLOTS)
