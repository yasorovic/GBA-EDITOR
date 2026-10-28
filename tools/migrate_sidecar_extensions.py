"""Donne à chaque asset l'extension de son type : `Player.json` devient `Player.sprite`.

Avant : tout asset stocké s'appelait `<nom>.json`. Après : son extension dit son type (`Player.sprite`,
`boom.sfx`, `Scene_01.scene`…) — le contenu reste du JSON, seul le nom du fichier change. La table des
extensions est `editor/core/models/asset_extensions.py`.

    python tools/migrate_sidecar_extensions.py "Project Test/PongAdvanced" "Project Demo/Platformer"
    python tools/migrate_sidecar_extensions.py --dry-run <projet>

Ce qui est renommé : chaque `*.json` d'un dossier de famille de `assets/` (sprites, backgrounds, sfx, music,
jingles, fonts, palettes, scenes, prefab, ui_layouts, music_boxes, jingle_boxes, sound_boxes, data,
fonts_assets), à n'importe quelle profondeur. Ce qui ne bouge pas : `texts.json`, `texts_<langue>.json` et
`variables.json` (à la racine de `assets/`), et le `.json` interne de l'éditeur sous `project/editor/`.

Rien n'est jamais écrasé : si `Player.sprite` existe déjà à côté de `Player.json`, le script s'arrête sur ce
projet et le dit, sans rien renommer. Idempotent : un projet déjà migré n'a plus de `.json` à renommer.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

_TABLE = Path(__file__).resolve().parents[1] / "editor" / "core" / "models" / "asset_extensions.py"
_spec = importlib.util.spec_from_file_location("asset_extensions", _TABLE)
asset_extensions = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(asset_extensions)


def _plan(root: Path) -> tuple[list[tuple[Path, Path]], list[str]]:
    """`(renommages, conflits)`."""
    renames: list[tuple[Path, Path]] = []
    conflicts: list[str] = []
    for folder, extension in asset_extensions.FAMILY_EXTENSIONS.items():
        directory = root / "assets" / folder
        if not directory.is_dir():
            continue
        for source in sorted(directory.rglob("*.json")):
            target = source.with_suffix(extension)
            if target.exists():
                conflicts.append(f"{target.relative_to(root).as_posix()} already exists")
            else:
                renames.append((source, target))
    return renames, conflicts


def migrate(root: Path, dry_run: bool) -> int:
    """Retourne le nombre de fichiers renommés ; sort sur une erreur si un conflit est détecté."""
    if not (root / "assets").is_dir():
        raise SystemExit(f"{root}: no assets/ folder — not a project folder")
    renames, conflicts = _plan(root)
    if conflicts:
        raise SystemExit(f"{root}: nothing renamed — " + "; ".join(conflicts))
    for source, target in renames:
        print(f"  {source.relative_to(root).as_posix()}  ->  {target.name}")
        if not dry_run:
            source.rename(target)
    return len(renames)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("projects", nargs="+", type=Path, help="project root folder(s)")
    parser.add_argument("--dry-run", action="store_true", help="report without renaming")
    args = parser.parse_args(argv)
    total = 0
    for root in args.projects:
        print(root)
        total += migrate(root, args.dry_run)
    print(f"{total} file(s) {'would be ' if args.dry_run else ''}renamed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
