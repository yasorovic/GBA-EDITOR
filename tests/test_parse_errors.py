"""Ce qu'une faute de SYNTAXE dit à l'auteur (correctif du 2026-09-02).

Le parse est le premier filtre de la chaîne, et c'était le seul message qui ne
disait pas où regarder : luaparser rend `SyntaxException("syntax errors: None")`
— pas de ligne, pas de jeton, pas d'attendu — là où le checker nomme sa ligne
et où `lua_subset` nomme le nœud refusé et la phrase à écrire à la place.

Rien n'était perdu, c'était jeté au FORMATAGE : luaparser lève sa
`SyntaxException` depuis un `except`, donc Python garde la
`ParseCancellationException` d'antlr dans `__context__`, laquelle porte
l'exception réelle avec son jeton fautif et ses jetons attendus.

Ces tests protègent les deux moitiés du message : ce qu'antlr sait (la LIGNE et
l'ATTENDU) et ce qu'il ne sait pas dire (le faux ami d'un auteur venu d'un autre
langage). Ils protègent aussi ce qu'on refuse de faire : rapporter le jeton
TROUVÉ, qu'antlr désigne là où il a renoncé et non là où l'auteur s'est trompé.
"""
from __future__ import annotations

import pytest


def _faute(src: str):
    from scripting.parser import parse, LuaParseError
    with pytest.raises(LuaParseError) as exc:
        parse(src)
    return exc.value


def _ok(src: str):
    from scripting.parser import parse
    return parse(src)


# ── Ce qu'antlr sait, et que luaparser jetait ─────────────────────


def test_le_message_ne_dit_plus_none():
    """Le défaut d'origine, figé : quelle que soit la faute, plus jamais
    « syntax errors: None »."""
    e = _faute('function on_update()\n\tif x :\n\tend\nend\n')
    assert "None" not in str(e)
    assert "syntax errors" not in str(e)


def test_un_end_manquant_se_nomme():
    """Le cas de loin le plus fréquent, et celui dont la ligne brute est la
    moins parlante : antlr bute sur la FIN DU FICHIER, pas sur le bloc resté
    ouvert. Le message le dit plutôt que d'envoyer l'auteur regarder la
    dernière ligne, qui est presque toujours correcte."""
    e = _faute('function on_update()\n\tif x then\n\t\tfoo()\nend\n')
    assert "end" in str(e) and "missing" in str(e)
    assert e.line == 5


def test_ce_quon_ne_sait_pas_ne_sinvente_pas():
    """Il reste des fautes dont antlr ne rend NI jeton NI attendu et qu'aucun
    faux ami n'explique (`local x =` sans valeur). antlr y renonce sur le jeton
    suivant : le message le dit (« avant `end` », la faute est plus haut) au
    lieu de désigner ce jeton comme coupable."""
    e = _faute('function on_update()\n\tlocal x = \nend\n')
    assert "before `end`" in str(e) and "previous line" in str(e)
    assert e.line == 3


def test_le_jeton_TROUVE_nest_pas_rapporte():
    """Sur `if x(...) :`, antlr nomme la parenthèse de l'appel, pas les
    deux-points — il désigne où il a renoncé, pas où l'auteur s'est trompé.
    Rapporter ce jeton enverrait corriger du code correct."""
    e = _faute('function on_update()\n\tif input:pressed("a") :\n\t\tfoo()\n\tend\nend\n')
    assert "(" not in str(e)


# ── Les faux amis d'un autre langage ──────────────────────────────


@pytest.mark.parametrize("src,attendu,ligne", [
    # Le script qui a révélé le défaut : « : » au lieu de « then ».
    ('function on_update()\n\tif input:pressed("a") :\n\t\tfoo()\n\tend\nend\n',
     "then", 2),
    ('function on_update()\n\tfor i = 1, 3 :\n\tend\nend\n',       "do", 2),
    # Le script qui a révélé le second défaut : « += », et rien pour le dire.
    ('function on_update()\n\tif x then\n\t\tcurpos +=1\n\tend\nend\n',
     "x = x + 1", 3),
    ('function on_update()\n\tcurpos -= 1\nend\n',                 "x = x + 1", 2),
    ('function on_update()\n\tcurpos++\nend\n',                    "++", 2),
    ('function on_update()\n\tif 1 != 2 then end\nend\n',          "~=", 2),
    ('function on_update()\n\tif a && b then end\nend\n',          "and", 2),
    ('function on_update()\n\tif a || b then end\nend\n',          "or", 2),
    ('function on_update()\n\tif a then\n\telif b then\n\tend\nend\n', "elseif", 3),
    ('function on_update()\n\t# un commentaire\nend\n',            "--", 2),
    ('function on_update()\n\t// un commentaire\nend\n',           "--", 2),
])
def test_un_faux_ami_se_nomme_sur_sa_ligne(src, attendu, ligne):
    e = _faute(src)
    assert attendu in str(e)
    assert e.line == ligne


