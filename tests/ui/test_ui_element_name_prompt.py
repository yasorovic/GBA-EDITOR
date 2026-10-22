"""Un nom d'élément d'interface déjà pris : l'auteur est prévenu et choisit, au lieu d'un suffixe silencieux."""
from __future__ import annotations

from core.models.ui_region import UILayout, UIText
from core.project import Project
from ui.common.popup import MessageBox
from ui.scene_manager.ui_element_name import resolve_ui_element_name


def _project(tmp_path):
    project = Project(tmp_path / "jeu")
    hud, shop = UILayout(name="hud"), UILayout(name="shop")
    taken, mine = UIText(name="slot2"), UIText(name="slot9")
    hud.elements.append(taken)
    shop.elements.append(mine)
    project.ui_layouts.append(hud)
    project.ui_layouts.append(shop)
    return project, shop, mine


def test_un_nom_libre_est_rendu_tel_quel_sans_question(qapp, tmp_path, monkeypatch):
    project, shop, mine = _project(tmp_path)
    monkeypatch.setattr(MessageBox, "question", lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked")))

    assert resolve_ui_element_name(None, project, shop, mine, "slot3") == "slot3"


def test_un_nom_pris_propose_le_suffixe_et_l_auteur_accepte(qapp, tmp_path, monkeypatch):
    project, shop, mine = _project(tmp_path)
    shown = []
    monkeypatch.setattr(MessageBox, "question",
                        lambda parent, title, text, *a, **k: shown.append(text) or MessageBox.StandardButton.Yes)

    assert resolve_ui_element_name(None, project, shop, mine, "slot2") == "slot2_2"
    assert "hud" in shown[0] and "slot2_2" in shown[0]


def test_un_nom_pris_que_l_auteur_refuse_ne_change_rien(qapp, tmp_path, monkeypatch):
    project, shop, mine = _project(tmp_path)
    monkeypatch.setattr(MessageBox, "question", lambda *a, **k: MessageBox.StandardButton.No)

    assert resolve_ui_element_name(None, project, shop, mine, "slot2") is None
    assert mine.name == "slot9"
