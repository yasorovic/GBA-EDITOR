"""Parité posé / spawné du mouvement automatique et du sommeil Rigid.

Une vraie scène : chaque corps est un prefab, posé une fois ET spawné par le script de scène. Les lignes C sont celles
que le générateur émet pour cette scène : la table du descripteur de modèle (`model_desc_lines`), le pas commun
(`motion_helper_lines`), puis `physics_motion_lines` et `physics_sleep_lines`. Le type d'emplacement de chaque posé est
celui du layout (`OamLayout.placed_model`, posé par `scene_init`) ; un né porte le `model_id` de son modèle. Une
partie ne joue qu'un emplacement à la fois, les autres restant inactifs.

Les tables par emplacement hors d'Actor sont remises à zéro par la destruction (`actor_slot_tables_clear`), vérifié
par la sonde native `actor_box_probe.c` : ici, un emplacement neuf suffit. Voir `test_parity_posed_spawned.py`
pour la règle.
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
Actor g_actors[2 * N];
s32 g_rigid_rest[2 * N][2];
int g_spool_start = N, g_spool_hw = N, g_scene_placed = 0;
u32 g_alive_bits[1], g_alive_epoch;
static inline void actor_apply_velocity(Actor* s) { s->x+=s->vx; s->y+=s->vy; }
@HELPERS@
@TABLE@
static const u8 type_pose[N] = {@TYPES_POSES@};
static const u8 type_ne[N] = {@TYPES_NES@};

static void tick(void){
@MOTION@
@SLEEP@
}
static void rapporte(const char* chemin, int c, const char* nom, int f, const Actor* a){
    printf("%s %d %s %d %d %d %d %d %d\n", chemin, c, nom, f, a->x, a->y, a->vx, a->vy, a->physics_sleep);
}
/* Un seul emplacement vivant : le posé `c` (emplacement c), ou le né du même corps (emplacement N + c). */
static void joue(const char* chemin, int c, const char* nom, int vx, int vy){
    for(int k = 0; k < 2 * N; k++){ g_actors[k] = (Actor){0}; g_actors[k].inst = k; g_rigid_rest[k][0] = g_rigid_rest[k][1] = 0; }
    g_alive_bits[0] = 0; g_spool_hw = N; g_scene_placed = N;   /* [0, N) : les posés */
    int s = chemin[1] == 'o' && chemin[2] == 's' ? c : N + c;   /* "pose" ou "pool" */
    Actor* a = &g_actors[s];
    a->x = 10 << 8; a->y = 10 << 8; a->vx = vx; a->vy = vy; a->active = 1; a->alive = 1;
    if(s < N){ a->model = type_pose[c]; alive_bit_set(s); }
    else { a->model = type_ne[c]; alive_bit_set(s); g_spool_hw = s + 1; }
    for(int f = 0; f < @FRAMES@; f++){ tick(); rapporte(chemin, c, nom, f, a); }
}

int main(void){
@RUNS@
    return 0;
}
"""


def _scene(tmp_path):
    """Le projet : un prefab par corps, chacun posé une fois (copie liée) et spawné par le script de scène."""
    import copy
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor, Prefab, Scene
    from core.project import Project

    prefabs, posed = [], []
    for nom, mode, reglages in CORPS:
        pf = Prefab(name=nom)
        pf.actor.components += [CollisionShapeComponent(solid=True), PhysicsBodyComponent(mode=mode, **reglages)]
        prefabs.append(pf)
        posed.append(Actor(name=f"{nom}Pose", prefab_name=nom, components=copy.deepcopy(pf.actor.components)))
    scene = Scene(name="S", actors=posed, physics_enabled=True, physics_gravity_override=True,
                  physics_gravity_x=0.0, physics_gravity_y=0.25, physics_max_fall_speed=8.0,
                  physics_linear_damping=0.02, physics_sleep_enabled=True, physics_sleep_threshold=0.05,
                  physics_sleep_frames=30)
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = prefabs
    faire_naitre(tmp_path, scene, *(nom for nom, _m, _r in CORPS))
    return p, scene


def _emissions(tmp_path):
    from codegen.oam_alloc import scene_oam_layout
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.model_desc import model_desc_lines
    from codegen.runtime_codegen.physics.motion import motion_helper_lines, physics_motion_lines, physics_sleep_lines

    p, scene = _scene(tmp_path)
    pi = scene_pi(p, scene)
    actors = [(a, None) for a in scene.actors]
    lay = scene_oam_layout(p, scene)
    ids = {m["prefab"].name: m["model_id"] for m in pi if m["shared"]}
    return {
        "table": model_desc_lines(p, scene, actors, pi),
        "helpers": motion_helper_lines(),
        "motion": physics_motion_lines(scene, p.settings, actors, pi),
        "sleep": physics_sleep_lines(scene, p.settings, actors, pi),
        "types_poses": lay.placed_model,
        "types_nes": [ids[nom] for nom, _m, _r in CORPS],
    }


