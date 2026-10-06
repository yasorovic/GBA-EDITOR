"""Fondations du balisage typographique ``[font=nom]…[/font]``."""
from __future__ import annotations


def test_font_est_une_portee_et_ne_sort_pas_dans_le_texte_affiche():
    from core.text_markup import parse

    parsed = parse("Bonjour [font=Titre]monde[/font] !")

    assert parsed.display == "Bonjour monde !"
    assert [(m.kind, m.at, m.end, m.value) for m in parsed.of_kind("font")] == [
        ("font", 8, 13, "Titre")
    ]


def test_font_partage_les_regles_generiques_d_imbrication():
    from core.text_markup import parse

    parsed = parse("[font=Titre][color=2]A[/font][/color]")

    assert parsed.display == "A"
    assert parsed.of_kind("font")[0].value == "Titre"
    assert any("crossed nesting" in issue.message for issue in parsed.issues)


def test_une_police_de_balisage_inconnue_bloque_le_build(tmp_path):
    from core.project import Project
    from core.models.font import Font, Glyph
    from core.validator import ValidationContext, _check_markup_fonts

    project = Project(tmp_path / "jeu")
    project.fonts.append(Font(name="Dialogue", glyphs=[Glyph(char="A", w=8, h=8)]))
    text = project.new_text(content="[font=Titre]A[/font]")
    text.key = "intro"

    ctx = ValidationContext(project)
    _check_markup_fonts(ctx)

    assert len(ctx.errors) == 1
    assert "intro" in ctx.errors[0].message
    assert "Titre" in ctx.errors[0].message


def test_une_police_de_balisage_connue_est_acceptee(tmp_path):
    from core.project import Project
    from core.models.font import Font, Glyph
    from core.validator import ValidationContext, _check_markup_fonts

    project = Project(tmp_path / "jeu")
    project.fonts.append(Font(name="Titre", glyphs=[Glyph(char="A", w=8, h=8)]))
    project.new_text(content="[font=Titre]A[/font]")

    ctx = ValidationContext(project)
    _check_markup_fonts(ctx)

    assert ctx.errors == []


def test_projection_masque_les_balises_sans_aplatir_le_contenu():
    from core.text_markup import PROJ_CONTENT, PROJ_MARKUP, project

    hidden = project("A[font=Titre]BC[/font]D")
    shown = project("A[font=Titre]BC[/font]D", show_markup=True)

    assert hidden.text == "ABCD"
    assert shown.text == "A[font=Titre]BC[/font]D"
    assert [s.kind for s in shown.spans] == [
        PROJ_CONTENT, PROJ_MARKUP, PROJ_CONTENT, PROJ_MARKUP, PROJ_CONTENT,
    ]
    assert shown.spans[2].font_name == "Titre"


def test_projection_garde_une_valeur_atomique():
    from core.text_markup import PROJ_VALUE, project

    projection = project("PV : $hp!3", {"hp": 12345})

    assert projection.text == "PV : 123"
    value = next(s for s in projection.spans if s.kind == PROJ_VALUE)
    assert value.atomic is True
    assert projection.visible_to_source(len("PV : 1")) == value.source_start
    assert projection.visible_to_source(len("PV : 123"), right=True) == value.source_end


def test_retrait_de_balisage_ne_supprime_que_les_bornes_de_la_portee():
    from core.text_markup import removable_markup_edits

    source = "[wave]Bonjour[/wave]"
    edits = removable_markup_edits(source, len("[wave]"), len("[wave]Bonjour"))

    assert edits == [(len("[wave]Bonjour"), len(source), ""), (0, len("[wave]"), "")]


def test_retrait_de_balisage_accepte_la_selection_qui_contient_les_balises():
    from core.text_markup import removable_markup_edits

    source = "[font=Titre]Bonjour[/font]"

    assert removable_markup_edits(source, 0, len(source)) == [
        (len("[font=Titre]Bonjour"), len(source), ""),
        (0, len("[font=Titre]"), ""),
    ]
