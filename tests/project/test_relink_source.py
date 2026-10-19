"""La source qui manque : une erreur de build par fichier, et le geste qui relie l'asset à un autre fichier."""
import wave
from pathlib import Path

import pytest
from PIL import Image

from asset_fixtures import create_all
from core import asset_relink
from core.project import Project
from core.validator import validate_project


def _wav(path: Path) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(8000)
        out.writeframes(bytes(800))


def _project(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "Jeu", "Jeu")
    for folder in ((p.assets_dir / "sprites"), (p.assets_dir / "backgrounds"), (p.assets_dir / "sfx"), (p.assets_dir / "scripts")):
        folder.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), (200, 30, 30)).save((p.assets_dir / "sprites") / "hero.png")
    _wav((p.assets_dir / "sfx") / "boom.wav")
    Image.new("RGB", (32, 32), (10, 20, 30)).save((p.assets_dir / "backgrounds") / "sky.png")
    p = Project.open(p.root)
    p.load_all_resources()
    create_all(p, ("sprites", (p.assets_dir / "sprites") / "hero.png"), ("sfx", (p.assets_dir / "sfx") / "boom.wav"),
               ("backgrounds", (p.assets_dir / "backgrounds") / "sky.png"))
    return p


def _errors(root: Path) -> list[str]:
    project = Project.open(root)
    project.load_all_resources()
    return [str(m) for m in validate_project(project)[1]]


def test_a_source_that_is_there_is_not_an_error(tmp_path: Path):
    p = _project(tmp_path)
    assert asset_relink.missing_sources(p) == []
    assert not any("source file not found" in e for e in _errors(p.root))


def test_each_missing_source_is_ONE_error_whatever_the_family(tmp_path: Path):
    p = _project(tmp_path)
    ((p.assets_dir / "sprites") / "hero.png").unlink()
    ((p.assets_dir / "sfx") / "boom.wav").unlink()
    ((p.assets_dir / "backgrounds") / "sky.png").unlink()

    errors = [e for e in _errors(p.root) if "source file not found" in e]

    assert len(errors) == 3                                                    # une par fichier, pas quatre messages par famille
    for family, name in (("Sprite", "hero"), ("SFX", "boom"), ("Background", "sky")):
        assert any(f'{family} "{name}"' in e and "relink" in e for e in errors), (family, name)


def test_relinking_a_sound_keeps_its_name_and_id_and_clears_the_error(tmp_path: Path):
    p = _project(tmp_path)
    boom = p.sfx.get("boom")
    identity, volume = boom.id, boom.volume
    ((p.assets_dir / "sfx") / "boom.wav").unlink()
    elsewhere = (p.assets_dir / "sfx") / "kept" / "explosion.wav"
    elsewhere.parent.mkdir()
    _wav(elsewhere)

    assert asset_relink.relink_source(p, "sfx", boom, elsewhere) == "asset"

    assert boom.asset == "assets/sfx/kept/explosion.wav"
    assert (boom.name, boom.id, boom.volume) == ("boom", identity, volume)
    reopened = Project.open(p.root)
    reopened.load_all_resources()
    assert reopened.sfx.get("boom").asset == "assets/sfx/kept/explosion.wav"
    assert not any("source file not found" in e for e in _errors(p.root))


def test_relinking_a_sprite_to_a_file_with_another_name_re_encodes_it_and_creates_nothing(tmp_path: Path):
    p = _project(tmp_path)
    hero = p.sprites.get("hero")
    ((p.assets_dir / "sprites") / "hero.png").unlink()
    Image.new("RGB", (16, 16), (30, 200, 40)).save((p.assets_dir / "sprites") / "hero_green.png")
    count = len(p.sprites)

    asset_relink.relink_source(p, "sprites", hero, (p.assets_dir / "sprites") / "hero_green.png")

    assert hero.asset == "assets/sprites/hero_green.png" and hero.name == "hero"
    assert len(p.sprites) == count and p.sprites.get("hero_green") is None      # pas de doublon né du nom du fichier
    assert hero.palettes                                                         # l'encodage vient du NOUVEAU fichier
    assert not any("source file not found" in e for e in _errors(p.root))


def test_relinking_a_background_to_an_image_anywhere_under_assets_re_encodes_it(tmp_path: Path):
    p = _project(tmp_path)
    sky = p.backgrounds.get("sky")
    ((p.assets_dir / "backgrounds") / "sky.png").unlink()
    elsewhere = p.assets_dir / "Levels" / "Act1" / "sunset.png"
    elsewhere.parent.mkdir(parents=True)
    Image.new("RGB", (32, 32), (200, 100, 50)).save(elsewhere)

    asset_relink.relink_source(p, "backgrounds", sky, elsewhere)

    assert sky.asset == "assets/Levels/Act1/sunset.png" and sky.name == "sky"
    assert p.background_image_path(sky) == elsewhere.resolve()
    assert not any("source file not found" in e for e in _errors(p.root))


