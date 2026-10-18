"""Une seule règle de nom libre : `coin`, `coin_2`, `coin_3`."""
from core.asset_folder_store import AssetFolderStore
from core.models.components import CollisionBoxComponent
from core.models.scene import Actor
from core.models.text import key_from_path
from core.models.unique_name import unique_name


def test_unique_name_keeps_a_free_base_and_counts_from_two():
    assert unique_name("coin", set()) == "coin"
    assert unique_name("coin", {"coin"}) == "coin_2"
    assert unique_name("coin", {"coin", "coin_2"}) == "coin_3"
    assert unique_name("coin", ["coin", "coin_3"]) == "coin_2"      # le premier trou


def test_text_keys_follow_the_same_rule():
    assert key_from_path(["Village", "Garde"]) == "Village_Garde"
    assert key_from_path(["Village", "Garde"], taken={"Village_Garde"}) == "Village_Garde_2"
    assert key_from_path([]) == "texte"
    assert key_from_path([], taken={"texte"}) == "texte_2"


def test_component_ids_follow_the_same_rule():
    actor = Actor(name="Hero")
    actor.add_component("collision_box")
    second = actor.add_component("collision_box")
    third = actor.add_component("collision_box")
    assert [c.id for c in actor.components][-3:] == ["collision", "collision_2", "collision_3"]
    assert isinstance(second, CollisionBoxComponent) and third.id == "collision_3"


def test_folder_groups_follow_the_same_rule(tmp_path):
    store = AssetFolderStore(tmp_path)
    names = [store.create_group("scenes", "Group").name for _ in range(3)]
    assert names == ["Group", "Group_2", "Group_3"]
