"""La résolution des chemins d'asset est gardée, et un build repart de résolutions fraîches."""
from core.project import _resolve_under, forget_resolved_asset_paths


def test_resolution_matches_path_resolve_and_is_kept(tmp_path):
    forget_resolved_asset_paths()
    first = _resolve_under(tmp_path, "assets/scripts/Player.lua")
    assert first == (tmp_path / "assets" / "scripts" / "Player.lua").resolve()
    assert _resolve_under(tmp_path, "assets/scripts/Player.lua") is first
    assert _resolve_under.cache_info().hits >= 1


def test_forget_drops_every_kept_resolution(tmp_path):
    _resolve_under(tmp_path, "assets/a.png")
    forget_resolved_asset_paths()
    assert _resolve_under.cache_info().currsize == 0


def test_same_relative_path_under_two_roots_is_not_mixed(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert _resolve_under(a, "x.lua") != _resolve_under(b, "x.lua")
