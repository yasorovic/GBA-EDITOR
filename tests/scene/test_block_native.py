"""Le blocage entre acteurs : le C réel de `actors_resolve_blocks`, compilé et exécuté, puis ce que le
générateur émet (tables filtrées par la matrice de collision, pools)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.models.components import CollisionBoxComponent
from core.models.scene import Actor
from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
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
    CollisionBox* b = &a->collision.boxes[0];
    b->w = w; b->h = h; b->solid = solid; b->active = 1;
}
static void report(const char* nom, int i){
    printf("%%s %%d %%d\n", nom, g_actors[i].x >> 8, g_actors[i].y >> 8);
}

int main(void){
    const u16 idx[] = {1, 2};
    const u8 box[] = {0, 0};
    /* le bloqueur : 16x16 en (50, 50) ; le mobile 16x16 */
    mk(1, 50, 50, 0, 0, 16, 16, 0); mk(2, 200, 200, 0, 0, 16, 16, 0);

    mk(0, 40, 52, 256, 0, 16, 16, 1);                          /* vient de la gauche : 6 px dedans */
    actors_resolve_blocks(&g_actors[0], idx, box, 2);  report("gauche", 0);
    mk(0, 60, 52, -256, 0, 16, 16, 1);                         /* vient de la droite : 6 px dedans */
    actors_resolve_blocks(&g_actors[0], idx, box, 2);  report("droite", 0);
    mk(0, 52, 40, 0, 256, 16, 16, 1);                          /* vient du haut */
    actors_resolve_blocks(&g_actors[0], idx, box, 2);  report("haut", 0);
    mk(0, 52, 60, 0, -256, 16, 16, 1);                         /* vient du bas */
    actors_resolve_blocks(&g_actors[0], idx, box, 2);  report("bas", 0);
    mk(0, 38, 40, 256, 256, 16, 16, 1);                        /* coin : 4 px en x, 6 px en y -> glisse en x */
    actors_resolve_blocks(&g_actors[0], idx, box, 2);  report("coin", 0);

    mk(0, 40, 52, 0, 0, 16, 16, 1);                            /* sans vitesse : téléporté, laissé */
    actors_resolve_blocks(&g_actors[0], idx, box, 2);  report("immobile", 0);
    mk(0, 40, 52, 256, 0, 16, 16, 0);                          /* sans boîte solide : laissé */
    actors_resolve_blocks(&g_actors[0], idx, box, 2);  report("non_solide", 0);
    mk(0, 10, 10, 256, 0, 16, 16, 1);                          /* loin : laissé */
    actors_resolve_blocks(&g_actors[0], idx, box, 2);  report("loin", 0);

    mk(0, 40, 52, 256, 0, 16, 16, 1); g_actors[1].active = 0;  /* bloqueur inactif : traversé */
    actors_resolve_blocks(&g_actors[0], idx, box, 2);  report("inactif", 0);
    g_actors[1].active = 1; g_actors[1].collision.boxes[0].active = 0;   /* boîte inactive : traversée */
    mk(0, 40, 52, 256, 0, 16, 16, 1);
    actors_resolve_blocks(&g_actors[0], idx, box, 2);  report("boite_inactive", 0);
    g_actors[1].collision.boxes[0].active = 1;

    mk(0, 40, 52, 256, 0, 16, 16, 1); g_actors[0].x += 128;    /* la fraction (1/2 px) survit */
    actors_resolve_blocks(&g_actors[0], idx, box, 2);
    printf("fraction %%d\n", g_actors[0].x & 255);

    {   /* un acteur ne se bloque pas lui-même */
        const u16 moi[] = {0}; const u8 b0[] = {0};
        mk(0, 40, 52, 256, 0, 16, 16, 1);
        actors_resolve_blocks(&g_actors[0], moi, b0, 1);  report("soi_meme", 0);
    }

    {   /* Le pool PARTAGÉ : un bloqueur né à l'emplacement 3 (modèle 7, boîte 0), un autre modèle à l'emplacement 4. */
        const u8 pm[] = {7}, pb[] = {0};
        mk(3, 50, 50, 0, 0, 16, 16, 0); g_actors[3].model = 7;
        mk(4, 50, 50, 0, 0, 16, 16, 0); g_actors[4].model = 9;     /* un autre modèle : traversé */
        g_spool_start = 3; g_spool_hw = 5;
        pool_bit_set(3); pool_bit_set(4);
        mk(0, 40, 52, 256, 0, 16, 16, 1);
        actors_resolve_blocks_pool(&g_actors[0], pm, pb, 1);   report("pool_gauche", 0);
        mk(0, 40, 52, 256, 0, 16, 16, 1); g_actors[3].model = 9;
        actors_resolve_blocks_pool(&g_actors[0], pm, pb, 1);   report("pool_autre_modele", 0);
        g_actors[3].model = 7; g_actors[3].active = 0;
        mk(0, 40, 52, 256, 0, 16, 16, 1);
        actors_resolve_blocks_pool(&g_actors[0], pm, pb, 1);   report("pool_inactif", 0);
        g_actors[3].active = 1; g_spool_hw = 3;
        mk(0, 40, 52, 256, 0, 16, 16, 1);
        actors_resolve_blocks_pool(&g_actors[0], pm, pb, 1);   report("pool_hors_hw", 0);
        g_spool_hw = 5;
        mk(3, 40, 52, 0, 0, 16, 16, 1); g_actors[3].model = 7; g_actors[3].vx = 256;   /* un bloqueur ne se bloque pas lui-même */
        actors_resolve_blocks_pool(&g_actors[3], pm, pb, 1);   report("pool_soi_meme", 3);
    }
    return 0;
}
"""


