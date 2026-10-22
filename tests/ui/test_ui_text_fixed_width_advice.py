"""Un texte qui déborde ne conseille d'agrandir que ce qui s'agrandit : une chaîne Text renvoie vers la Textbox."""
from __future__ import annotations

from types import SimpleNamespace

from core.models.ui_region import UIText, UITextbox
from core.validator import _widen_advice


def test_une_chaine_text_conseille_la_textbox():
    advice = _widen_advice(UIText(name="titre"))

    assert "Textbox" in advice and "Enlarge" not in advice


def test_une_textbox_conseille_de_l_agrandir():
    assert _widen_advice(UITextbox(name="dialogue")).startswith("Enlarge")


def test_le_champ_largeur_d_un_text_dit_pourquoi_il_est_grise(qapp):
    from core.models.ui_region import UILayout
    from core.models.scene import Scene
    from core.project import Project
    from ui.scene_manager.inspectors.ui_inspector import UIInspector
    import tempfile
    from pathlib import Path

    project = Project(Path(tempfile.mkdtemp()) / "jeu")
    layout, element = UILayout(name="hud"), UIText(name="titre")
    layout.elements.append(element)
    project.ui_layouts.append(layout)
    scene = Scene(name="Fin", ui_layouts=["hud"])
    project.scenes.append(scene)
    inspector = UIInspector()

    inspector.load(layout, element, project, scene)

    assert not inspector._sp["w"].isEnabled()
    assert "Textbox" in inspector._sp["w"].toolTip()
