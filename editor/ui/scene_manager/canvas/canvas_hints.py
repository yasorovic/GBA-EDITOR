"""ui/scene_manager/canvas/canvas_hints.py : contenu de la table des raccourcis
du canvas de scène, par outil actif (ids de `FloatingToolbar.tool_changed`)."""
from __future__ import annotations

from ui.common.shortcut_hints import Hints, bound, combo, key_icon, mouse

_TITLES = {
    "select": "cvtool.select",
    "add": "cvtool.add_actor",
    "add_area": "cvtool.add_area",
    "erase": "cvtool.eraser",
    "paint_brush": "cvtool.surface_painting",
    "paint_rect": "cvtool.surface_painting",
    "paint_fill": "cvtool.surface_painting",
    "ui_text": "cvtool.interface_widget",
    "ui_textbox": "cvtool.interface_widget",
    "ui_container": "cvtool.interface_widget",
    "ui_list": "cvtool.interface_widget",
    "ui_image": "cvtool.interface_widget",
}

_PAINT = [(mouse("left_drag"), "hints.scene.paint_value"),
          (mouse("right_drag"), "hints.scene.paint_clear")]


def _tool_rows(tool: str) -> list:
    if tool == "select":
        return [
            (mouse("left_click"), "hints.scene.select_item"),
            (combo("Ctrl / Shift", mouse("left_click")), "hints.scene.extend_selection"),
            (mouse("left_drag"), "hints.scene.move_or_rubber_band"),
            (combo("Alt", mouse("left_drag")), "hints.scene.duplicate_drag"),
            (mouse("right_click"), "hints.scene.actor_menu"),
            (key_icon("dir_omni"), "hints.scene.nudge"),
        ]
    if tool == "add":
        return [(mouse("left_click"), "hints.scene.place_actor")]
    if tool == "add_area":
        return [(mouse("left_click"), "hints.scene.place_area")]
    if tool == "erase":
        return [(mouse("left_click"), "hints.scene.erase_actor")]
    if tool in ("paint_brush", "paint_rect", "paint_fill"):
        return _PAINT
    if tool.startswith("ui_"):
        return [(mouse("left_click"), "hints.scene.ui_place_default"),
                (mouse("left_drag"), "hints.scene.ui_draw_rect")]
    return []


def scene_canvas_hints(tool: str) -> Hints:
    rows = _tool_rows(tool or "select")
    if tool and tool != "select":
        rows = rows + [(bound("common.cancel"), "hints.scene.back_to_select")]
    return _TITLES.get(tool or "select", "cvtool.select"), rows
