"""L'écran Texts a son « + » : il crée un texte dans le dossier choisi, comme le clic droit « Create »."""
from __future__ import annotations

from PyQt6.QtWidgets import QToolButton

from core.project import Project
from ui.text_editor.text_library import TextLibrary


def _library(tmp_path):
    project = Project(tmp_path / "jeu")
    project.new_text(content="Bonjour", path=["maman", "salut"])
    library = TextLibrary()
    library.resize(300, 400)
    library.load_project(project)
    library.show()
    return library


def test_le_plus_demande_un_texte_dans_le_dossier_choisi(qapp, tmp_path):
    from ui.text_editor import text_library as module
    library = _library(tmp_path)
    asked = []
    library.create_requested.connect(asked.append)
    stack = [library._tree.topLevelItem(i) for i in range(library._tree.topLevelItemCount())]
    folder = None
    while stack and folder is None:
        item = stack.pop()
        if tuple(item.data(0, module._ROLE_PATH) or ()) == ("maman",):
            folder = item
        stack.extend(item.child(n) for n in range(item.childCount()))
    assert folder is not None
    library._tree.setCurrentItem(folder)

    next(b for b in library.findChildren(QToolButton) if b.width() == 24).click()

    assert len(asked) == 1
    assert tuple(asked[0]) == tuple(folder.data(0, module._ROLE_PATH))
    assert tuple(asked[0]) == ("maman",)
