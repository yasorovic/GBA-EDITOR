"""Mouvement automatique : gravité de scène des Character et Kinematic qui la suivent, intégration des Kinematic et Rigid,
puis sommeil des Rigid. Les deux passes lisent le descripteur de modèle (`model_desc`) : un seul code pour un acteur posé
ou né."""
from __future__ import annotations

from codegen.runtime_codegen.model_desc import (
    BODY_MODE_RIGID, body_desc, each_slot, model_desc_sym, scene_has_moving_bodies, scene_owners,
)
from codegen.runtime_codegen.physics.areas import effect_areas, effect_rank_lines, effect_table_lines
from codegen.runtime_codegen.shared_pool_gen import shared_models


def motion_helper_lines() -> list[str]:
    """Les aides C du mouvement automatique et du sommeil, un seul code pour un acteur posé ou né : le descripteur `d` de son type dit
    son mode et sa part de gravité, la scène donne le reste. Character et Kinematic reçoivent la gravité (un Character
    l'applique par son script) ; Kinematic et Rigid intègrent leur vitesse ; le Rigid est amorti et peut dormir.

      gx, gy        gravité de scène, Q8 (constante, ou `g_gravity_x/y` quand un script l'écrit) ;
      damping       part de vitesse gardée par un Rigid, sur 256 ;
      max_fall      vitesse de chute maximale, Q8 (0 : aucune) ;
      sleep_frames  délai du sommeil de scène, 0 s'il est coupé. Le compteur ne se remet pas à zéro ici : une vitesse
                    résiduelle sous le seuil ne doit pas empêcher le sommeil (`physics_sleep_lines` le remet à zéro
                    quand la vitesse dépasse le seuil, l'API de script quand elle l'écrit).

    Inline forcé : appelée dans la boucle d'un tick, une vraie fonction double le coût de la passe (mesure du
    2026-11-06, `internal/development/TODO.md`)."""
    return [
        "static inline __attribute__((always_inline, unused)) void body_motion_step(Actor* a,const ModelDesc* d,",
        "        int gx,int gy,int damping,int max_fall,int sleep_frames){",
        "    int mode=d->body_mode;",
        "    if(mode==BODY_MODE_NONE) return;",
        "    int bgx=(gx*d->gravity_scale)/256, bgy=(gy*d->gravity_scale)/256;",
        "    if(mode==BODY_MODE_RIGID){",
        "        if(sleep_frames&&d->can_sleep&&a->physics_sleep>=sleep_frames&&!a->vx&&!a->vy) return;",
        "        a->vx+=bgx; a->vy+=bgy;",
        "        if(damping==0){ a->vx=0; a->vy=0; }",
        "        else if(damping!=256){ a->vx=(a->vx*damping)/256; a->vy=(a->vy*damping)/256; }",
        "        if(max_fall&&a->vy>max_fall) a->vy=max_fall;",
        "        actor_apply_velocity(a);",
        "        return;",
        "    }",
        "    if(bgx||bgy){",
        "        a->vx+=bgx; a->vy+=bgy;",
        "        if(max_fall&&a->vy>max_fall) a->vy=max_fall;",
        "    }",
        "    if(mode==BODY_MODE_KINEMATIC) actor_apply_velocity(a);",
        "}",
        "/* Le sommeil d'un Rigid : `radius` (Q8) et `frames` viennent de la scène, cf. `physics_sleep_lines`. */",
        "static inline __attribute__((always_inline, unused)) void body_sleep_step(Actor* a,const ModelDesc* d,",
        "        int radius,int frames){",
        "    if(d->body_mode!=BODY_MODE_RIGID||!d->can_sleep) return;",
        "    int* r=g_rigid_rest[a->slot_index]; int dx=a->x-r[0], dy=a->y-r[1];",
        "    if(dx<=radius&&dx>=-radius&&dy<=radius&&dy>=-radius){",
        "        if(a->physics_sleep<frames) a->physics_sleep++;",
        "        if(a->physics_sleep>=frames){ a->vx=0; a->vy=0; }",
        "    } else { r[0]=a->x; r[1]=a->y; a->physics_sleep=0; }",
        "}",
        "",
    ]


