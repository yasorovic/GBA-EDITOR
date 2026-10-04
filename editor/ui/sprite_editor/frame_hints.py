"""ui/sprite_editor/frame_hints.py — contenu de la table des raccourcis du canvas
de composition du Sprite Editor. Contexte = ce que le canvas offre : « brush »
(brosse active), « pick » (pas de brosse : on ramasse des tuiles posées),
« readonly » (direction miroir)."""
from __future__ import annotations

from ui.common.shortcut_hints import Hints, bound, mouse

_TITLES = {
    "brush": "hints.sprite.title_brush",
    "pick": "hints.sprite.title_pick",
    "readonly": "hints.sprite.title_readonly",
}


def frame_canvas_hints(context: str) -> Hints:
    rows = []
    if context == "brush":
        rows = [
            (mouse("left_click"), "hints.sprite.paint"),
            (mouse("right_click"), "hints.sprite.erase"),
            (bound("sprite.flip_h"), "hints.sprite.flip_h"),
            (bound("sprite.flip_v"), "hints.sprite.flip_v"),
        ]
    elif context == "pick":
        rows = [
            (mouse("left_drag"), "hints.sprite.pick_up"),
            (mouse("right_click"), "hints.sprite.erase"),
        ]
    return _TITLES.get(context, "hints.sprite.title_pick"), rows
