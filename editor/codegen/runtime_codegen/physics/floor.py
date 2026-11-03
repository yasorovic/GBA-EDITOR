"""Contact au sol final d'un CharacterBody ou d'un RigidBody sur les corps poses sous lui."""
from __future__ import annotations

from core.models.collision_tiles import ONEWAY_NONE, ONEWAY_UP
from core.models.components import (
    ONE_WAY_GRAVITY,
    ONE_WAY_OFF,
    PHYSICS_BODY_CHARACTER,
    PHYSICS_BODY_KINEMATIC,
    PHYSICS_BODY_RIGID,
    PHYSICS_BODY_STATIC,
)
from core.models.settings import tags_collide
from codegen.runtime_codegen.shared_pool_gen import shared_models
from codegen.runtime_codegen.physics.body import (
    physics_blocker_entries,
    physics_body_mode,
    physics_collider_entries,
    project_sets_gravity,
    shape_one_way_dir,
    support_normal,
)


def project_has_floors(p) -> bool:
    """Le projet peut produire un contact au sol entre acteurs poses."""
    owners = [actor for scene in getattr(p, "scenes", []) or [] for actor in scene.actors]
    owners += list(getattr(p, "prefabs", []) or [])
    modes = {physics_body_mode(owner) for owner in owners}
    if PHYSICS_BODY_RIGID in modes:
        return True
    return PHYSICS_BODY_CHARACTER in modes and bool(
        modes & {PHYSICS_BODY_STATIC, PHYSICS_BODY_KINEMATIC})


def floor_helper_lines() -> list[str]:
    """Teste un contact final exact, sans refaire la resolution physique."""
    return [
        "static void __attribute__((unused)) actor_floor_test(Actor* a,u8 ab,Actor* s,u8 sb){",
        "    if(!g_actor_floor||g_actor_floor[a->inst]||!a->active||!s->active) return;",
        "    if(ab>=a->collision.box_count||sb>=s->collision.box_count||a->vy<0) return;",
        "    const CollisionShape* b=&a->collision.boxes[ab]; const CollisionShape* p=&s->collision.boxes[sb];",
        "    if(!b->active||!p->active) return;",
        "    int al=(a->x>>8)+b->x,ar=al+b->w,bottom=(a->y>>8)+b->y+b->h;",
        "    int pl=(s->x>>8)+p->x,pr=pl+p->w,top=(s->y>>8)+p->y;",
        "    if(bottom==top&&al<pr&&ar>pl) g_actor_floor[a->inst]=(u16)(s->inst+1);",
        "}",
        "/* Le même contact pour un côté d'appui `n` quelconque : 1 bas, 2 haut, 3 droite, 4 gauche. Le corps ne doit pas",
        "   s'éloigner de son appui (vitesse de sens contraire), comme `a->vy<0` ci-dessus pour le bas. */",
        "static void __attribute__((unused)) actor_floor_test_n(Actor* a,u8 ab,Actor* s,u8 sb,u8 n){",
        "    if(!g_actor_floor||g_actor_floor[a->inst]||!a->active||!s->active) return;",
        "    if(ab>=a->collision.box_count||sb>=s->collision.box_count) return;",
        "    const CollisionShape* b=&a->collision.boxes[ab]; const CollisionShape* p=&s->collision.boxes[sb];",
        "    if(!b->active||!p->active) return;",
        "    int al=(a->x>>8)+b->x,ar=al+b->w,at=(a->y>>8)+b->y,abt=at+b->h;",
        "    int pl=(s->x>>8)+p->x,pr=pl+p->w,pt=(s->y>>8)+p->y,pb=pt+p->h;",
        "    int hit;",
        "    if(n==1) hit=a->vy>=0&&abt==pt&&al<pr&&ar>pl;",
        "    else if(n==2) hit=a->vy<=0&&at==pb&&al<pr&&ar>pl;",
        "    else if(n==3) hit=a->vx>=0&&ar==pl&&at<pb&&abt>pt;",
        "    else hit=a->vx<=0&&al==pr&&at<pb&&abt>pt;",
        "    if(hit) g_actor_floor[a->inst]=(u16)(s->inst+1);",
        "}",
        "",
    ]


