"""La note des inspecteurs Area, Camera et Script reste sous le nom pendant que les cartes défilent."""
import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QWidget

from core.models.camera import Camera
from core.models.scene import Area, Scene
from core.project import Project
from ui.common.labels import label
from ui.common.widgets import CollapsibleCard
from ui.scene_manager.inspectors.area_inspector import AreaInspector
from ui.scene_manager.inspectors.camera_inspector import CameraInspector
from ui.scene_manager.inspectors.script_inspector import ScriptInspector


def _area(tmp_path):
    insp = AreaInspector()
    insp.load(Area(name="Zone", notes="Une note"), Project(tmp_path / "game"), None)
    return insp


def _camera(tmp_path):
    scene = Scene(name="S1")
    cam = Camera(name="Cam", notes="Une note")
    scene.cameras.append(cam)
    scene.camera = "Cam"
    insp = CameraInspector()
    insp.load(scene, cam, project=None)
    return insp


def _script(tmp_path):
    path = tmp_path / "hero.lua"
    path.write_text("", encoding="utf-8")
    insp = ScriptInspector()
    insp.load(path)
    insp._notes_edit.set_text_silent("Une note")
    return insp


@pytest.mark.parametrize("build", [_area, _camera, _script])
def test_note_reste_fixe_pendant_le_defilement(qapp, tmp_path, build):
    insp = build(tmp_path)
    insp.resize(400, 400)
    insp.show()
    insp._scroll.widget().layout().addWidget(spacer := QWidget())
    spacer.setFixedHeight(1200)
    for _ in range(3):      # le layout de la zone défilante se recalcule sur plusieurs passes
        qapp.processEvents()
    note = insp._notes_edit
    assert note.toPlainText() == "Une note"
    assert not insp._scroll.isAncestorOf(note)
    assert all(c._title_lbl.text() != label("common.note") for c in insp.findChildren(CollapsibleCard))
    before = note.mapTo(insp, QPoint())
    bar = insp._scroll.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum())
    qapp.processEvents()
    assert note.isVisible() and note.mapTo(insp, QPoint()) == before
    insp.close()
