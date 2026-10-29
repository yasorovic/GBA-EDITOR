"""L'onglet Disk : le « + », le bouton « Create <nom> » et le clic droit (créer depuis une source, supprimer)."""
from pathlib import Path

from PyQt6.QtWidgets import QMenu

from core import disk_tree
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
            create_from_sources=lambda paths, family: self.created.extend((Path(p).name, family) for p in paths),
            delete_items=lambda nodes: self.deleted.append([n.name for n in nodes]),
            deletable=lambda node: node.family not in ("texts", "variables"),
            import_files=lambda folder: self.imported.append(folder),
            import_paths=lambda files, folder: self.imported.append(folder),
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


def test_the_button_is_hidden_for_everything_that_is_not_one_free_source(qapp):
    view, _spy = _view(qapp)

    for names in ((), ("hero.sprite",), ("notes.txt",), ("hero.png", "boom.wav"), ("boom.wav", "hero.sprite")):
        _select(view, *names)
        assert not view._btn_create.isVisibleTo(view), names                       # ni asset, ni format inconnu, ni sources sans type commun


def _texts(menu: QMenu) -> list[str]:
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def test_the_context_menu_of_one_source_creates_and_of_assets_deletes(qapp):
    spy = _Spy()
    nodes = {n.name: n for n in _tree().walk()}

    single = QMenu()
    add_asset_actions(single, [nodes["theme.hex"]], spy.callbacks())
    assert _texts(single) == ["Create", "Reveal", "Delete"]
    single.actions()[0].trigger()
    assert spy.created == [("theme.hex", "palettes")]

    ambiguous = QMenu()
    add_asset_actions(ambiguous, [nodes["hero.png"]], spy.callbacks())
    assert _texts(ambiguous) == ["Create as", "Reveal", "Delete"]
    assert [a.text() for a in ambiguous.actions()[0].menu().actions()] == ["Sprite", "Background", "Font"]

    assets = QMenu()
    add_asset_actions(assets, [nodes["hero.sprite"], nodes["Level.scene"], nodes["texts.json"]], spy.callbacks())
    assert _texts(assets) == ["Delete 2 items"]                                     # les textes ne se suppriment pas ici
    assets.actions()[0].trigger()
    assert spy.deleted == [["hero.sprite", "Level.scene"]]


def test_create_is_greyed_out_when_the_selection_has_no_type_in_common_and_says_why(qapp):
    spy = _Spy()
    nodes = {n.name: n for n in _tree().walk()}

    mixed_formats = QMenu()
    add_asset_actions(mixed_formats, [nodes["hero.png"], nodes["boom.wav"]], spy.callbacks())
    entry = mixed_formats.actions()[0]
    assert entry.text() == "Create" and not entry.isEnabled()
    assert "same type" in entry.toolTip()

    with_an_asset = QMenu()
    add_asset_actions(with_an_asset, [nodes["boom.wav"], nodes["hero.sprite"]], spy.callbacks())
    entry = with_an_asset.actions()[0]
    assert not entry.isEnabled() and "source files only" in entry.toolTip()
    assert spy.created == []


def test_several_sources_of_one_format_are_created_in_one_gesture(qapp):
    spy = _Spy()
    first = disk_tree.DiskNode("boom.wav", BASE / "boom.wav", disk_tree.FREE_SOURCE)
    second = disk_tree.DiskNode("zap.wav", BASE / "zap.wav", disk_tree.LINKED_SOURCE, "zap", "sfx")

    menu = QMenu()
    add_asset_actions(menu, [first, second], spy.callbacks())
    assert menu.actions()[0].text() == "Create as"
    assert [a.text() for a in menu.actions()[0].menu().actions()] == ["Sound effect", "Music", "Jingle"]
    menu.actions()[0].menu().actions()[1].trigger()

    assert spy.created == [("boom.wav", "music"), ("zap.wav", "music")]


def test_the_button_creates_every_selected_source_and_offers_only_shared_types(qapp):
    view, spy = _view(qapp)

    _select(view, "boom.wav", "hero.png")
    assert not view._btn_create.isVisibleTo(view)                                   # un PNG et un WAV : aucun type commun

    _select(view, "boom.wav")
    view._btn_create.click()
    assert spy.created == [("boom.wav", "sfx")]


def test_files_and_folders_can_be_deleted_but_not_the_project_tables(qapp):
    spy = _Spy()
    nodes = {n.name: n for n in _tree().walk()}
    menu = QMenu()
    add_asset_actions(menu, [nodes["notes.txt"], nodes["Art"]], spy.callbacks())
    assert _texts(menu) == ["Delete 2 items"]
    tables = QMenu()
    add_asset_actions(tables, [nodes["texts.json"]], spy.callbacks())
    assert _texts(tables) == ["Reveal"]                              # pas de Delete : seul l'emplacement s'offre


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


def test_a_source_that_already_has_an_asset_can_still_give_another(qapp):
    spy = _Spy()
    linked = disk_tree.DiskNode("hero.png", BASE / "Art" / "hero.png", disk_tree.LINKED_SOURCE, "hero", "sprites")
    menu = QMenu()

    add_asset_actions(menu, [linked], spy.callbacks())

    assert menu.actions()[0].text() == "Create as"                              # le bouton et le clic droit s'y adaptent


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




def test_a_new_folder_is_chosen_and_open_for_naming_in_the_view_that_made_it(qapp):
    from PyQt6.QtWidgets import QAbstractItemView, QLineEdit
    view, spy = _view(qapp)
    tree = _tree()
    tree.children[0].children.append(disk_tree.DiskNode("New folder", BASE / "Art" / "New folder", disk_tree.FOLDER))
    view.set_tree(tree)                                                    # on reste dans « Art »

    view.begin_rename_path(str(BASE / "Art" / "New folder"))
    qapp.processEvents()

    assert [i.text() for i in view._list.selectedItems()] == ["New folder"]
    assert view._list.state() == QAbstractItemView.State.EditingState
    editor = view._list.findChild(QLineEdit)
    assert editor is not None and editor.height() <= 22                  # une boîte à la taille du nom, pas d'un formulaire