@pytest.fixture(scope="module")
def emissions(tmp_path_factory):
    return _emissions(tmp_path_factory.mktemp("parite_mouvement_projet"))


@pytest.fixture(scope="module")
def etats(tmp_path_factory, emissions):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la parité est vérifiée en CI")
    dossier = tmp_path_factory.mktemp("parite_mouvement")
    e = emissions
    for nom in ("table", "motion", "sleep"):
        assert e[nom], f"{nom} : rien d'émis, la sonde ne comparerait rien"
    runs = "\n".join(f'    joue("pose", {c}, "{n}", {vx}, {vy}); joue("pool", {c}, "{n}", {vx}, {vy});'
                     for c in range(len(CORPS)) for n, vx, vy in SCENARIOS)
    source = (SONDE.replace("@N@", str(len(CORPS))).replace("@FRAMES@", str(FRAMES)).replace("@RUNS@", runs)
              .replace("@HELPERS@", "\n".join(e["helpers"])).replace("@TABLE@", "\n".join(e["table"]))
              .replace("@TYPES_POSES@", ",".join(map(str, e["types_poses"])))
              .replace("@TYPES_NES@", ",".join(map(str, e["types_nes"])))
              .replace("@MOTION@", "\n".join(e["motion"])).replace("@SLEEP@", "\n".join(e["sleep"])))
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    etats: dict[tuple[str, str, str], list[tuple[int, ...]]] = {}
    for ligne in sortie.stdout.strip().splitlines():
        chemin, c, nom, _frame, *valeurs = ligne.split()
        etats.setdefault((chemin, CORPS[int(c)][0], nom), []).append(tuple(int(v) for v in valeurs))
    return etats


def test_un_pose_et_un_ne_du_meme_prefab_ont_le_meme_type(emissions):
    """Une copie posée identique au prefab prend le `model_id` du modèle né : une seule ligne de descripteur."""
    assert emissions["types_poses"] == emissions["types_nes"]
    assert len(set(emissions["types_poses"])) == len(CORPS)


@pytest.mark.parametrize("corps", [c[0] for c in CORPS])
@pytest.mark.parametrize("nom", [s[0] for s in SCENARIOS])
def test_le_mouvement_et_le_sommeil_donnent_le_meme_etat_pose_et_spawne(etats, corps, nom):
    """(x, y, vx, vy, compteur de sommeil), image par image."""
    assert len(etats[("pose", corps, nom)]) == FRAMES
    assert etats[("pool", corps, nom)] == etats[("pose", corps, nom)]


def test_la_reference_pose_s_endort_ou_derive_vraiment(etats):
    """Sans cela, des états égaux mais inertes passeraient pour une parité."""
    assert etats[("pose", "Caisse", "repos")][-1][4] == 30            # le compteur atteint le délai et s'y tient
    rapide = etats[("pose", "Caisse", "derive_rapide")]
    # Amortissement 0,02 : la vitesse décroît (251 / 256 par image) ; le corps ralentit sans s'endormir.
    assert max(etat[4] for etat in rapide) < 30 and 0 < rapide[-1][2] < 256
    lente = etats[("pose", "Caisse", "derive_lente")]
    assert lente[-1][2] == 0 and lente[-1][4] == 30                   # endormi : la vitesse est remise à zéro


def test_la_reference_pose_suit_la_gravite_de_son_type(etats):
    """Chaque mode lit sa ligne du descripteur : chute, gravité inversée, gravité ignorée, gravité sans mouvement."""
    bille = etats[("pose", "Bille", "repos")]
    assert bille[0][3] == 62 and 62 < bille[-1][3] < 8 * 256 and bille[-1][1] > 10 << 8  # (0 + 64) * 251 / 256, puis accélère
    assert etats[("pose", "Ballon", "repos")][-1][1] < 10 << 8                          # monte
    lift = etats[("pose", "Lift", "derive_rapide")][-1]
    assert lift[3] > 0 and lift[0] > (10 << 8) + 256 * 30                               # tombe ET glisse, sans amortissement
    rail = etats[("pose", "Rail", "derive_rapide")][-1]
    assert rail[3] == 0 and rail[1] == 10 << 8 and rail[0] == (10 << 8) + 256 * FRAMES  # aucune gravité
    heros = etats[("pose", "Heros", "repos")][-1]
    assert heros[3] == 8 * 256 and heros[1] == 10 << 8                                  # la vitesse monte, la position reste
