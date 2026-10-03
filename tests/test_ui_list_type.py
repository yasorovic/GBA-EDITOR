"""`UIList` est un TYPE, plus un drapeau du conteneur (ROADMAP v0.22, 2026-09-02).

Ce que ces tests tiennent, et qui n'a pas de garde ailleurs :

- **La relecture des anciens projets.** Un `{"kind": "panel", "is_list": true}`
  doit ressortir en `UIList` sans rien perdre, et ne jamais être réécrit sous
  cette forme. Le cas `list_axis: "horizontal"` se termine au niveau de la mise
  en page, seul endroit à connaître le nombre de rangées — c'est exactement le
  genre de conversion en deux temps qui se casse en silence.
- **Le fond est une CAPACITÉ.** Les émetteurs demandaient `kind == KIND_CONTAINER` ;
  si un seul redevenait un test de type, la liste perdrait son fond sans qu'une
  erreur soit levée nulle part.
- **Ce qu'une liste accueille.** Ses enfants SONT ses rangées : accepter une
  image ferait poser un élément que le build ignore ensuite.
"""
from __future__ import annotations

import re

import pytest


# ── Relecture des projets d'avant le 2026-09-02 ───────────────────

def test_un_panneau_marque_liste_ressort_en_uilist():
    from core.models.ui_region import element_from_dict, KIND_LIST

    el = element_from_dict({
        "kind": "panel", "name": "Menu", "is_list": True,
        "list_wrap": False, "list_repeat_delay": 7, "list_repeat_rate": 2,
        "fill_kind": "color", "fill_palette": "hud", "fill_index": 3,
    })
    assert el.kind == KIND_LIST
    # Les `list_*` perdent leur préfixe, redondant sur un type qui EST une liste.
    assert (el.wrap, el.repeat_delay, el.repeat_rate) == (False, 7, 2)
    # Le fond suit le type : il vit dans le mixin, pas dans le panneau.
    assert (el.fill_kind, el.fill_palette, el.fill_index) == ("color", "hud", 3)


def test_un_panneau_ordinaire_devient_un_conteneur():
    """`"panel"` était le kind du conteneur jusqu'au 2026-09-02 — le mot était
    déjà pris par les panneaux de l'ÉDITEUR, qui sont autre chose. Un projet
    d'avant se relit sans rien perdre, et sans gagner de navigation."""
    from core.models.ui_region import element_from_dict, KIND_CONTAINER, UIContainer

    el = element_from_dict({"kind": "panel", "name": "Cadre",
                            "fill_kind": "color", "fill_index": 4})
    assert isinstance(el, UIContainer) and el.kind == KIND_CONTAINER
    assert el.fill_index == 4
    assert "nav_columns" not in el.to_dict()


def test_les_formes_anciennes_ne_sont_jamais_reecrites():
    """Une seule forme s'ÉCRIT — la recette de `KIND_REGION`, appliquée aussi au
    drapeau `is_list` et au kind `"panel"`."""
    from core.models.ui_region import element_from_dict

    liste = element_from_dict({"kind": "panel", "name": "Menu",
                               "is_list": True}).to_dict()
    assert liste["kind"] == "list"
    assert "is_list" not in liste and "list_axis" not in liste \
        and "list_wrap" not in liste

    conteneur = element_from_dict({"kind": "panel", "name": "Cadre"}).to_dict()
    assert conteneur["kind"] == "container"


def test_une_liste_horizontale_devient_une_grille_dune_ligne():
    """`list_axis` avait besoin des ENFANTS pour se convertir : une rangée
    d'onglets est une grille d'une ligne, donc `nav_columns` = le nombre de
    rangées. L'élément seul ne les connaît pas — la conversion se termine dans
    `UILayout.from_dict`, et c'est ce raccord qu'on tient ici."""
    from core.models.ui_region import UILayout, NAV_ROW

    lay = UILayout.from_dict({"name": "hud", "elements": [
        {"kind": "panel", "name": "Onglets", "is_list": True,
         "list_axis": "horizontal"},
        {"kind": "text", "name": "a", "parent": "Onglets"},
        {"kind": "text", "name": "b", "parent": "Onglets"},
        {"kind": "text", "name": "c", "parent": "Onglets"},
    ]})
    lst = lay.get("Onglets")
    assert (lst.nav_columns, lst.nav_major) == (3, NAV_ROW)


def test_une_liste_verticale_na_rien_a_convertir():
    from core.models.ui_region import UILayout, NAV_COLUMN

    lay = UILayout.from_dict({"name": "hud", "elements": [
        {"kind": "panel", "name": "Menu", "is_list": True, "list_axis": "vertical"},
        {"kind": "text", "name": "a", "parent": "Menu"},
    ]})
    lst = lay.get("Menu")
    assert (lst.nav_columns, lst.nav_major) == (1, NAV_COLUMN)


# ── Le fond est une capacité, pas un type ─────────────────────────

def test_les_deux_conteneurs_dessinent_un_fond():
    from core.models.ui_region import UIContainer, UIList, UIText, UIImage, can_fill

    assert can_fill(UIContainer()) and can_fill(UIList())
    assert not can_fill(UIText()) and not can_fill(UIImage())


