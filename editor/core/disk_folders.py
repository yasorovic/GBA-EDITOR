"""
core/disk_folders.py — créer un dossier de `assets/`.

Une des écritures de l'onglet Disk (`core/disk_move.py` déplace et renomme ; `core/disk_tree.py` ne fait que lire).
Un dossier n'est qu'un dossier du disque : rien n'est écrit dans le projet, rien ne
change pour le build. La création refuse tout ce qui sort de `assets/` — un chemin remonté (`..`), un
autre disque — et rend `None` plutôt que de lever : un refus est une réponse, pas une panne.
"""
from __future__ import annotations

import os
from pathlib import Path

from core.models.unique_name import unique_name

# Ce qu'un nom de dossier ou de fichier ne peut pas contenir sous Windows — la liste la plus stricte des
# systèmes visés : un projet doit pouvoir passer d'une machine à l'autre.
_FORBIDDEN = set('<>:"/|?*') | {chr(92)}      # chr(92) : la barre oblique inverse


def valid_entry_name(name: str) -> bool:
    name = name.strip()
    return (bool(name) and name not in (".", "..")
            and not (_FORBIDDEN & set(name))
            and name == name.rstrip(". "))        # Windows retire en silence un point ou une espace final


def inside(root: Path, path: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return False
    return True


def create_folder(parent: Path, base: str, root: Path) -> Path | None:
    """Crée `parent/base` (`base_2`, `base_3`… si le nom est pris, comme partout dans
    l'éditeur). `None` si `parent` n'est pas un dossier de `root`."""
    parent = Path(parent)
    if not parent.is_dir() or not inside(root, parent):
        return None
    name = unique_name(base, {entry.name for entry in os.scandir(parent)})
    try:
        (parent / name).mkdir()
    except OSError:          # un homonyme à la casse près sous Windows, un droit refusé
        return None
    return parent / name
