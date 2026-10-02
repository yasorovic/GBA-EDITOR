"""Le contrôle « toute entrée du catalogue de libellés est citée » (tools/check_architecture)
doit voir les clés CONSTRUITES, sans pour autant excuser une entrée morte.

Il signalait à tort 53 libellés vivants (`label(f"win.{key}_note")`,
`label("win.iwram_part" + section)`) : des familles que l'arbre syntaxique ne montre
qu'en morceaux. Ces tests tiennent la règle, ET sa limite : un message ordinaire
ou un chemin n'est pas une famille de clés.
"""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent


def _outil():
    spec = importlib.util.spec_from_file_location(
        "check_architecture_under_test", REPO_DIR / "tools" / "check_architecture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jined(source: str) -> ast.JoinedStr:
    return ast.parse(source, mode="eval").body


def test_une_cle_construite_par_f_string_forme_une_famille():
    famille = _outil()._famille_de_cles(_jined('f"win.{key}_note"'))

    assert famille is not None
    assert famille.fullmatch("win.bgpal_note")
    assert famille.fullmatch("win.oam_note")
    assert not famille.fullmatch("win.oam_title")          # un autre suffixe n'est pas excusé
    assert not famille.fullmatch("scttree.oam_note")       # un autre écran non plus


def test_un_message_ordinaire_n_excuse_aucune_cle():
    outil = _outil()

    assert outil._famille_de_cles(_jined('f"Erreur {x} dans {y}"')) is None
    assert outil._famille_de_cles(_jined('f"{a}.{b}"')) is None          # pas de préfixe lisible
    assert outil._famille_de_cles(_jined('f"win.constante"')) is None    # aucune partie variable


def test_le_catalogue_reel_n_a_plus_de_cle_orpheline_ni_de_cle_morte():
    """Sur le dépôt réel : tout est cité, donc rien à supprimer ni à excuser."""
    outil = _outil()
    import os, sys
    sys.path.insert(0, str(REPO_DIR / "editor"))
    trees = {}
    for path in (REPO_DIR / "editor").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            trees[str(path)] = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
    ancien = os.getcwd()
    try:
        problemes = outil.controle_catalogue(trees, "labels", outil.CITATIONS_LABELS)
    finally:
        os.chdir(ancien)

    assert problemes == [], "\n".join(problemes[:10])
    # garde-fou du test lui-même : le catalogue n'est pas vide
    catalogue = json.loads((REPO_DIR / "editor" / "ui" / "common" / "labels" / "labels.json")
                           .read_text(encoding="utf-8"))["labels"]
    assert len(catalogue) > 1000
