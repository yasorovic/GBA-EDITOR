from core.scene_graph_state import SceneGraphState


def test_position_de_scene_persistante(tmp_path):
    state = SceneGraphState(tmp_path)
    assert state.scene_position("Title") is None
    assert state.set_scene_position("Title", 40, 20)

    reloaded = SceneGraphState(tmp_path)
    assert reloaded.scene_position("Title") == (40.0, 20.0)
    assert (tmp_path / "project" / "editor" / "scene-graph.json").exists()


def test_position_identique_ne_reecrit_pas(tmp_path):
    state = SceneGraphState(tmp_path)
    assert state.set_scene_position("Title", 10, 10)
    assert not state.set_scene_position("Title", 10, 10)


def test_re_arrange_ecrase_toutes_les_positions(tmp_path):
    state = SceneGraphState(tmp_path)
    state.set_scene_position("Title", 0, 0)
    state.set_scene_position("Old", 5, 5)
    state.replace_scene_positions({"Title": (100, 200)})

    reloaded = SceneGraphState(tmp_path)
    assert reloaded.positions() == {"Title": (100.0, 200.0)}


def test_renommage_de_scene_migre_la_position(tmp_path):
    state = SceneGraphState(tmp_path)
    state.set_scene_position("Shop", 12, 34)

    state.rename_scene("Shop", "GeneralStore")

    assert state.scene_position("GeneralStore") == (12.0, 34.0)
    assert state.scene_position("Shop") is None


def test_purge_oublie_les_scenes_disparues(tmp_path):
    state = SceneGraphState(tmp_path)
    state.set_scene_position("Shop", 1, 2)
    state.set_scene_position("Ghost", 3, 4)

    state.prune({"Shop"})

    assert state.scene_position("Ghost") is None
    assert state.scene_position("Shop") == (1.0, 2.0)


def test_presentation_de_groupe_persistante(tmp_path):
    state = SceneGraphState(tmp_path)
    assert state.group_collapsed("g1") is True          # replié par défaut
    assert state.set_group_collapsed("g1", False)
    assert state.set_group_box_position("g1", 30, 40)

    reloaded = SceneGraphState(tmp_path)
    assert reloaded.group_collapsed("g1") is False
    assert reloaded.group_box_position("g1") == (30.0, 40.0)


def test_apercu_de_scene_persistant(tmp_path):
    state = SceneGraphState(tmp_path)
    assert state.scene_preview("Title") is False           # condensé par défaut
    assert state.set_scene_preview("Title", True)
    assert not state.set_scene_preview("Title", True)       # inchangé

    assert SceneGraphState(tmp_path).scene_preview("Title") is True

    assert state.set_scene_preview("Title", False)          # retour au condensé
    assert SceneGraphState(tmp_path).scene_preview("Title") is False


def test_style_d_arete_persistant(tmp_path):
    state = SceneGraphState(tmp_path)
    assert state.edge_style("Title", "Arena") == "auto"
    assert state.set_edge_style("Title", "Arena", "curve")
    assert SceneGraphState(tmp_path).edge_style("Title", "Arena") == "curve"

    state.set_edge_style("Title", "Arena", "auto")
    assert SceneGraphState(tmp_path).edge_style("Title", "Arena") == "auto"


def test_apercu_purge_avec_la_scene_disparue(tmp_path):
    state = SceneGraphState(tmp_path)
    state.set_scene_preview("Ghost", True)
    state.set_scene_preview("Title", True)

    state.prune({"Title"})

    assert state.scene_preview("Title") is True
    assert state.scene_preview("Ghost") is False


def test_renommer_une_scene_migre_son_apercu(tmp_path):
    state = SceneGraphState(tmp_path)
    state.set_scene_preview("Shop", True)

    state.rename_scene("Shop", "GeneralStore")

    assert state.scene_preview("GeneralStore") is True
    assert state.scene_preview("Shop") is False


def test_geometrie_de_cadre_deplie_persistante(tmp_path):
    state = SceneGraphState(tmp_path)
    assert state.group_frame("g1") is None
    assert state.set_group_frame("g1", 10, 20, 300, 200)
    assert not state.set_group_frame("g1", 10, 20, 300, 200)   # identique

    assert SceneGraphState(tmp_path).group_frame("g1") == (10.0, 20.0, 300.0, 200.0)


def test_purge_oublie_les_groupes_disparus(tmp_path):
    state = SceneGraphState(tmp_path)
    state.set_group_collapsed("g1", False)
    state.set_group_collapsed("g2", False)

    state.prune(set(), {"g1"})

    assert state.group_collapsed("g1") is False   # toujours là
    assert state.group_collapsed("g2") is True    # purgé → défaut


def test_fichier_absent_donne_un_etat_vide(tmp_path):
    assert SceneGraphState(tmp_path).positions() == {}
