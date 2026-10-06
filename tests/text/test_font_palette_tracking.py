"""La police, une palette d'asset — la scène traque la palette des polices.

Vérifie le cœur du chantier « La police, une palette d'asset comme les autres » :
- une police à usage LIBRE (texte hors conteneur) occupe une banque BG, comme un
  sprite, et apparaît grisée dans la vue de palettes ;
- une police utilisée UNIQUEMENT dans un conteneur à fond n'occupe RIEN : son
  texte prend la banque du conteneur (comportement par défaut) ;
- `scene_font_runtime_banks` (ce que `scene_init` émet) reflète les deux :
  own=1 pour la police propre libre, own=0 pour la police seulement imbriquée.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from core.models.font import Font, Glyph
from core.models.palette import OWN_PAL_BANK, PaletteBank
from core.models.scene import Scene, scene_font_pal_bank
from core.models.settings import Language
from core.models.ui_region import UIContainer, UIText, UILayout, FILL_COLOR
from core.project import Project
from codegen.palette_alloc import (
    scene_palette_view, scene_font_runtime_banks, scene_bank_layout,
)


def _ecrire_planche(path, ink: tuple[int, int, int]) -> None:
    """Une planche 8×8 : moitié encre opaque, moitié transparente."""
    arr = np.zeros((8, 8, 4), dtype=np.uint8)
    arr[:4, :, :3] = ink
    arr[:4, :, 3] = 255            # encre opaque
    Image.fromarray(arr, "RGBA").save(path)


def _police(p: Project, nom: str, ink: tuple[int, int, int]) -> Font:
    rel = f"assets/fonts/{nom}.png"
    _ecrire_planche(p.asset_abs(rel), ink)
    f = Font(name=nom, cell_w=8, cell_h=8, line_height=8, asset=rel)
    f.glyphs = [Glyph(char=c, w=8, h=8, advance=8) for c in "OK abc"]
    p.fonts.append(f)
    return f


@pytest.fixture
def projet(tmp_path) -> Project:
    p = Project(tmp_path)
    (p.assets_dir / "fonts").mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def scene_avec_conteneur(projet) -> Scene:
    """Un conteneur couleur avec un texte ENFANT (police imbriquée), et un texte
    LIBRE à la racine (police libre)."""
    _police(projet, "FontFree", (200, 30, 30))     # encre rouge
    _police(projet, "FontNested", (30, 30, 200))    # encre bleue
    projet.palettes.append(PaletteBank(name="BoxPal",
                                       colors=[0, 0x001F, 0x03E0, 0x7C00] + [0] * 12))

    box = UIContainer(name="Box", fill_kind=FILL_COLOR,
                      fill_palette="BoxPal", fill_index=1, x=0, y=0, w=120, h=40)
    inside = UIText(name="inside", parent="Box", font_name="FontNested",
                    x=8, y=8, w=96, h=16)
    free = UIText(name="free", parent="", font_name="FontFree",
                  x=0, y=120, w=96, h=16)
    lay = UILayout(name="HUD", elements=[box, inside, free])
    projet.ui_layouts.append(lay)

    scene = Scene(name="S", font_name="FontFree",
                  ui_layouts=["HUD"], active_bg_palettes=["BoxPal"])
    projet.scenes.append(scene)
    return scene


def _font_labels(view) -> list[str]:
    """Étiquettes des entrées d'asset qui viennent d'une police."""
    out = []
    for e in view.asset_entries:
        for inst in e.instances:
            if inst.kind == "font":
                out.append(inst.label)
    return out


def test_une_police_libre_occupe_une_banque_grisee(projet, scene_avec_conteneur):
    view = scene_palette_view(projet, scene_avec_conteneur, "bg")
    labels = _font_labels(view)
    assert any("FontFree" in l for l in labels), labels


def test_une_police_seulement_imbriquee_n_occupe_rien(projet, scene_avec_conteneur):
    view = scene_palette_view(projet, scene_avec_conteneur, "bg")
    labels = _font_labels(view)
    # FontNested n'est utilisée que dans le conteneur : elle prend la banque du
    # conteneur, pas un slot à elle → absente de la vue.
    assert not any("FontNested" in l for l in labels), labels


def test_runtime_banks_own_pour_libre_zero_pour_imbriquee(projet, scene_avec_conteneur):
    banks = scene_font_runtime_banks(projet, scene_avec_conteneur)
    assert "FontFree" in banks and "FontNested" in banks, banks
    # Police libre en mode propre : charge sa palette (own=1), banque allouée.
    free_bank, free_own = banks["FontFree"]
    assert free_own == 1
    assert 0 <= free_bank < 16
    # Police seulement imbriquée : ne charge rien (own=0), le conteneur possède
    # la banque.
    _nested_bank, nested_own = banks["FontNested"]
    assert nested_own == 0


def test_la_police_libre_partage_l_allocation_bg(projet, scene_avec_conteneur):
    """La banque de la police libre est une vraie banque de `scene_bank_layout`,
    pas un 15 épinglé : la police entre dans l'allocation comme un sprite."""
    layout = scene_bank_layout(projet, scene_avec_conteneur, "bg")
    banks = scene_font_runtime_banks(projet, scene_avec_conteneur)
    free_bank, _ = banks["FontFree"]
    # La banque allouée est réellement occupée dans le layout.
    assert layout.slot_colors[free_bank] is not None


