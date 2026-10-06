"""v0.25 — une scène référence PLUSIEURS nœuds `Interface` (`Scene.ui_layouts`,
liste). Migration de l'ancien champ unique `ui_layout`, résolution côté Project,
et le badge de partage (`ui_layout_users`) qui suit la liste."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "editor"))

from core.models.scene import Scene            # noqa: E402
from core.models.ui_region import (            # noqa: E402
    UILayout, UIText, UIImage, TARGET_OBJ, TARGET_BG)
from core.project import Project               # noqa: E402


def _names(nodes):
    """Les noms d'asset référencés par une liste d'`InterfaceNode` (v0.12) — la
    scène tient des nœuds, plus des noms nus."""
    return [n.layout_name for n in nodes]


# ── Migration & sérialisation (modèle pur) ────────────────────────

def test_ancien_ui_layout_unique_devient_une_liste():
    """Un fichier d'avant v0.25 porte `ui_layout` (nom unique) : il se relit en
    liste à une entrée, et ne se réécrit que sous la forme liste."""
    sc = Scene.from_dict({"name": "Titre", "ui_layout": "hud"})
    assert _names(sc.ui_layouts) == ["hud"]
    assert "ui_layout" not in sc.to_dict()
    assert [n["layout_name"] for n in sc.to_dict()["ui_layouts"]] == ["hud"]


def test_ancien_ui_layout_vide_ne_cree_pas_de_reference():
    sc = Scene.from_dict({"name": "Titre", "ui_layout": ""})
    assert sc.ui_layouts == []


def test_nouvelle_forme_liste_relue_telle_quelle():
    sc = Scene.from_dict({"name": "Titre", "ui_layouts": ["hud", "bulle"]})
    assert _names(sc.ui_layouts) == ["hud", "bulle"]


def test_scene_sans_interface_donne_liste_vide():
    assert Scene(name="Vide").ui_layouts == []


# ── Résolution côté Project ───────────────────────────────────────

def test_scene_ui_layouts_resout_dans_lordre(tmp_path):
    p = Project(tmp_path)
    p.ui_layouts.append(UILayout(name="hud"))
    p.ui_layouts.append(UILayout(name="bulle"))
    sc = Scene(name="Titre", ui_layouts=["bulle", "hud"])
    resolved = p.scene_ui_layouts(sc)
    assert [l.name for l in resolved] == ["bulle", "hud"]


def test_ref_cassee_est_sautee_pas_fatale(tmp_path):
    p = Project(tmp_path)
    p.ui_layouts.append(UILayout(name="hud"))
    sc = Scene(name="Titre", ui_layouts=["fantome", "hud"])
    assert [l.name for l in p.scene_ui_layouts(sc)] == ["hud"]


def test_shim_singulier_rend_le_premier(tmp_path):
    p = Project(tmp_path)
    p.ui_layouts.append(UILayout(name="hud"))
    p.ui_layouts.append(UILayout(name="bulle"))
    sc = Scene(name="Titre", ui_layouts=["hud", "bulle"])
    assert p.scene_ui_layout(sc).name == "hud"
    assert p.scene_ui_layout(Scene(name="Vide")) is None


def test_ui_layout_users_compte_chaque_scene_qui_reference(tmp_path):
    """Le badge « partagée — N scènes » suit la liste : un nœud partagé par deux
    scènes les compte toutes deux, y compris quand l'une le combine à un autre."""
    p = Project(tmp_path)
    p.ui_layouts.append(UILayout(name="hud"))
    p.scenes.append(Scene(name="A", ui_layouts=["hud"]))
    p.scenes.append(Scene(name="B", ui_layouts=["hud", "bulle"]))
    p.scenes.append(Scene(name="C", ui_layouts=["autre"]))
    users = p.ui_layout_users("hud")
    assert {s.name for s in users} == {"A", "B"}


# ── Agrégation N-par-scène (temps 3 : ce que le codegen itère) ─────

def _two_layout_project(tmp_path):
    p = Project(tmp_path)
    hud = UILayout(name="hud", target=TARGET_BG)
    hud.elements += [UIText(name="score"), UIImage(name="coeur")]
    bulle = UILayout(name="bulle", target=TARGET_OBJ)
    bulle.elements += [UIText(name="ligne"), UIImage(name="fleche")]
    p.ui_layouts.append(hud)
    p.ui_layouts.append(bulle)
    return p, Scene(name="Jeu", ui_layouts=["hud", "bulle"])


