"""
core/script_owners.py — À quoi chaque fichier de script est attaché.

Un script n'a pas de type : c'est son ATTACHE qui lui donne son contexte — les
événements qu'il peut définir, l'existence de `self`. Trois familles de
propriétaire :

    "actor"   un acteur de scène ou un prefab (ils partagent `self` et les événements)
    "scene"   une scène
    "camera"  une caméra

Cette lecture est la source unique de la question « de quelle famille est ce
script ? » : le validateur s'en sert pour refuser un fichier attaché à deux
familles, l'éditeur de script pour ne proposer que les événements du propriétaire.
"""
from __future__ import annotations

from pathlib import Path

# famille → mot dit à l'auteur
FAMILY_LABELS = {"actor": "acteur/prefab", "scene": "scène", "camera": "caméra"}


def script_attachments(project) -> dict[str, dict[str, list[str]]]:
    """Fichier de script (chemin du projet, tel que stocké) → famille → propriétaires.

    Un composant script inactif n'attache rien : le build l'ignore aussi."""
    found: dict[str, dict[str, list[str]]] = {}

    def attach(path: str, family: str, owner: str):
        if path:
            found.setdefault(path, {}).setdefault(family, []).append(owner)

    for scene in project.scenes:
        attach(getattr(scene, "script", ""), "scene", f"scene \"{scene.name}\"")
        for actor in scene.actors:
            comp = actor.get_component("script")
            if comp and comp.active:
                attach(comp.script, "actor", f"actor \"{actor.name}\" ({scene.name})")
        for cam in scene.cameras:
            attach(getattr(cam, "script", ""), "camera", f"camera \"{cam.name}\"")
    for prefab in project.prefabs:
        comp = prefab.get_component("script")
        if comp and comp.active:
            attach(comp.script, "actor", f"prefab \"{prefab.name}\"")
    return found


def actors_and_prefabs_of_script(project, path: Path) -> list:
    """Les acteurs et prefabs (objets) dont le composant script actif désigne ce fichier."""
    target = Path(path).resolve()

    def uses(owner) -> bool:
        comp = owner.get_component("script")
        abs_path = project.asset_abs(comp.script) if comp and comp.active and comp.script else None
        return abs_path is not None and Path(abs_path).resolve() == target

    return ([a for scene in project.scenes for a in scene.actors if uses(a)]
            + [pf for pf in project.prefabs if uses(pf)])


def family_of_script(project, path: Path) -> str | None:
    """La famille du propriétaire de ce fichier, ou None s'il n'est attaché à rien
    (ou, cas refusé au build, à plusieurs familles à la fois : aucune ne l'emporte)."""
    target = Path(path).resolve()
    families: set[str] = set()
    for rel, by_family in script_attachments(project).items():
        abs_path = project.asset_abs(rel)
        if abs_path is not None and Path(abs_path).resolve() == target:
            families.update(by_family)
    return next(iter(families)) if len(families) == 1 else None
