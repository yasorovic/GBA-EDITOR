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
from .exports_parser import parse_exports
from .refactor import LuaRef, iter_refs, non_literal_args_in_text, scene_compiled_scripts


@dataclass(frozen=True)
class SceneGraphNode:
    """Une scène déclarée par le projet, dans son ordre de catalogue.

    `has_dynamic_exit` : la scène contient un ``scene:switch(<calculé>)`` (une
    cible choisie au runtime, dessinée en arête vers un nœud « calculé »), ou un
    script illisible dont on ne sait rien. C'est le fait que le diagnostic traduit
    en « point de vigilance ».
    """

    name: str
    is_start: bool = False
    has_dynamic_exit: bool = False


@dataclass(frozen=True)
class ExportLink:
    """Une sortie portée par un membre posé de la scène (acteur ou Area) : son script appelle
    ``scene:switch(<export>)`` et l'export ``scene_ref`` vaut, sur CETTE instance, le nom de la scène cible (valeur
    réglée dans l'inspecteur, sinon le `default` du script). `owner` est le nom du membre, `owner_kind` dit dans
    quelle liste de la scène le chercher ("actor" ou "area", un acteur et une Area pouvant porter le même nom).
    `ref` est l'appel, pour ouvrir le script à la bonne ligne."""

    owner: str
    owner_kind: str
    export: str
    ref: LuaRef


@dataclass(frozen=True)
class SceneGraphEdge:
    """Des appels allant d'une scène vers une autre.

    Plusieurs appels entre la même paire sont regroupés : ``refs`` conserve
    néanmoins chaque occurrence littérale afin que l'interface puisse afficher le
    compteur et ouvrir le bon script à la bonne ligne. ``links`` porte les sorties
    dont la cible est la valeur d'un export sur une instance : elles se rebranchent
    sur l'instance, jamais dans le texte du script, que toutes les instances partagent.

    `computed` : la cible n'est pas une scène mais une sortie qu'on ne sait pas
    résoudre avant le jeu. `target` est alors le texte de l'expression
    (``levels[i]``) ou le nom de l'export laissé vide ; ses `refs` sont les
    expressions elles-mêmes, qu'un rebranchement remplace par un nom de scène.
    """

    source: str
    target: str
    refs: tuple[LuaRef, ...]
    links: tuple[ExportLink, ...] = ()
    computed: bool = False

    @property
    def count(self) -> int:
        return len(self.refs) + len(self.links)

    @property
    def target_key(self) -> str:
        """Le nœud où l'arête arrive. Une sortie calculée a son nœud À ELLE, propre à sa scène : deux scènes qui
        écrivent `scene:switch(levels[i])` n'ont pas la même sortie."""
        return f"{self.source}::{self.target}" if self.computed else self.target

    def calls(self) -> tuple[LuaRef, ...]:
        """Tous les appels de la transition, littéraux puis exports : ce qu'on ouvre."""
        return self.refs + tuple(link.ref for link in self.links)


@dataclass(frozen=True)
class SceneGraph:
    """Résultat immuable prêt à être dessiné, sans dépendance à Qt."""

    nodes: tuple[SceneGraphNode, ...]
    edges: tuple[SceneGraphEdge, ...]