def test_scene_ui_slots_agrege_les_deux_noeuds_dans_lordre(tmp_path):
    p, sc = _two_layout_project(tmp_path)
    slots = p.scene_ui_slots(sc)
    assert [el.name for _l, el in slots] == ["score", "ligne"]
    # chaque slot est apparié à SON nœud (d'où la cible correcte)
    assert {el.name: lay.name for lay, el in slots} == {
        "score": "hud", "ligne": "bulle"}


def test_scene_ui_images_agrege_les_deux_noeuds(tmp_path):
    p, sc = _two_layout_project(tmp_path)
    assert [el.name for _l, el in p.scene_ui_images(sc)] == ["coeur", "fleche"]


def test_scene_ui_elements_couvre_tout(tmp_path):
    p, sc = _two_layout_project(tmp_path)
    assert [el.name for _l, el in p.scene_ui_elements(sc)] == [
        "score", "coeur", "ligne", "fleche"]


# ── v0.12 : slot BG par nœud + routage de rendu (tranche 2, étape 1) ──

def test_scene_ui_bg_slot_vient_du_noeud(tmp_path):
    """Le slot BG d'UI de la scène est celui de son premier nœud rendu en BG,
    plus l'ancien `Scene.text_bg`."""
    p = Project(tmp_path)
    hud = UILayout(name="hud", target=TARGET_BG)
    hud.elements.append(UIText(name="score"))
    p.ui_layouts.append(hud)
    sc = Scene(name="Jeu", ui_layouts=["hud"])
    sc.ui_layouts[0].bg_slot = 2
    assert p.scene_ui_bg_slot(sc) == 2


def test_scene_ui_bg_slot_defaut_sans_noeud_bg(tmp_path):
    """Une scène sans nœud rendu en Background retombe sur le slot par défaut
    (le texte scripté/libre garde une couche UI, comme l'ancien text_bg=1)."""
    p = Project(tmp_path)
    assert p.scene_ui_bg_slot(Scene(name="Vide")) == p.UI_BG_SLOT_DEFAULT


def test_migration_deux_scenes_partagent_un_layout_deux_slots():
    """Le test qui DISTINGUE le modèle par nœud du champ posé sur l'asset : deux
    scènes qui partageaient un layout avec deux `text_bg` différents gardent
    chacune son slot."""
    a = Scene.from_dict({"name": "A", "text_bg": 0, "ui_layouts": ["hud"]})
    b = Scene.from_dict({"name": "B", "text_bg": 2, "ui_layouts": ["hud"]})
    assert a.ui_layouts[0].bg_slot == 0
    assert b.ui_layouts[0].bg_slot == 2


def test_routage_emis_par_noeud(tmp_path):
    """`scene_init` installe le routage de rendu : une réinit puis, par zone BG,
    son slot — celui du NŒUD, pas un slot de scène unique."""
    from codegen.runtime_codegen.main_gen import _gen_ui_routes
    p = Project(tmp_path)
    hud = UILayout(name="hud", target=TARGET_BG)
    hud.elements.append(UIText(name="score"))
    p.ui_layouts.append(hud)
    sc = Scene(name="Jeu", ui_layouts=["hud"])
    sc.ui_layouts[0].bg_slot = 2
    lines = _gen_ui_routes(p, sc)
    assert any("scene_routes_reset()" in l for l in lines)
    # `score` est la région 0 de `all_regions`, routée vers le slot 2 du nœud.
    assert any("scene_route_region(0, 2)" in l for l in lines)


def test_bound_interface_lit_la_cible_de_lasset_sans_figer(tmp_path):
    """Anti-régression : la vue liée lit l'ancrage/cible de l'ASSET, pas une copie
    figée sur le nœud — éditer l'asset se voit sans délai. `bg_slot`, lui, reste
    par nœud."""
    p = Project(tmp_path)
    hud = UILayout(name="hud", target=TARGET_BG)
    hud.elements.append(UIText(name="score"))
    p.ui_layouts.append(hud)
    sc = Scene(name="S", ui_layouts=["hud"])
    sc.ui_layouts[0].bg_slot = 3
    b = p.scene_ui_layouts(sc)[0]
    assert b.resolved_target(None) == TARGET_BG and b.bg_slot == 3
    hud.target = TARGET_OBJ                      # l'auteur édite l'asset
    assert p.scene_ui_layouts(sc)[0].resolved_target(None) == TARGET_OBJ


