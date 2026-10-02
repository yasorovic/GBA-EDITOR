"""ui/common/external_editor.py — ouvrir un asset (image ou audio) dans un
logiciel externe.

L'éditeur n'est PAS un outil de dessin ni un outil audio (cf.
project_not_a_drawing_tool) : pour une retouche pixel par pixel ou une
retouche de forme d'onde, la bonne réponse est de déléguer au logiciel que
l'utilisateur connaît déjà, pas de réinventer Aseprite/Audacity dans Qt.

Trois niveaux, dans l'ordre :
  1. logiciel CONFIGURÉ par l'utilisateur pour ce TYPE de fichier (QSettings,
     réglable depuis le menu du bouton « Edit ») — image et audio ont chacun
     leur propre réglage, un même outil ne convenant pas aux deux ;
  2. sinon, l'application par défaut du système pour ce type de fichier ;
  3. sinon, rien — pas de message d'erreur, pas de repli inventé.

Le fichier réédité est repris par `project_watcher` (déjà en place pour tout
`assets/`) : cette fonction n'a qu'à ouvrir, jamais à ré-importer.
"""
from __future__ import annotations
from core.app_info import APP_NAME
from ui.common.labels import label
import subprocess
from pathlib import Path

from PyQt6.QtCore import QSettings, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QWidget

_ORG, _APP = APP_NAME, "Preferences"

KIND_IMAGE = "image"
KIND_AUDIO = "audio"


def _key(kind: str) -> str:
    return f"{kind}_editor_path"


def get_configured_editor(kind: str = KIND_IMAGE) -> str:
    """Chemin de l'exécutable choisi par l'utilisateur pour `kind`, ou ""
    (défaut système)."""
    return QSettings(_ORG, _APP).value(_key(kind), "", type=str)


def set_configured_editor(path: str, kind: str = KIND_IMAGE) -> None:
    QSettings(_ORG, _APP).setValue(_key(kind), path or "")


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
    if not path or not Path(path).exists():
        return
    configured = get_configured_editor(kind)
    if configured and Path(configured).exists():
        try:
            subprocess.Popen([configured, str(path)])
            return
        except OSError:
            pass  # exécutable configuré cassé : on retombe sur le défaut système
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_image(path: Path, parent: QWidget | None = None) -> None:
    open_file(path, parent, KIND_IMAGE)


def open_audio(path: Path, parent: QWidget | None = None) -> None:
    open_file(path, parent, KIND_AUDIO)
