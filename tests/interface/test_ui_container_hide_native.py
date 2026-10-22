"""`hide()` sur un CONTENEUR efface son fond (écrit en tuiles à l'init) ; `show()` le repose, avec ses enfants.

Le cadre d'un dialogue n'est pas une image : `scene_init` l'écrit une fois dans la tilemap, et le moteur ne savait ni l'effacer
ni le reposer, donc `hide()` ne cachait que le texte et les images posées dessus. Ce test compile le VRAI `gba_engine.h`
(cf. `tests/native/ui_fill_probe.c`, qui substitue un tableau à la VRAM) et lit les cases à chaque étape. Sans compilateur C
hôte il se saute, comme les autres tests natifs : la CI le tient.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

REPO_DIR = Path(__file__).resolve().parents[2]
NATIVE_DIR = REPO_DIR / "tests" / "native"
FOND, VIDE = "2005", "0000"
IMAGE = [(1, 1), (2, 1), (1, 2), (2, 2)]            # l'image 16x16 px posée en (8, 8)
CADRE = [(c, r) for r in range(3) for c in range(4)]  # le fond du conteneur : 4x3 cases


def _etapes(tmp_path_factory, cache_au_depart: bool) -> dict:
    compilateur = compilateur_hote()
    if compilateur is None:
        message = "aucun compilateur C hôte : le masquage d'un conteneur n'est PAS vérifié"
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message + " ; il l'est en CI")
    env = environnement(compilateur)
    binaire = tmp_path_factory.mktemp("native") / "ui_fill_probe"
    options = ["-DAU_DEPART_CACHE"] if cache_au_depart else []
    resultat = subprocess.run(
        [compilateur, "-std=c11", "-O0", *options, "-o", str(binaire), str(NATIVE_DIR / "ui_fill_probe.c"),
         "-I", str(NATIVE_DIR / "libgba_shim"), "-I", str(REPO_DIR / "runtime" / "include")],
        capture_output=True, text=True, env=env)
    if resultat.returncode != 0:
        pytest.fail(f"la sonde ne compile plus contre gba_engine.h :\n{resultat.stderr[-2000:]}")
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=env).stdout
    etapes: dict = {}
    for ligne in sortie.splitlines():
        etape, col, row, valeur = ligne.split()
        etapes.setdefault(etape, {})[(int(col), int(row))] = valeur
    return etapes


@pytest.fixture(scope="module")
def visible(tmp_path_factory) -> dict:
    return _etapes(tmp_path_factory, cache_au_depart=False)


@pytest.fixture(scope="module")
def cache(tmp_path_factory) -> dict:
    return _etapes(tmp_path_factory, cache_au_depart=True)


def test_le_fond_est_pose_a_l_init_quand_le_conteneur_est_visible(visible):
    assert all(visible["init"][cell] == FOND for cell in CADRE)


def test_masquer_le_conteneur_efface_son_fond_et_ses_enfants(visible):
    assert all(visible["cache"][cell] == VIDE for cell in CADRE)


def test_l_image_masquee_plus_tard_ne_repose_pas_le_fond(visible):
    """L'image rend ce qu'elle recouvrait à sa prochaine mise à jour : le conteneur étant caché, c'est du vide, pas le cadre."""
    assert all(visible["cache_puis_image"][cell] == VIDE for cell in CADRE)


def test_remontrer_le_conteneur_repose_le_fond_et_l_image(visible):
    assert all(visible["revient"][cell] == FOND for cell in CADRE if cell not in IMAGE)
    assert all(visible["revient"][cell] not in (FOND, VIDE) for cell in IMAGE)


def test_masquer_puis_remontrer_dans_la_meme_frame_ne_perd_pas_l_image(visible):
    assert all(visible["meme_frame"][cell] not in (FOND, VIDE) for cell in IMAGE)


def test_un_conteneur_cache_au_depart_n_est_pas_dessine(cache):
    assert all(cache["init"][cell] == VIDE for cell in CADRE)
    assert all(cache["pose"][cell] == VIDE for cell in CADRE)       # l'image, enfant caché, ne se pose pas non plus


def test_un_conteneur_cache_au_depart_apparait_au_show(cache):
    assert all(cache["revient"][cell] == FOND for cell in CADRE if cell not in IMAGE)
