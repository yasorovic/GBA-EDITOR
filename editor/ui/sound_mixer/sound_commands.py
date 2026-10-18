"""
ui/sound_mixer/sound_commands.py — Les écritures annulables des trois boîtes.

Même rangement que `data_editor/data_commands.py` : une commande vit à côté de
l'écran qui la déclenche, et `core/history.py` ne porte que le socle et les
commandes génériques.

Ce qui est ici, c'est ce qu'une commande générique ne sait PAS faire : les
gestes COMPOSÉS. Supprimer un état emporte ses arêtes et peut déplacer l'état
de départ ; le renommer réécrit tout ce qui le cite. Un `RemoveListItemCmd`
suivi d'un `SetFieldCmd` demanderait deux Ctrl+Z pour défaire un seul geste — et
laisserait le graphe incohérent entre les deux.

L'ajout d'une TRANSITION ou d'une ACTION, lui, reste générique
(`AddListItemCmd` / `RemoveListItemCmd`) : il ne touche qu'une liste.
"""
from __future__ import annotations

from core.command_dispatcher import get_dispatcher
from core.history import Command
from ui.common.deferred_writes import get_deferred_writes


class MoveMusicNodesCmd(Command):
    """Déplacement de nœuds dans le graphe (glisser souris).

    Au PLURIEL : Qt déplace tous les nœuds sélectionnés ensemble, et un seul
    glisser doit se défaire d'un seul Ctrl+Z. Les commandes consécutives sur
    le MÊME jeu de nœuds fusionnent, sinon un glisser de trois pixels
    laisserait trois entrées.

    Distincte de `MoveActorCmd` à dessein : la fusion ne doit pas confondre un
    glisser d'actor et un glisser de nœud, et l'étiquette est ce que l'auteur
    lit dans Annuler.
    """

    def __init__(self, moves: list, persist_fn=None):
        # moves : [(MusicState, (old_x, old_y), (new_x, new_y))]
        self._moves = list(moves)
        self.label = ("Déplacer le nœud" if len(moves) == 1
                      else f"Déplacer {len(moves)} nœuds")
        self._persist = persist_fn

    def _apply(self, which: int):
        for state, old, new in self._moves:
            state.x, state.y = (old, new)[which]
        if self._persist:
            self._persist()

    def execute(self):
        self._apply(1)

    def undo(self):
        self._apply(0)

    def merge(self, newer: "Command") -> bool:
        if not isinstance(newer, MoveMusicNodesCmd):
            return False
        mine = [id(s) for s, _o, _n in self._moves]
        theirs = [id(s) for s, _o, _n in newer._moves]
        if mine != theirs:
            return False
        self._moves = [(s, old, nxt)
                       for (s, old, _), (_, _, nxt) in zip(self._moves,
                                                           newer._moves)]
        self._persist = newer._persist
        return True


class AddBoxStateCmd(Command):
    """Création d'un état, dans n'importe laquelle des trois boîtes.

    Composée parce que le PREMIER état d'une boîte en devient aussi l'état de
    départ : sans ça, une boîte neuve n'aurait rien à jouer au démarrage.

    Partagée par les trois : ajouter un état, c'est exactement le même geste
    qu'on parle de musique ou d'actions — `states` et `start` sont les mêmes
    champs. La SUPPRESSION, elle, ne l'est pas : seule la MusicBox a des
    arêtes à emporter.
    """

    def __init__(self, box, state, persist_fn=None):
        self._box = box
        self._state = state
        self._took_start = not box.start
        self.label = "Ajouter un état"
        self._persist = persist_fn

    def execute(self):
        if self._state not in self._box.states:
            self._box.states.append(self._state)
        if self._took_start:
            self._box.start = self._state.name
        if self._persist:
            self._persist()

    def undo(self):
        if self._state in self._box.states:
            self._box.states.remove(self._state)
        if self._took_start:
            self._box.start = ""
        if self._persist:
            self._persist()


class RemoveMusicStateCmd(Command):
    """Suppression d'un état musical, de ses arêtes et de son statut de départ.

    Les arêtes qui le citaient n'ont plus de sens : les laisser ferait des
    transitions vers le vide, muettes et invisibles. Elles partent donc avec
    lui — et reviennent avec lui, à leur place d'origine.
    """

    def __init__(self, box, state, persist_fn=None):
        self._box = box
        self._state = state
        self._index = box.states.index(state)
        # Position mémorisée : l'ordre de la liste est celui de l'inspecteur et
        # celui des index émis en C, il doit se restituer à l'identique.
        self._edges = [(i, tr) for i, tr in enumerate(box.transitions)
                       if tr.src == state.name or tr.dst == state.name]
        self._was_start = box.start == state.name
        self.label = f"Supprimer l'état {state.name}"
        self._persist = persist_fn

    def execute(self):
        box = self._box
        if self._state in box.states:
            box.states.remove(self._state)
        for _i, tr in self._edges:
            if tr in box.transitions:
                box.transitions.remove(tr)
        if self._was_start:
            box.start = box.states[0].name if box.states else ""
        if self._persist:
            self._persist()

    def undo(self):
        box = self._box
        box.states.insert(min(self._index, len(box.states)), self._state)
        for i, tr in self._edges:                     # indices croissants
            box.transitions.insert(min(i, len(box.transitions)), tr)
        if self._was_start:
            box.start = self._state.name
        if self._persist:
            self._persist()


