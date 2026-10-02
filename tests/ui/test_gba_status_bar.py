"""La jauge « sprites / tuiles / cycles » de la barre d'état lit les MÊMES faits que
le build : un composant sprite sans sprite n'affiche rien et ne réserve rien, et
plusieurs apparences ne pèsent que sur la VRAM (une seule dessine à la fois)."""
import pytest

from core.models.components import SpriteComponent
from core.models.scene import Actor, Scene
from core.models.sprite import SpriteAsset
from core.project import Project
from window import GbaStatusBar


def _barre(qapp, tmp_path, *acteurs):
    p = Project(tmp_path)
    p.sprites.append(SpriteAsset(name="A", asset="A.png", frame_w=16, frame_h=16))
    p.sprites.append(SpriteAsset(name="B", asset="B.png", frame_w=32, frame_h=32))
    scene = Scene(name="S", actors=list(acteurs))
    p.scenes.items = [scene]
    barre = GbaStatusBar()
    barre.update_scene(scene, p)
    lues = {k: c[0].text() for k, c in barre._counters.items()}
    return {"sprites": lues["oam"], "cycles": lues["cycles"], "tiles": lues["vram"],
            "palettes": lues["objpal"], "affine": lues["affine"], "bg_palettes": lues["bgpal"], "sram": lues["sram"]}


def _acteur(nom, *composants):
    a = Actor(name=nom)
    a.components.extend(composants)
    return a


def test_un_composant_sprite_vide_ne_compte_pas_(qapp, tmp_path):
    vide = _acteur("Vide", SpriteComponent())                         # aucun sprite choisi
    orphelin = _acteur("Orphelin", SpriteComponent(sprite_name="Introuvable"))
    lues = _barre(qapp, tmp_path, vide, orphelin)
    assert lues["sprites"].startswith("0/128") and lues["tiles"].startswith("0/1024")


def test_un_acteur_a_sprite_compte_pour_une_entree(qapp, tmp_path):
    hero = _acteur("Hero", SpriteComponent(sprite_name="A"))
    lues = _barre(qapp, tmp_path, hero, _acteur("Vide", SpriteComponent()))
    assert lues["sprites"].startswith("1/128")


def test_plusieurs_apparences_coutent_une_entree_et_les_tuiles_de_chacune(qapp, tmp_path):
    hero = _acteur("Hero", SpriteComponent(id="a", sprite_name="A", active=True),
                   SpriteComponent(id="b", sprite_name="B", active=False))
    lues = _barre(qapp, tmp_path, hero)
    assert lues["sprites"].startswith("1/128")
    assert lues["tiles"].startswith("20/1024")            # A : 2×2 + B : 4×4, tout résident
    assert lues["cycles"].startswith("16/1210")           # la ligne la plus chargée : A, affiché


def test_un_sprite_introuvable_ne_fait_plus_planter_la_barre(qapp, tmp_path):
    """Avant : `spans.append(... sp.frame_h ...)` lisait `sp` même quand il valait None."""
    _barre(qapp, tmp_path, _acteur("Hero", SpriteComponent(sprite_name="Fantome")))


def _compteurs(barre):
    return {k: c[0].text() for k, c in barre._counters.items()}


def test_les_mesures_du_build_sont_inconnues_avant_un_build(qapp, tmp_path):
    p = Project(tmp_path)
    scene = Scene(name="S")
    p.scenes.items = [scene]
    barre = GbaStatusBar()
    barre.update_scene(scene, p)
    lues = _compteurs(barre)
    assert lues["bgvram"].startswith("?/") and lues["ewram"].startswith("?/")
    assert lues["iwram"].startswith("?/")


def test_les_mesures_du_build_s_affichent_apres_un_build(qapp, tmp_path):
    from codegen.rom_report import RomReport
    p = Project(tmp_path)
    scene = Scene(name="S")
    p.scenes.items = [scene]
    barre = GbaStatusBar()
    barre.set_build_report(RomReport(rom_bytes=1, cartridge_bytes=4 << 20, categories={},
                                     ewram_bytes=2048, iwram_bytes=1024,
                                     bg_vram_blocks={"S": 3}))
    barre.update_scene(scene, p)
    lues = _compteurs(barre)
    assert lues["bgvram"] == "6.0/64 KiB"        # 3 blocs de 2 Kio
    assert lues["ewram"] == "2.0/256 KiB" and lues["iwram"] == "1.0/32 KiB"
    barre.set_build_report(None)                  # autre projet : on oublie la mesure
    assert _compteurs(barre)["ewram"].startswith("?/")


def test_les_matrices_affines_se_comptent_au_dela_de_32(qapp, tmp_path):
    p = Project(tmp_path)
    p.sprites.append(SpriteAsset(name="A", asset="A.png", frame_w=16, frame_h=16))
    acteurs = [_acteur(f"A{i}", SpriteComponent(sprite_name="A", affine_transform=True))
               for i in range(40)]
    lues = _barre(qapp, tmp_path, *acteurs)
    assert lues["sprites"].startswith("40/128")
    assert lues["affine"] == "40/32"          # le compte dépasse le plafond, il ne se tait pas


def test_la_pile_iwram_s_allume_avec_le_remplissage(qapp):
    from ui.common.stack_gauge import StackGauge
    pile = StackGauge()
    assert pile.lit_slabs() == 0                   # inconnu : éteinte
    pile.set_ratio(0.0);  assert pile.lit_slabs() == 0
    pile.set_ratio(0.01); assert pile.lit_slabs() == 1   # une fraction entamée s'allume
    pile.set_ratio(0.43); assert pile.lit_slabs() == 3
    pile.set_ratio(1.0);  assert pile.lit_slabs() == 6


def test_l_infobulle_iwram_nomme_ce_qui_l_occupe(qapp, tmp_path):
    from codegen.rom_report import RomReport
    p = Project(tmp_path)
    scene = Scene(name="S")
    p.scenes.items = [scene]
    barre = GbaStatusBar()
    barre.set_build_report(RomReport(
        rom_bytes=1, cartridge_bytes=4 << 20, categories={}, iwram_bytes=7168,
        iwram_sections={".iwram": 5120, ".bss": 2048}, iwram_top=[("g_big_table", 4096)]))
    barre.update_scene(scene, p)
    tip = barre._counters["iwram"][0].toolTip()
    assert "g_big_table" in tip and "5.0 KiB" in tip and "2.0 KiB" in tip
