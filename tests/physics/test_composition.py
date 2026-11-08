"""La composition parent → enfant, posé ou né : une seule fonction runtime (`slot_compose_all`), deux façons d'avoir le lien.

Une racine, un bras (enfant de la racine) et une main (enfant du bras), posés dans la scène (`placed_link_lines`) ou nés
ensemble comme un prefab à parties (`part_link_lines`). Les deux dérivent le local de la pose authorée ; à une position de
racine donnée, le bras et la main tombent au même endroit (un acteur n'a ni rotation ni échelle : translation seule). Les
deux règles du sous-arbre sont vérifiées : une racine éteinte éteint ses enfants, un enfant éteint ne se recompose pas (et
éteint les siens). Les sprites sont absents : la propagation de `visible` n'est pas couverte.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

# Pose authorée de la hiérarchie, dans le MONDE d'un template posé à l'origine : (x, y).
BRAS = (16, 8)
MAIN = (24, 8)
RACINE_POSEE = (100, 50)         # où la racine est posée dans la scène; le prefab, lui, est à l'origine

# (nom, x, y) de la racine à l'exécution.
SCENARIOS = [
    ("neutre", 100, 50),
    ("deplacee", 37, 12),
    ("negative", -10, -20),
]

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
Actor g_actors[8];
int g_spool_start, g_actor_slot_end, g_scene_placed;
u32 g_alive_bits[1], g_alive_epoch;
SlotLink g_slot_link[8]; int g_slot_depth;
OamEntry g_oam_entries[1];
#define EASE_IN 0
#define EASE_OUT 1
#define EASE_IN_OUT 2
void window_set(int id,int x,int y,int w,int h);
void window_show(int id,int on);
#include "runtime_api_inline.h"

static void membre(int k, int x, int y, int actif){
    g_actors[k] = (Actor){0};
    g_actors[k].slot_index = k; g_actors[k].alive = 1; g_actors[k].active = actif; g_actors[k].oam_entry = -1;
    g_actors[k].x = x; g_actors[k].y = y;
    g_slot_link[k].parent = -1; g_slot_link[k].depth = 0;
}
static void rapporte(const char* chemin, const char* nom, int base){
    for(int k = 1; k <= 2; k++){
        const Actor* a = &g_actors[base + k];
        printf("%s %s %d %d %d %d\n", chemin, nom, k, a->x, a->y, a->active);
    }
}
/* Posé : racine 0, bras 1, main 2. */
static void joue_pose(const char* nom, int x, int y, int racine_active, int bras_actif){
    for(int k = 0; k < 8; k++) membre(k, 0, 0, 0);
    membre(0, x << 8, y << 8, racine_active);
    membre(1, 0, 0, bras_actif);
    membre(2, 0, 0, 1);
@PLACED@
    slot_compose_all();
    rapporte("pose", nom, 0);
}
/* Né : racine 4, bras 5, main 6 (un groupe contigu de 3 emplacements). */
static void joue_pool(const char* nom, int x, int y, int racine_active, int bras_actif){
    for(int k = 0; k < 8; k++) membre(k, 0, 0, 0);
    membre(4, x << 8, y << 8, racine_active);
    membre(5, 0, 0, bras_actif);
    membre(6, 0, 0, 1);
@POOL@
    slot_compose_all();
    rapporte("pool", nom, 4);
}

int main(void){
    g_actor_slot_end = 8;
@RUNS@
    return 0;
}
"""


def _hierarchie():
    from core.models.scene import Actor, Prefab

    def piece(nom, pose, parent=None, origine=(0, 0)):
        x, y = pose
        return Actor(name=nom, x=origine[0] + x, y=origine[1] + y, parent=parent)

    racine = Actor(name="Racine", x=RACINE_POSEE[0], y=RACINE_POSEE[1])
    posés = [racine, piece("Bras", BRAS, "Racine", RACINE_POSEE), piece("Main", MAIN, "Bras", RACINE_POSEE)]
    prefab = Prefab(name="Racine")
    prefab.children = [piece("Bras", BRAS), piece("Main", MAIN, "Bras")]
    return posés, prefab


def _liens():
    from codegen.runtime_codegen.gen_actor_hierarchy import link_depth, part_link_lines, placed_link_lines

    posés, prefab = _hierarchie()
    scene = [(a, None) for a in posés]
    profondeur = link_depth(scene, [{"prefab": prefab, "shared": True}])
    return placed_link_lines(scene, 0), part_link_lines(prefab, "4", "    "), profondeur


@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la composition est vérifiée en CI")
    posé, pool, profondeur = _liens()
    assert len(posé) == 2 and len(pool) == 2, "un lien par enfant, de chaque côté"
    assert profondeur == 2
    cas = [(nom, x, y, 1, 1) for nom, x, y in SCENARIOS]
    cas += [("racine_eteinte", 100, 50, 0, 1), ("bras_eteint", 100, 50, 1, 0)]
    runs = "\n".join(f'    joue_pose("{n}", {x}, {y}, {ra}, {ba}); joue_pool("{n}", {x}, {y}, {ra}, {ba});'
                     for n, x, y, ra, ba in cas)
    runs = f"    g_slot_depth = {profondeur};\n" + runs
    dossier = tmp_path_factory.mktemp("composition")
    (dossier / "obj_state.h").write_text("#define OBJ_STATE_STRIDE 1\n", encoding="utf-8")
    source = SONDE.replace("@PLACED@", "\n".join(posé)).replace("@POOL@", "\n".join(pool)).replace("@RUNS@", runs)
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(dossier), "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    etats: dict[tuple[str, str], list[tuple[int, ...]]] = {}
    for ligne in sortie.stdout.strip().splitlines():
        chemin, nom, *valeurs = ligne.split()
        etats.setdefault((chemin, nom), []).append(tuple(int(v) for v in valeurs[1:]))
    return etats


@pytest.mark.parametrize("nom", [s[0] for s in SCENARIOS] + ["racine_eteinte", "bras_eteint"])
def test_un_lien_pose_et_un_lien_ne_composent_pareil(etats, nom):
    """(x, y, actif) du bras puis de la main, identiques quel que soit le lien."""
    assert len(etats[("pose", nom)]) == 2
    assert etats[("pool", nom)] == etats[("pose", nom)]


def test_la_composition_place_les_enfants(etats):
    """Sans cela, des états égaux mais jamais recomposés passeraient pour une égalité."""
    (bras_x, bras_y, _a), (main_x, main_y, _a2) = etats[("pose", "neutre")]
    assert (bras_x, bras_y) == ((100 + 16) << 8, (50 + 8) << 8)
    assert (main_x, main_y) == ((100 + 24) << 8, (50 + 8) << 8)       # 8 px à droite du bras
    assert etats[("pose", "negative")][1][:2] == ((-10 + 24) << 8, (-20 + 8) << 8)   # la main suit la racine


def test_une_racine_eteinte_eteint_ses_enfants(etats):
    """Le bras et la main s'éteignent, sans être recomposés."""
    assert etats[("pose", "racine_eteinte")] == [(0, 0, 0), (0, 0, 0)]


def test_un_enfant_eteint_n_est_pas_recompose_et_eteint_les_siens(etats):
    """Le bras éteint garde sa position ; la main, dont le parent est éteint, s'éteint à son tour."""
    assert etats[("pose", "bras_eteint")] == [(0, 0, 0), (0, 0, 0)]
