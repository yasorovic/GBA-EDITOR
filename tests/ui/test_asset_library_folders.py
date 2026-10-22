"""Dossiers d'auteur dans la Scene library — capacité générale du AssetLibrary,
dont la famille Scenes est le premier client (store partagé avec le Graphe)."""
from __future__ import annotations

import hashlib


def _sid(name):
    """L'id (12 chiffres hex) qu'un test donne à la scène `name` — déterministe, pour écrire les rangements sans projet."""
    return hashlib.sha1(name.encode()).hexdigest()[:12]


def _scene(name, **fields):
    from core.models.scene import Scene
    scene = Scene(name=name, **fields)
    scene.id = _sid(name)
    return scene


def test_folded_nodes_range_les_assets_sous_leurs_dossiers():
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_library import AssetNode, FolderScheme, folded_nodes
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        store = AssetFolderStore(Path(d))
        village = store.create_folder("scenes", "Village")

        class _Scene:
            def __init__(self, name): self.name, self.id = name, _sid(name)
        shop, title = _Scene("Shop"), _Scene("Title")
        store.move_member("scenes", _sid("Shop"), village.id)

        scheme = FolderScheme(
            folders=lambda: store.folders("scenes"),
            create=lambda n, p: store.create_folder("scenes", n, p),
            rename=lambda i, n: store.rename_folder("scenes", i, n),
            delete=lambda i: store.delete_folder("scenes", i),
            set_parent=lambda i, p: store.set_parent("scenes", i, p),
            move=lambda s, i: store.move_member("scenes", s.id, i),
            folder_of=lambda s: store.folder_of("scenes", s.id),
        )
        raw = [AssetNode(name="Shop", obj=shop), AssetNode(name="Title", obj=title)]
        roots = folded_nodes(raw, scheme)

        # Un dossier en tête (contenant Shop), puis Title à la racine.
        folder = next(n for n in roots if n.is_folder)
        assert folder.name == "Village"
        assert [c.obj for c in folder.children] == [shop]
        assert any(n.obj is title for n in roots)


def _scenes_project(tmp_path):
    from core.project import Project
    from core.models.scene import Scene
    project = Project(tmp_path / "jeu")
    for name in ("Title", "Shop", "Arena"):
        project.scenes.append(_scene(name))
    return project


def _folder_items(tree):
    from ui.common.asset_library import _ROLE_FOLDER
    out = []
    stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    while stack:
        it = stack.pop()
        if it.data(0, _ROLE_FOLDER) is not None:
            out.append(it)
        stack.extend(it.child(n) for n in range(it.childCount()))
    return out


def test_le_project_viewer_montre_les_dossiers_de_scenes(qapp, tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_kinds import SCENES
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    folder = store.create_folder("scenes", "Town")
    store.move_member("scenes", _sid("Shop"), folder.id)

    panel = SceneLibraryPanel()
    panel.load_project(project)
    panel.set_folder_store(store)

    tree = panel._library._trees[SCENES.label]
    folders = _folder_items(tree)
    assert [f.text(0) for f in folders] == ["Town"]
    # La scène Shop est rangée SOUS le dossier ; les autres à la racine.
    shop_parent = folders[0]
    names = {shop_parent.child(i).text(0).split()[0] for i in range(shop_parent.childCount())}
    assert names == {"Shop"}


def _press(tree, item, modifiers):
    """Simule un clic gauche sur `item`, avec ces modificateurs — `QTest.mouseClick`
    (l'outil documenté par Qt pour ça) plutôt qu'un `QMouseEvent` fabriqué à la
    main : un clic direct sur `mousePressEvent` seul ne fait pas transiter le
    widget par le focus/press/release complet dont dépend l'ancre interne de
    Qt (`QItemSelectionModel.currentIndex`), et un Maj-clic simulé ainsi
    n'étendait rien — juste un symptôme de test, pas un bug de l'éditeur."""
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt as QtNS
    from PyQt6.QtWidgets import QApplication
    rect = tree.visualItemRect(item)
    QTest.mouseClick(tree.viewport(), QtNS.MouseButton.LeftButton, modifiers, rect.center())
    # Draine l'émission différée (`QTimer.singleShot(0, ...)`, cf.
    # `_on_selection_set_changed`) tout de suite : un clic de test = un clic,
    # jamais un timer qui traîne jusqu'au test suivant.
    QApplication.instance().processEvents()


def test_le_clic_simple_active_mais_la_multi_selection_ne_charge_rien(qapp, tmp_path):
    """La multi-sélection dans la Scene library n'active (ne charge) plus
    chaque scène ; seul un clic simple, résolu sur la sélection STABILISÉE,
    active — et l'émission est différée d'un tour de boucle (cf.
    `_on_selection_set_changed`), d'où les `processEvents()`."""
    from PyQt6.QtCore import Qt as QtNS
    from ui.common.asset_kinds import SCENES
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel

    project = _scenes_project(tmp_path)
    panel = SceneLibraryPanel()
    panel.load_project(project)

    activated = []
    panel._library.selected.connect(lambda label, obj: activated.append(obj.name))

    tree = panel._library._trees[SCENES.label]
    items = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]

    # Clic simple → activation (une émission).
    _press(tree, items[0], QtNS.KeyboardModifier.NoModifier)
    assert activated == ["Title"]

    # Maj-clic → lot sélectionné, aucune activation supplémentaire.
    _press(tree, items[1], QtNS.KeyboardModifier.ShiftModifier)
    assert activated == ["Title"]     # inchangé : le lot n'active pas

    # Retour à une sélection unique (clic simple) → activation de nouveau.
    _press(tree, items[2], QtNS.KeyboardModifier.NoModifier)
    assert activated[-1] == "Arena"


