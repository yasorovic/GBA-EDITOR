"""La vue Graphe projette à l'affichage et ne re-parse qu'au changement."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _dispose_graph_views(qapp):
    """Détruit les `SceneGraphView` créées par un test avant le suivant.

    Les tests instancient des vues sans parent et sans les fermer ; sans boucle
    d'événements (contrairement à l'app réelle, qui n'a qu'une vue durable), les
    QGraphicsScene/QWidget s'accumulent et finissent par corrompre l'arbre Qt à
    un GC ultérieur (violation d'accès Windows). On les supprime déterministe-
    ment après chaque test."""
    from PyQt6 import sip
    from PyQt6.QtWidgets import QApplication
    yield
    from ui.scene_manager.scene_graph_view import SceneGraphView
    for w in list(QApplication.allWidgets()):
        if isinstance(w, SceneGraphView) and not sip.isdeleted(w):
            sip.delete(w)


def _project(tmp_path):
    from core.project import Project
    from core.models.scene import Scene

    project = Project(tmp_path / "jeu")
    scripts = project.root / "assets" / "scripts" / "scenes"
    scripts.mkdir(parents=True)
    for name in ("Title", "Arena"):
        project.scenes.append(Scene(name=name))
    project.settings.start_scene = "Title"
    source = scripts / "title.lua"
    source.write_text('scene:switch("Arena")\n', encoding="utf-8")
    project.scenes[0].script = "assets/scripts/scenes/title.lua"
    return project, source


def test_refresh_projette_le_graphe_du_projet(qapp, tmp_path):
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _source = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    assert view.graph is None  # rien n'est projeté avant l'affichage

    view.refresh()

    assert [node.name for node in view.graph.nodes] == ["Title", "Arena"]
    assert [(e.source, e.target) for e in view.graph.edges] == [("Title", "Arena")]


def test_les_cartes_portent_les_ports_de_diagnostic(qapp, tmp_path):
    """Chaque carte rendue expose un port d'entrée et un port de sortie, colorés
    selon le diagnostic dérivé : Title (départ) sort en littéral vers Arena, qui
    est atteignable mais cul-de-sac."""
    from scripting.scene_graph import EntryState, ExitState
    from ui.scene_manager.scene_graph_items import NodePortItem, SceneCardItem
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()

    cards = {i.name: i for i in view._scene.items() if isinstance(i, SceneCardItem)}
    for card in cards.values():
        ports = [c for c in card.childItems() if isinstance(c, NodePortItem)]
        assert len(ports) == 2  # une entrée, une sortie
    assert cards["Title"].diagnostic.entry is EntryState.REACHABLE
    assert cards["Title"].diagnostic.exit is ExitState.LITERAL
    assert cards["Arena"].diagnostic.entry is EntryState.REACHABLE
    assert cards["Arena"].diagnostic.exit is ExitState.NONE


def test_definir_la_scene_de_depart_depuis_le_graphe(qapp, tmp_path):
    """Le clic-droit « Définir comme scène de départ » réécrit
    `settings.start_scene` (annulable) et re-projette : le nouveau nœud devient le
    départ, son entrée passe atteignable ; Ctrl+Z restaure l'ancien."""
    from core.history import get_history
    from scripting.scene_graph import EntryState
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)   # départ = Title
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()

    view._set_start_scene("Arena")
    assert project.settings.start_scene == "Arena"
    assert {n.name: n.is_start for n in view.graph.nodes}["Arena"] is True
    # Arena n'a aucune arête entrante : c'est le statut de départ qui la rend
    # atteignable au diagnostic.
    from scripting.scene_graph import node_diagnostics
    assert node_diagnostics(view.graph)["Arena"].entry is EntryState.REACHABLE

    get_history().undo()
    assert project.settings.start_scene == "Title"
    assert {n.name: n.is_start for n in view.graph.nodes}["Title"] is True


def test_une_scene_ajoutee_apparait_au_refresh(qapp, tmp_path):
    """Bug : le graphe n'apprenait une scène créée qu'au ré-affichage. Un refresh
    (déclenché en direct par la fenêtre sur `project_tree_changed`) suffit."""
    from core.models.scene import Scene
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()
    assert "Newbie" not in {n.name for n in view.graph.nodes}

    project.scenes.append(Scene(name="Newbie"))
    view.refresh()

    assert "Newbie" in {n.name for n in view.graph.nodes}


def test_refresh_est_memoise_sur_empreinte_constante(qapp, tmp_path):
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _source = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)

    view.refresh()
    first = view.graph
    view.refresh()

    # Même empreinte : aucun re-parse, on réutilise l'objet précédent.
    assert view.graph is first


def test_une_edition_de_script_force_une_reprojection(qapp, tmp_path):
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, source = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()
    before = view.graph

    # Le mtime en nanosecondes suffit à distinguer l'empreinte ; on l'assure.
    import os
    st = os.stat(source)
    source.write_text('scene:switch("Title")\n', encoding="utf-8")
    os.utime(source, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))

    view.refresh()

    assert view.graph is not before
    assert [(e.source, e.target) for e in view.graph.edges] == [("Title", "Title")]


