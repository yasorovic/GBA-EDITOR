"""Supprimer un élément puis en recréer un du même nom ne doit pas faire effacer
le remplaçant à la fermeture (`commit_all_removals`)."""
from pathlib import Path

from core.models.scene import Scene
from core.project import Project


def test_recreated_scene_survives_closing(tmp_path: Path):
    project = Project.create(tmp_path / "Game", "Game")
    for folder in (project.assets_dir,):
        folder.mkdir(parents=True, exist_ok=True)
    project.scenes.soft_delete(project.scenes[0])

    replacement = Scene(name="Scene_01")
    replacement.notes = "mon travail"
    project.scenes.append(replacement)
    project.save_scene(replacement)

    project.commit_all_removals()

    reopened = Project.open(project.root)
    assert [scene.notes for scene in reopened.scenes] == ["mon travail"]


def test_a_plain_soft_delete_is_still_committed(tmp_path: Path):
    project = Project.create(tmp_path / "Game", "Game")
    for folder in (project.assets_dir,):
        folder.mkdir(parents=True, exist_ok=True)
    project.scenes.soft_delete(project.scenes[0])

    project.commit_all_removals()

    assert not (project.root / "assets" / "Scene_01.scene").exists()


def test_a_soft_deleted_background_is_not_resurrected_by_a_lookup(tmp_path: Path):
    """Le JSON d'un fond supprimé reste sur disque jusqu'à la fermeture : un
    `get` ne doit pas le relire. Il revenait dans les listes, puis était
    réécrit à la fermeture — la suppression ne tenait pas au lancement suivant."""
    from PIL import Image
    from core.models.background import BackgroundAsset

    p = Project.create(tmp_path / "Jeu", "Jeu")
    for folder in (p.assets_dir, p.assets_dir, p.assets_dir, (p.assets_dir / "scripts")):
        folder.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), (1, 2, 3)).save(p.assets_dir / "Sky.png")
    ba = BackgroundAsset(name="Sky", asset="assets/backgrounds/Sky.png")
    p.backgrounds.append(ba)
    p.backgrounds.save(ba)

    p.backgrounds.soft_delete(ba)

    assert p.backgrounds.get("Sky") is None
    assert p.backgrounds.ensure_loaded("Sky") is None
    assert [b.name for b in p.backgrounds] == []

    p.save()
    p.commit_all_removals()
    assert not (p.assets_dir / "Sky.background").exists()
    assert (p.assets_dir / "Sky.png").exists()                 # la source reste : l'asset la pointait


def test_a_restored_background_is_found_again(tmp_path: Path):
    from core.models.background import BackgroundAsset

    p = Project.create(tmp_path / "Jeu", "Jeu")
    for folder in (p.assets_dir, p.assets_dir, p.assets_dir, (p.assets_dir / "scripts")):
        folder.mkdir(parents=True, exist_ok=True)
    ba = BackgroundAsset(name="Sky", asset="assets/backgrounds/Sky.png")
    p.backgrounds.append(ba)
    p.backgrounds.save(ba)
    p.backgrounds.soft_delete(ba)
    p.backgrounds.restore(ba)
    assert p.backgrounds.get("Sky") is ba


# ── `.temp/` : la suppression déplace le fichier de l'asset (jamais sa source), Ctrl+Z le rend ──────


def _background(p, name="Sky"):
    from PIL import Image
    from core.models.background import BackgroundAsset
    Image.new("RGB", (16, 16), (1, 2, 3)).save(p.assets_dir / f"{name}.png")
    ba = BackgroundAsset(name=name, asset=f"assets/backgrounds/{name}.png")
    p.backgrounds.append(ba)
    p.backgrounds.save(ba)
    return ba


def test_deleting_moves_the_asset_file_into_temp_and_leaves_the_source(tmp_path: Path):
    p = Project.create(tmp_path / "Jeu", "Jeu")
    for folder in (p.assets_dir, p.assets_dir, p.assets_dir, (p.assets_dir / "scripts")):
        folder.mkdir(parents=True, exist_ok=True)
    ba = _background(p)
    p.backgrounds.soft_delete(ba)
    assert (p.assets_dir / "Sky.png").is_file()
    assert not (p.assets_dir / "Sky.background").exists()
    assert not (p.root / ".temp" / "assets" / "Sky.png").exists()
    assert (p.root / ".temp" / "assets" / "Sky.background").is_file()


def test_undo_puts_the_asset_file_back_where_it_was(tmp_path: Path):
    p = Project.create(tmp_path / "Jeu", "Jeu")
    for folder in (p.assets_dir, p.assets_dir, p.assets_dir, (p.assets_dir / "scripts")):
        folder.mkdir(parents=True, exist_ok=True)
    ba = _background(p)
    p.backgrounds.soft_delete(ba)
    p.backgrounds.restore(ba)
    assert (p.assets_dir / "Sky.png").is_file()
    assert (p.assets_dir / "Sky.background").is_file()
    assert not any((p.root / ".temp").rglob("Sky.*"))
    assert p.backgrounds.get("Sky") is ba


def test_closing_empties_temp_for_good(tmp_path: Path):
    p = Project.create(tmp_path / "Jeu", "Jeu")
    for folder in (p.assets_dir, p.assets_dir, p.assets_dir, (p.assets_dir / "scripts")):
        folder.mkdir(parents=True, exist_ok=True)
    p.backgrounds.soft_delete(_background(p))
    p.commit_all_removals()
    assert not (p.root / ".temp").exists()
    assert not (p.assets_dir / "Sky.background").exists()
    assert (p.assets_dir / "Sky.png").exists()


def test_opening_a_project_empties_what_a_crash_left_in_temp(tmp_path: Path):
    p = Project.create(tmp_path / "Jeu", "Jeu")
    for folder in (p.assets_dir, p.assets_dir, p.assets_dir, (p.assets_dir / "scripts")):
        folder.mkdir(parents=True, exist_ok=True)
    p.backgrounds.soft_delete(_background(p))
    reopened = Project.open(p.root)
    assert not (reopened.root / ".temp").exists()
    assert reopened.backgrounds.get("Sky") is None


def test_a_name_reused_after_deleting_does_not_collide_in_temp(tmp_path: Path):
    p = Project.create(tmp_path / "Jeu", "Jeu")
    for folder in (p.assets_dir, p.assets_dir, p.assets_dir, (p.assets_dir / "scripts")):
        folder.mkdir(parents=True, exist_ok=True)
    first = _background(p)
    p.backgrounds.soft_delete(first)
    second = _background(p)                  # même nom, nouveau fichier
    p.backgrounds.soft_delete(second)
    p.backgrounds.restore(second)
    assert (p.assets_dir / "Sky.background").is_file()
    assert (p.root / ".temp" / "assets" / "Sky.background").is_file()


def test_a_json_only_family_goes_through_temp_too(tmp_path: Path):
    from core.models.scene import Scene
    p = Project.create(tmp_path / "Jeu", "Jeu")
    for folder in (p.assets_dir, p.assets_dir, p.assets_dir, (p.assets_dir / "scripts")):
        folder.mkdir(parents=True, exist_ok=True)
    scene = Scene(name="Level")
    p.scenes.append(scene)
    p.scenes.save(scene)
    p.scenes.soft_delete(scene)
    assert not (p.assets_dir / "Level.scene").exists()
    assert (p.root / ".temp" / "assets" / "Level.scene").is_file()
    p.scenes.restore(scene)
    assert (p.assets_dir / "Level.scene").is_file()
