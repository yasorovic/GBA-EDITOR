"""Index léger d'une collection de ressources persistées.

Un :class:`ResourceIndex` ne désérialise jamais un asset : il répond seulement
à « quels fichiers existent ? » et « où se trouve celui-ci ? ». C'est la
première moitié d'un chargement paresseux ; le cache d'objets reste dans
``ResourceStore``.
"""

from __future__ import annotations

import os
from pathlib import Path


_WIN_FORBIDDEN = str.maketrans({c: "_" for c in r'\/:*?"<>|'})


def safe_filename(name: str) -> str:
    """Forme disque canonique d'un nom de ressource sous Windows."""
    return name.translate(_WIN_FORBIDDEN).strip() or "_"


def list_files(directory: Path) -> list[Path]:
    """Tous les fichiers sous `directory`, en un seul parcours."""
    return [Path(folder) / name for folder, _, names in os.walk(directory) for name in names]


class ResourceIndex:
    """Inventaire ``nom de ressource → fichier`` d'une collection.

    Le nom exposé est le stem du fichier : comme dans ``ResourceStore``, le
    fichier est l'identité faisant foi lorsqu'un champ ``name`` du JSON a
    dérivé. Les entrées sont rangées par nom pour rendre les écrans et les tests
    déterministes.

    **L'inventaire est RÉCURSIF** : il parcourt tout `directory` (pour un projet,
    `assets/`) et retient les fichiers qui portent l'extension de la famille. Un
    sidecar peut donc vivre n'importe où (`assets/sfx/platformer/coin.sfx`,
    `assets/Persos/coin.sfx`), là où l'auteur l'a rangé : l'extension dit le type. Deux fichiers de même nom dans deux dossiers ne peuvent pas porter la
    même identité : celui qui est le moins profond l'emporte (à profondeur égale,
    l'ordre alphabétique du chemin), les autres sont gardés dans `duplicates` pour
    que l'application les signale — rien n'est renommé ni écrit ici.
    """

    def __init__(self, directory: Path, suffix: str):
        self.directory = directory
        self.suffix = suffix
        self._paths: dict[str, Path] = {}
        # {nom: [chemins ignorés]} — les homonymes que l'inventaire n'a pas retenus.
        self.duplicates: dict[str, list[Path]] = {}

    def scan(self, listing: list[Path] | None = None) -> None:
        """Reconstruit l'inventaire sans ouvrir le contenu des fichiers. `listing` : les fichiers déjà
        énumérés (`list_files`), pour que plusieurs index partagent UN parcours du disque."""
        self._paths = {}
        self.duplicates = {}
        if not self.directory.exists():
            return
        if listing is None:
            found = [p for p in self.directory.rglob(f"*{self.suffix}") if p.is_file()]
        else:
            found = [p for p in listing if p.name.endswith(self.suffix) and self.directory in p.parents]
        # Le moins profond d'abord : un sidecar posé à la racine du dossier l'emporte sur un homonyme rangé plus bas.
        found.sort(key=lambda p: (len(p.relative_to(self.directory).parts), p.relative_to(self.directory).as_posix()))
        kept: dict[str, Path] = {}
        for path in found:
            if path.stem in kept:
                self.duplicates.setdefault(path.stem, []).append(path)
            else:
                kept[path.stem] = path
        self._paths = dict(sorted(kept.items()))

    def names(self) -> tuple[str, ...]:
        """Noms connus, dans l'ordre stable du système de fichiers projet."""
        return tuple(self._paths)

    def path_for(self, name: str) -> Path | None:
        """Chemin du sidecar nommé ``name``, ou ``None`` s'il n'est pas indexé."""
        return self._paths.get(safe_filename(name))

    def record(self, name: str, path: Path | None = None) -> None:
        """Enregistre une écriture connue sans rescanner toute la collection."""
        stem = safe_filename(name)
        self._paths[stem] = path or self.directory / f"{stem}{self.suffix}"

    def forget(self, name: str) -> None:
        """Retire une ressource effacée de l'inventaire mémoire."""
        self._paths.pop(safe_filename(name), None)

    def __contains__(self, name: str) -> bool:
        return self.path_for(name) is not None
