"""Le blocage entre acteurs : le C réel de `actors_resolve_blocks`, compilé et exécuté, puis ce que le
générateur émet (tables filtrées par la matrice de collision, pools)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.models.components import CollisionShapeComponent
from core.models.scene import Actor
from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#include "gba_debug.h"
#define BS_ATTR_IWRAM __attribute__((noinline))   /* hors GBA : fonction ordinaire (cf. runtime_api_inline.h) */
#define EWRAM_BSS                                 /* hors GBA : mémoire ordinaire */
u8 g_support_normal = 1;
Actor g_actors[8];
int g_spool_start = 0, g_actor_slot_end = 0, g_scene_placed = 0;
u32 g_alive_bits[1];
u32 g_alive_epoch;
PoolCursor g_nth;
%(helpers)s

/* Un acteur actif en (x, y) pixels, vitesse (vx, vy), une boîte (w x h) en (0, 0). */
static void mk(int i, int x, int y, int vx, int vy, int w, int h, int solid){
    Actor* a = &g_actors[i];
    *a = (Actor){0};
    a->active = 1; a->x = x << 8; a->y = y << 8; a->vx = vx; a->vy = vy;
    a->collision.box_count = 1;
    CollisionShape* b = &a->collision.boxes[0];
    b->w = w; b->h = h; b->solid = solid; b->active = 1;
}
static void report(const char* nom, int i){
    printf("%%s %%d %%d\n", nom, g_actors[i].x >> 8, g_actors[i].y >> 8);
}
static void report_motion(const char* nom, int i){
    printf("%%s %%d %%d %%d %%d\n", nom, g_actors[i].x >> 8, g_actors[i].y >> 8,
           g_actors[i].vx, g_actors[i].vy);
}

/* Le mobile est du type 1, les bloqueurs du type 2 (rang compact 0, boîte 0) ; le type 7 bloque aussi (rang compact 1),
   le type 9 ne bloque pas. Une seule ligne de mobile : `run[0]`. */
static const u8 bi[10] = {255, 255, 0, 255, 255, 255, 255, 1, 255, 255};
static const PairRun run[1][2] = {{{0, 1}, {0, 1}}};
static const u8 box[1] = {0};
/* La scène du cas : `hi` posés, et le pool (emplacements 3 et plus, jusqu'à `g_actor_slot_end`) si `pool` ; sans pool, le
   parcours s'arrête au dernier posé, comme dans une scène sans pool (`scene_init`). */
static void bloque(int i, u8 mask, int hi, int pool){
    g_scene_placed = hi; if(!pool) g_actor_slot_end = hi; BlockTarget list[8]; int n = block_targets(bi, list);
    actors_resolve_blocks(&g_actors[i], mask, run[0], list, n, box);
}

int main(void){
    /* le bloqueur : 16x16 en (50, 50) ; le mobile 16x16 */
    mk(1, 50, 50, 0, 0, 16, 16, 0); mk(2, 200, 200, 0, 0, 16, 16, 0);
    g_actors[1].type_id = 2; g_actors[2].type_id = 2;

    mk(0, 40, 52, 256, 0, 16, 16, 1);                          /* vient de la gauche : 6 px dedans */
    bloque(0, 1, 3, 0);  report("gauche", 0);
    mk(0, 60, 52, -256, 0, 16, 16, 1);                         /* vient de la droite : 6 px dedans */
    bloque(0, 1, 3, 0);  report("droite", 0);
    mk(0, 52, 40, 0, 256, 16, 16, 1);                          /* vient du haut */
    bloque(0, 1, 3, 0);  report("haut", 0);
    report_motion("character_stop", 0);
    mk(0, 52, 60, 0, -256, 16, 16, 1);                         /* vient du bas */
    bloque(0, 1, 3, 0);  report("bas", 0);
    mk(0, 38, 40, 256, 256, 16, 16, 1);                        /* coin : 4 px en x, 6 px en y -> glisse en x */
    bloque(0, 1, 3, 0);  report("coin", 0);

    mk(0, 40, 52, 0, 0, 16, 16, 1);                            /* sans vitesse : téléporté, laissé */
    bloque(0, 1, 3, 0);  report("immobile", 0);
    mk(0, 40, 52, 256, 0, 16, 16, 0);                          /* sans forme de corps : laissé */
    bloque(0, 0, 3, 0);  report("non_solide", 0);
    mk(0, 10, 10, 256, 0, 16, 16, 1);                          /* loin : laissé */
    bloque(0, 1, 3, 0);  report("loin", 0);

    mk(0, 40, 52, 256, 0, 16, 16, 1); g_actors[1].active = 0;  /* bloqueur inactif : traversé */
    bloque(0, 1, 3, 0);  report("inactif", 0);
    g_actors[1].active = 1; g_actors[1].collision.boxes[0].active = 0;   /* boîte inactive : traversée */
    mk(0, 40, 52, 256, 0, 16, 16, 1);
    bloque(0, 1, 3, 0);  report("boite_inactive", 0);
    g_actors[1].collision.boxes[0].active = 1;

    mk(0, 40, 52, 256, 0, 16, 16, 1); g_actors[0].x += 128;    /* la fraction (1/2 px) survit */
    bloque(0, 1, 3, 0);
    printf("fraction %%d\n", g_actors[0].x & 255);

    /* un acteur ne se bloque pas lui-même : le mobile est ici du type bloqueur, seul dans les posés */
    mk(0, 40, 52, 256, 0, 16, 16, 1); g_actors[0].type_id = 2;
    bloque(0, 1, 1, 0);  report("soi_meme", 0);

    {   /* Le pool PARTAGÉ : un bloqueur né à l'emplacement 3 (type 7, boîte 0), un autre type à l'emplacement 4. Les
           bloqueurs posés sont désactivés : seul le pool bloque (un parcours voit tous les emplacements actifs). */
        g_actors[1].active = 0; g_actors[2].active = 0;
        mk(3, 50, 50, 0, 0, 16, 16, 0); g_actors[3].type_id = 7;
        mk(4, 50, 50, 0, 0, 16, 16, 0); g_actors[4].type_id = 9;     /* un autre type : traversé */
        g_spool_start = 3; g_actor_slot_end = 5;
        alive_bit_set(3); alive_bit_set(4);
        mk(0, 40, 52, 256, 0, 16, 16, 1);
        bloque(0, 1, 0, 1);   report("pool_gauche", 0);
        mk(0, 40, 52, 256, 0, 16, 16, 1); g_actors[3].type_id = 9;
        bloque(0, 1, 0, 1);   report("pool_autre_modele", 0);
        g_actors[3].type_id = 7; g_actors[3].active = 0;
        mk(0, 40, 52, 256, 0, 16, 16, 1);
        bloque(0, 1, 0, 1);   report("pool_inactif", 0);
        g_actors[3].active = 1; g_actor_slot_end = 3;
        mk(0, 40, 52, 256, 0, 16, 16, 1);
        bloque(0, 1, 0, 1);   report("pool_hors_hw", 0);
        g_actor_slot_end = 5;
        mk(3, 40, 52, 0, 0, 16, 16, 1); g_actors[3].type_id = 7; g_actors[3].vx = 256;   /* un bloqueur ne se bloque pas lui-même */
        bloque(3, 1, 0, 1);   report("pool_soi_meme", 3);
        /* posés et pool à la fois : le posé de type 2 en (50, 50) arrête le mobile avant le pool */
        g_actors[4].active = 0; g_actors[1].active = 1;
        mk(3, 50, 50, 0, 0, 16, 16, 0); g_actors[3].type_id = 7;
        mk(0, 40, 52, 256, 0, 16, 16, 1);
        bloque(0, 1, 3, 1);   report("pose_puis_pool", 0);
    }

    {   /* Rigid au-dessus d'un Static : toute la correction et l'impulsion vont au Rigid. */
        mk(0, 50, 40, 0, 256, 16, 16, 1);
        mk(1, 50, 50, 0, 0, 16, 16, 0);
        rigid_contact(&g_actors[0], &g_actors[1], 0, 0, 256, 0, 0, 0);
        report_motion("rigid_static", 0);
    }

    {   /* Deux Rigid de même masse partagent correction et vitesse normale. */
        mk(0, 50, 40, 0, 256, 16, 16, 1);
        mk(1, 50, 50, 0, 0, 16, 16, 1);
        rigid_contact(&g_actors[0], &g_actors[1], 0, 0, 256, 256, 0, 0);
        report_motion("rigid_rigid_a", 0);
        report_motion("rigid_rigid_b", 1);
    }

    {   /* Le corps deux fois plus lourd ne prend qu'un tiers de la correction. */
        mk(0, 50, 40, 0, 256, 16, 16, 1);
        mk(1, 50, 50, 0, 0, 16, 16, 1);
        rigid_contact(&g_actors[0], &g_actors[1], 0, 0, 256, 128, 0, 0);
        report_motion("rigid_mass_light", 0);
        report_motion("rigid_mass_heavy", 1);
    }

    {   /* Une restitution maximale inverse la vitesse normale du Rigid. */
        mk(0, 50, 40, 0, 256, 16, 16, 1);
        mk(1, 50, 50, 0, 0, 16, 16, 0);
        rigid_contact(&g_actors[0], &g_actors[1], 0, 0, 256, 0, 256, 0);
        report_motion("rigid_bounce", 0);
    }

    {   /* Une friction maximale arrête la vitesse tangentielle contre un Static. */
        mk(0, 50, 40, 256, 0, 16, 16, 1);
        mk(1, 50, 50, 0, 0, 16, 16, 0);
        rigid_contact(&g_actors[0], &g_actors[1], 0, 0, 256, 0, 0, 256);
        report_motion("rigid_friction", 0);
    }


    {   /* Une plateforme déplace une seule fois le corps posé sur son ancienne face supérieure. */
        int carry_x=0, carry_y=0; u8 carried=0;
        mk(0, 52, 50, 512, 0, 16, 16, 0);
        mk(1, 54, 34, 0, 0, 8, 16, 1);
        kinematic_carry_n(&g_actors[0], &g_actors[1], 0, 0, 50<<8, 50<<8,
                        &carried, &carry_x, &carry_y, 1);
        report("kinematic_rider", 1);
        printf("kinematic_delta %%d %%d %%d\n", carry_x, carry_y, carried);

        carry_x=carry_y=0; carried=0;
        mk(1, 54, 34, 0, -256, 8, 16, 1);
        kinematic_carry_n(&g_actors[0], &g_actors[1], 0, 0, 50<<8, 50<<8,
                        &carried, &carry_x, &carry_y, 1);
        report("kinematic_jump", 1);

        carry_x=carry_y=0; carried=0;
        mk(0, 50, 52, 0, 512, 16, 16, 0);
        mk(1, 54, 34, 0, 0, 8, 16, 1);
        kinematic_carry_n(&g_actors[0], &g_actors[1], 0, 0, 50<<8, 50<<8,
                        &carried, &carry_x, &carry_y, 1);
        report("kinematic_rider_vertical", 1);
    }
    return 0;
}
"""