def test_maj_clic_selectionne_la_plage_sans_perdre_le_premier(qapp, tmp_path):
    """Régression du chantier précédent : décider l'activation sur
    `currentItemChanged` (émis AVANT que Qt pose la plage d'un Maj-clic)
    activait la scène cliquée EN PLEIN GESTE, ce qui reconstruisait l'arbre et
    perdait le premier élément. On décide maintenant sur la sélection
    stabilisée (`itemSelectionChanged`), et Qt gère la plage nativement."""
    from PyQt6.QtCore import Qt as QtNS
    from ui.common.asset_kinds import SCENES
    from ui.common.asset_library import _ROLE_OBJ
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel

    project = _scenes_project(tmp_path)
    panel = SceneLibraryPanel()
    panel.load_project(project)

    activated = []
    panel._library.selected.connect(lambda label, obj: activated.append(obj.name))

    tree = panel._library._trees[SCENES.label]
    items = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    assert len(items) >= 3
    names = [it.data(0, _ROLE_OBJ).name for it in items]

    _press(tree, items[0], QtNS.KeyboardModifier.NoModifier)
    assert activated == [names[0]]

    _press(tree, items[2], QtNS.KeyboardModifier.ShiftModifier)

    selected = {i.data(0, _ROLE_OBJ).name for i in tree.selectedItems()}
    assert selected == {names[0], names[1], names[2]}
    assert activated == [names[0]]     # le lot n'a rien activé de plus


def test_ctrl_clic_bascule_un_element_sans_toucher_au_reste(qapp, tmp_path):
    from PyQt6.QtCore import Qt as QtNS
    from ui.common.asset_kinds import SCENES
    from ui.common.asset_library import _ROLE_OBJ
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel

    project = _scenes_project(tmp_path)
    panel = SceneLibraryPanel()
    panel.load_project(project)

    tree = panel._library._trees[SCENES.label]
    items = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    assert len(items) >= 3
    names = [it.data(0, _ROLE_OBJ).name for it in items]

    _press(tree, items[0], QtNS.KeyboardModifier.NoModifier)
    _press(tree, items[2], QtNS.KeyboardModifier.ControlModifier)   # ajoute C

    selected = {i.data(0, _ROLE_OBJ).name for i in tree.selectedItems()}
    assert selected == {names[0], names[2]}

    _press(tree, items[0], QtNS.KeyboardModifier.ControlModifier)   # retire A

    selected = {i.data(0, _ROLE_OBJ).name for i in tree.selectedItems()}
    assert selected == {names[2]}


def test_selection_de_scenes_relayee_pour_le_graphe(qapp, tmp_path):
    from ui.common.asset_kinds import SCENES
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel

    project = _scenes_project(tmp_path)
    panel = SceneLibraryPanel()
    panel.load_project(project)
    got = []
    panel.scenes_selected.connect(got.append)

    tree = panel._library._trees[SCENES.label]
    tree.topLevelItem(1).setSelected(True)   # "Shop"
    qapp.processEvents()      # l'émission est différée d'un tour de boucle

    assert got and "Shop" in got[-1]


