"""Un script qui déplace un enfant : le déplacement survit à la composition (`slot_local_from_world`).

Une racine (Ship), son enfant (Moon) et le petit-enfant (Pin), liés par les lignes réellement émises pour une scène
(`placed_link_lines`), puis composés par le runtime (`slot_compose_all`). Chaque cas joue une image : des écritures de
script, puis la composition, comme dans le tick. Les quatre écritures de position du script (`position`, `move`,
`move_to`, `apply_velocity`) mettent à jour le décalage local de l'enfant, lu contre la position du parent au moment
de l'écriture. Le pas physique du moteur et l'ordre du tick ne sont pas couverts ici.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

SHIP = (100, 50)
MOON = (128, 50)        # 28 px à droite de Ship
PIN = (136, 50)         # 8 px à droite de Moon

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
Actor g_actors[4];
int g_spool_start, g_actor_slot_end, g_scene_placed;
u32 g_alive_bits[1], g_alive_epoch;
SlotLink g_slot_link[4]; int g_slot_depth;
OamEntry g_oam_entries[1];
#define EASE_IN 0
#define EASE_OUT 1
#define EASE_IN_OUT 2
void window_set(int id,int x,int y,int w,int h);
void window_show(int id,int on);
#include "runtime_api_inline.h"

static Actor* const ship = &g_actors[0];
static Actor* const moon = &g_actors[1];
static Actor* const pin  = &g_actors[2];

/* La scène à son entrée : les poses authorées, puis les liens émis par le build. */
static void entre(void){
    for(int k = 0; k < 4; k++){
        g_actors[k] = (Actor){0};
        g_actors[k].slot_index = k; g_actors[k].alive = 1; g_actors[k].active = 1; g_actors[k].oam_entry = -1;
        g_slot_link[k].parent = -1; g_slot_link[k].depth = 0;
    }
    ship->x = @SX@ << 8; ship->y = @SY@ << 8;
    moon->x = @MX@ << 8; moon->y = @MY@ << 8;
    pin->x  = @PX@ << 8; pin->y  = @PY@ << 8;
@LINKS@
}
static void rapporte(const char* nom){
    printf("%s %d %d %d %d %d %d\n", nom, ship->x, ship->y, moon->x, moon->y, pin->x, pin->y);
}

int main(void){
    g_actor_slot_end = 4;
    g_slot_depth = @DEPTH@;

    /* Rien n'est écrit : la composition redonne la pose authorée. */
    entre(); slot_compose_all(); rapporte("immobile");

    /* L'orbite de Ship.lua : le parent bouge, puis écrit la position de son enfant. */
    entre();
    actor_set_position(ship, (Vec2){110, 50});
    actor_set_position(moon, (Vec2){110, 30});
    slot_compose_all(); rapporte("parent_puis_enfant");

    /* Le parent écrit son enfant, puis bouge : l'enfant suit ce déplacement. */
    entre();
    actor_set_position(moon, (Vec2){100, 30});
    actor_set_position(ship, (Vec2){110, 50});
    slot_compose_all(); rapporte("enfant_puis_parent");

    /* L'écriture survit aux images suivantes : le nouveau décalage reste. */
    entre();
    actor_set_position(moon, (Vec2){100, 30});
    slot_compose_all();
    actor_set_position(ship, (Vec2){120, 60});
    slot_compose_all(); rapporte("image_suivante");

    entre(); actor_move(moon, (Vec2){0, 1}, 3); slot_compose_all(); rapporte("move");
    entre(); actor_move_to(moon, (Vec2){128, 40}, 4); slot_compose_all(); rapporte("move_to");
    entre(); actor_move_to(moon, (Vec2){130, 50}, 4); slot_compose_all(); rapporte("move_to_atteint");

    entre();
    moon->vx = 128; moon->vy = -64;
    actor_apply_velocity(moon); slot_compose_all(); rapporte("apply_velocity");

    /* Une racine n'a pas de décalage : son écriture ne change que sa position. */
    entre(); actor_set_position(ship, (Vec2){0, 0}); slot_compose_all(); rapporte("racine");
    return 0;
}
"""


@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la position d'un enfant est vérifiée en CI")
    from core.models.scene import Actor
    from codegen.runtime_codegen.gen_actor_hierarchy import link_depth, placed_link_lines

    scene = [(Actor(name="Ship", x=SHIP[0], y=SHIP[1]), None),
             (Actor(name="Moon", x=MOON[0], y=MOON[1], parent="Ship"), None),
             (Actor(name="Pin", x=PIN[0], y=PIN[1], parent="Moon"), None)]
    liens = placed_link_lines(scene, 0)
    assert len(liens) == 2
    valeurs = {"@SX@": SHIP[0], "@SY@": SHIP[1], "@MX@": MOON[0], "@MY@": MOON[1], "@PX@": PIN[0], "@PY@": PIN[1],
               "@DEPTH@": link_depth(scene, []), "@LINKS@": "\n".join(liens)}
    source = SONDE
    for cle, valeur in valeurs.items():
        source = source.replace(cle, str(valeur))
    dossier = tmp_path_factory.mktemp("child_position")
    (dossier / "obj_state.h").write_text("#define OBJ_STATE_STRIDE 1\n", encoding="utf-8")
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(dossier), "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    return {nom: tuple(int(v) for v in reste)
            for nom, *reste in (ligne.split() for ligne in sortie.stdout.strip().splitlines())}


def px(*xy):
    return tuple(v << 8 for v in xy)


def test_sans_ecriture_la_pose_authoree_revient(etats):
    assert etats["immobile"] == px(*SHIP, *MOON, *PIN)


def test_le_parent_bouge_puis_ecrit_son_enfant(etats):
    """L'enfant tombe pile sur la position écrite ; le petit-enfant le suit."""
    assert etats["parent_puis_enfant"] == px(110, 50, 110, 30, 118, 30)


def test_le_parent_ecrit_son_enfant_puis_bouge(etats):
    """Le décalage est lu contre le parent au moment de l'écriture : l'enfant suit le déplacement qui vient après."""
    assert etats["enfant_puis_parent"] == px(110, 50, 110, 30, 118, 30)


def test_le_nouveau_decalage_reste_aux_images_suivantes(etats):
    assert etats["image_suivante"] == px(120, 60, 120, 40, 128, 40)


def test_move_et_move_to_deplacent_un_enfant(etats):
    assert etats["move"] == px(*SHIP, 128, 53, 136, 53)
    assert etats["move_to"] == px(*SHIP, 128, 46, 136, 46)
    assert etats["move_to_atteint"] == px(*SHIP, 130, 50, 138, 50)


def test_apply_velocity_garde_le_sous_pixel_d_un_enfant(etats):
    ship_x, ship_y, moon_x, moon_y, pin_x, pin_y = etats["apply_velocity"]
    assert (moon_x, moon_y) == ((MOON[0] << 8) + 128, (MOON[1] << 8) - 64)
    assert (pin_x - moon_x, pin_y - moon_y) == ((PIN[0] - MOON[0]) << 8, 0)


def test_une_racine_deplacee_emmene_ses_enfants(etats):
    assert etats["racine"] == px(0, 0, 28, 0, 36, 0)
