"""Deux assets dont les noms donnent le même symbole C se remplaceraient dans la ROM."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "editor"))

from core.models.scene import Scene
from core.validator import _check_asset_symbol_collisions


class _Ctx:
    def __init__(self, **kinds):
        empty = {"scenes": [], "sprites": [], "backgrounds": [], "prefabs": []}
        self.project = type("P", (), {**empty, **kinds})()
        self.errors: list[str] = []

    def error(self, _owner, message, target=None):
        self.errors.append(message)


def test_names_giving_one_symbol_are_an_error():
    ctx = _Ctx(scenes=[Scene(name="My Scene"), Scene(name="My_Scene")])
    _check_asset_symbol_collisions(ctx)
    assert len(ctx.errors) == 1 and "My_Scene" in ctx.errors[0]


def test_distinct_names_pass():
    ctx = _Ctx(scenes=[Scene(name="Menu"), Scene(name="Arena")])
    _check_asset_symbol_collisions(ctx)
    assert ctx.errors == []
