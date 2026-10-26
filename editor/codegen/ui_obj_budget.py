"""editor/codegen/ui_obj_budget.py — ce que l'interface en sprites coûte en OAM et en tuiles OBJ.

Bandes de texte en cible OBJ, images d'UI, fonds de conteneur en sprites. `oam_alloc` en lit le
poste « UI » du budget OAM d'une scène ; `gen_text.obj_text_alloc` en lit le placement."""
from __future__ import annotations

from codegen.grit_conversion import count_frames
from core.models.scene import Scene
from core.project import Project


def scene_ui_obj_slots(scene: Scene, project) -> int:
    """Entrées OAM que les OBJ d'INTERFACE de cette scène consomment — bandes de
    texte en cible OBJ, images d'UI, fonds de conteneur en sprites. Posé ENTRE les acteurs et les pools : le build réserve la bande
    OBJ juste après les acteurs, et `scene_oam_layout` fait donc démarrer les
    pools à `placed + ui`.

    Défensif : un projet à demi chargé (asset manquant) ne doit pas faire
    tomber le budget — 0 alors, le poste UI reste sûrement sous-compté plutôt
    que de lever."""
    try:
        return int(scene_obj_ui_slots(project, scene) or 0)
    except Exception:  # tolerated: half-loaded project: the validator reports the missing asset
        return 0


def layout_obj_budget_resolved(p: Project, lay) -> dict:
    """Le budget OBJ d'UNE mise en page, noms d'asset résolus.

    `layout_obj_budget` (modèle) ne résout ni les sprites ni la table de textes :
    c'est ici, qui les connaît, de fournir les frames, les tailles de frame et
    les glyphes animés — sous-réserver ferait écrire une image dans les tuiles de
    la suivante. Source unique lue par `gen_text.obj_text_alloc` (placement des zones) ET
    `scene_obj_ui_slots` (le pic OBJ d'une scène), pour que les
    deux comptent EXACTEMENT la même chose."""
    from core.models.ui_region import layout_obj_budget
    frames, sizes = {}, {}
    for im in lay.images:
        sprite = p.get_sprite(getattr(im, "sprite_name", "") or "")
        if sprite is not None and sprite.asset:
            frames[im.name] = count_frames(p, sprite)
            sizes[im.name] = (int(getattr(sprite, "frame_w", 0) or 0),
                              int(getattr(sprite, "frame_h", 0) or 0))
    return layout_obj_budget(lay, image_frames=frames, image_frame_size=sizes,
                             animated_by_name=p.layout_animated_glyphs(lay))


def scene_obj_ui_slots(p: Project, scene) -> int:
    """Slots OAM que l'interface en sprites de CETTE scène occupe — son pic. C'est le poste « UI » du budget OAM par scène
    (`scene_ui_obj_slots`), et la largeur de la bande OBJ que
    `scene_init` réserve juste après les acteurs (ordre acteurs → UI → pools).

    Max sur les mises en page que la scène référence : une seule bande OBJ est
    active à la fois (base unique, `text_obj_set_base`), donc c'est la plus
    gourmande qui commande — exactement le `max` que le build calculait
    globalement avant, restreint à la scène. Les mises en page sont lues via leur
    ASSET brut (`bound.layout`), même résolution que `gen_text.obj_text_alloc`, pour que la
    largeur réservée et le placement des zones concordent au slot près."""
    peak = 0
    seen = set()
    for bound in p.scene_ui_layouts(scene):
        lay = getattr(bound, "layout", bound)
        if id(lay) in seen:
            continue
        seen.add(id(lay))
        peak = max(peak, layout_obj_budget_resolved(p, lay)["oam"])
    return peak
