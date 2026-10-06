"""La disposition par couches est pure : profondeur de gauche à droite, cycles
et scènes isolées rangés sans se superposer, sans dépendance à Qt."""
from __future__ import annotations

from scripting.scene_graph import SceneGraph, SceneGraphEdge, SceneGraphNode


def _graph(names, edges, start=None):
    nodes = tuple(SceneGraphNode(n, n == start) for n in names)
    es = tuple(SceneGraphEdge(s, t, ()) for s, t in edges)
    return SceneGraph(nodes, es)


def _col(pos, name):
    from ui.scene_manager.scene_graph_layout import MARGIN, COL_STEP
    return round((pos[name][0] - MARGIN) / COL_STEP)


def test_chaine_lineaire_empile_les_couches_vers_la_droite():
    from ui.scene_manager.scene_graph_layout import layout_positions

    pos = layout_positions(_graph(["A", "B", "C"], [("A", "B"), ("B", "C")]))

    assert [_col(pos, n) for n in ("A", "B", "C")] == [0, 1, 2]
    assert pos["A"][1] == pos["B"][1] == pos["C"][1]  # une seule rangée


def test_branche_partage_une_couche_sur_deux_rangees():
    from ui.scene_manager.scene_graph_layout import layout_positions

    pos = layout_positions(_graph(["A", "B", "C"], [("A", "B"), ("A", "C")]))

    assert _col(pos, "A") == 0
    assert _col(pos, "B") == _col(pos, "C") == 1
    assert pos["B"][1] != pos["C"][1]  # pas de chevauchement dans la couche


def test_un_cycle_ne_gonfle_pas_les_couches():
    from ui.scene_manager.scene_graph_layout import layout_positions

    # A → B → A : l'arête retour ne doit pas repousser A d'une couche.
    pos = layout_positions(_graph(["A", "B"], [("A", "B"), ("B", "A")], start="A"))

    assert _col(pos, "A") == 0
    assert _col(pos, "B") == 1


def test_une_scene_isolee_est_rangee_sous_le_bloc_relie():
    from ui.scene_manager.scene_graph_layout import layout_positions

    pos = layout_positions(_graph(["A", "B", "Seule"], [("A", "B")]))

    # Sous le bloc relié (y strictement plus grand), donc sans le chevaucher.
    assert pos["Seule"][1] > pos["A"][1]
    assert pos["Seule"][1] > pos["B"][1]


def test_une_cible_absente_recoit_une_couche_a_droite_de_sa_source():
    from ui.scene_manager.scene_graph_layout import layout_positions

    pos = layout_positions(_graph(["A"], [("A", "Nowhere")]))

    assert "Nowhere" in pos
    assert _col(pos, "Nowhere") == _col(pos, "A") + 1
