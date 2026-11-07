"""Parité posé / spawné de la composition parent → enfant.

Même hiérarchie, deux façons de l'avoir : une racine, un bras (enfant de la racine) et une main (enfant du bras)
posés dans la scène, ou ces trois pièces nées ensemble dans le pool comme un prefab à parties. Les lignes C sont
celles de `parent_compose_lines` (posé) et `pool_compose_lines` (pool), compilées avec le vrai `gba_sincos`.
À une racine donnée (position, rotation, échelle), le bras et la main doivent tomber au même endroit, avec la même
rotation et la même échelle. Les sprites sont absents : la propagation de `visible` n'est pas couverte.

Voir `test_parity_posed_spawned.py` pour la règle.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

# Pose authorée de la hiérarchie, dans le MONDE d'un template posé à l'origine : (x, y, rotation, échelle %).
BRAS = (16, 8, 0, 100)
MAIN = (24, 8, 30, 200)
RACINE_POSEE = (100, 50)         # où la racine est posée dans la scène; le prefab, lui, est à l'origine

# (nom, x, y, rotation, échelle Q8) de la racine à l'exécution.
SCENARIOS = [
    ("neutre", 100, 50, 0, 256),
    ("tournee_90", 100, 50, 90, 256),
    ("tournee_45", 37, 12, 45, 256),
    ("echelle_double", 100, 50, 0, 512),
    ("tournee_et_echelle", 80, 20, 30, 384),
    ("tournee_negative", 10, 10, -60, 256),
]

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
Actor g_actors[8];
int g_spool_start, g_spool_hw, g_scene_placed;
u32 g_alive_bits[1], g_alive_epoch;
#define EASE_IN 0
#define EASE_OUT 1
#define EASE_IN_OUT 2
void window_set(int id,int x,int y,int w,int h);
void window_show(int id,int on);
#include "runtime_api_inline.h"

static void membre(int k, int x, int y, int rot, int sx, int sy, int actif){
    g_actors[k] = (Actor){0};
    g_actors[k].inst = k; g_actors[k].alive = 1; g_actors[k].active = actif;
    g_actors[k].x = x; g_actors[k].y = y; g_actors[k].rotation = rot; g_actors[k].scale_x = sx; g_actors[k].scale_y = sy;
}
static void rapporte(const char* chemin, const char* nom, int base){
    for(int k = 1; k <= 2; k++){
        const Actor* a = &g_actors[base + k];
        printf("%s %s %d %d %d %d %d %d %d\n", chemin, nom, k, a->x, a->y, a->rotation, a->scale_x, a->scale_y, a->active);
    }
}
/* Posé : racine 0, bras 1, main 2. */
static void joue_pose(const char* nom, int x, int y, int rot, int echelle, int racine_active, int bras_actif){
    membre(0, x << 8, y << 8, rot, echelle, echelle, racine_active);
    membre(1, 0, 0, 0, 256, 256, bras_actif);
    membre(2, 0, 0, 0, 256, 256, 1);
@PLACED@
    rapporte("pose", nom, 0);
}
/* Pool : racine 4, bras 5, main 6 (un groupe contigu de 3 emplacements, modèle 1 puis 2 et 3). */
static void joue_pool(const char* nom, int x, int y, int rot, int echelle, int racine_active, int bras_actif){
    membre(4, x << 8, y << 8, rot, echelle, echelle, racine_active); g_actors[4].model = 1;
    membre(5, 0, 0, 0, 256, 256, bras_actif); g_actors[5].model = 2;
    membre(6, 0, 0, 0, 256, 256, 1); g_actors[6].model = 3;
    g_spool_start = 4; g_spool_hw = 7;
    alive_bit_set(4); alive_bit_set(5); alive_bit_set(6);
@POOL@
    rapporte("pool", nom, 4);
}

int main(void){
@RUNS@
    return 0;
}
"""


