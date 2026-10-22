"""Le « + » d'import prend plusieurs fichiers d'un coup ; sélectionner une ressource montre sa section."""
from __future__ import annotations

from PIL import Image


def _project(tmp_path):
    from core.project import Project
    project = Project(tmp_path / "jeu")
    project.root.mkdir(parents=True, exist_ok=True)
    return project


def test_le_plus_importe_tous_les_fichiers_choisis(qapp, tmp_path, monkeypatch):
    from ui.common import source_import
    project = _project(tmp_path)
    sources = []
    for name in ("hero", "cat"):
        path = tmp_path / f"{name}.png"
        Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(path)
        sources.append(str(path))
    monkeypatch.setattr(source_import.QFileDialog, "getOpenFileNames", lambda *a, **k: (sources, ""))

    first = source_import.import_from_file(project, "sprites", "Import")

    assert first is not None
    assert {s.name for s in project.sprites} == {"hero", "cat"}


def test_selectionner_une_ressource_deplie_sa_section(qapp, tmp_path):
    from core.models.scene import Scene
    from ui.common.asset_kinds import SCENES
    from ui.common.asset_library import AssetLibrary
    project = _project(tmp_path)
    scene = Scene(name="Title")
    scene.id = "0123456789ab"
    project.scenes.append(scene)
    library = AssetLibrary("Library", [SCENES])
    library.load_project(project)
    library._sections["Scenes"].set_expanded(False)

    assert library.select("Scenes", scene)

    assert library._sections["Scenes"]._expanded
