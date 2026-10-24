"""Tout membre d'une scène porte name, id et, s'il est l'instance d'un asset, source (l'id de cet asset)."""
import json

from core.models.background import BackgroundLayer
from core.models.scene import Actor, Prefab, Scene, WindowSlot
from core.models.camera import Camera
from core.project import Project


def _scene_json(project, scene):
    return json.loads(project.scenes.path_of(scene).read_text(encoding="utf-8"))


def _project_with_scene(tmp_path):
    p = Project.create(tmp_path / "Game", "Game")
    p.prefabs.append(Prefab(name="Coin"))
    p.prefabs.save_all()
    scene = Scene(name="Arena", actors=[Actor(name="coin_1", prefab_name="Coin"), Actor(name="Free")],
                  background_layers=[BackgroundLayer(background_name="")],
                  cameras=[Camera(name="Main")], windows=[WindowSlot(name="Hud")])
    p.scenes.append(scene)
    p.scenes.save_all()
    return p, scene


def test_chaque_membre_a_un_id_unique_et_les_instances_une_source(tmp_path):
    p, scene = _project_with_scene(tmp_path)
    data = _scene_json(p, scene)
    ids = [m["id"] for key in ("actors", "background_layers", "cameras", "windows") for m in data[key]]
    assert len(ids) == 5 and len(set(ids)) == 5
    coin, free = data["actors"]
    assert list(coin)[:3] == ["name", "id", "source"] and coin["source"] == p.prefabs.get("Coin").id
    assert "source" not in free and "prefab_name" not in coin
    assert data["background_layers"][0]["name"] == "BG0"


def test_renommer_le_prefab_ne_reecrit_pas_la_source_et_le_lien_survit(tmp_path):
    p, scene = _project_with_scene(tmp_path)
    before = _scene_json(p, scene)["actors"][0]["source"]
    p.rename_prefab(p.prefabs.get("Coin"), "Gem")
    assert _scene_json(p, scene)["actors"][0]["source"] == before
    p.scenes.load()
    from core.scene_sources import resolve_scene_sources
    resolve_scene_sources(p, p.scenes.get("Arena"))
    assert p.scenes.get("Arena").actors[0].prefab_name == "Gem"


def test_un_acteur_d_avant_l_en_tete_recoit_son_id_de_prefab(tmp_path):
    p, scene = _project_with_scene(tmp_path)
    path = p.scenes.path_of(scene)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["actors"][0]["prefab_name"] = data["actors"][0].pop("source") and "Coin"
    path.write_text(json.dumps(data), encoding="utf-8")
    p.scenes.load()
    from core.scene_sources import resolve_scene_sources
    loaded = p.scenes.get("Arena")
    resolve_scene_sources(p, loaded)
    assert loaded.actors[0].source == p.prefabs.get("Coin").id
