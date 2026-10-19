"""ui/common/external_editor.py — ouvrir un asset (image ou audio) dans un
logiciel externe.

L'éditeur n'est PAS un outil de dessin ni un outil audio (cf.
project_not_a_drawing_tool) : pour une retouche pixel par pixel ou une
retouche de forme d'onde, la bonne réponse est de déléguer au logiciel que
l'utilisateur connaît déjà, pas de réinventer Aseprite/Audacity dans Qt.

Trois niveaux, dans l'ordre :
  1. logiciel CONFIGURÉ par l'utilisateur pour ce TYPE de fichier (Réglages →
     External Tools, aussi réglable depuis le menu du bouton « Edit ») — image et
     audio ont chacun leur propre réglage, un même outil ne convenant pas aux deux ;
  2. sinon, l'application par défaut du système pour ce type de fichier ;
  3. sinon, rien — pas de message d'erreur, pas de repli inventé.

Le fichier réédité est repris par `project_watcher` (déjà en place pour tout
`assets/`) : cette fonction n'a qu'à ouvrir, jamais à ré-importer.
"""
from __future__ import annotations
from core.external_tools import ExternalTools
from core.tool_process import tool_environment
from ui.common.labels import label
import subprocess
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QWidget

KIND_IMAGE = "image"
KIND_AUDIO = "audio"


def get_configured_editor(kind: str = KIND_IMAGE) -> str:
    """Chemin de l'exécutable réglé pour `kind` dans Réglages → External Tools, ou ""
    (défaut système)."""
    return str(ExternalTools().path(kind) or "")


def set_configured_editor(path: str, kind: str = KIND_IMAGE) -> None:
    ExternalTools().set_path(kind, Path(path) if path else None)


def choose_editor(parent: QWidget | None, kind: str = KIND_IMAGE) -> None:
    """Fait choisir l'exécutable à l'utilisateur (dialogue natif du système,
    pas un formulaire maison) et l'enregistre."""
    title = label('extedit.choose_an_image_editor') if kind == KIND_IMAGE else label('extedit.choose_an_audio_editor')
    path, _ = QFileDialog.getOpenFileName(parent, title)
    if path:
        set_configured_editor(path, kind)


def use_system_default(kind: str = KIND_IMAGE) -> None:
    set_configured_editor("", kind)


def open_file(path: Path, parent: QWidget | None = None, kind: str = KIND_IMAGE) -> None:
    """Ouvre `path` dans le logiciel configuré pour `kind`, sinon l'appli par
    défaut du système, sinon rien."""
    open_with(get_configured_editor(kind), path)


def open_with(editor, path: Path) -> None:
    """Ouvre `path` dans l'exécutable `editor` (chemin, ou vide), sinon dans l'application par défaut du système.
    C'est le repli des réglages « External Tools » de l'écran Réglages (`core.external_tools`)."""
    if not path or not Path(path).exists():
        return
    if editor and Path(editor).is_dir():
        # Un dossier d'installation (« …\Aseprite ») : on cherche l'exécutable de même nom dedans.
        editor = Path(editor) / f"{Path(editor).name}.exe"
    if editor and Path(editor).exists():
        try:
            subprocess.Popen([str(editor), str(path)], env=tool_environment())
            return
        except OSError:
            pass  # exécutable configuré cassé : on retombe sur le défaut système
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_image(path: Path, parent: QWidget | None = None) -> None:
    open_file(path, parent, KIND_IMAGE)