def test_deux_noeuds_deux_slots_dans_une_scene(tmp_path):
    """Multi-slot (tranche 2, étape 2) : deux nœuds `Interface` sur deux slots BG
    dans la MÊME scène — chacun est déclaré, et son texte routé vers son slot."""
    p = Project(tmp_path)
    a = UILayout(name="a", target=TARGET_BG); a.elements.append(UIText(name="ta"))
    b = UILayout(name="b", target=TARGET_BG); b.elements.append(UIText(name="tb"))
    p.ui_layouts.append(a)
    p.ui_layouts.append(b)
    sc = Scene(name="S", ui_layouts=["a", "b"])
    sc.ui_layouts[0].bg_slot = 0
    sc.ui_layouts[1].bg_slot = 2
    assert p.scene_ui_bg_slots(sc) == [0, 2]
    from codegen.runtime_codegen.main_gen import _gen_ui_routes
    joined = "\n".join(_gen_ui_routes(p, sc))
    assert "scene_route_region(0, 0)" in joined   # ta → BG0
    assert "scene_route_region(1, 2)" in joined   # tb → BG2


def test_la_cible_suit_le_noeud_de_chaque_element(tmp_path):
    """Le point du temps 3 : deux nœuds de la même scène résolvent des cibles
    DIFFÉRENTES, chaque élément prenant celle de son nœud."""
    p, sc = _two_layout_project(tmp_path)
    by_target = {el.name: lay.resolved_target(el)
                 for lay, el in p.scene_ui_elements(sc)}
    assert by_target == {"score": TARGET_BG, "coeur": TARGET_BG,
                         "ligne": TARGET_OBJ, "fleche": TARGET_OBJ}


# ── Renommer un nœud (temps 4 : le + crée, l'en-tête renomme) ──────

def test_rename_ui_layout_met_a_jour_les_refs_de_scenes(tmp_path):
    p = Project(tmp_path)
    p.ui_layouts.append(UILayout(name="hud"))
    p.scenes.append(Scene(name="A", ui_layouts=["hud"]))
    p.scenes.append(Scene(name="B", ui_layouts=["hud", "bulle"]))
    applied = p.rename_ui_layout(p.get_ui_layout("hud"), "menu")
    assert applied == "menu"
    assert p.get_ui_layout("menu") is not None
    assert p.get_ui_layout("hud") is None
    assert _names(p.scenes[0].ui_layouts) == ["menu"]
    assert _names(p.scenes[1].ui_layouts) == ["menu", "bulle"]   # ordre préservé


def test_rename_ui_layout_resout_une_collision(tmp_path):
    p = Project(tmp_path)
    p.ui_layouts.append(UILayout(name="hud"))
    p.ui_layouts.append(UILayout(name="bulle"))
    applied = p.rename_ui_layout(p.get_ui_layout("hud"), "bulle")
    assert applied != "bulle"          # le nom existant n'est pas écrasé
    assert p.get_ui_layout("bulle").name == "bulle"   # l'original intact


# ── Supprimer un nœud (clic-droit sur le nœud d'interface) ────────

def test_supprimer_un_noeud_partage_ne_retire_que_la_reference(tmp_path):
    from core.history import DeleteInterfaceCmd
    p = Project(tmp_path)
    hud = UILayout(name="hud")
    p.ui_layouts.append(hud)
    a = Scene(name="A", ui_layouts=["hud", "bulle"])
    b = Scene(name="B", ui_layouts=["hud"])
    p.scenes.append(a)
    p.scenes.append(b)
    cmd = DeleteInterfaceCmd(p.ui_layouts, hud, a.ui_layouts, delete_asset=False)
    cmd.execute()
    assert _names(a.ui_layouts) == ["bulle"]      # la ref de A part
    assert p.get_ui_layout("hud") is not None     # l'asset reste (B l'emploie)
    cmd.undo()
    assert _names(a.ui_layouts) == ["hud", "bulle"]        # ordre restauré


def test_supprimer_le_seul_usager_emporte_lasset(tmp_path):
    from core.history import DeleteInterfaceCmd
    p = Project(tmp_path)
    bulle = UILayout(name="bulle")
    p.ui_layouts.append(bulle)
    a = Scene(name="A", ui_layouts=["bulle"])
    p.scenes.append(a)
    cmd = DeleteInterfaceCmd(p.ui_layouts, bulle, a.ui_layouts, delete_asset=True)
    cmd.execute()
    assert a.ui_layouts == []
    assert p.get_ui_layout("bulle") is None        # l'asset orphelin part
    cmd.undo()
    assert _names(a.ui_layouts) == ["bulle"]
    assert p.get_ui_layout("bulle") is not None     # et revient à l'annulation
