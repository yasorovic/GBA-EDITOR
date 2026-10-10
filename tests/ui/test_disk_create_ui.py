"""L'onglet Disk : le « + », le bouton « Create <nom> » et le clic droit (créer depuis une source, supprimer)."""
from pathlib import Path

from PyQt6.QtWidgets import QMenu

from core import disk_tree
from ui.common.disk_tree_view import DiskTreeView
from ui.common.disk_view import DiskCallbacks, DiskView, add_asset_actions

BASE = Path("assets")


def _tree() -> disk_tree.DiskNode:
    art = disk_tree.DiskNode("Art", BASE / "Art", disk_tree.FOLDER, children=[
        disk_tree.DiskNode("hero.png", BASE / "Art" / "hero.png", disk_tree.FREE_SOURCE),
        disk_tree.DiskNode("boom.wav", BASE / "Art" / "boom.wav", disk_tree.FREE_SOURCE),
        disk_tree.DiskNode("theme.hex", BASE / "Art" / "theme.hex", disk_tree.FREE_SOURCE),
        disk_tree.DiskNode("notes.txt", BASE / "Art" / "notes.txt", disk_tree.UNSUPPORTED),
        disk_tree.DiskNode("hero.sprite", BASE / "Art" / "hero.sprite", disk_tree.ASSET, "hero", "sprites"),
        disk_tree.DiskNode("Level.scene", BASE / "Art" / "Level.scene", disk_tree.ASSET, "Level", "scenes"),
        disk_tree.DiskNode("texts.json", BASE / "Art" / "texts.json", disk_tree.ASSET, "texts", "texts"),
    ])
    return disk_tree.DiskNode("assets", BASE, disk_tree.FOLDER, children=[art])


FAMILIES = {".png": [("sprites", "Sprite", "hero"), ("backgrounds", "Background", "hero"), ("fonts", "Font", "hero")],
            ".wav": [("sfx", "Sound effect", "boom"), ("music", "Music", "boom"), ("jingles", "Jingle", "boom")],
            ".hex": [("palettes", "Palette", "theme")]}


class _Spy:
    def __init__(self):
        self.created, self.deleted, self.imported, self.blank, self.folders = [], [], [], [], []

    def callbacks(self) -> DiskCallbacks:
        return DiskCallbacks(
            create_options=lambda path: list(FAMILIES.get(Path(path).suffix, [])),
            create_from_source=lambda path, family: self.created.append((Path(path).name, family)),
            delete_items=lambda nodes: self.deleted.append([n.name for n in nodes]),
            deletable=lambda node: node.family not in ("texts", "variables"),
            import_files=lambda folder: self.imported.append(folder),
            create_blank=lambda kind, folder: self.blank.append((kind, folder)),
            new_folder=lambda parent: self.folders.append(parent),
            blank_kinds=[("scene", "Scene"), ("prefab", "Prefab")])


def _view(qapp):
    spy = _Spy()
    view = DiskView()
    view.resize(700, 300)
    view.set_tree(_tree())
    view.set_callbacks(spy.callbacks())
    view.show()
    view._enter(_row(view, "Art"))
    return view, spy


def _row(view, text):
    return next(view._list.item(i) for i in range(view._list.count()) if view._list.item(i).text() == text)


def _select(view, *names):
    view._list.clearSelection()
    for name in names:
        _row(view, name).setSelected(True)


def test_the_button_names_the_asset_a_single_free_source_would_become(qapp):
    view, spy = _view(qapp)

    _select(view, "hero.png")

    assert view._btn_create.isVisibleTo(view) and view._btn_create.text() == "Create"
    assert view._btn_create_more.isVisibleTo(view)                                 # un PNG peut devenir autre chose
    view._btn_create.click()
    assert spy.created == [("hero.png", "sprites")]                                # le clic prend le type le plus courant


def test_the_arrow_only_shows_when_the_file_can_become_several_types(qapp):
    view, _spy = _view(qapp)

    _select(view, "theme.hex")

    assert view._btn_create.text() == "Create"
    assert not view._btn_create_more.isVisibleTo(view)                             # une palette : un seul type


def test_the_button_is_hidden_for_everything_that_is_not_one_free_source(qapp):
    view, _spy = _view(qapp)

    for names in ((), ("hero.sprite",), ("notes.txt",), ("hero.png", "boom.wav")):
        _select(view, *names)
        assert not view._btn_create.isVisibleTo(view), names                       # ni asset, ni format inconnu, ni multi-sélection


