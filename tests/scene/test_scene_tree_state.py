from core.scene_tree_state import SceneTreeState


def test_un_dossier_ne_modifie_que_le_sidecar_editeur(tmp_path):
    state = SceneTreeState(tmp_path)
    folder = state.create_folder("Arena", "Gameplay")
    assert state.move_member("Arena", "actor:Hero", folder.id)

    reloaded = SceneTreeState(tmp_path)
    folders = reloaded.folders("Arena")
    assert folders == [type(folder)(folder.id, "Gameplay", ("actor:Hero",))]
    assert (tmp_path / "project" / "editor" / "scene-tree.json").exists()


def test_supprimer_un_dossier_ne_supprime_pas_son_contenu(tmp_path):
    state = SceneTreeState(tmp_path)
    folder = state.create_folder("Arena", "Gameplay")
    state.move_member("Arena", "actor:Hero", folder.id)

    assert state.delete_folder("Arena", folder.id)
    assert state.folder_of("Arena", "actor:Hero") is None


def test_visibilite_editeur_persistante_et_heritee_du_dossier(tmp_path):
    state = SceneTreeState(tmp_path)
    folder = state.create_folder("Arena", "Gameplay")
    state.move_member("Arena", "actor:Hero", folder.id)
    state.set_member_visible("Arena", "camera:Main", False)
    state.set_folder_visible("Arena", folder.id, False)

    reloaded = SceneTreeState(tmp_path)
    assert not reloaded.member_visible("Arena", "actor:Hero")
    assert not reloaded.member_visible("Arena", "camera:Main")
    assert reloaded.member_visible("Arena", "ui:HUD")


def test_couleur_de_dossier_persistante(tmp_path):
    state = SceneTreeState(tmp_path)
    folder = state.create_folder("Arena", "Gameplay")

    assert state.set_folder_color("Arena", folder.id, "#6EA8FE")

    reloaded = SceneTreeState(tmp_path)
    assert reloaded.folders("Arena")[0].color == "#6EA8FE"