class RemoveActionStateCmd(Command):
    """Suppression d'un état d'une SoundBox ou d'une JingleBox.

    Plus simple que son homologue musical : une boîte d'actions n'a pas
    d'arêtes, il n'y a donc rien à emporter avec l'état. Reste le statut de
    départ, qui doit retomber sur un état existant — et revenir à celui-ci
    quand on annule.
    """

    def __init__(self, box, state, persist_fn=None):
        self._box = box
        self._state = state
        self._index = box.states.index(state)
        self._was_start = box.start == state.name
        self.label = f"Supprimer l'état {state.name}"
        self._persist = persist_fn

    def execute(self):
        box = self._box
        if self._state in box.states:
            box.states.remove(self._state)
        if self._was_start:
            box.start = box.states[0].name if box.states else ""
        if self._persist:
            self._persist()

    def undo(self):
        box = self._box
        # À sa PLACE : l'ordre des états est celui des colonnes de la table et
        # celui des index émis en C.
        box.states.insert(min(self._index, len(box.states)), self._state)
        if self._was_start:
            box.start = self._state.name
        if self._persist:
            self._persist()


class SetActionTargetCmd(Command):
    """Une case de la table : vers quoi une action pointe dans cet état.

    Une commande dédiée parce que la cible vit dans un DICTIONNAIRE, pas dans
    un champ : `SetFieldCmd` écrirait l'attribut `mapping` entier. Et une
    action qui ne pointe vers rien est ABSENTE du mapping, pas présente à
    vide — c'est ce qui distingue « ne joue rien ici » de « à remplir ».
    """

    def __init__(self, state, action: str, old: str, new: str, persist_fn=None):
        self._state = state
        self._action = action
        self._old, self._new = old, new
        self.label = f"{action} dans {state.name}"
        self._persist = persist_fn

    def _apply(self, value: str):
        if value:
            self._state.mapping[self._action] = value
        else:
            self._state.mapping.pop(self._action, None)
        if self._persist:
            self._persist()

    def execute(self):
        self._apply(self._new)

    def undo(self):
        self._apply(self._old)

    def merge(self, newer: "Command") -> bool:
        if (isinstance(newer, SetActionTargetCmd)
                and self._state is newer._state
                and self._action == newer._action):
            self._new = newer._new
            self._persist = newer._persist
            return True
        return False


class RenameMusicStateCmd(Command):
    """Renommage d'un état, et de tout ce qui le cite.

    Un état est cité par son NOM dans les arêtes et dans l'état de départ :
    renommer sans réécrire ces citations couperait le graphe en silence.
    """

    def __init__(self, box, state, new_name: str, persist_fn=None):
        self._box = box
        self._state = state
        self._old = state.name
        self._new = new_name
        self.label = f"Renommer {self._old} en {new_name}"
        self._persist = persist_fn

    def _rename(self, old: str, new: str):
        self._state.name = new
        for tr in self._box.transitions:
            if tr.src == old:
                tr.src = new
            if tr.dst == old:
                tr.dst = new
        if self._box.start == old:
            self._box.start = new
        if self._persist:
            self._persist()

    def execute(self):
        self._rename(self._old, self._new)

    def undo(self):
        self._rename(self._new, self._old)


class RenameSoundCmd(Command):
    """Renommage d'un effet, d'une musique ou d'un jingle, et de tout ce qui le cite (scripts, scènes, boîtes, repères).

    Passe par `Project.rename_sound`, qui réécrit les références : défaire renomme dans l'autre sens, avec les mêmes
    réécritures. `refresh_fn(asset)` remet l'écran à jour après chaque sens.
    """

    def __init__(self, project, asset, new_name: str, refresh_fn=None):
        self._project = project
        self._asset = asset
        self._old, self._new = asset.name, new_name
        self.label = f"Renommer {self._old} en {new_name}"
        self._refresh = refresh_fn

    def _rename(self, name: str):
        get_deferred_writes().flush()           # un réglage en attente s'écrit sous l'ancien nom, avant le déménagement
        with get_dispatcher().suspended():
            self._project.rename_sound(self._asset, name)
        if self._refresh:
            self._refresh(self._asset)

    def execute(self):
        self._rename(self._new)

    def undo(self):
        self._rename(self._old)

