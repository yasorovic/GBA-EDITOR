"""CameraInspector — après conformation à la mise en page normale (champs
vectoriels `W.pair` + notices), `load()` doit toujours refléter le modèle.

Garde le câblage des paires : une paire mal reliée (widget1/widget2 inversés,
attribut oublié) casserait ici sans rien casser au build.
"""
from __future__ import annotations

from core.models.camera import Camera, CAM_FOLLOW
from core.models.scene import Scene
from ui.scene_manager.inspectors.camera_inspector import CameraInspector


def test_load_reflete_le_modele(qapp):
    insp = CameraInspector()
    cam = Camera(name="Cam", mode=CAM_FOLLOW, x=32, y=16, frame_w=200, frame_h=120,
                 margin_x=50, margin_y=25, bounds_w=1024, bounds_h=512,
                 bounds_x=8, bounds_y=8)
    scene = Scene(name="S1")
    scene.cameras.append(cam)

    insp.load(scene, cam, project=None)

    assert (insp._pos_x.raw(), insp._pos_y.raw()) == (32, 16)
    assert (insp._frame_w.raw(), insp._frame_h.raw()) == (200, 120)
    assert (insp._margin_x.raw(), insp._margin_y.raw()) == (50, 25)
    assert (insp._bounds_w.raw(), insp._bounds_h.raw()) == (1024, 512)
    assert (insp._bounds_x.raw(), insp._bounds_y.raw()) == (8, 8)