@pytest.fixture(scope="module")
def resultats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; le blocage est vérifié en CI")
    from codegen.runtime_codegen.physics.blocks import block_helper_lines
    from codegen.runtime_codegen.physics.impulses import impulse_helper_lines
    from codegen.runtime_codegen.physics.kinematic import kinematic_helper_lines
    dossier = tmp_path_factory.mktemp("block")
    helpers = block_helper_lines() + impulse_helper_lines() + kinematic_helper_lines()
    (dossier / "probe.c").write_text(SONDE % {"helpers": "\n".join(helpers)}, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    lignes = subprocess.run([str(binaire)], capture_output=True, text=True,
                            env=environnement(compilateur)).stdout.strip().splitlines()
    return {ligne.split()[0]: tuple(int(v) for v in ligne.split()[1:]) for ligne in lignes}


def test_un_mobile_est_repousse_hors_de_la_boite_par_l_axe_le_plus_court(resultats):
    assert resultats["gauche"] == (34, 52)       # bloqueur à x=50 : le mobile finit à 50 - 16
    assert resultats["droite"] == (66, 52)       # 50 + 16
    assert resultats["haut"] == (52, 34)
    assert resultats["bas"] == (52, 66)


def test_un_character_annule_sa_vitesse_sur_la_normale_bloquee(resultats):
    assert resultats["character_stop"] == (52, 34, 0, 0)


def test_en_diagonale_le_mobile_glisse_le_long_de_l_obstacle(resultats):
    assert resultats["coin"] == (34, 40)         # 4 px en x < 6 px en y : poussé en x, y intact


def test_ni_immobile_ni_sans_boite_solide_ni_loin_n_est_touche(resultats):
    assert resultats["immobile"] == (40, 52)
    assert resultats["non_solide"] == (40, 52)
    assert resultats["loin"] == (10, 10)


def test_un_bloqueur_inactif_ou_sa_boite_inactive_se_traverse(resultats):
    assert resultats["inactif"] == (40, 52)
    assert resultats["boite_inactive"] == (40, 52)


def test_la_fraction_de_la_position_survit_et_on_ne_se_bloque_pas_soi_meme(resultats):
    assert resultats["fraction"] == (128,)
    assert resultats["soi_meme"] == (40, 52)


def test_un_rigid_s_arrete_sur_un_static_et_deux_rigid_partagent_l_impulsion(resultats):
    assert resultats["rigid_static"] == (50, 34, 0, 0)
    assert resultats["rigid_rigid_a"] == (50, 37, 0, 128)
    assert resultats["rigid_rigid_b"] == (50, 53, 0, 128)


def test_la_masse_repartit_la_correction_sans_changer_la_vitesse_commune(resultats):
    assert resultats["rigid_mass_light"] == (50, 36, 0, 86)
    assert resultats["rigid_mass_heavy"] == (50, 52, 0, 86)


def test_restitution_et_friction_modifient_la_vitesse_du_contact(resultats):
    assert resultats["rigid_bounce"] == (50, 34, 0, -256)
    assert resultats["rigid_friction"] == (50, 34, 0, 0)


def test_un_kinematic_transporte_un_corps_pose_mais_pas_un_corps_qui_saute(resultats):
    assert resultats["kinematic_rider"] == (56, 34)
    assert resultats["kinematic_delta"] == (512, 0, 1)
    assert resultats["kinematic_jump"] == (54, 34)
    assert resultats["kinematic_rider_vertical"] == (54, 36)


# ── Ce que le générateur émet ─────────────────────────────────────────

def _scene(*acteurs):
    return [(a, None) for a in acteurs]


def _acteur(nom, restitution=None, friction=None, **boite):
    a = Actor(name=nom)
    a.components = [CollisionShapeComponent(id="b", **boite)]
    if restitution is not None or friction is not None:
        from core.models.components import PhysicMaterialComponent
        a.components.append(PhysicMaterialComponent(id="m", restitution=restitution or 0.0, friction=friction or 0.0))
        a.components[0].material_id = "m"
    return a


def _projet(paires_desactivees=()):
    return SimpleNamespace(settings=SimpleNamespace(collision_disabled_pairs=list(paires_desactivees),
                                                    collision_tags=[]))


@pytest.fixture
def lignes(tmp_path):
    """`lignes(acteurs, paires_desactivees)` : la passe de blocage émise pour une vraie scène de ces acteurs posés."""
    def emet(acteurs, paires_desactivees=()):
        from codegen.runtime_codegen.physics.blocks import block_tick_lines
        from core.models.scene import Scene
        from core.project import Project
        scene = Scene(name="S", actors=list(acteurs), physics_enabled=True)
        p = Project(tmp_path)
        p.scenes.items = [scene]
        p.settings.collision_disabled_pairs = list(paires_desactivees)
        return block_tick_lines(p, scene, _scene(*acteurs), [], lambda _p, _o: (None, None))
    return emet


def _tables(lignes) -> dict[str, list[int]]:
    """Les tables `_bk_*` émises, à plat."""
    import re
    out = {}
    for ligne in lignes:
        if m := re.search(r"static \w+ (_bk_\w+)(?:\[\d+\])+[^=]*=\{(.*)\};", ligne):
            out[m[1]] = [int(v) for v in re.findall(r"\d+", m[2])]
    return out


def _rencontres(lignes) -> dict[int, tuple[int, dict[int, list[int]]]]:
    """Par type mobile : (masque de corps, {type bloqueur : rangs des boîtes qui l'arrêtent}), lu dans les tables."""
    t = _tables(lignes)
    nb = sum(1 for j in t["_bk_bi"] if j != 255)
    out = {}
    for kind, i in enumerate(t["_bk_mi"]):
        if i == 255:
            continue
        row = t["_bk_run"][2 * nb * i: 2 * nb * (i + 1)]
        out[kind] = (t["_bk_mask"][i], {b: t["_bk_box"][row[2 * j]: row[2 * j] + row[2 * j + 1]]
                                        for b, j in enumerate(t["_bk_bi"]) if j != 255 and row[2 * j + 1]})
    return out


def test_le_mobile_recoit_la_table_des_boites_bloquantes(lignes):
    hero = _acteur("Hero", tag="Player")
    coffre = _acteur("Chest", tag="body", response="block", solid=False)
    emis = lignes([hero, coffre])
    # Types 1 (Hero) et 2 (Chest) : le coffre n'a pas de boîte solide, il n'est pas un mobile.
    assert _rencontres(emis) == {1: (1, {2: [0]})}
    assert any("actors_resolve_blocks(_a,_bk_mask[_mi],_bk_run[_mi],_bk_list,_bk_n,_bk_box);" in l for l in emis)
    assert any("_bk_n=block_targets(_bk_bi,_bk_list);" in l for l in emis)


def test_un_static_body_bloque_sans_devenir_un_mobile(lignes):
    from core.models.components import PhysicsBodyComponent
    hero = _acteur("Hero", tag="Player")
    mur = _acteur("Wall", tag="body", response="block", solid=False)
    mur.components.append(PhysicsBodyComponent(mode="StaticBody"))
    assert _rencontres(lignes([hero, mur])) == {1: (1, {2: [0]})}


@pytest.fixture
def impulsions(tmp_path):
    """`impulsions(acteurs, **scène)` : la passe d'impulsions émise pour une vraie scène de ces acteurs posés (types 1, 2,
    ... dans l'ordre), lue dans ses tables : {"code", "masses" par type, "couples" par couple ordonné de types}."""
    import re

    def emet(acteurs, **scene_kw):
        from codegen.runtime_codegen.physics.impulses import impulse_tick_lines
        from core.models.scene import Scene
        from core.project import Project
        scene = Scene(name="Physics", actors=list(acteurs), physics_enabled=True, **scene_kw)
        p = Project(tmp_path)
        p.scenes.items = [scene]
        code = "\n".join(impulse_tick_lines(p, scene, _scene(*acteurs), [], None))
        table = lambda nom: [int(v) for v in re.findall(r"\d+", re.search(rf"{nom}(?:\[\d+\])+[^=]*=\{{(.*)\}};", code)[1])]
        ki, masses, runs, pairs = table("_ri_ki"), table("_ri_mass"), table("_ri_run"), table("_ri_pair")
        corps = {k: i for k, i in enumerate(ki) if i != 255}
        n = len(corps)
        couples = {}
        for a, i in corps.items():
            for b, j in corps.items():
                first, count = runs[2 * (i * n + j)], runs[2 * (i * n + j) + 1]
                if count:
                    couples[(a, b)] = [tuple(pairs[4 * q: 4 * q + 4]) for q in range(first, first + count)]
        return {"code": code, "masses": {k: masses[i] for k, i in corps.items()}, "couples": couples}
    return emet


def test_un_rigid_pose_passe_par_la_table_d_impulsions_et_non_le_blocage_historique(lignes, impulsions):
    from core.models.components import PhysicsBodyComponent
    rigid = _acteur("Crate", tag="body", response="block")
    rigid.components.append(PhysicsBodyComponent(mode="RigidBody"))
    sol = _acteur("Floor", tag="body", response="block", solid=False)
    sol.components.append(PhysicsBodyComponent(mode="StaticBody"))

    assert lignes([rigid, sol]) == []
    emis = impulsions([rigid, sol])
    # Types 1 (Crate) et 2 (Floor) : un couple de boîtes (0, 0), sans matériau, entre la caisse et le sol comme entre deux
    # caisses du même type ; 4 passes, sommeil après 30 images.
    assert emis["couples"] == {(1, 1): [(0, 0, 0, 0)], (1, 2): [(0, 0, 0, 0)], (2, 1): [(0, 0, 0, 0)]}
    assert emis["masses"] == {1: 256, 2: 0}
    assert "_ri_live,1,4,30);" in emis["code"]

    six_passes = impulsions([rigid, sol], physics_gravity_override=True, physics_solver_iterations=6)
    assert "_ri_live,1,6," in six_passes["code"]


def test_beaucoup_de_paires_rigid_passent_par_l_instantane_et_la_liste_des_paires_retenues(impulsions):
    from core.models.components import PhysicsBodyComponent
    crates = []
    for i in range(24):                 # 24 Rigid : 276 paires de corps, au-delà de ce qu'un compteur u8 peut parcourir
        crate = _acteur(f"Crate{i}", tag="body", response="block")
        crate.components.append(PhysicsBodyComponent(mode="RigidBody"))
        crates.append(crate)
    code = impulsions(crates)["code"]
    # Un instantané d'un corps par emplacement, une liste des paires retenues par la première passe (indices 32 bits).
    assert "static RigidBody _ri_list[24];" in code
    assert "static u32 _ri_live[276] EWRAM_BSS;" in code
    assert code.count("rigid_solve(") == 1


def test_la_table_encode_la_masse_inverse_de_chaque_rigid(impulsions):
    from core.models.components import PhysicsBodyComponent
    light = _acteur("Light", tag="body", response="block")
    light.components.append(PhysicsBodyComponent(mode="RigidBody", mass=0.5))
    heavy = _acteur("Heavy", tag="body", response="block")
    heavy.components.append(PhysicsBodyComponent(mode="RigidBody", mass=2.0))

    assert impulsions([light, heavy])["masses"] == {1: 512, 2: 128}


def test_la_table_cuit_les_materiaux_du_contact(impulsions):
    from core.models.components import PhysicsBodyComponent
    rigid = _acteur("Ball", tag="body", response="block", restitution=0.25, friction=0.25)
    rigid.components.append(PhysicsBodyComponent(mode="RigidBody"))
    wall = _acteur("Wall", tag="body", response="block", restitution=0.75, friction=1.0)
    wall.components.append(PhysicsBodyComponent(mode="StaticBody"))

    assert impulsions([rigid, wall])["couples"][(1, 2)] == [(0, 0, 192, 128)]


def test_un_kinematic_est_une_masse_infinie_pour_un_rigid(impulsions):
    from core.models.components import PhysicsBodyComponent
    platform = _acteur("Platform", tag="body", response="block")
    platform.components.append(PhysicsBodyComponent(mode="KinematicBody"))
    rigid = _acteur("Crate", tag="body", response="block")
    rigid.components.append(PhysicsBodyComponent(mode="RigidBody", mass=2.0))

    emis = impulsions([platform, rigid])
    assert emis["masses"] == {1: 0, 2: 128} and (1, 2) in emis["couples"]


def test_un_character_est_une_masse_infinie_pour_un_rigid(impulsions):
    from core.models.components import PhysicsBodyComponent
    character = _acteur("Hero", tag="body", response="block")
    character.components.append(PhysicsBodyComponent(mode="CharacterBody"))
    rigid = _acteur("Crate", tag="body", response="block")
    rigid.components.append(PhysicsBodyComponent(mode="RigidBody"))

    emis = impulsions([character, rigid])
    assert emis["masses"] == {1: 0, 2: 256} and (1, 2) in emis["couples"]


def test_un_kinematic_n_est_repousse_que_par_un_static(lignes):
    from core.models.components import PhysicsBodyComponent
    platform = _acteur("Platform", tag="body", response="block")
    platform.components.append(PhysicsBodyComponent(mode="KinematicBody"))
    character = _acteur("Character", tag="body", response="block", solid=False)
    character.components.append(PhysicsBodyComponent(mode="CharacterBody"))
    wall = _acteur("Wall", tag="body", response="block", solid=False)
    wall.components.append(PhysicsBodyComponent(mode="StaticBody"))

    rencontres = _rencontres(lignes([platform, character, wall]))

    # Types 1 (Platform), 2 (Character), 3 (Wall). La plateforme n'est arrêtée que par le mur ; le Character l'est par
    # la plateforme (bit haut : un Kinematic pousse même un mobile immobile), par un autre Character de son type et par
    # le mur.
    assert rencontres[1] == (1, {3: [0]})
    assert rencontres[2] == (1, {1: [0x80], 2: [0], 3: [0]})


def test_la_relation_du_body_restreint_forme_mobile_et_bloqueur(lignes):
    from core.models.components import PhysicsBodyComponent
    hero = Actor(name="Hero", components=[
        CollisionShapeComponent(id="hurt", tag="Hurt", solid=True),
        CollisionShapeComponent(id="body", tag="Player", solid=True),
        PhysicsBodyComponent(mode="CharacterBody", collider_id="body"),
    ])
    wall = Actor(name="Wall", components=[
        CollisionShapeComponent(id="sensor", tag="Ignored", response="block"),
        CollisionShapeComponent(id="shape", tag="body", response="block"),
        PhysicsBodyComponent(mode="StaticBody", collider_id="shape"),
    ])

    assert _rencontres(lignes([hero, wall])) == {1: (2, {2: [1]})}


def test_la_relation_du_body_restreint_les_paires_d_impulsion(impulsions):
    from core.models.components import PhysicsBodyComponent
    rigid = Actor(name="Crate", components=[
        CollisionShapeComponent(id="sensor", tag="Ignored", solid=True),
        CollisionShapeComponent(id="shape", tag="body", solid=True),
        PhysicsBodyComponent(mode="RigidBody", collider_id="shape"),
    ])
    wall = Actor(name="Wall", components=[
        CollisionShapeComponent(id="sensor", tag="Ignored", response="block"),
        CollisionShapeComponent(id="shape", tag="body", response="block"),
        PhysicsBodyComponent(mode="StaticBody", collider_id="shape"),
    ])

    assert impulsions([rigid, wall])["couples"][(1, 2)] == [(1, 1, 0, 0)]


def test_sans_bloqueur_rien_n_est_emis(lignes):
    assert lignes([_acteur("Hero", tag="Player"), _acteur("Wall", tag="body")]) == []


def test_la_matrice_de_collision_laisse_passer_un_couple_desactive(lignes):
    from core.models.settings import pair_key
    hero = _acteur("Hero", tag="Player")
    coffre = _acteur("Chest", tag="body", response="block")
    # Le coffre (boîte solide) est aussi un mobile, que le héros (boîte bloquante ? non : `sensor`) n'arrête pas.
    assert 1 not in _rencontres(lignes([hero, coffre], [pair_key("Player", "body")]))
    assert _rencontres(lignes([hero, coffre]))[1] == (1, {2: [0]})


def test_le_masque_de_contact_est_cuit_par_couple_de_boites():
    from codegen.runtime_codegen.gen_scene_query import collision_pair_mask
    from core.models.settings import pair_key

    left = Actor(name="Left", components=[
        CollisionShapeComponent(id="visible", tag="first"),
        CollisionShapeComponent(id="hidden", tag="second"),
    ])
    right = Actor(name="Right", components=[
        CollisionShapeComponent(id="target", tag="first"),
        CollisionShapeComponent(id="other", tag="second"),
    ])

    settings = _projet([pair_key("first", "second")]).settings
    assert collision_pair_mask(left, right, settings) == 0b100001


def test_le_blocage_est_refuse_par_defaut_et_survit_a_la_serialisation():
    from core.models.components import components_from_list, components_to_list
    assert CollisionShapeComponent().response == "sensor"
    serialise = components_to_list([CollisionShapeComponent(response="block")])
    assert serialise[0]["response"] == "block"
    (relu,) = components_from_list(serialise)
    assert relu.response == "block"
    ancien = {"component_type": "collision_shape", "id": "b", "solid": True, "tag": "body"}
    assert components_from_list([ancien])[0].response == "sensor"


# ── La boîte propre d'un Interactive en `facing` bloque, en `hover` non ──

def _coffre(interaction):
    from core.models.components import InteractiveComponent
    a = Actor(name="Chest")
    a.components = [InteractiveComponent(interaction=interaction)]
    return a


def test_la_boite_propre_d_un_interactive_facing_est_un_obstacle():
    from core.models.components import effective_collision_shapes
    (obstacle,) = effective_collision_shapes(_coffre("facing"))
    assert obstacle.response == "block" and obstacle.solid is True and obstacle.tag == "Interactive"
    (plaque,) = effective_collision_shapes(_coffre("hover"))
    assert plaque.response == "sensor" and plaque.solid is False      # on doit pouvoir la recouvrir


def test_un_coffre_facing_arrete_le_joueur_sans_boite_dessinee_par_l_auteur(lignes):
    hero = _acteur("Hero", tag="Player")
    assert _rencontres(lignes([hero, _coffre("facing")])) == {1: (1, {2: [0]})}


def test_une_plaque_hover_n_arrete_personne(lignes):
    assert lignes([_acteur("Hero", tag="Player"), _coffre("hover")]) == []


def test_la_case_de_matrice_player_interactive_decide_si_le_coffre_arrete(lignes):
    from core.models.settings import pair_key
    hero = _acteur("Hero", tag="Player")
    assert lignes([hero, _coffre("facing")], [pair_key("Player", "Interactive")]) == []


def test_le_projet_declare_un_bloqueur_pour_les_aides_c():
    from codegen.runtime_codegen.physics.blocks import project_has_blockers
    scene = SimpleNamespace(actors=[_coffre("facing")])
    assert project_has_blockers(SimpleNamespace(scenes=[scene], prefabs=[])) is True
    scene = SimpleNamespace(actors=[_coffre("hover")])
    assert project_has_blockers(SimpleNamespace(scenes=[scene], prefabs=[])) is False


def test_une_instance_du_pool_bloque_par_son_modele(resultats):
    assert resultats["pool_gauche"] == (34, 52)          # repoussé à gauche du bloqueur : 50 - 16
    assert resultats["pool_autre_modele"] == (40, 52)    # un autre modèle ne bloque pas
    assert resultats["pool_inactif"] == (40, 52)
    assert resultats["pool_hors_hw"] == (40, 52)         # au-delà du plus haut emplacement utilisé : ignoré
    assert resultats["pool_soi_meme"] == (40, 52)
    assert resultats["pose_puis_pool"] == (34, 52)
