"""deleted_files.py — le dossier `.temp/` où va ce que l'auteur supprime.

Supprimer une ressource depuis l'éditeur ne laisse plus ses fichiers en place
jusqu'à la fermeture : ils sont DÉPLACÉS dans `<projet>/.temp/`, sous le même
chemin relatif qu'ils avaient. Le disque dit alors la même chose que l'éditeur,
et rien ne peut ressusciter un fond supprimé — ni un `get` qui relit le JSON,
ni la réconciliation du lancement suivant, ni une sauvegarde de fin de session.

Ctrl+Z ramène les fichiers à leur place exacte. La fermeture de l'éditeur vide
`.temp/` pour de bon, et l'ouverture d'un projet le vide aussi (un plantage a pu
le laisser plein).

Un déplacement refusé (fichier verrouillé par un indexeur, un antivirus) est
sans conséquence : le fichier reste où il est et la suppression redevient celle
d'avant — différée, effacée à la fermeture par `Project.commit_all_removals`.
"""
from __future__ import annotations

import shutil
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Iterable, Optional

TEMP_FOLDER_NAME = ".temp"


class DeletedFilesBin:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.folder = project_root / TEMP_FOLDER_NAME
        # chemin d'origine -> copies rangées, la plus récente en dernier : un
        # même fichier supprimé, restauré puis supprimé de nouveau s'empile.
        self._stashed: dict[Path, list[Path]] = {}
        self._watcher = None

    def attach_watcher(self, watcher) -> None:
        """Le surveillant de fichiers, pour qu'il ne prenne pas ces déplacements
        pour des dépôts ou des suppressions venus de l'extérieur."""
        self._watcher = watcher

    @contextmanager
    def _quiet(self, paths: list[Path]):
        if self._watcher is None:
            yield
            return
        with self._watcher.suspended():
            for path in paths:
                self._watcher.claim(path)
            yield

    def stash(self, paths: Iterable[Path]) -> None:
        """Range ces fichiers dans `.temp/` (ceux qui n'existent pas sont ignorés)."""
        paths = [Path(p) for p in paths if Path(p).is_file()]
        with self._quiet(paths):
            for original in paths:
                destination = self._destination(original)
                if destination is None:
                    continue
                try:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(original), str(destination))
                except OSError:
                    continue            # verrouillé : la suppression reste différée
                self._stashed.setdefault(original, []).append(destination)

    def restore(self, paths: Iterable[Path]) -> None:
        """Remet à leur place les fichiers rangés (jamais par-dessus un fichier
        qui aurait repris le nom entre-temps)."""
        paths = [Path(p) for p in paths]
        with self._quiet(paths):
            for original in paths:
                copies = self._stashed.get(original)
                if not copies:
                    continue
                source = copies[-1]
                if original.exists() or not source.is_file():
                    continue
                try:
                    original.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(original))
                except OSError:
                    continue
                copies.pop()
                if not copies:
                    del self._stashed[original]

    def purge(self) -> None:
        """Détruit `.temp/` : la suppression devient définitive."""
        self._stashed.clear()
        shutil.rmtree(self.folder, ignore_errors=True)

    def _destination(self, original: Path) -> Optional[Path]:
        try:
            relative = original.resolve().relative_to(self.project_root)
        except ValueError:
            return None                 # hors du projet : on n'y touche pas
        destination = self.folder / relative
        number = 2
        while destination.exists():
            destination = self.folder / relative.with_name(
                f"{relative.stem}~{number}{relative.suffix}")
            number += 1
        return destination
