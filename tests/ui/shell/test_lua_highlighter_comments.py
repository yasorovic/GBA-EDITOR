"""Les commentaires `--[[ ]]`, qui traversent les lignes.

Une règle d'expression régulière ne voit qu'une ligne : ce qui est tenu ici,
c'est l'ÉTAT porté d'une ligne à la suivante (ouvert, fermé, niveau du crochet)
et la couleur réellement posée sur le texte, celle que l'auteur voit.
"""
from __future__ import annotations

from ui.common.theme import C


def _editor(qapp, source: str):
    from ui.script_editor.lua_editor import LuaEditor
    ed = LuaEditor()
    ed.setPlainText(source)
    qapp.processEvents()
    return ed


def _couleurs(ed, ligne: int) -> list[str]:
    """Les couleurs posées sur la ligne, dans l'ordre des portions colorées."""
    bloc = ed.document().findBlockByNumber(ligne)
    return [r.format.foreground().color().name() for r in bloc.layout().formats()]


def _est_commente(ed, ligne: int) -> bool:
    couleurs = _couleurs(ed, ligne)
    return bool(couleurs) and all(c == C.SYNTAX_COMMENT.lower() for c in couleurs)


SOURCE = "\n".join([
    "local a = 1",                  # 0
    "--[[ une note",                # 1
    "    function f() end",         # 2
    "]]",                           # 3
    "local b = 2",                  # 4
])


def test_les_lignes_du_commentaire_sont_toutes_colorees(qapp):
    ed = _editor(qapp, SOURCE)
    assert _est_commente(ed, 1)
    assert _est_commente(ed, 2)
    assert _est_commente(ed, 3)


def test_le_code_autour_garde_ses_couleurs(qapp):
    """Fermer le commentaire rend la ligne suivante au code : sans ça, tout le
    reste du fichier passerait en vert."""
    ed = _editor(qapp, SOURCE)
    assert not _est_commente(ed, 0)
    assert not _est_commente(ed, 4)


def test_un_mot_cle_dans_le_commentaire_n_est_plus_un_mot_cle(qapp):
    """`function` commenté est du texte : le format du commentaire s'applique
    après les règles ordinaires."""
    ed = _editor(qapp, SOURCE)
    assert C.SYNTAX_KEYWORD.lower() not in _couleurs(ed, 2)


def test_le_crochet_long_ne_se_ferme_qu_a_son_niveau(qapp):
    """`--[=[` ne se ferme pas sur `]]` : le niveau du crochet compte."""
    ed = _editor(qapp, "--[=[ note\n]]\nencore\n]=]\nlocal a = 1")
    assert _est_commente(ed, 1)
    assert _est_commente(ed, 2)
    assert not _est_commente(ed, 4)


def test_un_commentaire_simple_n_ouvre_pas_de_bloc(qapp):
    """Un `--[[` écrit APRÈS un `--` est dans un commentaire de ligne : il
    n'ouvre rien, et la ligne suivante reste du code."""
    ed = _editor(qapp, "-- note --[[\nlocal a = 1")
    assert not _est_commente(ed, 1)


def test_le_commentaire_long_indente_reste_un_commentaire(qapp):
    ed = _editor(qapp, "function f()\n    --[[ une note\n    encore\n    ]]\nend")
    assert _est_commente(ed, 1)
    assert _est_commente(ed, 2)
    assert _est_commente(ed, 3)


def test_un_faux_commentaire_long_dans_une_chaine_ne_colore_pas_la_suite(qapp):
    ed = _editor(qapp, 'local note = "--[[ pas un commentaire"\nlocal a = 1')
    assert not _est_commente(ed, 1)
    assert ed.fold_end(0) is None


# ── Repli ─────────────────────────────────────────────────────────
def test_un_commentaire_multiligne_se_replie(qapp):
    """Il n'indente rien, mais c'est souvent la plus longue chose à passer."""
    ed = _editor(qapp, SOURCE)
    assert ed.fold_end(1) == 3
    assert ed.fold(1) is True
    doc = ed.document()
    assert [n for n in range(doc.blockCount()) if doc.findBlockByNumber(n).isVisible()] \
        == [0, 1, 4]


def test_un_commentaire_ferme_sur_sa_ligne_ne_se_replie_pas(qapp):
    ed = _editor(qapp, "--[[ note ]]\nlocal a = 1")
    assert ed.fold_end(0) is None


def test_un_commentaire_long_sans_fermeture_ne_se_replie_pas(qapp):
    ed = _editor(qapp, "--[[ note\nencore")
    assert ed.fold_end(0) is None
