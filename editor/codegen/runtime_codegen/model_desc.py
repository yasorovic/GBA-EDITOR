"""runtime_codegen/model_desc.py : la table du DESCRIPTEUR DE MODÈLE d'une scène (`ModelDesc`, cf. actor_types_static.h).

Une ligne par type d'emplacement (`Actor.model`) : le type 0, ceux du pool partagé (`model_id`, puis `model_id + k`
pour la partie k), puis ceux des acteurs posés (`OamLayout.placed_model`). Le runtime lit la ligne de l'emplacement,
qu'il soit posé ou né : c'est ce qui permet d'écrire un module une seule fois (règle « posé = spawné »).

Aujourd'hui la table ne porte que le mouvement automatique (`physics.motion`) ; chaque module migré y ajoute ses
champs. Elle est rangée en IWRAM (section `.data.*` : sans elle, GCC remet en ROM une table jamais écrite, et la ROM
coûte des états d'attente à chaque lecture)."""
from __future__ import annotations

from codegen.c_names import sym as c_sym
from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen.physics.body import physics_body, physics_body_mode
from codegen.runtime_codegen.shared_pool_gen import shared_models
from core.models.components import PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_RIGID

_BODY_MODE = {PHYSICS_BODY_CHARACTER: 1, PHYSICS_BODY_KINEMATIC: 2, PHYSICS_BODY_RIGID: 3}


def model_desc_sym(scene) -> str:
    return f"g_model_desc_{c_sym(scene.name)}"


def body_desc(owner) -> tuple[int, int, int]:
    """(body_mode, can_sleep, gravity_scale Q8) d'un porteur. Character et Kinematic ignorent la gravité de scène sans
    `use_scene_gravity` (un acteur sans corps, Character par repli, l'ignore aussi) ; un Rigid la suit toujours."""
    mode = physics_body_mode(owner)
    body = physics_body(owner)
    if mode in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC) and not (body and body.use_scene_gravity):
        scale = 0
    else:
        scale = round((body.gravity_scale if body else 1.0) * 256)
    return _BODY_MODE.get(mode, 0), 1 if body is None or body.can_sleep else 0, scale


def scene_has_moving_bodies(scene_actors, pi) -> bool:
    """Un corps de la scène, posé ou modèle du pool, reçoit le mouvement automatique : la table et la passe existent."""
    owners = [actor for actor, _sprite in scene_actors] + [m["prefab"] for m in shared_models(pi)]
    return any(physics_body_mode(o) in _BODY_MODE for o in owners)


def model_desc_lines(p, scene, scene_actors, pi) -> list[str]:
    """La définition C de `g_model_desc_<Scène>`, ou rien si aucun corps ne bouge (personne ne la lit)."""
    if not scene_has_moving_bodies(scene_actors, pi):
        return []
    lay = scene_oam_layout(p, scene)
    rows: list = [((0, 0, 0), "aucun type")] * lay.kinds
    for m in shared_models(pi):
        # Une partie suit sa racine par la composition, elle ne reçoit pas de mouvement propre.
        rows[m["model_id"]] = (body_desc(m["prefab"]), f"né : {m['prefab'].name}")
    for (actor, _sprite), kind in zip(scene_actors, lay.placed_model, strict=True):
        rows[kind] = (body_desc(actor), f"posé : {actor.name}")
    body = [f"    {{{mode},{sleep},{scale}}},   /* {kind} {label} */"
            for kind, ((mode, sleep, scale), label) in enumerate(rows)]
    return [f"/* Descripteur de modèle de la scène {scene.name} : une ligne par type d'emplacement (`Actor.model`), "
            "lue en IWRAM à chaque image. */",
            f"static ModelDesc {model_desc_sym(scene)}[{lay.kinds}] __attribute__((section(\".data.model_desc\"))) = {{",
            *body, "};", ""]
