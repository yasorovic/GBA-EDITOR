"""Repli des blocs indentés et surlignage de la ligne désignée par le journal.

Le dessin des flèches ne se teste pas (offscreen n'a pas de police) : ce qui est
tenu, c'est la GÉOMÉTRIE du repli (quelles lignes disparaissent, lesquelles
reviennent) et le fait qu'un saut depuis le journal retrouve sa ligne même
repliée.
"""
from __future__ import annotations

SOURCE = "\n".join([
    "function state_ground()",          # 0
    "    local body = 1",               # 1
    "",                                 # 2
    "    if body then",                 # 3
    "        body = 2",                 # 4
    "    end",                          # 5
    "end",                              # 6
    "",                                 # 7
    "function autre()",                 # 8
    "    return 1",                     # 9
    "end",                              # 10
])


def _editor(qapp, source: str = SOURCE):
    from ui.script_editor.lua_editor import LuaEditor
    ed = LuaEditor()
    ed.setPlainText(source)
    ed.resize(600, 400)
    ed.show()
    qapp.processEvents()
    return ed


def _visibles(ed) -> list[int]:
    doc = ed.document()
    return [n for n in range(doc.blockCount()) if doc.findBlockByNumber(n).isVisible()]


# ── Ce qu'une ligne ouvre ─────────────────────────────────────────
def test_le_bloc_s_arrete_a_la_premiere_ligne_moins_indentee(qapp):
    """Le corps d'une fonction va jusqu'à son `end`, que l'indentation ramène
    au niveau de l'en-tête. La ligne blanche qui suit n'en fait pas partie."""
    ed = _editor(qapp)
    assert ed.fold_end(0) == 5
    assert ed.fold_end(3) == 4


def test_une_ligne_qui_n_ouvre_rien_n_est_pas_repliable(qapp):
    """Ni une ligne isolée, ni une ligne blanche, ni un `end`."""
    ed = _editor(qapp)
    assert ed.fold_end(5) is None     # end
    assert ed.fold_end(7) is None     # ligne blanche
    assert ed.fold_end(9) is None     # dernière ligne d'un corps


# ── Replier et rouvrir ────────────────────────────────────────────
def test_replier_cache_le_corps_et_garde_l_en_tete(qapp):
    ed = _editor(qapp)
    assert ed.fold(0) is True
    assert _visibles(ed) == [0, 6, 7, 8, 9, 10]
    assert ed.is_folded(0)


def test_rouvrir_rend_les_lignes(qapp):
    ed = _editor(qapp)
    ed.fold(0)
    ed.unfold(0)
    assert _visibles(ed) == list(range(11))
    assert ed.folded_lines() == set()


def test_rouvrir_un_parent_ne_rouvre_pas_l_enfant_replie(qapp):
    """L'auteur avait fermé le `if` : rouvrir la fonction ne le rouvre pas."""
    ed = _editor(qapp)
    ed.fold(3)
    ed.fold(0)
    ed.unfold(0)
    assert 4 not in _visibles(ed)
    assert ed.folded_lines() == {3}


def test_le_repli_suit_sa_ligne_quand_on_ecrit_au_dessus(qapp):
    """Le repli est ancré sur son bloc, pas sur un numéro : une ligne insérée
    plus haut décale tout, la flèche doit rester sur la même fonction."""
    from PyQt6.QtGui import QTextCursor
    ed = _editor(qapp)
    ed.fold(8)
    cur = QTextCursor(ed.document().firstBlock())
    cur.insertText("-- commentaire\n")
    qapp.processEvents()
    assert ed.folded_lines() == {9}


def test_un_corps_disparu_rouvre_tout(qapp):
    """Supprimer le corps d'un repli fermé laisserait des lignes cachées sans
    flèche pour les rendre : la sortie sûre est de tout rouvrir."""
    ed = _editor(qapp)
    ed.fold(8)
    ed.setPlainText("function autre()\nend\n")
    qapp.processEvents()
    assert _visibles(ed) == list(range(ed.document().blockCount()))
    assert ed.folded_lines() == set()


# ── Saut depuis le journal ────────────────────────────────────────
def test_le_saut_rouvre_le_repli_qui_cachait_la_ligne(qapp):
    ed = _editor(qapp)
    ed.fold(0)
    ed.goto_line(5)                     # 1-indexé → bloc 4, caché
    assert ed.document().findBlockByNumber(4).isVisible()
    assert ed.textCursor().blockNumber() == 4


def test_le_saut_surligne_la_ligne_entiere(qapp):
    ed = _editor(qapp)
    ed.goto_line(4)
    selections = ed.extraSelections()
    assert len(selections) == 1
    assert selections[0].cursor.blockNumber() == 3


def test_la_premiere_frappe_efface_le_surlignage(qapp):
    """Le surlignage désigne un état du texte : l'édition l'invalide."""
    ed = _editor(qapp)
    ed.goto_line(4)
    ed.insert_at_cursor("x")
    qapp.processEvents()
    assert ed.extraSelections() == []


def test_entree_apres_then_indente_le_corps(qapp):
    ed = _editor(qapp, 'if state == "ground" then')
    ed.moveCursor(ed.textCursor().MoveOperation.End)
    ed.insert_newline_keeping_indent()
    assert ed.toPlainText() == 'if state == "ground" then\n    '


def test_entree_apres_then_dans_un_commentaire_ne_creuse_pas(qapp):
    ed = _editor(qapp, '-- then')
    ed.moveCursor(ed.textCursor().MoveOperation.End)
    ed.insert_newline_keeping_indent()
    assert ed.toPlainText() == '-- then\n'


def test_entree_apres_un_bloc_ferme_sur_sa_ligne_ne_creuse_pas(qapp):
    ed = _editor(qapp, 'if state == "ground" then end')
    ed.moveCursor(ed.textCursor().MoveOperation.End)
    ed.insert_newline_keeping_indent()
    assert ed.toPlainText() == 'if state == "ground" then end\n'


def test_entree_apres_end_realigne_la_fermeture(qapp):
    ed = _editor(qapp, "if state then\n    value = 1\n        end")
    ed.moveCursor(ed.textCursor().MoveOperation.End)
    ed.insert_newline_keeping_indent()
    assert ed.toPlainText() == "if state then\n    value = 1\nend\n"


def test_entree_apres_else_realigne_et_rentre_dans_la_branche(qapp):
    ed = _editor(qapp, "if state then\n    value = 1\n    else")
    ed.moveCursor(ed.textCursor().MoveOperation.End)
    ed.insert_newline_keeping_indent()
    assert ed.toPlainText() == "if state then\n    value = 1\nelse\n    "


def test_entree_apres_une_ligne_normale_ne_cumule_pas_les_espaces(qapp):
    ed = _editor(qapp, "if state then\n    value = 1\n        other = 2")
    ed.moveCursor(ed.textCursor().MoveOperation.End)
    ed.insert_newline_keeping_indent()
    assert ed.toPlainText() == "if state then\n    value = 1\n    other = 2\n    "
