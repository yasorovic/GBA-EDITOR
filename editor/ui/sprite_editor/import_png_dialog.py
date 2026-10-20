"""ui/sprite_editor/import_png_dialog.py — import sprite NON-DESTRUCTIF.

Aligné sur le pipeline background : Watcher/UI → **Validator** (detect_sprite_import_mode)
→ **Encodage** (encode_sprite, métadonnées) → asset éditable. Le PNG source n'est
JAMAIS modifié ; la PAL_BANK (sous-palettes) + le pont de compat `own_palette`
vivent dans le .sprite du sprite. Plus de dialogue de compression modal — l'algo se
règle dans l'éditeur (comme le mode d'un background dans son inspecteur).
"""
from __future__ import annotations
from ui.common.labels import label
from typing import Optional

from ui.common.popup import MessageBox as QMessageBox

from core.resources import asset_reconciliation
from core.command_dispatcher import get_dispatcher


def _encode_and_store(project, sprite, source) -> Optional[str]:
    """Encode `source` sur `sprite` (métadonnées, PNG intact) + persiste via le
    dispatcher. Renvoie un warning d'import éventuel (palette réduite)."""
    warning = asset_reconciliation.encode_sprite_asset(sprite, source)
    get_dispatcher().save_sprite(sprite)
    return warning


def import_new_sprite(project, parent=None):
    """Choisit un fichier, le COPIE tel quel dans le dossier que l'onglet Disk affiche, puis crée le sprite qui le pointe et l'encode
    (Validator → Encodage). Une seule entrée d'historique : Ctrl+Z retire la copie ET le sprite. Retourne le
    sprite, ou None."""
    from ui.common.source_import import import_from_file
    return import_from_file(project, "sprites", label('imgpng.import_an_image'), label('imgpng.images_png'),
                            parent, error_title=label('imgpng.import_sprite'))


def replace_sprite_image(project, sprite, parent=None) -> bool:
    """Choisit un nouveau fichier, l'écrit sur la source du sprite courant (annulable, cf. `replace_source`) et le
    ré-encode. True si appliqué."""
    if not sprite:
        return False
    from ui.common.source_import import replace_source
    dst = replace_source(project, sprite, label('imgpng.choose_an_image'), label('imgpng.images_png'), parent)
    if dst is None:
        return False
    sprite.asset = project.asset_rel(dst)
    warning = _encode_and_store(project, sprite, dst)
    if warning and parent is not None:
        QMessageBox.information(parent, label('imgpng.replace_sprite'), warning)
    return True