def _counts(view):
    from ui.scene_manager.scene_graph_items import (
        MissingTargetItem, SceneCardItem, SceneGraphEdgeItem)
    items = view._scene.items()
    return (
        [i for i in items if isinstance(i, SceneCardItem)],
        [i for i in items if isinstance(i, MissingTargetItem)],
        [i for i in items if isinstance(i, SceneGraphEdgeItem)],
    )


def test_rendu_vide_ne_dessine_rien(qapp, tmp_path):
    from core.project import Project
    from ui.scene_manager.scene_graph_view import SceneGraphView

    view = SceneGraphView()
    view.set_project(Project(tmp_path / "vide"))
    view.refresh()

    cards, missing, edges = _counts(view)
    assert (cards, missing, edges) == ([], [], [])


def test_rendu_simple_une_carte_marquee_et_une_arete(qapp, tmp_path):
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()

    cards, missing, edges = _counts(view)
    assert {c.name for c in cards} == {"Title", "Arena"}
    assert [c.name for c in cards if c.is_start] == ["Title"]
    assert missing == []
    assert len(edges) == 1 and edges[0].count == 1


def test_rendu_agrege_porte_le_compteur(qapp, tmp_path):
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, source = _project(tmp_path)
    source.write_text('scene:switch("Arena")\nscene:switch("Arena")\n', encoding="utf-8")
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()

    _cards, _missing, edges = _counts(view)
    assert len(edges) == 1 and edges[0].count == 2


def test_arete_s_ancre_aux_ports_des_cartes(qapp, tmp_path):
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()

    edge = _edge(view)
    source, target = _card(view, "Title").anchor_rect(), _card(view, "Arena").anchor_rect()
    first = edge._path.elementAt(0)
    last = edge._path.elementAt(edge._path.elementCount() - 1)
    assert (first.x, first.y) == (source.right(), source.center().y())
    assert (last.x, last.y) == (target.left(), target.center().y())


def test_rendu_cible_absente_donne_un_marqueur_pas_une_carte(qapp, tmp_path):
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, source = _project(tmp_path)
    source.write_text('scene:switch("Nowhere")\n', encoding="utf-8")
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()

    cards, missing, edges = _counts(view)
    assert {c.name for c in cards} == {"Title", "Arena"}  # jamais de fausse scène
    assert [m.name for m in missing] == ["Nowhere"]
    assert len(edges) == 1


def _card(view, name):
    from ui.scene_manager.scene_graph_items import SceneCardItem
    return next(i for i in view._scene.items()
               if isinstance(i, SceneCardItem) and i.name == name)


def _edge(view):
    from ui.scene_manager.scene_graph_items import SceneGraphEdgeItem
    return next(i for i in view._scene.items() if isinstance(i, SceneGraphEdgeItem))


def test_clic_sur_une_scene_la_selectionne_via_le_bus(qapp, tmp_path):
    from core.selection_bus import get_bus
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()
    get_bus().clear()

    view._view.clicked.emit(_card(view, "Title"))

    assert get_bus().current is project.scenes[0]


def test_double_clic_sur_une_scene_demande_son_ouverture(qapp, tmp_path):
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()
    seen = []
    view.scene_opened.connect(seen.append)

    view._view.double_clicked.emit(_card(view, "Arena"))

    assert seen == ["Arena"]


def test_clic_sur_une_arete_expose_ses_appels(qapp, tmp_path):
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()
    got = []
    view.edge_selected.connect(got.append)

    view._view.clicked.emit(_edge(view))

    assert got and [(edge.source, edge.target) for edge in got[0]] == [("Title", "Arena")]


def test_clic_droit_sur_arete_bascule_son_trace(qapp, tmp_path):
    from core.scene_graph_state import SceneGraphState
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()
    edge = _edge(view)

    view._toggle_edge_style(edge)
    assert edge.style == "curve" and edge.isSelected()
    assert SceneGraphState(project.root).edge_style("Title", "Arena") == "curve"

    view._toggle_edge_style(edge)
    assert edge.style == "straight"


def test_double_clic_sur_une_arete_ouvre_a_la_ligne_de_lappel(qapp, tmp_path):
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, source = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()
    got = []
    view.edge_opened.connect(got.append)

    view._view.double_clicked.emit(_edge(view))

    assert got and got[0].refs[0].line == 1 and got[0].refs[0].path == source


def test_seed_auto_est_materialise_dans_le_sidecar(qapp, tmp_path):
    from core.scene_graph_state import SceneGraphState
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()

    # Dès le premier rendu, chaque scène a une position stockée (graine auto).
    stored = SceneGraphState(project.root)
    assert set(stored.positions()) == {"Title", "Arena"}


def test_deplacer_un_noeud_persiste_sa_position(qapp, tmp_path):
    from core.scene_graph_state import SceneGraphState
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()

    _card(view, "Arena").setPos(500, 300)
    view._view.drag_finished.emit()

    assert SceneGraphState(project.root).scene_position("Arena") == (500.0, 300.0)


def test_rearrange_ecrase_les_positions_manuelles(qapp, tmp_path):
    from core.scene_graph_state import SceneGraphState
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()
    _card(view, "Arena").setPos(999, 999)
    view._view.drag_finished.emit()

    view._rearrange()

    # Re-arrange remet chaque nœud à sa place auto (jamais l'ancienne manuelle).
    assert SceneGraphState(project.root).scene_position("Arena") != (999.0, 999.0)


