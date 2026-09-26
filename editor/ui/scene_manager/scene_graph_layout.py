"""ui/scene_manager/scene_graph_layout.py — disposition par couches, pure.

Pose les nœuds du graphe de gauche à droite, par couches de dépendances : une
scène est à droite de celles qui mènent à elle. C'est de la présentation, pas du
domaine — mais c'est du calcul pur (aucun Qt), donc testable seul et remplaçable
sans toucher au dessin.

Deux règles portées par le plan (ROADMAP v0.12, étape 4) :

- **Les cycles et les retours ne décalent pas les couches.** Les arêtes retour
  sont retirées avant le calcul des profondeurs ; elles resteront dessinées en
  courbe par la vue, mais n'inflígent aucune couche supplémentaire.
- **Les scènes isolées sont rangées à part**, sous le bloc en couches, sans
  chevaucher les nœuds reliés.

Les cibles introuvables (``scene:switch("X")`` sans scène nommée ``X``) sont des
nœuds de placement comme les autres : elles reçoivent une couche à droite de leur
source. La vue les dessine en marqueur d'erreur, mais la disposition les traite
uniformément pour éviter qu'elles se superposent.
"""
from __future__ import annotations

from scripting.scene_graph import SceneGraph
from ui.scene_manager.scene_graph_items import CARD_H, CARD_W

COL_STEP = CARD_W + 60.0
ROW_STEP = CARD_H + 40.0
MARGIN = 20.0
_ISOLATED_GAP = ROW_STEP  # respiration entre le bloc relié et les scènes seules

Positions = dict[str, tuple[float, float]]


def _node_order(graph: SceneGraph) -> list[str]:
    """Tous les nœuds à placer, dans un ordre stable : scènes du catalogue, puis
    cibles introuvables à leur première apparition. Cet ordre — jamais la
    topologie — fixe le rang des nœuds d'une même couche, donc il ne bouge pas
    avec les cycles."""
    order = [node.name for node in graph.nodes]
    seen = set(order)
    for edge in graph.edges:
        if edge.target not in seen:
            order.append(edge.target)
            seen.add(edge.target)
    return order


def _back_edges(order: list[str], succ: dict[str, list[str]]) -> set[tuple[int, str, str]]:
    """Arêtes retour (vers un nœud encore sur la pile DFS) — à ignorer pour la
    profondeur. Repérées par index d'arête pour ne pas confondre deux liens
    parallèles entre la même paire."""
    state: dict[str, int] = {}  # 0 = sur la pile, 1 = terminé
    back: set[tuple[int, str, str]] = set()

    def visit(root: str) -> None:
        stack = [(root, 0)]
        while stack:
            node, i = stack[-1]
            if i == 0:
                state[node] = 0
            if i < len(succ[node]):
                stack[-1] = (node, i + 1)
                idx, target = succ[node][i]
                if state.get(target) == 0:
                    back.add((idx, node, target))
                elif target not in state:
                    stack.append((target, 0))
            else:
                state[node] = 1
                stack.pop()

    for name in order:
        if name not in state:
            visit(name)
    return back


def layout_positions(graph: SceneGraph) -> Positions:
    """Coordonnées (x, y) de chaque scène ET de chaque cible introuvable."""
    order = _node_order(graph)
    rank = {name: i for i, name in enumerate(order)}

    # Successeurs sans les boucles sur soi : une auto-transition n'est pas une
    # dépendance de profondeur. Indexés pour distinguer les arêtes parallèles.
    succ: dict[str, list[tuple[int, str]]] = {name: [] for name in order}
    for idx, edge in enumerate(graph.edges):
        if edge.source != edge.target:
            succ[edge.source].append((idx, edge.target))

    back = _back_edges(order, succ)
    forward = [(u, v) for u in order for (idx, v) in succ[u]
               if (idx, u, v) not in back]

    # Profondeur = plus long chemin dans le DAG (sans arêtes retour). Le DAG
    # garantit la convergence ; on relâche jusqu'à stabilité.
    layer = {name: 0 for name in order}
    for _ in range(len(order)):
        changed = False
        for u, v in forward:
            if layer[v] < layer[u] + 1:
                layer[v] = layer[u] + 1
                changed = True
        if not changed:
            break

    incident = {name for u, v in forward for name in (u, v)}
    linked = [name for name in order if name in incident]
    isolated = [name for name in order if name not in incident]

    # Nœuds reliés : colonne = couche, rang dans la couche = ordre de catalogue.
    columns: dict[int, list[str]] = {}
    for name in sorted(linked, key=lambda n: (layer[n], rank[n])):
        columns.setdefault(layer[name], []).append(name)

    positions: Positions = {}
    max_rows = 0
    for col, names in columns.items():
        max_rows = max(max_rows, len(names))
        for row, name in enumerate(names):
            positions[name] = (MARGIN + col * COL_STEP, MARGIN + row * ROW_STEP)

    # Scènes isolées : une rangée sous le bloc relié, sans chevauchement.
    base_y = MARGIN + max_rows * ROW_STEP + _ISOLATED_GAP if linked else MARGIN
    for i, name in enumerate(isolated):
        positions[name] = (MARGIN + i * COL_STEP, base_y)

    return positions
