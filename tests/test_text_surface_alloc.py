"""La surface de composition est allouée PAR ZONE, pas partagée.

La surface partagée est adressée modulo (`text_surf_tile` dans gba_engine.h)
et ne couvre que 8 rangées sur les 20 de l'écran : deux zones dont les rangées
coïncidaient modulo 8 se disputaient les mêmes tuiles et s'écrasaient en VRAM.
Un titre en haut et une boîte de dialogue en bas — une mise en page banale —
tombaient dans ce cas, et aucun garde-fou ne pouvait rendre ça acceptable :
c'était la mise en page qu'il fallait interdire.

Ce que ces tests protègent :

- des blocs DISJOINTS, quelle que soit la distance entre les zones : c'est la
  propriété qui remplace l'ancien garde-fou ;
- un bloc à la taille du rectangle ABSOLU (une zone enfant d'un panneau
  n'occupe pas les tuiles écran de son offset local) ;
- la surface partagée n'est plus réservée que si un script écrit LIBREMENT
  (`text.draw` / `text.clear`), qui n'ont pas de rectangle à qui donner un
  bloc — la payer sans cela, c'est 240 tuiles pour rien ;
- le chemin TILEMAP ne réclame aucune surface.

Cf. `RegionSurf` (gba_engine.h), `scene_text_reservation` (`surf_layout`) et
`font_emit.scene_writes_free`.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def projet(tmp_path):
    """Une scène, deux zones BG éloignées à l'écran, une police COMPOSÉE.

    Les rangées sont choisies pour tomber en conflit sous l'ancien adressage :
    la zone du haut couvre les rangées 2-5, celle du bas 13-17 — 13 % 8 == 5,
    donc elles se recouvraient sur la rangée 5."""
    from core.project import Project
    from core.models.ui_region import UILayout, UIText
    from core.models.font import Font, Glyph
    from core.models.scene import Scene

    from PIL import Image

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)

    # Police COMPOSÉE : trop de glyphes pour le chemin tilemap, comme une CJK.
    # La planche doit EXISTER sur disque — `encodable_project_fonts` écarte
    # une police sans image, et une police écartée ne réclame aucune surface.
    planche = p.root / "assets" / "fonts" / "grosse.png"
    planche.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(planche)

    police = Font(name="grosse", cell_w=8, cell_h=8, line_height=8,
                  asset=p.asset_rel(planche))
    police.glyphs = [Glyph(char=chr(0x4E00 + i), x=0, y=0, w=8, h=8, advance=8)
                     for i in range(400)]
    p.fonts.append(police)

    titre = UIText(name="titre", x=16, y=16, w=208, h=32)     # rangées 2-5
    boite = UIText(name="boite", x=16, y=104, w=208, h=40)    # rangées 13-17
    layout = UILayout(name="hud")
    layout.elements += [titre, boite]
    p.ui_layouts.append(layout)

    scene = Scene(name="S1", ui_layouts=["hud"], font_name="grosse")
    p.scenes.append(scene)
    return p, scene, layout, titre, boite


def _surf(p, scene):
    from codegen.runtime_codegen.gen_text import scene_text_reservation
    return scene_text_reservation(p, scene)


def test_la_police_choisie_est_bien_composee(projet):
    """Sinon les tests suivants vérifieraient le chemin tilemap sans le dire."""
    from codegen.font_emit import render_composited
    p, _s, _l, _t, _b = projet
    assert render_composited(p.fonts.get("grosse"))


def test_chaque_zone_recoit_son_bloc(projet):
    p, scene, _lay, _t, _b = projet
    layout = _surf(p, scene)["surf_layout"]
    assert {e["name"] for e in layout} == {"titre", "boite"}


def test_les_blocs_ne_se_recouvrent_jamais(projet):
    """LA propriété du chantier : deux zones que l'ancien adressage faisait
    s'écraser (rangées 2-5 et 13-17) occupent des tuiles distinctes."""
    p, scene, _lay, _t, _b = projet
    occupe: set[int] = set()
    for e in _surf(p, scene)["surf_layout"]:
        bloc = set(range(e["base"], e["base"] + e["w"] * e["h"]))
        assert not (bloc & occupe), f"le bloc de '{e['name']}' en recouvre un autre"
        occupe |= bloc