def test_zoom_molette_reste_borne(qapp, tmp_path):
    from ui.scene_manager import scene_graph_view as mod
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()

    class _Wheel:
        def __init__(self, dy):
            self._dy = dy

        def angleDelta(self):
            class _D:
                y = lambda _self, v=self._dy: v
            return _D()

    for _ in range(50):
        view._view.wheelEvent(_Wheel(120))
    assert view._view._zoom <= mod._MAX_ZOOM
    for _ in range(100):
        view._view.wheelEvent(_Wheel(-120))
    assert view._view._zoom >= mod._MIN_ZOOM


def test_le_marqueur_de_cible_absente_est_inerte(qapp, tmp_path):
    from core.selection_bus import get_bus
    from ui.scene_manager.scene_graph_items import MissingTargetItem
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, source = _project(tmp_path)
    source.write_text('scene:switch("Nowhere")\n', encoding="utf-8")
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()
    get_bus().clear()
    seen = []
    view.scene_opened.connect(seen.append)
    marker = next(i for i in view._scene.items() if isinstance(i, MissingTargetItem))

    view._view.clicked.emit(marker)
    view._view.double_clicked.emit(marker)

    assert get_bus().current is None and seen == []


# ── Groupes (tranche 3c) : boîtes repliables lues du store partagé ──────

def _grouped_view(tmp_path, collapsed: bool):
    """Vue avec Arena rangée dans un groupe, replié ou déplié."""
    from core.asset_folder_store import AssetFolderStore
    from core.scene_graph_state import SceneGraphState
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    state = SceneGraphState(project.root)
    folders = AssetFolderStore(project.root)
    group = folders.create_folder("scenes", "World")
    folders.move_member("scenes", "Arena", group.id)
    state.set_group_collapsed(group.id, collapsed)

    view = SceneGraphView()
    view.set_project(project, state, folders)
    view.refresh()
    return view, group


def _boxes(view):
    from ui.scene_manager.scene_graph_group_items import SceneGroupBoxItem
    return [i for i in view._scene.items() if isinstance(i, SceneGroupBoxItem)]


def test_groupe_replie_cache_ses_scenes_et_montre_une_boite(qapp, tmp_path):
    view, group = _grouped_view(tmp_path, collapsed=True)

    cards, _missing, edges = _counts(view)
    # Arena est cachée dans la boîte ; Title (hors groupe) reste visible.
    assert {c.name for c in cards} == {"Title"}
    boxes = _boxes(view)
    assert len(boxes) == 1 and boxes[0].collapsed and boxes[0].group_id == group.id
    # L'arête Title→Arena subsiste, raccordée à la boîte.
    assert len(edges) == 1


def test_groupe_deplie_montre_ses_scenes_et_un_cadre(qapp, tmp_path):
    view, _group = _grouped_view(tmp_path, collapsed=False)

    cards, _missing, edges = _counts(view)
    assert {c.name for c in cards} == {"Title", "Arena"}
    boxes = _boxes(view)
    assert len(boxes) == 1 and not boxes[0].collapsed
    assert len(edges) == 1


def test_le_chevron_bascule_le_repli(qapp, tmp_path):
    from ui.scene_manager.scene_graph_group_items import GroupToggleItem

    view, group = _grouped_view(tmp_path, collapsed=True)
    toggle = next(i for i in view._scene.items() if isinstance(i, GroupToggleItem))

    view._view.clicked.emit(toggle)

    # Déplié : la scène membre réapparaît, l'état est persisté.
    assert "Arena" in view._cards
    assert view._state.group_collapsed(group.id) is False


def test_deplacer_une_boite_repliee_persiste_sa_position(qapp, tmp_path):
    view, group = _grouped_view(tmp_path, collapsed=True)
    box = _boxes(view)[0]

    box.setPos(400, 250)
    view._view.drag_finished.emit()

    assert view._state.group_box_position(group.id) == (400.0, 250.0)


def _two_groups_view(tmp_path):
    """Deux groupes racine repliés (World, Inner), l'un loin de l'autre — de quoi
    glisser Inner DANS World."""
    from core.asset_folder_store import AssetFolderStore
    from core.scene_graph_state import SceneGraphState
    from ui.scene_manager.scene_graph_view import SceneGraphView
    from ui.scene_manager.scene_graph_group_items import COLLAPSED_W, COLLAPSED_H

    project, _ = _project(tmp_path)
    state = SceneGraphState(project.root)
    folders = AssetFolderStore(project.root)
    world = folders.create_folder("scenes", "World")
    inner = folders.create_folder("scenes", "Inner")
    folders.move_member("scenes", "Arena", world.id)
    folders.move_member("scenes", "Title", inner.id)
    state.set_group_collapsed(world.id, True)
    state.set_group_collapsed(inner.id, True)
    view = SceneGraphView()
    view.set_project(project, state, folders)
    view.refresh()
    # Écarter les deux boîtes, puis re-render pour les reposer.
    state.set_group_box_position(world.id, 0.0, 0.0)
    state.set_group_box_position(inner.id, 600.0, 0.0)
    view._render(view._graph)
    return view, folders, world, inner, (COLLAPSED_W, COLLAPSED_H)


