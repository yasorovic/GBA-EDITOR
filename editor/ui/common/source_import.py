"""ui/common/source_import.py — « importer » : choisir un fichier, le copier dans le dossier que l'onglet Disk affiche, créer l'asset qui le pointe.

C'est *Create from source* précédé d'un sélecteur de fichier et d'une copie. Une seule entrée d'historique : Ctrl+Z retire
la copie ET l'asset. Les « + » des sprites et des sons y passent.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog

from ui.common.import_collision import ask_overwrite
from ui.common.import_folder import import_folder
from ui.common.popup import MessageBox as QMessageBox


class _Executed:
    """Une commande déjà exécutée : l'historique ne la rejoue pas à l'empilement, mais l'annule et la refait."""

    def __init__(self, cmd):
        self._cmd = cmd
        self._first = True
        self.label = cmd.label

    def execute(self):
        if self._first:
            self._first = False
            return
        self._cmd.execute()

    def undo(self):
        self._cmd.undo()


def import_from_file(project, family: str, title: str, file_filter: str | None = None, parent=None,
                     error_title: str | None = None):
    """Choisit UN OU PLUSIEURS fichiers, les COPIE tels quels dans le dossier affiché, puis crée un asset de type `family`
    par fichier, en une seule entrée d'historique. Rend le premier asset créé, ou None (annulé, ou tout refusé : les
    copies sont alors retirées et l'erreur dite). Un fichier refusé parmi d'autres est dit, les autres sont importés."""
    from core import asset_creation
    from core.disk_commands import ImportFilesCmd
    from core.history import MacroCmd, get_history
    from core import source_collisions
    if file_filter is None:
        extensions = sorted(e for e, families in asset_creation.SOURCE_FAMILIES.items() if family in families)
        file_filter = f"{asset_creation.FAMILY_WORDS[family]} ({' '.join('*' + e for e in extensions)})"
    paths, _ = QFileDialog.getOpenFileNames(parent, title, "", file_filter)
    if not paths:
        return None
    sources = [Path(path) for path in paths]
    folder = import_folder(project)
    clashes = [source for source in sources if source_collisions.collides(source, folder)]
    overwrite = False
    if clashes:
        citing = [c for source in clashes for c in source_collisions.citing(project, folder / source.name)]
        overwrite = ask_overwrite(parent, [source.name for source in clashes], citing)
        if overwrite is None:
            return None
    pairs, taken = [], set()
    for source in sources:
        copy = source_collisions.destination(source, folder, overwrite, taken)
        taken.add(copy.name)                          # deux fichiers de même nom dans le lot ne s'écrasent pas
        pairs.append((source, copy))
    copies = ImportFilesCmd(pairs)
    copies.execute()                                  # les copies doivent exister pour être lues et encodées
    gesture = asset_creation.create_from_source(project, family, [copy for _source, copy in pairs])
    if gesture.command is None:
        copies.undo()
        QMessageBox.information(parent, error_title or title, " ".join(gesture.errors))
        return None
    name = gesture.names[0] if len(gesture.names) == 1 else f"{len(gesture.names)} fichiers"
    get_history().push(MacroCmd([_Executed(copies), gesture.command], f"Importer {name}"))
    notices = gesture.errors + gesture.warnings
    if notices:
        QMessageBox.information(parent, error_title or title, " ".join(notices))
    return gesture.items[0]


def replace_source(project, item, title: str, file_filter: str, parent=None) -> Path | None:
    """« Remplacer l'image » : choisit un fichier et l'écrit SUR la source que `item` cite déjà (plus de `_2`). Annulable :
    l'historique garde l'ancien contenu. Si d'autres assets citent cette source, l'auteur choisit : l'écraser pour tous, ou
    donner à `item` sa propre copie. Rend le fichier désormais cité par `item`, ou None (annulé)."""
    from core import source_collisions
    from core.disk_commands import ImportFilesCmd
    from core.history import get_history
    path, _ = QFileDialog.getOpenFileName(parent, title, "", file_filter)
    if not path:
        return None
    chosen, current = Path(path), project.asset_abs(item.asset)
    if current is not None and current.is_file() and chosen.resolve() == current.resolve():
        return current                                      # déjà la source : rien à copier, l'appelant ré-encode
    if current is not None and current.is_file():
        others = source_collisions.citing(project, current, exclude=item)
        overwrite = True if not others else ask_overwrite(parent, [current.name], others)
        if overwrite is None:
            return None
        target = current if overwrite else source_collisions.destination(chosen, current.parent, False)
    else:                                                   # source absente : un import ordinaire
        folder = import_folder(project)
        overwrite = False
        if source_collisions.collides(chosen, folder):
            overwrite = ask_overwrite(parent, [chosen.name], source_collisions.citing(project, folder / chosen.name))
            if overwrite is None:
                return None
        target = source_collisions.destination(chosen, folder, overwrite)
    get_history().push(ImportFilesCmd([(chosen, target)]))
    return target
