"""
core/disk_commands.py — les gestes de l'onglet Disk qui touchent au disque, rendus annulables.

Créer, importer, déplacer, renommer un dossier ou un fichier : chacun est une `Command` de l'historique (Ctrl+Z / Ctrl+Y).
Les écritures elles-mêmes restent dans `core.disk_folders`, `core.disk_move` (qui déplace et renomme) et `core.asset_creation` : une commande
ne fait que les appeler dans un sens, puis dans l'autre.

`around` : une fonction sans argument qui rend un gestionnaire de contexte entourant l'écriture (la fenêtre y
suspend le surveillant, pour qu'un geste de l'éditeur ne lui revienne pas comme une modification externe).
"""
from __future__ import annotations

import shutil
from contextlib import nullcontext
from pathlib import Path
from typing import Callable, Optional

from core import disk_folders, disk_move
from core.history import Command


class SuspendedCmd(Command):
    """Une commande de l'historique exécutée, et annulée, avec `around` autour (le surveillant suspendu) : un geste de
    l'éditeur ne doit pas lui revenir comme une modification venue de l'extérieur."""

    def __init__(self, cmd: Command, around: Callable):
        self._cmd = cmd
        self._around = around
        self.label = cmd.label

    def execute(self):
        with self._around():
            self._cmd.execute()

    def undo(self):
        with self._around():
            self._cmd.undo()


class CreateFileCmd(Command):
    """Un fichier neuf (un script, un behavior) : le créer, puis le retirer. Le contenu est gardé pour refaire."""

    def __init__(self, path: Path, content: bytes, around: Callable = nullcontext):
        self._path = Path(path)
        self._content = content
        self._around = around
        self.label = f"Créer {self._path.name}"

    def execute(self):
        with self._around():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_bytes(self._content)

    def undo(self):
        with self._around():
            self._path.unlink(missing_ok=True)


class ImportFilesCmd(Command):
    """Copier des fichiers de l'extérieur dans `assets/`. Annuler retire les copies et les dossiers que l'import a
    créés, et remet en place le contenu des fichiers qu'une copie a ÉCRASÉS ; l'original, hors du projet, n'est jamais
    touché."""

    def __init__(self, copies: list[tuple[Path, Path]], around: Callable = nullcontext):
        self._copies = [(Path(src), Path(dst)) for src, dst in copies]      # (source extérieure, copie dans le projet)
        self._around = around
        self._made: list[Path] = []                                         # les dossiers créés, du plus haut au plus bas
        self._overwritten: dict[Path, bytes] = {}                           # le contenu d'avant, des copies qui en écrasent un
        self.label = f"Importer {len(self._copies)} fichier(s)"

    def execute(self):
        with self._around():
            self._made = []
            self._overwritten = {}
            for source, copy in self._copies:
                if copy.is_file():
                    self._overwritten[copy] = copy.read_bytes()
                missing = [d for d in reversed(copy.parents) if not d.exists()]
                copy.parent.mkdir(parents=True, exist_ok=True)
                self._made += [d for d in missing if d not in self._made]
                shutil.copy2(source, copy)

    def undo(self):
        with self._around():
            for _source, copy in self._copies:
                if copy in self._overwritten:
                    copy.write_bytes(self._overwritten[copy])
                else:
                    copy.unlink(missing_ok=True)
            for folder in reversed(self._made):
                try:
                    folder.rmdir()
                except OSError:                 # l'auteur y a rangé autre chose depuis : on n'y touche pas
                    pass


class MoveFilesCmd(Command):
    """Déplacer des fichiers et dossiers vers un dossier de `assets/` (`core.disk_move`). Annuler remet chaque élément
    déplacé dans son dossier d'origine ; les références des assets (sources, scripts attachés) suivent dans les deux
    sens, comme au déplacement."""

    def __init__(self, project, paths, target, around: Callable = nullcontext):
        self._project = project
        self._paths = [Path(p) for p in paths]
        self._target = Path(target)
        self._around = around
        self.result: Optional[disk_move.MoveResult] = None
        self.label = f"Déplacer {len(self._paths)} élément(s)"

    def execute(self):
        with self._around():
            self.result = disk_move.move_to_folder(self._project, self._paths, self._target)

    def undo(self):
        if self.result is None:
            return
        with self._around():
            for before, after in reversed(self.result.moved):
                disk_move.move_to_folder(self._project, [after], before.parent)


class DeleteFilesCmd(Command):
    """Supprimer des fichiers et des dossiers de `assets/`. Les fichiers vont dans `.temp/` (la corbeille du projet,
    `DeletedFilesBin`) sous leur chemin relatif ; annuler les y reprend et refait les dossiers. `.temp/` est vidé à la
    fermeture : la suppression devient alors définitive.

    `folders` : les dossiers à retirer une fois vidés, du plus profond au moins profond."""

    def __init__(self, project, files, folders):
        self._bin = project.deleted_files
        self._files = [Path(p) for p in files]
        self._folders = sorted((Path(p) for p in folders), key=lambda p: len(p.parts), reverse=True)
        self.label = f"Supprimer {len(self._files) + len(self._folders)} élément(s)"

    def execute(self):
        self._bin.stash(self._files)
        for folder in self._folders:
            try:
                folder.rmdir()                            # un dossier resté plein (fichier verrouillé) n'est pas retiré
            except OSError:
                pass

    def undo(self):
        for folder in reversed(self._folders):
            folder.mkdir(parents=True, exist_ok=True)
        self._bin.restore(self._files)


class CreateFolderCmd(Command):
    """Un dossier neuf, nommé d'office (`disk_folders.create_folder`). Annuler le retire s'il est resté vide."""

    def __init__(self, parent: Path, base: str, root: Path, around: Callable = nullcontext):
        self._parent, self._base, self._root = Path(parent), base, Path(root)
        self._around = around
        self.created: Optional[Path] = None
        self.label = "Nouveau dossier"

    def execute(self):
        with self._around():
            self.created = disk_folders.create_folder(self._parent, self._base, self._root)

    def undo(self):
        if self.created is not None and self.created.is_dir():
            with self._around():
                try:
                    self.created.rmdir()                  # un dossier où l'on a rangé quelque chose depuis n'est pas retiré
                except OSError:
                    pass


class RenamePathCmd(Command):
    """Renommer un fichier ou un dossier de `assets/` (`disk_move.rename_in_place`) ; annuler lui rend son nom. Les
    références des assets suivent dans les deux sens, comme à un déplacement."""

    def __init__(self, project, path: Path, new_name: str, around: Callable = nullcontext):
        self._project, self._path, self._new_name = project, Path(path), new_name
        self._around = around
        self.renamed: Optional[Path] = None
        self.label = f"Renommer {self._path.name}"

    def execute(self):
        with self._around():
            self.renamed = disk_move.rename_in_place(self._project, self._path, self._new_name)

    def undo(self):
        if self.renamed is not None:
            with self._around():
                disk_move.rename_in_place(self._project, self.renamed, self._path.name)
