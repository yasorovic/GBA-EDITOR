from core.asset_folder_store import AssetFolderStore, AssetFolder


def test_dossier_membre_persistant_par_famille(tmp_path):
    store = AssetFolderStore(tmp_path)
    folder = store.create_folder("scenes", "Village")
    assert store.move_member("scenes", "Shop", folder.id)

    reloaded = AssetFolderStore(tmp_path)
    folders = reloaded.folders("scenes")
    assert len(folders) == 1
    assert folders[0].name == "Village" and folders[0].members == ("Shop",)
    assert reloaded.folder_of("scenes", "Shop") == folder.id
    # Une autre famille est un espace de noms distinct.
    assert reloaded.folders("sprites") == []
    assert (tmp_path / "project" / "editor" / "asset-folders.json").exists()


def test_dossiers_imbricables_sans_cycle(tmp_path):
    store = AssetFolderStore(tmp_path)
    outer = store.create_folder("scenes", "Game")
    inner = store.create_folder("scenes", "Village", parent_id=outer.id)
    assert inner.parent_id == outer.id
    assert not store.set_parent("scenes", outer.id, inner.id)


def test_supprimer_un_dossier_remonte_son_contenu(tmp_path):
    store = AssetFolderStore(tmp_path)
    outer = store.create_folder("scenes", "Game")
    inner = store.create_folder("scenes", "Village", parent_id=outer.id)
    store.move_member("scenes", "Shop", inner.id)

    assert store.delete_folder("scenes", inner.id)
    assert store.folder_of("scenes", "Shop") == outer.id
    assert [f.name for f in store.folders("scenes")] == ["Game"]


def test_supprimer_un_dossier_et_son_sous_arbre_rend_les_membres(tmp_path):
    """`delete_folder_tree` retire le dossier ET tous ses descendants, et rend les
    clés membres du sous-arbre — contraste avec `delete_folder` qui les remonte."""
    store = AssetFolderStore(tmp_path)
    outer = store.create_folder("scenes", "Game")
    inner = store.create_folder("scenes", "Village", parent_id=outer.id)
    store.move_member("scenes", "Shop", inner.id)
    store.move_member("scenes", "Hub", outer.id)
    # Un dossier voisin, hors du sous-arbre : il ne doit pas bouger.
    other = store.create_folder("scenes", "Menus")
    store.move_member("scenes", "Title", other.id)

    members = store.delete_folder_tree("scenes", outer.id)

    assert sorted(members) == ["Hub", "Shop"]
    assert [f.name for f in store.folders("scenes")] == ["Menus"]
    assert store.folder_of("scenes", "Title") == other.id
    # Rien n'a été remonté : les scènes du sous-arbre ne sont plus rangées.
    assert store.folder_of("scenes", "Shop") is None
    assert store.folder_of("scenes", "Hub") is None


def test_couleur_de_dossier_persistante(tmp_path):
    store = AssetFolderStore(tmp_path)
    folder = store.create_folder("scenes", "Village")
    assert store.set_color("scenes", folder.id, "#6EA8FE")

    assert AssetFolderStore(tmp_path).folders("scenes")[0].color == "#6EA8FE"


def test_renommage_de_membre_migre_l_appartenance(tmp_path):
    store = AssetFolderStore(tmp_path)
    folder = store.create_folder("scenes", "Village")
    store.move_member("scenes", "Shop", folder.id)

    store.rename_member("scenes", "Shop", "GeneralStore")

    assert store.folder_of("scenes", "GeneralStore") == folder.id
    assert store.folder_of("scenes", "Shop") is None


def test_purge_oublie_les_membres_disparus(tmp_path):
    store = AssetFolderStore(tmp_path)
    folder = store.create_folder("scenes", "Village")
    store.move_member("scenes", "Shop", folder.id)
    store.move_member("scenes", "Ghost", folder.id)

    store.prune("scenes", {"Shop"})

    assert store.folders("scenes")[0].members == ("Shop",)


def test_dataclass_dossier_expose_les_champs(tmp_path):
    store = AssetFolderStore(tmp_path)
    folder = store.create_folder("scenes", "Village")
    assert isinstance(folder, AssetFolder)
    assert folder.parent_id is None and folder.color == ""


def test_top_ancestor_remonte_la_chaine(tmp_path):
    store = AssetFolderStore(tmp_path)
    game = store.create_folder("scenes", "Game")
    town = store.create_folder("scenes", "Town", parent_id=game.id)
    inn = store.create_folder("scenes", "Inn", parent_id=town.id)

    assert store.top_ancestor("scenes", inn.id) == game.id
    assert store.top_ancestor("scenes", game.id) == game.id
    assert store.top_ancestor("scenes", None) is None


def test_fichier_absent_donne_un_etat_vide(tmp_path):
    assert AssetFolderStore(tmp_path).folders("scenes") == []


def test_create_group_range_les_membres_et_nomme_unique(tmp_path):
    store = AssetFolderStore(tmp_path)
    first = store.create_group("scenes", "Group", ["Shop", "Inn"])
    assert first.name == "Group" and set(first.members) == {"Shop", "Inn"}
    # Un second groupe du même nom devient « Group_2 ».
    second = store.create_group("scenes", "Group")
    assert second.name == "Group_2" and second.members == ()
    # L'appartenance a bien été écrite sur disque.
    assert AssetFolderStore(tmp_path).folder_of("scenes", "Shop") == first.id


def test_create_group_retire_le_membre_de_son_dossier_actuel(tmp_path):
    store = AssetFolderStore(tmp_path)
    old = store.create_folder("scenes", "Old")
    store.move_member("scenes", "Shop", old.id)

    new = store.create_group("scenes", "Group", ["Shop"])

    assert store.folder_of("scenes", "Shop") == new.id
    assert store.folders("scenes")[0].members == ()  # Old s'est vidé


def test_create_group_sous_un_parent(tmp_path):
    store = AssetFolderStore(tmp_path)
    parent = store.create_folder("scenes", "World")
    child = store.create_group("scenes", "Group", ["Shop"], parent_id=parent.id)
    assert child.parent_id == parent.id
