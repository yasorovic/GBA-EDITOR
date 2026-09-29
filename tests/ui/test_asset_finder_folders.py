"""Dossiers d'auteur dans le project viewer — capacité générale du AssetFinder,
dont la famille Scenes est le premier client (store partagé avec le Graphe)."""
from __future__ import annotations


def test_folded_nodes_range_les_assets_sous_leurs_dossiers():
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_finder import AssetNode, FolderScheme, folded_nodes
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        store = AssetFolderStore(Path(d))
        village = store.create_folder("scenes", "Village")

        class _Scene:
            def __init__(self, name): self.name = name
        shop, title = _Scene("Shop"), _Scene("Title")
        store.move_member("scenes", "Shop", village.id)

        scheme = FolderScheme(
            folders=lambda: store.folders("scenes"),
            create=lambda n, p: store.create_folder("scenes", n, p),
            rename=lambda i, n: store.rename_folder("scenes", i, n),
            delete=lambda i: store.delete_folder("scenes", i),
            set_parent=lambda i, p: store.set_parent("scenes", i, p),
            move=lambda s, i: store.move_member("scenes", s.name, i),
            folder_of=lambda s: store.folder_of("scenes", s.name),
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
        project.scenes.append(Scene(name=name))
    return project


def _folder_items(tree):
    from ui.common.asset_finder import _ROLE_FOLDER
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
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    folder = store.create_folder("scenes", "Town")
    store.move_member("scenes", "Shop", folder.id)

    panel = AssetsFinderPanel()
    panel.load_project(project)
    panel.set_folder_store(store)

    tree = panel._finder._trees[SCENES.label]
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
    """La multi-sélection dans le project viewer n'active (ne charge) plus
    chaque scène ; seul un clic simple, résolu sur la sélection STABILISÉE,
    active — et l'émission est différée d'un tour de boucle (cf.
    `_on_selection_set_changed`), d'où les `processEvents()`."""
    from PyQt6.QtCore import Qt as QtNS
    from ui.common.asset_kinds import SCENES
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    panel = AssetsFinderPanel()
    panel.load_project(project)

    activated = []
    panel._finder.selected.connect(lambda label, obj: activated.append(obj.name))

    tree = panel._finder._trees[SCENES.label]
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
    from ui.common.asset_finder import _ROLE_OBJ
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    panel = AssetsFinderPanel()
    panel.load_project(project)

    activated = []
    panel._finder.selected.connect(lambda label, obj: activated.append(obj.name))

    tree = panel._finder._trees[SCENES.label]
    items = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    assert len(items) >= 3
    names = [it.data(0, _ROLE_OBJ).name for it in items]

    _press(tree, items[0], QtNS.KeyboardModifier.NoModifier)
    assert activated == [names[0]]

    _press(tree, items[2], QtNS.KeyboardModifier.ShiftModifier)

    selected = {i.data(0, _ROLE_OBJ).name for i in tree.selectedItems()}
    assert selected == {names[0], names[1], names[2]}
    assert activated == [names[0]]     # le lot n'a rien activé de plus


def test_maj_clic_conserve_la_selection_active(qapp, tmp_path):
    """Le Maj-clic natif de Qt (`ExtendedSelection`) ne touche qu'à la plage
    entre l'item courant et la cible — un item choisi par Ctrl-clic ailleurs
    reste sélectionné."""
    from PyQt6.QtCore import Qt as QtNS
    from ui.common.asset_kinds import SCENES
    from ui.common.asset_finder import _ROLE_OBJ
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel
    from core.models.scene import Scene

    project = _scenes_project(tmp_path)
    for name in ("Boss", "Credits"):
        project.scenes.append(Scene(name=name))
    panel = AssetsFinderPanel()
    panel.load_project(project)

    tree = panel._finder._trees[SCENES.label]
    items = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    names = [it.data(0, _ROLE_OBJ).name for it in items]
    assert len(items) >= 5

    _press(tree, items[0], QtNS.KeyboardModifier.NoModifier)          # ancre = 0
    _press(tree, items[4], QtNS.KeyboardModifier.ControlModifier)     # + item 4 (devient courant)

    selected = {i.data(0, _ROLE_OBJ).name for i in tree.selectedItems()}
    assert selected == {names[0], names[4]}

    # Maj-clic sur l'item 2 : Qt étend depuis l'item COURANT (4, posé par le
    # Ctrl-clic) jusqu'à 2 — couvre 2..4 — sans effacer l'item 0.
    _press(tree, items[2], QtNS.KeyboardModifier.ShiftModifier)

    selected = {i.data(0, _ROLE_OBJ).name for i in tree.selectedItems()}
    assert selected == {names[0], names[2], names[3], names[4]}


def test_ctrl_clic_bascule_un_element_sans_toucher_au_reste(qapp, tmp_path):
    from PyQt6.QtCore import Qt as QtNS
    from ui.common.asset_kinds import SCENES
    from ui.common.asset_finder import _ROLE_OBJ
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    panel = AssetsFinderPanel()
    panel.load_project(project)

    tree = panel._finder._trees[SCENES.label]
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


def test_la_surbrillance_survit_a_un_repeuplement(qapp, tmp_path):
    """Régression : `populate()` reconstruit l'arbre (renommage, activation
    d'une scène, tout ce qui appelle `refresh()`) — la sélection doit survivre
    par IDENTITÉ d'asset, pas seulement tant que les vieux `QTreeWidgetItem`
    existent. Sans ça, la surbrillance disparaissait au moindre clic simple
    (l'activation de la scène déclenche justement un `refresh()`)."""
    from ui.common.asset_kinds import SCENES
    from ui.common.asset_finder import _ROLE_OBJ
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    qapp.processEvents()   # draine un éventuel timer différé d'un test précédent

    project = _scenes_project(tmp_path)
    panel = AssetsFinderPanel()
    panel.load_project(project)

    tree = panel._finder._trees[SCENES.label]
    shop = next(s for s in project.scenes if s.name == "Shop")
    tree.select_obj(shop)
    assert {i.data(0, _ROLE_OBJ).name for i in tree.selectedItems()} == {"Shop"}

    panel.refresh()      # repeuple : les anciens QTreeWidgetItem sont détruits

    selected = {i.data(0, _ROLE_OBJ).name for i in tree.selectedItems()}
    assert selected == {"Shop"}
    current = tree.currentItem()
    assert current is not None and current.data(0, _ROLE_OBJ).name == "Shop"


def test_le_tree_scenes_ne_active_pas_le_drag_qt(qapp, tmp_path):
    """Garde-fou : activer le drag Qt (InternalMove/acceptDrops) sur un
    QTreeWidget désactive la sélection au rectangle. Le rangement en dossiers
    passe par le menu contextuel, pas par le drag — la multi-sélection prime."""
    from PyQt6.QtWidgets import QAbstractItemView
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_kinds import SCENES
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    panel = AssetsFinderPanel()
    panel.load_project(project)
    panel.set_folder_store(AssetFolderStore(project.root))

    tree = panel._finder._trees[SCENES.label]
    assert tree.dragEnabled() is False
    assert tree.dragDropMode() == QAbstractItemView.DragDropMode.NoDragDrop


def test_selection_de_scenes_relayee_pour_le_graphe(qapp, tmp_path):
    from ui.common.asset_kinds import SCENES
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    panel = AssetsFinderPanel()
    panel.load_project(project)
    got = []
    panel.scenes_selected.connect(got.append)

    tree = panel._finder._trees[SCENES.label]
    tree.topLevelItem(1).setSelected(True)   # "Shop"
    qapp.processEvents()      # l'émission est différée d'un tour de boucle

    assert got and "Shop" in got[-1]


def test_highlight_scenes_surligne_sans_activer(qapp, tmp_path):
    from ui.common.asset_kinds import SCENES
    from ui.common.asset_finder import _ROLE_OBJ
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    panel = AssetsFinderPanel()
    panel.load_project(project)
    activated, relayed = [], []
    panel._finder.selected.connect(lambda l, o: activated.append(o.name))
    panel.scenes_selected.connect(relayed.append)

    panel.highlight_scenes(["Arena", "Title"])

    tree = panel._finder._trees[SCENES.label]
    selected = {i.data(0, _ROLE_OBJ).name for i in tree.selectedItems()}
    assert selected == {"Arena", "Title"}
    assert activated == []     # highlight n'active (ne charge) aucune scène
    assert relayed == []       # ni ne réémet (anti-boucle)


def test_highlight_scene_dans_un_groupe_replie_surligne_le_groupe(qapp, tmp_path):
    """Sélectionner dans le graphe une scène rangée dans un groupe REPLIÉ côté
    project viewer reporte le surlignage sur le GROUPE — la ligne de la scène
    n'y est pas dépliée, mais le panneau garde un retour visuel."""
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_kinds import SCENES
    from ui.common.asset_finder import _ROLE_FOLDER, _ROLE_OBJ
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    folder = store.create_folder("scenes", "Town")
    store.move_member("scenes", "Shop", folder.id)

    panel = AssetsFinderPanel()
    panel.load_project(project)
    panel.set_folder_store(store)

    tree = panel._finder._trees[SCENES.label]
    town = _folder_items(tree)[0]

    # Groupe REPLIÉ : la ligne de Shop est cachée → c'est le groupe qui se surligne.
    town.setExpanded(False)
    panel.highlight_scenes(["Shop"])
    sel = tree.selectedItems()
    assert sel == [town]
    assert sel[0].data(0, _ROLE_FOLDER) == folder.id

    # Groupe DÉPLIÉ : la ligne de Shop est visible → c'est elle qui se surligne.
    town.setExpanded(True)
    panel.highlight_scenes(["Shop"])
    sel = tree.selectedItems()
    assert [i.data(0, _ROLE_OBJ).name for i in sel] == ["Shop"]


def test_deplacer_une_scene_vers_un_dossier_via_le_store(qapp, tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_kinds import SCENES
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    panel = AssetsFinderPanel()
    panel.load_project(project)
    panel.set_folder_store(store)

    tree = panel._finder._trees[SCENES.label]
    scheme = panel._finder.folder_scheme(SCENES.label)
    folder = scheme.create("Town", None)
    arena = next(s for s in project.scenes if s.name == "Arena")
    tree._move_to_folder(scheme, arena, folder.id)

    # Rangement reflété dans le store partagé (donc visible aussi côté Graphe).
    assert store.folder_of("scenes", "Arena") == folder.id


def test_creer_un_groupe_vide_depuis_le_menu_ajout(qapp, tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    panel = AssetsFinderPanel()
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
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    panel = AssetsFinderPanel()
    panel.load_project(project)
    panel.set_folder_store(store)

    tree = panel._finder._trees[SCENES.label]
    tree.topLevelItem(0).setSelected(True)   # Title
    tree.topLevelItem(2).setSelected(True)   # Arena
    panel._group_selected_scenes()

    groups = store.folders("scenes")
    assert len(groups) == 1 and set(groups[0].members) == {"Title", "Arena"}


def test_ctrl_g_sans_selection_ne_cree_rien(qapp, tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    panel = AssetsFinderPanel()
    panel.load_project(project)
    panel.set_folder_store(store)

    panel._group_selected_scenes()

    assert store.folders("scenes") == []


def test_clic_droit_grouper_range_un_lot(qapp, tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_kinds import SCENES
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    panel = AssetsFinderPanel()
    panel.load_project(project)
    panel.set_folder_store(store)
    changed = []
    panel.groups_changed.connect(lambda: changed.append(True))

    tree = panel._finder._trees[SCENES.label]
    title = next(s for s in project.scenes if s.name == "Title")
    arena = next(s for s in project.scenes if s.name == "Arena")
    tree._group([title, arena])

    groups = store.folders("scenes")
    assert len(groups) == 1 and set(groups[0].members) == {"Title", "Arena"}
    assert changed          # le Graphe est prévenu (folders_changed → groups_changed)


def test_clic_droit_grouper_un_seul_item(qapp, tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_kinds import SCENES
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    panel = AssetsFinderPanel()
    panel.load_project(project)
    panel.set_folder_store(store)

    tree = panel._finder._trees[SCENES.label]
    shop = next(s for s in project.scenes if s.name == "Shop")
    tree._group([shop])

    assert store.folders("scenes")[0].members == ("Shop",)


def test_multi_deplacer_vers_le_dossier(qapp, tmp_path):
    from core.asset_folder_store import AssetFolderStore
    from ui.common.asset_kinds import SCENES
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    project = _scenes_project(tmp_path)
    store = AssetFolderStore(project.root)
    folder = store.create_folder("scenes", "Town")
    panel = AssetsFinderPanel()
    panel.load_project(project)
    panel.set_folder_store(store)

    tree = panel._finder._trees[SCENES.label]
    scheme = panel._finder.folder_scheme(SCENES.label)
    title = next(s for s in project.scenes if s.name == "Title")
    arena = next(s for s in project.scenes if s.name == "Arena")
    tree._move_many_to_folder(scheme, [title, arena], folder.id)

    assert store.folder_of("scenes", "Title") == folder.id
    assert store.folder_of("scenes", "Arena") == folder.id