def test_le_fond_couleur_dune_liste_est_emis(tmp_path):
    """Le test qui attrape un `kind == KIND_CONTAINER` réintroduit dans un émetteur :
    la liste garderait son champ et perdrait son fond, sans erreur nulle part."""
    from core.project import Project
    from core.models.scene import Scene
    from core.models.palette import PaletteBank
    from core.models.ui_region import UILayout, UIList
    from codegen.runtime_codegen.gen_text import scene_color_fills

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)
    lay = UILayout(name="hud")
    lay.elements.append(UIList(name="Menu", x=0, y=0, w=64, h=32,
                              fill_kind="color", fill_palette="hud",
                              fill_index=2))
    p.ui_layouts.append(lay)
    p.palettes.append(PaletteBank(name="hud", colors=[0] * 16))
    scene = Scene(name="Titre", ui_layouts=["hud"])
    scene.ui_layouts[0].bg_slot = 0     # slot BG du nœud Interface (v0.12)
    scene.active_bg_palettes = ["hud"]
    p.scenes.append(scene)

    fills, _indices = scene_color_fills(p, scene)
    assert [f["name"] for f in fills] == ["Menu"]


# ── Ce qu'une liste accueille ─────────────────────────────────────

def test_une_liste_naccueille_que_des_textes():
    from core.models.ui_region import UILayout, UIList, UIText, UIImage

    lay = UILayout(name="hud")
    lay.elements += [UIList(name="Menu"), UIText(name="ligne"),
                     UIImage(name="curseur")]
    assert lay.can_contain("Menu", "text")
    assert not lay.can_contain("Menu", "image")
    # Et le reparentage le fait respecter, pas seulement le menu contextuel.
    assert lay.place_child("ligne", "Menu")
    assert not lay.place_child("curseur", "Menu")
    assert lay.get("curseur").parent == ""


def test_un_conteneur_accueille_tous_les_types():
    from core.models.ui_region import UILayout, UIContainer, UIImage

    lay = UILayout(name="hud")
    lay.elements += [UIContainer(name="Cadre"), UIImage(name="deco")]
    assert lay.can_contain("Cadre", "image")
    assert lay.place_child("deco", "Cadre")


# ── Ce que le build émet ──────────────────────────────────────────

def _row(src: str) -> list[str]:
    m = re.search(r"g_ui_lists\[\] = \{\{([^}]*)\}", src)
    assert m, f"g_ui_lists introuvable :\n{src}"
    return [x.strip() for x in m.group(1).split(",")]


@pytest.fixture
def projet(tmp_path):
    from core.project import Project
    from core.models.ui_region import UILayout, UIList, UIText, UIImage, NAV_ROW

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)
    lst = UIList(name="Menu", nav_columns=2, nav_major=NAV_ROW,
                 cursor_image="Fleche", cursor_mode="slide", cursor_speed=4,
                 selected_text_color=5, selected_highlight_color=9)
    lay = UILayout(name="hud")
    lay.elements.append(lst)
    lay.elements += [UIText(name=n, parent="Menu")
                     for n in ("a", "b", "c", "d")]
    lay.elements.append(UIImage(name="Fleche"))
    p.ui_layouts.append(lay)
    return p, lay, lst


def test_la_grille_le_curseur_et_le_style_partent_dans_la_table(projet):
    from codegen.runtime_codegen.gen_ui import emit_ui_lists_c
    p, _lay, _lst = projet
    src = "\n".join(emit_ui_lists_c(p))
    rows, cols, major, wrap = _row(src)[:4]
    assert (rows, cols, major) == ("4", "2", "1")
    cursor, mode, speed, ink, hl = _row(src)[7:12]
    # Le curseur est un INDEX dans g_ui_images — la seule image du projet.
    assert (cursor, mode, speed, ink, hl) == ("0", "1", "4", "5", "9")


def test_une_liste_sans_curseur_est_un_cas_normal(projet):
    """Le curseur n'est PAS obligatoire : une liste qui marque sa sélection au
    surlignement, ou qu'un script pilote lui-même, n'en désigne aucun. Rien à
    signaler, donc — un avertissement ici ferait passer un choix pour un oubli,
    et pousserait à poser une image dont le jeu n'a pas besoin."""
    from codegen.runtime_codegen.gen_ui import emit_ui_lists_c
    p, _lay, lst = projet
    lst.cursor_image = ""
    logs: list[str] = []
    src = "\n".join(emit_ui_lists_c(p, emit=lambda _k, m: logs.append(m)))
    # -1 = aucun curseur ; `ui_list_cursor_follow` sort là-dessus sans rien lire.
    assert _row(src)[7] == "-1"
    assert not any("curseur" in m for m in logs)


def test_un_curseur_introuvable_ne_fait_pas_echouer_le_build(projet):
    from codegen.runtime_codegen.gen_ui import emit_ui_lists_c
    p, _lay, lst = projet
    lst.cursor_image = "Absent"
    logs: list[str] = []
    src = "\n".join(emit_ui_lists_c(
        p, emit=lambda k, m: logs.append(m.console_line() if k == "diagnostic" else m)))
    assert _row(src)[7] == "-1"
    assert any("Absent" in m for m in logs)


def test_letat_actif_authore_part_dans_son_tableau_vivant(projet):
    from codegen.runtime_codegen.gen_ui import emit_ui_lists_c
    p, _lay, lst = projet
    lst.active = False
    src = "\n".join(emit_ui_lists_c(p))
    assert "int g_ui_list_active[] = {0};" in src


def test_la_couleur_de_selection_est_chargee_par_la_scene(projet):
    """Sans ça, `text_var_for` ne trouve pas la variante et la rangée choisie
    reste à son encre — un réglage posé, sans effet, et rien qui le dise."""
    from core.models.scene import Scene
    from codegen.runtime_codegen.gen_text import scene_text_colors
    p, _lay, _lst = projet
    scene = Scene(name="Titre", ui_layouts=["hud"])
    p.scenes.append(scene)
    assert 5 in scene_text_colors(p, scene, "police")
