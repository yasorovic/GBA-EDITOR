"""La copie des palettes en RAM : les écrivains ne touchent plus la mémoire de palettes, `palette_commit()` y recopie la
plage modifiée juste après le VBlank.

La sonde native (`tests/native/palette_probe.c`) compile le VRAI `gba_engine.h` en substituant un tableau à la mémoire de
palettes. Sans compilateur C hôte elle se saute, comme les autres tests natifs : la CI la tient. Le second test lit le
`main.c` émis pour une vraie scène.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from codegen.runtime_codegen import main_gen
from core.project import Project
from native_toolchain import compilateur_hote, environnement

REPO_DIR = Path(__file__).resolve().parents[2]
NATIVE_DIR = REPO_DIR / "tests" / "native"
INTACTE = "7777"


@pytest.fixture(scope="module")
def etapes(tmp_path_factory) -> dict:
    compilateur = compilateur_hote()
    if compilateur is None:
        message = "aucun compilateur C hôte : la copie des palettes n'est PAS vérifiée"
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message + " ; elle l'est en CI")
    env = environnement(compilateur)
    binaire = tmp_path_factory.mktemp("native") / "palette_probe"
    resultat = subprocess.run(
        [compilateur, "-std=c11", "-O0", "-o", str(binaire), str(NATIVE_DIR / "palette_probe.c"),
         "-I", str(NATIVE_DIR / "libgba_shim"), "-I", str(REPO_DIR / "runtime" / "include")],
        capture_output=True, text=True, env=env)
    if resultat.returncode != 0:
        pytest.fail(f"la sonde ne compile plus contre gba_engine.h :\n{resultat.stderr[-2000:]}")
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=env).stdout
    out: dict = {}
    for ligne in sortie.splitlines():
        etape, pool, index, valeur = ligne.split()
        out.setdefault(etape, {})[(int(pool), int(index))] = valeur
    return out


BANQUE_3 = range(48, 64)


def test_une_ecriture_n_atteint_pas_la_memoire_de_palettes_avant_le_vblank(etapes):
    assert all(valeur == INTACTE for valeur in etapes["ecrite"].values())


def test_le_commit_recopie_la_banque_ecrite_et_rien_d_autre(etapes):
    recopiee = etapes["recopiee"]
    assert [recopiee[(0, i)] for i in BANQUE_3] == ["0000"] + [f"02{c:02x}" for c in range(1, 16)]
    assert recopiee[(0, 47)] == recopiee[(0, 64)] == INTACTE
    assert all(recopiee[(1, i)] == INTACTE for i in range(47, 65))


def test_un_commit_sans_ecriture_ne_recopie_rien(etapes):
    assert etapes["rien_a_recopier"][(0, 48)] == "1111"


def test_le_pool_obj_a_sa_propre_plage(etapes):
    obj = etapes["obj"]
    assert [obj[(1, i)] for i in BANQUE_3] == ["0000"] + [f"01{c:02x}" for c in range(1, 16)]
    assert obj[(0, 48)] == "1111"     # le pool BG n'a pas été recopié une seconde fois


class _Journal:
    def __call__(self, event, *args):
        pass


def test_le_main_emis_ecrit_les_palettes_par_la_copie_et_les_recopie_apres_le_vblank(tmp_path):
    p = Project.create(tmp_path / "Game", "Game")
    scene = p.active_scene
    data = [{"scene": scene, "bg_pairs": [], "scene_actors": [], "extra_sprites": [], "prefab_sprites": []}]
    assert main_gen.generate_main(p, data, None, [], [], _Journal()) is True
    main_c = (p.src_dir / "main.c").read_text(encoding="utf-8")

    assert "VBlankIntrWait();\n        palette_commit();" in main_c
    assert "palette_write(PAL_POOL_BG, 0, &backdrop, 1);" in main_c
    assert "PAL_BG_RAM" not in main_c and "PAL_OBJ_RAM" not in main_c
