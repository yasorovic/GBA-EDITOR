"""Migre les ids d'un projet vers le format hexadécimal de 12 caractères.

Avant : variables et textes portaient un entier de 12 chiffres décimaux, les
dossiers et les notes un `uuid4().hex` de 32 caractères. Après : tous portent
12 chiffres hexadécimaux (cf. `editor/core/models/ids.py`).

    python tools/migrate_ids_to_hex.py "Project Demo/PongAdvanced" "Project Demo/Platformer"
    python tools/migrate_ids_to_hex.py --dry-run <projet>

Ce qui est réécrit, dans `<projet>/project/` :
  - `variables.json`            — l'`id` de chaque global et constante ;
  - `texts.json`, `texts_*.json` — l'`id` de chaque texte (le maître et les sides) ;
  - tout JSON du dossier        — les références de champ `"var": <entier>` ;
  - `editor/scene-tree.json`, `editor/asset-folders.json`, `editor/scene-graph.json`
                                 — ids de dossier et de note (clés, `parent_id`,
                                 `hidden_folders`…).

Le nouvel id est DÉRIVÉ de l'ancien (SHA-256 tronqué), pas tiré au sort : deux
exécutions donnent le même résultat, et le même ancien id (par exemple celui
d'un texte dans le maître et dans ses sides) devient toujours le même nouvel id.
La réécriture est textuelle, pas un `json.dump` : mise en page et fins de ligne
restent ceux du fichier.

Idempotent : un projet déjà migré n'a plus d'entier ni d'uuid à convertir.
Une sauvegarde faite avec l'ancien format n'est plus relue par la ROM (l'id de
sauvegarde dérive de l'id de variable) ; sans objet tant que le projet n'est
pas diffusé.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ID_HEX_LENGTH = 12   # miroir de `core.models.ids.ID_HEX_LENGTH`

_INT_ID_FIELD = re.compile(r'("id"\s*:\s*)(\d+)(?=\s*[,}\r\n])')
_VAR_REF = re.compile(r'("var"\s*:\s*)(\d+)(?=\s*[,}\r\n])')
_UUID_TOKEN = re.compile(r'"([0-9a-f]{32})"')

_DATA_FILES = ("variables.json", "texts.json")
_FOLDER_FILES = ("scene-tree.json", "asset-folders.json", "scene-graph.json")


def derived_id(old: str) -> str:
    return hashlib.sha256(str(old).encode("utf-8")).hexdigest()[:ID_HEX_LENGTH]


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _write(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def _mapping(olds: set[str], where: str) -> dict[str, str]:
    mapping = {old: derived_id(old) for old in sorted(olds)}
    if len(set(mapping.values())) != len(mapping):
        raise SystemExit(f"{where}: two different ids derive to the same new id")
    return mapping


def _int_ids(text: str) -> set[str]:
    return {m.group(2) for m in _INT_ID_FIELD.finditer(text)}


def _project_files(root: Path, pattern: str) -> list[Path]:
    return sorted((root / "project").glob(pattern))


def _validate(path: Path, text: str) -> None:
    try:
        json.loads(text)
    except ValueError as exc:
        raise SystemExit(f"{path}: rewrite produced invalid JSON ({exc})")


def migrate(root: Path, dry_run: bool) -> int:
    """Retourne le nombre de fichiers modifiés."""
    project_dir = root / "project"
    if not project_dir.is_dir():
        raise SystemExit(f"{root}: no project/ folder")

    # Entiers : variables d'un côté, textes (maître + sides) de l'autre.
    variables_file = project_dir / "variables.json"
    variable_ids = _int_ids(_read(variables_file)) if variables_file.exists() else set()
    text_files = _project_files(root, "texts.json") + _project_files(root, "texts_*.json")
    text_ids: set[str] = set()
    for path in text_files:
        text_ids |= _int_ids(_read(path))
    variable_map = _mapping(variable_ids, "variables")
    text_map = _mapping(text_ids, "texts")

    # uuid : dossiers et notes, dans les trois sidecars d'éditeur.
    folder_files = [project_dir / "editor" / name for name in _FOLDER_FILES
                    if (project_dir / "editor" / name).exists()]
    uuids: set[str] = set()
    for path in folder_files:
        uuids |= {m.group(1) for m in _UUID_TOKEN.finditer(_read(path))}
    uuid_map = _mapping(uuids, "folders")

    changed = 0

    def rewrite(path: Path, text: str, label: str) -> None:
        nonlocal changed
        if text == _read(path):
            return
        _validate(path, text)
        changed += 1
        print(f"  {path.relative_to(root)}  ({label})")
        if not dry_run:
            _write(path, text)

    if variables_file.exists():
        text = _INT_ID_FIELD.sub(lambda m: f'{m.group(1)}"{variable_map[m.group(2)]}"',
                                 _read(variables_file))
        rewrite(variables_file, text, f"{len(variable_map)} variable ids")
    for path in text_files:
        text = _INT_ID_FIELD.sub(lambda m: f'{m.group(1)}"{text_map[m.group(2)]}"', _read(path))
        rewrite(path, text, "text ids")

    # Références `"var": <entier>` : partout sauf variables.json, qui porte les
    # ids eux-mêmes. Un entier inconnu est une référence cassée : on s'arrête
    # plutôt que d'inventer un lien.
    def var_ref(path: Path):
        def replace(m: re.Match) -> str:
            old = m.group(2)
            if old not in variable_map:
                raise SystemExit(f"{path}: reference to unknown variable id {old}")
            return f'{m.group(1)}"{variable_map[old]}"'
        return replace

    for path in sorted(project_dir.rglob("*.json")):
        if path == variables_file or path in text_files or path.parent.name == "build":
            continue
        original = _read(path)
        text = _VAR_REF.sub(var_ref(path), original)
        if path in folder_files:
            text = _UUID_TOKEN.sub(lambda m: f'"{uuid_map[m.group(1)]}"', text)
        rewrite(path, text, "references" if path not in folder_files else "folder and note ids")
    return changed


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("projects", nargs="+", type=Path, help="project root folder(s)")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args(argv)
    total = 0
    for root in args.projects:
        print(root)
        total += migrate(root, args.dry_run)
    print(f"{total} file(s) {'would be ' if args.dry_run else ''}rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
