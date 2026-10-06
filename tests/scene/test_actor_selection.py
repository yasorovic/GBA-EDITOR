from core.models.scene import Actor
from core.selection_bus import ActorSelection


def test_actor_selection_conserve_lacteur_actif_par_identite():
    """Deux acteurs égaux ne doivent pas se confondre dans une multi-sélection."""
    first = Actor(name="Twin")
    second = Actor(name="Twin")

    selection = ActorSelection([first, second], second)

    assert selection.active is second
