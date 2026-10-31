"""Le cache de l'arbre Lua brut : même texte, même arbre ; une erreur de syntaxe n'est jamais gardée."""
import pytest

from scripting.parser import LuaParseError, parse, raw_tree


def test_same_source_gives_the_same_tree():
    src = "function on_update(self)\n  self.x = 1\nend\n"
    assert raw_tree(src) is raw_tree(src)
    assert raw_tree(src) is not raw_tree(src + "-- other\n")


def test_parse_result_is_unchanged_by_the_cache():
    src = "function on_update(self)\n  self.x = 1\nend\n"
    first = parse(src)
    second = parse(src)
    assert first is not second          # chaque appel convertit : seul l'arbre brut est partagé
    assert [f.name for f in first.functions] == [f.name for f in second.functions] == ["on_update"]


def test_syntax_error_is_reported_every_time():
    bad = "function on_update(self\n"
    for _ in range(2):
        with pytest.raises(LuaParseError):
            parse(bad)
