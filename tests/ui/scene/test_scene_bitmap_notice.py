"""Un fond bitmap sur une scène tuilée : le canvas de scène le montre tel que l'encodage le porte, et le dit d'une notice
non bloquante (le bitmap n'existe qu'en vidéo 3/4/5)."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.project import Project

PONG = Path(__file__).resolve().parent.parent.parent.parent / "Project Test" / "PongAdvanced"


def _editor_with_bitmap_layer():
    if not PONG.exists():
        pytest.skip(f"démo absente : {PONG}")
    from ui.scene_manager.scene_canvas import SceneEditor
    project = Project.open(PONG)
    project.load_all_resources()
    bitmap = next((b for b in project.backgrounds if b.mode == "bitmap" and b.bitmap), None)
    if bitmap is None:
        pytest.skip("la démo n'a pas de fond bitmap compressé")
    scene = project.active_scene
    layer = scene.background_layers[0] if scene.background_layers else None
    if layer is None:
        pytest.skip("la scène de démo n'a pas de calque de fond")
    layer.background_name = bitmap.name
    editor = SceneEditor()
    editor.load_project(project)
    return editor, scene, bitmap


def test_a_bitmap_background_on_a_tiled_scene_raises_a_notice(qapp):
    editor, scene, bitmap = _editor_with_bitmap_layer()
    scene.render_mode = 0
    editor.refresh_bg()
    notice = editor._canvas_container._notice
    assert notice.isVisibleTo(editor._canvas_container) and bitmap.name in notice.text()

    scene.render_mode = 4                       # un mode bitmap : plus rien à signaler
    editor.refresh_bg()
    assert not notice.isVisibleTo(editor._canvas_container)


def test_the_scene_shows_the_encoded_bitmap_not_the_raw_png(qapp):
    from ui.scene_manager.canvas.canvas_raster import bitmap_pixmap
    _editor, _scene, bitmap = _editor_with_bitmap_layer()
    pix = bitmap_pixmap(bitmap)
    assert (pix.width(), pix.height()) == (bitmap.out_w, bitmap.out_h)
