"""Le mouvement automatique et le sommeil Rigid, sur le C émis pour une vraie scène.

Chaque corps est un prefab spawné par le script de scène ; un posé prend le même chemin (`SLOT_EACH`, type lu à
l'emplacement). Les lignes C sont la table du descripteur de modèle (`model_desc_lines`), le pas commun
(`motion_helper_lines`), puis `physics_motion_lines` et `physics_sleep_lines`. Un seul corps vit à la fois, à
l'emplacement de son modèle dans le pool.

Les tables par emplacement hors d'Actor sont remises à zéro par la destruction (`actor_slot_tables_clear`), vérifié
par la sonde native `actor_box_probe.c` : ici, un emplacement neuf suffit.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement
from oam_fixtures import faire_naitre

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 40

# Les corps : (nom du prefab, mode, réglages du PhysicsBody). Gravité de scène 0,25 px par image², chute max 8.
CORPS = [
    ("Caisse", "RigidBody", {"gravity_scale": 0.0}),     # sans gravité : isole le sommeil
    ("Bille", "RigidBody", {}),                          # gravité, amortissement, chute maximale
    ("Ballon", "RigidBody", {"gravity_scale": -0.5}),    # gravité inversée et réduite
    ("Lift", "KinematicBody", {}),                       # gravité de scène, vitesse intégrée
    ("Rail", "KinematicBody", {"use_scene_gravity": False}),
    ("Heros", "CharacterBody", {}),                      # gravité seule : son script l'applique
]

# (nom, vx, vy) en Q8, au départ. Le sommeil par défaut : 30 images, seuil 0,05 px.
SCENARIOS = [
    ("repos", 0, 0),
    ("derive_rapide", 256, 0),
    ("derive_lente", 3, 0),
]

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32; typedef int s32;
#include "actor_types_static.h"
#define N @N@
Actor g_actors[@SLOTS@];
s32 g_rigid_rest[@SLOTS@][2];
int g_spool_start = @START@, g_actor_slot_end = @START@, g_scene_placed = @START@;
u32 g_alive_bits[(@SLOTS@ + 31) / 32], g_alive_epoch;
@HELPERS@
@TABLE@
static const u8 type_ne[N] = {@TYPES@};
static const int slot_ne[N] = {@SLOTS_NES@};

static void tick(void){
@MOTION@
@SLEEP@
}
static void joue(int c, const char* nom, int vx, int vy){
    for(int k = 0; k < @SLOTS@; k++){ g_actors[k] = (Actor){0}; g_actors[k].slot_index = k; g_rigid_rest[k][0] = g_rigid_rest[k][1] = 0; }
    for(int k = 0; k < (@SLOTS@ + 31) / 32; k++) g_alive_bits[k] = 0;
    int s = slot_ne[c];
    Actor* a = &g_actors[s];
    a->x = 10 << 8; a->y = 10 << 8; a->vx = vx; a->vy = vy; a->active = 1; a->alive = 1;
    a->type_id = type_ne[c]; alive_bit_set(s); g_actor_slot_end = s + 1;
    for(int f = 0; f < @FRAMES@; f++){
        tick();
        printf("%d %s %d %d %d %d %d\n", c, nom, a->x, a->y, a->vx, a->vy, a->physics_sleep);
    }
}

int main(void){
@RUNS@
    return 0;
}
"""


def _emissions(tmp_path):
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.model_desc import model_desc_lines
    from codegen.runtime_codegen.physics.motion import motion_helper_lines, physics_motion_lines, physics_sleep_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Prefab, Scene
    from core.project import Project

    prefabs = []
    for nom, mode, reglages in CORPS:
        pf = Prefab(name=nom)
        pf.actor.components += [CollisionShapeComponent(solid=True), PhysicsBodyComponent(mode=mode, **reglages)]
        prefabs.append(pf)
    scene = Scene(name="S", actors=[], physics_enabled=True, physics_gravity_override=True,
                  physics_gravity_x=0.0, physics_gravity_y=0.25, physics_max_fall_speed=8.0,
                  physics_linear_damping=0.02, physics_sleep_enabled=True, physics_sleep_threshold=0.05,
                  physics_sleep_frames=30)
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = prefabs
    faire_naitre(tmp_path, scene, *(nom for nom, _m, _r in CORPS))
    pi = scene_pi(p, scene)
    models = {m["prefab"].name: m for m in pi if m["shared"]}
    spool = models[CORPS[0][0]]["spool"]
    return {
        "table": model_desc_lines(p, scene, [], pi),
        "helpers": motion_helper_lines(),
        "motion": physics_motion_lines(scene, p.settings, [], pi),
        "sleep": physics_sleep_lines(scene, p.settings, [], pi),
        "types": [models[nom]["root_type_id"] for nom, _m, _r in CORPS],
        "start": spool["start"], "slots": spool["end"],
    }


