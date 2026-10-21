"""
core/asset_duplication.py — dupliquer un asset : une variante, qui POINTE la même source.

Un asset n'est pas son fichier source : deux assets peuvent citer le même `.wav`
ou le même PNG avec des réglages différents. Dupliquer en est le geste — l'auteur ne réimporte pas, ne recrée pas, il
part d'un asset réglé.

- **La copie** est le sidecar relu : les champs de l'original, son `asset` (la source n'est JAMAIS copiée), un NOUVEL id
  (donné à l'écriture), un nom libre dans son type (`coin`, `coin_2`), et elle est rangée à côté de l'original.
- **Indépendante** : aucun lien vivant avec l'original.
- **Annulable** : `Duplication.command` est un `CreateAssetCmd` non poussé ; le finder et l'onglet Disk le poussent, seul
  ou groupé dans un `MacroCmd` pour un lot.
- **Une seule exception, la palette** : ses couleurs vivent dans un `.hex` que deux palettes ne peuvent pas partager (cf.
  `asset_creation.palette_is_taken`) ; la copie reçoit donc SON `.hex`, écrit dans le dossier des palettes.
- **Les scripts** sont des fichiers, pas des assets de store : `duplicate_script` en copie le fichier.
- **Les sources** (un `.wav`, un PNG…) se copient de même, à côté de l'original, sous un nom libre : `duplicate_sources`.
  La copie est une source LIBRE — aucun asset ne la cite, `Create` en tire un asset quand l'auteur le veut.

Ce module construit la commande ; il ne l'exécute pas (l'historique est affaire de l'appelant).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.models import project_json
from core.models.unique_name import unique_name

# `coin_2` : la forme que `unique_name` écrit. Dupliquer `coin_2` redonne `coin_3`, pas `coin_2_2`.
_NUMBERED = re.compile(r"^(?P<base>.+)_\d+$")


@dataclass
class Duplication:
    """Ce que `duplicate` a préparé : la commande (NON poussée) et l'asset neuf qu'elle range."""
    command: object
    item: object


def duplicable_families(project) -> tuple[str, ...]:
    """Les familles dont un asset se duplique : toutes celles que le projet range dans un store, adossées à une source
    ou non. La même table que l'arbre Disk — une famille ajoutée là l'est ici. Les textes et les variables (un fichier
    pour tout le projet) n'y sont pas."""
    return (tuple(family for family, _store, _sources in project.source_families())
            + tuple(family for family, _store in project.authored_families()))


def is_duplicable(project, family: str) -> bool:
    return family in duplicable_families(project)


def copy_name(base: str, taken) -> str:
    """Le nom de la copie de `base` : `base_2`, `base_3`… Si `base` est lui-même un `x_N` dont `x` existe (une copie
    d'une copie), la suite continue sur `x` plutôt que de s'empiler en `x_2_2`."""
    taken = set(taken)
    numbered = _NUMBERED.match(base)
    root = numbered.group("base") if numbered and numbered.group("base") in taken else base
    return unique_name(root, taken | {root})


def _taken_names(store) -> set[str]:
    """Les noms que la copie ne peut pas prendre : ceux du store, et ceux que son inventaire disque connaît encore
    (un asset supprimé, pas encore effacé, garde son fichier)."""
    return {item.name for item in store} | set(store.known_names())


def _copy_of(store, item):
    """L'asset `item` relu depuis sa propre sérialisation : exactement ce que `save` écrirait puis `load` relirait."""
    if hasattr(item, "colors"):
        # Une palette : ses couleurs, SANS le chemin de son `.hex` — la copie en écrit un à elle.
        return store.cls(name=item.name, colors=list(item.colors), size=item.size)
    copied = store.cls.from_dict(json.loads(project_json.dumps(item.to_dict())))
    # Une copie de table n'hérite pas du lien de l'original.
    if getattr(copied, "text_link", None):
        copied.text_link = {}
    return copied


def duplicate(project, family: str, item, taken: Optional[set] = None) -> Duplication:
    """La copie de `item` (de la famille `family`) et la commande qui la range, à côté de l'original.

    `taken` : les noms déjà pris, que l'appelant d'un LOT partage d'un appel à l'autre — chaque copie y ajoute le sien,
    de sorte que deux copies du même lot ne se rencontrent pas. Absent : le store seul décide."""
    from core.history import CreateAssetCmd
    if not is_duplicable(project, family):
        raise ValueError(f"{family} cannot be duplicated")
    store = getattr(project, family)
    names = _taken_names(store) if taken is None else taken
    copy = _copy_of(store, item)
    copy.name = copy_name(item.name, names)
    names.add(copy.name)
    folder = Path(store.path_of(item)).parent
    return Duplication(CreateAssetCmd(store, copy, folder), copy)


def duplicate_many(project, family: str, items) -> list[Duplication]:
    """Une `Duplication` par asset, leurs noms uniques ENTRE EUX aussi."""
    store = getattr(project, family)
    taken = _taken_names(store)
    return [duplicate(project, family, item, taken) for item in items]


def duplicate_sources(paths, around=None):
    """`(commande, [copies])` : un fichier source copié à côté de lui, sous un nom libre dans SON dossier (toutes
    extensions confondues : `coin.wav` et `coin.sfx` ne doivent pas donner `coin_2` deux fois pour deux fichiers
    différents). Les copies d'un même lot ne se rencontrent pas. UNE commande pour tout le lot, annulable (c'est
    `ImportFilesCmd`, qui retire les copies à l'annulation — l'original n'est jamais touché)."""
    from contextlib import nullcontext
    from core.disk_commands import ImportFilesCmd
    taken_by_folder: dict[Path, set] = {}
    copies = []
    for raw in paths:
        source = Path(raw)
        taken = taken_by_folder.setdefault(source.parent, {entry.stem for entry in source.parent.iterdir()})
        stem = copy_name(source.stem, taken)
        taken.add(stem)
        copies.append((source, source.with_name(f"{stem}{source.suffix}")))
    return ImportFilesCmd(copies, around=around or nullcontext), [target for _source, target in copies]


def duplicate_script(path, taken_stems, around=None):
    """`(commande, nouveau chemin)` : la copie d'un script, à côté de lui, sous un nom libre parmi `taken_stems` (les noms
    de TOUS les scripts du projet : un behavior se retrouve par son nom). `around` : le contexte à ouvrir autour de
    l'écriture (le surveillant suspendu), comme les autres commandes de fichier."""
    from contextlib import nullcontext
    from core.disk_commands import CreateFileCmd
    source = Path(path)
    stems = set(taken_stems)
    stem = copy_name(source.stem, stems)
    target = source.with_name(f"{stem}{source.suffix}")
    return CreateFileCmd(target, source.read_bytes(), around=around or nullcontext), target