def test_glisser_un_groupe_dans_un_autre_l_imbrique(qapp, tmp_path):
    """Le geste « déplacer dans un groupe » vaut aussi pour les nœuds GROUPE :
    glisser la boîte d'Inner sur celle de World l'y imbrique (parent_id), et le
    project viewer partage le store (`groups_changed`)."""
    view, folders, world, inner, (cw, ch) = _two_groups_view(tmp_path)
    changed = []
    view.groups_changed.connect(lambda: changed.append(True))

    view._boxes[inner.id].setPos(0.0, 0.0)   # pile sur World
    view._view.drag_finished.emit()

    nested = next(f for f in folders.folders("scenes") if f.id == inner.id)
    assert nested.parent_id == world.id
    assert changed == [True]


def _nested_view(tmp_path):
    """World (racine, déplié) contient le sous-groupe Inner (replié) ; Arena est
    dans Inner, Title à la racine. Le cadre de World doit montrer Inner dedans."""
    from core.project import Project
    from core.models.scene import Scene
    from core.asset_folder_store import AssetFolderStore
    from core.scene_graph_state import SceneGraphState
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project = Project(tmp_path / "jeu")
    (project.root / "assets" / "scripts" / "scenes").mkdir(parents=True)
    for name in ("Title", "Arena"):
        project.scenes.append(Scene(name=name))
    project.settings.start_scene = "Title"
    folders = AssetFolderStore(project.root)
    world = folders.create_folder("scenes", "World")
    inner = folders.create_folder("scenes", "Inner", world.id)
    folders.move_member("scenes", "Arena", inner.id)
    state = SceneGraphState(project.root)
    state.set_group_collapsed(world.id, False)   # World déplié
    state.set_group_collapsed(inner.id, True)    # Inner replié
    view = SceneGraphView()
    view.set_project(project, state, folders)
    view.refresh()
    return view, folders, world, inner


def test_un_cadre_deplie_montre_ses_sous_groupes_dedans(qapp, tmp_path):
    """Rendu récursif : World déplié dessine Inner (son sous-groupe) comme une
    boîte, et Arena (dans Inner replié) est cachée sous cette boîte, pas une carte
    perdue au niveau racine."""
    view, _folders, world, inner = _nested_view(tmp_path)

    assert world.id in view._frames        # World = cadre déplié
    assert inner.id in view._boxes         # Inner = boîte, DANS le cadre de World
    assert "Arena" not in view._cards      # Arena cachée dans Inner
    assert "Title" in view._cards          # Title reste une carte racine


def test_sortir_un_sous_groupe_par_glisser_le_remonte(qapp, tmp_path):
    """Le sous-groupe Inner, visible comme boîte dans le cadre de World, glissé
    HORS de ce cadre remonte à la racine (parent_id → None) — le « sortir » par
    glisser, symétrique de l'imbrication."""
    view, folders, world, inner = _nested_view(tmp_path)

    view._boxes[inner.id].setPos(5000.0, 5000.0)   # loin, hors du cadre de World
    view._view.drag_finished.emit()

    out = next(f for f in folders.folders("scenes") if f.id == inner.id)
    assert out.parent_id is None


def test_glisser_un_groupe_hors_de_tout_le_laisse_a_la_racine(qapp, tmp_path):
    """Un groupe racine glissé loin de tout autre groupe reste à la racine
    (parent None) — le pendant « rien ne le contient » du recalcul."""
    view, folders, world, inner, _ = _two_groups_view(tmp_path)

    view._boxes[inner.id].setPos(4000.0, 4000.0)   # loin de World
    view._view.drag_finished.emit()

    out = next(f for f in folders.folders("scenes") if f.id == inner.id)
    assert out.parent_id is None


# ── Niveaux (tranche 3d) : descente, portes de frontière, fil d'Ariane ──

def _leveled_view(tmp_path):
    """A (start, hors groupe) → B → C, avec B et C dans le groupe World.
    L'arête A→B franchit la frontière ; B→C est interne au groupe."""
    from core.project import Project
    from core.models.scene import Scene
    from core.asset_folder_store import AssetFolderStore
    from core.scene_graph_state import SceneGraphState
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project = Project(tmp_path / "jeu")
    scripts = project.root / "assets" / "scripts" / "scenes"
    scripts.mkdir(parents=True)
    for name in ("A", "B", "C"):
        project.scenes.append(Scene(name=name))
    project.settings.start_scene = "A"
    (scripts / "a.lua").write_text('scene:switch("B")\n', encoding="utf-8")
    (scripts / "b.lua").write_text('scene:switch("C")\n', encoding="utf-8")
    project.scenes[0].script = "assets/scripts/scenes/a.lua"
    project.scenes[1].script = "assets/scripts/scenes/b.lua"

    state = SceneGraphState(project.root)
    folders = AssetFolderStore(project.root)
    world = folders.create_folder("scenes", "World")
    folders.move_member("scenes", "B", world.id)
    folders.move_member("scenes", "C", world.id)

    view = SceneGraphView()
    view.set_project(project, state, folders)
    view.refresh()
    return view, world


