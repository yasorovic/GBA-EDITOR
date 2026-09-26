"""editor/codegen/actor_budget.py — la façade « budget d'acteurs » de l'inspecteur.

La géométrie OAM d'une scène vit désormais dans `codegen/oam_alloc.py` (source de
vérité unique, sur le modèle de `palette_alloc.py`, ROADMAP v0.17 T1+T2+T3). Ce
module n'en est plus que la VUE ÉDITEUR : il lit `scene_oam_layout` et rend le
dict que la carte « Actor budget » affiche, pour que l'inspecteur n'ait aucune
arithmétique à refaire de son côté. Il ré-exporte aussi les quelques symboles que
l'UI et le validateur importaient d'ici, pour ne pas casser leurs imports.

Le budget est DÉRIVÉ, pas réparti. Il a TROIS postes et UN plafond :

    acteurs posés  +  OBJ d'interface  +  slots de pool  =  128

Les deux premiers se COMPTENT (résolus au build), seul le pool se DÉCLARE. Le
plafond (128) est celui du matériel — cf. `oam_alloc` pour ce qu'il compte et ce
qu'il sur-compte volontairement.
"""
from __future__ import annotations

from core.models.scene import Scene
# La géométrie est ailleurs : ce module la LIT. Ré-exports pour les appelants
# historiques (inspecteur, validateur) qui importaient ces noms d'ici.
from codegen.oam_alloc import (
    OAM_LIMIT, prefab_group, scene_actor_slots, scene_pool_instances,
    scene_ui_obj_slots, scene_oam_layout,
)

__all__ = [
    "OAM_LIMIT", "prefab_group", "scene_actor_slots", "scene_pool_instances",
    "scene_ui_obj_slots", "scene_pool_slots", "prefab_pool_instances",
    "scene_actor_budget",
]


def prefab_pool_instances(project, prefab) -> int:
    """Combien d'instances de ce prefab vivent au plus dans UNE scène, toutes
    scènes confondues — le MAX sur les scènes qui le déclarent, 0 si aucune.

    Depuis la compilation par scène (ROADMAP v0.17), le pool émis en ROM est
    per-scène : ce max ne sert plus au chemin build OAM (`headers`/`main_gen`
    lisent `scene_oam_layout`). Il ne survit que pour les décomptes encore
    PROJET-WIDE — l'allocateur de palette réserve un slot OBJ global à un prefab
    poolé (T5 non couvert ici), et le build émet les tuiles d'un sprite de prefab
    dès qu'une scène le spawne. Plus de repli sur `Prefab.max_instances` : un
    prefab qu'aucune scène ne déclare n'est plus spawnable, et c'est le contrat
    (le champ hérité ne pilote plus rien)."""
    return max((scene_pool_instances(s, prefab) for s in project.scenes),
               default=0)


def scene_pool_slots(scene: Scene, project) -> int:
    """Entrées OAM que les pools de cette scène consomment — instances × parties
    QUI AFFICHENT UN SPRITE, sommées sur les prefabs qu'elle déclare. Un marqueur
    (point de tir, ancre de hitbox) n'en coûte aucune."""
    return scene_oam_layout(project, scene).pool_entries


def scene_actor_budget(scene: Scene, project) -> dict:
    """Tout ce que la carte « Actor budget » affiche, en un seul appel. Trois
    postes, une seule faute possible — le total déborde des 128 entrées du
    matériel (`over_budget`).

    Le poste « acteurs » de l'INSPECTEUR honore l'override `Scene.actor_slots`
    (réservation manuelle, ROADMAP v0.17) : c'est un affichage de budget, pas la
    géométrie de build. `pool` et `placed`, eux, viennent de `scene_oam_layout`
    (la géométrie réelle). Les deux ne divergent que si l'auteur a posé un
    override — aucune scène neuve ne le fait."""
    lay = scene_oam_layout(project, scene)
    # override, sinon = les acteurs posés QUI AFFICHENT un sprite (un contrôleur ou
    # un déclencheur ne consomme aucune entrée OAM).
    actors = scene.actor_slots if scene.actor_slots > 0 else lay.placed_entries
    ui     = lay.ui
    pool   = lay.pool_entries
    used   = actors + ui + pool
    return {
        "actors":      actors,
        "ui":          ui,
        "pool":        pool,
        "placed":      lay.placed,
        "used":        used,
        "total":       OAM_LIMIT,
        "free":        OAM_LIMIT - used,
        "over_budget": used > OAM_LIMIT,
    }
