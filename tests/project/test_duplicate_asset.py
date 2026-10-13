"""*Duplicate* : une variante d'un asset, qui pointe la MÊME source avec ses propres réglages."""
import wave
from pathlib import Path

import pytest
from PIL import Image

from asset_fixtures import create
from core import asset_duplication, blank_assets
from core.history import CommandHistory, MacroCmd
from core.project import Project


def _wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(8000)
        out.writeframes(bytes(800))
    return path


def _png(path: Path, size=(16, 16)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (200, 30, 30)).save(path)
    return path


def _project(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "Jeu", "Jeu")
    p = Project.open(p.root)
    p.load_all_resources()
    return p


def _duplicate(project, family, item, history):
    duplication = asset_duplication.duplicate(project, family, item)
    history.push(duplication.command)
    return duplication.item


def test_the_copy_points_at_the_same_source_with_its_own_settings_and_identity(tmp_path: Path):
    p = _project(tmp_path)
    folder = p.assets_dir / "Anywhere"
    source = _wav(folder / "coin.wav")
    original = create(p, "sfx", source)
    original.volume = 40
    original.sample_rate = 11025
    p.sfx.save(original)
    before = source.read_bytes()

    copy = _duplicate(p, "sfx", original, CommandHistory())

    assert copy is not original and copy.name == "coin_2"
    assert copy.asset == original.asset and source.read_bytes() == before     # la source n'est ni copiée ni touchée
    assert (copy.volume, copy.sample_rate) == (40, 11025)
    assert copy.id and copy.id != original.id
    assert p.sfx.path_of(copy).parent == folder                                # à côté de l'original, pas à la racine de la famille
    copy.volume = 90                                                           # indépendante : l'original ne bouge pas
    assert original.volume == 40


def test_the_copy_survives_reopening_the_project(tmp_path: Path):
    p = _project(tmp_path)
    original = create(p, "music", _wav(p.assets_dir / "theme.wav"))
    original.add_section(0, 500, "Loop")
    p.music.save(original)

    copy = _duplicate(p, "music", original, CommandHistory())
    copy.sections[0].name = "Changed"
    p.music.save(copy)

    reopened = Project.open(p.root)
    reopened.load_all_resources()
    assert {m.name for m in reopened.music} == {"theme", "theme_2"}
    assert reopened.music.get("theme").sections[0].name == "Loop"             # les sections sont copiées en profondeur
    assert reopened.music.get("theme_2").sections[0].name == "Changed"
    assert reopened.music.get("theme_2").asset == reopened.music.get("theme").asset


def test_duplicating_a_copy_continues_the_numbering_instead_of_stacking_suffixes():
    assert asset_duplication.copy_name("coin", {"coin"}) == "coin_2"
    assert asset_duplication.copy_name("coin_2", {"coin", "coin_2"}) == "coin_3"
    assert asset_duplication.copy_name("coin", {"coin", "coin_2"}) == "coin_3"
    assert asset_duplication.copy_name("Level_1", {"Level_1"}) == "Level_1_2"   # `Level` n'existe pas : ce n'est pas une copie


def test_one_undo_removes_the_copy_and_redo_brings_it_back(tmp_path: Path):
    p = _project(tmp_path)
    original = create(p, "sfx", _wav(p.assets_dir / "coin.wav"))
    history = CommandHistory()

    copy = _duplicate(p, "sfx", original, history)
    assert [s.name for s in p.sfx] == ["coin", "coin_2"]

    history.undo()
    assert [s.name for s in p.sfx] == ["coin"]
    history.redo()
    assert {s.name for s in p.sfx} == {"coin", "coin_2"} and p.sfx.get("coin_2") is copy


def test_a_batch_is_one_history_entry_and_its_copies_do_not_collide(tmp_path: Path):
    p = _project(tmp_path)
    source = _wav(p.assets_dir / "coin.wav")
    first = create(p, "sfx", source, "coin")
    second = create(p, "sfx", source, "coin_2")
    history = CommandHistory()

    copies = asset_duplication.duplicate_many(p, "sfx", [first, second])
    history.push(MacroCmd([d.command for d in copies], "Duplicate"))

    names = [d.item.name for d in copies]
    assert len(set(names)) == 2 and not {"coin", "coin_2"} & set(names)
    assert len(p.sfx) == 4
    history.undo()
    assert [s.name for s in p.sfx] == ["coin", "coin_2"]                       # UN Ctrl+Z pour tout le lot


def test_a_sprite_copy_keeps_its_encoding_and_never_shares_the_png(tmp_path: Path):
    p = _project(tmp_path)
    source = _png(p.assets_dir / "hero.png")
    sprite = create(p, "sprites", source)
    sprite.frame_w = 8

    copy = _duplicate(p, "sprites", sprite, CommandHistory())

    assert copy.asset == sprite.asset and copy.frame_w == 8
    assert copy.palettes == sprite.palettes and copy.palettes is not sprite.palettes
    assert sorted(f.name for f in source.parent.glob("*.png")) == ["hero.png"]


