r"""Un littéral Lua devient une chaîne C qui dit la même chose : `\65` est décimal en Lua, octal en C."""
from scripting.codegen import _c_quoted


def test_les_echappements_que_lua_et_c_lisent_differemment_sont_reecrits():
    assert _c_quoted(r"\65") == r'"\101"'              # 'A', pas l'octal 65
    assert _c_quoted(r"\10x") == r'"\012x"'            # saut de ligne ; le `x` suivant n'est pas avalé
    assert _c_quoted(r"\x41B") == r'"\101B"'           # `B` n'étend pas l'échappement hexadécimal
    assert _c_quoted(r"\u{e9}") == r'"\303\251"'       # UTF-8
    assert _c_quoted(r"a\z   b") == '"ab"'


def test_les_echappements_communs_et_le_guillemet_nu_sont_conserves():
    assert _c_quoted(r"a\nb\"c\\d") == r'"a\nb\"c\\d"'
    assert _c_quoted('say "hi"') == r'"say \"hi\""'
