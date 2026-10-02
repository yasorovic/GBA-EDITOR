"""ui/scene_manager/canvas/canvas_hints.py — contenu de la table des raccourcis
du canvas de scène, par outil actif (ids de `FloatingToolbar.tool_changed`)."""
from __future__ import annotations

from ui.common.shortcut_hints import Hints, bound, combo, key_icon, mouse, view_rows

_TITLES = {
    "select": "cvtool.select",
    "add": "cvtool.add_actor",
    "erase": "cvtool.eraser",
    "collision_8": "cvtool.8_8_px_brush",
    "collision_16": "cvtool.16_16_px_brush",
    "collision_slope": "cvtool.floor_slope",
    "collision_slope_inv": "cvtool.ceiling_slope",
    "inpaint_brush": "cvtool.scene_inpainting",
    "inpaint_rect": "cvtool.scene_inpainting",
    "ui_text": "cvtool.interface_widget",
    "ui_container": "cvtool.interface_widget",
    "ui_list": "cvtool.interface_widget",
    "ui_image": "cvtool.interface_widget",
}

_PAINT = [(mouse("left_drag"), "hints.scene.paint_solid"),
          (mouse("right_drag"), "hints.scene.erase_tiles")]
_SLOPE = [(mouse("left_drag"), "hints.scene.draw_slope"),
          (mouse("right_drag"), "hints.scene.erase_slope")]
_INPAINT_BRUSH = [(mouse("left_drag"), "hints.scene.inpaint_paint"),
                  (mouse("right_drag"), "hints.scene.inpaint_clear")]
_INPAINT_RECT = [(mouse("left_drag"), "hints.scene.inpaint_rect_paint"),
                 (mouse("right_drag"), "hints.scene.inpaint_rect_clear")]


def _tool_rows(tool: str) -> list:
    if tool == "select":
        return [
            (mouse("left_click"), "hints.scene.select_item"),
            (combo("Ctrl / Shift", mouse("left_click")), "hints.scene.extend_selection"),
            (mouse("left_drag"), "hints.scene.move_or_rubber_band"),
            (combo("Alt", mouse("left_drag")), "hints.scene.duplicate_drag"),
            (mouse("right_click"), "hints.scene.actor_menu"),
            (key_icon("dir_omni"), "hints.scene.nudge"),
            (bound("canvas.delete"), "hints.scene.delete"),
            (bound("canvas.duplicate"), "hints.scene.duplicate"),
            (f"{bound('canvas.copy')} / {bound('canvas.paste')}", "hints.scene.copy_paste"),
        ]
    if tool == "add":
        return [(mouse("left_click"), "hints.scene.place_actor")]
    if tool == "erase":
        return [(mouse("left_click"), "hints.scene.erase_actor")]
    if tool in ("collision_8", "collision_16"):
        return _PAINT
    if tool in ("collision_slope", "collision_slope_inv"):
        return _SLOPE
    if tool == "inpaint_brush":
        return _INPAINT_BRUSH
    if tool == "inpaint_rect":
        return _INPAINT_RECT
    if tool.startswith("ui_"):
        return [(mouse("left_click"), "hints.scene.ui_place_default"),
                (mouse("left_drag"), "hints.scene.ui_draw_rect")]
    return []


def scene_canvas_hints(tool: str) -> Hints:
    rows = _tool_rows(tool or "select")
    if tool and tool != "select":
        rows = rows + [(bound("canvas.cancel"), "hints.scene.back_to_select")]
    return _TITLES.get(tool or "select", "cvtool.select"), rows + view_rows()
