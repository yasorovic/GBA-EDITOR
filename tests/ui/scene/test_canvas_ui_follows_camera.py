"""Une interface ancrée à l'ÉCRAN vit dans le repère de la caméra de démarrage :
elle y est posée, la suit quand on la déplace, et le cadre de la caméra
s'affiche tant qu'elle est sélectionnée (sinon on ne voit pas où elle tombera)."""
from __future__ import annotations


def _scene_with_camera(tmp_path, anchor):
    from core.project import Project
    from core.models.scene import Scene
    from core.models.camera import Camera
    from core.models.ui_region import UILayout, UIText
    from ui.scene_manager.canvas.canvas_scene import GBAScene

    p = Project(tmp_path)
    lay = UILayout(name="ui", anchor=anchor)
    lay.elements.append(UIText(name="hud", x=8, y=16, w=32, h=16))
    p.ui_layouts.append(lay)
    scene = Scene(name="S", ui_layouts=["ui"])
    p.scenes.append(scene)
    p.set_active_scene(0)
    cam = Camera(name="cam")
    gs = GBAScene()
    gs.resize_canvas(480, 320)
    gs.setup_camera(64, 32, camera=cam, project=p)
    gs.set_ui_regions(p.scene_ui_layouts(scene), p, scene)
    return gs


def test_zone_ecran_posee_dans_le_repere_de_la_camera(qapp, tmp_path):
    gs = _scene_with_camera(tmp_path, "screen")
    item = gs._ui_region_items[0]
    assert (item.pos().x(), item.pos().y()) == (64 + 8, 32 + 16)


def test_zone_ecran_suit_la_camera_et_montre_le_cadre(qapp, tmp_path):
    gs = _scene_with_camera(tmp_path, "screen")
    item = gs._ui_region_items[0]
    gs._camera.setPos(100, 50)
    assert (item.pos().x(), item.pos().y()) == (108, 66)
    assert not gs._camera.view_forced
    item.setSelected(True)
    assert gs._camera.view_forced
    item.setSelected(False)
    assert not gs._camera.view_forced


def test_zone_monde_ignore_la_camera(qapp, tmp_path):
    gs = _scene_with_camera(tmp_path, "world")
    item = gs._ui_region_items[0]
    gs._camera.setPos(100, 50)
    assert (item.pos().x(), item.pos().y()) == (8, 16)
    item.setSelected(True)
    assert not gs._camera.view_forced
