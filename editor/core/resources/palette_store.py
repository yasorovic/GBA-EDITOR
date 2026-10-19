"""Persistance des palettes : le ``.hex`` est la donnée canonique, la palette le POINTE.

Une palette est un asset ``<nom>.palette`` (du JSON : nom, taille, et ``asset`` — le chemin du ``.hex``
relatif au projet), rangé où l'auteur veut sous ``assets/``. Ses couleurs vivent dans le ``.hex``, lisible
et modifiable sans l'éditeur, et ne sont jamais dupliquées dans le ``.palette``. Comme pour les autres
familles, l'asset ne suit pas son fichier source, et le fichier ne suit pas son asset : seul le chemin
``asset`` les relie.

Un ``.hex`` que nul ``.palette`` ne cite est une source libre, comme un PNG qu'aucun asset ne cite : il devient
une palette par *Create from source*, jamais de lui-même. Une palette neuve naît avec son ``.hex`` à côté d'elle.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.models import project_json
from core.models.palette import PaletteBank
from core.resources.resource_store import ResourceStore, atomic_write


class PaletteStore(ResourceStore[PaletteBank]):
    """Catalogue de :class:`PaletteBank`, chacune pointant son fichier ``.hex``."""

    def __init__(self, root: Path, project_root: Path | None = None):
        super().__init__(root, PaletteBank)
        # Les chemins `asset` sont relatifs à la racine du PROJET (comme ceux des autres familles).
        self._project_root = Path(project_root) if project_root is not None else self.root

    # ── Où vit le .hex ────────────────────────────────────────────

    def _rel(self, path: Path) -> str:
        try:
            return Path(path).resolve().relative_to(self._project_root.resolve()).as_posix()
        except ValueError:
            return Path(path).as_posix()

    def _abs(self, rel: str) -> Path:
        path = Path(rel)
        return path if path.is_absolute() else (self._project_root / path).resolve()

    def hex_path(self, bank: PaletteBank) -> Path:
        """Le fichier des couleurs de `bank` : celui que son asset cite ; une palette neuve, qui n'en cite pas
        encore, aura le sien à côté de son `.palette`."""
        if bank.asset:
            return self._abs(bank.asset)
        return self._path(bank.name).with_suffix(".hex")

    def source_path(self, name: str) -> Path:
        bank = next((b for b in self.items if b.name == name), None)
        return self.hex_path(bank) if bank is not None else self._path(name).with_suffix(".hex")

    # ── Lecture ───────────────────────────────────────────────────

    def _load_metadata(self, path: Path) -> dict:
        """Les métadonnées du sidecar, ou {} s'il est illisible : le `.hex` est
        la donnée canonique, un JSON voisin abîmé ne doit pas faire disparaître
        la palette. Le fichier est signalé (`unreadable`) et sa copie de
        sauvegarde faite avant que le sidecar ne soit réécrit."""
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as error:
            self.unreadable[self._key(path)] = f"{type(error).__name__}: {error}"
            return {}
        return data if isinstance(data, dict) else {}

    def _write_sidecar(self, bank: PaletteBank, folder: Path | None = None) -> None:
        path = self._path(bank.name, folder)
        self._keep_unreadable(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, project_json.dumps(bank.to_metadata_dict()))
        self.index.record(bank.name, path)

    def _read(self, name: str, sidecar: Path) -> PaletteBank | None:
        """Lit la palette `name` : son sidecar, puis le `.hex` qu'il cite (à défaut, celui qui porte son nom à
        côté de lui). Une palette dont le `.hex` a disparu n'est pas chargée, et son sidecar n'est pas touché :
        supprimer le fichier source est une intention, pas une panne à réparer."""
        metadata = self._load_metadata(sidecar)
        cited = metadata.get("asset")
        hex_file = self._abs(cited) if isinstance(cited, str) and cited else sidecar.with_suffix(".hex")
        if not hex_file.exists():
            hex_file = self._migrate_colors_in_sidecar(name, sidecar, metadata, hex_file)
            if hex_file is None:
                return None
        try:
            bank = PaletteBank.from_hex(name, hex_file.read_text(encoding="utf-8"), metadata)
        except Exception as error:
            self.unreadable[self._key(hex_file)] = f"{type(error).__name__}: {error}"
            print(f"[project] palette read error {hex_file.name}: {error}")
            return None
        bank.asset = self._rel(hex_file)
        if metadata != bank.to_metadata_dict():
            self._write_sidecar(bank)              # un sidecar d'avant le champ `asset` le reçoit une fois
        else:
            self.index.record(name, sidecar)
        for index, existing in enumerate(self.items):
            if existing.name == name:
                self.items[index] = bank
                return bank
        self.items.append(bank)
        return bank

    def _migrate_colors_in_sidecar(self, name: str, sidecar: Path, metadata: dict, hex_file: Path) -> Path | None:
        """Les projets antérieurs n'ont que leur JSON, couleurs comprises : on en tire le `.hex`, une fois.
        Un sidecar moderne (sans couleurs) dont le `.hex` manque reste tel quel."""
        if "colors" not in metadata:
            return None
        try:
            legacy = PaletteBank.from_dict(metadata)
            legacy.name = name
            legacy.asset = self._rel(hex_file)
            atomic_write(hex_file, legacy.to_hex())
            return hex_file
        except Exception as error:
            print(f"[project] palette migration error {sidecar.name}: {error}")
            return None

    def load(self):
        self.items = []
        self.unreadable = {}
        self.index.scan()
        if not self.root.exists():
            return
        for name in self.index.names():
            sidecar = self.index.path_for(name)
            if sidecar is not None:
                self._read(name, sidecar)

    def load_one(self, name: str) -> PaletteBank | None:
        sidecar = self.index.path_for(name)
        return self._read(name, sidecar) if sidecar is not None else None

    # ── Écriture ──────────────────────────────────────────────────

    def save(self, item: PaletteBank, folder: Path | None = None):
        if not item.asset:
            item.asset = self._rel(self._path(item.name, folder).with_suffix(".hex"))     # à côté de son .palette
        hex_file = self.hex_path(item)
        hex_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(hex_file, item.to_hex())
        self._write_sidecar(item, folder)

    def _files_of(self, item: PaletteBank) -> list[Path]:
        return [self.path_of(item)]               # le `.hex` est la source, il reste : on ne supprime que l'asset

    def delete(self, item: PaletteBank):
        for path in self._files_of(item):
            if path.exists():
                path.unlink()
        self.index.forget(item.name)
        self.remove(item)
        self._pending_delete = [x for x in self._pending_delete if x is not item]

    def commit_deletes(self):
        for item in self.pending_deletes():   # cf. ResourceStore.pending_deletes
            for path in self._files_of(item):
                if path.exists():
                    path.unlink()
            self.index.forget(item.name)
        self._pending_delete.clear()