def test_le_bloc_suit_le_rectangle_absolu(projet):
    """Une zone ENFANT d'un panneau occupe les tuiles de sa position écran, pas
    celles de son offset local — sans quoi le bloc serait dimensionné sur la
    mauvaise géométrie."""
    from core.models.ui_region import UIContainer
    p, scene, layout, _titre, boite = projet
    panneau = UIContainer(name="cadre", x=16, y=96, w=208, h=56)
    layout.elements.insert(0, panneau)
    boite.parent = "cadre"
    boite.x, boite.y = 8, 8            # → absolu (24, 104), inchangé

    e = next(x for x in _surf(p, scene)["surf_layout"] if x["name"] == "boite")
    assert (e["w"], e["h"]) == (26, 5)   # 208 px de large depuis x=24, 40 px de haut


def test_sans_ecriture_libre_la_surface_partagee_nest_pas_payee(projet):
    p, scene, _lay, _t, _b = projet
    assert _surf(p, scene)["shared_surf_tiles"] == 0


def test_un_script_qui_ecrit_librement_la_fait_reserver(projet, monkeypatch):
    """`text.draw` n'a pas de rectangle : il lui faut la surface partagée."""
    from codegen import font_emit
    p, scene, _lay, _t, _b = projet
    src = p.project_dir / "libre.lua"
    src.write_text('text:draw(2, 2, "salut")\n', encoding="utf-8")
    monkeypatch.setattr(type(p), "scene_scripts",
                        lambda self, sc: ([src], False), raising=False)
    font_emit.clear_font_scan_cache()
    assert _surf(p, scene)["shared_surf_tiles"] == 240


def test_draw_in_nest_pas_une_ecriture_libre(projet, monkeypatch):
    """`box:draw(…)` passe par une zone, donc par le bloc de cette zone — le
    confondre avec `text.draw` ferait payer 240 tuiles à toute scène scriptée."""
    from codegen import font_emit
    p, scene, _lay, _t, _b = projet
    src = p.project_dir / "zone.lua"
    src.write_text('interface:get("boite"):draw("salut")\n', encoding="utf-8")
    monkeypatch.setattr(type(p), "scene_scripts",
                        lambda self, sc: ([src], False), raising=False)
    font_emit.clear_font_scan_cache()
    assert _surf(p, scene)["shared_surf_tiles"] == 0


def test_un_script_illisible_fait_reserver(projet, monkeypatch):
    """Indécidable = on réserve : ne pas le faire corromprait l'affichage,
    le faire pour rien ne coûte que des tuiles. Même règle que
    `scene_font_names`."""
    from codegen import font_emit
    p, scene, _lay, _t, _b = projet
    monkeypatch.setattr(type(p), "scene_scripts",
                        lambda self, sc: ([], True), raising=False)
    font_emit.clear_font_scan_cache()
    assert _surf(p, scene)["shared_surf_tiles"] == 240


def test_le_chemin_tilemap_ne_reclame_aucune_surface(projet):
    """Une police assez petite pour tenir en VRAM pose des tuiles : pas de
    surface du tout, ni partagée ni par zone."""
    p, scene, _lay, _t, _b = projet
    police = p.fonts.get("grosse")
    del police.glyphs[8:]              # 8 glyphes : le tilemap suffit
    res = _surf(p, scene)
    assert res["surf_layout"] == []
    assert res["shared_surf_tiles"] == 0


def test_une_police_de_langue_composee_reserve_les_zones(projet):
    """Le remplacement japonais de la police par défaut doit être pris en
    compte au build, pas seulement une fois la ROM lancée. Sinon le runtime
    compose ses pixels sans bloc de surface propre et les tronque."""
    from core.models.font import Font, Glyph
    from core.models.settings import Language

    p, scene, _layout, titre, boite = projet
    # `grosse` est notre police CJK composée. Le défaut latin tient au contraire
    # dans la tilemap, mais il est remplacé par `grosse` en japonais.
    latin = Font(name="latin", cell_w=8, cell_h=8, line_height=8,
                 asset=p.fonts.get("grosse").asset)
    latin.glyphs = [Glyph(char="A", x=0, y=0, w=8, h=8, advance=8)]
    p.fonts.append(latin)
    p.settings.default_font = "latin"
    p.settings.languages = [Language(code="ja", name="Japanese",
                                     default_font="grosse")]
    scene.font_name = ""
    assert titre.font_name == boite.font_name == ""

    layout = _surf(p, scene)["surf_layout"]
    assert {entry["name"] for entry in layout} == {"titre", "boite"}
