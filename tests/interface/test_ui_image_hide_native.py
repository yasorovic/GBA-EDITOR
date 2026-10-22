"""Masquer ou déplacer une image BG rend ce qu'elle recouvrait (le fond du conteneur), au lieu de trouer la tilemap.

`ui_image_clear_bg` écrivait la tuile 0 : le cadre d'un dialogue perdait ses cases sous le portrait masqué, et le décor
y apparaissait. Ce test compile le VRAI `gba_engine.h` (cf. `tests/native/ui_image_probe.c`, qui substitue un tableau à la VRAM)
et lit les cases de l'image à chaque étape. Sans compilateur C hôte il se saute, comme les autres tests natifs : la CI le tient.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

REPO_DIR = Path(__file__).resolve().parents[2]
NATIVE_DIR = REPO_DIR / "tests" / "native"
FOND = "2005"          # l'entrée posée partout par la sonde : le « cadre » du conteneur


@pytest.fixture(scope="module")
def cases(tmp_path_factory) -> dict:
    compilateur = compilateur_hote()
    if compilateur is None:
        message = "aucun compilateur C hôte : le masquage d'une image BG n'est PAS vérifié"
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message + " ; il l'est en CI")
    env = environnement(compilateur)
    binaire = tmp_path_factory.mktemp("native") / "ui_image_probe"
    resultat = subprocess.run(
        [compilateur, "-std=c11", "-O0", "-o", str(binaire), str(NATIVE_DIR / "ui_image_probe.c"),
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


IMAGE = [(1, 1), (2, 1), (1, 2), (2, 2)]        # les cases de l'image (16x16 px posée en (8, 8))


def test_posee_l_image_remplace_le_fond_sur_ses_cases(cases):
    assert all(cases["pose"][cell] != FOND for cell in IMAGE)
    assert cases["pose"][(0, 0)] == FOND and cases["pose"][(3, 1)] == FOND


def test_masquee_l_image_rend_le_fond_du_conteneur(cases):
    assert all(cases["masque"][cell] == FOND for cell in IMAGE)


def test_reposee_l_image_revient(cases):
    assert all(cases["repose"][cell] != FOND for cell in IMAGE)


def test_deplacee_l_image_libere_ses_anciennes_cases(cases):
    assert cases["deplace"][(1, 1)] == FOND and cases["deplace"][(1, 2)] == FOND
    assert all(cases["deplace"][cell] != FOND for cell in [(2, 1), (3, 1), (2, 2), (3, 2)])