def test_the_other_types_are_offered_with_the_same_name(qapp):
    view, spy = _view(qapp)
    _select(view, "boom.wav")

    assert [family for family, _word, _name in view._create_options] == ["sfx", "music", "jingles"]
    view._callbacks.create_from_source(view._create_path, "music")
    assert spy.created == [("boom.wav", "music")]


def _texts(menu: QMenu) -> list[str]:
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def test_the_context_menu_of_one_source_creates_and_of_assets_deletes(qapp):
    spy = _Spy()
    nodes = {n.name: n for n in _tree().walk()}

    single = QMenu()
    add_asset_actions(single, [nodes["theme.hex"]], spy.callbacks())
    assert _texts(single) == ["Create", "Reveal in file manager", "Delete"]
    single.actions()[0].trigger()
    assert spy.created == [("theme.hex", "palettes")]

    ambiguous = QMenu()
    add_asset_actions(ambiguous, [nodes["hero.png"]], spy.callbacks())
    assert _texts(ambiguous) == ["Create as", "Reveal in file manager", "Delete"]
    assert [a.text() for a in ambiguous.actions()[0].menu().actions()] == ["Sprite", "Background", "Font"]

    assets = QMenu()
    add_asset_actions(assets, [nodes["hero.sprite"], nodes["Level.scene"], nodes["texts.json"]], spy.callbacks())
    assert _texts(assets) == ["Delete 2 items"]                                     # les textes ne se suppriment pas ici
    assets.actions()[0].trigger()
    assert spy.deleted == [["hero.sprite", "Level.scene"]]


def test_create_from_source_is_greyed_out_in_a_multi_selection_and_says_why(qapp):
    spy = _Spy()
    nodes = {n.name: n for n in _tree().walk()}
    menu = QMenu()

    add_asset_actions(menu, [nodes["hero.png"], nodes["boom.wav"]], spy.callbacks())

    entry = menu.actions()[0]
    assert entry.text() == "Create" and not entry.isEnabled()
    assert "one file at a time" in entry.toolTip()
    assert spy.created == []


def test_files_and_folders_can_be_deleted_but_not_the_project_tables(qapp):
    spy = _Spy()
    nodes = {n.name: n for n in _tree().walk()}
    menu = QMenu()
    add_asset_actions(menu, [nodes["notes.txt"], nodes["Art"]], spy.callbacks())
    assert _texts(menu) == ["Delete 2 items"]
    tables = QMenu()
    add_asset_actions(tables, [nodes["texts.json"]], spy.callbacks())
    assert _texts(tables) == ["Reveal in file manager"]                              # pas de Delete : seul l'emplacement s'offre


def test_the_plus_menu_offers_import_create_and_new_folder_for_the_folder_shown(qapp, monkeypatch):
    view, spy = _view(qapp)
    shown = {}

    def fake_exec(menu, *_args):
        shown["items"] = [(a.text(), [s.text() for s in a.menu().actions()] if a.menu() else None) for a in menu.actions()]
        shown["icons"] = [not a.icon().isNull() for a in menu.actions()]
        shown["sub_icons"] = [not s.icon().isNull() for a in menu.actions() if a.menu() for s in a.menu().actions()]
        for action in menu.actions():
            if action.text() == "Import…":
                action.trigger()
            elif action.text() == "New folder":
                action.trigger()
            elif action.menu() is not None:
                action.menu().actions()[0].trigger()                               # « Scene »
    monkeypatch.setattr(QMenu, "exec", fake_exec)

    view._show_plus_menu()

    assert shown["items"] == [("Import…", None), ("Create", ["Scene", "Prefab"]), ("", None), ("New folder", None)]
    assert shown["icons"] == [True, True, False, True]                              # une icône par entrée, comme le « + » des scènes
    assert shown["sub_icons"] == [True, True]
    folder = str(BASE / "Art")
    assert spy.imported == [folder] and spy.folders == [folder] and spy.blank == [("scene", folder)]


def test_the_tree_has_the_same_context_menu(qapp):
    spy = _Spy()
    view = DiskTreeView()
    view.resize(400, 400)
    view.set_tree(_tree())
    view.set_callbacks(spy.callbacks())
    view.show()
    view._tree.expandAll()
    item = next(i for i in _items(view._tree) if i.text(0) == "theme.hex")
    item.setSelected(True)
    menu = QMenu()
    nodes = [n for n in (i.data(0, 256 + 2) for i in view._tree.selectedItems()) if n is not None]

    add_asset_actions(menu, nodes, view._callbacks)

    assert _texts(menu) == ["Create", "Reveal in file manager", "Delete"]


