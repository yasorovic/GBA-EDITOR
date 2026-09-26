"""Projection pure du graphe des scènes.

Le graphe ne constitue pas un modèle à enregistrer : il est reconstruit à
partir des appels ``scene:switch("…")`` qui figurent dans les scripts.  Cette
frontière permet à la vue Qt de rester un simple rendu et de conserver, pour
chaque arête, l'emplacement précis à ouvrir ou à réécrire.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path

from .api import DOMAIN_SCENE
from .refactor import LuaRef, domain_args_in_text, iter_refs


@dataclass(frozen=True)
class SceneGraphNode:
    """Une scène déclarée par le projet, dans son ordre de catalogue.

    `has_dynamic_exit` retient ce que les arêtes ne peuvent pas dire : la scène
    contient un ``scene:switch(<calculé>)`` — une cible choisie au runtime, ou un
    script illisible dont on ne sait rien. C'est le fait que le diagnostic traduit
    en « point de vigilance » ; il ne devient jamais une fausse arête.
    """

    name: str
    is_start: bool = False
    has_dynamic_exit: bool = False


@dataclass(frozen=True)
class SceneGraphEdge:
    """Des appels littéraux allant d'une scène vers une autre.

    Plusieurs appels entre la même paire sont regroupés : ``refs`` conserve
    néanmoins chaque occurrence afin que l'interface puisse afficher le
    compteur et ouvrir le bon script à la bonne ligne.
    """

    source: str
    target: str
    refs: tuple[LuaRef, ...]


@dataclass(frozen=True)
class SceneGraph:
    """Résultat immuable prêt à être dessiné, sans dépendance à Qt."""

    nodes: tuple[SceneGraphNode, ...]
    edges: tuple[SceneGraphEdge, ...]


def scene_graph(project) -> SceneGraph:
    """Construit le graphe connu des appels ``scene.switch`` d'un projet.

    Les scripts sont associés à leur scène par ``Project.scene_scripts`` : le
    même appel dans un script d'acteur devient donc une sortie de la scène où
    cet acteur s'exécute. Les scripts non analysables et les arguments calculés
    ne sont volontairement pas transformés en fausses destinations ; ils
    restent la responsabilité du Script Editor jusqu'à la future représentation
    explicite des cibles indéterminées.
    """
    scenes = tuple(getattr(project, "scenes", ()) or ())
    start = getattr(getattr(project, "settings", None), "start_scene", "")

    grouped: dict[tuple[str, str], list[LuaRef]] = {}
    dynamic: set[str] = set()
    for scene in scenes:
        # Plusieurs acteurs peuvent référencer le même fichier ; une occurrence
        # de code doit rester une occurrence de graphe, pas une par utilisateur.
        paths: set[Path] = set()
        if hasattr(project, "scene_scripts"):
            scripts, _opaque = project.scene_scripts(scene)
            paths.update(Path(path) for path in scripts)
        for path in sorted(paths, key=lambda p: str(p).casefold()):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for ref in iter_refs(text, path=path, domain=DOMAIN_SCENE):
                # Le domaine seul peut un jour porter plusieurs appels. Le
                # graphe de scènes représente strictement cette transition.
                if ref.api_key != "scene.switch":
                    continue
                grouped.setdefault((scene.name, ref.value), []).append(ref)
            # Une cible calculée (`scene:switch(var)`) ou un script illisible ne
            # produit aucune arête, mais reste un fait à signaler : la scène a une
            # sortie qu'on ne sait pas résoudre. Même primitive que la réservation
            # VRAM des polices — l'ignorance se propage, elle ne se confond pas
            # avec « aucune sortie ».
            if domain_args_in_text(text, DOMAIN_SCENE)[1]:
                dynamic.add(scene.name)

    nodes = tuple(
        SceneGraphNode(scene.name, scene.name == start, scene.name in dynamic)
        for scene in scenes)

    edges = tuple(
        SceneGraphEdge(source, target, tuple(sorted(
            refs, key=lambda ref: (str(ref.path).casefold(), ref.start))))
        for (source, target), refs in grouped.items()
    )
    return SceneGraph(nodes, edges)


# ── Diagnostics de lecture — ce que le graphe sait déjà, gratuitement ──
#
# Purement dérivé de la projection : aucune écriture, aucun accès script. Nomme
# les FAITS (atteignable, cul-de-sac, cible calculée, cible cassée) ; la couleur
# qui les rend lisibles est de la présentation et vit dans la vue.


class EntryState(enum.Enum):
    """Le nœud reçoit-il un lien ? La scène de départ compte comme atteignable
    (le jeu y démarre), même sans arête entrante."""

    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"


class ExitState(enum.Enum):
    """Où pointe le nœud, par ordre de vigilance décroissante quand plusieurs
    cas coexistent : une cible cassée prime sur une cible calculée, qui prime sur
    une cible résolue, qui prime sur l'absence de sortie."""

    BROKEN = "broken"      # cite un nom qu'aucune scène ne porte
    DYNAMIC = "dynamic"    # cible calculée / script illisible — point de vigilance
    LITERAL = "literal"    # au moins une cible résolue
    NONE = "none"          # aucune sortie — cul-de-sac


@dataclass(frozen=True)
class NodeDiagnostic:
    entry: EntryState
    exit: ExitState


def node_diagnostics(graph: SceneGraph) -> dict[str, NodeDiagnostic]:
    """État d'entrée/sortie de chaque scène, dérivé des seules arêtes et du flag
    `has_dynamic_exit`. Les marqueurs de cible absente ne sont pas des nœuds et
    n'ont pas de diagnostic — leur seule existence EST le signal."""
    names = {node.name for node in graph.nodes}
    incoming = {node.name: False for node in graph.nodes}
    literal_out = {node.name: False for node in graph.nodes}
    broken_out = {node.name: False for node in graph.nodes}
    for edge in graph.edges:
        if edge.source in names:
            if edge.target in names:
                literal_out[edge.source] = True
            else:
                broken_out[edge.source] = True
        if edge.target in names:
            incoming[edge.target] = True

    out: dict[str, NodeDiagnostic] = {}
    for node in graph.nodes:
        entry = (EntryState.REACHABLE
                 if node.is_start or incoming[node.name]
                 else EntryState.UNREACHABLE)
        if broken_out[node.name]:
            exit_ = ExitState.BROKEN
        elif node.has_dynamic_exit:
            exit_ = ExitState.DYNAMIC
        elif literal_out[node.name]:
            exit_ = ExitState.LITERAL
        else:
            exit_ = ExitState.NONE
        out[node.name] = NodeDiagnostic(entry, exit_)
    return out
