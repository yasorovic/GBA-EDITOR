"""v0.12 — validation des nœuds `Interface` (slot BG par nœud).

Trois règles que le build doit refuser plutôt que de sortir un ROM corrompu :
  • un slot BG que le mode vidéo n'expose pas ;
  • un même layout posé deux fois dans une scène (collision de noms REGION_*/IMAGE_*) ;
  • une interface qui partage son slot BG avec un décor (charblock écrasé).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "editor"))

from core.project import Project                        # noqa: E402
from core.models.scene import Scene                     # noqa: E402
from core.models.background import BackgroundLayer      # noqa: E402
from core.models.ui_region import UILayout, UIText, TARGET_BG   # noqa: E402
from core.validator import (                            # noqa: E402
    ValidationContext, _check_ui_node_slots, _check_bg_text_cbb_conflict)


def _errs(p, fn) -> list[str]:
    ctx = ValidationContext(p)
    fn(ctx)
    return [m.message for m in ctx.errors]


def _proj(tmp_path) -> Project:
    p = Project(tmp_path)
    hud = UILayout(name="hud", target=TARGET_BG)
    hud.elements.append(UIText(name="score"))
    p.ui_layouts.append(hud)
    return p


def test_slot_indisponible_dans_le_mode_est_une_erreur(tmp_path):
    p = _proj(tmp_path)
    sc = Scene(name="S", ui_layouts=["hud"], render_mode=1)   # mode 1 : pas de BG3
    sc.ui_layouts[0].bg_slot = 3
    p.scenes.append(sc)
    assert any("BG3" in e and "mode" in e for e in _errs(p, _check_ui_node_slots))


def test_slot_valide_ne_dit_rien(tmp_path):
    p = _proj(tmp_path)
    sc = Scene(name="S", ui_layouts=["hud"], render_mode=0)
    sc.ui_layouts[0].bg_slot = 2
    p.scenes.append(sc)
    assert _errs(p, _check_ui_node_slots) == []


def test_meme_layout_pose_deux_fois_est_une_erreur(tmp_path):
    p = _proj(tmp_path)
    p.scenes.append(Scene(name="S", ui_layouts=["hud", "hud"]))
    assert any("placed twice" in e for e in _errs(p, _check_ui_node_slots))


def _deux_layouts(tmp_path, nom_b: str) -> Project:
    p = Project(tmp_path)
    for layout_name, element in (("main", "titre"), ("victoire", nom_b)):
        layout = UILayout(name=layout_name, target=TARGET_BG)
        layout.elements.append(UIText(name=element))
        p.ui_layouts.append(layout)
    return p


def test_deux_layouts_avec_un_element_homonyme_est_une_erreur(tmp_path):
    """Deux scènes, deux layouts, chacun avec « titre » : REGION_TITRE serait défini
    deux fois, avec deux valeurs. Le cas d'une démo réelle."""
    from core.validator import _check_ui_element_names_unique

    errors = _errs(_deux_layouts(tmp_path, "titre"), _check_ui_element_names_unique)

    assert len(errors) == 1
    assert "titre" in errors[0] and "'main'" in errors[0] and "'victoire'" in errors[0]


def test_des_noms_distincts_entre_layouts_ne_disent_rien(tmp_path):
    from core.validator import _check_ui_element_names_unique

    assert _errs(_deux_layouts(tmp_path, "titre_victoire"), _check_ui_element_names_unique) == []


def test_deux_elements_homonymes_dans_un_meme_layout_sont_signales(tmp_path):
    from core.validator import _check_ui_element_names_unique

    p = Project(tmp_path)
    layout = UILayout(name="hud", target=TARGET_BG)
    layout.elements += [UIText(name="score"), UIText(name="score")]
    p.ui_layouts.append(layout)

    assert any("score" in e for e in _errs(p, _check_ui_element_names_unique))


def test_interface_qui_partage_son_slot_avec_un_decor(tmp_path):
    p = _proj(tmp_path)
    sc = Scene(name="S", ui_layouts=["hud"],
               background_layers=[BackgroundLayer(background_name="decor", bg_slot=2)])
    sc.ui_layouts[0].bg_slot = 2
    p.scenes.append(sc)
    assert any("shares its slot" in e for e in _errs(p, _check_bg_text_cbb_conflict))


def test_interface_et_decor_sur_slots_distincts_ok(tmp_path):
    p = _proj(tmp_path)
    sc = Scene(name="S", ui_layouts=["hud"],
               background_layers=[BackgroundLayer(background_name="decor", bg_slot=0)])
    sc.ui_layouts[0].bg_slot = 2
    p.scenes.append(sc)
    assert _errs(p, _check_bg_text_cbb_conflict) == []
