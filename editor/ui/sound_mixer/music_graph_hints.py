"""ui/sound_mixer/music_graph_hints.py — contenu de la table des raccourcis du
graphe de musique (états et transitions). Pas d'outil : une seule table."""
from __future__ import annotations

from ui.common.labels import label
from ui.common.shortcut_hints import Hints, bound, mouse, view_rows


def music_graph_hints(_context: str) -> Hints:
    rows = [
        (mouse("left_click"), "hints.sound.select"),
        (mouse("left_drag"), "hints.sound.move_or_rubber_band"),
        (label("hints.sound.key_port_drag"), "hints.sound.link"),
        (label("hints.sound.key_arrow_end_drag"), "hints.sound.rewire"),
        (mouse("drop"), "hints.sound.drop_track"),
        ("Del", "hints.sound.delete"),
        (bound("sound.play_pause"), "hints.sound.play_pause"),
    ]
    return "hints.sound.title", rows + view_rows(None)
