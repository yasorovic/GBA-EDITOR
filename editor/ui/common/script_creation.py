"""ui/common/script_creation.py — le « + » de la famille Scripts.

Partagé par le Project viewer et le Script finder : le menu (script seul ou
behavior) et la création du fichier vivent ici, une seule fois. L'appelant ne
fournit que le projet et ce qu'il fait du script créé (rafraîchir, ouvrir)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt6.QtWidgets import QMenu, QWidget
from PyQt6.QtGui import QCursor

from core.command_dispatcher import unique_name
from ui.common.labels import label
from ui.common.theme import QSS


def show_add_script_menu(parent: QWidget, project, on_created: Callable[[Path], None]):
    """Menu sous le curseur : un script seul (à attacher ensuite), ou un behavior
    (un module, importé par `require`)."""
    if project is None:
        return
    menu = QMenu(parent)
    menu.setStyleSheet(QSS.menu)
    menu.addAction(label("assf.script"),
                   lambda: _create(project, "empty", project.scripts_dir, "Script", on_created))
    menu.addAction(label("assf.behavior_script"),
                   lambda: _create(project, "behavior", project.scripts_behaviors_dir,
                                   "Behavior", on_created))
    menu.exec(QCursor.pos())


def _create(project, kind: str, directory: Path, base: str, on_created):
    """Crée un script au nommage automatique (pas de pop-up). Pas d'actor précis
    à ce stade : contexte de composants vide, même template que
    component_editors/script.py."""
    from scripting.script_templates import ScriptTemplateContext, generate_script_template
    directory.mkdir(parents=True, exist_ok=True)
    name = unique_name(base, {f.stem for f in directory.glob("*.lua")})
    path = directory / f"{name}.lua"
    path.write_text(generate_script_template(ScriptTemplateContext(kind=kind, name=name)),
                    encoding="utf-8")
    on_created(path)
