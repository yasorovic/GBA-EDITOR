"""Le « + » de la famille Scripts est *Create blank* : un script ou un behavior naît dans le dossier que l'onglet Disk affiche."""
from ui.common import asset_kinds, import_folder
from core.history import CommandHistory
from core.project import Project


def test_add_behavior_is_born_in_the_shown_folder_and_undone(tmp_path, monkeypatch):
    p = Project.create(tmp_path / "Jeu", "Jeu")
    p.load_all_resources()
    history = CommandHistory()
    monkeypatch.setattr(asset_kinds, "get_history", lambda: history)
    monkeypatch.setattr(asset_kinds, "_menu_choice", lambda entries: entries[1][1]())      # « behavior »
    folder = p.assets_dir / "AI"
    folder.mkdir()
    monkeypatch.setattr(import_folder, "_shown_folder", lambda: str(folder))

    created = []
    asset_kinds.add_script(p, created.append)

    assert created == [folder / "Behavior.lua"] and created[0].is_file()
    history.undo()
    assert not created[0].exists()