def _doors(view):
    from ui.scene_manager.scene_graph_group_items import BoundaryDoorItem
    return [i for i in view._scene.items() if isinstance(i, BoundaryDoorItem)]


def test_descendre_dans_un_groupe_montre_ses_scenes_et_une_porte(qapp, tmp_path):
    view, world = _leveled_view(tmp_path)

    view._descend(world.id)

    cards, _missing, edges = _counts(view)
    # Seules les scènes du groupe ; A (externe) n'est plus une carte.
    assert {c.name for c in cards} == {"B", "C"}
    # Deux arêtes : B→C interne, ET le lien de la porte d'entrée vers B (A→B).
    assert len(edges) == 2
    assert {(e.edge.source, e.edge.target) for e in edges} == {("B", "C"), ("A", "B")}
    doors = _doors(view)
    assert len(doors) == 1 and doors[0].incoming and doors[0].count == 1  # A→B entre


def test_le_lien_de_sortie_relie_le_noeud_a_la_porte(qapp, tmp_path):
    """Une scène du groupe qui bascule vers l'extérieur : en descendant, un lien
    part du nœud interne vers la porte de sortie (pas seulement une porte qui
    flotte)."""
    from core.project import Project
    from core.models.scene import Scene
    from core.asset_folder_store import AssetFolderStore
    from core.scene_graph_state import SceneGraphState
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project = Project(tmp_path / "jeu")
    scripts = project.root / "assets" / "scripts" / "scenes"
    scripts.mkdir(parents=True)
    for name in ("Inside", "Outside"):
        project.scenes.append(Scene(name=name))
    project.settings.start_scene = "Inside"
    (scripts / "inside.lua").write_text('scene:switch("Outside")\n', encoding="utf-8")
    project.scenes[0].script = "assets/scripts/scenes/inside.lua"

    folders = AssetFolderStore(project.root)
    world = folders.create_folder("scenes", "World")
    folders.move_member("scenes", "Inside", world.id)   # Inside dans le groupe, Outside dehors

    view = SceneGraphView()
    view.set_project(project, SceneGraphState(project.root), folders)
    view.refresh()
    view._descend(world.id)

    cards, _missing, edges = _counts(view)
    assert {c.name for c in cards} == {"Inside"}
    doors = _doors(view)
    assert len(doors) == 1 and doors[0].incoming is False and doors[0].count == 1
    # Le lien de sortie porte bien l'appel Inside→Outside.
    assert [(e.edge.source, e.edge.target) for e in edges] == [("Inside", "Outside")]


def test_le_fil_d_ariane_suit_le_niveau(qapp, tmp_path):
    # La racine porte le NOM DU PROJET (ici « jeu », le dossier du projet).
    view, world = _leveled_view(tmp_path)
    assert [name for _id, name in view._breadcrumb_path()] == ["jeu"]

    view._descend(world.id)
    assert [name for _id, name in view._breadcrumb_path()] == ["jeu", "World"]


def test_backspace_remonte_d_un_niveau(qapp, tmp_path):
    view, world = _leveled_view(tmp_path)
    view._descend(world.id)
    assert view._level == world.id

    view._view.ascend_requested.emit()

    assert view._level is None
    cards, _m, _e = _counts(view)
    assert "A" in {c.name for c in cards}      # de retour à la racine


def test_le_clic_sur_un_maillon_remonte(qapp, tmp_path):
    view, world = _leveled_view(tmp_path)
    view._descend(world.id)

    view._breadcrumb.level_selected.emit(None)

    assert view._level is None


# ── Sélection croisée avec le project viewer (tranche 4) ────────────────

def test_selectionner_des_cartes_emet_les_noms(qapp, tmp_path):
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()
    got = []
    view.scenes_selected.connect(got.append)

    _card(view, "Arena").setSelected(True)

    assert got and "Arena" in got[-1]


def test_selected_scene_name_une_seule(qapp, tmp_path):
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()

    assert view.selected_scene_name() is None          # rien de sélectionné
    _card(view, "Arena").setSelected(True)
    assert view.selected_scene_name() == "Arena"       # une seule → son nom
    _card(view, "Title").setSelected(True)
    assert view.selected_scene_name() is None          # plusieurs → aucune cible unique


def test_highlight_scenes_selectionne_sans_reemettre(qapp, tmp_path):
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()
    got = []
    view.scenes_selected.connect(got.append)

    view.highlight_scenes(["Arena"])

    assert _card(view, "Arena").isSelected()
    assert got == []          # synchro entrante : pas de ré-émission (anti-boucle)


# ── Aperçu du fond PAR SCÈNE (pastille du nœud) ─────────────────────────

def _grapher_state(tmp_path):
    from core.scene_graph_state import SceneGraphState
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project, SceneGraphState(project.root))
    view.refresh()
    return view


