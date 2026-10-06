"""Une écriture interrompue ne doit jamais abîmer la dernière sauvegarde valide.

`atomic_write` écrit un fichier temporaire puis le renomme sur la cible. Un crash
(ou une coupure) peut donc tomber à trois endroits : pendant l'écriture du
temporaire, juste avant le rename, ou entre deux fichiers d'une sauvegarde
complète. On le simule en faisant échouer ces appels : c'est le même état disque
qu'un processus tué à cet instant.

Invariants testés :
  - la cible garde son ancien contenu intact, et le projet se rouvre ;
  - un `.tmp` orphelin (le processus est mort avant de le nettoyer) ne gêne pas
    la réouverture et ne se confond pas avec un asset ;
  - une sauvegarde de projet coupée au milieu laisse chaque fichier soit à
    l'ancienne version, soit à la nouvelle, jamais tronqué.

Limite : l'atomicité du rename lui-même, sur coupure de courant, dépend du
système de fichiers (NTFS, ext4) et n'est pas vérifiable d'ici.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.project import Project
from core.resources import resource_store
from core.resources.resource_store import atomic_write


_TEXT = (".json", ".project")


class SimulatedCrash(Exception):
    """Le processus meurt ici."""


def test_crash_pendant_l_ecriture_du_temporaire_garde_l_ancien(tmp_path, monkeypatch):
    target = tmp_path / "scene.json"
    atomic_write(target, '{"v": 1}')

    def half_write(self, text, encoding="utf-8", **kwargs):
        Path.write_bytes(self, text.encode(encoding)[:3])       # écriture tronquée
        raise SimulatedCrash

    monkeypatch.setattr(Path, "write_text", half_write)
    with pytest.raises(SimulatedCrash):
        atomic_write(target, '{"v": 2, "long": "contenu"}')
    monkeypatch.undo()

    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 1}


def test_crash_avant_le_rename_garde_l_ancien(tmp_path, monkeypatch):
    target = tmp_path / "scene.json"
    atomic_write(target, '{"v": 1}')

    def no_replace(self, destination):
        raise SimulatedCrash

    monkeypatch.setattr(Path, "replace", no_replace)
    with pytest.raises(SimulatedCrash):
        atomic_write(target, '{"v": 2}')
    monkeypatch.undo()

    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 1}


def test_tmp_orphelin_ne_gene_pas_la_reouverture(tmp_path):
    root = tmp_path / "Jeu"
    project = Project.create(root, "Jeu")
    project.save()

    orphans = [p.with_suffix(p.suffix + ".tmp")
               for p in sorted(root.rglob("*.json"))[:5]]
    for orphan in orphans:
        orphan.write_text('{ "name": "demi', encoding="utf-8")      # tronqué

    reopened = Project.open(root)
    reopened.load_all_resources()
    reopened.save()                                                 # et se resauvegarde

    for orphan in orphans:
        assert orphan.read_text(encoding="utf-8") == '{ "name": "demi' or not orphan.exists()


def test_sauvegarde_de_projet_coupee_au_milieu(tmp_path, monkeypatch):
    """Coupe la sauvegarde complète au Nième fichier, pour chaque N : aucun
    fichier tronqué, et le projet se rouvre."""
    root = tmp_path / "Jeu"
    project = Project.create(root, "Jeu")
    project.save()
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and p.suffix in _TEXT}

    project.settings.author = "autre"                               # deux fichiers à réécrire :
    project.scenes[0].notes = "modifiée"                            # le projet et la scène
    project.save()
    after = {p: p.read_bytes() for p in before}
    changed = [p for p in after if before.get(p) != after[p]]
    assert changed, "le scénario ne change aucun fichier : la coupure ne testerait rien"

    # Retour à l'état « avant », puis sauvegarde interrompue après `cut` renames.
    for cut in range(1, len(changed) + 1):
        for path, data in before.items():
            path.write_bytes(data)
        done = {"n": 0}
        real_replace = Path.replace

        def counting_replace(self, destination, _real=real_replace, _cut=cut, _done=done):
            if _done["n"] >= _cut:
                raise SimulatedCrash
            _done["n"] += 1
            return _real(self, destination)

        monkeypatch.setattr(Path, "replace", counting_replace)
        try:
            project.save()
        except SimulatedCrash:
            pass
        monkeypatch.undo()

        for path in before:
            text = path.read_bytes()
            assert text in (before.get(path), after.get(path)), \
                f"{path.name} n'est ni l'ancienne ni la nouvelle version (coupure après {cut})"
            if path.suffix != ".hex":
                json.loads(text)                                     # jamais tronqué
        reopened = Project.open(root)
        reopened.load_all_resources()