def _items(tree):
    stack = [tree.topLevelItem(0)]
    while stack:
        item = stack.pop()
        yield item
        stack.extend(item.child(i) for i in range(item.childCount()))


def test_the_plus_and_the_loupe_are_flush_right_like_on_the_asset_finders(qapp):
    view, _spy = _view(qapp)
    view.resize(900, 300)
    qapp.processEvents()

    assert view._summary.x() < view._btn_plus.x() < view._btn_search.x()           # à droite du compteur, la loupe en dernier
    assert view._btn_search.x() + view._btn_search.width() >= view.width() - 20    # collés au bord droit


def test_the_loupe_filters_the_entries_by_name_and_keeps_the_way_up(qapp):
    view, _spy = _view(qapp)

    view._btn_search.setChecked(True)
    view._search_box.setText("boo")

    shown = [view._list.item(i).text() for i in range(view._list.count()) if not view._list.item(i).isHidden()]
    assert shown == ["...", "boom.wav"]                                            # « ... » reste, le reste est filtré

    view._enter(_row(view, "..."))                                                  # changer de dossier garde le filtre
    assert [view._list.item(i).text() for i in range(view._list.count()) if not view._list.item(i).isHidden()] == ["assets"]

    view._btn_search.setChecked(False)                                              # refermer la loupe rend tout
    assert not any(view._list.item(i).isHidden() for i in range(view._list.count()))


def test_the_context_menu_entries_carry_icons_too(qapp):
    spy = _Spy()
    nodes = {n.name: n for n in _tree().walk()}
    source, assets = QMenu(), QMenu()

    add_asset_actions(source, [nodes["hero.png"]], spy.callbacks())
    add_asset_actions(assets, [nodes["hero.sprite"]], spy.callbacks())

    submenu = source.actions()[0].menu()
    assert not source.actions()[0].icon().isNull() and all(not a.icon().isNull() for a in submenu.actions())
    assert not assets.actions()[0].icon().isNull()


def test_a_source_that_already_has_an_asset_can_still_give_another(qapp):
    spy = _Spy()
    linked = disk_tree.DiskNode("hero.png", BASE / "Art" / "hero.png", disk_tree.LINKED_SOURCE, "hero", "sprites")
    menu = QMenu()

    add_asset_actions(menu, [linked], spy.callbacks())

    assert menu.actions()[0].text() == "Create as"                              # le bouton et le clic droit s'y adaptent


def test_the_button_follows_a_linked_source_too(qapp):
    spy = _Spy()
    root = _tree()
    art = root.children[0]
    art.children[0] = disk_tree.DiskNode("hero.png", BASE / "Art" / "hero.png", disk_tree.LINKED_SOURCE, "hero", "sprites")
    view = DiskView()
    view.resize(700, 300)
    view.set_tree(root)
    view.set_callbacks(spy.callbacks())
    view.show()
    view._enter(_row(view, "Art"))

    _select(view, "hero.png")

    assert view._btn_create.isVisibleTo(view) and view._btn_create.text() == "Create"


def test_a_project_json_offers_edit_externally_to_the_text_editor(qapp):
    opened = []
    spy = _Spy()
    callbacks = spy.callbacks()
    callbacks.edit_externally = opened.append
    texts = _tree().children[0].children[-1]
    scene = next(n for n in _tree().children[0].children if n.family == "scenes")

    menu = QMenu()
    add_asset_actions(menu, [texts], callbacks)
    entry = next(a for a in menu.actions() if a.text() == "Edit externally")
    entry.trigger()
    assert opened == [texts.path]

    for nodes, cb in (([scene], callbacks), ([texts], spy.callbacks())):      # un autre asset ; ou aucun éditeur câblé
        menu = QMenu()
        add_asset_actions(menu, nodes, cb)
        assert all(a.text() != "Edit externally" for a in menu.actions())


def test_the_menu_ends_with_reveal_then_delete_and_delete_names_no_count_for_one(qapp):
    spy = _Spy()
    callbacks = spy.callbacks()
    one, two = _tree().children[0].children[4], _tree().children[0].children[5]
    for nodes, delete_text in (([one], "Delete"), ([one, two], "Delete 2 items")):
        menu = QMenu()
        add_asset_actions(menu, nodes, callbacks)
        texts = [a.text() for a in menu.actions() if not a.isSeparator()]
        assert texts[-1] == delete_text
        assert ("Reveal in file manager" in texts) == (len(nodes) == 1)
        if len(nodes) == 1:
            assert texts[-2] == "Reveal in file manager"
