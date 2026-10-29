"""Resynchro du canvas après undo/redo — le 4ᵉ invariant A1.

Les trois `*_undo` prouvent que le MODÈLE revient après un undo. Ferme la boucle
côté VUE : après un undo, la fenêtre appelle `_flush_after_undo_redo`, dont
l'action sur le canvas est `SceneEditor.reload_scene_items()` — les items sont
reposés depuis le modèle (« le modèle en mémoire = vérité après undo »), pour
TOUTES les familles.

Ces tests gardent aussi un CORRECTIF : `_flush` ne reposait que les SPRITES, si
bien qu'un item de caméra ou de zone déplacé puis annulé restait à sa position
draggée alors que le modèle était revenu. `reload_scene_items` (sprites + caméras
+ zones) referme ce trou ; le test zone ci-dessous tomberait si on l'ouvrait à
nouveau.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.project import Project
from core.history import get_history, MoveUIRegionCmd

REPO_DIR = Path(__file__).resolve().parent.parent.parent.parent
MYGAME = REPO_DIR / "Project Demo" / "MyGame"


@pytest.fixture
def history():
    h = get_history()
    h.clear()
    yield h
    h.clear()


def _editor(project_dir: Path):
    if not project_dir.exists():
        pytest.skip(f"démo absente : {project_dir}")
    from ui.scene_manager.scene_canvas import SceneEditor
    ed = SceneEditor()
    ed.load_project(Project.open(project_dir))
    return ed


def _first_region(ed):
    from ui.scene_manager.canvas.canvas_region_item import UIRegionItem
    p = ed._project
    for i, s in enumerate(p.scenes):
        if any(lay.elements for lay in p.scene_ui_layouts(s)):
            p.set_active_scene(i)
            ed.load_project(p)
            break
    items = [it for it in ed._gba_scene.items() if isinstance(it, UIRegionItem)]
    if not items:
        pytest.skip("aucune zone d'interface dans la démo")
    return items[0]._region


def _region_pos(ed, el):
    from ui.scene_manager.canvas.canvas_region_item import UIRegionItem
    it = next(it for it in ed._gba_scene.items()
              if isinstance(it, UIRegionItem) and it._region is el)
    return (it.pos().x(), it.pos().y())


def test_resync_ramene_la_zone_dinterface(qapp, history):
    """Le correctif : un item de ZONE annulé revient à la position du modèle.
    Avant `reload_scene_items`, `_flush` ne reposait que les sprites — la zone
    restait à sa position draggée."""
    ed = _editor(MYGAME)
    el = _first_region(ed)
    p0 = _region_pos(ed, el)

    history.push(MoveUIRegionCmd(el, el.x, el.y, el.x + 16, el.y))
    ed.reload_scene_items()
    assert _region_pos(ed, el) != p0            # la zone a suivi (résolu)

    history.undo()
    ed.reload_scene_items()
    assert _region_pos(ed, el) == p0            # et revient exactement