def test_noeuds_condenses_par_defaut(qapp, tmp_path):
    from ui.scene_manager.scene_graph_items import CARD_W

    view = _grapher_state(tmp_path)
    card = _card(view, "Title")
    assert card._preview_enabled is False and card._w == CARD_W
    # Chaque nœud porte une pastille de bascule.
    from ui.scene_manager.scene_graph_items import ScenePreviewToggleItem
    pills = [i for i in view._scene.items() if isinstance(i, ScenePreviewToggleItem)]
    assert {p.name for p in pills} == {"Title", "Arena"}


def test_pastille_active_l_apercu_de_cette_scene_seulement(qapp, tmp_path):
    from ui.scene_manager.scene_graph_items import PREVIEW_W, CARD_W, ScenePreviewToggleItem

    view = _grapher_state(tmp_path)
    pill = next(i for i in view._scene.items()
                if isinstance(i, ScenePreviewToggleItem) and i.name == "Title")

    view._view.clicked.emit(pill)     # clic sur la pastille de Title

    assert view._state.scene_preview("Title") is True
    assert _card(view, "Title")._preview_enabled and _card(view, "Title")._w == PREVIEW_W
    # Arena, non touchée, reste condensée.
    assert _card(view, "Arena")._preview_enabled is False and _card(view, "Arena")._w == CARD_W


def test_re_clic_repasse_en_condense(qapp, tmp_path):
    from ui.scene_manager.scene_graph_items import CARD_W, ScenePreviewToggleItem

    view = _grapher_state(tmp_path)

    def pill(name):
        return next(i for i in view._scene.items()
                    if isinstance(i, ScenePreviewToggleItem) and i.name == name)

    view._view.clicked.emit(pill("Title"))
    view._view.clicked.emit(pill("Title"))   # re-projeté entre les deux clics

    assert view._state.scene_preview("Title") is False
    assert _card(view, "Title")._preview_enabled is False and _card(view, "Title")._w == CARD_W


def test_apercu_actif_sans_fond_montre_le_backdrop(qapp, tmp_path):
    """Sans fond affecté, la vignette est la couleur de backdrop de la scène
    (ce que le matériel montrerait), pas un écran vide."""
    from PyQt6.QtGui import QColor
    from core.models.gba_color import bgr555_to_rgb888
    from ui.scene_manager.scene_graph_items import PREVIEW_W, ScenePreviewToggleItem

    view = _grapher_state(tmp_path)      # scènes sans aucun layer de fond
    # Backdrop rouge vif (BGR555) sur la scène Title.
    red = 0x001F
    view._project.scenes[0].backdrop_color = red
    view._view.clicked.emit(next(i for i in view._scene.items()
                                 if isinstance(i, ScenePreviewToggleItem) and i.name == "Title"))

    card = _card(view, "Title")
    assert card._preview_enabled and card._w == PREVIEW_W
    assert card._preview is not None
    # La vignette est bien peinte de la couleur de backdrop.
    expected = QColor(*bgr555_to_rgb888(red))
    assert card._preview.toImage().pixelColor(4, 4) == expected


def test_apercu_actif_compose_la_vignette_du_fond(qapp, tmp_path, monkeypatch):
    from PyQt6.QtGui import QPixmap
    from core.models.background import BackgroundLayer
    from core.scene_graph_state import SceneGraphState
    from ui.scene_manager import scene_graph_view as mod
    from ui.scene_manager.scene_graph_items import ScenePreviewToggleItem
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    project.scenes[0].background_layers.append(BackgroundLayer(background_name="town"))
    dummy = QPixmap(240, 160)
    dummy.fill()
    monkeypatch.setattr(mod, "layer_png_path", lambda p, layer: tmp_path / "x.png")
    monkeypatch.setattr(mod, "bg_pixmap", lambda *a, **k: dummy)

    view = SceneGraphView()
    view.set_project(project, SceneGraphState(project.root))
    view.refresh()
    view._view.clicked.emit(next(i for i in view._scene.items()
                                 if isinstance(i, ScenePreviewToggleItem) and i.name == "Title"))

    assert _card(view, "Title")._preview is not None


# ── Création de groupe depuis le Graphe (Ctrl+G, clic-droit) ────────────

