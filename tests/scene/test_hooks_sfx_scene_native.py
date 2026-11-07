"""Les crochets d'image (`on_update`, `on_late_update`) et le SoundFx déclenché par un bouton, sur le C émis pour une
vraie scène.

Le prefab `Bell` (SoundFx sur le bouton A, script qui définit les deux crochets) naît dans le pool partagé ; un posé
prend le même chemin (`SLOT_EACH`, type lu à l'emplacement). Les lignes C sont celles du générateur : la table du
descripteur (`model_desc_lines`), puis `hook_pass_lines` et `sfx_input_pass_lines`. La sonde compte les appels de
chaque crochet, lit la position vue par `on_late_update` (écrite par `on_update` : l'ordre compte) et les sons joués.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement
from oam_fixtures import faire_naitre

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 5
APPUIS = (1, 3)        # les frames où A est pressé
SFX_DING = 5

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32; typedef int s32;
#include "actor_types_static.h"
#define SFX_DING @SFX@
Actor g_actors[@SLOTS@];
int g_spool_start = @START@, g_actor_slot_end = @START@, g_scene_placed = @START@;
u32 g_alive_bits[(@SLOTS@ + 31) / 32], g_alive_epoch;
static int pressed, sfx_calls, last_sfx, last_volume, updates, lates, seen_x;
static int input_pressed(int mask){ return pressed && mask == BTN_A; }
static void sfx_play(int id, int volume, int unused){ sfx_calls++; last_sfx = id; last_volume = volume; }
void @SYM@_on_update(Actor* a){ updates++; a->x += 256; }
void @SYM@_on_late_update(Actor* a){ lates++; seen_x = a->x >> 8; }
@TABLE@
static void tick(void){
@UPDATE@
@SFX_PASS@
@LATE@
}
int main(void){
    int s = @START@;
    for(int k = 0; k < @SLOTS@; k++){ g_actors[k] = (Actor){0}; g_actors[k].slot_index = k; }
    Actor* a = &g_actors[s];
    a->active = 1; a->alive = 1; a->type_id = @TYPE@;
    alive_bit_set(s); g_actor_slot_end = s + 1;
    for(int f = 0; f < @FRAMES@; f++){
        pressed = @PRESSED@;
        sfx_calls = 0; last_sfx = last_volume = -1;
        tick();
        printf("%d %d %d %d %d %d\n", sfx_calls, last_sfx, last_volume, updates, lates, seen_x);
    }
    return 0;
}
"""


def _emissions(tmp_path):
    from types import SimpleNamespace
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.model_desc import hook_pass_lines, model_desc_lines, sfx_input_pass_lines
    from core.models.audio import Sfx
    from core.models.components import SoundFxComponent
    from core.models.scene import Prefab, Scene
    from core.project import Project

    bell = Prefab(name="Bell")
    bell.actor.components.append(SoundFxComponent(sfx_name="Ding", trigger="a"))
    scene = Scene(name="S", actors=[])
    p = Project(tmp_path)
    p.sfx.append(Sfx(name="Ding", volume=50))
    p.scenes.items = [scene]
    p.prefabs.items = [bell]
    faire_naitre(tmp_path, scene, "Bell")
    pi = scene_pi(p, scene)
    model = next(m for m in pi if m["shared"])
    has = lambda _sym, event: event in ("on_update", "on_late_update")
    layout = SimpleNamespace(masks={})          # « a » n'est pas un accord déclaré : le bouton nu
    return {
        "sym": model["sym"],
        "table": model_desc_lines(p, scene, [], pi, [], has, layout),
        "update": hook_pass_lines(scene, pi, [], has, "on_update"),
        "late": hook_pass_lines(scene, pi, [], has, "on_late_update"),
        "sfx": sfx_input_pass_lines(p, scene, [], pi, layout),
        "type": model["root_type_id"], "start": model["spool"]["start"], "slots": model["spool"]["end"],
    }


@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    """Image par image : (sons joués, effet, volume, appels de on_update, appels de on_late_update, x vu par late)."""
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; les crochets sont vérifiés en CI")
    e = _emissions(tmp_path_factory.mktemp("crochets_scene_projet"))
    for nom in ("table", "update", "late", "sfx"):
        assert e[nom], f"{nom} : rien d'émis, la sonde ne vérifierait rien"
    pressed = "||".join(f"f=={f}" for f in APPUIS)
    source = (SONDE.replace("@SYM@", e["sym"]).replace("@TABLE@", "\n".join(e["table"]))
              .replace("@UPDATE@", "\n".join(e["update"])).replace("@LATE@", "\n".join(e["late"]))
              .replace("@SFX_PASS@", "\n".join(e["sfx"])).replace("@SFX@", str(SFX_DING))
              .replace("@FRAMES@", str(FRAMES)).replace("@PRESSED@", f"({pressed})").replace("@TYPE@", str(e["type"]))
              .replace("@START@", str(e["start"])).replace("@SLOTS@", str(e["slots"])))
    dossier = tmp_path_factory.mktemp("crochets_scene")
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    etats = [tuple(int(v) for v in ligne.split()) for ligne in sortie.stdout.strip().splitlines()]
    assert len(etats) == FRAMES
    return etats


def test_un_on_update_puis_un_on_late_update_par_image(etats):
    for f, row in enumerate(etats, start=1):
        assert row[3:] == (f, f, f)          # late voit le x écrit par update à la même image


def test_le_son_joue_seulement_a_l_appui(etats):
    assert [row[0] for row in etats] == [1 if f in APPUIS else 0 for f in range(FRAMES)]


def test_le_son_joue_est_le_bon_au_bon_volume(etats):
    from core.models.audio import volume_to_effect
    for f in APPUIS:
        assert etats[f][1:3] == (SFX_DING, volume_to_effect(50))
