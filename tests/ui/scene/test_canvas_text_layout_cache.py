"""Le canvas ne refait la mise en page d'un texte que si ses ingrédients changent."""
from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtGui import QImage, QPainter

from core.project import Project

DEMO = Path(__file__).resolve().parent.parent.parent.parent / "Project Demo" / "Platformer"


def _textbox_item(tmp_path):
    if not DEMO.exists():
        pytest.skip("démo absente")
    from ui.scene_manager.scene_canvas import SceneEditor
    from ui.scene_manager.canvas.canvas_region_item import UIRegionItem
    project = Project.open(DEMO)
    project.set_active_scene([s.name for s in project.scenes].index("Scene_01"))
    editor = SceneEditor()
    editor.load_project(project)
    # Une chaîne (`Text` ponctuel) ne se coupe pas : sa largeur n'entre pas dans la clé, seules les boîtes la changent.
    items = [i for i in editor._gba_scene.items()
             if isinstance(i, UIRegionItem) and getattr(i._region, "wraps", True)]
    if not items:
        pytest.skip("aucune boîte de texte dans la démo")
    return editor, items[0]


def test_repaint_reuses_layout_until_the_box_changes(qapp, tmp_path, monkeypatch):
    editor, item = _textbox_item(tmp_path)
    calls = []
    real = item._compute_text_layout
    monkeypatch.setattr(item, "_compute_text_layout",
                        lambda *a: calls.append(1) or real(*a))
    image = QImage(256, 192, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        item.paint(painter, None)
        item.paint(painter, None)
        first = len(calls)
        assert first == 1                       # un seul calcul pour deux repaints
        item.setRect(0, 0, item.rect().width() + 8, item.rect().height())
        item.paint(painter, None)
        assert len(calls) == 2                  # la largeur change la clé
    finally:
        painter.end()
