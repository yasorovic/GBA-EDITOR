"""v0.25 — le nœud `Interface` (`UILayout`) possède Anchor + Target, et tout son
sous-arbre en hérite. Les champs ont quitté les éléments ; un fichier d'avant
v0.25 (ancrage/cible sur l'élément racine) est remonté au nœud à la lecture."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "editor"))

from core.models.ui_region import (          # noqa: E402
    UILayout, UIText, UIContainer, UIImage,
    ANCHOR_SCREEN, ANCHOR_WORLD, ANCHOR_ACTOR, TARGET_BG, TARGET_OBJ,
)


def test_les_elements_ne_portent_plus_ancrage_ni_cible():
    """Anchor/Target ont quitté les quatre types — ils appartiennent au nœud."""
    for el in (UIText(), UIContainer(), UIImage()):
        assert not hasattr(el, "anchor")
        assert not hasattr(el, "anchor_actor")
        assert "anchor" not in el.to_dict()
    assert not hasattr(UIText(), "target")
    assert "target" not in UIText().to_dict()


def test_la_cible_et_lancrage_sont_lus_sur_le_noeud():
    """`resolved_target`/`effective_anchor` lisent le nœud, pas l'élément — et
    tout enfant partage la même réponse."""
    lay = UILayout(name="hud", anchor=ANCHOR_SCREEN, target=TARGET_OBJ)
    lay.elements += [UIContainer(name="cadre"),
                     UIText(name="ligne", parent="cadre")]
    for el in lay.elements:
        assert lay.resolved_target(el) == TARGET_OBJ
        assert lay.effective_anchor(el) == (ANCHOR_SCREEN, "")


def test_lancrage_actor_impose_obj_sur_le_noeud():
    """`forced_target()` remonté au nœud : un nœud ancré actor est OBJ, quel que
    soit le `target` posé, et l'inspecteur lira la contrainte sur le nœud."""
    lay = UILayout(name="bulle", anchor=ANCHOR_ACTOR, anchor_actor="hero",
                   target=TARGET_BG)
    assert lay.resolved_target() == TARGET_OBJ
    assert lay.effective_anchor() == (ANCHOR_ACTOR, "hero")


def test_un_fichier_davant_v025_remonte_lancrage_de_la_racine():
    """Ancien format : anchor/anchor_actor/target vivaient sur l'élément RACINE.
    À la lecture ils remontent au nœud ; la première racine décide."""
    old = {
        "name": "hud",
        "elements": [
            {"kind": "container", "name": "root", "parent": "",
             "anchor": "world", "anchor_actor": ""},
            {"kind": "text", "name": "ligne", "parent": "root",
             "target": "obj"},          # ignoré : un enfant ne décide pas
        ],
    }
    lay = UILayout.from_dict(old)
    assert lay.anchor == ANCHOR_WORLD
    assert lay.target == ""             # aucune racine ne portait de target
    # Les éléments relus n'ont plus les champs migrés.
    assert not hasattr(lay.get("root"), "anchor")
    assert not hasattr(lay.get("ligne"), "target")


def test_le_target_migre_depuis_la_premiere_racine_qui_en_porte():
    old = {
        "name": "hud",
        "elements": [
            {"kind": "text", "name": "boite", "parent": "",
             "anchor": "screen", "target": "obj"},
        ],
    }
    lay = UILayout.from_dict(old)
    assert lay.anchor == ANCHOR_SCREEN
    assert lay.target == TARGET_OBJ


def test_round_trip_conserve_le_couple_du_noeud():
    lay = UILayout(name="hud", anchor=ANCHOR_ACTOR, anchor_actor="hero",
                   target=TARGET_BG)
    lay.elements.append(UIText(name="ligne"))
    revived = UILayout.from_dict(lay.to_dict())
    assert (revived.anchor, revived.anchor_actor) == (ANCHOR_ACTOR, "hero")
    # `target` sérialisé tel quel (BG est un choix réel, pas un dérivé).
    assert revived.target == TARGET_BG
