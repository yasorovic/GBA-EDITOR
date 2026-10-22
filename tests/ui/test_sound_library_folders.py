"""Dossiers d'auteur dans le Sound library : effets, musiques et jingles se rangent comme les scènes.

Le « + » d'une famille rangeable offre deux gestes — un asset, un dossier — donc un choix : il prend l'icône
« + ▾ ». Les dossiers vivent dans le store PARTAGÉ de la session (celui des scènes), par famille : un dossier
d'effets n'apparaît pas chez les musiques, et un son reste dans son dossier quand on le renomme.
"""
from __future__ import annotations

import pytest

from core.asset_folder_store import AssetFolderStore
from core.project import Project
from ui.common.asset_library import AssetLibrary, _ROLE_FOLDER
from ui.common.asset_kinds import JINGLES, MUSIC, SFX


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


@pytest.fixture
def library(qapp, project) -> AssetLibrary:
    f = AssetLibrary("Sound library", [SFX, MUSIC, JINGLES])
    f.load_project(project)
    return f


def _folders_shown(library: AssetLibrary, kind) -> list[str]:
    tree = library._trees[kind.label]
    names, stack = [], [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    while stack:
        item = stack.pop()
        if item.data(0, _ROLE_FOLDER) is not None:
            names.append(item.text(0))
        stack.extend(item.child(i) for i in range(item.childCount()))
    return sorted(names)


def _menu_texts(menu) -> list[str]:
    return [action.text() for action in menu.actions()]


def test_les_trois_familles_sonores_declarent_leur_rangement():
    assert (SFX.folder_family, MUSIC.folder_family, JINGLES.folder_family) == ("sfx", "music", "jingles")


def test_le_plus_prend_l_icone_a_menu_des_que_le_rangement_est_actif(library, project):
    for kind in (SFX, MUSIC, JINGLES):
        assert library._sections[kind.label]._btn_add._icon_name == "add"       # un seul geste : un « + » nu
    library.set_folder_store(AssetFolderStore(project.root))
    for kind in (SFX, MUSIC, JINGLES):
        assert library._sections[kind.label]._btn_add._icon_name == "add_menu"  # deux gestes : « + ▾ »


def test_le_menu_du_plus_propose_un_asset_ou_un_dossier(library, project):
    library.set_folder_store(AssetFolderStore(project.root))
    cases = ((SFX, "Add an SFX"), (MUSIC, "Add a track"), (JINGLES, "Add a jingle"))
    for kind, add_text in cases:
        menu = library._add_menu(kind, library.folder_scheme(kind.label))
        assert _menu_texts(menu) == [add_text, "New folder"]


def test_nouveau_dossier_cree_un_dossier_de_la_famille_et_l_ouvre_en_renommage(library, project):
    store = AssetFolderStore(project.root)
    library.set_folder_store(store)
    menu = library._add_menu(MUSIC, library.folder_scheme(MUSIC.label))
    next(a for a in menu.actions() if a.text() == "New folder").trigger()
    assert len(store.folders("music")) == 1
    assert len(_folders_shown(library, MUSIC)) == 1
    assert store.folders("sfx") == [] and _folders_shown(library, SFX) == []     # une autre famille ne voit rien


def test_ajouter_un_asset_depuis_le_menu_marche_toujours(library, project, tmp_path, monkeypatch):
    import wave
    from PyQt6.QtWidgets import QFileDialog
    source = tmp_path / "theme.wav"                     # un son naît d'un fichier : « + » ouvre le sélecteur
    with wave.open(str(source), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(8000)
        out.writeframes(bytes(800))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(source)], ""))
    library.set_folder_store(AssetFolderStore(project.root))
    menu = library._add_menu(MUSIC, library.folder_scheme(MUSIC.label))
    next(a for a in menu.actions() if a.text() == "Add a track").trigger()
    assert len(project.music) == 1


def test_un_son_range_reste_dans_son_dossier_et_le_dossier_survit_a_la_session(library, project):
    from core.history import AddResourceCmd, get_history
    from core.models.audio import Music
    store = AssetFolderStore(project.root)
    library.set_folder_store(store)
    track = Music(name="Theme")
    track.id = "0123456789ab"
    get_history().push(AddResourceCmd(project.music, track))
    scheme = library.folder_scheme(MUSIC.label)
    folder = scheme.create("Boss", None)
    scheme.move(track, folder.id)

    track.name = "Boss theme"                                    # renommé : l'id, lui, ne change pas
    assert scheme.folder_of(track) == folder.id
    reopened = AssetFolderStore(project.root)                    # une autre session, le même fichier
    assert reopened.folder_of("music", "0123456789ab") == folder.id


def test_l_ecran_son_range_ses_familles_dans_le_store_partage(qapp, project, monkeypatch):
    from ui.sound_mixer.box_playback import BoxPlayer
    from ui.sound_mixer.sound_panel import SoundMixerScreen
    monkeypatch.setattr(BoxPlayer, "_open_sink", lambda self: None)
    screen = SoundMixerScreen()
    screen.load_project(project)
    store = AssetFolderStore(project.root)
    stale = store.create_folder("music", "Old")
    store.move_member("music", "aaaaaaaaaaaa", stale.id)         # un id qu'aucun son ne porte
    screen.set_folder_store(store)
    for kind in (SFX, MUSIC, JINGLES):
        assert screen._library.folder_scheme(kind.label) is not None
    assert store.folders("music")[0].members == ()               # le son disparu est oublié, le dossier reste


def test_le_panneau_des_scenes_expose_le_store_qu_il_possede(qapp, project):
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel
    panel = SceneLibraryPanel()
    assert panel.folder_store is None
    store = AssetFolderStore(project.root)
    panel.load_project(project)
    panel.set_folder_store(store)
    assert panel.folder_store is store
