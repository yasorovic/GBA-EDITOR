"""Un littéral `text:draw("...")` devient un avertissement NOMMÉ dès qu'une
langue est déclarée (ROADMAP v0.9, décision 6 / phase 3.5).

C'était un raccourci ASSUMÉ au prix de la traduction depuis la v0.3.2 : rien
ne le signale dans un projet monolingue, parce que personne n'a demandé à le
payer. Dès qu'une traduction existe, un littéral est un trou GARANTI — l'écran
Texte ne peut rien y accrocher, il n'a pas d'id. Cf. `_check_literal_texts`.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def projet(tmp_path):
    from core.project import Project
    from core.models.settings import Language

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)
    p.scripts_scenes_dir.mkdir(parents=True, exist_ok=True)

    t = p.new_text(content="Score")
    t.key = "score_label"

    (p.scripts_scenes_dir / "Arena.lua").write_text(
        'function on_start()\n'
        '    text:draw(2, 2, "score_label")\n'    # une vraie clé : pas un trou
        '    text:draw(4, 6, "Bonjour")\n'          # un littéral : LE trou
        'end\n',
        encoding="utf-8")

    p.settings.source_lang = Language(code="en", name="English")
    return p


def _warnings_for(p):
    from core.validator import ValidationContext, _check_literal_texts
    ctx = ValidationContext(p)
    _check_literal_texts(ctx)
    return [m.message for m in ctx.warnings]


def test_silencieux_sans_langue_declaree(projet):
    p = projet
    assert p.settings.languages == []
    assert _warnings_for(p) == []


def test_un_litteral_est_signale_avec_fichier_et_ligne(projet):
    from core.models.settings import Language
    p = projet
    p.settings.languages = [Language(code="fr", name="French")]

    warns = _warnings_for(p)
    assert len(warns) == 1
    assert "Arena.lua:3" in warns[0]
    assert "Bonjour" in warns[0]


def test_une_vraie_cle_n_est_jamais_signalee(projet):
    """`text:draw(2, 2, "score_label")` cite une entrée RÉELLE — ce n'est pas
    un littéral, même si le repérage syntaxique est identique."""
    from core.models.settings import Language
    p = projet
    p.settings.languages = [Language(code="fr", name="French")]

    warns = _warnings_for(p)
    assert not any("score_label" in w for w in warns)
