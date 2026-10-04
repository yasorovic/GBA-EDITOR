"""ActorInspector — les champs liés par `FieldBinder` reflètent le modèle, et une
édition les y réécrit.

Ces tests couvrent le contrat que l'inspecteur promet à l'utilisateur : ce qu'il
affiche EST l'état de l'acteur sélectionné (jamais celui d'un acteur précédent),
et éditer un champ mute l'acteur. Ils gardent aussi le correctif rotation/scale
(cf. TodoTechnique, Correctifs) : ces trois champs n'étaient jamais repeuplés au
chargement.
"""
from __future__ import annotations

import pytest

from core.models.scene import Actor
from ui.scene_manager.inspectors.actor_inspector import ActorInspector

# Les champs 1:1 confiés au binder, avec deux jeux de valeurs distincts.
_A = dict(x=48, y=96, rotation=90, scale_x=2.0, scale_y=1.5,
          priority=2, obj_mode=2, screen_space=True, visible=False)
_B = dict(x=8, y=8, rotation=0, scale_x=1.0, scale_y=1.0,
          priority=0, obj_mode=0, screen_space=False, visible=True)


def _widget_state(insp: ActorInspector) -> dict:
    return dict(
        x=insp._tx.raw(), y=insp._ty.raw(),
        rotation=insp._trotation.raw(),
        scale_x=insp._tscale_x.raw(), scale_y=insp._tscale_y.raw(),
        priority=insp._tpriority.raw(),
        obj_mode=[0, 2][insp._tobj_mode.currentIndex()],
        screen_space=insp._tscreen.isChecked(),
        visible=insp._tvisible.isChecked(),
    )


def test_load_reflete_le_modele(qapp):
    insp = ActorInspector()
    insp.load(Actor(name="Hero", **_A), project=None, scene=None)
    st = _widget_state(insp)
    for k, v in _A.items():
        assert st[k] == pytest.approx(v), f"{k}: widget {st[k]} != modèle {v}"


def test_changer_dacteur_repeuple_tout(qapp):
    """Le cœur du correctif rotation/scale : après un second `load`, aucun champ
    ne doit garder la valeur du premier acteur."""
    insp = ActorInspector()
    insp.load(Actor(name="Hero", **_A), project=None, scene=None)
    insp.load(Actor(name="Coin", **_B), project=None, scene=None)
    st = _widget_state(insp)
    for k, v in _B.items():
        assert st[k] == pytest.approx(v), f"{k}: widget {st[k]} != modèle {v}"


def test_edition_ecrit_dans_le_modele(qapp):
    insp = ActorInspector()
    a = Actor(name="Hero", **_B)
    insp.load(a, project=None, scene=None)

    insp._tvisible.setChecked(False)
    insp._tpriority._spin.setValue(3)
    insp._trotation._spin.setValue(45)

    assert a.visible is False
    assert a.priority == 3
    assert a.rotation == 45