def test_a_file_outside_the_project_cannot_be_the_source_of_a_background(tmp_path: Path):
    p = _project(tmp_path)
    sky = p.backgrounds.get("sky")
    outside = tmp_path / "elsewhere.png"
    Image.new("RGB", (32, 32), (1, 2, 3)).save(outside)
    before = sky.asset

    with pytest.raises(ValueError, match="inside the project"):
        asset_relink.relink_source(p, "backgrounds", sky, outside)
    assert sky.asset == before


def test_a_file_that_does_not_fit_is_refused_and_the_asset_is_left_alone(tmp_path: Path):
    p = _project(tmp_path)
    boom = p.sfx.get("boom")
    note = (p.assets_dir / "sfx") / "notes.txt"
    note.write_text("x", encoding="utf-8")
    broken = (p.assets_dir / "sprites") / "broken.png"
    broken.write_bytes(b"not an image")
    hero = p.sprites.get("hero")
    before = (boom.asset, hero.asset, list(hero.palettes))

    with pytest.raises(ValueError, match="not a source format"):
        asset_relink.relink_source(p, "sfx", boom, note)
    with pytest.raises(ValueError, match="could not be read"):
        asset_relink.relink_source(p, "sprites", hero, broken)
    with pytest.raises(ValueError, match="not a file"):
        asset_relink.relink_source(p, "sfx", boom, (p.assets_dir / "sfx") / "missing.wav")

    assert (boom.asset, hero.asset, list(hero.palettes)) == before


def test_the_relink_picker_lists_only_the_files_the_family_accepts(tmp_path):
    from core.asset_relink import compatible_files
    from core.project import Project
    project = Project(tmp_path)
    for rel in ("images/a.png", "deep/er/b.PNG", "sounds/c.wav", "notes.txt", "pal/d.hex"):
        target = project.assets_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")

    names = lambda family: [p.relative_to(project.assets_dir).as_posix() for p in compatible_files(project, family)]

    assert names("backgrounds") == ["deep/er/b.PNG", "images/a.png"] == names("sprites")
    assert names("sfx") == ["sounds/c.wav"] and names("palettes") == ["pal/d.hex"]


def test_a_relink_is_one_undoable_step_and_redo_does_not_reread_the_file(tmp_path: Path):
    from core.history import get_history
    from core.asset_relink import RelinkSourceCmd
    p = _project(tmp_path)
    boom = p.sfx.get("boom")
    before = boom.asset
    elsewhere = (p.assets_dir / "sfx") / "kept" / "explosion.wav"
    elsewhere.parent.mkdir()
    _wav(elsewhere)
    refreshed = []
    history = get_history()
    depth = len(history._undo)

    history.push(RelinkSourceCmd(p, "sfx", boom, elsewhere, after=lambda: refreshed.append(1)))

    assert boom.asset == "assets/sfx/kept/explosion.wav" and len(history._undo) == depth + 1
    history.undo()
    assert boom.asset == before and p.sfx.get("boom").asset == before and len(refreshed) == 2
    elsewhere.unlink()                                               # le fichier relié disparaît : le refaire n'en a pas besoin
    history.redo()
    assert boom.asset == "assets/sfx/kept/explosion.wav"


def test_a_refused_relink_leaves_no_history_entry(tmp_path: Path):
    import pytest
    from core.history import get_history
    from core.asset_relink import RelinkSourceCmd
    p = _project(tmp_path)
    notes = p.assets_dir / "notes.txt"
    notes.write_text("x")
    history = get_history()
    depth = len(history._undo)

    with pytest.raises(ValueError):
        history.push(RelinkSourceCmd(p, "sfx", p.sfx.get("boom"), notes))

    assert len(history._undo) == depth


def test_relinking_a_background_re_imports_the_image_and_keeps_the_painting(tmp_path: Path):
    from PIL import Image
    p = _project(tmp_path)
    sky = p.backgrounds.get("sky")
    sky.canvas_size, sky.image_pos, sky.image_size = (8, 8), (0, 0), (8, 8)   # réglages de l'ANCIENNE image
    sky.tile_paint = {(1, 1): (1, 0)}
    sky.tile_palette_overrides = {(2, 2): 0}
    bigger = p.assets_dir / "backgrounds" / "bigger.png"
    Image.new("P", (240, 160), 0).save(bigger)

    asset_relink.relink_source(p, "backgrounds", sky, bigger)

    assert (sky.tiles_w, sky.tiles_h) == (30, 20)                    # la taille suit la NOUVELLE image
    assert sky.canvas_size is None and sky.image_pos is None and sky.image_size is None
    assert sky.compression.is_default()
    assert sky.tile_paint == {(1, 1): (1, 0)} and sky.tile_palette_overrides == {(2, 2): 0}

