"""UIInspector ↔ historique — le round-trip édition → undo/redo d'une zone (ARCHI A1).

Même invariant que `test_actor_inspector_undo`, sur l'autre inspecteur qui édite
par champs 1:1 : une géométrie modifiée passe par `_set` → `SetFieldCmd` →
`CommandHistory`, l'undo restaure le modèle ET l'inspecteur le reflète après
`load`, un no-op ne pousse rien, une salve sur le même champ fusionne en une
entrée. C'est ce que promet « l'inspecteur reflète la réalité du modèle » pour
les éléments d'interface — un objet PARTAGÉ par N scènes, donc d'autant plus
sensible à une pile d'annulation qui mentirait.
"""
from __future__ import annotations

import pytest

from core.history import get_history
from core.models.ui_region import UILayout, UIText
from ui.scene_manager.inspectors.ui_inspector import UIInspector


@pytest.fixture
def history():
    h = get_history()
    h.clear()
    yield h
    h.clear()


def _loaded():
    """Un `UIInspector` chargé sur une zone de texte d'une mise en page minimale.
    Retourne (inspecteur, élément)."""
    lay = UILayout(name="HUD")
    el = UIText(name="Score", x=0, y=0, w=32, h=8)
    lay.elements.append(el)
    insp = UIInspector()
    insp.load(lay, el, project=None, scene=None)
    return insp, el, lay


def test_une_edition_de_geometrie_cree_une_entree(qapp, history):
    insp, el, _ = _loaded()

    insp._sp["x"].setValue(64)

    assert el.x == 64
    assert history.can_undo
    assert history.undo_label == "Geometry"


def test_undo_restaure_et_linspecteur_le_reflete(qapp, history):
    insp, el, lay = _loaded()

    insp._sp["x"].setValue(64)
    insp._sp["y"].setValue(24)          # champ DIFFÉRENT → 2e entrée
    assert (el.x, el.y) == (64, 24)

    history.undo()                       # défait y
    assert (el.x, el.y) == (64, 0)
    history.undo()                       # défait x
    assert (el.x, el.y) == (0, 0)

    insp.load(lay, el, project=None, scene=None)
    assert insp._sp["x"].value() == 0
    assert insp._sp["y"].value() == 0


def test_redo_rejoue(qapp, history):
    insp, el, _ = _loaded()

    insp._sp["w"].setValue(64)
    history.undo()
    assert el.w == 32
    assert history.can_redo

    history.redo()
    assert el.w == 64


def test_un_no_op_ne_cree_aucune_commande(qapp, history):
    insp, el, _ = _loaded()

    insp._set("x", el.x, "Geometry")     # déjà 0

    assert not history.can_undo


def test_frappes_fusionnees_une_seule_entree(qapp, history):
    """Tirer un réglage de taille est UN geste : la salve fusionne, un seul undo
    revient à l'origine (`SetFieldCmd.merge`, même champ + même élément)."""
    insp, el, _ = _loaded()

    insp._sp["w"].setValue(48)
    insp._sp["w"].setValue(96)
    insp._sp["w"].setValue(128)
    assert el.w == 128

    history.undo()
    assert el.w == 32                    # l'origine, pas 96 ni 48
    assert not history.can_undo
