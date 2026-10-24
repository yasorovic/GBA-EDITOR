"""Tout sidecar commence par le même en-tête : name, id, puis source quand l'asset en a une."""
import json

from core.models.sprite import SpriteAsset
from core.models.scene import Prefab
from core.project import Project


def _keys(path):
    return list(json.loads(path.read_text(encoding="utf-8")))


def test_l_entete_est_le_meme_pour_tous_les_assets(tmp_path):
    p = Project.create(tmp_path / "Game", "Game")
    p.sprites.append(SpriteAsset(name="Hero", asset="assets/sprites/Hero.png"))
    p.prefabs.append(Prefab(name="Coin"))
    p.sprites.save_all()
    p.prefabs.save_all()
    assert _keys(p.sprites.path_of(p.sprites.get("Hero")))[:3] == ["name", "id", "source"]
    assert _keys(p.prefabs.path_of(p.prefabs.get("Coin")))[:2] == ["name", "id"]
    assert "source" not in _keys(p.prefabs.path_of(p.prefabs.get("Coin")))


def test_un_sidecar_d_avant_l_entete_se_lit_toujours(tmp_path):
    p = Project.create(tmp_path / "Game", "Game")
    p.sprites.append(SpriteAsset(name="Hero", asset="assets/sprites/Hero.png"))
    p.sprites.save_all()
    path = p.sprites.path_of(p.sprites.get("Hero"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["asset"] = data.pop("source")
    path.write_text(json.dumps(data), encoding="utf-8")
    p.sprites.load()
    assert p.sprites.get("Hero").asset == "assets/sprites/Hero.png"
