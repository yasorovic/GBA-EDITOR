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
    lues = [lbl.text() for lbl, _limit, _warn in barre._counters]
    return dict(zip(("sprites", "cycles", "tiles", "palettes"), lues))


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
