"""
core/disk_move.py — déplacer fichiers et dossiers de `assets/` d'un dossier à un autre.

Une des écritures de l'onglet Disk (l'autre, `core/disk_folders.py`, crée un dossier). Renommer est un déplacement
sur place : même suivi des références.
Un asset se retrouve par l'extension de son sidecar, où qu'il soit sous `assets/` : déplacer un sidecar ne
demande donc rien d'autre. Ce qui demande un travail, c'est une SOURCE citée par un asset (un `.wav`, un
`.png`…) : l'asset la désigne par son chemin, qui doit suivre le fichier. Après le déplacement, chaque asset
dont la source était sous un chemin déplacé voit son chemin réécrit.

Rien n'est jamais écrasé : un fichier du même nom à destination refuse ce déplacement-là, sans toucher aux
autres. Quelques fichiers ne bougent pas, parce que le reste du code les cherche à un endroit précis :
les textes et variables, et les scripts `.lua`.
Un refus est une réponse (`MoveResult.refused`), pas une panne.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from core.disk_folders import inside, valid_entry_name
from core.resources.resource_index import list_files

# Les motifs d'un refus, que l'interface traduit.
OUTSIDE = "outside"            # la source ou la destination n'est pas dans `assets/` (ou c'est `assets/` lui-même)
INTO_ITSELF = "into_itself"    # un dossier ne peut pas se ranger dans lui-même
EXISTS = "exists"              # un fichier du même nom est déjà là
PROTECTED = "protected"        # un fichier que le reste du code cherche à un endroit précis
FAILED = "failed"              # le système a refusé (fichier ouvert ailleurs, droit refusé)

# Les champs d'un asset qui désignent un fichier source.
_SOURCE_SLOTS = ("asset", "descriptor")


@dataclass
class MoveResult:
    moved: list[tuple[Path, Path]] = field(default_factory=list)      # (avant, après)
    refused: list[tuple[Path, str]] = field(default_factory=list)     # (chemin, motif)


def _is_under(path: Path, folder: Path) -> bool:
    """`path` est `folder` ou dedans. Comparé par parties, donc SENSIBLE à la casse : `Path.relative_to` sous Windows
    confond `scr` et `SCR`, qui sont pourtant deux dossiers distincts quand le dossier parent est sensible à la casse."""
    return path.parts[:len(folder.parts)] == folder.parts


def _protected_files(project) -> set[Path]:
    """Les tables du projet entier."""
    files: set[Path] = set()
    files.add(project.texts_file.resolve())
    files.add(project.variables_file.resolve())
    files.update(project.translation_file(code).resolve() for code in project.translations)
    return files


def _files_in(path: Path):
    if path.is_dir():
        for folder, _, names in os.walk(path):
            for name in names:
                yield Path(folder) / name
    else:
        yield path


def _is_protected(path: Path, protected: set[Path]) -> bool:
    return any(f.resolve() in protected for f in _files_in(path))


_NOTHING = "nothing"            # déjà dans ce dossier : ni déplacement ni refus


def _verdict(raw, target: Path, assets: Path, protected: set[Path]) -> tuple[Path, str | None]:
    """`(chemin résolu, motif)` : `None` si le déplacement est possible, `_NOTHING` s'il n'y a rien à faire,
    sinon le motif du refus. La SEULE règle, lue par le déplacement et par le survol de l'interface."""
    source = Path(raw)
    if not source.exists() or not inside(assets, source) or source.resolve() == assets:
        return source, OUTSIDE
    source = source.resolve()
    if source.parent.parts == target.parts:
        return source, _NOTHING
    if _is_under(target, source):
        return source, INTO_ITSELF
    if (target / source.name).exists():
        return source, EXISTS
    if _is_protected(source, protected):
        return source, PROTECTED
    return source, None


def drop_verdict(project, paths, target) -> tuple[bool, tuple[Path, str] | None]:
    """`(possible, refus)` pour un glisser de `paths` vers `target`, SANS rien toucher : c'est la question que
    pose l'interface au survol. `possible` : au moins un élément se déplacerait. `refus` : le premier élément
    refusé et son motif, pour le dire à l'auteur ; `None` s'il n'y en a pas (rien à déplacer n'est pas un refus)."""
    project.load_all_resources()
    assets = project.user_library_dir.resolve()
    target = Path(target)
    if not target.is_dir() or not inside(assets, target):
        return False, ((Path(paths[0]), OUTSIDE) if paths else None)
    protected = _protected_files(project)
    target = target.resolve()
    verdicts = [_verdict(p, target, assets, protected) for p in paths]
    refusal = next(((source, reason) for source, reason in verdicts if reason not in (None, _NOTHING)), None)
    return any(reason is None for _, reason in verdicts), refusal


