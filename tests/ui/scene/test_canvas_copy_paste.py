"""Copier/coller des éléments d'interface d'une scène à une autre (canvas).

Régression : `UIRegionController._layout_of` cherchait l'élément dans
`project.active_scene`, alors que tout le reste du contrôleur (`ready`,
`_ensure_layout`, donc le COLLAGE) lit la scène du CONTEXTE (`set_context`). Le
temps d'une bascule de scène les deux divergent : le collage visait la bonne
scène, mais la copie regardait dans la mauvaise, `copy_groups` rendait une liste
vide et le presse-papier se remplissait de rien. Symptôme rapporté : « le Ctrl+V
marche, le Ctrl+C dans une autre scène ne fait rien ».

Ces tests verrouillent que la copie s'appuie sur la scène du contexte, seule
source de vérité du contrôleur, et pas sur `active_scene`."""
from __future__ import annotations


def _project_two_scenes(tmp_path):
    from core.project import Project
    from core.models.scene import Scene
    from core.models.ui_region import UILayout, UIText

    p = Project(tmp_path)
    lay_a = UILayout(name="ui_A")
    lay_a.elements.append(UIText(name="textA", x=8, y=8, w=32, h=16))
    lay_b = UILayout(name="ui_B")
    lay_b.elements.append(UIText(name="textB", x=8, y=8, w=32, h=16))
    p.ui_layouts.append(lay_a)
    p.ui_layouts.append(lay_b)
    p.scenes.append(Scene(name="A", ui_layouts=["ui_A"]))
    p.scenes.append(Scene(name="B", ui_layouts=["ui_B"]))
    return p, lay_a, lay_b


def test_copy_groups_utilise_la_scene_du_contexte(qapp, tmp_path):
    """La copie trouve l'élément dans la scène du contexte même quand
    `active_scene` pointe encore ailleurs (l'état transitoire d'une bascule)."""
    from ui.scene_manager.canvas.canvas_controllers import UIRegionController

    p, _lay_a, lay_b = _project_two_scenes(tmp_path)
    ctrl = UIRegionController()

    p.set_active_scene(0)                    # active_scene = A (pas encore basculée)
    ctrl.set_context(p, p.scenes[1])         # contexte = B (canvas déjà sur B)

    groups = ctrl.copy_groups([lay_b.elements[0]])
    assert [[e.name for e in g] for g in groups] == [["textB"]]


def test_copy_groups_trouve_chaque_scene_quand_le_contexte_suit(qapp, tmp_path):
    """Cas nominal : contexte et scène active alignés, la copie marche dans A
    comme dans B (et non seulement dans la première ouverte)."""
    from ui.scene_manager.canvas.canvas_controllers import UIRegionController

    p, lay_a, lay_b = _project_two_scenes(tmp_path)
    ctrl = UIRegionController()

    for idx, elem in ((0, lay_a.elements[0]), (1, lay_b.elements[0])):
        p.set_active_scene(idx)
        ctrl.set_context(p, p.scenes[idx])
        groups = ctrl.copy_groups([elem])
        assert [[e.name for e in g] for g in groups] == [[elem.name]]


def test_copie_puis_collage_dans_lautre_scene(qapp, tmp_path):
    """Le geste complet : copier dans B (contexte B), coller dans A (contexte A).
    La copie de A porte le nom d'origine réutilisé et vit bien dans la mise en
    page de A — un aller-retour entre scènes, pas une copie dans le vide."""
    from ui.scene_manager.canvas.canvas_controllers import UIRegionController

    p, lay_a, lay_b = _project_two_scenes(tmp_path)
    ctrl = UIRegionController()

    ctrl.set_context(p, p.scenes[1])         # contexte = B
    groups = ctrl.copy_groups([lay_b.elements[0]])
    assert groups                            # le presse-papier n'est pas vide

    ctrl.set_context(p, p.scenes[0])         # contexte = A
    pasted = ctrl.paste_elements(groups)
    assert len(pasted) == 1
    assert pasted[0] in lay_a.elements
