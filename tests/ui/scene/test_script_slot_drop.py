"""Le slot du script attaché (acteur, Area, scène, caméra) : un seul modèle, `attached_script_slot`."""
from PyQt6.QtWidgets import QInputDialog

from core.history import CommandHistory
from core.lua_scripts import BEHAVIOR_MARKER
from core.project import Project
from ui.common import import_folder
from ui.common.disk_view import disk_mime
from ui.common.pickers import attached_script_slot
from ui.common.widgets import PickerPopup


def _slot(p, assigned, opened=None, template="actor"):
    return attached_script_slot(
        project=lambda: p, on_assigned=assigned.append, on_cleared=lambda: None,
        open_file=(opened.append if opened is not None else lambda _path: None), template=template,
        add_label="Add", new_title="New")


def test_only_one_attachable_script_dropped_from_disk_is_attached(tmp_path, qapp):
    p = Project.create(tmp_path / "Jeu", "Jeu")
    p.load_all_resources()
    door = p.user_library_dir / "Door.lua"
    door.write_text("function on_start() end\n", encoding="utf-8")
    chase = p.user_library_dir / "Chase.lua"
    chase.write_text(f"{BEHAVIOR_MARKER}\n", encoding="utf-8")
    assigned = []
    slot = _slot(p, assigned)

    assert slot._resolve_drop(disk_mime([chase])) is None          # un behavior ne s'attache à rien
    assert slot._resolve_drop(disk_mime([door, door])) is None     # plusieurs fichiers
    slot.pick(slot._resolve_drop(disk_mime([door])))
    assert assigned == [p.asset_rel(door)]


def test_a_new_scene_script_is_born_from_the_scene_template_and_undone(tmp_path, qapp, monkeypatch):
    p = Project.create(tmp_path / "Jeu", "Jeu")
    p.load_all_resources()
    history = CommandHistory()
    monkeypatch.setattr("core.history.get_history", lambda: history)
    monkeypatch.setattr(import_folder, "_shown_folder", lambda: str(p.user_library_dir))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *_a, **_k: ("Level", True)))
    assigned, opened = [], []
    slot = _slot(p, assigned, opened, template="scene")

    shown = []
    monkeypatch.setattr(PickerPopup, "show_below", lambda popup, _anchor: shown.append(popup))
    slot.open_picker()   # « + » : la liste ; « Nouveau script » y mène à la création
    shown[0].new_requested.emit()

    created = p.user_library_dir / "Level.lua"
    assert assigned == [p.asset_rel(created)] and opened == [str(created)]
    assert created.read_text(encoding="utf-8") == "function on_update()\nend\n"
    history.undo()
    assert not created.exists()
