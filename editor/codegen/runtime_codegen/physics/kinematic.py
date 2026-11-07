"""Transport des corps poses sur un KinematicBody place dans la scene."""
from __future__ import annotations

from core.models.components import (
    COLLISION_RESPONSE_BLOCK,
    PHYSICS_BODY_CHARACTER,
    PHYSICS_BODY_KINEMATIC,
    PHYSICS_BODY_RIGID,
    PHYSICS_BODY_STATIC,
)
from core.models.settings import tags_collide
from core.models.collision_tiles import ONEWAY_UP
from codegen.runtime_codegen.physics.body import (
    physics_body_mode, physics_collider_entries, project_sets_gravity, support_normal,
)
from codegen.runtime_codegen.shared_pool_gen import shared_models


def project_has_kinematic(p) -> bool:
    owners = [actor for scene in getattr(p, "scenes", []) or [] for actor in scene.actors]
    owners += list(getattr(p, "prefabs", []) or [])
    return any(physics_body_mode(owner) == PHYSICS_BODY_KINEMATIC for owner in owners)


def kinematic_helper_lines() -> list[str]:
    """Aide C : applique une seule fois le déplacement réel de la plateforme au passager."""
    return [
        "static void __attribute__((unused)) kinematic_carry(Actor* k,Actor* a,u8 kb,u8 ab,",
        "        int old_x,int old_y,u8* carried,int* carry_x,int* carry_y){",
        "    if(*carried||!k->active||!a->active||kb>=k->collision.box_count||ab>=a->collision.box_count) return;",
        "    const CollisionShape* p=&k->collision.boxes[kb]; const CollisionShape* b=&a->collision.boxes[ab];",
        "    if(!p->active||!b->active) return;",
        "    int dx=k->x-old_x,dy=k->y-old_y; if(!dx&&!dy) return;",
        "    int pl=(old_x>>8)+p->x,pr=pl+p->w,pt=(old_y>>8)+p->y;",
        "    int al=(a->x>>8)+b->x,ar=al+b->w,abottom=(a->y>>8)+b->y+b->h;",
        "    if(abottom!=pt||al>=pr||ar<=pl||a->vy<0) return;",
        "    a->x+=dx; a->y+=dy; *carry_x+=dx; *carry_y+=dy; *carried=1;",
        "}",
        "/* Le même transport pour un côté d'appui `n` quelconque (1 bas, 2 haut, 3 droite, 4 gauche) : le passager repose",
        "   sur la face de la plateforme qui regarde la gravité, telle qu'elle était AVANT son déplacement, et ne s'en",
        "   éloigne pas (vitesse de sens contraire). `kinematic_carry` ci-dessus reste le cas du bas. */",
        "static void __attribute__((unused)) kinematic_carry_n(Actor* k,Actor* a,u8 kb,u8 ab,",
        "        int old_x,int old_y,u8* carried,int* carry_x,int* carry_y,u8 n){",
        "    if(*carried||!k->active||!a->active||kb>=k->collision.box_count||ab>=a->collision.box_count) return;",
        "    const CollisionShape* p=&k->collision.boxes[kb]; const CollisionShape* b=&a->collision.boxes[ab];",
        "    if(!p->active||!b->active) return;",
        "    int dx=k->x-old_x,dy=k->y-old_y; if(!dx&&!dy) return;",
        "    int pl=(old_x>>8)+p->x,pr=pl+p->w,pt=(old_y>>8)+p->y,pb=pt+p->h;",
        "    int al=(a->x>>8)+b->x,ar=al+b->w,at=(a->y>>8)+b->y,abt=at+b->h;",
        "    int rests;",
        "    if(n==1) rests=abt==pt&&al<pr&&ar>pl&&a->vy>=0;",
        "    else if(n==2) rests=at==pb&&al<pr&&ar>pl&&a->vy<=0;",
        "    else if(n==3) rests=ar==pl&&at<pb&&abt>pt&&a->vx>=0;",
        "    else rests=al==pr&&at<pb&&abt>pt&&a->vx<=0;",
        "    if(!rests) return;",
        "    a->x+=dx; a->y+=dy; *carry_x+=dx; *carry_y+=dy; *carried=1;",
        "}",
        "",
    ]


def _block_boxes(owner, sprite) -> list[tuple[int, object]]:
    return [(rank, box) for rank, box in physics_collider_entries(owner, sprite)
            if box.active
            and box.response == COLLISION_RESPONSE_BLOCK]


def _body_boxes(owner, sprite) -> list[tuple[int, object]]:
    return [(rank, box) for rank, box in physics_collider_entries(owner, sprite)
            if box.active]


