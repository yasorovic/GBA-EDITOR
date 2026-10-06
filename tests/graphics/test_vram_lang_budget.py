"""La réservation VRAM du texte est ce que le runtime CHARGE (ROADMAP v0.9,
phase 5.1).

Avant cette phase, deux calculs répondaient à la même question et ne
tombaient pas d'accord : `_emit_font_subsets` émettait le sous-ensemble de
glyphes UNI sur toutes les langues (décision 4 de la phase 3.3) — que
`text_set_font` copie en VRAM entier, quelle que soit la valeur de `g_lang` —
pendant que `scene_text_reservation` dimensionnait le bloc sur la seule langue
SOURCE. Une traduction qui ajoutait des caractères faisait donc charger deux
fois ce qui avait été réservé, et le débordement écrasait ce qui suit le bloc
de glyphes : les bases des polices voisines, la surface composée, les sprites
en cible BG. Rien ne le disait — `_check_vram_lang_budget` (phase 3.4)
comparait langue par langue, donc sous-estimait l'union lui aussi, et n'était
qu'un avertissement au motif — faux — que « rien n'est cassé aujourd'hui ».

Ces tests remplacent cette comparaison par l'égalité qu'elle aurait dû
protéger : **ce qui est réservé est exactement ce qui est chargé**.
"""
from __future__ import annotations

import pytest

# 12 glyphes hors-latin, pour simuler ce qu'une traduction ajoute (un vrai
# projet y mettrait des kanji ou des accents) sans dépendre d'une planche
# réelle sur disque.
_EXTRA = "".join(chr(0xE000 + i) for i in range(12))


def _font(p):
    # `encodable_project_fonts` écarte une police sans planche PRÉSENTE SUR
    # DISQUE (cf. test_text_surface_alloc.py) : une police sans fichier n'est
    # pas retenue, même déclarée dans le projet.
    from PIL import Image
    from core.models.font import Font, Glyph
    planche = p.root / "assets" / "fonts" / "test_font.png"
    planche.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(planche)
    f = Font(name="test_font", cell_w=8, cell_h=8, line_height=8,
             asset=p.asset_rel(planche))
    f.glyphs = [Glyph(char=c, w=8, h=8, advance=8) for c in ("Hi0123456789" + _EXTRA)]
    return f


@pytest.fixture
def projet(tmp_path):
    from core.project import Project
    from core.models.settings import Language
    from core.models.ui_region import UILayout, UIText
    from core.models.scene import Scene

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)
    p.fonts.append(_font(p))

    zone = UIText(name="bubble", w=64, h=16)
    layout = UILayout(name="hud")
    layout.elements.append(zone)
    p.ui_layouts.append(layout)

    t = p.new_text(content="Hi", path=["Dialogue", "Greet"])
    zone.text_key = t.key

    scene = Scene(name="Main", ui_layouts=["hud"], font_name="test_font")
    p.scenes.append(scene)

    p.settings.source_lang = Language(code="en", name="English")
    p.settings.languages = [Language(code="ja", name="Japanese")]
    p.load_translations()
    return p, scene, t


def _reserve(p, scene) -> int:
    """Tuiles de glyphes que le BUILD réserve pour cette scène."""
    from codegen.runtime_codegen.gen_text import scene_text_reservation
    return scene_text_reservation(p, scene)["mono_tiles"]


def _load(p, scene) -> int:
    """Tuiles de glyphes que le RUNTIME copie en VRAM — la longueur du
    `FontSubset` émis, que `text_set_font` recopie entière (`n_load`)."""
    from codegen.font_emit import (encode_font, build_font_subset,
                                   scene_codepoints_union)
    from codegen.runtime_codegen.gen_text import _declared_lang_codes
    font = p.fonts[0]
    e = encode_font(font, p.asset_abs(font.asset))
    sub = build_font_subset(e, scene_codepoints_union(p, scene,
                                                      _declared_lang_codes(p)))
    return len(sub["load"])


def test_sans_traduction_reserve_ce_qui_est_charge(projet):
    p, scene, _t = projet
    assert _reserve(p, scene) == _load(p, scene)


def test_une_traduction_qui_ajoute_des_glyphes_est_reservee(projet):
    """Le cas qui débordait : la source tient en 12 tuiles, la traduction en
    ajoute 12, et le runtime charge l'union des deux."""
    p, scene, t = projet
    p.translations["ja"][t.id] = _EXTRA

    charge = _load(p, scene)
    assert charge == 24                      # 12 chiffres + 12 glyphes ajoutés
    assert _reserve(p, scene) == charge      # et non 12, comme avant la phase 5.1


def test_une_traduction_plus_courte_ne_retire_rien(projet):
    """L'union ne rétrécit jamais : une traduction qui n'emploie qu'une partie
    des caractères de la source laisse la source dans le sous-ensemble."""
    p, scene, t = projet
    p.translations["ja"][t.id] = "H"

    assert _reserve(p, scene) == _load(p, scene)
    assert _reserve(p, scene) == 12          # "Hi" + les chiffres, inchangé


def test_projet_monolingue_inchange(projet):
    """Un projet sans langue déclarée voit exactement les mêmes chiffres
    qu'avant la phase 5.1 : l'union d'une seule langue est cette langue."""
    p, scene, t = projet
    p.translations["ja"][t.id] = _EXTRA
    p.settings.languages = []

    assert _reserve(p, scene) == _load(p, scene)
    assert _reserve(p, scene) == 12          # la traduction orpheline ne pèse plus


def test_la_liste_des_langues_est_la_meme_pour_les_deux_lecteurs(projet):
    """`_declared_lang_codes` est le point unique : c'est de leur divergence
    que venait le décalage, pas du calcul de sous-ensemble lui-même."""
    p, _scene, _t = projet
    from codegen.runtime_codegen.gen_text import _declared_lang_codes
    assert _declared_lang_codes(p) == ["en", "ja"]

    p.settings.languages = []
    p.settings.source_lang.code = ""
    assert _declared_lang_codes(p) == [""]
