"""WaypointPath - un itinéraire de points posé dans une scène.

Les points restent locaux à l'origine du Path. Sans parent, cette origine est
dans le monde. Avec un acteur parent, elle est recomposée avec cet acteur au
runtime, comme une Area : le même itinéraire peut alors voyager avec lui.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.models.scene_member import SceneMember


PATH_ONCE = "once"
PATH_LOOP = "loop"
PATH_PING_PONG = "ping_pong"
PATH_MODES = (PATH_ONCE, PATH_LOOP, PATH_PING_PONG)


def _point(value) -> tuple[int, int]:
    """Lit un point du fichier, sans jamais laisser entrer de flottant."""
    if isinstance(value, dict):
        return int(value.get("x", 0)), int(value.get("y", 0))
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return int(value[0]), int(value[1])
    return 0, 0


@dataclass
class WaypointPath(SceneMember):
    """Une route discrète que les scripts peuvent suivre ou lire point par point."""
    name: str = "Path"
    x: int = 120
    y: int = 80
    points: list = field(default_factory=lambda: [(-16, 0), (16, 0)])
    mode: str = PATH_LOOP
    parent: Optional[str] = None
    notes: str = ""

    def __post_init__(self):
        self.x, self.y = int(self.x), int(self.y)
        self.points = [_point(point) for point in self.points]
        if self.mode not in PATH_MODES:
            self.mode = PATH_LOOP

    def to_dict(self) -> dict:
        return {
            **self.member_header(),
            "x": self.x,
            "y": self.y,
            "points": [{"x": x, "y": y} for x, y in self.points],
            **({"mode": self.mode} if self.mode != PATH_LOOP else {}),
            **({"parent": self.parent} if self.parent else {}),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WaypointPath":
        path = cls(
            name=str(data.get("name", "Path")),
            x=data.get("x", 120),
            y=data.get("y", 80),
            points=data.get("points", []),
            mode=str(data.get("mode", PATH_LOOP)),
            parent=data.get("parent") or None,
            notes=str(data.get("notes", "")),
        )
        path.read_member_header(data)
        return path
