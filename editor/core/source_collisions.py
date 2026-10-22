"""
core/source_collisions.py — quand un fichier importé porte le nom d'un fichier déjà rangé.

Une seule règle pour tous les gestes d'import et de remplacement : le même nom EXACT dans le dossier est une collision,
que l'auteur tranche (écraser / garder les deux) ; tout autre nom pris est suffixé par `unique_name`, sans question.
"""
from __future__ import annotations

from pathlib import Path

from core.models.unique_name import unique_name


def collides(source: Path, folder: Path) -> bool:
    """Copier `source` dans `folder` écraserait un AUTRE fichier (un fichier déjà dans `folder` se copie sous un nouveau nom)."""
    same_name = Path(folder) / Path(source).name
    return same_name.is_file() and same_name.resolve() != Path(source).resolve()


def destination(source: Path, folder: Path, overwrite: bool, taken_names=None) -> Path:
    """Où va la copie : le même nom si l'auteur écrase, sinon le premier nom libre (`taken_names` : les noms de fichier de
    ce lot). Seul un fichier de MÊME extension prend le nom : `village.xm` peut côtoyer `village.png`, deux sources de
    types différents ne se gênent pas et l'asset créé garde le nom que l'auteur a choisi pour son fichier."""
    source, folder = Path(source), Path(folder)
    if overwrite and collides(source, folder):
        return folder / source.name
    names = {entry.name for entry in folder.iterdir()} if folder.is_dir() else set()
    same_kind = {Path(n).stem for n in names | set(taken_names or ()) if Path(n).suffix.lower() == source.suffix.lower()}
    return folder / f"{unique_name(source.stem, same_kind)}{source.suffix}"


def citing(project, path: Path, exclude=None) -> list[str]:
    """Les assets (hors `exclude`) dont la source est `path` : écraser le fichier les change aussi."""
    target = Path(path).resolve()
    found = []
    for family, store, source_paths in project.source_families():
        for item in store:
            if item is not exclude and any(Path(p).resolve() == target for p in source_paths(project, item)):
                found.append(f"{family}: {item.name}")
    return found
