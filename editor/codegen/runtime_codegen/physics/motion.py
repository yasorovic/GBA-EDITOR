"""Mouvement automatique : gravité de scène des Character et Kinematic qui la suivent, intégration des Kinematic et Rigid.

Le sommeil Rigid (`physics_sleep_lines`) garde encore un chemin posé et un chemin par modèle du pool : il migre au
descripteur de modèle dans un pas suivant du chantier « posé et spawné »."""
from __future__ import annotations

from codegen.runtime_codegen.model_desc import model_desc_sym, scene_has_moving_bodies
from codegen.runtime_codegen.physics.body import physics_body, physics_body_mode
from codegen.runtime_codegen.shared_pool_gen import shared_models
from core.models.components import PHYSICS_BODY_RIGID


def motion_helper_lines() -> list[str]:
    """L'aide C du mouvement automatique, un seul code pour un acteur posé ou né : le descripteur `d` de son type dit
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
        "",
    ]


def physics_motion_lines(scene, project_settings, scene_actors, actor_offset: int, pi: list[dict],
                         dynamic_gravity: bool = False) -> list[str]:
    """Le pas automatique, après les scripts et avant toute résolution de collision : `body_motion_step` pour chaque
    emplacement actif, posé ou né, avec la ligne de son type dans le descripteur de modèle (`model_desc`). Le build ne
    spécialise plus rien par acteur ni par modèle ; il donne seulement les constantes de la scène.

    `dynamic_gravity` : un script écrit `scene.gravity` (cf. `project_sets_gravity`), la gravité se lit donc dans
    `g_gravity_x/y` au lieu d'être une constante de la scène."""
    if not scene_has_moving_bodies(scene_actors, pi):
        return []
    if dynamic_gravity:
        gx, gy = "g_gravity_x", "g_gravity_y"
    else:
        gravity_x, gravity_y = scene.effective_physics_gravity(project_settings)
        gx, gy = round(gravity_x * 256), round(gravity_y * 256)
    _iterations, max_fall_speed, damping, sleep_enabled, _sleep_threshold, sleep_delay = (
        scene.effective_physics_simulation(project_settings))
    step = (f"body_motion_step(_a,&{model_desc_sym(scene)}[_a->model],{gx},{gy},"
            f"{round((1.0 - damping) * 256)},{round(max_fall_speed * 256)},{sleep_delay if sleep_enabled else 0});")
    lines = ["    /* Kinematic/Rigid : mouvement avant les collisions, un seul pas pour les posés et les nés */"]
    if scene_actors:
        lines += [f"    for(int _k={actor_offset}; _k<{actor_offset + len(scene_actors)}; _k++){{",
                  "        Actor* _a=&g_actors[_k];", f"        if(_a->active) {step}", "    }"]
    if shared_models(pi):
        lines += ["    POOL_EACH(_pm){", "        Actor* _a=&g_actors[_pm];", f"        if(_a->active) {step}", "    }"]
    return lines


def physics_sleep_lines(scene, project_settings, scene_actors, actor_offset: int, pi: list[dict]) -> list[str]:
    """Endort les Rigid qui sont restés dans un rayon de `seuil x délai` autour d'une position d'ancrage.

    Le repos se lit sur la position, pas sur la vitesse : une pile de corps garde une vitesse résiduelle (la gravité
    ajoutée à chaque frame) que la correction de position, en pixels entiers, annule par à-coups, et ni la vitesse ni le
    déplacement d'une frame à l'autre ne la verraient au repos. L'ancre vit dans `g_rigid_rest`, indexée par emplacement;
    elle est reprise à la position courante dès que le corps en sort, ce qui remet le compteur à zéro."""
    _iterations, _max_fall, _damping, enabled, sleep_threshold, frames = (
        scene.effective_physics_simulation(project_settings))
    if not enabled:
        return []
    radius = round(sleep_threshold * 256) * frames

    def update(target: str, indent: str) -> list[str]:
        return [
            f"{indent}{{ int* _r=g_rigid_rest[({target})->inst]; int _dx=({target})->x-_r[0], _dy=({target})->y-_r[1];",
            f"{indent}  if(_dx<= {radius}&&_dx>=-{radius}&&_dy<= {radius}&&_dy>=-{radius}){{",
            f"{indent}      if(({target})->physics_sleep<{frames}) ({target})->physics_sleep++;",
            f"{indent}      if(({target})->physics_sleep>={frames}) "
            f"{{ ({target})->vx=0; ({target})->vy=0; }}",
            f"{indent}  }}else {{ _r[0]=({target})->x; _r[1]=({target})->y; ({target})->physics_sleep=0; }} }}",
        ]

    lines: list[str] = []
    for index, (actor, _sprite) in enumerate(scene_actors):
        body = physics_body(actor)
        if physics_body_mode(actor) == PHYSICS_BODY_RIGID and (body is None or body.can_sleep):
            target = f"&g_actors[{actor_offset + index}]"
            lines += [f"    if(({target})->active){{", *update(target, "        "), "    }"]

    cases = []
    for model in shared_models(pi):
        body = physics_body(model["prefab"])
        if (physics_body_mode(model["prefab"]) == PHYSICS_BODY_RIGID
                and (body is None or body.can_sleep)):
            cases += [f"        case {model['model_id']}: {{", *update("_a", "            "), "        } break;"]
    if cases:
        lines += ["    POOL_EACH(_ps){", "        Actor* _a=&g_actors[_ps];",
                  "        if(!_a->active) continue;", "        switch(_a->model){",
                  *cases, "        default: break;", "        }", "    }"]
    if lines:
        lines.insert(0, "    /* Sommeil Rigid : mesure apres toutes les resolutions */")
    return lines