def floor_tick_lines(p, scene_actors, actor_offset: int, scene=None, pi=(), shown=None) -> list[str]:
    """Actualise le contact au sol apres toutes les corrections de position de la frame.

    Un CharacterBody repose sur un StaticBody ou un KinematicBody. Un RigidBody repose aussi sur un Character ou un
    autre Rigid : le solveur d'impulsions le laisse exactement au contact, sans produire lui-meme de contact au sol.

    Le corps et son appui peuvent etre poses ou nes dans le pool partage (`pi`, `shown`) : un corps du pool est parcouru
    avec les emplacements utilises, et ses appuis du pool sont ceux des emplacements de chaque modele. Le premier appui
    qui porte l'emporte, les appuis poses d'abord (comme l'ordre de la scene entre poses)."""
    n = support_normal(scene, p.settings) if scene is not None else ONEWAY_UP
    # Un script écrit `scene.gravity` : le côté d'appui se lit à l'exécution (`g_support_normal`). Une face à sens
    # unique de direction fixe ne compte alors que tant que le côté d'appui est le sien ; une face en mode `gravity`
    # garde la direction cuite au départ de la scène (ses blocages le sont aussi), donc reste un sol.
    dynamic = project_sets_gravity(p)
    pool = [(m["model_id"], m["prefab"], shown(p, m["prefab"])[1]) for m in shared_models(pi)] if shown else []

    def supports(owner, sprite) -> list[tuple[int, object, int, int, bool]]:
        """(rang de boite, boite, mode, garde, sens unique) de chaque face qui peut porter, ou rien."""
        mode = physics_body_mode(owner)
        if mode not in (PHYSICS_BODY_STATIC, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_CHARACTER, PHYSICS_BODY_RIGID):
            return []
        out = []
        for sb, box in physics_blocker_entries(owner, sprite):
            guard = 0
            face = ONEWAY_NONE
            if scene is not None:
                face = shape_one_way_dir(box, scene, p.settings)
                if dynamic and box.one_way not in (ONE_WAY_OFF, ONE_WAY_GRAVITY):
                    guard = face
                # Une face à sens unique ne porte que par sa face d'appui : les autres ne sont pas un sol.
                elif face not in (ONEWAY_NONE, n):
                    continue
            out.append((sb, box, mode, guard, face != ONEWAY_NONE))
        return out

    # Les appuis : (acteur posé ou None, modèle du pool ou None, rang, boîte, mode, garde).
    floors = [(actor_offset + si, None, sb, box, mode, guard, oneway)
              for si, (owner, sprite) in enumerate(scene_actors)
              for sb, box, mode, guard, oneway in supports(owner, sprite)]
    floors += [(None, model, sb, box, mode, guard, oneway)
               for model, owner, sprite in pool for sb, box, mode, guard, oneway in supports(owner, sprite)]

    def tests(body_ref: str, owner, sprite, body_actor: int | None, body_model: int | None, pad: str) -> list[str]:
        """Les tests de contact d'un corps (posé ou emplacement du pool) contre tous ses appuis possibles."""
        mode = physics_body_mode(owner)
        out = []
        for cb, box in physics_collider_entries(owner, sprite):
            for si, model, sb, floor, floor_mode, guard, oneway in floors:
                if ((si is not None and si == body_actor)
                        or not (mode == PHYSICS_BODY_RIGID or floor_mode in (PHYSICS_BODY_STATIC, PHYSICS_BODY_KINEMATIC))
                        or not tags_collide(p.settings, box.tag or "body", floor.tag or "body")):
                    continue
                inner = pad + ("" if si is not None else "    ")
                if dynamic:
                    call = f"actor_floor_test_n({body_ref},{cb},%s,{sb},g_support_normal);"
                    call = f"if(g_support_normal=={guard}) {call}" if guard else call
                elif n == ONEWAY_UP:
                    call = f"actor_floor_test({body_ref},{cb},%s,{sb});"
                else:
                    call = f"actor_floor_test_n({body_ref},{cb},%s,{sb},{n});"
                if oneway:      # `drop_through` : un corps qui descend à travers les faces à sens unique n'y repose plus
                    call = f"if(!(g_drop_through&&g_drop_through[({body_ref})->inst])) {call}"
                if si is not None:
                    out.append(f"{pad}" + call % f"&g_actors[{si}]")
                else:      # un appui du pool : chaque emplacement utilisé de son modèle
                    out += [f"{pad}POOL_EACH(_fs){{",
                            f"{inner}if(g_actors[_fs].model!={model}{'||_fs==_fp' if model == body_model else ''}) continue;",
                            f"{inner}" + call % "&g_actors[_fs]",
                            f"{pad}}}"]
        return out

    lines: list[str] = []
    for ci, (owner, sprite) in enumerate(scene_actors):
        if physics_body_mode(owner) not in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_RIGID):
            continue
        idx = actor_offset + ci
        lines.append(f"    g_actor_floor[{idx}]=0;")
        lines += tests(f"&g_actors[{idx}]", owner, sprite, idx, None, "    ")
    cases = []
    for model, owner, sprite in pool:
        if physics_body_mode(owner) not in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_RIGID):
            continue
        cases += [f"        case {model}: {{", "            g_actor_floor[_fp]=0;",
                  *tests("_a", owner, sprite, None, model, "            "), "        } break;"]
    if cases:
        lines += ["    POOL_EACH(_fp){", "        Actor* _a=&g_actors[_fp];", "        switch(_a->model){", *cases,
                  "        default: break;", "        }", "    }"]
    if lines:
        lines.insert(0, "    /* Contact au sol final des CharacterBody et RigidBody sur les corps poses ou nes dans le pool */")
    return lines
