"""Le noyau de rendu partagé : la fin de la phase `render` existe en UN exemplaire (`scene_render_end`), que la scène
pose ses acteurs ou les fasse naître, et ce qu'elle fait en C réel est le même après N images.

Cas de parité de la règle « posé = spawné » : le chemin des posés et celui du pool écrivent leurs sprites avant, puis
appellent la même fin ; elle ne reçoit que le premier emplacement OAM libre."""
from __future__ import annotations

import re
import subprocess

import pytest

from codegen.runtime_codegen import main_gen
from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from native_toolchain import compilateur_hote, environnement
from oam_fixtures import tout_afficher

_DEFINITION = "static void scene_render_end(int oamn) {"


class _Journal:
    def __call__(self, event, *args):
        pass


def _main_c(tmp_path, *, spawne: bool) -> str:
    """Le `main.c` d'un projet à deux scènes : l'une pose son acteur, l'autre le fait naître au tick 0."""
    p = Project.create(tmp_path / "Game", "Game")
    posee = p.active_scene
    posee.actors = [Actor(name="Hero")]
    autre = Scene(name="Born", script="assets/born.lua")
    p.scenes.append(autre)
    p.prefabs.items = [Prefab(name="Hero")] if spawne else []
    tout_afficher(p)
    if spawne:
        (p.root / "assets").mkdir(parents=True, exist_ok=True)
        (p.root / "assets" / "born.lua").write_text(
            'function on_start()\n    actor:spawn("Hero", vec2(0, 0))\nend\n', encoding="utf-8")
    data = [{"scene": s, "bg_pairs": [], "scene_actors": [(a, None) for a in s.actors],
             "extra_sprites": [], "prefab_sprites": []} for s in (posee, autre)]
    assert main_gen.generate_main(p, data, None, [], list(p.prefabs), _Journal()) is True
    return (p.src_dir / "main.c").read_text(encoding="utf-8")


@pytest.mark.parametrize("spawne", [False, True])
def test_toutes_les_scenes_finissent_leur_rendu_par_le_meme_appel(tmp_path, spawne):
    text = _main_c(tmp_path, spawne=spawne)
    assert text.count(_DEFINITION) == 1
    phases = re.findall(r"static void scene_tick_\w+_render\(void\) \{\n(.*?)\n\}\n", text, re.S)
    assert len(phases) == 2
    for corps in phases:
        assert corps.rstrip().endswith("scene_render_end(_oamn);")
        # la fin n'est plus recopiée dans la scène
        for appel in ("oam_hide_from(", "ui_list_tick();", "ui_image_update();", "text_update();", "oam_update();"):
            assert appel not in corps


def _fin_du_rendu(text: str) -> str:
    debut = text.index(_DEFINITION)
    return text[debut:text.index("\n}\n", debut) + 3]


_SONDE = r"""
#include <stdio.h>
#include <string.h>
typedef unsigned short u16;
typedef struct { u16 attr0, attr1, attr2, dummy; } S;
S shadow_oam[128];
int g_oam_hw = 0, g_oam_dropped = 0, g_affine_dropped = 0, _g_frame = 0;
static char journal[256]; static int lu = 0;
static void note(const char *m) { lu += snprintf(journal + lu, sizeof journal - lu, "%s ", m); }
static void oam_hide_from(int n) {
    for (int k = n; k < g_oam_hw; k++) shadow_oam[k].attr0 = 0x0200;
    g_oam_hw = n;
}
static void ui_list_tick(void) { note("list"); }
static void ui_image_update(void) { note("image"); }
static void text_update(void) { note("text"); }
static void oam_update(void) { note("oam"); }
static void debug_write_str(const char *s) { (void)s; note("w"); }
static void debug_write_int(int v) { (void)v; }
static void debug_flush(void) { note("flush"); }

@FIN@

/* Une image : le chemin écrit `n` sprites (des posés, ou des emplacements du pool : la fin ne le sait pas). */
static void image(int n, int perdus) {
    for (int k = 0; k < n; k++) shadow_oam[k].attr0 = 0x0100;
    g_oam_dropped = perdus;
    lu = 0; journal[0] = 0;
    scene_render_end(n);
}

int main(void) {
    /* 6 images : la dernière écrit moins que les précédentes, l'excédent doit s'éteindre */
    int suite[6] = {5, 5, 3, 3, 8, 2};
    for (int i = 0; i < 6; i++) {
        _g_frame = i * 64;
        image(suite[i], i == 2 ? 4 : 0);
        int eteints = 0, allumes = 0;
        for (int k = 0; k < 128; k++) { if (shadow_oam[k].attr0 == 0x0200) eteints++; if (shadow_oam[k].attr0 == 0x0100) allumes++; }
        printf("%d allumes=%d eteints=%d hw=%d dropped=%d journal=%s\n", i, allumes, eteints, g_oam_hw, g_oam_dropped, journal);
    }
    return 0;
}
"""


def test_la_fin_du_rendu_eteint_l_excedent_et_garde_l_ordre(tmp_path):
    """C réel : `oam_hide_from` d'abord, l'avertissement ensuite, puis l'interface, le texte et la copie OAM."""
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la fin du rendu est vérifiée en CI")
    fin = _fin_du_rendu(_main_c(tmp_path / "a", spawne=False))
    assert fin == _fin_du_rendu(_main_c(tmp_path / "b", spawne=True))      # posé ou spawné : le même texte
    (tmp_path / "sonde.c").write_text(_SONDE.replace("@FIN@", fin), encoding="utf-8")
    binaire = tmp_path / "sonde"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O1", "-w", "-o", str(binaire), str(tmp_path / "sonde.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    brut = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur)).stdout
    lignes = brut.strip().splitlines()
    assert len(lignes) == 6
    # image 0 : 5 allumés ; image 2 : 3 allumés et les 2 du dessus éteints, 4 sprites perdus dits (trame 128 & 63 == 0)
    assert lignes[0].startswith("0 allumes=5 eteints=0 hw=5 dropped=0 journal=list image text oam")
    assert lignes[2].startswith("2 allumes=3 eteints=2 hw=3 dropped=0 journal=w w flush list image text oam")
    assert lignes[5].startswith("5 allumes=2 eteints=6 hw=2")
