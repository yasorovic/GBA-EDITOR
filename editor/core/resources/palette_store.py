"""Persistance des palettes : le ``.hex`` est la donnée canonique.

Une palette est visible et modifiable sans l'éditeur dans
``assets/palettes/<nom>.hex``. Le JSON voisin est seulement un sidecar pour
les métadonnées de l'éditeur ; il ne duplique volontairement jamais les
couleurs.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.models import project_json
from core.models.palette import PaletteBank
from core.resources.resource_store import ResourceStore, atomic_write, safe_filename


class PaletteStore(ResourceStore[PaletteBank]):
    """Catalogue de :class:`PaletteBank` adossé à des fichiers ``.hex``."""

    def __init__(self, directory: Path):
        super().__init__(directory, PaletteBank)

    def source_path(self, name: str) -> Path:
        return self.dir / f"{safe_filename(name)}.hex"

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
            self.unreadable[path.name] = f"{type(error).__name__}: {error}"
            return {}
        return data if isinstance(data, dict) else {}

    def _write_sidecar(self, bank: PaletteBank) -> None:
        path = self._path(bank.name)
        self._keep_unreadable(path)
        atomic_write(path, project_json.dumps(bank.to_metadata_dict()))

    def save(self, item: PaletteBank):
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self.source_path(item.name), item.to_hex())
        self._write_sidecar(item)

    def load(self):
        self.items = []
        self.unreadable = {}
        if not self.dir.exists():
            return

        # Les projets antérieurs n'ont que leur JSON. Une seule migration les
        # transforme en source .hex, puis les ouvertures suivantes lisent le
        # format canonique comme tous les autres projets.
        for sidecar in sorted(self.dir.glob("*.json")):
            source = sidecar.with_suffix(".hex")
            if source.exists():
                continue
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                # Un sidecar moderne orphelin signifie que l'utilisateur a
                # supprimé le .hex. Ne jamais le recréer : la suppression du
                # fichier source est une intention, pas une panne à réparer.
                if not isinstance(data, dict) or "colors" not in data:
                    continue
                legacy = PaletteBank.from_dict(data)
                legacy.name = sidecar.stem
                self.save(legacy)
            except Exception as error:
                print(f"[project] palette migration error {sidecar.name}: {error}")

        for source in sorted(self.dir.glob("*.hex")):
            try:
                metadata = self._load_metadata(source.with_suffix(".json"))
                bank = PaletteBank.from_hex(
                    source.stem, source.read_text(encoding="utf-8"), metadata)
                self.items.append(bank)
                # Un .hex déposé à la main devient immédiatement un asset
                # complet pour l'éditeur, sans que ses couleurs soient copiées.
                self._write_sidecar(bank)
            except Exception as error:
                self.unreadable[source.name] = f"{type(error).__name__}: {error}"
                print(f"[project] palette read error {source.name}: {error}")

    def load_one(self, name: str) -> PaletteBank | None:
        source = self.source_path(name)
        if not source.exists():
            return None
        try:
            metadata = self._load_metadata(self._path(name))
            bank = PaletteBank.from_hex(
                name, source.read_text(encoding="utf-8"), metadata)
            self._write_sidecar(bank)
            for index, existing in enumerate(self.items):
                if existing.name == name:
                    self.items[index] = bank
                    return bank
            self.items.append(bank)
            return bank
        except Exception as error:
            print(f"[project] PaletteBank reload error {name}: {error}")
            return None

    def delete(self, item: PaletteBank):
        for path in (self.source_path(item.name), self._path(item.name)):
            if path.exists():
                path.unlink()
        self.remove(item)
        self._pending_delete = [x for x in self._pending_delete if x is not item]

    def commit_deletes(self):
        for item in self.pending_deletes():   # cf. ResourceStore.pending_deletes
            for path in (self.source_path(item.name), self._path(item.name)):
                if path.exists():
                    path.unlink()
        self._pending_delete.clear()

    def rename(self, item: PaletteBank, new_name: str):
        for path in (self.source_path(item.name), self._path(item.name)):
            if path.exists():
                path.unlink()
        item.name = new_name
        self.save(item)
