"""Les glyphes animés d'une zone d'interface — dérivés, plus déclarés.

Le nombre de caractères qu'une zone sort de la bande pour les animer était un
champ, rempli à la main dans l'inspecteur. Il se déduit désormais du texte
affiché. Ce que ces tests protègent, c'est ce que cette bascule ne doit PAS
casser :

- une réservation trop BASSE fait retomber l'effet en statique sans un mot :
  d'où le maximum sur toutes les langues, et pas la seule source ;
- une réservation trop HAUTE mange des slots OAM que les acteurs n'auront
  plus : d'où le plafond, et le zéro quand rien n'est animé ;
- le modèle ne résout pas la table de textes — le compte lui est FOURNI, comme
  les frames d'un sprite (`layout_obj_budget`).

Cf. `Project.region_animated_glyphs` et `core/models/ui_region.py`.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def projet(tmp_path):
    from core.project import Project
    from core.models.settings import Language
    from core.models.ui_region import UILayout, UIText

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)
    zone = UIText(name="bubble", w=64, h=16)
    layout = UILayout(name="hud")
    layout.elements.append(zone)
    p.ui_layouts.append(layout)
    t = p.new_text(content="Hi [wave]there[/wave]")
    t.key = "line"
    zone.text_key = t.key
    p.settings.source_lang = Language(code="en", name="English")
    p.settings.languages = [Language(code="de", name="Deutsch")]
    p.load_translations()
    return p, layout, zone, t


def test_le_compte_vient_du_texte_affiche(projet):
    p, _lay, zone, _t = projet
    assert p.region_animated_glyphs(zone) == len("there")


def test_rien_danime_ne_reserve_rien(projet):
    p, _lay, zone, t = projet
    t.content = "Hi there"          # plus une seule balise animée
    assert p.region_animated_glyphs(zone) == 0


def test_une_traduction_plus_large_eleve_la_reservation(projet):
    """Sous-réserver ferait retomber l'effet en statique dans cette langue-là,
    et la ROM contient les deux."""
    p, _lay, zone, t = projet
    p.translations["de"][t.id] = "Hallo [wave]weite Welt[/wave]"
    assert p.region_animated_glyphs(zone) == len("weite Welt")


def test_une_zone_sans_entree_se_mesure_sur_son_echantillon(projet):
    from core.models.ui_region import UIText
    p, lay, _zone, t = projet
    libre = UIText(name="script_zone", w=64, h=16)
    lay.elements.append(libre)
    assert p.region_animated_glyphs(libre) == 0     # rien à quoi se raccrocher
    libre.preview_text = t.key
    assert p.region_animated_glyphs(libre) == len("there")


def test_le_plafond_materiel_est_respecte(projet):
    from core.models.ui_region import ANIM_GLYPH_MAX
    p, _lay, zone, t = projet
    t.content = "[shake]" + "x" * (ANIM_GLYPH_MAX + 20) + "[/shake]"
    # Au-delà, le runtime écrête (tableaux de capture de taille fixe) : réserver
    # plus serait payer des slots OAM que rien ne peut utiliser.
    assert p.region_animated_glyphs(zone) == ANIM_GLYPH_MAX


def test_la_geometrie_recoit_le_compte_elle_ne_le_lit_pas(projet):
    """Le modèle ne résout pas la table de textes — même convention que
    `image_frames`. Un appelant qui ne fournit rien obtient la bande seule."""
    from core.models.ui_region import strip_geometry
    _p, _lay, zone, _t = projet
    assert not hasattr(zone, "animated_glyphs")
    base = strip_geometry(zone)
    assert base["anim"] == 0
    with_anim = strip_geometry(zone, 5)
    assert with_anim["anim"] == 5
    assert with_anim["oam"] == base["oam"] + 5


def test_le_budget_de_la_mise_en_page_prend_le_dictionnaire(projet):
    from core.models.ui_region import layout_obj_budget, TARGET_OBJ
    p, lay, zone, _t = projet
    lay.target = TARGET_OBJ          # la cible appartient au nœud (v0.25)
    place = layout_obj_budget(
        lay, animated_by_name=p.layout_animated_glyphs(lay))["place"]
    assert place[zone.name]["anim"] == len("there")
    # Sans le dictionnaire : la bande seule, jamais une supposition.
    assert layout_obj_budget(lay)["place"][zone.name]["anim"] == 0


def test_un_ancien_fichier_perd_la_cle_sans_broncher(projet):
    """La clé d'un projet écrit avant la bascule est ignorée à la lecture et ne
    se réécrit pas — « une seule forme ÉCRITE »."""
    from core.models.ui_region import UIText
    _p, _lay, zone, _t = projet
    d = zone.to_dict()
    assert "animated_glyphs" not in d
    revived = UIText.from_dict({**d, "animated_glyphs": 12})
    assert not hasattr(revived, "animated_glyphs")
    assert "animated_glyphs" not in revived.to_dict()