def test_override_du_picker_place_la_police_sur_un_slot_de_scene(projet, scene_avec_conteneur):
    """Le picker « UI colors » (police par défaut, clé "") override la police
    libre vers un slot de scène : own passe à 0, la banque devient ce slot."""
    scene_avec_conteneur.font_pal_banks = {"": 0}   # BoxPal, slot 0
    assert scene_font_pal_bank(scene_avec_conteneur, "FontFree", "FontFree") == 0
    banks = scene_font_runtime_banks(projet, scene_avec_conteneur)
    assert banks["FontFree"] == (0, 0)


def test_substitut_de_langue_herite_de_la_palette_du_defaut(projet, scene_avec_conteneur):
    """Une traduction japonaise remplace le défaut logique, pas son choix de
    palette : l'encre sélectionnée dans l'inspecteur doit donc rester active."""
    _police(projet, "FontJapanese", (20, 20, 20))
    projet.settings.default_font = "FontFree"
    projet.settings.languages = [Language(code="ja", name="Japanese",
                                          default_font="FontJapanese")]
    scene_avec_conteneur.font_pal_banks = {"": 0}

    banks = scene_font_runtime_banks(projet, scene_avec_conteneur)

    assert banks["FontFree"] == (0, 0)
    assert banks["FontJapanese"] == (0, 0)


def test_renommer_une_police_suit_son_override_de_banque(projet, scene_avec_conteneur):
    """Renommer une police NON-défaut déplace sa clé dans `Scene.font_pal_banks`
    (keyé par nom) : sans ce suivi, l'override vivrait sous le nom mort et
    retomberait en silence sur la palette propre. La police PAR DÉFAUT passe par
    la clé "" — stable, non concernée."""
    scene = scene_avec_conteneur
    # Un override par NOM sur une police non-défaut, plus la clé "" du défaut.
    scene.font_pal_banks = {"FontNested": 2, "": 0}
    font = next(f for f in projet.fonts if f.name == "FontNested")

    projet.rename_font(font, "FontRenamed")

    assert "FontNested" not in scene.font_pal_banks
    assert scene.font_pal_banks.get("FontRenamed") == 2
    assert scene.font_pal_banks.get("") == 0          # le défaut est épargné
    # Le codegen lit l'override sous le nouveau nom.
    assert scene_font_pal_bank(scene, "FontRenamed", "FontFree") == 2