def test_deplacer_une_scene_vers_un_dossier_via_le_store(qapp, tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_kinds import SCENES
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    panel = SceneLibraryPanel()
    panel.load_project(project)
    panel.set_folder_store(store)

    tree = panel._library._trees[SCENES.label]
    scheme = panel._library.folder_scheme(SCENES.label)
    folder = scheme.create("Town", None)
    arena = next(s for s in project.scenes if s.name == "Arena")
    tree._move_to_folder(scheme, arena, folder.id)

    # Rangement reflété dans le store partagé (donc visible aussi côté Graphe).
    assert store.folder_of("scenes", _sid("Arena")) == folder.id


def test_creer_un_groupe_vide_depuis_le_menu_ajout(qapp, tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    panel = SceneLibraryPanel()
    panel.load_project(project)
    panel.set_folder_store(store)
    changed = []
    panel.groups_changed.connect(lambda: changed.append(True))

    panel._create_scene_group()

    groups = store.folders("scenes")
    assert [g.name for g in groups] == ["Group"] and groups[0].members == ()
    assert changed == [True]


def test_ctrl_g_groupe_les_scenes_selectionnees(qapp, tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_kinds import SCENES
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    panel = SceneLibraryPanel()
    panel.load_project(project)
    panel.set_folder_store(store)

    tree = panel._library._trees[SCENES.label]
    tree.topLevelItem(0).setSelected(True)   # Title
    tree.topLevelItem(2).setSelected(True)   # Arena
    panel._group_selected_scenes()

    groups = store.folders("scenes")
    assert len(groups) == 1 and set(groups[0].members) == {_sid("Title"), _sid("Arena")}


def test_clic_droit_grouper_range_un_lot(qapp, tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_kinds import SCENES
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    panel = SceneLibraryPanel()
    panel.load_project(project)
    panel.set_folder_store(store)
    changed = []
    panel.groups_changed.connect(lambda: changed.append(True))

    tree = panel._library._trees[SCENES.label]
    title = next(s for s in project.scenes if s.name == "Title")
    arena = next(s for s in project.scenes if s.name == "Arena")
    tree._group([title, arena])

    groups = store.folders("scenes")
    assert len(groups) == 1 and set(groups[0].members) == {_sid("Title"), _sid("Arena")}
    assert changed          # le Graphe est prévenu (folders_changed → groups_changed)


def test_multi_deplacer_vers_le_dossier(qapp, tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_kinds import SCENES
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    folder = store.create_folder("scenes", "Town")
    panel = SceneLibraryPanel()
    panel.load_project(project)
    panel.set_folder_store(store)

    tree = panel._library._trees[SCENES.label]
    scheme = panel._library.folder_scheme(SCENES.label)
    title = next(s for s in project.scenes if s.name == "Title")
    arena = next(s for s in project.scenes if s.name == "Arena")
    tree._move_many_to_folder(scheme, [title, arena], folder.id)

    assert store.folder_of("scenes", _sid("Title")) == folder.id
    assert store.folder_of("scenes", _sid("Arena")) == folder.id


def test_un_library_range_seulement_les_familles_qui_le_declarent(qapp, tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_library import AssetLibrary
    from ui.common.asset_kinds import PREFABS, SCENES

    project = _scenes_project(tmp_path)
    library = AssetLibrary("Library", [SCENES, PREFABS])
    library.load_project(project)

    library.set_folder_store(AssetFolderStore(project.root))

    assert library.folder_scheme(SCENES.label) is not None      # SCENES déclare folder_family
    assert library.folder_scheme(PREFABS.label) is None         # PREFABS ne le déclare pas : à plat


def test_le_scheme_d_une_famille_range_par_id_dans_sa_propre_famille(tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_library import FolderScheme

    store = AssetFolderStore(tmp_path)
    sprites = FolderScheme.for_family(store, "sprites")
    folder = sprites.create("Enemies", None)

    class _Asset:
        id = "0123456789ab"
    sprites.move(_Asset, folder.id)

    assert sprites.folder_of(_Asset) == folder.id
    assert store.folder_of("sprites", "0123456789ab") == folder.id
    assert store.folders("scenes") == []                       # une autre famille ne voit rien