@pytest.fixture(scope="module")
def resultats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; le blocage est vérifié en CI")
    from codegen.runtime_codegen.block_gen import block_helper_lines
    dossier = tmp_path_factory.mktemp("block")
    (dossier / "probe.c").write_text(SONDE % {"helpers": "\n".join(block_helper_lines())}, encoding="utf-8")
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


# ── Ce que le générateur émet ─────────────────────────────────────────

def _scene(*acteurs):
    return [(a, None) for a in acteurs]


def _acteur(nom, **boite):
    a = Actor(name=nom)
    a.components = [CollisionBoxComponent(id="b", **boite)]
    return a


def _projet(paires_desactivees=()):
    return SimpleNamespace(settings=SimpleNamespace(collision_disabled_pairs=list(paires_desactivees),
                                                    collision_tags=[]))


def _lignes(p, acteurs):
    from codegen.runtime_codegen.block_gen import block_tick_lines
    return block_tick_lines(p, None, _scene(*acteurs), 0, [], lambda _p, _o: (None, None))


def test_le_mobile_recoit_la_table_des_boites_bloquantes():
    hero = _acteur("Hero", tag="Player")
    coffre = _acteur("Chest", tag="body", blocks_actors=True, solid=False)
    lignes = "\n".join(_lignes(_projet(), [hero, coffre]))
    assert "static const u16 _bk_idx[]={1};" in lignes
    assert "actors_resolve_blocks(&g_actors[0],_bk_idx,_bk_box,1);" in lignes
    # Le coffre n'a pas de boîte solide : il n'est pas un mobile.
    assert "g_actors[1]," not in lignes


def test_sans_bloqueur_rien_n_est_emis():
    assert _lignes(_projet(), [_acteur("Hero", tag="Player"), _acteur("Wall", tag="body")]) == []


def test_la_matrice_de_collision_laisse_passer_un_couple_desactive():
    from core.models.settings import pair_key
    hero = _acteur("Hero", tag="Player")
    coffre = _acteur("Chest", tag="body", blocks_actors=True)
    passe = _lignes(_projet([pair_key("Player", "body")]), [hero, coffre])
    assert not any("actors_resolve_blocks(&g_actors[0]" in l for l in passe)
    bloque = _lignes(_projet(), [hero, coffre])
    assert any("actors_resolve_blocks(&g_actors[0]" in l for l in bloque)


def test_le_blocage_est_refuse_par_defaut_et_survit_a_la_serialisation():
    from core.models.components import components_from_list, components_to_list
    assert CollisionBoxComponent().blocks_actors is False
    (relu,) = components_from_list(components_to_list([CollisionBoxComponent(blocks_actors=True)]))
    assert relu.blocks_actors is True
    ancien = {"component_type": "collision_box", "id": "b", "solid": True, "tag": "body"}
    assert components_from_list([ancien])[0].blocks_actors is False


# ── La boîte propre d'un Interactive en `facing` bloque, en `hover` non ──

def _coffre(interaction):
    from core.models.components import InteractiveComponent
    a = Actor(name="Chest")
    a.components = [InteractiveComponent(interaction=interaction)]
    return a


def test_la_boite_propre_d_un_interactive_facing_est_un_obstacle():
    from core.models.components import effective_collision_boxes
    (obstacle,) = effective_collision_boxes(_coffre("facing"))
    assert obstacle.blocks_actors is True and obstacle.solid is True and obstacle.tag == "Interactive"
    (plaque,) = effective_collision_boxes(_coffre("hover"))
    assert plaque.blocks_actors is False and plaque.solid is False      # on doit pouvoir la recouvrir


def test_un_coffre_facing_arrete_le_joueur_sans_boite_dessinee_par_l_auteur():
    hero = _acteur("Hero", tag="Player")
    lignes = "\n".join(_lignes(_projet(), [hero, _coffre("facing")]))
    assert "static const u16 _bk_idx[]={1};" in lignes and "static const u8 _bk_box[]={0};" in lignes
    assert "actors_resolve_blocks(&g_actors[0],_bk_idx,_bk_box,1);" in lignes


def test_une_plaque_hover_n_arrete_personne():
    assert _lignes(_projet(), [_acteur("Hero", tag="Player"), _coffre("hover")]) == []


def test_la_case_de_matrice_player_interactive_decide_si_le_coffre_arrete():
    from core.models.settings import pair_key
    hero = _acteur("Hero", tag="Player")
    passe = _lignes(_projet([pair_key("Player", "Interactive")]), [hero, _coffre("facing")])
    assert passe == []


def test_le_projet_declare_un_bloqueur_pour_les_aides_c():
    from codegen.runtime_codegen.block_gen import project_has_blockers
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
