"""Un fond cite son image par un chemin relatif au projet : `sky.png` devient `assets/backgrounds/sky.png`.

Avant : `BackgroundAsset.asset` ne retenait que le NOM du fichier, retrouvé dans `assets/backgrounds/`.
Après : comme les sprites et les sons, il porte le chemin de l'image relatif au projet, et l'image peut
être rangée où l'on veut sous `assets/`.

    python tools/migrate_background_paths.py "Project Demo/PongAdvanced" "Project Demo/Platformer"
    python tools/migrate_background_paths.py --dry-run <projet>

Ce qui change : le champ `asset` de chaque `*.background` sous `assets/` dont la valeur n'est qu'un nom de
fichier (sans `/`). Le reste du fichier n'est pas touché. Idempotent : un fond déjà migré n'a plus rien à changer.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_ASSET = re.compile(r'("asset"\s*:\s*")([^"/\\]+)(")')


def migrate(root: Path, dry_run: bool) -> int:
    """Retourne le nombre de fonds migrés."""
    assets = root / "assets"
    if not assets.is_dir():
        raise SystemExit(f"{root}: no assets/ folder — not a project folder")
    count = 0
    for path in sorted(assets.rglob("*.background")):
        text = path.read_text(encoding="utf-8")
        match = _ASSET.search(text)                                 # le premier : le champ de premier niveau
        if match is None:
            continue
        expected = f"assets/backgrounds/{match.group(2)}"
        new_text = text[:match.start()] + match.group(1) + expected + match.group(3) + text[match.end():]
        if json.loads(new_text).get("asset") != expected:           # le premier `"asset"` n'était pas celui de premier niveau
            raise SystemExit(f"{path}: unexpected layout, nothing changed")
        print(f"  {path.relative_to(root).as_posix()}  ->  {expected}")
        if not dry_run:
            path.write_text(new_text, encoding="utf-8", newline="")
        count += 1
    return count


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("projects", nargs="+", type=Path, help="project root folder(s)")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args(argv)
    total = 0
    for root in args.projects:
        print(root)
        total += migrate(root, args.dry_run)
    print(f"{total} background(s) {'would be ' if args.dry_run else ''}migrated")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
