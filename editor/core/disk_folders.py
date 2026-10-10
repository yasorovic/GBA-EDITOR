"""
core/disk_folders.py — créer et renommer un dossier de `assets/`.

L'unique écriture de l'onglet Disk (le reste, `core/disk_tree.py`, ne fait que lire).
Un dossier n'est qu'un dossier du disque : rien n'est écrit dans le projet, rien ne
change pour le build. Les deux gestes refusent tout ce qui sort de `assets/` — un
chemin remonté (`..`), un autre disque — et rendent `None` plutôt que de lever : un
refus est une réponse, pas une panne.
"""
from __future__ import annotations

import os
from pathlib import Path

from core.models.unique_name import unique_name

# Ce qu'un nom de dossier ne peut pas contenir sous Windows — la liste la plus stricte des
# systèmes visés : un projet doit pouvoir passer d'une machine à l'autre.
_FORBIDDEN = set('<>:"/|?*') | {chr(92)}      # chr(92) : la barre oblique inverse


def valid_folder_name(name: str) -> bool:
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


def rename_folder(folder: Path, new_name: str, root: Path) -> Path | None:
    """Renomme `folder`. `None` si le nom est invalide ou déjà pris, ou si `folder` est `root`
    lui-même ou n'en fait pas partie. Un nom inchangé rend `folder` sans rien toucher."""
    folder = Path(folder)
    new_name = new_name.strip()
    if (not valid_folder_name(new_name) or not folder.is_dir()
            or not inside(root, folder) or folder.resolve() == Path(root).resolve()):
        return None
    if new_name == folder.name:
        return folder
    target = folder.with_name(new_name)
    # Sous Windows `a` → `A` désigne le même dossier : ce n'est pas un nom pris.
    if target.exists() and not os.path.samefile(target, folder):
        return None
    try:
        folder.rename(target)
    except OSError:
        return None
    return target