def _carry_pairs(p, kinematic, kinematic_sprite, target, target_sprite) -> list[tuple[int, int]]:
    """Les couples (rang de la boîte de la plateforme, rang de celle du passager) qui peuvent se porter."""
    if physics_body_mode(target) not in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_RIGID):
        return []
    return [(kb, ab) for kb, kbox in _block_boxes(kinematic, kinematic_sprite)
            for ab, abox in _body_boxes(target, target_sprite)
            if tags_collide(p.settings, kbox.tag or "body", abox.tag or "body")]


def _carry_groups(p, scene_actors, actor_offset: int, pi, shown):
    """Qui porte qui : (posé/posé, posé/pool, pool/posé, pool/pool). Un modèle du pool est désigné par son identité
    (`model_id`) : ses emplacements ne sont connus qu'à l'exécution.

    Clés : (acteur plateforme, acteur passager), (acteur plateforme, modèle passager), (modèle plateforme, acteur
    passager), (modèle plateforme, modèle passager) ; valeur : les couples de boîtes."""
    placed = [(i, owner, sprite) for i, (owner, sprite) in enumerate(scene_actors)]
    pool = [(m["model_id"], m["prefab"], shown(p, m["prefab"])[1]) for m in shared_models(pi)] if shown else []
    is_k = lambda owner: physics_body_mode(owner) == PHYSICS_BODY_KINEMATIC
    pp: dict = {}
    for ki, kinematic, ks in placed:
        if not is_k(kinematic):
            continue
        for ti, target, ts in placed:
            if ti != ki and (pairs := _carry_pairs(p, kinematic, ks, target, ts)):
                pp[(actor_offset + ki, actor_offset + ti)] = pairs
    pool_passenger: dict = {}
    pool_platform_placed: dict = {}
    pool_platform_pool: dict = {}
    for ki, kinematic, ks in placed:
        if is_k(kinematic):
            for mid, target, ts in pool:
                if pairs := _carry_pairs(p, kinematic, ks, target, ts):
                    pool_passenger[(actor_offset + ki, mid)] = pairs
    for mk, kinematic, ks in pool:
        if not is_k(kinematic):
            continue
        for ti, target, ts in placed:
            if pairs := _carry_pairs(p, kinematic, ks, target, ts):
                pool_platform_placed[(mk, actor_offset + ti)] = pairs
        for mt, target, ts in pool:
            if mt != mk and (pairs := _carry_pairs(p, kinematic, ks, target, ts)):
                pool_platform_pool[(mk, mt)] = pairs
    return pp, pool_passenger, pool_platform_placed, pool_platform_pool


