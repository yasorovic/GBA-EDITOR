"""ui/background_editor/bg_hints.py — contenu de la table des raccourcis du
Background Editor. Contexte = outil de peinture actif, ou « select » (le mode Canvas)."""
from __future__ import annotations

from ui.common.labels import label
from ui.common.shortcut_hints import Hints, combo, mouse

_TITLES = {
    "brush": "bginp.brush",
    "fill": "bginp.fill",
    "rect": "cvtool.rectangle",
    "eraser": "bginp.eraser",
    "select": "bginp.select",
}

_ROWS = {
    "brush": [(mouse("left_drag"), "hints.bg.paint"), (mouse("right_drag"), "hints.bg.erase")],
    "fill": [(mouse("left_click"), "hints.bg.fill")],
    "rect": [(mouse("left_drag"), "hints.bg.paint_rect")],
    "eraser": [(mouse("left_drag"), "hints.bg.erase_all")],
    # Mode Paint du pinceau : `<outil>_paint`, mêmes outils, geste « poser une couleur ».
    "brush_paint": [(mouse("left_drag"), "hints.bg.paint_tiles"), (mouse("right_drag"), "hints.bg.erase_tiles")],
    "fill_paint": [(mouse("left_click"), "hints.bg.fill_tiles")],
    "rect_paint": [(mouse("left_drag"), "hints.bg.paint_rect_tiles")],
    "eraser_paint": [(mouse("left_drag"), "hints.bg.erase_all")],
    # L'outil « select » est le mode Canvas : poser l'image dans le canvas.
    "select": [
        (mouse("left_drag"), "hints.bg.canvas_move"),
        (combo("Shift", mouse("left_drag")), "hints.bg.keep_ratio"),
        (combo("Ctrl", mouse("left_drag")), "hints.bg.snap_grid"),
        ("Enter", "hints.bg.canvas_apply"),
        ("Esc", "hints.bg.canvas_cancel"),
    ],
}


def background_hints(context: str) -> Hints:
    rows = list(_ROWS.get(context, []))
    # Les fonds animés posés se déplacent et se retirent quel que soit l'outil.
    if context.removesuffix("_paint") in ("brush", "fill", "rect", "eraser"):
        rows += [(label("hints.bg.key_animated_drag"), "hints.bg.move_animated")]
    return _TITLES.get(context.removesuffix("_paint"), "bginp.brush"), rows