def move_to_folder(project, paths, target) -> MoveResult:
    """Range `paths` (fichiers et dossiers) dans le dossier `target`. Les chemins que l'asset cite sont réécrits."""
    project.load_all_resources()                       # sans les familles différées, leurs assets pointeraient encore l'ancien chemin
    assets = project.user_library_dir.resolve()
    result = MoveResult()
    target = Path(target)
    if not target.is_dir() or not inside(assets, target):
        result.refused = [(Path(p), OUTSIDE) for p in paths]
        return result
    target = target.resolve()
    protected = _protected_files(project)

    for raw in paths:
        source, reason = _verdict(raw, target, assets, protected)
        if reason == _NOTHING:
            continue                                   # déjà là : rien à faire, ce n'est pas un refus
        if reason is not None:
            result.refused.append((source, reason))
            continue
        destination = target / source.name
        try:
            shutil.move(str(source), str(destination))
        except OSError:
            result.refused.append((source, FAILED))
            continue
        result.moved.append((source, destination))

    if result.moved:
        _follow(project, result.moved, assets)
    return result


def rename_in_place(project, path, new_name: str) -> Path | None:
    """Renomme `path` (fichier ou dossier) sans le changer de dossier ; les chemins que l'asset cite sont réécrits,
    comme à un déplacement. `None` si le nom est invalide ou pris, ou si `path` est `assets/` lui-même, n'en fait pas
    partie, ou est un fichier que le code cherche à un endroit précis. Un nom inchangé rend `path` sans rien toucher."""
    project.load_all_resources()
    assets = project.user_library_dir.resolve()
    path = Path(path)
    new_name = new_name.strip()
    if (not valid_entry_name(new_name) or not path.exists()
            or not inside(assets, path) or path.resolve() == assets):
        return None
    if new_name == path.name:
        return path
    source = path.resolve()
    target = source.with_name(new_name)
    # Sous Windows `a` → `A` désigne le même fichier : ce n'est pas un nom pris.
    if (target.exists() and not os.path.samefile(target, source)) or _is_protected(source, _protected_files(project)):
        return None
    try:
        source.rename(target)
    except OSError:
        return None
    _follow(project, [(source, target)], assets)
    return path.with_name(new_name)


def _rewritten(project, value, moved: list[tuple[Path, Path]], root: Path) -> str | None:
    """Le nouveau chemin (relatif au projet) qu'une référence `value` doit prendre, ou `None` si ce qu'elle
    désigne n'a pas bougé."""
    current = project.asset_abs(value) if value else None
    if current is None:
        return None
    current = current.resolve()
    for before, after in moved:
        if _is_under(current, before):
            return (after / current.relative_to(before)).relative_to(root).as_posix()
    return None


def _repoint_scripts(project, moved: list[tuple[Path, Path]], root: Path) -> None:
    """Un script se désigne par son chemin dans les scènes (la scène, ses caméras, ses acteurs) et les
    prefabs : un script déplacé, ou rangé dans un dossier déplacé, ne doit pas perdre son attache."""
    for scene in project.scenes:
        touched = False
        owners = [(scene, "script"), *((cam, "script") for cam in scene.cameras)]
        for actor in scene.actors:
            comp = actor.get_component("script")
            if comp is not None:
                owners.append((comp, "script"))
        for owner, field in owners:
            fresh = _rewritten(project, getattr(owner, field, ""), moved, root)
            if fresh is not None:
                setattr(owner, field, fresh)
                touched = True
        if touched:
            project.save_scene(scene)
    for prefab in project.prefabs:
        comp = prefab.get_component("script")
        fresh = _rewritten(project, comp.script, moved, root) if comp is not None else None
        if fresh is not None:
            comp.script = fresh
            project.prefabs.save(prefab)


def _follow(project, moved: list[tuple[Path, Path]], assets: Path) -> None:
    """Remet le projet d'accord avec le disque : les index relisent les dossiers (un sidecar déplacé a un
    nouveau chemin), PUIS les assets dont la source a bougé voient leur chemin réécrit et sont enregistrés
    — dans cet ordre, sinon l'enregistrement écrirait le sidecar à son ancienne place."""
    listing = list_files(assets)                       # un seul parcours de `assets/` pour tous les index
    for store in project._resource_stores():
        store.scan_index(listing)
    root = project.root.resolve()
    _repoint_scripts(project, moved, root)
    for _, store, _ in project.source_families():
        for item in store:
            changed = False
            for slot in _SOURCE_SLOTS:
                fresh = _rewritten(project, getattr(item, slot, ""), moved, root)
                if fresh is not None:
                    setattr(item, slot, fresh)
                    changed = True
            if changed:
                store.save(item)