def scene_graph(project) -> SceneGraph:
    """Construit le graphe connu des appels ``scene.switch`` d'un projet.

    Les scripts d'une scène sont ceux que le build compile pour elle
    (`scene_compiled_scripts`) : le même appel dans un script d'acteur devient donc
    une sortie de la scène où cet acteur s'exécute, et le script d'un prefab ne
    compte que dans les scènes où ce prefab a un modèle (posé, ou spawné par un nom
    littéral). Un argument calculé n'est jamais transformé en fausse
    destination : il mène à un nœud « calculé » qui porte son expression. Un
    script non analysable ne donne aucune arête, seulement `has_dynamic_exit`.
    """
    scenes = tuple(getattr(project, "scenes", ()) or ())
    start = getattr(getattr(project, "settings", None), "start_scene", "")

    grouped: dict[tuple[str, str], list[LuaRef]] = {}
    linked: dict[tuple[str, str], list[ExportLink]] = {}
    computed_refs: dict[tuple[str, str], list[LuaRef]] = {}
    computed_links: dict[tuple[str, str], list[ExportLink]] = {}
    dynamic: set[str] = set()
    for scene in scenes:
        # Plusieurs acteurs peuvent référencer le même fichier ; une occurrence
        # de code doit rester une occurrence de graphe, pas une par utilisateur.
        paths = {path for path in scene_compiled_scripts(project, scene) if path.suffix.lower() == ".lua"}
        export_calls: dict[Path, list[LuaRef]] = {}
        defaults: dict[Path, dict] = {}
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
            defaults[path] = {var["name"]: var["default"] for var in parse_exports(path)
                              if var["type"] == "scene_ref"}
            exported, expressions, unknown = non_literal_args_in_text(
                text, DOMAIN_SCENE, set(defaults[path]), path)
            export_calls[path] = [ref for ref in exported if ref.api_key == "scene.switch"]
            # Une cible calculée (`scene:switch(levels[i])`) mène à son nœud
            # « calculé » ; un script illisible ne mène nulle part. Les deux
            # restent un fait à signaler : la scène a une sortie qu'on ne sait pas
            # résoudre. Même primitive que la réservation VRAM des polices :
            # l'ignorance se propage, elle ne se confond pas avec « aucune
            # sortie ». Un export `scene_ref` jamais réassigné n'est pas calculé :
            # chaque instance posée en donne la valeur, ci-dessous.
            for ref in expressions:
                if ref.api_key == "scene.switch":
                    computed_refs.setdefault((scene.name, ref.value), []).append(ref)
                    dynamic.add(scene.name)
            if unknown:
                dynamic.add(scene.name)

        # Un export prend sa valeur sur l'instance : seuls les membres POSÉS de la scène la portent, acteurs et Areas
        # (le build compile le script d'une Area avec les valeurs de CETTE Area, comme celui d'un acteur posé).
        members = ([("actor", a) for a in getattr(scene, "actors", ()) or ()]
                   + [("area", a) for a in getattr(scene, "areas", ()) or ()])
        for kind, member in members:
            comp = member.get_component("script") if hasattr(member, "get_component") else None
            if not comp or not getattr(comp, "active", True) or not getattr(comp, "script", ""):
                continue
            path = Path(project.asset_abs(comp.script)).resolve()     # résolu, comme `scene_compiled_scripts`
            if path not in export_calls:
                continue
            values = getattr(comp, "exports_values", None) or {}
            for ref in export_calls[path]:
                target = str(values.get(ref.value, defaults[path].get(ref.value, "")) or "")
                link = ExportLink(member.name, kind, ref.value, ref)
                if not target:
                    # Export laissé vide : aucune cible connue. Son nœud « calculé » porte le nom de l'export, et le
                    # rebrancher règle l'instance, comme pour une porte réglée.
                    computed_links.setdefault((scene.name, ref.value), []).append(link)
                    dynamic.add(scene.name)
                    continue
                linked.setdefault((scene.name, target), []).append(link)

    nodes = tuple(
        SceneGraphNode(scene.name, scene.name == start, scene.name in dynamic)
        for scene in scenes)

    def by_place(refs):
        return tuple(sorted(refs, key=lambda ref: (str(ref.path).casefold(), ref.start)))

    edges = tuple(
        SceneGraphEdge(source, target, by_place(grouped.get((source, target), ())),
                       tuple(linked.get((source, target), ())))
        for source, target in dict.fromkeys([*grouped, *linked])
    ) + tuple(
        SceneGraphEdge(source, target, by_place(computed_refs.get((source, target), ())),
                       tuple(computed_links.get((source, target), ())), computed=True)
        for source, target in dict.fromkeys([*computed_refs, *computed_links])
    )
    return SceneGraph(nodes, edges)


# ── Diagnostics de lecture : ce que le graphe sait déjà, gratuitement ──
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
    DYNAMIC = "dynamic"    # cible calculée / script illisible : point de vigilance
    LITERAL = "literal"    # au moins une cible résolue
    NONE = "none"          # aucune sortie : cul-de-sac


@dataclass(frozen=True)
class NodeDiagnostic:
    entry: EntryState
    exit: ExitState


def node_diagnostics(graph: SceneGraph) -> dict[str, NodeDiagnostic]:
    """État d'entrée/sortie de chaque scène, dérivé des seules arêtes et du flag
    `has_dynamic_exit`. Les marqueurs de cible absente ne sont pas des nœuds et
    n'ont pas de diagnostic : leur seule existence EST le signal."""
    names = {node.name for node in graph.nodes}
    incoming = {node.name: False for node in graph.nodes}
    literal_out = {node.name: False for node in graph.nodes}
    broken_out = {node.name: False for node in graph.nodes}
    for edge in graph.edges:
        if edge.computed:
            continue        # ni scène ni nom cassé : `has_dynamic_exit` le porte déjà
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