def kinematic_tick_parts(
        p, scene_actors, actor_offset: int, scene=None, pi=(), shown=None,
) -> tuple[list[str], list[str], list[int]]:
    """Instantanés avant mouvement, transport après résolution, puis les passagers posés.

    Le passager repose sur la face de la plateforme qui regarde la gravité de la scène (`support_normal`) : le dessus
    sous la gravité habituelle, le dessous sous une gravité vers le haut, un côté sous une gravité latérale.

    Plateformes et passagers peuvent être posés ou nés dans le pool partagé (`pi`, `shown`). Le déplacement porté vit
    dans `_kin_d`, une ligne par emplacement de `g_actors` (x, y, puis l'écrasement déjà signalé), remise à zéro à chaque
    image pour les posés et les emplacements utilisés du pool : la résolution contre la carte l'ajoute à la vitesse de
    l'emplacement, quel qu'il soit (`physics.character.body_tile_step`)."""
    normal = support_normal(scene, p.settings) if scene is not None else ONEWAY_UP
    # Un script écrit `scene.gravity` : le côté d'appui se lit à l'exécution, quel que soit celui du départ.
    dynamic = project_sets_gravity(p)
    groups, pool_passenger, pool_platform_placed, pool_platform_pool = _carry_groups(
        p, scene_actors, actor_offset, pi, shown)
    if not (groups or pool_passenger or pool_platform_placed or pool_platform_pool):
        return [], [], []

    def carry(platform: str, passenger: str, kb: int, ab: int, old_x: str, old_y: str, carried: str,
              dx: str, dy: str) -> str:
        tail = f"{old_x},{old_y},{carried},{dx},{dy}"
        if normal == ONEWAY_UP and not dynamic:
            return f"kinematic_carry({platform},{passenger},{kb},{ab},{tail});"
        return f"kinematic_carry_n({platform},{passenger},{kb},{ab},{tail},{'g_support_normal' if dynamic else normal});"

    spool = shared_models(pi)[0]["spool"] if (pool_passenger or pool_platform_placed or pool_platform_pool) else None
    size = spool["end"] - spool["start"] if spool else 0
    kinematic_indices = sorted({ki for ki, _ in groups} | {ki for ki, _ in pool_passenger})
    target_indices = sorted({ti for _, ti in groups} | {ti for _, ti in pool_platform_placed})
    pool_platforms = sorted({mk for mk, _ in pool_platform_placed} | {mk for mk, _ in pool_platform_pool})
    before = [line for ki in kinematic_indices for line in (
        f"    int _kin_old_x_{ki}=g_actors[{ki}].x;",
        f"    int _kin_old_y_{ki}=g_actors[{ki}].y;",
    )]
    if pool_platforms:
        before += [f"    static int _kin_po[{size}][2] EWRAM_BSS;       /* position d'avant mouvement des plateformes du pool */",
                   "    POOL_EACH(_kk){",
                   "        switch(g_actors[_kk].model){",
                   *[f"        case {mk}:" for mk in pool_platforms],
                   "            _kin_po[_kk-g_spool_start][0]=g_actors[_kk].x; _kin_po[_kk-g_spool_start][1]=g_actors[_kk].y; break;",
                   "        default: break;",
                   "        }",
                   "    }"]
    after = ["    static int _kin_d[G_ACTOR_COUNT][3] EWRAM_BSS;   /* déplacement porté et écrasement, par emplacement */"]
    if scene_actors:
        after.append(f"    for(int _kz={actor_offset};_kz<{actor_offset + len(scene_actors)};_kz++) "
                     "_kin_d[_kz][0]=_kin_d[_kz][1]=_kin_d[_kz][2]=0;")
    if spool:
        after.append("    for(int _kz=g_spool_start;_kz<g_spool_hw;_kz++) _kin_d[_kz][0]=_kin_d[_kz][1]=_kin_d[_kz][2]=0;")
    for (ki, ti), pairs in groups.items():
        carried = f"_kin_carried_{ki}_{ti}"
        after.append(f"    u8 {carried}=0;")
        for kb, ab in pairs:
            after.append("    " + carry(f"&g_actors[{ki}]", f"&g_actors[{ti}]", kb, ab, f"_kin_old_x_{ki}",
                                         f"_kin_old_y_{ki}", f"&{carried}", f"&_kin_d[{ti}][0]", f"&_kin_d[{ti}][1]"))
    for (ki, mid), pairs in pool_passenger.items():
        after += ["    POOL_EACH(_ps){",
                  f"        if(g_actors[_ps].model!={mid}) continue;",
                  "        u8 _pc=0; int* _pd=_kin_d[_ps];",
                  *["        " + carry(f"&g_actors[{ki}]", "&g_actors[_ps]", kb, ab, f"_kin_old_x_{ki}",
                                       f"_kin_old_y_{ki}", "&_pc", "&_pd[0]", "&_pd[1]") for kb, ab in pairs],
                  "    }"]
    for (mk, ti), pairs in pool_platform_placed.items():
        after += ["    POOL_EACH(_ks){",
                  f"        if(g_actors[_ks].model!={mk}) continue;",
                  "        u8 _kc=0; int* _po=_kin_po[_ks-g_spool_start];",
                  *["        " + carry("&g_actors[_ks]", f"&g_actors[{ti}]", kb, ab, "_po[0]", "_po[1]", "&_kc",
                                       f"&_kin_d[{ti}][0]", f"&_kin_d[{ti}][1]") for kb, ab in pairs],
                  "    }"]
    for (mk, mt), pairs in pool_platform_pool.items():
        after += ["    POOL_EACH(_ks){",
                  f"        if(g_actors[_ks].model!={mk}) continue;",
                  "        int* _po=_kin_po[_ks-g_spool_start];",
                  "        POOL_EACH(_ps){",
                  f"            if(g_actors[_ps].model!={mt}) continue;",
                  "            u8 _kc=0; int* _pd=_kin_d[_ps];",
                  *["            " + carry("&g_actors[_ks]", "&g_actors[_ps]", kb, ab, "_po[0]", "_po[1]", "&_kc",
                                           "&_pd[0]", "&_pd[1]") for kb, ab in pairs],
                  "        }",
                  "    }"]
    return before, after, target_indices


def kinematic_crush_pairs(p, scene_actors, actor_offset: int) -> dict[int, list[tuple[int, int, int]]]:
    """Les StaticBody qui peuvent coincer un Character transporte."""
    statics = []
    for si, (owner, sprite) in enumerate(scene_actors):
        if physics_body_mode(owner) == PHYSICS_BODY_STATIC:
            statics.extend((actor_offset + si, sb, box)
                           for sb, box in _block_boxes(owner, sprite))

    pairs: dict[int, list[tuple[int, int, int]]] = {}
    for ci, (character, sprite) in enumerate(scene_actors):
        if physics_body_mode(character) != PHYSICS_BODY_CHARACTER:
            continue
        for cb, cbox in _body_boxes(character, sprite):
            for si, sb, sbox in statics:
                if tags_collide(p.settings, cbox.tag or "body", sbox.tag or "body"):
                    pairs.setdefault(actor_offset + ci, []).append((cb, si, sb))
    return pairs