def _hierarchie():
    from core.models.scene import Actor, Prefab

    def piece(nom, pose, parent=None, origine=(0, 0)):
        x, y, rotation, echelle = pose
        return Actor(name=nom, x=origine[0] + x, y=origine[1] + y, rotation=rotation,
                     scale_x=echelle / 100, scale_y=echelle / 100, parent=parent)

    racine = Actor(name="Racine", x=RACINE_POSEE[0], y=RACINE_POSEE[1])
    posés = [racine, piece("Bras", BRAS, "Racine", RACINE_POSEE), piece("Main", MAIN, "Bras", RACINE_POSEE)]
    prefab = Prefab(name="Racine")
    prefab.children = [piece("Bras", BRAS), piece("Main", MAIN, "Bras")]
    return posés, prefab


def _emissions():
    from codegen.runtime_codegen.gen_pool import parent_compose_lines, pool_compose_lines

    posés, prefab = _hierarchie()
    posé = parent_compose_lines([(a, None) for a in posés], 0, [-1] * len(posés))
    modele = {"prefab": prefab, "shared": True, "model_id": 1, "group": 3, "member_entries": [-1, -1, -1],
              "spool": {"entries": False}}
    return posé, pool_compose_lines([modele])


@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la parité est vérifiée en CI")
    posé, pool = _emissions()
    assert posé, "le chemin posé n'émet aucune composition : la sonde ne comparerait rien"
    assert pool, "le chemin du pool n'émet aucune composition : la sonde ne comparerait rien"
    cas = [(nom, x, y, rot, e, 1, 1) for nom, x, y, rot, e in SCENARIOS]
    cas += [("racine_eteinte", 100, 50, 0, 256, 0, 1), ("bras_eteint", 100, 50, 0, 256, 1, 0)]
    runs = "\n".join(f'    joue_pose("{n}", {x}, {y}, {r}, {e}, {ra}, {ba}); joue_pool("{n}", {x}, {y}, {r}, {e}, {ra}, {ba});'
                     for n, x, y, r, e, ra, ba in cas)
    dossier = tmp_path_factory.mktemp("parite_composition")
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


@pytest.mark.parametrize("nom", [s[0] for s in SCENARIOS])
def test_la_composition_donne_le_meme_etat_pose_et_spawne(etats, nom):
    """(x, y, rotation, échelle x, échelle y, actif) du bras puis de la main, identiques pour les deux chemins."""
    assert len(etats[("pose", nom)]) == 2
    assert etats[("pool", nom)] == etats[("pose", nom)]


def test_la_reference_pose_compose_vraiment(etats):
    """Sans cela, des états égaux mais jamais recomposés passeraient pour une parité."""
    (bras_x, bras_y, bras_rot, bras_sx, _sy, _a), (main_x, main_y, main_rot, main_sx, _sy2, _a2) = etats[("pose", "neutre")]
    assert (bras_x, bras_y, bras_rot, bras_sx) == ((100 + 16) << 8, (50 + 8) << 8, 0, 256)
    assert (main_x, main_y) == ((100 + 24) << 8, (50 + 8) << 8)       # 8 px à droite du bras, sans rotation parente
    assert (main_rot, main_sx) == (30, 512)
    assert etats[("pose", "tournee_90")][0][2] == 90                  # le bras tourne avec la racine


@pytest.mark.xfail(strict=True, reason=(
    "écart de règle : le pool éteint le sous-arbre d'une racine éteinte (`pool_compose_lines`), le posé ne le fait "
    "pas (`parent_compose_lines` ne lit pas `active`; `actor_set_active` n'écrit que l'acteur). À trancher : une seule "
    "règle pour les deux, puis retirer ce xfail."))
def test_une_racine_eteinte_eteint_ses_enfants_posee_comme_spawnee(etats):
    assert etats[("pool", "racine_eteinte")] == etats[("pose", "racine_eteinte")]


@pytest.mark.xfail(strict=True, reason=(
    "écart de règle : le posé recompose un enfant éteint (position et échelle écrites), le pool ne compose pas un "
    "enfant éteint (`if(g_actors[_sK].active)`), et sa propre descendance (la main) se compose alors sur la position "
    "périmée de ce parent : (2048, 0) au lieu de (31744, 14848). À trancher, puis retirer ce xfail."))
def test_un_enfant_eteint_n_est_pas_recompose_pose_comme_spawne(etats):
    assert etats[("pool", "bras_eteint")] == etats[("pose", "bras_eteint")]
