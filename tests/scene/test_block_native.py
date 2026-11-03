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
Actor g_actors[8];
int g_spool_start = 0, g_spool_hw = 0;
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

int main(void){
    const u16 idx[] = {1, 2};
    const u8 box[] = {0, 0};
    /* le bloqueur : 16x16 en (50, 50) ; le mobile 16x16 */
    mk(1, 50, 50, 0, 0, 16, 16, 0); mk(2, 200, 200, 0, 0, 16, 16, 0);

    mk(0, 40, 52, 256, 0, 16, 16, 1);                          /* vient de la gauche : 6 px dedans */
    actors_resolve_blocks(&g_actors[0], 1, idx, box, 2);  report("gauche", 0);
    mk(0, 60, 52, -256, 0, 16, 16, 1);                         /* vient de la droite : 6 px dedans */
    actors_resolve_blocks(&g_actors[0], 1, idx, box, 2);  report("droite", 0);
    mk(0, 52, 40, 0, 256, 16, 16, 1);                          /* vient du haut */
    actors_resolve_blocks(&g_actors[0], 1, idx, box, 2);  report("haut", 0);
    report_motion("character_stop", 0);
    mk(0, 52, 60, 0, -256, 16, 16, 1);                         /* vient du bas */
    actors_resolve_blocks(&g_actors[0], 1, idx, box, 2);  report("bas", 0);
    mk(0, 38, 40, 256, 256, 16, 16, 1);                        /* coin : 4 px en x, 6 px en y -> glisse en x */
    actors_resolve_blocks(&g_actors[0], 1, idx, box, 2);  report("coin", 0);

    mk(0, 40, 52, 0, 0, 16, 16, 1);                            /* sans vitesse : téléporté, laissé */
    actors_resolve_blocks(&g_actors[0], 1, idx, box, 2);  report("immobile", 0);
    mk(0, 40, 52, 256, 0, 16, 16, 0);                          /* sans forme de corps : laissé */
    actors_resolve_blocks(&g_actors[0], 0, idx, box, 2);  report("non_solide", 0);
    mk(0, 10, 10, 256, 0, 16, 16, 1);                          /* loin : laissé */
    actors_resolve_blocks(&g_actors[0], 1, idx, box, 2);  report("loin", 0);

    mk(0, 40, 52, 256, 0, 16, 16, 1); g_actors[1].active = 0;  /* bloqueur inactif : traversé */
    actors_resolve_blocks(&g_actors[0], 1, idx, box, 2);  report("inactif", 0);
    g_actors[1].active = 1; g_actors[1].collision.boxes[0].active = 0;   /* boîte inactive : traversée */
    mk(0, 40, 52, 256, 0, 16, 16, 1);
    actors_resolve_blocks(&g_actors[0], 1, idx, box, 2);  report("boite_inactive", 0);
    g_actors[1].collision.boxes[0].active = 1;

    mk(0, 40, 52, 256, 0, 16, 16, 1); g_actors[0].x += 128;    /* la fraction (1/2 px) survit */
    actors_resolve_blocks(&g_actors[0], 1, idx, box, 2);
    printf("fraction %%d\n", g_actors[0].x & 255);

    {   /* un acteur ne se bloque pas lui-même */
        const u16 moi[] = {0}; const u8 b0[] = {0};
        mk(0, 40, 52, 256, 0, 16, 16, 1);
        actors_resolve_blocks(&g_actors[0], 1, moi, b0, 1);  report("soi_meme", 0);
    }

    {   /* Le pool PARTAGÉ : un bloqueur né à l'emplacement 3 (modèle 7, boîte 0), un autre modèle à l'emplacement 4. */
        const u8 pm[] = {7}, pb[] = {0};
        mk(3, 50, 50, 0, 0, 16, 16, 0); g_actors[3].model = 7;
        mk(4, 50, 50, 0, 0, 16, 16, 0); g_actors[4].model = 9;     /* un autre modèle : traversé */
        g_spool_start = 3; g_spool_hw = 5;
        pool_bit_set(3); pool_bit_set(4);
        mk(0, 40, 52, 256, 0, 16, 16, 1);
        actors_resolve_blocks_pool(&g_actors[0], 1, pm, pb, 1);   report("pool_gauche", 0);
        mk(0, 40, 52, 256, 0, 16, 16, 1); g_actors[3].model = 9;
        actors_resolve_blocks_pool(&g_actors[0], 1, pm, pb, 1);   report("pool_autre_modele", 0);
        g_actors[3].model = 7; g_actors[3].active = 0;
        mk(0, 40, 52, 256, 0, 16, 16, 1);
        actors_resolve_blocks_pool(&g_actors[0], 1, pm, pb, 1);   report("pool_inactif", 0);
        g_actors[3].active = 1; g_spool_hw = 3;
        mk(0, 40, 52, 256, 0, 16, 16, 1);
        actors_resolve_blocks_pool(&g_actors[0], 1, pm, pb, 1);   report("pool_hors_hw", 0);
        g_spool_hw = 5;
        mk(3, 40, 52, 0, 0, 16, 16, 1); g_actors[3].model = 7; g_actors[3].vx = 256;   /* un bloqueur ne se bloque pas lui-même */
        actors_resolve_blocks_pool(&g_actors[3], 1, pm, pb, 1);   report("pool_soi_meme", 3);
    }

    {   /* Rigid au-dessus d'un Static : toute la correction et l'impulsion vont au Rigid. */
        const RigidPair pair = {0, 1, 256, 0, 0, 0};
        mk(0, 50, 40, 0, 256, 16, 16, 1);
        mk(1, 50, 50, 0, 0, 16, 16, 0);
        rigid_pair_resolve(&pair);
        report_motion("rigid_static", 0);
    }

    {   /* Deux Rigid de même masse partagent correction et vitesse normale. */
        const RigidPair pair = {0, 1, 256, 256, 0, 0};
        mk(0, 50, 40, 0, 256, 16, 16, 1);
        mk(1, 50, 50, 0, 0, 16, 16, 1);
        rigid_pair_resolve(&pair);
        report_motion("rigid_rigid_a", 0);
        report_motion("rigid_rigid_b", 1);
    }

    {   /* Le corps deux fois plus lourd ne prend qu'un tiers de la correction. */
        const RigidPair pair = {0, 1, 256, 128, 0, 0};
        mk(0, 50, 40, 0, 256, 16, 16, 1);
        mk(1, 50, 50, 0, 0, 16, 16, 1);
        rigid_pair_resolve(&pair);
        report_motion("rigid_mass_light", 0);
        report_motion("rigid_mass_heavy", 1);
    }

    {   /* Une restitution maximale inverse la vitesse normale du Rigid. */
        const RigidPair pair = {0, 1, 256, 0, 256, 0, 0, 0};
        mk(0, 50, 40, 0, 256, 16, 16, 1);
        mk(1, 50, 50, 0, 0, 16, 16, 0);
        rigid_pair_resolve(&pair);
        report_motion("rigid_bounce", 0);
    }

    {   /* Une friction maximale arrête la vitesse tangentielle contre un Static. */
        const RigidPair pair = {0, 1, 256, 0, 0, 256, 0, 0};
        mk(0, 50, 40, 256, 0, 16, 16, 1);
        mk(1, 50, 50, 0, 0, 16, 16, 0);
        rigid_pair_resolve(&pair);
        report_motion("rigid_friction", 0);
    }


    {   /* Une plateforme déplace une seule fois le corps posé sur son ancienne face supérieure. */
        int carry_x=0, carry_y=0; u8 carried=0;
        mk(0, 52, 50, 512, 0, 16, 16, 0);
        mk(1, 54, 34, 0, 0, 8, 16, 1);
        kinematic_carry(&g_actors[0], &g_actors[1], 0, 0, 50<<8, 50<<8,
                        &carried, &carry_x, &carry_y);
        report("kinematic_rider", 1);
        printf("kinematic_delta %%d %%d %%d\n", carry_x, carry_y, carried);

        carry_x=carry_y=0; carried=0;
        mk(1, 54, 34, 0, -256, 8, 16, 1);
        kinematic_carry(&g_actors[0], &g_actors[1], 0, 0, 50<<8, 50<<8,
                        &carried, &carry_x, &carry_y);
        report("kinematic_jump", 1);

        carry_x=carry_y=0; carried=0;
        mk(0, 50, 52, 0, 512, 16, 16, 0);
        mk(1, 54, 34, 0, 0, 8, 16, 1);
        kinematic_carry(&g_actors[0], &g_actors[1], 0, 0, 50<<8, 50<<8,
                        &carried, &carry_x, &carry_y);
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


def _lignes(p, acteurs):
    from codegen.runtime_codegen.physics.blocks import block_tick_lines
    return block_tick_lines(p, None, _scene(*acteurs), 0, [], lambda _p, _o: (None, None))


def _lignes_impulsions(p, acteurs):
    from codegen.runtime_codegen.physics.impulses import impulse_tick_lines
    from core.models.scene import Scene
    return impulse_tick_lines(p, Scene(name="Physics"), _scene(*acteurs), 0, [], None)


def test_le_mobile_recoit_la_table_des_boites_bloquantes():
    hero = _acteur("Hero", tag="Player")
    coffre = _acteur("Chest", tag="body", response="block", solid=False)
    lignes = "\n".join(_lignes(_projet(), [hero, coffre]))
    assert "static const u16 _bk_idx[]={1};" in lignes
    assert "actors_resolve_blocks(&g_actors[0],1,_bk_idx,_bk_box,1);" in lignes
    # Le coffre n'a pas de boîte solide : il n'est pas un mobile.
    assert "g_actors[1]," not in lignes


def test_un_static_body_bloque_sans_devenir_un_mobile():
    from core.models.components import PhysicsBodyComponent
    hero = _acteur("Hero", tag="Player")
    mur = _acteur("Wall", tag="body", response="block", solid=False)
    mur.components.append(PhysicsBodyComponent(mode="StaticBody"))
    lignes = "\n".join(_lignes(_projet(), [hero, mur]))
    assert "static const u16 _bk_idx[]={1};" in lignes
    assert "g_actors[1]," not in lignes


def test_un_rigid_pose_passe_par_la_table_d_impulsions_et_non_le_blocage_historique():
    from core.models.components import PhysicsBodyComponent
    from codegen.runtime_codegen.physics.impulses import impulse_tick_lines
    from core.models.scene import Scene
    rigid = _acteur("Crate", tag="body", response="block")
    rigid.components.append(PhysicsBodyComponent(mode="RigidBody"))
    sol = _acteur("Floor", tag="body", response="block", solid=False)
    sol.components.append(PhysicsBodyComponent(mode="StaticBody"))

    assert not any("actors_resolve_blocks(&g_actors[0]" in line
                   for line in _lignes(_projet(), [rigid, sol]))
    lignes = "\n".join(_lignes_impulsions(_projet(), [rigid, sol]))
    assert "static const RigidPair _rigid_pairs[1]" in lignes
    assert "{0,1,256,0,0,0,0,0}" in lignes
    assert "_it<4" in lignes

    six_passes = "\n".join(impulse_tick_lines(
        _projet(), Scene(name="Physics", physics_gravity_override=True,
                         physics_solver_iterations=6), _scene(rigid, sol), 0, [], None))
    assert "_it<6" in six_passes


def test_plus_de_255_paires_rigid_utilisent_des_compteurs_16_bits_et_le_rejet_par_rectangles():
    from core.models.components import PhysicsBodyComponent
    crates = []
    for i in range(24):                 # 24 Rigid : 276 paires, au-delà de ce qu'un compteur u8 peut parcourir
        crate = _acteur(f"Crate{i}", tag="body", response="block")
        crate.components.append(PhysicsBodyComponent(mode="RigidBody"))
        crates.append(crate)
    lignes = "\n".join(_lignes_impulsions(_projet(), crates))
    assert "static const RigidPair _rigid_pairs[276]" in lignes
    assert "u8 _k" not in lignes
    # Les rectangles sont relevés une fois, et seules les paires retenues par la première passe sont rejouées.
    assert lignes.count("rigid_side_rect(") == 1
    assert "static s16 _rigid_rect[24][5];" in lignes
    assert "u16 _live_n=rigid_pairs_scan(_rigid_pairs,_rigid_pair_sides,_rigid_rect,276,_rigid_live,30);" in lignes
    assert "for(u8 _it=1;_it<4;_it++)" in lignes
    # Une paire dont les deux côtés sont au repos (StaticBody ou Rigid endormi) n'est pas rejouée.
    assert "rigid_side_rect(_rigid_sides[_s][0],_rigid_sides[_s][1],_rigid_sides[_s][2],30,_rigid_rect[_s]);" in lignes


def test_la_table_encode_la_masse_inverse_de_chaque_rigid():
    from core.models.components import PhysicsBodyComponent
    light = _acteur("Light", tag="body", response="block")
    light.components.append(PhysicsBodyComponent(mode="RigidBody", mass=0.5))
    heavy = _acteur("Heavy", tag="body", response="block")
    heavy.components.append(PhysicsBodyComponent(mode="RigidBody", mass=2.0))

    lignes = "\n".join(_lignes_impulsions(_projet(), [light, heavy]))

    assert "{0,1,512,128,0,0,0,0}" in lignes


def test_la_table_cuit_les_materiaux_du_contact():
    from core.models.components import PhysicsBodyComponent
    rigid = _acteur("Ball", tag="body", response="block", restitution=0.25, friction=0.25)
    rigid.components.append(PhysicsBodyComponent(mode="RigidBody"))
    wall = _acteur("Wall", tag="body", response="block", restitution=0.75, friction=1.0)
    wall.components.append(PhysicsBodyComponent(mode="StaticBody"))

    lignes = "\n".join(_lignes_impulsions(_projet(), [rigid, wall]))

    assert "{0,1,256,0,192,128,0,0}" in lignes


def test_un_kinematic_est_une_masse_infinie_pour_un_rigid():
    from core.models.components import PhysicsBodyComponent
    platform = _acteur("Platform", tag="body", response="block")
    platform.components.append(PhysicsBodyComponent(mode="KinematicBody"))
    rigid = _acteur("Crate", tag="body", response="block")
    rigid.components.append(PhysicsBodyComponent(mode="RigidBody", mass=2.0))

    lignes = "\n".join(_lignes_impulsions(_projet(), [platform, rigid]))

    assert "{0,1,0,128,0,0,0,0}" in lignes


def test_un_character_est_une_masse_infinie_pour_un_rigid():
    from core.models.components import PhysicsBodyComponent
    character = _acteur("Hero", tag="body", response="block")
    character.components.append(PhysicsBodyComponent(mode="CharacterBody"))
    rigid = _acteur("Crate", tag="body", response="block")
    rigid.components.append(PhysicsBodyComponent(mode="RigidBody"))

    lignes = "\n".join(_lignes_impulsions(_projet(), [character, rigid]))

    assert "{0,1,0,256,0,0,0,0}" in lignes


def test_un_kinematic_n_est_repousse_que_par_un_static():
    from core.models.components import PhysicsBodyComponent
    platform = _acteur("Platform", tag="body", response="block")
    platform.components.append(PhysicsBodyComponent(mode="KinematicBody"))
    character = _acteur("Character", tag="body", response="block", solid=False)
    character.components.append(PhysicsBodyComponent(mode="CharacterBody"))
    wall = _acteur("Wall", tag="body", response="block", solid=False)
    wall.components.append(PhysicsBodyComponent(mode="StaticBody"))

    lignes = "\n".join(_lignes(_projet(), [platform, character, wall]))

    assert "static const u16 _bk_idx[]={2};" in lignes
    assert "static const u16 _bk_idx[]={1,2};" not in lignes


def test_la_relation_du_body_restreint_forme_mobile_et_bloqueur():
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

    lignes = "\n".join(_lignes(_projet(), [hero, wall]))

    assert "actors_resolve_blocks(&g_actors[0],2,_bk_idx,_bk_box,1);" in lignes
    assert "static const u8 _bk_box[]={1};" in lignes


def test_la_relation_du_body_restreint_les_paires_d_impulsion():
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

    lignes = "\n".join(_lignes_impulsions(_projet(), [rigid, wall]))

    assert "{0,1,256,0,0,0,1,1}" in lignes
    assert "_rigid_pairs[1]" in lignes


def test_sans_bloqueur_rien_n_est_emis():
    assert _lignes(_projet(), [_acteur("Hero", tag="Player"), _acteur("Wall", tag="body")]) == []


def test_la_matrice_de_collision_laisse_passer_un_couple_desactive():
    from core.models.settings import pair_key
    hero = _acteur("Hero", tag="Player")
    coffre = _acteur("Chest", tag="body", response="block")
    passe = _lignes(_projet([pair_key("Player", "body")]), [hero, coffre])
    assert not any("actors_resolve_blocks(&g_actors[0]" in l for l in passe)
    bloque = _lignes(_projet(), [hero, coffre])
    assert any("actors_resolve_blocks(&g_actors[0]" in l for l in bloque)


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


def test_un_coffre_facing_arrete_le_joueur_sans_boite_dessinee_par_l_auteur():
    hero = _acteur("Hero", tag="Player")
    lignes = "\n".join(_lignes(_projet(), [hero, _coffre("facing")]))
    assert "static const u16 _bk_idx[]={1};" in lignes and "static const u8 _bk_box[]={0};" in lignes
    assert "actors_resolve_blocks(&g_actors[0],1,_bk_idx,_bk_box,1);" in lignes


def test_une_plaque_hover_n_arrete_personne():
    assert _lignes(_projet(), [_acteur("Hero", tag="Player"), _coffre("hover")]) == []


def test_la_case_de_matrice_player_interactive_decide_si_le_coffre_arrete():
    from core.models.settings import pair_key
    hero = _acteur("Hero", tag="Player")
    passe = _lignes(_projet([pair_key("Player", "Interactive")]), [hero, _coffre("facing")])
    assert passe == []


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
