"""Un fond de plus de 1024 tuiles uniques est signalé (avertissement), jamais bloqué."""
from types import SimpleNamespace

from core.validator import ValidationContext, _check_background_tile_capacity


def _background(tiles, mode="tiled", animated=False, target=0):
    return SimpleNamespace(name="Big", tileset=["0" * 64] * tiles, mode=mode, is_animated=animated,
                           compression=SimpleNamespace(tile_target=target),
                           effective_tileset=lambda: ["0" * 64] * tiles)


def _warnings(*backgrounds):
    ctx = ValidationContext(SimpleNamespace(active_scene=None, backgrounds=list(backgrounds)))
    _check_background_tile_capacity(ctx)
    assert not ctx.errors
    return ctx.warnings


def test_over_limit_warns():
    assert "1025 unique tiles" in _warnings(_background(1025))[0].message


def test_at_limit_and_bitmap_are_silent():
    assert not _warnings(_background(1024), _background(5000, mode="bitmap"), _background(5000, animated=True))


def test_unknown_build_language_warns_but_known_one_does_not():
    from core.validator import _check_build_language

    def warnings(build_language):
        languages = [SimpleNamespace(code="fr")]
        settings = SimpleNamespace(language_mode="monolingual", build_language=build_language,
                                   source_lang=SimpleNamespace(code=""), languages=languages)
        ctx = ValidationContext(SimpleNamespace(active_scene=None, backgrounds=[], settings=settings))
        _check_build_language(ctx)
        return ctx.warnings

    assert "no longer exists" in warnings("jp")[0].message
    assert not warnings("fr") and not warnings("")


def test_tile_target_not_reached_warns():
    messages = [w.message for w in _warnings(_background(300, target=256), _background(256, target=256))]
    assert len(messages) == 1 and "asks for 256 tiles but has 300" in messages[0]