def test_a_background_and_a_font_copy_point_at_the_same_image(tmp_path: Path):
    p = _project(tmp_path)
    sheet = Image.new("RGB", (128, 112), (0, 0, 0))
    for y in range(14):
        for x in range(16):
            sheet.putpixel((x * 8 + 1, y * 8 + 1), (255, 255, 255))
    (p.assets_dir / "chunky.png").parent.mkdir(parents=True, exist_ok=True)
    sheet.save(p.assets_dir / "chunky.png")
    background = create(p, "backgrounds", _png(p.assets_dir / "sky.png", (32, 32)))
    font = create(p, "fonts", p.assets_dir / "chunky.png")
    history = CommandHistory()

    for family, item in (("backgrounds", background), ("fonts", font)):
        copy = _duplicate(p, family, item, history)
        assert copy.asset == item.asset and copy.name == f"{item.name}_2"
    assert sorted(f.name for f in p.assets_dir.glob("*.png")) == ["chunky.png", "sky.png"]


def test_a_palette_copy_gets_its_own_hex_it_never_shares_the_original(tmp_path: Path):
    p = _project(tmp_path)
    store, bank = blank_assets.build_blank(p, "palette")
    from core.history import CreateAssetCmd
    history = CommandHistory()
    history.push(CreateAssetCmd(store, bank, p.palettes_dir))

    copy = _duplicate(p, "palettes", bank, history)

    assert copy.colors == bank.colors and copy.colors is not bank.colors
    assert copy.asset and copy.asset != bank.asset                              # son propre .hex
    assert p.palettes.hex_path(copy).is_file() and p.palettes.hex_path(bank).is_file()


@pytest.mark.parametrize("kind", [kind for kind, _family, _base in blank_assets.BLANK_KINDS])
def test_every_blank_asset_family_can_be_duplicated(tmp_path: Path, kind):
    p = _project(tmp_path)
    store, item = blank_assets.build_blank(p, kind)
    family = next(f for k, f, _b in blank_assets.BLANK_KINDS if k == kind)
    history = CommandHistory()
    from core.history import CreateAssetCmd
    history.push(CreateAssetCmd(store, item, None))

    copy = _duplicate(p, family, item, history)

    assert copy is not item and copy.name != item.name
    assert copy.id != item.id or family == "palettes"                          # les palettes n'ont pas encore d'id (ROADMAP, 5a)
    reopened = Project.open(p.root)
    reopened.load_all_resources()
    assert getattr(reopened, family).get(copy.name) is not None


def test_texts_and_variables_are_not_duplicable(tmp_path: Path):
    p = _project(tmp_path)
    assert not asset_duplication.is_duplicable(p, "texts")
    assert not asset_duplication.is_duplicable(p, "variables")
    assert not asset_duplication.is_duplicable(p, "scripts")                   # un fichier : `duplicate_script`
    assert {"sprites", "sfx", "scenes", "palettes", "font_assets"} <= set(asset_duplication.duplicable_families(p))


def test_a_script_copy_is_a_new_file_next_to_the_original(tmp_path: Path):
    p = _project(tmp_path)
    script = p.assets_dir / "Logic" / "boss.lua"
    script.parent.mkdir(parents=True)
    script.write_text("-- @behavior\nreturn {}\n", encoding="utf-8")
    history = CommandHistory()

    command, target = asset_duplication.duplicate_script(script, {"boss"})
    history.push(command)

    assert target == script.with_name("boss_2.lua")
    assert target.read_text(encoding="utf-8") == script.read_text(encoding="utf-8")
    history.undo()
    assert not target.exists() and script.exists()


def test_a_source_copy_is_a_free_file_next_to_the_original_and_one_undo_removes_it(tmp_path: Path):
    p = _project(tmp_path)
    folder = p.assets_dir / "Sounds"
    coin = _wav(folder / "coin.wav")
    asset = create(p, "sfx", coin)
    (folder / "coin_2.sfx").write_text("{}", encoding="utf-8")                   # un fichier d'une autre extension prend `coin_2`
    history = CommandHistory()

    command, copies = asset_duplication.duplicate_sources([coin, coin])           # le même fichier deux fois : deux copies distinctes
    history.push(command)

    assert [c.name for c in copies] == ["coin_3.wav", "coin_4.wav"]
    assert all(c.parent == folder and c.read_bytes() == coin.read_bytes() for c in copies)
    assert p.sfx.get("coin") is asset and not p.sfx.get("coin_3")                 # aucun asset ne naît : la copie est une source libre
    history.undo()
    assert not any(c.exists() for c in copies) and coin.exists()
    history.redo()
    assert all(c.exists() for c in copies)
