"""Équivalence entre l'aperçu Python et le moteur C — le test que la
documentation réclamait sans l'avoir.

ARCHITECTURE.md range `core/engine_emulation/` sous une mise en garde explicite :
« ce que l'éditeur REFAIT en Python parce que la console le fait en C — DEUX
implémentations à tenir d'accord ». Le risque n'est pas qu'une des deux soit
fausse, c'est qu'elles DÉRIVENT. Et une dérive ne se manifeste ni par une
exception ni par un test rouge : elle se manifeste par un aperçu qui ne
correspond plus à la ROM, des mois après le commit qui l'a causée.

Ce fichier compile le VRAI `runtime/include/gba_engine.h` (via
`tests/native/text_layout_probe.c`), lui passe les cas de `text_layout_cases.py`,
et compare glyphe par glyphe avec ce que `layout_text()` a placé.

CE QU'IL FAUT SAVOIR AVANT DE S'ÉTONNER D'UN SAUT. Le test a besoin d'un
compilateur C pour la machine HÔTE — devkitPro n'en fournit pas, son
`arm-none-eabi-gcc` produit du code ARM qu'on ne peut pas exécuter ici. Sous
Windows, msys2 en donne un (`C:/msys64/ucrt64/bin/gcc.exe`) ; il suffit qu'il
soit sur le PATH, ou désigné par `CC`. Sans compilateur, ce fichier se saute, et
c'est la CI (ubuntu-latest) qui tient seule la garantie. **Un saut n'est pas un
succès** : si la ligne « skipped » apparaît en CI, c'est que le compilateur a
disparu, pas que le test s'est amélioré.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from core.engine_emulation.text_layout import layout_text
from native_toolchain import compilateur_hote, environnement
from text_layout_cases import CAS, police_a_glyphe_large, table_runtime

REPO_DIR    = Path(__file__).resolve().parents[2]
NATIVE_DIR  = Path(__file__).resolve().parents[1] / "native"
SONDE_C     = NATIVE_DIR / "text_layout_probe.c"
SHIM_DIR    = NATIVE_DIR / "libgba_shim"
MOTEUR_DIR  = REPO_DIR / "runtime" / "include"

ALIGNEMENTS = {"left": 0, "center": 1, "right": 2}   # cf. TEXT_ALIGN_* (gba_engine.h)


@pytest.fixture(scope="session")
def sonde(tmp_path_factory) -> tuple[Path, dict]:
    """Compile la sonde une fois pour toute la session."""
    compilateur = compilateur_hote()
    if compilateur is None:
        # La CI pose `GBA_TESTS_REQUIRE_NATIVE` : c'est elle qui porte la
        # garantie, un saut y serait un trou silencieux dans la couverture, pas
        # une tolérance. En local le saut reste normal — tout le monde n'a pas
        # de compilateur hôte sous la main.
        message = ("aucun compilateur C hôte (cc/gcc/clang, ou CC=...) — "
                   "l'équivalence Python/C n'est PAS vérifiée")
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message + " ; elle l'est en CI")

    env = environnement(compilateur)
    binaire = tmp_path_factory.mktemp("native") / "text_layout_probe"
    resultat = subprocess.run(
        [compilateur, "-std=c11", "-O0", "-Wall",
         "-o", str(binaire), str(SONDE_C),
         "-I", str(SHIM_DIR), "-I", str(MOTEUR_DIR)],
        capture_output=True, text=True, env=env,
    )
    if resultat.returncode != 0:
        pytest.fail(f"la sonde ne compile plus contre gba_engine.h "
                    f"(code {resultat.returncode}) :\n{resultat.stderr}")
    return binaire, env


def _interroger_le_moteur(sonde: tuple[Path, dict], table: dict, texte: str,
                          largeur: int, hauteur: int, align: str):
    """Fait poser `texte` par le moteur C et rend [(index de glyphe, x, y)]
    plus l'étendue préparée, en tuiles."""
    codepoints = [ord(c) for c in texte]
    champs: list[int] = [table["line_h"], table["cell_w"], table["composited"],
                         len(table["cp"])]
    for cle in ("cp", "adv", "gw", "gh", "seq_off", "seq_len"):
        champs += table[cle]
    champs += [len(table["seq"])] + table["seq"]
    champs += [largeur, hauteur, largeur // 8, ALIGNEMENTS[align]]
    champs += [len(codepoints)] + codepoints

    binaire, env = sonde
    resultat = subprocess.run([str(binaire)], input=" ".join(str(v) for v in champs),
                              capture_output=True, text=True, env=env)
    assert resultat.returncode == 0, f"la sonde a échoué : {resultat.stderr}"

    lignes = resultat.stdout.split()
    assert lignes[0] == "CAP"
    n = int(lignes[1])
    poses = [(int(lignes[2 + 3 * k + 2]), int(lignes[2 + 3 * k]),
              int(lignes[2 + 3 * k + 1])) for k in range(n)]
    reste = lignes[2 + 3 * n:]
    assert reste[0] == "SIZE"
    return poses, (int(reste[1]), int(reste[2]))


def _pose_python(font, table: dict, texte: str, largeur: int, hauteur: int,
                 align: str):
    """La même chose côté aperçu, exprimée dans les index du moteur pour être
    comparable."""
    index = {tuple(seq): i for i, seq in enumerate(table["glyphes"])}
    out, _ = layout_text(font, texte, largeur, hauteur, align)
    return [(index[tuple(ord(c) for c in g.char)], x, y) for g, x, y in out]


@pytest.mark.parametrize("cas", CAS, ids=[c[0] for c in CAS])
def test_le_moteur_et_l_apercu_posent_les_memes_glyphes(sonde, cas):
    nom, fabrique, texte, largeur, hauteur, align = cas
    font = fabrique()
    table = table_runtime(font)

    moteur, _ = _interroger_le_moteur(sonde, table, texte, largeur, hauteur, align)
    apercu = _pose_python(font, table, texte, largeur, hauteur, align)

    assert moteur == apercu, (
        f"« {nom} » : l'aperçu et la console ne placent pas le texte au même "
        f"endroit.\n  moteur C : {moteur}\n  aperçu Py : {apercu}")


@pytest.mark.parametrize("cas", CAS, ids=[c[0] for c in CAS])
def test_la_surface_preparee_couvre_ce_qui_est_ecrit(sonde, cas):
    """Invariant INTERNE au moteur, sans jumeau Python : `text_render_cp_al`
    mesure d'abord (`measure = 1`) pour préparer une surface, puis dessine. Si
    les deux passes de `text_layout` ne s'accordent pas, un glyphe atterrit dans
    une tuile que personne n'a effacée — ce qui s'y trouvait reste visible
    dessous."""
    _, fabrique, texte, largeur, hauteur, align = cas
    table = table_runtime(fabrique())

    poses, (w, h) = _interroger_le_moteur(sonde, table, texte, largeur, hauteur,
                                          align)
    for gi, x, y in poses:
        assert x // 8 < w, f"glyphe à x={x} hors de la surface préparée ({w} tuiles)"
        assert y // 8 < h, f"glyphe à y={y} hors de la surface préparée ({h} tuiles)"


@pytest.mark.xfail(strict=True, reason=(
    "DIVERGENCE CONNUE, constatée le 2026-08-13 : dans une boîte plus étroite "
    "qu'un glyphe, l'aperçu et le moteur ne font pas la même chose. Le moteur "
    "refuse de dessiner le glyphe (`text_glyph_fits`) et garde la ligne "
    "courante — sa coupe au glyphe est gardée par `x > 0` (text_scan_line), qui "
    "empêche une boîte trop étroite de ne jamais avancer. L'aperçu Python n'a "
    "ni cette garde ni ce test : il descend d'une ligne et POSE le glyphe en "
    "débordant, décalant tout le reste. Marqué strict : le jour où "
    "text_layout.py gagne la garde, ce test passera, et il faudra retirer "
    "cette marque."))
def test_boite_plus_etroite_qu_un_glyphe(sonde):
    font = police_a_glyphe_large()
    table = table_runtime(font)
    moteur, _ = _interroger_le_moteur(sonde, table, "WA", 8, 32, "left")
    apercu = _pose_python(font, table, "WA", 8, 32, "left")
    assert moteur == apercu


def test_la_sonde_refuse_un_texte_trop_long(sonde):
    """Garde de la sonde, pas du moteur : au-delà du budget de capture le moteur
    se remettrait à écrire en VRAM, à une adresse que ce processus n'a pas. Mieux
    vaut un refus net qu'un segfault que personne ne saurait lire."""
    table = table_runtime(CAS[0][1]())
    with pytest.raises(AssertionError, match="la sonde a échoué"):
        _interroger_le_moteur(sonde, table, "A" * 33, 240, 160, "left")
