"""Rangement des sprites : dossiers partagés, sélection stable et persistance."""
from core.asset_folder_store import AssetFolderStore
from core.models.sprite import SpriteAsset
from core.project import Project
from ui.common.asset_kinds import SPRITES
from ui.common.asset_library import _ROLE_OBJ
from ui.sprite_editor.sprite_library_panel import SpriteLibraryPanel


def test_rangement_sprite_conserve_selection_et_survit_a_la_reouverture(qapp, tmp_path):
    project = Project.create(tmp_path / "Game", "Game")
    for name in ("Hero_idle", "Hero_walk"):
        sprite = SpriteAsset(name=name)
        project.sprites.append(sprite)
        project.sprites.save(sprite)
    hero = project.sprites.get("Hero_idle")
    screen = SpriteLibraryPanel()
    screen.load_project(project)
    screen.select_sprite(hero.name)
    qapp.processEvents()
    store = AssetFolderStore(project.root)
    folder = store.create_folder("sprites", "Characters")
    child = store.create_folder("sprites", "Heroes", folder.id)
    store.move_member("sprites", "aaaaaaaaaaaa", child.id)
    screen.set_folder_store(store)
    library = screen._sprites
    tree = library._trees[SPRITES.label]
    scheme = library.folder_scheme(SPRITES.label)
    assert store.folders("sprites")[1].members == ()
    assert tree.currentItem().data(0, _ROLE_OBJ) is hero
    tree._move_many_to_folder(scheme, [hero], child.id)
    assert tree.currentItem().data(0, _ROLE_OBJ) is hero
    assert tree.currentItem().parent().text(0) == "Heroes"
    assert tree.currentItem().parent().parent().text(0) == "Characters"
    assert screen._current_sprite is hero
    assert library._sections[SPRITES.label]._btn_add._icon_name == "add_menu"
    assert scheme.rename(child.id, "Playable")
    library.refresh()
    assert tree.currentItem().parent().text(0) == "Playable"

    reopened = Project.open(project.root)
    reopened.load_all_resources()
    reopened_screen = SpriteLibraryPanel()
    reopened_screen.load_project(reopened)
    reopened_screen.set_folder_store(AssetFolderStore(project.root))
    reopened_screen.select_sprite(hero.name)
    item = reopened_screen._sprites._trees[SPRITES.label].currentItem()
    assert item.data(0, _ROLE_OBJ).id == hero.id
    assert item.parent().text(0) == "Playable"
    assert AssetFolderStore(project.root).folders("palettes") == []
    qapp.processEvents()


def test_plus_sprites_propose_import_et_nouveau_dossier(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMenu
    from ui.common.labels import label
    project = Project.create(tmp_path / "Game", "Game")
    screen = SpriteLibraryPanel()
    screen.load_project(project)
    store = AssetFolderStore(project.root)
    screen.set_folder_store(store)
    imported = []
    monkeypatch.setattr(screen, "_import_sprite", lambda: imported.append(True))

    def choose(menu, *_):
        actions = menu.actions()
        assert [a.text() for a in actions] == [
            label(SPRITES.add_tooltip_key), label("assetlibrary.new_folder")]
        actions[0].trigger()
        actions[1].trigger()

    monkeypatch.setattr(QMenu, "exec", choose)
    screen._sprites.add_requested.emit(SPRITES.label)
    assert imported == [True]
    assert len(store.folders("sprites")) == 1
