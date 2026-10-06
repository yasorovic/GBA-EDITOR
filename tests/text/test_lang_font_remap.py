"""`g_lang_font` — le remplacement de la Default Font par langue.

Une FontAsset explicitement nommée conserve sa propre chaîne de sources : seule
la Default Font du projet peut changer avec la langue.
"""
from __future__ import annotations

import re

from types import SimpleNamespace


def _lang(code: str, default_font: str = ""):
    return SimpleNamespace(code=code, default_font=default_font)


def _idxs(src: str, table: str) -> list[int]:
    m = re.search(re.escape(table) + r"\[\d+\] = \{([^}]*)\}", src)
    assert m, f"{table} introuvable dans :\n{src}"
    return [int(x) for x in m.group(1).split(",")]


def test_aucune_langue_declaree_est_identite():
    from codegen.font_emit import emit_lang_fonts_c
    src = "\n".join(emit_lang_fonts_c(["dialog"], []))
    assert "g_lang_font[1]" in src
    assert _idxs(src, "g_lang_font_0") == [0]


def test_langue_sans_remplacement_declare_est_identite():
    """Le cas courant : aucun remplacement de la Default Font."""
    from codegen.font_emit import emit_lang_fonts_c
    fr = _lang("fr")
    src = "\n".join(emit_lang_fonts_c(["dialog", "title"], [_lang("en"), fr]))
    assert _idxs(src, "g_lang_font_0") == [0, 1]   # source : toujours identité
    assert _idxs(src, "g_lang_font_1") == [0, 1]   # fr : identité aussi, rien à remplacer


def test_langue_avec_remplacement_pointe_l_autre_police():
    """Le cas d'un système d'écriture qui A BESOIN d'une autre planche —
    celui que le projet démo Fonts&Texts, lui, n'a pas besoin de déclarer."""
    from codegen.font_emit import emit_lang_fonts_c
    ja = _lang("ja", "dialog_ja")
    src = "\n".join(emit_lang_fonts_c(
        ["dialog", "dialog_ja", "title"], [_lang("en"), ja], "dialog"))
    # source : identité partout
    assert _idxs(src, "g_lang_font_0") == [0, 1, 2]
    # ja : la Default Font "dialog" devient "dialog_ja" ; "title", explicitement
    # nommée, reste elle-même.
    assert _idxs(src, "g_lang_font_1") == [1, 1, 2]


def test_remplacement_vers_une_police_absente_retombe_sur_l_identite():
    """Un nom mal tapé ou un asset supprimé ne doit pas produire un index hors
    bornes — au validateur de le signaler, pas à ce module de deviner."""
    from codegen.font_emit import emit_lang_fonts_c
    de = _lang("de", "police_qui_n_existe_plus")
    src = "\n".join(emit_lang_fonts_c(["dialog"], [_lang("en"), de], "dialog"))
    assert _idxs(src, "g_lang_font_1") == [0]