@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    """Par (corps, scénario), image par image : (x, y, vx, vy, compteur de sommeil)."""
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; le mouvement est vérifié en CI")
    e = _emissions(tmp_path_factory.mktemp("mouvement_scene_projet"))
    for nom in ("table", "motion", "sleep"):
        assert e[nom], f"{nom} : rien d'émis, la sonde ne vérifierait rien"
    assert e["slots"] >= e["start"] + len(CORPS)
    runs = "\n".join(f'    joue({c}, "{n}", {vx}, {vy});' for c in range(len(CORPS)) for n, vx, vy in SCENARIOS)
    source = (SONDE.replace("@N@", str(len(CORPS))).replace("@FRAMES@", str(FRAMES)).replace("@RUNS@", runs)
              .replace("@HELPERS@", "\n".join(e["helpers"])).replace("@TABLE@", "\n".join(e["table"]))
              .replace("@TYPES@", ",".join(map(str, e["types"])))
              .replace("@SLOTS_NES@", ",".join(str(e["start"] + c) for c in range(len(CORPS))))
              .replace("@START@", str(e["start"])).replace("@SLOTS@", str(e["slots"]))
              .replace("@MOTION@", "\n".join(e["motion"])).replace("@SLEEP@", "\n".join(e["sleep"])))
    dossier = tmp_path_factory.mktemp("mouvement_scene")
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    etats: dict[tuple[str, str], list[tuple[int, ...]]] = {}
    for ligne in sortie.stdout.strip().splitlines():
        c, nom, *valeurs = ligne.split()
        etats.setdefault((CORPS[int(c)][0], nom), []).append(tuple(int(v) for v in valeurs))
    assert all(len(v) == FRAMES for v in etats.values())
    return etats


def test_un_rigid_au_repos_s_endort_au_bout_du_delai(etats):
    assert etats[("Caisse", "repos")][-1][4] == 30            # le compteur atteint le délai et s'y tient


def test_un_rigid_lent_s_endort_et_sa_vitesse_est_remise_a_zero(etats):
    lente = etats[("Caisse", "derive_lente")]
    assert lente[-1][2] == 0 and lente[-1][4] == 30


def test_un_rigid_rapide_est_amorti_sans_s_endormir(etats):
    # Amortissement 0,02 : la vitesse décroît (251 / 256 par image) ; le corps ralentit sans s'endormir.
    rapide = etats[("Caisse", "derive_rapide")]
    assert max(etat[4] for etat in rapide) < 30 and 0 < rapide[-1][2] < 256


def test_un_rigid_tombe_avec_la_gravite_de_scene_amortie(etats):
    bille = etats[("Bille", "repos")]
    assert bille[0][3] == 62 and 62 < bille[-1][3] < 8 * 256 and bille[-1][1] > 10 << 8  # (0 + 64) * 251 / 256


def test_une_gravite_inversee_fait_monter_le_rigid(etats):
    assert etats[("Ballon", "repos")][-1][1] < 10 << 8


def test_un_kinematic_tombe_et_glisse_sans_amortissement(etats):
    lift = etats[("Lift", "derive_rapide")][-1]
    assert lift[3] > 0 and lift[0] > (10 << 8) + 256 * 30


def test_un_kinematic_sans_gravite_de_scene_ne_fait_que_glisser(etats):
    rail = etats[("Rail", "derive_rapide")][-1]
    assert rail[3] == 0 and rail[1] == 10 << 8 and rail[0] == (10 << 8) + 256 * FRAMES


def test_un_character_recoit_la_gravite_sans_que_sa_position_bouge(etats):
    heros = etats[("Heros", "repos")][-1]
    assert heros[3] == 8 * 256 and heros[1] == 10 << 8        # son script applique la vitesse, pas la passe
