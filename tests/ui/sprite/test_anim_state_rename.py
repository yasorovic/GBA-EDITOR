"""F2 renomme l'état d'animation de la ligne courante, même quand c'est une de ses directions qui est choisie."""
from __future__ import annotations

from PyQt6.QtGui import QShortcut
from PyQt6.QtWidgets import QLineEdit


def _panel(qapp, tmp_path):
    from core.models.sprite import AnimState, SpriteAsset, StateDirection
    from core.project import Project
    from ui.sprite_editor.sprite_library_panel import SpriteLibraryPanel

    project = Project(tmp_path / "jeu")
    sprite = SpriteAsset(name="Hero", asset="hero.png", states=[
        AnimState(name="Idle", directions=[StateDirection(dir=1), StateDirection(dir=3)])])
    project.sprites.append(sprite)
    panel = SpriteLibraryPanel()
    panel.resize(300, 400)
    panel.load_project(project)
    panel.show()
    panel._current_sprite = sprite
    panel.refresh_anim_tree()
    qapp.processEvents()
    return panel


def test_renommer_depuis_une_direction_edite_le_nom_de_son_etat(qapp, tmp_path):
    panel = _panel(qapp, tmp_path)
    tree = panel._anim_tree
    tree.setCurrentItem(tree.topLevelItem(0).child(1))      # une direction est choisie

    panel._rename_current_state()                            # ce que déclenche F2

    editor = tree.viewport().findChild(QLineEdit)
    assert editor is not None and editor.text() == "Idle"


def test_f2_est_branche_sur_l_arbre_des_etats(qapp, tmp_path):
    panel = _panel(qapp, tmp_path)
    keys = [s.key().toString() for s in panel._anim_tree.findChildren(QShortcut)]
    assert "F2" in keys
