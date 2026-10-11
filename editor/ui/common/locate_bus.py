"""locate_bus — LOCATE : demander à l'éditeur d'ouvrir l'onglet Disk sur un fichier.

Le geste part de partout — un finder, le canvas, l'arbre de scène — et aboutit en un seul
endroit, la fenêtre, qui possède l'onglet Disk. Chaque émetteur dit QUEL fichier (`path`) et
comment l'appeler à l'auteur (`name`, pour le message si le fichier n'existe pas) ; personne
n'a à connaître la fenêtre ni à recevoir un signal câblé écran par écran.

Deux gestes, deux noms (cf. `ui/common/reveal.py`) : *Locate* montre le fichier dans Disk,
*Reveal* le montre dans l'explorateur du système."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal


class LocateBus(QObject):
    requested = pyqtSignal(object, str)     # (Path | None, nom de l'élément)

    def locate(self, path: Path | None, name: str) -> None:
        self.requested.emit(path, name)


_bus: LocateBus | None = None


def get_locate_bus() -> LocateBus:
    global _bus
    if _bus is None:
        _bus = LocateBus()
    return _bus
