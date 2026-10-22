"""
core/disk_tree.py — le dossier `assets/` tel qu'il est sur le disque, annoté de
ce que le projet en fait. C'est ce que montre l'onglet Disk (lecture seule).

Le disque est la vérité : l'arbre n'invente aucun dossier et n'en cache aucun.
Chaque fichier reçoit seulement une MARQUE, qui dit sa place dans le projet :

  ASSET          le fichier d'un asset (son sidecar, ou un script `.lua`)
  LINKED_SOURCE  une source qu'un asset cite — l'asset est nommé
  FREE_SOURCE    un format que l'éditeur sait lire, qu'aucun asset ne cite
  UNSUPPORTED    tout le reste

Aucune écriture, aucune décision : la création d'un asset à partir d'une source
viendra avec le clic droit, plus tard.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from core.models.audio import MUSIC_FILE_EXTS, SFX_FILE_EXTS
from core.models.font import FONT_FILE_EXTS
from core.models.sprite import IMAGE_FILE_EXTS

FOLDER = "folder"
ASSET = "asset"
LINKED_SOURCE = "linked_source"
FREE_SOURCE = "free_source"
UNSUPPORTED = "unsupported"

# Etat visuel d'une entrée. Il est distinct de `kind` : `kind` décrit CE QUE
# le fichier est, alors que `status` dit si l'auteur a une action à faire.
STATUS_OK = "ok"
STATUS_ORPHAN_SOURCE = "orphan_source"
STATUS_MISSING_SOURCE = "missing_source"
STATUS_NEUTRAL = "neutral"

# Ce que l'éditeur sait lire comme SOURCE : l'union des listes de chaque famille
# (images, sons, musiques, polices) et le `.hex` d'une palette. Les listes
# elles-mêmes restent la seule source — ici on ne fait que les réunir.
SOURCE_EXTENSIONS = (IMAGE_FILE_EXTS | SFX_FILE_EXTS | MUSIC_FILE_EXTS
                     | FONT_FILE_EXTS | {".hex"})


@dataclass
class DiskNode:
    name: str                                   # nom sur le disque
    path: Path
    kind: str                                   # FOLDER | ASSET | LINKED_SOURCE | FREE_SOURCE | UNSUPPORTED
    owner: str = ""                             # nom de l'asset (ASSET, LINKED_SOURCE)
    family: str = ""                            # famille de l'asset (« sfx », « sprites »…), vide si inconnue
    children: list["DiskNode"] = field(default_factory=list)
    status: str = STATUS_NEUTRAL                  # OK | source libre | source manquante | information

    def walk(self):
        """Ce nœud puis tous ses descendants, dans l'ordre d'affichage."""
        yield self
        for child in self.children:
            yield from child.walk()


def _key(path) -> str:
    """Clé de comparaison d'un chemin : absolu et insensible à la casse sous Windows."""
    return os.path.normcase(os.path.abspath(path))


# `{clé de chemin: (nom d'asset, famille)}`
_Links = dict[str, tuple[str, str]]


def _linked_files(project) -> tuple[_Links, _Links, set[str]]:
    """`(fichiers d'asset, sources citées, assets à source absente)`."""
    assets: _Links = {}
    cited: dict[str, list[tuple[str, str]]] = {}
    missing_assets: set[str] = set()
    for family, store, source_paths in project.source_families():
        for item in store:
            asset_path = store.path_of(item)
            assets[_key(asset_path)] = (item.name, family)
            for path in source_paths(project, item):
                if path.exists():
                    cited.setdefault(_key(path), []).append((item.name, family))
                else:
                    missing_assets.add(_key(asset_path))
    # Ce que l'auteur crée dans l'éditeur n'a pas de source : le fichier est tout l'asset.
    for family, store in project.authored_families():
        for item in store:
            assets[_key(store.path_of(item))] = (item.name, family)
    # Les tables du projet entier, posées à la racine de `assets/` : textes (le maître et une traduction
    # par langue déclarée) et variables.
    assets[_key(project.texts_file)] = ("texts", "texts")
    for code in project.translations:
        assets[_key(project.translation_file(code))] = (code, "texts")
    assets[_key(project.variables_file)] = ("variables", "variables")
    # Une source peut avoir donné plusieurs assets (un sprite ET un fond tirés du même PNG) : on les nomme tous.
    sources: _Links = {key: (", ".join(name for name, _ in owners), owners[0][1]) for key, owners in cited.items()}
    return assets, sources, missing_assets


def _classify(path: Path, assets: _Links, sources: _Links, missing_assets: set[str]) -> tuple[str, str, str, str]:
    """`(marque, nom d'asset, famille, état)` d'un fichier."""
    key = _key(path)
    if key in assets:
        return (ASSET, *assets[key], STATUS_MISSING_SOURCE if key in missing_assets else STATUS_OK)
    if key in sources:
        return (LINKED_SOURCE, *sources[key], STATUS_OK)
    suffix = path.suffix.lower()
    if suffix == ".lua":                         # un script est directement son asset
        return ASSET, path.stem, "scripts", STATUS_OK
    if suffix in SOURCE_EXTENSIONS:
        return FREE_SOURCE, "", "", STATUS_ORPHAN_SOURCE
    return UNSUPPORTED, "", "", STATUS_NEUTRAL


def _scan(folder: Path, assets: _Links, sources: _Links, missing_assets: set[str]) -> list[DiskNode]:
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return []
    nodes: list[DiskNode] = []
    for entry in entries:
        path = Path(entry.path)
        if entry.is_dir(follow_symlinks=False):
            nodes.append(DiskNode(entry.name, path, FOLDER, children=_scan(path, assets, sources, missing_assets)))
        else:
            kind, owner, family, status = _classify(path, assets, sources, missing_assets)
            nodes.append(DiskNode(entry.name, path, kind, owner, family, status=status))
    # Dossiers d'abord, puis les fichiers — chacun par ordre alphabétique.
    nodes.sort(key=lambda n: (n.kind != FOLDER, n.name.casefold()))
    return nodes


def build_disk_tree(project) -> DiskNode:
    """L'arbre de `assets/`. Les familles différées doivent être chargées
    (`project.load_all_resources()`), sinon leurs assets passeraient pour des
    sources libres."""
    assets, sources, missing_assets = _linked_files(project)
    root = project.user_library_dir
    return DiskNode(root.name, root, FOLDER, children=_scan(root, assets, sources, missing_assets))
