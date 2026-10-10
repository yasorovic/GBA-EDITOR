"""ui/sprite_editor/import_png_dialog.py — import sprite NON-DESTRUCTIF.

Aligné sur le pipeline background : Watcher/UI → **Validator** (detect_sprite_import_mode)
→ **Encodage** (encode_sprite, métadonnées) → asset éditable. Le PNG source n'est
JAMAIS modifié ; la PAL_BANK (sous-palettes) + le pont de compat `own_palette`
vivent dans le .sprite du sprite. Plus de dialogue de compression modal — l'algo se
règle dans l'éditeur (comme le mode d'un background dans son inspecteur).
"""
from __future__ import annotations
from ui.common.labels import label
import shutil
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QFileDialog, QMessageBox

from core.resources import asset_reconciliation
from core.command_dispatcher import get_dispatcher


def _encode_and_store(project, sprite, source) -> Optional[str]:
    """Encode `source` sur `sprite` (métadonnées, PNG intact) + persiste via le
    dispatcher. Renvoie un warning d'import éventuel (palette réduite)."""
    warning = asset_reconciliation.encode_sprite_asset(sprite, source)
    get_dispatcher().save_sprite(sprite)
    return warning


def import_new_sprite(project, parent=None):
    """Choisit un fichier, le COPIE tel quel dans assets/sprites/ puis crée le sprite qui le pointe et l'encode
    (Validator → Encodage). Une seule entrée d'historique : Ctrl+Z retire la copie ET le sprite. Retourne le
    sprite, ou None."""
    from core import asset_creation
    from core.disk_commands import ImportFilesCmd
    from core.history import CreateAssetCmd, MacroCmd, get_history
    from core.models.unique_name import unique_name
    path, _ = QFileDialog.getOpenFileName(
        parent, label('imgpng.import_an_image'), "", label('imgpng.images_png'))
    if not path:
        return None
    source = Path(path)
    folder = project.sprites_dir
    taken = {entry.stem for entry in folder.iterdir()} if folder.is_dir() else set()
    copy = folder / f"{unique_name(source.stem, taken)}{source.suffix}"
    copies = ImportFilesCmd([(source, copy)])
    copies.execute()                                  # la copie doit exister pour être lue et encodée
    creation = asset_creation.build_from_source(project, "sprites", copy)
    if creation.error is not None:
        copies.undo()
        if parent is not None:
            QMessageBox.information(parent, label('imgpng.import_sprite'), creation.error)
        return None
    get_history().push(MacroCmd([_Executed(copies), CreateAssetCmd(creation.store, creation.item, creation.folder)],
                                f"Importer {creation.item.name}"))
    if creation.warning and parent is not None:
        QMessageBox.information(parent, label('imgpng.import_sprite'), creation.warning)
    return creation.item


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


def replace_sprite_image(project, sprite, parent=None) -> bool:
    """Choisit un nouveau fichier, le COPIE comme source du sprite courant, et le
    ré-encode (PNG jamais réécrit). True si appliqué."""
    if not sprite:
        return False
    path, _ = QFileDialog.getOpenFileName(
        parent, label('imgpng.choose_an_image'), "", label('imgpng.images_png'))
    if not path:
        return False
    dst_dir = project.assets_dir / "sprites"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{sprite.name}.png"
    shutil.copy2(path, dst)            # copie du source, jamais réécrit
    sprite.asset = project.asset_rel(dst)
    warning = _encode_and_store(project, sprite, dst)
    if warning and parent is not None:
        QMessageBox.information(parent, label('imgpng.replace_sprite'), warning)
    return True