def physics_motion_lines(scene, project_settings, scene_actors, pi: list[dict],
                         dynamic_gravity: bool = False, layout=None) -> list[str]:
    """Le pas automatique, après les scripts et avant toute résolution de collision : `body_motion_step` pour chaque
    emplacement actif, posé ou né, avec la ligne de son type dans le descripteur de modèle (`model_desc`). Le build ne
    spécialise plus rien par acteur ni par modèle ; il donne seulement les constantes de la scène.

    `dynamic_gravity` : un script écrit `scene.gravity` (cf. `project_sets_gravity`), la gravité se lit donc dans
    `g_gravity_x/y` au lieu d'être une constante de la scène. `layout` : la mise en page OAM de la scène (`scene_oam_layout`),
    nécessaire aux zones d'effet des Areas : chaque corps qu'une zone atteint la traverse (`area_effects_apply`) avant que la
    gravité soit ajoutée à sa vitesse, ce qui réveille aussi un Rigid endormi."""
    if not scene_has_moving_bodies(scene_actors, pi):
        return []
    if dynamic_gravity:
        gx, gy = "g_gravity_x", "g_gravity_y"
    else:
        gravity_x, gravity_y = scene.effective_physics_gravity(project_settings)
        gx, gy = round(gravity_x * 256), round(gravity_y * 256)
    _iterations, max_fall_speed, damping, sleep_enabled, _sleep_threshold, sleep_delay = (
        scene.effective_physics_simulation(project_settings))
    desc = f"&{model_desc_sym(scene)}[_a->type_id]"
    rest = f"{round((1.0 - damping) * 256)},{round(max_fall_speed * 256)},{sleep_delay if sleep_enabled else 0}"
    ranks = effect_rank_lines(scene, layout, scene_actors, pi) if layout is not None else []
    head = "    /* Kinematic/Rigid : mouvement avant les collisions, un seul pas pour les posés et les nés */"
    if not ranks:
        return [head, *each_slot(f"body_motion_step(_a,{desc},{gx},{gy},{rest});")]
    zones = len(effect_areas(scene))
    # La zone ajuste la vitesse et la gravité de scène du corps (`_gx/_gy`, avant l'échelle de gravité de son type) ; le pas
    # est celui d'un corps sans zone.
    step = (f"{{ int _gx={gx},_gy={gy}; u8 _r=_fx_rank[_a->type_id]; "
            f"if(_r!=255) area_effects_apply(_fx,{zones},_a,_r,{desc},&_gx,&_gy); "
            f"body_motion_step(_a,{desc},_gx,_gy,{rest}); }}")
    return [head, *effect_table_lines(scene), *ranks, *each_slot(step)]


def physics_sleep_lines(scene, project_settings, scene_actors, pi: list[dict]) -> list[str]:
    """Endort les Rigid qui sont restés dans un rayon de `seuil x délai` autour d'une position d'ancrage :
    `body_sleep_step` pour chaque emplacement actif, posé ou né, avec la ligne de son type dans le descripteur de modèle
    (seuls les types Rigid qui peuvent dormir sont concernés).

    Le repos se lit sur la position, pas sur la vitesse : une pile de corps garde une vitesse résiduelle (la gravité
    ajoutée à chaque frame) que la correction de position, en pixels entiers, annule par à-coups, et ni la vitesse ni le
    déplacement d'une frame à l'autre ne la verraient au repos. L'ancre vit dans `g_rigid_rest`, indexée par emplacement;
    elle est reprise à la position courante dès que le corps en sort, ce qui remet le compteur à zéro."""
    _iterations, _max_fall, _damping, enabled, sleep_threshold, frames = (
        scene.effective_physics_simulation(project_settings))
    if not enabled or not any(body_desc(o)[:2] == (BODY_MODE_RIGID, 1) for o in scene_owners(scene_actors, pi)):
        return []
    radius = round(sleep_threshold * 256) * frames
    step = f"body_sleep_step(_a,&{model_desc_sym(scene)}[_a->type_id],{radius},{frames});"
    return ["    /* Sommeil Rigid : mesure apres toutes les resolutions, un seul pas pour les posés et les nés */",
            *each_slot(step)]