def _grapher(tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from core.scene_graph_state import SceneGraphState
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    folders = AssetFolderStore(project.root)
    view = SceneGraphView()
    view.set_project(project, SceneGraphState(project.root), folders)
    view.refresh()
    return view, folders


def test_grouper_la_selection_range_les_scenes(qapp, tmp_path):
    view, folders = _grapher(tmp_path)
    changed = []
    view.groups_changed.connect(lambda: changed.append(True))
    _card(view, "Arena").setSelected(True)

    view._group_selected_scenes()

    groups = folders.folders("scenes")
    assert len(groups) == 1 and groups[0].members == ("Arena",)
    assert groups[0].name == "Group"
    assert changed == [True]
    # La boîte du groupe (replié par défaut) apparaît, la carte membre disparaît.
    assert "Arena" not in view._cards and len(_boxes(view)) == 1


def test_grouper_sans_selection_cree_un_groupe_vide(qapp, tmp_path):
    view, folders = _grapher(tmp_path)

    view._group_selected_scenes()

    groups = folders.folders("scenes")
    assert len(groups) == 1 and groups[0].members == ()
    # Même vide, le groupe apparaît dans le graphe : une boîte repliable, prête
    # à recevoir des scènes (régression : il était invisible tant que vide).
    boxes = _boxes(view)
    assert len(boxes) == 1 and boxes[0].group_id == groups[0].id


def test_un_groupe_vide_cree_dans_le_viewer_apparait_au_graphe(qapp, tmp_path):
    """Régression : un groupe créé vide dans le project viewer existait sur le
    disque mais restait invisible au graphe, qui ne dérivait ses boîtes que des
    scènes membres. Une boîte est désormais amorcée pour chaque dossier du
    niveau, membre ou pas."""
    view, folders = _grapher(tmp_path)
    folders.create_folder("scenes", "blop")

    view.reload_groups()      # ce que la fenêtre appelle sur groups_changed

    boxes = _boxes(view)
    assert [b.group_id for b in boxes] == [folders.folders("scenes")[0].id]


def _frame(view, gid):
    return view._frames[gid]


def test_glisser_une_scene_dans_le_cadre_la_rend_membre(qapp, tmp_path):
    """Appartenance géométrique : une carte lâchée DANS le cadre d'un groupe
    déplié devient membre de ce groupe (recalcul au relâchement)."""
    view, group = _grouped_view(tmp_path, collapsed=False)
    folders = view._folders
    assert folders.folder_of("scenes", "Title") is None  # hors groupe au départ

    # Pose Title au même endroit qu'Arena (déjà dans le cadre) → centre contenu.
    _card(view, "Title").setPos(_card(view, "Arena").pos())
    view._view.drag_finished.emit()

    assert folders.folder_of("scenes", "Title") == group.id


def test_glisser_une_scene_hors_du_cadre_la_sort_du_groupe(qapp, tmp_path):
    view, group = _grouped_view(tmp_path, collapsed=False)
    folders = view._folders
    assert folders.folder_of("scenes", "Arena") == group.id

    _card(view, "Arena").setPos(6000, 6000)   # loin, hors de tout cadre
    view._view.drag_finished.emit()

    assert folders.folder_of("scenes", "Arena") is None


def test_redimensionner_un_cadre_ne_fait_pas_fuir_ses_membres(qapp, tmp_path):
    """Rétrécir le cadre (le membre se retrouve dehors) ne change PAS
    l'appartenance : seul un glisser de carte le fait."""
    view, group = _grouped_view(tmp_path, collapsed=False)
    folders = view._folders
    frame = _frame(view, group.id)

    frame._w, frame._h = 10.0, _MIN_H_VALUE()   # cadre minuscule, Arena dehors
    view._view.drag_finished.emit()

    assert folders.folder_of("scenes", "Arena") == group.id  # toujours membre


def _MIN_H_VALUE():
    from ui.scene_manager.scene_graph_group_items import _MIN_H
    return _MIN_H


def test_deplacer_le_cadre_par_lentete_emporte_les_membres(qapp, tmp_path):
    """Le déplacement du cadre translate ses cartes membres, qui restent donc
    dans le groupe. La géométrie du cadre est persistée."""
    from core.scene_graph_state import SceneGraphState
    view, group = _grouped_view(tmp_path, collapsed=False)
    folders = view._folders
    frame = _frame(view, group.id)
    arena = _card(view, "Arena")
    start = arena.pos()

    # Simule un déplacement d'en-tête : le cadre et ses membres bougent de (+50,+30).
    frame.setPos(frame.pos().x() + 50, frame.pos().y() + 30)
    arena.setPos(start.x() + 50, start.y() + 30)
    view._view.drag_finished.emit()

    assert folders.folder_of("scenes", "Arena") == group.id     # reste dedans
    assert SceneGraphState(view._project.root).group_frame(group.id) is not None


def test_clic_droit_supprimer_une_scene(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)

    view._delete_scene("Arena")

    assert "Arena" not in {s.name for s in project.scenes}
    assert "Arena" not in view._cards        # la vue s'est re-projetée


def test_clic_droit_supprimer_une_scene_annulable(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from core.history import get_history
    from ui.scene_manager.scene_graph_view import SceneGraphView

    project, _ = _project(tmp_path)
    view = SceneGraphView()
    view.set_project(project)
    view.refresh()
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)

    view._delete_scene("Arena")
    get_history().undo()

    assert "Arena" in {s.name for s in project.scenes}   # Ctrl+Z la ramène


def test_clic_droit_supprimer_un_groupe_remonte_ses_membres(qapp, tmp_path):
    view, group = _grouped_view(tmp_path, collapsed=True)
    folders = view._folders
    changed = []
    view.groups_changed.connect(lambda: changed.append(True))
    assert folders.folder_of("scenes", "Arena") == group.id

    view._delete_group(group.id)

    assert folders.folders("scenes") == []          # le dossier a disparu
    assert folders.folder_of("scenes", "Arena") is None   # Arena remonte à la racine
    assert changed == [True]
    # Arena redevient une carte visible (plus cachée dans une boîte).
    assert "Arena" in view._cards


def test_grouper_au_niveau_ouvert_donne_le_parent(qapp, tmp_path):
    view, folders = _grapher(tmp_path)
    parent = folders.create_folder("scenes", "World")
    view._descend(parent.id)

    view._group_selected_scenes()

    child = next(f for f in folders.folders("scenes") if f.name == "Group")
    assert child.parent_id == parent.id


# ── Inspecteur d'arête (partie 4) ───────────────────────────────────────

def test_edge_inspector_liste_les_appels_et_saute_au_code(qapp, tmp_path):
    """L'inspecteur d'arête nomme la transition, liste ses occurrences, et émet la
    LuaRef exacte quand on clique une occurrence (saut au script)."""
    from PyQt6.QtWidgets import QFrame, QPushButton
    from scripting.scene_graph import scene_graph
    from ui.scene_manager.inspectors.edge_inspector import EdgeInspector

    project, source = _project(tmp_path)
    # Deux appels Title→Arena pour vérifier l'agrégation.
    source.write_text('scene:switch("Arena")\nscene:switch("Arena")\n', encoding="utf-8")
    edge = next(e for e in scene_graph(project).edges
                if (e.source, e.target) == ("Title", "Arena"))

    insp = EdgeInspector()
    opened = []
    insp.open_ref.connect(opened.append)
    insp.load(edge, project)

    # Lignes-feuilles cliquables (curseur main) = une par occurrence agrégée.
    from PyQt6.QtCore import Qt
    leaves = [w for i in range(insp._list_layout.count())
              if (w := insp._list_layout.itemAt(i).widget()) is not None
              and isinstance(w, QFrame)
              and w.cursor().shape() == Qt.CursorShape.PointingHandCursor]
    assert len(leaves) == len(edge.refs) == 2
    leaves[0].findChild(QPushButton).click()  # bouton explicite « Ouvrir »
    assert opened and opened[0] in edge.refs


def test_edge_inspector_signale_une_cible_introuvable(qapp, tmp_path):
    from scripting.scene_graph import scene_graph
    from ui.scene_manager.inspectors.edge_inspector import EdgeInspector

    project, source = _project(tmp_path)
    source.write_text('scene:switch("Ghost")\n', encoding="utf-8")
    edge = next(e for e in scene_graph(project).edges if e.target == "Ghost")

    insp = EdgeInspector()
    insp.load(edge, project)
    # La cible « Ghost » est absente du projet, mais l'appel qui la vise existe :
    # l'inspecteur liste donc son occurrence (le signal « introuvable » est porté
    # par le graphe via MissingTargetItem, pas par ce panneau).
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QFrame
    leaves = [w for i in range(insp._list_layout.count())
              if (w := insp._list_layout.itemAt(i).widget()) is not None
              and isinstance(w, QFrame)
              and w.cursor().shape() == Qt.CursorShape.PointingHandCursor]
    assert len(leaves) == len(edge.refs) == 1


# ── Suppressions : dossier+contenu, et sélection au Backspace ────────────

def test_supprimer_dossier_et_contenu(qapp, tmp_path, monkeypatch):
    """Clic-droit « Supprimer le dossier et son contenu » : les scènes du
    sous-arbre disparaissent ET le dossier aussi."""
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        "ui.scene_manager.scene_graph_view.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.Yes)
    view, folders = _grapher(tmp_path)
    group = folders.create_folder("scenes", "World")
    folders.move_member("scenes", "Arena", group.id)
    view.refresh()

    view._delete_group_deep(group.id)

    assert folders.folders("scenes") == []                    # dossier parti
    assert "Arena" not in {n.name for n in view.graph.nodes}   # scène supprimée
    assert "Title" in {n.name for n in view.graph.nodes}       # le reste intact


def test_backspace_supprime_la_selection(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        "ui.scene_manager.scene_graph_view.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.Yes)
    view, folders = _grapher(tmp_path)
    _card(view, "Arena").setSelected(True)

    view._delete_selection()

    assert "Arena" not in {n.name for n in view.graph.nodes}
    assert "Title" in {n.name for n in view.graph.nodes}


def test_backspace_sans_selection_remonte_dun_niveau(qapp, tmp_path):
    """Sans rien de sélectionné, Backspace garde son rôle d'origine : remonter."""
    view, folders = _grapher(tmp_path)
    group = folders.create_folder("scenes", "World")
    view.refresh()
    view._descend(group.id)
    assert view._level == group.id

    view._delete_selection()   # aucune sélection → ascension

    assert view._level is None
    assert {n.name for n in view.graph.nodes} == {"Title", "Arena"}


# ── Navigation par niveaux au clavier (← / →) ────────────────────────────

def test_fleche_droite_entre_dans_le_groupe_selectionne(qapp, tmp_path):
    view, folders = _grapher(tmp_path)
    group = folders.create_folder("scenes", "World")
    view.reload_groups()              # l'empreinte des scripts n'a pas bougé
    box = next(b for b in _boxes(view) if b.group_id == group.id)
    box.setSelected(True)

    view._descend_selected()          # ce que déclenche la flèche droite
    assert view._level == group.id

    view._ascend()                    # ce que déclenche la flèche gauche
    assert view._level is None


def test_fleche_droite_sans_groupe_unique_ne_fait_rien(qapp, tmp_path):
    view, _folders = _grapher(tmp_path)
    _card(view, "Arena").setSelected(True)   # une scène, pas un groupe

    view._descend_selected()
    assert view._level is None
