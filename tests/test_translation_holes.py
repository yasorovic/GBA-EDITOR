"""Le build compte les trous de traduction et les nomme (ROADMAP v0.9, phase 5.3).

Décision verrouillée à l'ouverture du jalon, restée sans implémentation
jusqu'à la phase 5 : le compte de trous existait dans l'ÉDITEUR (le badge par
onglet de l'atelier, phase 2), pas au build — là où quelqu'un fabrique une
cartouche et n'a plus l'écran sous les yeux.

Un trou n'est PAS une erreur : une entrée absente d'un side rend la source
(cf. `project_langs.py`), ce qui est exactement ce qui permet de traduire un
jeu par étapes. Ce que ces tests protègent, c'est qu'on le sache avant de
graver, et que le message porte l'ampleur (le compte) sans dérouler deux cents
clés.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def projet(tmp_path):
    from core.project import Project
    from core.models.settings import Language

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)
    for i in range(4):
        p.new_text(content=f"Bonjour {i}", path=["Dialogue"])

    p.settings.source_lang = Language(code="en", name="English")
    p.settings.languages = [Language(code="de", name="Deutsch")]
    p.load_translations()
    return p


def _warnings(p) -> list[str]:
    from core.validator import ValidationContext, _check_translation_holes
    ctx = ValidationContext(p)
    _check_translation_holes(ctx)
    return [m.message for m in ctx.warnings]


def test_aucune_traduction_compte_toutes_les_entrees(projet):
    warns = _warnings(projet)
    assert len(warns) == 1
    assert "Deutsch" in warns[0]
    assert "4 of 4" in warns[0]


def test_une_langue_complete_ne_dit_rien(projet):
    p = projet
    for t in p.texts:
        p.translations["de"][t.id] = "Hallo"
    assert _warnings(p) == []


def test_le_compte_suit_les_entrees_remplies(projet):
    p = projet
    p.translations["de"][p.texts[0].id] = "Hallo"
    warns = _warnings(p)
    assert len(warns) == 1 and "3 of 4" in warns[0]


def test_une_traduction_vide_est_un_trou(projet):
    """Une chaîne vide dans le side n'est pas une traduction : le repli sur la
    source s'applique pareil, donc le trou est le même."""
    p = projet
    for t in p.texts:
        p.translations["de"][t.id] = "   "
    assert "4 of 4" in _warnings(p)[0]


def test_le_message_nomme_les_premieres_cles_pas_toutes(projet):
    """Le compte porte l'ampleur, l'écran porte la liste — un message qui
    déroule deux cents clés ne se lit pas."""
    p = projet
    for i in range(10):
        p.new_text(content=f"Encore {i}", path=["Dialogue"])
    msg = _warnings(p)[0]
    assert msg.count(",") >= 3          # trois clés citées
    assert "and 11 more" in msg


def test_chaque_langue_a_son_message(projet):
    from core.models.settings import Language
    p = projet
    p.settings.languages.append(Language(code="ja", name="日本語"))
    p.load_translations()
    warns = _warnings(p)
    assert len(warns) == 2
    assert any("Deutsch" in w for w in warns) and any("日本語" in w for w in warns)


def test_projet_monolingue_silencieux(projet):
    """Sans langue déclarée il n'y a pas de trou : il y a un jeu dans sa
    langue. Même contrat que `_check_literal_texts`."""
    p = projet
    p.settings.languages = []
    assert _warnings(p) == []


def test_une_entree_source_vide_nest_pas_comptee(projet):
    """Une entrée que personne n'a encore écrite n'est pas un trou de
    TRADUCTION — il n'y a rien à traduire. La signaler ici doublerait un
    problème que l'écran Texte montre déjà en colonne Content."""
    p = projet
    p.texts[0].content = ""
    assert "3 of 3" in _warnings(p)[0]
