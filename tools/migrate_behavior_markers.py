"""Marque les behaviors d'un projet : `-- @behavior` en première ligne des `.lua` de `assets/scripts/behaviors/`.

Avant : un script était un behavior parce qu'il vivait dans `assets/scripts/behaviors/`.
Après : son rôle vient de son contenu — la première ligne `-- @behavior` — et il se range où l'on veut
(cf. `core/lua_scripts.py`). `require("behaviors/<nom>")` ne change pas : il se résout par nom.

    python tools/migrate_behavior_markers.py "Project Test/PongAdvanced" "Project Demo/Platformer"
    python tools/migrate_behavior_markers.py --dry-run <projet>

Ce qui change : chaque `.lua` de `assets/scripts/behaviors/` qui ne commence pas déjà par le marqueur le reçoit
en tête, sur sa propre ligne (les fins de ligne du fichier sont respectées). Rien d'autre n'est touché.
Idempotent : un behavior déjà marqué n'est pas modifié.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MARKER = "-- @behavior"


def migrate(root: Path, dry_run: bool) -> int:
    """Retourne le nombre de fichiers marqués."""
    assets = root / "assets"
    if not assets.is_dir():
        raise SystemExit(f"{root}: no assets/ folder — not a project folder")
    folder = assets / "scripts" / "behaviors"
    count = 0
    for path in sorted(folder.glob("*.lua")) if folder.is_dir() else []:
        raw = path.read_bytes()
        bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
        text = raw[len(bom):].decode("utf-8")
        if text.split("\n", 1)[0].strip() == MARKER:
            continue
        newline = "\r\n" if "\r\n" in text else "\n"
        print(f"  {path.relative_to(root).as_posix()}")
        if not dry_run:
            path.write_bytes(bom + (MARKER + newline + text).encode("utf-8"))
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
    print(f"{total} behavior(s) {'would be ' if args.dry_run else ''}marked")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
