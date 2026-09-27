"""Le matcheur d'input RÉEL (ROADMAP « Les inputs personnalisés », étape 2) :
`held(nom, n)`, `released`, `buffered` et `input_seq_pressed` vivent en C dans
`runtime/include/runtime_api_inline.h`. Comme `ui_list_probe.c`, il n'y a pas
de jumeau Python à comparer — c'est de l'arithmétique d'état, pas un rendu que
l'éditeur doit aussi prévisualiser. Le comportement ATTENDU est donc écrit
directement dans le test, sur les points qui ne se relisent pas :

  - `held(nom, n)` : le seuil est un « depuis au moins n frames », pas un
    « exactement n » (off-by-one classique) ;
  - `released` ne regarde que le frame précédent, sans état propre ;
  - `buffered` CONSOMME quand il répond vrai, et redevient éligible au prochain
    appui frais — pas avant ;
  - une séquence enchaîne ses pas SANS relâcher tous les boutons d'un pas à
    l'autre (`down+right → right` ne relâche QUE `down`) : c'est le piège que
    l'étape 2 a mis au jour (`_input_step_entered_at`, cf. runtime_api_inline.h) ;
  - une séquence hors fenêtre, ou dans le désordre, ne matche pas.

Sans compilateur C hôte, ce fichier se saute (voir `test_text_layout_native.py`
pour l'explication complète) ; c'est la CI qui tient seule la garantie.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_DIR   = Path(__file__).resolve().parent.parent
NATIVE_DIR = Path(__file__).resolve().parent / "native"
SONDE_C    = NATIVE_DIR / "input_matcher_probe.c"
SHIM_DIR   = NATIVE_DIR / "libgba_shim"
MOTEUR_DIR = REPO_DIR / "runtime" / "include"

# Masques (cf. actor_types_static.h : BTN_*)
A, DOWN, RIGHT = 0x0001, 0x0080, 0x0010
DOWN_RIGHT = DOWN | RIGHT


def _compilateur_hote() -> str | None:
    declare = os.environ.get("CC")
    if declare:
        resolu = shutil.which(declare)
        if resolu is None:
            pytest.fail(f"CC={declare!r} est introuvable")
        return resolu
    for nom in ("cc", "gcc", "clang"):
        chemin = shutil.which(nom)
        if chemin:
            return chemin
    return None


def _environnement(compilateur: str) -> dict:
    env = dict(os.environ)
    env["PATH"] = str(Path(compilateur).parent) + os.pathsep + env.get("PATH", "")
    return env


@pytest.fixture(scope="session")
def sonde(tmp_path_factory) -> tuple[Path, dict]:
    compilateur = _compilateur_hote()
    if compilateur is None:
        message = ("aucun compilateur C hôte (cc/gcc/clang, ou CC=...) — "
                   "le matcheur d'input n'est PAS vérifié contre le vrai C")
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message + " ; il l'est en CI")

    env = _environnement(compilateur)
    binaire = tmp_path_factory.mktemp("native") / "input_matcher_probe"
    resultat = subprocess.run(
        [compilateur, "-std=c11", "-O0", "-Wall",
         "-o", str(binaire), str(SONDE_C),
         "-I", str(SHIM_DIR), "-I", str(MOTEUR_DIR)],
        capture_output=True, text=True, env=env,
    )
    if resultat.returncode != 0:
        pytest.fail(f"la sonde ne compile plus contre runtime_api_inline.h "
                    f"(code {resultat.returncode}) :\n{resultat.stderr}")
    return binaire, env


def _rejouer(sonde, frames, heldn=(), released=(), seq=(), buffered=()):
    """Rejoue `frames` (un masque par frame) et rend, par requête, la liste des
    résultats frame par frame : {"HELDN": [[...par frame...], ...], ...}."""
    champs = [len(frames), *frames]
    champs += [len(heldn), *[v for pair in heldn for v in pair]]
    champs += [len(released), *released]
    champs += [len(seq)]
    for masks, window in seq:
        champs += [len(masks), *masks, window]
    champs += [len(buffered), *[v for triple in buffered for v in triple]]

    binaire, env = sonde
    resultat = subprocess.run([str(binaire)], input=" ".join(map(str, champs)),
                              capture_output=True, text=True, env=env)
    assert resultat.returncode == 0, f"la sonde a échoué : {resultat.stderr}"

    lignes = resultat.stdout.strip().split("\n")
    out = {"HELDN": [], "RELEASED": [], "SEQ": [], "BUFFERED": []}
    for i in range(len(frames)):
        for key in out:
            parts = lignes[i * 4 + list(out).index(key)].split()
            assert parts[0] == key, (key, parts)
            out[key].append([int(v) for v in parts[1:]])
    return out


# ── held(nom, n) : depuis AU MOINS n frames ─────────────────────────

def test_held_n_est_un_seuil_pas_une_egalite(sonde):
    # A tenu aux frames 1..5 (5 frames consécutives)
    frames = [0, A, A, A, A, A, 0]
    out = _rejouer(sonde, frames, heldn=[(A, 3)])
    par_frame = [r[0] for r in out["HELDN"]]
    # faux tant que < 3 frames consécutives, vrai à partir de la 3e, et ENCORE
    # vrai à la 5e (pas une égalité stricte à 3)
    assert par_frame == [0, 0, 0, 1, 1, 1, 0]


def test_held_n_retombe_a_zero_au_relachement(sonde):
    frames = [A, A, A, 0, A, A, A]
    out = _rejouer(sonde, frames, heldn=[(A, 3)])
    par_frame = [r[0] for r in out["HELDN"]]
    assert par_frame == [0, 0, 1, 0, 0, 0, 1]


# ── released : lecture du frame précédent seulement ─────────────────

def test_released_juste_apres_le_relachement(sonde):
    frames = [0, A, A, 0, 0]
    out = _rejouer(sonde, frames, released=[A])
    assert [r[0] for r in out["RELEASED"]] == [0, 0, 0, 1, 0]


# ── buffered : consomme, redevient éligible au prochain appui frais ─

def test_buffered_repond_vrai_une_fois_puis_se_taxit(sonde):
    frames = [0, 0, A, 0, 0, 0, 0, 0]
    out = _rejouer(sonde, frames, buffered=[(0, A, 4)])
    assert [r[0] for r in out["BUFFERED"]] == [0, 0, 1, 0, 0, 0, 0, 0]


def test_buffered_fenetre_de_une_frame_ne_tamponne_rien(sonde):
    # fenêtre à 1 frame : seul l'appui du frame même compte, `frames` a un effet
    frames = [0, 0, A, 0, 0]
    out = _rejouer(sonde, frames, buffered=[(0, A, 1)])
    assert [r[0] for r in out["BUFFERED"]] == [0, 0, 1, 0, 0]


def test_buffered_redevient_eligible_a_un_nouvel_appui(sonde):
    # deux appuis distincts dans la même fenêtre glissante : chacun compte
    frames = [0, A, 0, 0, A, 0, 0, 0]
    out = _rejouer(sonde, frames, buffered=[(0, A, 5)])
    assert [r[0] for r in out["BUFFERED"]] == [0, 1, 0, 0, 1, 0, 0, 0]


# ── input_seq_pressed : le piège documenté (chaînage sans relâcher) ─

def test_quart_de_cercle_enchaine_sans_tout_relacher(sonde):
    # down, down+right (down PUIS right ajouté), right (down relâché SEUL)
    frames = [0, DOWN, DOWN_RIGHT, RIGHT, 0]
    out = _rejouer(sonde, frames, seq=[([DOWN, DOWN_RIGHT, RIGHT], 15)])
    assert [r[0] for r in out["SEQ"]] == [0, 0, 0, 1, 0]


def test_double_appui_directionnel_avec_relachement(sonde):
    frames = [0, RIGHT, 0, RIGHT]
    out = _rejouer(sonde, frames, seq=[([RIGHT, RIGHT], 15)])
    assert [r[0] for r in out["SEQ"]] == [0, 0, 0, 1]


def test_maintien_continu_ne_mime_pas_un_double_appui(sonde):
    # un seul appui tenu : ce n'est PAS deux pas, la séquence ne matche jamais
    frames = [0, RIGHT, RIGHT, RIGHT, RIGHT]
    out = _rejouer(sonde, frames, seq=[([RIGHT, RIGHT], 15)])
    assert [r[0] for r in out["SEQ"]] == [0, 0, 0, 0, 0]


def test_sequence_trop_lente_hors_fenetre_echoue(sonde):
    # fenêtre de 2 frames entre les pas ; down puis (3 frames neutres) right
    frames = [DOWN, 0, 0, 0, RIGHT]
    out = _rejouer(sonde, frames, seq=[([DOWN, RIGHT], 2)])
    assert [r[0] for r in out["SEQ"]] == [0, 0, 0, 0, 0]


def test_sequence_dans_le_desordre_echoue(sonde):
    frames = [RIGHT, 0, DOWN]
    out = _rejouer(sonde, frames, seq=[([DOWN, RIGHT], 15)])
    assert [r[0] for r in out["SEQ"]] == [0, 0, 0]
