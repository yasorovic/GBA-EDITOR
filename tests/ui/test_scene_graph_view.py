"""La vue Graphe projette à l'affichage et ne re-parse qu'au changement."""
from __future__ import annotations

import hashlib

import pytest


def _sid(name):
    """L'id (12 chiffres hex) qu'un test donne à la scène `name` — déterministe, pour écrire les rangements sans projet."""
    return hashlib.sha1(name.encode()).hexdigest()[:12]


def _scene(name, **fields):
    from core.models.scene import Scene
    scene = Scene(name=name, **fields)
    scene.id = _sid(name)
    return scene


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
        project.scenes.append(_scene(name))
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
    folders.move_member("scenes", _sid("Arena"), group.id)
    state.set_group_collapsed(group.id, collapsed)

    view = SceneGraphView()
    view.set_project(project, state, folders)
    view.refresh()
    return view, group


# ── Niveaux (tranche 3d) : descente, portes de frontière, fil d'Ariane ──

# ── Sélection croisée avec le project viewer (tranche 4) ────────────────

# ── Aperçu du fond PAR SCÈNE (pastille du nœud) ─────────────────────────

# ── Création de groupe depuis le Graphe (Ctrl+G, clic-droit) ────────────

def test_glisser_une_scene_dans_le_cadre_la_rend_membre(qapp, tmp_path):
    """Appartenance géométrique : une carte lâchée DANS le cadre d'un groupe
    déplié devient membre de ce groupe (recalcul au relâchement)."""
    view, group = _grouped_view(tmp_path, collapsed=False)
    folders = view._folders
    assert folders.folder_of("scenes", _sid("Title")) is None  # hors groupe au départ

    # Pose Title au même endroit qu'Arena (déjà dans le cadre) → centre contenu.
    _card(view, "Title").setPos(_card(view, "Arena").pos())
    view._view.drag_finished.emit()

    assert folders.folder_of("scenes", _sid("Title")) == group.id


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
    assert folders.folder_of("scenes", _sid("Arena")) == group.id

    view._delete_group(group.id)

    assert folders.folders("scenes") == []          # le dossier a disparu
    assert folders.folder_of("scenes", _sid("Arena")) is None   # Arena remonte à la racine
    assert changed == [True]
    # Arena redevient une carte visible (plus cachée dans une boîte).
    assert "Arena" in view._cards


# ── Inspecteur d'arête (partie 4) ───────────────────────────────────────

# ── Suppressions : dossier+contenu, et sélection au Backspace ────────────

# ── Navigation par niveaux au clavier (← / →) ────────────────────────────

