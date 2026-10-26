"""editor/codegen/oam_budget.py — les décomptes d'un projet contre les plafonds du matériel.

Matrices affines, tuiles OBJ, taille de `g_oam_entries[]` et de `g_actors[]`. Lit la géométrie
de `oam_alloc` ; ne la décide pas."""
from __future__ import annotations

from codegen.actor_appearance import owner_appearances
from codegen.oam_alloc import project_has_model, scene_oam_layout
from codegen.ui_obj_budget import layout_obj_budget_resolved, scene_obj_ui_slots
from core.models.components import affine_sprite_component
from core.models.scene import Scene

# Les matrices affines de l'OAM : 32 par scène (matériel).
AFFINE_LIMIT = 32


def scene_affine_requests(project, scene: Scene) -> int:
    """Matrices affines que les acteurs POSÉS de la scène demandent — avant le plafond de `AFFINE_LIMIT`.

    Une matrice se réserve à la main (`SpriteComponent.affine_transform`), donc elle se compte : un acteur
    actif qui la coche en réserve une. Un enfant sans transform propre PARTAGE celle de son parent et ne
    coûte rien. `compute_affine_info` s'arrête en silence à 32 ; ce compte, lui, continue, pour que le
    dépassement se voie. Les instances NÉES n'en réservent pas : elles prennent à la frame celles que les
    posés laissent libres."""
    n = 0
    for a in scene.actors:
        if a.active:
            sc = affine_sprite_component(a)
            n += bool(sc and sc.affine_transform)
    return n


def project_obj_tiles(project) -> tuple[int, int]:
    """(tuiles OBJ occupées, plafond) — la VRAM des sprites telle que le build la pose.

    Contrairement à l'OAM, la VRAM OBJ n'est PAS per-scène : les tuiles de tous
    les sprites du projet sont résidentes et partagées (`main_gen` : union des
    acteurs de chaque scène, des apparences supplémentaires, des prefabs poolés
    et des images d'interface, dédupliquée par sprite, toutes frames comprises).
    Cette fonction rejoue exactement cette union ; `obj_tiles_used` fait le
    comptage, pour que la barre d'état et le build ne puissent pas diverger.

    Le plafond est celui du matériel : 1024 tuiles 4bpp, ramené à 512 dès qu'une
    scène est en mode bitmap (3-5), la VRAM BG empiétant sur l'espace sprite.
    Les zones de texte en sprites ajoutent leur bande, comme au build."""
    from codegen.runtime_codegen.gen_scene_query import obj_tiles_used, ui_image_sprites
    pairs: list = []
    for scene in project.scenes:
        for actor in scene.actors:
            if actor.active:
                pairs += [(actor, sp) for _c, sp in owner_appearances(project, actor)]
    for prefab in project.prefabs:
        if not project_has_model(project, prefab):
            continue
        for owner in [prefab, *(getattr(prefab, "children", []) or [])]:
            pairs += [(owner, sp) for _c, sp in owner_appearances(project, owner)]
    pairs += ui_image_sprites(project)

    used = obj_tiles_used(project, pairs)
    if any(scene_obj_ui_slots(project, s) > 0 for s in project.scenes):
        used += max((place["tile_rel"] + place["tiles"]
                     for lay in getattr(project, "ui_layouts", [])
                     for place in layout_obj_budget_resolved(project, lay)["place"].values()),
                    default=0)
    cap = 512 if any(getattr(s, "render_mode", 0) in (3, 4, 5) for s in project.scenes) else 1024
    return used, cap


def project_oam_entry_count(project) -> int:
    """Taille de `g_oam_entries[]` : la scène la plus gourmande (MAX, pas somme).

    Une seule scène est vivante à la fois et chaque `scene_init` repart de la
    base 0 : dimensionner sur le max suffit, la somme des unions faisait payer à
    la scène de menu les slots des balles du niveau d'action.
    Plancher à 1 — un `OamEntry g_oam_entries[0]` ne compile pas."""
    return max((scene_oam_layout(project, sc).table_size for sc in project.scenes),
               default=0) or 1


def project_actor_count(project) -> int:
    """Taille de `g_actors[]`, même règle (MAX des scènes, plancher à 1) mais
    sur les seuls ACTEURS : les OBJ d'interface occupent `g_oam_entries[]`, pas
    `g_actors[]` (marche 0b de « La struct Actor allégée »)."""
    return max((scene_oam_layout(project, sc).actors for sc in project.scenes),
               default=0) or 1
