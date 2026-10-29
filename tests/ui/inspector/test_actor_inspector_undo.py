"""ActorInspector ↔ historique — le round-trip complet édition → undo/redo (ARCHI A1).

`test_actor_inspector_binding` couvre le sens descendant (le widget écrit le
modèle). Ici on ferme la boucle que la revue a désignée comme « déjà solide mais
sans test » : une édition passe par `_set` → `SetFieldCmd` → `CommandHistory`, et
l'inspecteur reflète le modèle APRÈS un undo/redo. On garde aussi les deux
invariants fins de `_set` — pas de commande sur un no-op, une SEULE sur des
frappes fusionnées — dont dépend la lisibilité de la pile d'annulation.

Ces invariants sont le socle de « l'inspecteur reflète la réalité du modèle » :
une régression du chemin `_set`/merge/undo y atterrirait en silence, exactement
le risque que A1 cible.
"""
from __future__ import annotations

import pytest

from core.history import get_history
from core.models.scene import Actor
from ui.scene_manager.inspectors.actor_inspector import ActorInspector


@pytest.fixture
def history():
    """L'historique est un singleton global — on l'isole entre les tests."""
    h = get_history()
    h.clear()
    yield h
    h.clear()


def _loaded(actor: Actor) -> ActorInspector:
    insp = ActorInspector()
    insp.load(actor, project=None, scene=None)
    return insp


def test_une_edition_cree_une_entree_annulable(qapp, history):
    a = Actor(name="Hero", priority=0)
    insp = _loaded(a)

    insp._tpriority._spin.setValue(3)

    assert a.priority == 3
    assert history.can_undo
    assert history.undo_label == "Hero.priority"


def test_undo_restaure_le_modele_et_linspecteur_le_reflete(qapp, history):
    """Le cœur de A1 : après undo, le modèle revient à l'ancienne valeur ET un
    `load()` la fait remonter dans le widget (l'inspecteur ne ment pas)."""
    a = Actor(name="Hero", priority=0, rotation=0)
    insp = _loaded(a)

    insp._tpriority._spin.setValue(3)
    insp._trotation._spin.setValue(45)      # champ DIFFÉRENT → 2e entrée, pas de fusion
    assert (a.priority, a.rotation) == (3, 45)

    history.undo()                    # défait la rotation
    assert (a.priority, a.rotation) == (3, 0)
    history.undo()                    # défait la priorité
    assert (a.priority, a.rotation) == (0, 0)

    insp.load(a, project=None, scene=None)
    assert insp._tpriority.raw() == 0
    assert insp._trotation.raw() == 0


def test_redo_rejoue(qapp, history):
    a = Actor(name="Hero", priority=0)
    insp = _loaded(a)

    insp._tpriority._spin.setValue(2)
    history.undo()
    assert a.priority == 0
    assert history.can_redo

    history.redo()
    assert a.priority == 2


def test_un_no_op_ne_cree_aucune_commande(qapp, history):
    """`_set` sur la valeur COURANTE ne pousse rien : la pile d'annulation ne se
    remplit pas de gestes qui ne changent rien (cf. `_set`, `if old == value`)."""
    a = Actor(name="Hero", priority=2)
    insp = _loaded(a)

    insp._set("priority", 2)          # déjà 2

    assert not history.can_undo
    assert a.priority == 2


def test_frappes_fusionnees_une_seule_entree(qapp, history):
    """Deux éditions consécutives du MÊME champ fusionnent (`SetFieldCmd.merge`) :
    un seul undo, qui restaure la valeur d'ORIGINE, pas l'intermédiaire — tirer
    sur un réglage est UN geste, pas dix entrées d'historique."""
    a = Actor(name="Hero", priority=0)
    insp = _loaded(a)

    insp._tpriority._spin.setValue(1)
    insp._tpriority._spin.setValue(2)
    insp._tpriority._spin.setValue(3)
    assert a.priority == 3

    history.undo()
    assert a.priority == 0            # l'origine, pas 2 ni 1
    assert not history.can_undo       # une seule entrée fusionnée
