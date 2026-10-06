"""Le débordement d'une zone de texte, mesuré contre TOUTES les langues.

Avant ROADMAP v0.9, `_check_text_overflow` ne mesurait que `text.content` — la
source. Une traduction plus longue qu'elle déborde en silence : le build ne
dit rien, et la troncature ne se découvre qu'en jouant la ROM dans cette
langue-là. `_text_variants` est le correctif ; ces tests protègent son
contrat, pas la géométrie de `layout_text` elle-même (couverte ailleurs).
"""
from __future__ import annotations

import pytest


def _font(name="test_font", cell=(8, 8), chars="ABCDEFGHIJKLMNOPQRSTUVWXYZ! "):
    from core.models.font import Font, Glyph
    f = Font(name=name, cell_w=cell[0], cell_h=cell[1], line_height=cell[1])
    f.glyphs = [Glyph(char=c, w=cell[0], h=cell[1], advance=cell[0]) for c in chars]
    return f


@pytest.fixture
def projet(tmp_path):
    """Un projet avec une zone de texte étroite et une police à chasse fixe."""
    from core.project import Project
    from core.models.settings import Language
    from core.models.ui_region import UILayout, UIText

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)
    p.fonts.append(_font())

    region = UIText(name="hud", w=32, h=8)   # 4 glyphes de 8px, pas un de plus
    layout = UILayout(name="main")
    layout.elements.append(region)
    p.ui_layouts.append(layout)

    t = p.new_text(content="OK")             # tient très bien dans 32px
    t.key = "hud_msg"
    region.text_key = t.key

    p.settings.source_lang = Language(code="en", name="English")
    p.settings.languages = [Language(code="de", name="Deutsch")]
    p.load_translations()
    return p, t


def _warnings_for(p):
    from core.validator import ValidationContext, _check_text_overflow
    ctx = ValidationContext(p)
    _check_text_overflow(ctx)
    return [m.message for m in ctx.warnings]


def test_la_source_courte_ne_deborde_pas(projet):
    p, t = projet
    assert _warnings_for(p) == []


def test_une_traduction_plus_longue_deborde_et_le_dit(projet):
    p, t = projet
    p.translations["de"][t.id] = "TOO LONG FOR THIS BOX"
    warns = _warnings_for(p)
    assert len(warns) == 1
    assert "hud_msg" in warns[0] and '"de"' in warns[0]
    # La source, elle, reste dans les clous — un seul message, pas deux.
    assert "overflows" in warns[0]


def test_une_langue_non_traduite_ne_double_pas_le_message(projet):
    """Non traduite, elle affiche la SOURCE : la revérifier serait le même
    verdict une seconde fois."""
    p, t = projet
    t.content = "ALSO TOO LONG TO FIT HERE"   # la source elle-même déborde
    warns = _warnings_for(p)
    assert len(warns) == 1        # pas deux, malgré la langue "de" déclarée
    assert "« de »" not in warns[0]   # c'est la source qui parle, sans étiquette


def test_une_traduction_identique_a_la_source_nest_pas_revérifiée(projet):
    p, t = projet
    t.content = "TOO LONG TO FIT IN THIS BOX"
    p.translations["de"][t.id] = t.content    # même texte, mot pour mot
    warns = _warnings_for(p)
    assert len(warns) == 1   # dédupliqué par contenu, pas par langue

def test_un_projet_monolingue_se_comporte_a_l_identique(projet):
    """Retirer la déclaration ne doit rien changer au compte de messages issus
    de la source — la boucle des langues doit être un pur AJOUT."""
    p, t = projet
    t.content = "TOO LONG TO FIT IN THIS BOX"
    p.settings.languages = []
    warns = _warnings_for(p)
    assert len(warns) == 1
    assert "langue" not in warns[0]