def test_une_faute_lexicale_a_quand_meme_sa_ligne():
    """`!=` ne passe même pas le lexer : antlr écrit sa plainte sur sa sortie
    d'erreur et ne met RIEN dans l'exception. C'est le balayage des faux amis
    qui rend la ligne, seul cas où elle ne vient pas d'antlr."""
    e = _faute('function on_update()\n\n\n\tif 1 != 2 then end\nend\n')
    assert e.line == 4


# ── Ce que le balayage ne doit PAS prendre pour une faute ─────────


def test_un_faux_ami_dans_une_chaine_nest_pas_une_faute():
    """Une réplique de dialogue a le droit de contenir « != » : ce n'est pas
    du code. Sans ce filtre, tout script à dialogue aurait reçu un indice
    faux collé à sa vraie erreur."""
    e = _faute('function on_update()\n\tlocal s = "a != b"\n\tif x then\nend\n')
    assert "~=" not in str(e)
    assert "missing" in str(e)          # la vraie faute, seule


def test_un_faux_ami_en_commentaire_nest_pas_une_faute():
    e = _faute('function on_update()\n\t-- attention au != ici\n\tif x then\nend\n')
    assert "~=" not in str(e)


def test_un_faux_ami_est_rapporte_sur_SA_ligne_pas_celle_dantlr():
    """antlr nomme l'endroit où il a RENONCÉ, souvent plus bas que la faute :
    ici il bute sur la fin du fichier (ligne 5) alors que le « && » est ligne 4.
    C'est la ligne du faux ami qu'on rapporte — chaînes et commentaires ayant
    été écartés, ce qui reste est du code, donc une vraie faute et non une
    piste."""
    e = _faute('function on_update()\n\tlocal a = 1\n\tif a then\n\t\tb = a && 2\nend\n')
    assert "and" in str(e)
    assert e.line == 4


def test_une_table_ne_passe_pas_pour_une_affectation_composee():
    """`{a=1}` porte un « = » précédé d'un IDENTIFIANT, pas d'un opérateur : le
    motif de l'affectation composée ne doit pas s'y accrocher, sans quoi tout
    script à table recevrait un indice faux."""
    e = _faute('function on_update()\n\tlocal t = {a=1, b=2}\n\tif x then\nend\n')
    assert "composée" not in str(e)


def test_un_script_valide_ne_declenche_aucun_balayage():
    """Le balayage ne tourne qu'APRÈS un échec : un script correct qui contient
    « # » (l'opérateur de longueur) ou « != » dans une chaîne passe."""
    _ok('function on_update()\n\tlocal n = #t\n\tlocal s = "x != y"\n'
        '\tif 1 ~= 2 then end\nend\n')


def test_else_if_est_valide_mais_reclame_son_end():
    """`else if` est du Lua CORRECT — il ouvre un second bloc. L'indice ne se
    déclenche donc que si le parse a effectivement échoué, et il explique le
    « end » qui manque plutôt que d'interdire la forme."""
    _ok('function on_update()\n\tif a then\n\telse if b then\n\tend\n\tend\nend\n')
    e = _faute('function on_update()\n\tif a then\n\telse if b then\n\tend\nend\n')
    assert "end" in str(e)


# ── La conversion n'est pas une faute de syntaxe ──────────────────


def test_une_erreur_de_conversion_ne_se_deguise_pas_en_syntaxe():
    """Une exception levée par `_Converter` est un nœud que l'éditeur ne sait
    pas traiter, pas un script mal écrit : la déguiser en erreur de syntaxe
    enverrait l'auteur corriger un fichier qui n'a rien."""
    import scripting.parser as P

    class _Boum(P._Converter):
        def convert_chunk(self, node):
            raise RuntimeError("noeud inattendu")

    vrai, P._Converter = P._Converter, _Boum
    try:
        e = _faute("function on_update()\nend\n")
        assert "unreadable" in str(e) and "noeud inattendu" in str(e)
        assert e.line is None
    finally:
        P._Converter = vrai
