"""La marge des numéros de ligne de l'éditeur Lua.

Le rendu des chiffres ne se teste pas ici (un `QT_QPA_PLATFORM=offscreen` n'a
pas de police) : ce qui est tenu, c'est la GÉOMÉTRIE, la seule chose qui peut
casser sans qu'on le voie. Une marge trop étroite tronque les numéros, une
marge non réservée les fait peindre par-dessus le code, et une marge qui ne
suit pas la hauteur du viewport décale chaque numéro de sa ligne.
"""
from __future__ import annotations


def _editor(qapp, lines: int):
    from ui.script_editor.lua_editor import LuaEditor
    ed = LuaEditor()
    ed.setPlainText("\n".join(f"local x{n} = {n}" for n in range(1, lines + 1)))
    ed.resize(600, 300)
    ed.show()
    qapp.processEvents()
    return ed


def test_la_marge_s_elargit_avec_le_nombre_de_lignes(qapp):
    """Trois chiffres tiennent plus de place que deux : la largeur se calcule,
    elle n'est pas fixée une fois pour toutes."""
    court = _editor(qapp, 9)
    long = _editor(qapp, 150)
    assert long.line_number_width() > court.line_number_width()


def test_le_texte_commence_apres_la_marge(qapp):
    """La marge du viewport la réserve : sans ça, les chiffres se peindraient
    par-dessus la première colonne du code."""
    ed = _editor(qapp, 20)
    assert ed.viewportMargins().left() == ed.line_number_width()


def test_la_marge_suit_la_hauteur_du_viewport(qapp):
    """Elle est posée sur le viewport, pas sur le widget : le rembourrage de la
    feuille de style décalerait sinon chaque numéro de sa ligne."""
    ed = _editor(qapp, 20)
    assert ed._line_numbers.geometry().top() == ed.viewport().geometry().top()
    assert ed._line_numbers.height() == ed.viewport().height()


def test_la_largeur_reservee_suit_l_ajout_de_lignes(qapp):
    """Passer de 9 à 100 lignes élargit la marge DÉJÀ réservée, sinon le code
    se décalerait sous les chiffres au centième saut de ligne."""
    ed = _editor(qapp, 9)
    avant = ed.viewportMargins().left()
    ed.setPlainText("\n".join("x" for _ in range(100)))
    qapp.processEvents()
    assert ed.viewportMargins().left() > avant
