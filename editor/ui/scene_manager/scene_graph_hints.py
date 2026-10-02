"""ui/scene_manager/scene_graph_hints.py — contenu de la table des raccourcis du
Graphe des scènes. Pas d'outil ici : une seule table, celle de la vue."""
from __future__ import annotations

from ui.common.shortcut_hints import Hints, bound, combo, mouse, view_rows


def scene_graph_hints(_context: str) -> Hints:
    rows = [
        (mouse("left_click"), "hints.graph.select"),
        (combo("Ctrl / Shift", mouse("left_click")), "hints.graph.extend_selection"),
        (mouse("left_drag"), "hints.graph.move_or_rubber_band"),
        (mouse("double_click"), "hints.graph.open"),
        ("→ / ←", "hints.graph.enter_leave_group"),
        (bound("scene.group"), "hints.graph.group"),
        (bound("scene.graph_search"), "hints.graph.search"),
        (bound("scene.graph_toggle_minimap"), "hints.graph.minimap"),
        (bound("scene.graph_deselect"), "hints.graph.deselect"),
    ]
    rows += view_rows("scene.graph_fit", "hints.graph.fit")
    rows.append((combo("Space", mouse("left_drag")), "hints.pan"))
    rows.append((bound("scene.graph_zoom_reset"), "hints.graph.zoom_reset"))
    return "hints.graph.title", rows
