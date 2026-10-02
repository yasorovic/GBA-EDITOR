"""ui/background_editor/bg_hints.py — contenu de la table des raccourcis du
Background Editor. Contexte = outil de peinture actif, ou « crop » / « resize »
quand un mode de préparation de la source est ouvert (il prend alors la main)."""
from __future__ import annotations

from ui.common.labels import label
from ui.common.shortcut_hints import Hints, combo, mouse, view_rows

_TITLES = {
    "brush": "bginp.brush",
    "fill": "bginp.fill",
    "rect": "cvtool.rectangle",
    "eraser": "bginp.eraser",
    "crop": "bginp.crop",
    "resize": "bginp.resize",
}

_ROWS = {
    "brush": [(mouse("left_drag"), "hints.bg.paint")],
    "fill": [(mouse("left_click"), "hints.bg.fill")],
    "rect": [(mouse("left_drag"), "hints.bg.paint_rect")],
    "eraser": [(mouse("left_drag"), "hints.bg.erase")],
    "crop": [
        (mouse("left_drag"), "hints.bg.crop_adjust"),
        (combo("Shift", mouse("left_drag")), "hints.bg.keep_ratio"),
        (combo("Ctrl", mouse("left_drag")), "hints.bg.snap_grid"),
        ("Enter", "hints.bg.crop_apply"),
        ("Esc", "hints.bg.crop_cancel"),
    ],
    "resize": [
        (mouse("left_drag"), "hints.bg.resize_drag"),
        (combo("Shift", mouse("left_drag")), "hints.bg.keep_ratio"),
        (combo("Ctrl", mouse("left_drag")), "hints.bg.snap_grid"),
    ],
}


def background_hints(context: str) -> Hints:
    rows = list(_ROWS.get(context, []))
    # Les fonds animés posés se déplacent et se retirent quel que soit l'outil.
    if context in ("brush", "fill", "rect", "eraser"):
        rows += [(label("hints.bg.key_animated_drag"), "hints.bg.move_animated"),
                 ("Del", "hints.bg.delete_animated")]
    return _TITLES.get(context, "bginp.brush"), rows + view_rows(None)
