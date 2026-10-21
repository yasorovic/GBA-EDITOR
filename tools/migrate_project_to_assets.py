"""Déplace ce que l'auteur manipule de `project/` vers `assets/`.

Avant : scènes, prefabs, mises en page, boîtes sonores, tables de données, polices logiques, textes
et variables vivaient sous `project/`. Après : ils sont dans `assets/`, sous le même nom de dossier.

    python tools/migrate_project_to_assets.py "Project Demo/PongAdvanced" "Project Demo/Platformer"
    python tools/migrate_project_to_assets.py --dry-run <projet>

Ce qui bouge, dans `<projet>/` :
  project/scenes, prefab, ui_layouts, music_boxes, jingle_boxes, sound_boxes, data, fonts_assets
                                        →  assets/<même nom>/
  project/texts.json, texts_<langue>.json, variables.json
                                        →  assets/   (à la racine)

Ce qui reste dans `project/` : `editor/` (l'état interne de l'éditeur), `licenses/`, `README.md`.

Rien n'est jamais écrasé : si la destination contient déjà un fichier du même nom, le script s'arrête
sur ce dossier et le dit, sans rien toucher de ce qu'il a déjà déplacé de travers. Idempotent : un
projet déjà migré n'a plus rien à bouger. Les dossiers laissés vides sont supprimés.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

FOLDERS = ("scenes", "prefab", "ui_layouts", "music_boxes", "jingle_boxes",
           "sound_boxes", "data", "fonts_assets")
FILE_PATTERNS = ("texts.json", "texts_*.json", "variables.json")


def _plan(root: Path) -> tuple[list[tuple[Path, Path]], list[str]]:
    """`(déplacements, conflits)` : chaque déplacement est un fichier ou un dossier entier."""
    project, assets = root / "project", root / "assets"
    moves: list[tuple[Path, Path]] = []
    conflicts: list[str] = []
    for name in FOLDERS:
        source, target = project / name, assets / name
        if not source.is_dir():
            continue
        if not target.exists():
            moves.append((source, target))
            continue
        for child in sorted(source.iterdir()):          # le dossier de destination existe : fichier par fichier
            if (target / child.name).exists():
                conflicts.append(f"{(target / child.name).relative_to(root)} already exists")
            else:
                moves.append((child, target / child.name))
    for pattern in FILE_PATTERNS:
        for source in sorted(project.glob(pattern)):
            target = assets / source.name
            if target.exists():
                conflicts.append(f"{target.relative_to(root)} already exists")
            else:
                moves.append((source, target))
    return moves, conflicts


def migrate(root: Path, dry_run: bool) -> int:
    """Retourne le nombre d'éléments déplacés ; sort sur une erreur si un conflit est détecté."""
    if not (root / "project").is_dir() and not (root / "assets").is_dir():
        raise SystemExit(f"{root}: neither project/ nor assets/ — not a project folder")
    moves, conflicts = _plan(root)
    if conflicts:
        raise SystemExit(f"{root}: nothing moved — " + "; ".join(conflicts))
    for source, target in moves:
        print(f"  {source.relative_to(root)}  ->  {target.relative_to(root)}")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
    if not dry_run:
        for name in FOLDERS:                            # un dossier de `project/` devenu vide n'a plus de raison d'être
            leftover = root / "project" / name
            if leftover.is_dir() and not any(leftover.iterdir()):
                leftover.rmdir()
    return len(moves)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("projects", nargs="+", type=Path, help="project root folder(s)")
    parser.add_argument("--dry-run", action="store_true", help="report without moving")
    args = parser.parse_args(argv)
    total = 0
    for root in args.projects:
        print(root)
        total += migrate(root, args.dry_run)
    print(f"{total} item(s) {'would be ' if args.dry_run else ''}moved")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
