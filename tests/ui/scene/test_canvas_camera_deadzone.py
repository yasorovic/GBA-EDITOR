"""Le passepartout de la zone morte : en mode « suivre un acteur », le cadre de
la caméra montre en creux le rectangle que la cible parcourt sans que la caméra
bouge (`camera_follow()`), et les bandes autour sont voilées."""
from __future__ import annotations


def _scene(tmp_path, **cam_kwargs):
    from core.project import Project
    from core.models.scene import Scene
    from core.models.camera import Camera
    from ui.scene_manager.canvas.canvas_scene import GBAScene

    p = Project(tmp_path)
    scene = Scene(name="S")
    p.scenes.append(scene)
    p.set_active_scene(0)
    cam = Camera(name="cam", **cam_kwargs)
    gs = GBAScene()
    gs.resize_canvas(480, 320)
    gs.setup_camera(0, 0, camera=cam, project=p)
    return gs, cam, p


def test_mode_fixe_pas_de_passepartout(qapp, tmp_path):
    gs, _cam, _p = _scene(tmp_path)
    gs._camera.setSelected(True)
    assert not gs._camera._deadzone_edge.isVisible()
    assert not gs._camera._deadzone_veil.isVisible()


def test_suivi_creuse_la_zone_morte(qapp, tmp_path):
    gs, _cam, _p = _scene(tmp_path, mode="follow", margin_x=96, margin_y=64)
    gs._camera.setSelected(True)
    item = gs._camera
    assert item._deadzone_edge.isVisible()
    r = item._deadzone_edge.rect()
    # 240×160 moins les marges des deux côtés — l'écran, pas le frame : le
    # suivi se cale sur SCREEN_W/SCREEN_H.
    assert (r.x(), r.y(), r.width(), r.height()) == (96, 64, 48, 32)
    # Le voile couvre le cadre moins la zone morte.
    assert item._deadzone_veil.path().boundingRect().width() == 240
    assert not item._deadzone_veil.path().contains(r.center())


def test_marges_bornees_comme_le_runtime(qapp, tmp_path):
    gs, _cam, _p = _scene(tmp_path, mode="follow", margin_x=200, margin_y=120)
    r = gs._camera._deadzone_edge.rect()
    assert (r.width(), r.height()) == (0, 0)


def test_frame_reduit_decoupe_le_voile(qapp, tmp_path):
    gs, _cam, _p = _scene(tmp_path, mode="follow", margin_x=40, margin_y=20,
                          frame_w=160, frame_h=120)
    veil = gs._camera._deadzone_veil.path().boundingRect()
    assert (veil.width(), veil.height()) == (160, 120)


def test_passer_en_fixe_retire_le_passepartout(qapp, tmp_path):
    gs, cam, p = _scene(tmp_path, mode="follow", margin_x=40, margin_y=20)
    gs._camera.setSelected(True)
    assert gs._camera._deadzone_edge.isVisible()
    cam.mode = "fixed"
    gs._camera.refresh_follow_margins(p)
    assert not gs._camera._deadzone_edge.isVisible()
